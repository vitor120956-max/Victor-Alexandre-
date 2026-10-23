"""Assistente lean inspirado em DietrichGebert/ponytail (MIT).

Implementação própria e determinística. Nenhum hook, plugin, comando ou script
do upstream é instalado ou executado; nenhum prompt do repositório é copiado.
As skills avaliam declarações, diffs e árvores de código coladas pelo usuário e
devolvem candidatos com evidência e limites explícitos, nunca "código pronto".
"""
from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .workspace import safe_path

SOURCE_EXTENSIONS = {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".py", ".html", ".htm", ".css"}
CODE_EXTENSIONS = SOURCE_EXTENSIONS - {".html", ".htm", ".css"}
MAX_AUDIT_FILES = 400
MAX_AUDIT_TOTAL_BYTES = 3_000_000
MAX_AUDIT_FILE_BYTES = 1_000_000
MAX_DEBT_ROWS = 500
CLONE_WINDOW = 6

NEVER_CUT = (
    "validação nas fronteiras de confiança",
    "tratamento de erro que evita perda de dados",
    "segurança",
    "acessibilidade",
    "calibração exigida por hardware real",
    "qualquer coisa que o usuário pediu",
)

_LADDER = (
    ("need", "Precisa existir?", "Corte recursos, opções e flexibilidade que ninguém pediu."),
    ("reuse", "Já existe no projeto?", "Use o helper, componente ou padrão existente do jeito que o resto do código usa."),
    ("platform", "Biblioteca padrão ou recurso nativo?", "Um componente do projeto vence um widget nativo; o nativo vence uma dependência."),
    ("dependency", "Dependência já instalada?", "Use a que existe. Nunca adicione dependência para poucas linhas."),
    ("one_liner", "Cabe em uma linha legível?", "Uma linha que o leitor entende de primeira."),
    ("minimum", "O mínimo que funciona", "Só então escreva o menor código completo, com um teste pequeno."),
)

_RISKY_LOGIC = re.compile(
    r"\b(?:if|else|for|while|switch|case|try|catch|except|finally|parse|parseInt|parseFloat|regex|regexp|Decimal|money|price|amount|cents|currency|auth|token|permission|role|sql|select\s|insert\s|update\s|delete\s|encrypt|decrypt|hash|password|sign|verify)\b",
    re.I,
)
_RISKY_ADDED = re.compile(
    r"(?:\bif\s*\(|\bif\s+[^=]|\bfor\s*\(|\bfor\s+\w+\s+in\b|\bwhile\s*\(|\bswitch\s*\(|\btry\s*[:\{]|\bcatch\s*\(|\bexcept\b|\bcase\s+[^:]+:|\b(?:parse|parseInt|parseFloat|JSON\.parse|re\.compile|re\.match|re\.search|RegExp)\b|\b(?:Decimal|money|price|amount|cents|currency)\b|\b(?:auth|token|permission|role|sql|password|encrypt|decrypt|hash)\b)",
    re.I,
)
_TEST_PATH = re.compile(r"(?:^|/)(?:tests?|__tests__|spec)/|(?:\.|-|_)test\.|(?:\.|-|_)spec\.|(?:^|/)test_[^/]+\.py$|(?:^|/)[^/]+_test\.py$", re.I)

_GUARDRAILS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("validation", "validação", re.compile(r"\b(?:validate|is_valid|isvalid|sanitize|sanitise|escape_html|escapeHtml|allowlist|whitelist|schema|reject\s*\(|assert\s|raise\s+\w*Error|throw\s+new\s+\w*Error)", re.I)),
    ("security", "segurança", re.compile(r"\b(?:csrf|cors|same_origin|sameOrigin|authenticat\w*|authoriz\w*|permission\w*|role\b|bcrypt|argon2|hmac|constant_time|timingSafe|verify_token|verifyToken|require_auth|requireAuth)", re.I)),
    ("data-loss", "proteção contra perda de dados", re.compile(r"\b(?:transaction|rollback|commit\s*\(|fsync|atomic|backup|try\b|except\b|catch\s*\(|finally\b|with\s+open\s*\()", re.I)),
    ("accessibility", "acessibilidade", re.compile(r"(?:\baria-[a-z]+|alt\s*=|role\s*=|tabIndex|tabindex|aria_[a-z]+)", re.I)),
)
_DATA_TOKENS = ("try", "except", "catch", "finally", "with open", "transaction", "rollback")

_SECURITY_PATTERNS: tuple[tuple[str, str, re.Pattern[str], str], ...] = (
    ("eval", "código avaliado em tempo de execução", re.compile(r"\b(?:eval|new\s+Function|Function)\s*\("), "must"),
    ("shell", "execução de processo ou shell", re.compile(r"\b(?:child_process|subprocess|os\.system|popen|execSync|spawnSync|shell\s*=\s*True)\b"), "must"),
    ("html", "HTML injetado como string", re.compile(r"\b(?:innerHTML|outerHTML|dangerouslySetInnerHTML|insertAdjacentHTML)\b"), "must"),
    ("secret", "segredo literal no código", re.compile(r"(?i)\b(?:api[_-]?key|apikey|secret|password|passwd|access[_-]?token)\b\s*[:=]\s*['\"][^'\"\s]{8,}['\"]"), "must"),
    ("sql", "consulta SQL montada por concatenação", re.compile(r"(?i)(?:select|insert|update|delete)\b[^\n;]{0,140}(?:\+\s*\w|\$\{|\bformat\s*\()"), "should"),
    ("pickle", "desserialização insegura", re.compile(r"\b(?:pickle\.loads|yaml\.load\s*\((?![^)]*Loader\s*=\s*yaml\.SafeLoader)|marshal\.loads)\b"), "must"),
)

_MANUAL_PATTERNS: tuple[tuple[str, str, re.Pattern[str], str], ...] = (
    ("clamp", "limite entre mínimo e máximo", re.compile(r"Math\.min\(Math\.max\("), "Math.min/Math.max já resolvem; se o projeto tiver `clamp`, use o dele."),
    ("deep-clone", "cópia profunda por serialização", re.compile(r"JSON\.parse\(\s*JSON\.stringify\("), "`structuredClone` é nativo e preserva mais tipos que JSON."),
    ("uuid", "identificador aleatório artesanal", re.compile(r"Math\.random\(\)[^\n]{0,40}toString\(16\)"), "`crypto.randomUUID()` é nativo e criptograficamente seguro."),
    ("date", "data formatada manualmente", re.compile(r"toISOString\(\)[^\n]{0,20}split\(\s*['\"]T['\"]"), "`toISOString().slice(0, 10)` é mais claro que split."),
    ("python-clamp", "limite manual em Python", re.compile(r"\bmin\(\s*\w+\s*,\s*max\("), "`min(max(x, lo), hi)` já é a forma curta."),
)

_DEPENDENCY_LINE = re.compile(r"^\s*[\"']?([@A-Za-z0-9][\w./@-]{1,80})[\"']?\s*[:=]\s*[\"']?[\^~>=<\d*]")


class LeanError(ValueError):
    """Erro esperado da análise lean, seguro para apresentar ao usuário."""


def _lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _significant(value: str) -> set[str]:
    return {word for word in re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", value)}


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _findings_summary(findings: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(finding["group"] for finding in findings)
    return {"must": counts.get("must", 0), "should": counts.get("should", 0), "nice": counts.get("nice", 0), "total": len(findings)}


def _verdict(findings: list[dict[str, Any]]) -> str:
    must = [finding["id"] for finding in findings if finding["group"] == "must"]
    if must:
        return f"Corrija {_join_ids(must)} primeiro."
    should = [finding["id"] for finding in findings if finding["group"] == "should"]
    if should:
        return f"Corrija {_join_ids(should)} antes de enviar."
    return "Pode enviar."


def _join_ids(values: list[int]) -> str:
    if len(values) == 1:
        return str(values[0])
    return f"{', '.join(str(value) for value in values[:-1])} e {values[-1]}"


# ---------------------------------------------------------------- escada


def evaluate_ladder(
    *,
    mode: str = "full",
    task: str,
    proposal: str = "",
    reuse_fit: str = "none",
    reuse_evidence: str = "",
    stdlib_fit: str = "none",
    stdlib_evidence: str = "",
    dependency_fit: str = "none",
    dependency_evidence: str = "",
    one_liner: bool = False,
    estimated_lines: int = 1,
    unrequested: str = "",
    reach: str = "",
) -> dict[str, Any]:
    if mode not in {"lite", "full", "ultra"}:
        raise LeanError("Nível inválido: use lite, full ou ultra.")
    task = task.strip()
    if not task:
        raise LeanError("Descreva a tarefa antes de avaliar a escada.")
    fits = {"reuse": reuse_fit, "platform": stdlib_fit, "dependency": dependency_fit}
    evidences = {"reuse": reuse_evidence.strip(), "platform": stdlib_evidence.strip(), "dependency": dependency_evidence.strip()}
    for name, fit in fits.items():
        if fit not in {"none", "partial", "full"}:
            raise LeanError(f"Ajuste inválido para {name}: use none, partial ou full.")

    out_of_scope = [line.strip(" -*\t") for line in _lines(unrequested) if line.strip(" -*\t")]
    reach_items = [line.strip(" -*\t") for line in _lines(reach) if line.strip(" -*\t")]
    combined = f"{task}\n{proposal}"
    risky = sorted({match.group(0).lower() for match in _RISKY_LOGIC.finditer(combined)})
    needs_test = bool(risky) or estimated_lines > 40

    rungs: list[dict[str, Any]] = []
    rungs.append({
        "key": "need",
        "label": "Cortar o que ninguém pediu",
        "status": "cut" if out_of_scope else "clear",
        "evidence": "; ".join(out_of_scope[:8]) if out_of_scope else "Nenhum recurso não pedido foi declarado.",
        "detail": "Remova esses itens antes de avaliar os próximos degraus." if out_of_scope else "O pedido não declarou excesso de escopo.",
    })

    decision: dict[str, Any] | None = None
    ladder_map = {key: (label, detail) for key, label, detail in _LADDER}
    for key in ("reuse", "platform", "dependency"):
        fit = fits[key]
        label, detail = ladder_map[key]
        if fit == "full" and decision is None:
            status = "holds"
            decision = {"key": key, "label": label, "rung": {"reuse": 2, "platform": 3, "dependency": 4}[key], "evidence": evidences[key] or "Evidência não declarada."}
        elif fit == "partial":
            status = "partial"
        elif fit == "full":
            status = "lower" if decision else "holds"
        else:
            status = "skipped"
        rungs.append({
            "key": key,
            "label": label,
            "status": status if status != "lower" else "available",
            "evidence": evidences[key] or ("Cobertura parcial declarada." if fit == "partial" else "Não disponível."),
            "detail": detail,
        })

    one_liner_holds = bool(one_liner) and estimated_lines <= 1 and decision is None
    if one_liner_holds:
        decision = {"key": "one_liner", "label": ladder_map["one_liner"][0], "rung": 5, "evidence": "Uma linha legível resolve o pedido."}
    rungs.append({
        "key": "one_liner",
        "label": ladder_map["one_liner"][0],
        "status": "holds" if one_liner_holds else ("skipped" if not one_liner else "partial"),
        "evidence": "Declarado como uma linha." if one_liner else "Não cabe em uma linha.",
        "detail": ladder_map["one_liner"][1],
    })
    if decision is None:
        decision = {"key": "minimum", "label": ladder_map["minimum"][0], "rung": 6, "evidence": f"Mínimo necessário, estimado em {estimated_lines} linhas."}
    rungs.append({
        "key": "minimum",
        "label": ladder_map["minimum"][0],
        "status": "holds" if decision["key"] == "minimum" else "fallback",
        "evidence": f"{estimated_lines} linhas estimadas.",
        "detail": ladder_map["minimum"][1],
    })

    warnings: list[str] = []
    for key, evidence in evidences.items():
        if fits[key] in {"full", "partial"} and not evidence:
            warnings.append(f"Declare a evidência de {key}: sem caminho ou fato concreto, o degrau não pode ser confirmado.")
    if estimated_lines > 400:
        warnings.append("A estimativa passa de 400 linhas: confirme se a tarefa não está maior do que o pedido original.")
    if one_liner and estimated_lines > 1:
        warnings.append("Uma linha foi declarada, mas a estimativa passa de 1 linha; os dois campos se contradizem.")

    questions: list[str] = []
    if mode == "ultra":
        questions = [f"O pedido justifica: {item}?" for item in out_of_scope]
        if not out_of_scope:
            questions.append("O pedido justifica cada requisito acima? Se algo não tem uso previsto, corte agora.")
        if estimated_lines > 60:
            questions.append("A estimativa é a menor possível para o fluxo real, ou inclui flexibilidade futura?")
    elif mode == "lite" and out_of_scope:
        questions = [f"Opção menor: deixe de fora {item}." for item in out_of_scope[:1]]

    markdown_lines = [
        "# Decisão lean",
        "",
        f"**Tarefa:** {task}",
        f"**Nível:** {mode}",
        f"**Decisão:** degrau {decision['rung']} — {decision['label']}",
    ]
    if decision["evidence"]:
        markdown_lines.append(f"**Evidência:** {decision['evidence']}")
    markdown_lines += ["", "## Degraus", "", "| # | Degrau | Situação | Evidência |", "|---|---|---|---|"]
    status_label = {"holds": "**segura**", "available": "disponível", "partial": "parcial", "skipped": "não", "clear": "—", "cut": "cortar", "fallback": "fallback"}
    for index, rung in enumerate(rungs, start=1):
        markdown_lines.append(f"| {index} | {rung['label']} | {status_label.get(rung['status'], rung['status'])} | {rung['evidence'].replace('|', '/')} |")
    markdown_lines += ["", "## Nunca cortar", ""]
    markdown_lines += [f"- {item}." for item in NEVER_CUT]
    markdown_lines += ["", "## Obrigação de teste", ""]
    if needs_test:
        reason = ", ".join(risky[:6]) if risky else "o tamanho estimado indica lógica não trivial"
        markdown_lines.append(f"**Sim.** Deixe um teste pequeno que falha se a regra quebrar ({reason}).")
    else:
        markdown_lines.append("**Não.** A mudança declarada é trivial; não invente teste para inflar a entrega.")
    if reach_items:
        markdown_lines += ["", "## Alcance da mudança", ""]
        markdown_lines += [f"- {item}" for item in reach_items[:20]]
    if out_of_scope:
        markdown_lines += ["", "## Fora de escopo", ""]
        markdown_lines += [f"- {item}" for item in out_of_scope[:20]]
    if questions:
        markdown_lines += ["", "## Perguntas antes de construir" if mode == "ultra" else "## Opção menor", ""]
        markdown_lines += [f"- {question}" for question in questions]
    if warnings:
        markdown_lines += ["", "## Avisos", ""]
        markdown_lines += [f"- {warning}" for warning in warnings]
    markdown_lines += [
        "",
        "## Atalho, se houver",
        "",
        "Se a entrega tiver um limite conhecido, registre no código:",
        "",
        "`shortcut: <o limite>, <quando revisar>`",
        "",
        "Sem um gatilho escrito, a dívida vira permanente. A skill `lean.debt` coleta esses marcadores.",
    ]
    markdown_lines += [
        "",
        "## Não verificado",
        "",
        "- Leitura do código real, chamadores e testes: esta avaliação usa apenas as declarações acima.",
        "- Carga esperada e comportamento em produção não foram medidos.",
    ]

    return {
        "analysis": "ladder",
        "mode": mode,
        "task": task,
        "decision": decision,
        "rungs": rungs,
        "neverCut": list(NEVER_CUT),
        "testObligation": {"required": needs_test, "riskySignals": risky[:10]},
        "outOfScope": out_of_scope,
        "reach": reach_items,
        "questions": questions,
        "warnings": warnings,
        "executed": False,
        "readOnly": True,
        "markdown": "\n".join(markdown_lines),
        "limitations": [
            "A escada avalia o que foi declarado; ela não lê o repositório nem confirma que o helper citado existe.",
            "A decisão indica o menor caminho declarado, não uma aprovação de arquitetura.",
        ],
    }


# ---------------------------------------------------------------- diff


def _parse_diff(text: str) -> dict[str, Any]:
    added: list[dict[str, Any]] = []
    removed: list[dict[str, Any]] = []
    files: list[str] = []
    current: dict[str, str] = {"old": "", "new": ""}
    new_line = old_line = 0
    in_hunk = False
    saw_header = False
    for raw in _lines(text):
        if raw.startswith("diff --git "):
            match = re.match(r"diff --git a/(.+?) b/(.+)$", raw)
            current = {"old": match.group(1) if match else current["old"], "new": match.group(2) if match else current["new"]}
            if current["new"] and current["new"] not in files:
                files.append(current["new"])
            saw_header = True
            in_hunk = False
            continue
        if raw.startswith("--- "):
            saw_header = True
            value = raw[4:].strip()
            current["old"] = "" if value == "/dev/null" else re.sub(r"^[ab]/", "", value)
            continue
        if raw.startswith("+++ "):
            value = raw[4:].strip()
            current["new"] = "" if value == "/dev/null" else re.sub(r"^[ab]/", "", value)
            if current["new"] and current["new"] not in files:
                files.append(current["new"])
            continue
        if raw.startswith("@@"):
            match = re.match(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw)
            if not match:
                raise LeanError("Cabeçalho de trecho (@@) inválido no diff.")
            old_line, new_line = int(match.group(1)), int(match.group(2))
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            added.append({"path": current["new"] or "(sem caminho)", "line": new_line, "text": raw[1:]})
            new_line += 1
        elif raw.startswith("-") and not raw.startswith("---"):
            removed.append({"path": current["old"] or current["new"] or "(sem caminho)", "line": old_line, "text": raw[1:]})
            old_line += 1
        elif raw.startswith("\\"):
            continue
        else:
            old_line += 1
            new_line += 1

    input_mode = "diff"
    if not saw_header:
        input_mode = "snippet"
        files = ["(trecho)"]
        added = [{"path": "(trecho)", "line": index, "text": line} for index, line in enumerate(_lines(text), start=1) if line.strip()]
        removed = []

    if not added and not removed:
        raise LeanError("O diff não contém linhas adicionadas ou removidas para revisar.")
    return {"added": added, "removed": removed, "files": files, "input": input_mode}


def _guardrail_matches(line: str) -> list[tuple[str, str]]:
    return [(category, label) for category, label, pattern in _GUARDRAILS if pattern.search(line)]


def _security_matches(line: str) -> list[tuple[str, str, str]]:
    return [(key, label, group) for key, label, pattern, group in _SECURITY_PATTERNS if pattern.search(line)]


def _duplicate_blocks(added: list[dict[str, Any]], window: int = CLONE_WINDOW) -> list[dict[str, Any]]:
    by_path: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    for item in added:
        normalized = _norm(item["text"])
        if normalized and not normalized.startswith(("//", "#", "/*", "*")):
            by_path[item["path"]].append((item["line"], normalized, item["text"]))
    buckets: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for path, rows in by_path.items():
        for index in range(len(rows) - window + 1):
            chunk = rows[index:index + window]
            key = tuple(row[1] for row in chunk)
            buckets[key].append({"path": path, "start": chunk[0][0], "end": chunk[-1][0]})
    clones: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for key, occurrences in buckets.items():
        paths = {occurrence["path"] for occurrence in occurrences}
        if len(paths) < 2 and len(occurrences) < 2:
            continue
        first = occurrences[0]
        marker = (first["path"], first["start"])
        if marker in seen:
            continue
        seen.add(marker)
        clones.append({
            "occurrences": occurrences[:6],
            "lines": window,
            "sample": key[0],
            "extraCopies": len(occurrences) - 1,
        })
    clones.sort(key=lambda clone: clone["extraCopies"] * clone["lines"], reverse=True)
    return clones[:8]


def _manifest_dependencies(added: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for item in added:
        path = item["path"].lower()
        if not path.endswith(("package.json", "requirements.txt", "pyproject.toml", "cargo.toml", "go.mod", "composer.json", "gemfile")):
            continue
        text = item["text"].strip()
        if not text or text.startswith(("//", "#")):
            continue
        if path.endswith("requirements.txt"):
            name = re.match(r"^([A-Za-z0-9][\w.-]{1,60})", text)
            if name:
                findings.append({"name": name.group(1), "path": item["path"], "line": item["line"], "raw": text})
            continue
        match = _DEPENDENCY_LINE.match(item["text"])
        if not match:
            continue
        name = match.group(1)
        if name.lower() in {"name", "version", "main", "type", "license", "description", "private", "scripts", "engines", "node", "style", "module", "exports", "files", "homepage", "repository", "keywords", "author", "package", "python", "edition", "dependencies", "devdependencies"}:
            continue
        findings.append({"name": name, "path": item["path"], "line": item["line"], "raw": text})
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for finding in findings:
        unique.setdefault((finding["name"], finding["path"]), finding)
    return list(unique.values())[:12]


def review_change(*, diff: str, mode: str = "full", notes: str = "") -> dict[str, Any]:
    if mode not in {"lite", "full", "ultra"}:
        raise LeanError("Nível inválido: use lite, full ou ultra.")
    if len(diff) > 200_000:
        raise LeanError("O diff excede 200.000 caracteres; revise em partes.")
    parsed = _parse_diff(diff)
    added = parsed["added"]
    removed = parsed["removed"]
    files = parsed["files"]
    added_by_path: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in added:
        added_by_path[item["path"]].append(item)
    removed_by_path: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in removed:
        removed_by_path[item["path"]].append(item)
    added_norms = {_norm(item["text"]) for item in added if _norm(item["text"])}
    added_blob = "\n".join(item["text"] for item in added)
    removed_blob = "\n".join(item["text"] for item in removed)
    test_paths = [path for path in files if _TEST_PATH.search(path)]
    risky_added = [item for item in added if _RISKY_ADDED.search(item["text"])]

    findings: list[dict[str, Any]] = []

    def add_finding(group: str, kind: str, title: str, location: str, what: str, problem: str, fix: str, if_skipped: str, estimated: int = 0) -> None:
        findings.append({
            "id": len(findings) + 1,
            "group": group,
            "kind": kind,
            "title": title,
            "location": location,
            "what": what,
            "problem": problem,
            "fix": fix,
            "ifSkipped": if_skipped,
            "estimatedLines": estimated,
        })

    # 1. Proteções removidas sem substituto (agrupadas por arquivo e categoria).
    risk_phrase = {
        "validation": "entrada inválida",
        "security": "acesso indevido",
        "data-loss": "perda de dados",
        "accessibility": "barreira de acessibilidade",
    }
    removed_guardrails: dict[tuple[str, str], dict[str, Any]] = {}
    for item in removed:
        categories = _guardrail_matches(item["text"])
        if not categories:
            continue
        normalized = _norm(item["text"])
        if normalized in added_norms:
            continue
        category, label = categories[0]
        identifiers = _significant(item["text"])
        if identifiers and all(identifier in added_blob for identifier in identifiers):
            continue
        if category == "data-loss" and any(token in added_blob.lower() for token in _DATA_TOKENS):
            continue
        key = (item["path"], category)
        entry = removed_guardrails.get(key)
        if entry is None or item["line"] - entry["lines"][-1] > 12:
            removed_guardrails[key] = {"category": category, "label": label, "path": item["path"], "lines": [item["line"]], "samples": [item["text"].strip()[:160]]}
        else:
            entry["lines"].append(item["line"])
            if len(entry["samples"]) < 3:
                entry["samples"].append(item["text"].strip()[:160])
    for entry in removed_guardrails.values():
        start, end = entry["lines"][0], entry["lines"][-1]
        location = f"{entry['path']}:{start}" if start == end else f"{entry['path']}:{start}-{end}"
        samples = " / ".join(f"`{sample}`" for sample in entry["samples"])
        add_finding(
            "must",
            "removed-guardrail",
            f"Possível remoção de {entry['label']}",
            location,
            f"Linhas removidas: {samples}.",
            f"Elas cobriam {risk_phrase.get(entry['category'], entry['label'])}; o diff não mostra substituto equivalente.",
            "Restaure a checagem ou mostre no diff a linha que assume a mesma função.",
            f"O caminho fica exposto a {risk_phrase.get(entry['category'], entry['label'])} sem aviso; o problema aparece depois, em produção.",
        )

    # 2. Risco novo no código adicionado.
    removed_pattern_keys = {key for item in removed for key, _label, _group in _security_matches(item["text"])}
    for item in added:
        matches = _security_matches(item["text"])
        for key, label, group in matches:
            if key in removed_pattern_keys:
                continue
            if any(finding["kind"] == f"risk:{key}" for finding in findings):
                continue
            group_name = "must" if group == "must" else "should"
            add_finding(
                group_name,
                f"risk:{key}",
                f"Risco novo: {label}",
                f"{item['path']}:{item['line']}",
                f"Linha adicionada: `{item['text'].strip()[:160]}`.",
                "O padrão aparece pela primeira vez nesta mudança e depende de dados em tempo de execução.",
                "Confirme a origem dos dados. Use a API segura do projeto (consulta parametrizada, sanitização, `spawn` sem shell).",
                "Se a entrada vier de usuário ou rede, vira execução de código, injeção ou vazamento de credencial.",
            )

    # 3. Lógica arriscada sem teste.
    if risky_added and not test_paths:
        sample = risky_added[0]
        add_finding(
            "should",
            "missing-test",
            "Lógica arriscada sem teste no diff",
            f"{sample['path']}:{sample['line']}",
            f"Foram adicionadas {len(risky_added)} linhas com ramo, laço, parse, dinheiro ou segurança, e nenhum arquivo de teste aparece no diff.",
            "A regra nova não tem uma verificação que falhe quando ela quebrar.",
            "Adicione um teste pequeno para o caso principal e um caso de borda (vazio, zero, último item).",
            "A próxima mudança pode quebrar a regra sem que ninguém perceba até o relatório do usuário.",
        )

    # 4. Duplicação de blocos adicionados.
    for clone in _duplicate_blocks(added):
        first = clone["occurrences"][0]
        others = ", ".join(f"{item['path']}:{item['start']}" for item in clone["occurrences"][1:4])
        add_finding(
            "should",
            "duplication",
            "Blocos iguais adicionados em mais de um lugar",
            f"{first['path']}:{first['start']}",
            f"{clone['lines']} linhas normalizadas se repetem {clone['extraCopies'] + 1} vezes ({others}).",
            "Cópias que precisam mudar juntas divergem na primeira correção.",
            "Extraia uma função ou use a que já existe; mantenha uma definição só.",
            "Uma correção futura entra em uma cópia e esquece a outra.",
            estimated=clone["lines"] * clone["extraCopies"],
        )

    # 5. Dependências novas.
    for dependency in _manifest_dependencies(added):
        add_finding(
            "should",
            "new-dependency",
            f"Nova dependência: {dependency['name']}",
            f"{dependency['path']}:{dependency['line']}",
            f"O diff adiciona `{dependency['raw'][:120]}`.",
            "Uma dependência nova custa leitura, atualização e superfície de ataque.",
            "Confirme se a biblioteca padrão, o navegador ou uma dependência já instalada cobrem o caso.",
            "Você herda versões, vulnerabilidades e um pacote a mais para manter.",
        )

    # 6. Reimplementação da biblioteca padrão.
    seen_manual: set[str] = set()
    for item in added:
        for key, label, pattern, hint in _MANUAL_PATTERNS:
            if key in seen_manual or not pattern.search(item["text"]):
                continue
            seen_manual.add(key)
            add_finding(
                "should",
                f"manual:{key}",
                f"Forma longa para {label}",
                f"{item['path']}:{item['line']}",
                f"Linha adicionada: `{item['text'].strip()[:160]}`.",
                "A plataforma já oferece essa operação em uma forma mais curta e testada.",
                hint,
                "Mais linhas para ler e manter, com os casos de borda por sua conta.",
                estimated=2,
            )

    # 7. Wrapper de uso único.
    for item in added:
        stripped = item["text"].strip()
        if re.match(r"(?:export\s+)?(?:async\s+)?function\s+\w+\s*\([^)]*\)\s*\{\s*return\s+[\w.$]+\([^;]*\);\s*\}$", stripped):
            add_finding(
                "should",
                "single-use-wrapper",
                "Função que só repassa a chamada",
                f"{item['path']}:{item['line']}",
                f"`{stripped[:140]}` apenas devolve outra chamada.",
                "A camada extra não acrescenta regra, validação nem nome melhor.",
                "Chame a função de baixo diretamente no ponto de uso e apague a intermediação.",
                "Cada leitor precisa abrir dois lugares para entender uma chamada.",
                estimated=3,
            )

    # 8. Configuração adicionada sem outro leitor.
    env_names = {match for match in re.findall(r"(?:process\.env\.([A-Z][A-Z0-9_]{2,})|getenv\(\s*[\"']([A-Z][A-Z0-9_]{2,})[\"']\s*\))", added_blob) for match in match if match}
    for name in sorted(env_names):
        occurrences = len(re.findall(rf"\b{re.escape(name)}\b", added_blob))
        if occurrences <= 1:
            add_finding(
                "should",
                "unused-config",
                f"Configuração lida em um único ponto: {name}",
                "(diff)",
                f"`{name}` aparece uma vez no código adicionado.",
                "Opção que ninguém mais lê é flexibilidade sem uso.",
                "Fixe o valor no código até existir um segundo consumidor de verdade.",
                "Você mantém, documenta e testa uma opção que nunca varia.",
                estimated=2,
            )

    # 9. Abstração nova com uma implementação.
    interfaces = re.findall(r"(?:export\s+)?(?:interface|abstract\s+class)\s+(\w+)", added_blob)
    implements = re.findall(r"\bimplements\s+[\w, ]+", added_blob)
    for name in sorted(set(interfaces)):
        if not implements:
            add_finding(
                "nice",
                "yagni",
                f"Abstração sem segunda implementação: {name}",
                "(diff)",
                f"`{name}` foi adicionado sem outra implementação no diff.",
                "Contrato com um único implementador costuma ser antecipação.",
                "Use o tipo concreto até existir a segunda implementação.",
                "Uma camada a mais para navegar em cada leitura.",
                estimated=4,
            )

    findings.sort(key=lambda finding: {"must": 0, "should": 1, "nice": 2}[finding["group"]])
    for index, finding in enumerate(findings, start=1):
        finding["id"] = index
    if mode == "lite":
        findings = [finding for finding in findings if finding["group"] == "must"]

    lean_lines = sum(finding["estimatedLines"] for finding in findings if finding["estimatedLines"])
    lean_dependencies = sum(1 for finding in findings if finding["kind"] == "new-dependency")
    counts = _findings_summary(findings)
    verdict = _verdict(findings)
    added_count = len(added)
    removed_count = len(removed)

    markdown_lines = [
        "# Revisão lean",
        "",
        f"**Resumo mecânico:** {len(files)} arquivo(s), +{added_count}/-{removed_count} linhas"
        + (f", com teste tocado ({', '.join(test_paths[:3])})" if test_paths else ", sem teste no diff")
        + f". Nível {mode}.",
    ]
    if notes.strip():
        markdown_lines += ["", f"**Contexto informado:** {notes.strip()[:800]}"]
    if counts["total"] == 0:
        markdown_lines += ["", "Nada encontrado nas regras estáticas. Revise o diff completo antes de enviar."]
    group_labels = {"must": "Corrigir obrigatoriamente", "should": "Corrigir antes de enviar", "nice": "Opcional"}
    for group in ("must", "should", "nice"):
        group_findings = [finding for finding in findings if finding["group"] == group]
        if not group_findings:
            continue
        markdown_lines += ["", f"## {group_labels[group]}", ""]
        for finding in group_findings:
            markdown_lines += [
                f"{finding['id']}. **{finding['title']}** (`{finding['location']}`)",
                f"   - **O que é:** {finding['what']}",
                f"   - **Problema:** {finding['problem']}",
                f"   - **Correção:** {finding['fix']}",
                f"   - **Se ignorar:** {finding['ifSkipped']}",
                "",
            ]
    markdown_lines += ["", f"**Veredito:** {verdict}"]
    if lean_lines:
        markdown_lines.append(f"**Lean:** até -{lean_lines} linhas possíveis (estimativa).")
    if lean_dependencies:
        markdown_lines.append(f"**Lean:** -{lean_dependencies} dependência(s) possível(is).")
    markdown_lines += [
        "",
        "**Não verificado:** chamadores e código fora do diff, execução real, carga esperada, testes não executados e regras de negócio.",
    ]

    return {
        "analysis": "review",
        "mode": mode,
        "input": parsed["input"],
        "files": files,
        "addedLines": added_count,
        "removedLines": removed_count,
        "testFilesTouched": test_paths,
        "findings": findings,
        "counts": counts,
        "verdict": verdict,
        "leanLines": lean_lines,
        "leanDependencies": lean_dependencies,
        "executed": False,
        "readOnly": True,
        "markdown": "\n".join(markdown_lines),
        "limitations": [
            "As regras são estáticas: um achado é candidato e exige confirmação no código real.",
            "Sem executar testes ou medir carga, esta revisão não afirma que a mudança funciona.",
        ],
    }


# ---------------------------------------------------------------- dívida


_MARKER_LINE = re.compile(
    r"^\s*(?://+|#+|/\*+|\*+|--+|;+|<!--)\s*(?P<marker>[A-Za-z][A-Za-z0-9_-]*)\s*:\s*(?P<body>.*?)\s*(?:\*/)?\s*$"
)
_VAGUE_TRIGGERS = {"later", "future", "some day", "someday", "eventually", "todo", "tbd", "never", "depois", "futuro", "algum dia", "nunca"}
_FILE_HEADER = re.compile(r"^(?:={2,}\s*|\#{3,}\s*)(?P<path>[^\s=#][^\n]*?)\s*(?:={2,})?$")


def _debt_rows(text: str, marker: str, include_legacy: bool) -> list[dict[str, Any]]:
    markers = {marker.lower()} | ({"ponytail"} if include_legacy else set())
    rows: list[dict[str, Any]] = []
    current_file = "(trecho colado)"
    for index, raw in enumerate(_lines(text), start=1):
        header = _FILE_HEADER.match(raw.strip())
        if header and not raw.strip().startswith(("//", "#!", "# ")) and ("/" in header.group("path") or "." in header.group("path")):
            current_file = header.group("path").strip()
            continue
        match = _MARKER_LINE.match(raw)
        if not match or match.group("marker").lower() not in markers:
            continue
        lowered = raw.lower()
        if "keyboard" in lowered or "tecla" in lowered:
            continue
        body = match.group("body").strip().rstrip("*/").strip()
        if not body:
            continue
        ceiling, upgrade = body, ""
        if "," in body:
            ceiling, upgrade = body.split(",", 1)
            ceiling, upgrade = ceiling.strip(), upgrade.strip()
        trigger_missing = (not upgrade) or upgrade.lower().strip(" .") in _VAGUE_TRIGGERS or bool(
            re.fullmatch(r"(?:revisar|ver|fazer|tratar|corrigir|ajustar|melhorar)?\s*(?:depois|futuro|later|eventually|someday|algum dia|nunca)", upgrade.lower().strip(" ."))
        )
        rows.append({
            "file": current_file,
            "line": index,
            "marker": match.group("marker"),
            "ceiling": ceiling,
            "upgrade": upgrade,
            "noTrigger": trigger_missing,
            "legacy": match.group("marker").lower() != marker.lower(),
            "raw": raw.strip()[:300],
        })
        if len(rows) >= MAX_DEBT_ROWS:
            break
    return rows


def _read_source_file(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) > MAX_AUDIT_FILE_BYTES or b"\x00" in data[:1024]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _walk_sources(root: Path, patterns: set[str] | None, exclude_tests: bool = False, max_files: int = MAX_AUDIT_FILES) -> tuple[list[Path], list[dict[str, str]], bool]:
    selected: list[Path] = []
    skipped: list[dict[str, str]] = []
    limited = False
    resolved = root.resolve()
    for directory, directories, files in os.walk(resolved, followlinks=False):
        kept: list[str] = []
        for name in sorted(directories):
            if name.startswith(".") or (Path(directory) / name).is_symlink():
                continue
            if name in {"node_modules", "dist", "build", "coverage", "__pycache__", ".venv", "venv", "target", "vendor"}:
                continue
            kept.append(name)
        directories[:] = kept
        for name in sorted(files):
            if len(selected) >= max_files:
                limited = True
                break
            if name.startswith("."):
                continue
            candidate = Path(directory) / name
            if candidate.is_symlink():
                continue
            suffix = candidate.suffix.lower()
            if patterns is not None and suffix not in patterns:
                continue
            try:
                relative = candidate.relative_to(resolved)
            except ValueError:
                continue
            if candidate.stat().st_size > MAX_AUDIT_FILE_BYTES:
                skipped.append({"path": relative.as_posix(), "reason": "file-too-large"})
                continue
            if exclude_tests and _TEST_PATH.search(relative.as_posix()):
                continue
            selected.append(candidate)
        if limited:
            break
    return selected, skipped, limited


def _source_root(files_root: Path, relative: str) -> Path:
    root = files_root.resolve() / "reverse"
    if not relative.strip():
        raise LeanError("Informe a pasta de código na área reversa.")
    try:
        path = safe_path(root, relative)
    except ValueError as exc:
        raise LeanError(str(exc)) from exc
    if not path.is_dir() or path.is_symlink():
        raise LeanError("A pasta informada não existe na área reversa.")
    return path


def harvest_debt(*, files_root: Path | None, code: str, path: str = "", marker: str = "shortcut", include_legacy: bool = True) -> dict[str, Any]:
    marker = marker.strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,20}", marker):
        raise LeanError("Use um marcador simples, como shortcut ou ponytail.")
    has_code = bool(code.strip())
    has_path = bool(path.strip())
    if has_code == has_path:
        raise LeanError("Informe exatamente uma fonte: código colado ou uma pasta na área reversa.")
    source = "code"
    files_scanned = 1
    if has_path:
        if files_root is None:
            raise LeanError("A leitura por pasta exige a raiz de arquivos do JARVIS.")
        root = _source_root(files_root, path)
        selected, skipped, limited = _walk_sources(root, SOURCE_EXTENSIONS)
        chunks: list[str] = []
        files_scanned = 0
        for file_path in selected:
            text = _read_source_file(file_path)
            if text is None:
                skipped.append({"path": file_path.relative_to(root).as_posix(), "reason": "unreadable-or-binary"})
                continue
            relative = file_path.relative_to(root.resolve()).as_posix()
            files_scanned += 1
            chunks.append(f"### {relative}\n{text}")
            if sum(len(chunk) for chunk in chunks) > 2_000_000:
                limited = True
                break
        code = "\n".join(chunks)
        source = "tree"
    else:
        skipped, limited = [], False
    rows = _debt_rows(code, marker, include_legacy)
    no_trigger = [row for row in rows if row["noTrigger"]]
    by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_file[row["file"]].append(row)
    markdown_lines = ["# Dívida de atalhos", ""]
    if not rows:
        markdown_lines += ["Nenhum marcador encontrado. Confirme se o marcador aparece em um comentário, por exemplo `// shortcut: sem cache, revisar com 100 usuários`."]
    else:
        for file_name in sorted(by_file):
            markdown_lines += [f"## {file_name}", ""]
            for row in by_file[file_name]:
                suffix = " `no-trigger`" if row["noTrigger"] else ""
                upgrade = row["upgrade"] or "sem gatilho declarado"
                markdown_lines.append(f"- `{file_name}:{row['line']}` — teto: {row['ceiling']}. revisar: {upgrade}.{suffix}")
            markdown_lines.append("")
        markdown_lines.append(f"**{len(rows)} marcador(es), {len(no_trigger)} sem gatilho.**")
    markdown_lines += ["", "**Não verificado:** autoria e data do atalho exigiriam o histórico do Git, que não é lido por esta skill."]
    return {
        "analysis": "debt",
        "source": source,
        "marker": marker,
        "rows": rows,
        "files": sorted(by_file),
        "totals": {"markers": len(rows), "noTrigger": len(no_trigger), "files": len(by_file)},
        "coverage": {"filesScanned": files_scanned, "skipped": skipped[:50], "limitReached": limited},
        "executed": False,
        "readOnly": True,
        "markdown": "\n".join(markdown_lines),
        "limitations": [
            "Só linhas de comentário com o marcador entram no levantamento; prosa que cita a convenção fica de fora.",
            "Um gatilho genérico (depois, futuro, TODO) é tratado como ausente.",
        ],
    }


# ---------------------------------------------------------------- auditoria


def _test_candidates(path: str) -> list[str]:
    pure = Path(path)
    stem = pure.stem
    suffix = pure.suffix
    parent = pure.parent.as_posix()
    prefix = "" if parent == "." else f"{parent}/"
    return [
        f"{prefix}{stem}.test{suffix}",
        f"{prefix}{stem}.spec{suffix}",
        f"{prefix}__tests__/{stem}{suffix}",
        f"{prefix}tests/{stem}.test{suffix}",
        f"{parent}/test_{stem}.py" if parent != "." else f"test_{stem}.py",
        f"{parent}/{stem}_test.py" if parent != "." else f"{stem}_test.py",
    ]


def audit_tree(*, files_root: Path, path: str, mode: str = "full", max_files: int = 400) -> dict[str, Any]:
    if mode not in {"lite", "full", "ultra"}:
        raise LeanError("Nível inválido: use lite, full ou ultra.")
    root = _source_root(files_root, path)
    selected, skipped, limited = _walk_sources(root, SOURCE_EXTENSIONS | {".json"}, max_files=max_files)
    contents: dict[str, str] = {}
    total_bytes = 0
    for file_path in selected:
        if total_bytes >= MAX_AUDIT_TOTAL_BYTES:
            limited = True
            skipped.append({"path": file_path.relative_to(root.resolve()).as_posix(), "reason": "total-byte-limit"})
            break
        text = _read_source_file(file_path)
        if text is None:
            skipped.append({"path": file_path.relative_to(root.resolve()).as_posix(), "reason": "unreadable-or-binary"})
            continue
        relative = file_path.relative_to(root.resolve()).as_posix()
        total_bytes += len(text.encode("utf-8"))
        contents[relative] = text
    if not contents:
        raise LeanError("Nenhum arquivo de código legível foi encontrado nessa pasta.")

    code_files = {name: text for name, text in contents.items() if Path(name).suffix.lower() in CODE_EXTENSIONS and not _TEST_PATH.search(name)}
    test_files = {name: text for name, text in contents.items() if _TEST_PATH.search(name)}
    all_tests_blob = "\n".join(test_files.values())
    file_set = set(contents)

    findings: list[dict[str, Any]] = []

    def add(group: str, kind: str, title: str, location: str, what: str, problem: str, fix: str, if_skipped: str, estimated: int = 0) -> None:
        findings.append({
            "id": 0, "group": group, "kind": kind, "title": title, "location": location,
            "what": what, "problem": problem, "fix": fix, "ifSkipped": if_skipped, "estimatedLines": estimated,
        })

    tested_paths: set[str] = set()
    for name in code_files:
        stem = Path(name).stem
        has_test = any(candidate in file_set for candidate in _test_candidates(name)) or bool(re.search(rf"\b{re.escape(stem)}\b", all_tests_blob))
        if has_test:
            tested_paths.add(name)

    security_hits: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
    risky_files: list[str] = []
    for name, text in code_files.items():
        for number, line in enumerate(_lines(text), start=1):
            for key, label, pattern, group in _SECURITY_PATTERNS:
                if pattern.search(line):
                    security_hits[key].append((name, number, line.strip()[:160]))
        if _RISKY_ADDED.search(text):
            risky_files.append(name)

    for key, label, _pattern, group in _SECURITY_PATTERNS:
        hits = security_hits.get(key, [])
        if not hits:
            continue
        name, number, sample = hits[0]
        add(
            "must" if group == "must" else "should",
            f"risk:{key}",
            f"{label.capitalize()}",
            f"{name}:{number}",
            f"{len(hits)} ocorrência(s); exemplo: `{sample}`.",
            "O padrão depende de dados em tempo de execução e concentra risco de segurança ou perda de dados.",
            "Confirme a origem dos dados e troque pela API segura do projeto (consulta parametrizada, sanitização, `spawn` sem shell, HMAC).",
            "Se a entrada vier de usuário ou rede, vira execução de código, injeção ou vazamento de credencial.",
        )

    untested = [name for name in sorted(risky_files) if name not in tested_paths]
    if untested:
        listed = ", ".join(untested[:4]) + (f" e mais {len(untested) - 4}" if len(untested) > 4 else "")
        add(
            "should",
            "missing-test",
            "Lógica arriscada sem teste",
            untested[0],
            f"{len(untested)} arquivo(s) com ramos, laços, parse, dinheiro ou segurança sem teste correspondente: {listed}.",
            "Uma regra sem teste quebra sem aviso na próxima mudança.",
            "Comece pelo arquivo de maior tráfego e cubra o caso principal e um caso de borda; teste trivial não é obrigatório.",
            "A próxima alteração pode inverter a regra sem ninguém perceber.",
        )

    debt_rows = _debt_rows("\n".join(f"### {name}\n{text}" for name, text in code_files.items()), "shortcut", True)
    no_trigger = [row for row in debt_rows if row["noTrigger"]]
    if no_trigger:
        sample = no_trigger[0]
        add(
            "should",
            "debt-rot",
            "Atalho sem gatilho de revisão",
            f"{sample['file']}:{sample['line']}",
            f"{len(no_trigger)} marcador(es) `shortcut:` não declaram quando revisar.",
            "Um atalho sem data ou limite vira decisão permanente por esquecimento.",
            "Acrescente o limite e o gatilho: `shortcut: <limite>, <quando revisar>`.",
            "A dívida some do radar até alguém tropeçar nela em produção.",
        )

    clones: list[dict[str, Any]] = []
    buckets: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for name, text in code_files.items():
        rows = [(number, _norm(line)) for number, line in enumerate(_lines(text), start=1) if _norm(line) and not _norm(line).startswith(("//", "#", "/*", "*"))]
        for index in range(len(rows) - CLONE_WINDOW + 1):
            chunk = rows[index:index + CLONE_WINDOW]
            buckets[tuple(row[1] for row in chunk)].append({"path": name, "start": chunk[0][0], "end": chunk[-1][0]})
    seen: set[tuple[str, int]] = set()
    covered: list[tuple[str, int, int]] = []
    for key, occurrences in buckets.items():
        if len({occurrence["path"] for occurrence in occurrences}) < 2:
            continue
        markers = {(occurrence["path"], occurrence["start"]) for occurrence in occurrences}
        if markers & seen:
            continue
        if any(
            occurrence["path"] == path and start <= occurrence["start"] <= end + CLONE_WINDOW
            for path, start, end in covered
            for occurrence in occurrences
        ):
            continue
        seen |= markers
        covered.append((occurrences[0]["path"], occurrences[0]["start"], occurrences[0]["start"] + CLONE_WINDOW - 1))
        clones.append({"occurrences": occurrences[:6], "lines": CLONE_WINDOW, "sample": key[0]})
    clones.sort(key=lambda clone: len(clone["occurrences"]), reverse=True)
    for clone in clones[:5]:
        first = clone["occurrences"][0]
        others = ", ".join(f"{item['path']}:{item['start']}" for item in clone["occurrences"][1:3])
        add(
            "should",
            "duplication",
            "Blocos iguais em arquivos diferentes",
            f"{first['path']}:{first['start']}",
            f"{clone['lines']} linhas normalizadas se repetem em {len(clone['occurrences'])} lugares ({others}).",
            "Cópias que mudam juntas divergem na primeira correção.",
            "Mantenha uma definição e importe nos outros pontos.",
            "Uma correção entra em uma cópia e esquece a outra.",
            estimated=clone["lines"] * (len(clone["occurrences"]) - 1),
        )

    unused_exports: list[tuple[str, int, str]] = []
    for name, text in code_files.items():
        for number, line in enumerate(_lines(text), start=1):
            match = re.match(r"\s*export\s+(?:async\s+)?(?:function|const|let|class)\s+(\w+)", line)
            if not match:
                continue
            symbol = match.group(1)
            occurrences = sum(len(re.findall(rf"\b{re.escape(symbol)}\b", content)) for content in contents.values())
            if occurrences <= 1:
                unused_exports.append((name, number, symbol))
    for name, number, symbol in unused_exports[:5]:
        add(
            "nice",
            "unused-export",
            f"Export sem uso na árvore: {symbol}",
            f"{name}:{number}",
            f"`{symbol}` aparece uma única vez em todos os arquivos analisados.",
            "Export não usado é código que alguém mantém e testa sem consumidor.",
            "Apague o export (ou o arquivo) se nada externo consome; confirme imports dinâmicos antes.",
            "Superfície morta que segue sendo lida, revisada e atualizada.",
            estimated=3,
        )

    index_priority = {"must": 0, "should": 1, "nice": 2}
    findings.sort(key=lambda finding: index_priority[finding["group"]])
    total_findings = len(findings)
    for index, finding in enumerate(findings, start=1):
        finding["id"] = index
    omitted = 0
    if mode == "lite":
        findings = [finding for finding in findings if finding["group"] == "must"]
    else:
        omitted = max(0, total_findings - 20)
        findings = findings[:20]
    counts = _findings_summary(findings)
    lean_lines = sum(finding["estimatedLines"] for finding in findings if finding["estimatedLines"])
    verdict = "Saudável sob as regras estáticas." if counts["must"] == 0 and counts["should"] == 0 else _verdict(findings)
    total_lines = sum(text.count("\n") + 1 for text in contents.values())

    markdown_lines = [
        "# Auditoria lean",
        "",
        f"**Inventário:** {len(contents)} arquivos, {total_lines} linhas, {len(code_files)} de código e {len(test_files)} de teste. Nível {mode}.",
        f"**Veredito:** {verdict}",
    ]
    if counts["total"] == 0:
        markdown_lines += ["", "Nenhum candidato pelas regras estáticas. A revisão humana do fluxo principal continua necessária."]
    group_labels = {"must": "Corrigir obrigatoriamente", "should": "Corrigir", "nice": "Opcional"}
    for group in ("must", "should", "nice"):
        group_findings = [finding for finding in findings if finding["group"] == group]
        if not group_findings:
            continue
        markdown_lines += ["", f"## {group_labels[group]}", ""]
        for finding in group_findings:
            markdown_lines += [
                f"{finding['id']}. **{finding['title']}** (`{finding['location']}`)",
                f"   - **O que é:** {finding['what']}",
                f"   - **Problema:** {finding['problem']}",
                f"   - **Correção:** {finding['fix']}",
                f"   - **Se ignorar:** {finding['ifSkipped']}",
                "",
            ]
    if omitted:
        markdown_lines.append(f"{omitted} achado(s) menor(es) foram omitidos.")
    if lean_lines:
        markdown_lines.append(f"**Lean:** até -{lean_lines} linhas possíveis (estimativa).")
    markdown_lines += [
        "",
        "**Não verificado:** execução, chamadores fora da árvore, carga esperada, testes não executados e dependências externas.",
    ]

    return {
        "analysis": "audit",
        "mode": mode,
        "path": path,
        "inventory": {
            "files": len(contents),
            "codeFiles": len(code_files),
            "testFiles": len(test_files),
            "lines": total_lines,
            "bytes": total_bytes,
        },
        "findings": findings,
        "counts": counts,
        "omitted": omitted,
        "verdict": verdict,
        "leanLines": lean_lines,
        "debt": {"markers": len(debt_rows), "noTrigger": len(no_trigger)},
        "coverage": {"skipped": skipped[:50], "limitReached": limited, "maxFiles": max_files},
        "executed": False,
        "readOnly": True,
        "markdown": "\n".join(markdown_lines),
        "limitations": [
            "Auditoria estática: os achados são candidatos e precisam de confirmação no código real.",
            "A árvore é limitada a 400 arquivos e 3 MB; partes não lidas ficam declaradas na cobertura.",
        ],
    }
