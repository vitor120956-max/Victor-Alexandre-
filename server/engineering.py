"""Workflows determinísticos de engenharia, sem executar código ou comandos.

Adaptação própria de ideias de addyosmani/agent-skills (MIT). Nenhum arquivo do
repositório de referência é carregado em runtime.
"""
from __future__ import annotations

import heapq
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Iterable


def _lines(value: str, label: str, *, maximum: int = 50, allow_empty: bool = False) -> list[str]:
    lines = [re.sub(r"^\s*[-*]\s+", "", line).strip() for line in value.splitlines()]
    lines = [line for line in lines if line]
    if not lines and not allow_empty:
        raise ValueError(f"Informe ao menos uma linha em {label}.")
    if len(lines) > maximum:
        raise ValueError(f"{label} excede o limite de {maximum} linhas.")
    return lines


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def _normalized(value: str) -> str:
    return "".join(character for character in unicodedata.normalize("NFKD", value.lower()) if not unicodedata.combining(character))


def _ambiguity_warnings(values: Iterable[str]) -> list[str]:
    text = _normalized(" ".join(values))
    vague = [term for term in ("rapido", "facil", "intuitivo", "robusto", "seguro", "melhor", "otimo") if re.search(rf"\b{term}\w*\b", text)]
    if not vague:
        return []
    return [f"Termos subjetivos encontrados ({', '.join(vague)}). Defina medidas e condições observáveis antes da aprovação."]


def create_spec(title: str, objective: str, users: str, requirements: str, acceptance: str, constraints: str, open_questions: str) -> dict[str, Any]:
    required = _lines(requirements, "requisitos")
    criteria = _lines(acceptance, "critérios de aceite")
    limits = _lines(constraints, "restrições", allow_empty=True)
    questions = _lines(open_questions, "questões abertas", allow_empty=True)
    warnings = _ambiguity_warnings([*required, *criteria])
    if len(criteria) < len(required):
        warnings.append("Há menos critérios de aceite que requisitos. Revise a cobertura antes de planejar.")
    markdown = "\n".join([
        f"# Especificação: {title.strip()}",
        "",
        "> Rascunho gerado por regras locais. Requer revisão e aprovação humana; não é uma especificação aprovada automaticamente.",
        "",
        "## Objetivo",
        objective.strip(),
        "",
        "## Usuários e beneficiários",
        users.strip(),
        "",
        "## Requisitos",
        *[f"{index}. {item}" for index, item in enumerate(required, start=1)],
        "",
        "## Critérios de aceite",
        *[f"- [ ] {item}" for item in criteria],
        "",
        "## Restrições e limites",
        *(f"- {item}" for item in (limits or ["Nenhuma restrição adicional foi informada; confirme se isso é intencional."])),
        "",
        "## Limites de execução",
        "- Sempre: validar entradas, preservar dados e apresentar evidência de verificação.",
        "- Pedir antes: alterar escopo, integrações, credenciais, dados ou publicação.",
        "- Nunca: inventar aprovação, ocultar falhas ou executar comandos colados neste documento.",
        "",
        "## Questões abertas",
        *(f"- {item}" for item in (questions or ["Nenhuma registrada; confirme premissas e métricas com os responsáveis."])),
        "",
        "## Alertas de qualidade",
        *(f"- {item}" for item in (warnings or ["Nenhum alerta lexical; a clareza ainda precisa de revisão humana."])),
    ])
    return {"markdown": markdown, "requirementCount": len(required), "acceptanceCount": len(criteria), "warnings": warnings, "approvalRequired": True}


def create_plan(title: str, requirements: str, dependencies: str, test_command: str, build_command: str) -> dict[str, Any]:
    required = _lines(requirements, "fatias", maximum=30)
    graph: dict[int, set[int]] = {index: set() for index in range(1, len(required) + 1)}
    for entry in _lines(dependencies, "dependências", maximum=100, allow_empty=True):
        match = re.fullmatch(r"(\d+)\s*:\s*(\d+(?:\s*,\s*\d+)*)", entry)
        if not match:
            raise ValueError("Dependências devem usar o formato '2:1' ou '3:1,2'.")
        target = int(match.group(1))
        sources = [int(value.strip()) for value in match.group(2).split(",")]
        if target not in graph or any(source not in graph for source in sources) or target in sources:
            raise ValueError("A dependência contém índice inexistente ou autorreferência.")
        graph[target].update(sources)
    done: set[int] = set()
    ready = [index for index, sources in graph.items() if not sources]
    heapq.heapify(ready)
    ordered: list[int] = []
    while ready:
        current = heapq.heappop(ready)
        ordered.append(current)
        done.add(current)
        for candidate, sources in graph.items():
            if candidate not in done and candidate not in ready and sources <= done:
                heapq.heappush(ready, candidate)
    if len(ordered) != len(required):
        raise ValueError("As dependências formam um ciclo. Corrija o grafo antes de planejar.")
    tasks = [{"originalTask": index, "title": required[index - 1], "dependsOn": sorted(graph[index])} for index in ordered]
    markdown = [
        f"# Plano de implementação: {title.strip()}",
        "",
        "> Planejamento local; nenhum comando abaixo foi executado. Use somente depois de aprovar a especificação.",
        "",
        "## Fatias verticais ordenadas",
    ]
    for position, task in enumerate(tasks, start=1):
        dependencies_text = ", ".join(f"requisito {item}" for item in task["dependsOn"]) or "nenhuma"
        markdown.extend([
            f"### Tarefa {position} · requisito {task['originalTask']}: {task['title']}",
            f"- **Entrega:** uma fatia funcional e verificável para: {task['title']}",
            f"- **Aceite:** {task['title']}",
            f"- **Dependências declaradas:** {dependencies_text}.",
            f"- **Verificação sugerida:** `{test_command}`; `{build_command}`; checar o fluxo correspondente manualmente.",
            "- **Checkpoint humano:** revisar diff, evidências e escopo antes de avançar.",
            "",
        ])
        if position % 3 == 0 and position < len(tasks):
            markdown.extend([f"## Checkpoint após tarefa {position}", "- [ ] Testes, build e fluxo principal revisados com evidências.", ""])
    return {"markdown": "\n".join(markdown).rstrip(), "tasks": tasks, "taskCount": len(tasks), "commandsExecuted": False}


def design_tests(title: str, acceptance: str, risks: str, test_command: str) -> dict[str, Any]:
    criteria = _lines(acceptance, "critérios de aceite")
    risk_items = _lines(risks, "riscos", allow_empty=True)
    warnings = _ambiguity_warnings(criteria)
    cases: list[dict[str, str]] = []
    levels = [
        ("Unitário", "Demonstrar o comportamento esperado e suas fronteiras"),
        ("Negativo", "Exercitar entrada inválida, ausência de dados e falha esperada"),
        ("Integração", "Confirmar o fluxo entre os componentes reais envolvidos"),
        ("Regressão", "Verificar que o teste falha quando a condição principal é invertida"),
    ]
    for index, criterion in enumerate(criteria, start=1):
        for level, action in levels:
            cases.append({"criterion": criterion, "level": level, "action": f"{action}: {criterion}", "id": f"C{index}-{level[:3].upper()}"})
    markdown = [
        f"# Matriz de testes: {title.strip()}",
        "",
        "> Casos sugeridos, não testes executados. Adapte os níveis ao que for relevante e registre evidências reais.",
        "",
        "| Caso | Nível | Condição a verificar |",
        "|---|---|---|",
        *(f"| {case['id']} | {case['level']} | {_cell(case['action'])} |" for case in cases),
        "",
        "## Riscos a transformar em testes",
        *(f"- {item}" for item in (risk_items or ["Nenhum risco adicional informado; revisar dados, permissões, falhas e limites."])),
        "",
        "## Ciclo de evidência",
        f"1. RED: escreva um caso que falhe pelo motivo esperado. 2. GREEN: implemente o mínimo. 3. REFACTOR: preserve o comportamento. 4. Execute `{test_command}` e registre o resultado.",
        "",
        "## Alertas",
        *(f"- {item}" for item in (warnings or ["A matriz não substitui análise de cobertura, testes manuais ou revisão humana."])),
    ]
    return {"markdown": "\n".join(markdown), "cases": cases, "criterionCount": len(criteria), "testCaseCount": len(cases), "warnings": warnings, "testsExecuted": False}


_REVIEW_RULES: list[tuple[set[str], re.Pattern[str], str, str, str]] = [
    ({"python", "javascript", "typescript", "jsx", "tsx"}, re.compile(r"\beval\s*\(", re.I), "critical", "Segurança", "Avaliação dinâmica de código; elimine ou justifique uma fronteira segura."),
    ({"python"}, re.compile(r"\bexec\s*\(", re.I), "critical", "Segurança", "Execução dinâmica de código; não use com dados externos."),
    ({"python"}, re.compile(r"\bos\.system\s*\(", re.I), "critical", "Segurança", "Chamada de shell; revise a necessidade e qualquer entrada externa."),
    ({"python"}, re.compile(r"shell\s*=\s*True", re.I), "critical", "Segurança", "Subprocesso com shell exige revisão de injeção e allowlist."),
    ({"python", "javascript", "typescript", "jsx", "tsx"}, re.compile(r"(?:api[_-]?key|secret|password|token)\s*=\s*['\"][^'\"]{8,}", re.I), "critical", "Segurança", "Possível segredo literal; o valor não foi copiado para este relatório."),
    ({"python"}, re.compile(r"\.execute\s*\(\s*f['\"]", re.I), "warning", "Segurança", "SQL com f-string pode indicar concatenação; prefira parâmetros."),
    ({"python"}, re.compile(r"\b(?:pickle\.loads?|yaml\.load)\s*\(", re.I), "warning", "Segurança", "Desserialização exige formato seguro e origem confiável."),
    ({"javascript", "typescript", "jsx", "tsx"}, re.compile(r"new\s+Function\s*\(", re.I), "critical", "Segurança", "Construção dinâmica de função; evite interpretar texto como código."),
    ({"javascript", "typescript", "jsx", "tsx"}, re.compile(r"\.innerHTML\s*=", re.I), "warning", "Segurança", "HTML direto exige sanitização; prefira APIs de texto."),
    ({"jsx", "tsx"}, re.compile(r"dangerouslySetInnerHTML", re.I), "warning", "Segurança", "HTML sem escape no React exige sanitização e justificativa."),
    ({"javascript", "typescript", "jsx", "tsx"}, re.compile(r"localStorage[^\n]*(?:token|password|secret)|(?:token|password|secret)[^\n]*localStorage", re.I), "warning", "Segurança", "Possível credencial em armazenamento acessível ao navegador."),
    ({"python", "javascript", "typescript", "jsx", "tsx"}, re.compile(r"\bwhile\s*(?:\(\s*)?(?:True|true)\b", re.I), "warning", "Performance", "Loop aparentemente ilimitado; confirme parada, timeout e limite de trabalho."),
    ({"typescript", "tsx"}, re.compile(r"(?::|\bas)\s+any\b"), "info", "Tipagem", "Tipo any reduz a clareza da fronteira; considere um tipo explícito."),
    ({"python"}, re.compile(r"^\s*(?:except(?:\s+Exception)?\s*:\s*pass|except\s*:\s*$)", re.I), "warning", "Correção", "Tratamento de exceção amplo ou vazio pode ocultar falhas."),
    ({"python"}, re.compile(r"\bprint\s*\("), "info", "Depuração", "Confirme se a saída de depuração deve permanecer e não contém dados sensíveis."),
    ({"javascript", "typescript", "jsx", "tsx"}, re.compile(r"\bconsole\.log\s*\("), "info", "Depuração", "Confirme se o log deve permanecer e não contém dados sensíveis."),
    ({"python", "javascript", "typescript", "jsx", "tsx"}, re.compile(r"\b(?:TODO|FIXME)\b", re.I), "info", "Manutenção", "Pendência encontrada; confirme responsável e prazo."),
]


def review_code(code: str, language: str, changed_lines: int) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    for line_number, line in enumerate(code.splitlines(), start=1):
        for languages, pattern, severity, axis, message in _REVIEW_RULES:
            if language in languages and pattern.search(line):
                findings.append({"line": line_number, "severity": severity, "axis": axis, "message": message})
    total_lines = len(code.splitlines())
    if changed_lines > 300:
        findings.append({"line": None, "severity": "warning", "axis": "Tamanho", "message": f"As {changed_lines} linhas alteradas merecem divisão ou justificativa de escopo."})
    if total_lines > 1_000:
        findings.append({"line": None, "severity": "info", "axis": "Tamanho", "message": f"O trecho tem {total_lines} linhas; avalie decomposição sem presumir um limite universal."})
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda item: (severity_order[item["severity"]], item["line"] or 0))
    truncated = len(findings) > 100
    visible = findings[:100]
    counts = {severity: sum(item["severity"] == severity for item in findings) for severity in severity_order}
    markdown = [
        "# Revisão estática de código",
        "",
        f"Linguagem: **{language}** · {total_lines} linhas analisadas · {len(findings)} sinais conhecidos.",
        "",
        "> Heurística local: o código não foi executado e nenhum achado prova exploração ou ausência de vulnerabilidades. Testes e revisão humana continuam necessários.",
        "",
    ]
    if visible:
        markdown.extend(["| Severidade | Linha | Eixo | Sinal para revisar |", "|---|---:|---|---|"])
        markdown.extend(f"| {item['severity']} | {item['line'] or '—'} | {item['axis']} | {_cell(item['message'])} |" for item in visible)
    else:
        markdown.append("Nenhum dos padrões conhecidos foi encontrado. **Isso não equivale a aprovação ou código seguro.**")
    if truncated:
        markdown.extend(["", f"Relatório limitado a 100 de {len(findings)} sinais."])
    return {"markdown": "\n".join(markdown), "findings": visible, "findingCount": len(findings), "counts": counts, "truncated": truncated, "codeExecuted": False}


def threat_model(feature: str, assets: str, boundaries: str) -> dict[str, Any]:
    asset_items = _lines(assets, "ativos", maximum=20)
    boundary_items = _lines(boundaries, "fronteiras", maximum=8)
    lenses = [
        ("Spoofing", "Como a identidade e a origem são autenticadas nesta fronteira?"),
        ("Tampering", "Como integridade e autorização impedem alteração indevida dos dados?"),
        ("Repudiation", "Que evento de auditoria registra ação, ator e resultado sem armazenar segredos?"),
        ("Information disclosure", f"Quais campos de {', '.join(asset_items[:3])} podem aparecer em respostas, logs ou erros?"),
        ("Denial of service", "Quais limites de tamanho, taxa, tempo e concorrência interrompem abuso?"),
        ("Elevation of privilege", "A autorização é verificada no recurso específico com privilégio mínimo?"),
    ]
    threats = [{"boundary": boundary, "category": category, "question": question} for boundary in boundary_items for category, question in lenses]
    markdown = [
        f"# Modelo de ameaças: {feature.strip()}",
        "",
        "> Rascunho STRIDE gerado por regras. Não é uma auditoria concluída nem evidência de que os controles existem.",
        "",
        "## Ativos declarados",
        *(f"- {item}" for item in asset_items),
        "",
        "| Fronteira | STRIDE | Pergunta de verificação |",
        "|---|---|---|",
        *(f"| {_cell(item['boundary'])} | {item['category']} | {_cell(item['question'])} |" for item in threats),
        "",
        "## Casos de abuso prioritários",
        *(f"- Em **{boundary}**: enviar dados fora do contrato, repetir chamadas além do limite e tentar acessar recursos de outro ator." for boundary in boundary_items),
        "",
        "## Evidências necessárias antes de aceitar o modelo",
        "- Validar schemas, autorização por recurso, mensagens de erro e logs sem dados sensíveis.",
        "- Testar limites de upload/corpo, rate limit, timeout e comportamento sob falha.",
        "- Confirmar gestão de segredos e auditoria nativa das dependências com o lockfile versionado.",
    ]
    return {"markdown": "\n".join(markdown), "assetCount": len(asset_items), "boundaryCount": len(boundary_items), "threatCount": len(threats), "auditCompleted": False}


def _rating(value: float, good: float, improvement: float) -> str:
    if value <= good:
        return "good"
    if value <= improvement:
        return "needs-improvement"
    return "poor"


def evaluate_webvitals(lcp_ms: float, inp_ms: float, cls: float, source: str, sample_size: int) -> dict[str, Any]:
    ratings = {"LCP": _rating(lcp_ms, 2_500, 4_000), "INP": _rating(inp_ms, 200, 500), "CLS": _rating(cls, 0.1, 0.25)}
    rank = {"good": 0, "needs-improvement": 1, "poor": 2}
    labels = {"good": "Bom", "needs-improvement": "Precisa melhorar", "poor": "Ruim"}
    overall = max(ratings.values(), key=lambda item: rank[item])
    values = {"LCP": f"{lcp_ms:,.0f} ms", "INP": f"{inp_ms:,.0f} ms", "CLS": f"{cls:.3f}"}
    thresholds = {"LCP": "≤ 2.500 ms / ≤ 4.000 ms", "INP": "≤ 200 ms / ≤ 500 ms", "CLS": "≤ 0,100 / ≤ 0,250"}
    recommendations = []
    if ratings["LCP"] != "good":
        recommendations.append("LCP: investigar servidor, recursos que bloqueiam renderização e imagem principal; medir antes e depois.")
    if ratings["INP"] != "good":
        recommendations.append("INP: procurar long tasks, JavaScript excessivo e atualizações grandes no trace de interação.")
    if ratings["CLS"] != "good":
        recommendations.append("CLS: inspecionar dimensões de mídia, fontes e conteúdo inserido tardiamente.")
    warnings = []
    if source == "lab":
        warnings.append("Medição sintética: útil para investigação, mas não comprova a experiência de usuários reais; valide em campo.")
    elif sample_size == 0:
        warnings.append("Informe o tamanho da amostra de campo; a classificação usa somente os valores fornecidos.")
    elif sample_size < 100:
        warnings.append("Amostra de campo pequena; evite tratar o valor como um p75 representativo.")
    markdown = "\n".join([
        "# Avaliação de Core Web Vitals",
        "",
        f"Origem declarada: **{'laboratório' if source == 'lab' else 'campo / RUM'}** · Resultado geral: **{labels[overall]}**.",
        "",
        "| Métrica | Valor informado | Classificação | Limiares Bom / Precisa melhorar |",
        "|---|---:|---|---|",
        *(f"| {metric} | {values[metric]} | {labels[rating]} | {thresholds[metric]} |" for metric, rating in ratings.items()),
        "",
        "## Próximas investigações",
        *(f"- {item}" for item in (recommendations or ["Manter orçamento e monitoramento; uma boa pontuação pontual não elimina regressões futuras."])),
        "",
        "## Limites da evidência",
        *(f"- {item}" for item in (warnings or ["Compare medições nas mesmas condições e confirme o p75 de campo antes de concluir impacto real."])),
    ])
    return {"markdown": markdown, "ratings": ratings, "overall": overall, "source": source, "sampleSize": sample_size, "warnings": warnings, "measurementTaken": False}


def create_adr(identifier: str, title: str, status: str, context: str, decision: str, alternatives: str, consequences: str) -> dict[str, Any]:
    alternative_items = _lines(alternatives, "alternativas", maximum=20)
    consequence_items = _lines(consequences, "consequências", maximum=30)
    parsed = []
    warnings = []
    for item in alternative_items:
        parts = [part.strip() for part in item.split("|")]
        if len(parts) < 4:
            warnings.append(f"Alternativa '{parts[0]}' precisa de prós, contras e motivo de rejeição no formato de quatro colunas.")
        parts.extend(["Não informado"] * (4 - len(parts)))
        parsed.append({"name": parts[0], "pros": parts[1], "cons": parts[2], "reason": " | ".join(parts[3:])})
    if identifier.strip().upper() == "ADR-XXX":
        warnings.append("Substitua ADR-XXX pela numeração do projeto antes de aceitar o registro.")
    markdown = [
        f"# {identifier.strip()}: {title.strip()}",
        "",
        f"## Status\n{status}",
        f"## Data\n{datetime.now(timezone.utc).date().isoformat()}",
        f"## Contexto\n{context.strip()}",
        f"## Decisão\n{decision.strip()}",
        "## Alternativas consideradas",
    ]
    for alternative in parsed:
        markdown.extend([
            f"### {alternative['name']}",
            f"- Prós: {alternative['pros']}",
            f"- Contras: {alternative['cons']}",
            f"- Motivo da rejeição: {alternative['reason']}",
            "",
        ])
    markdown.extend(["## Consequências", *(f"- {item}" for item in consequence_items), "", "## Pendências", *(f"- {item}" for item in (warnings or ["Revisar o ADR com os responsáveis e preservar seu histórico; não apagar decisões substituídas."]))])
    return {"markdown": "\n".join(markdown), "alternatives": parsed, "warnings": warnings, "approvalRequired": True}


def release_gate(release: str, checks: dict[str, bool], user_facing: bool, evidence: str) -> dict[str, Any]:
    labels = {
        "testsPassed": "Testes declarados como aprovados",
        "buildPassed": "Build e tipagem declarados como aprovados",
        "reviewApproved": "Revisão humana declarada como aprovada",
        "securityChecked": "Segredos e auditoria de dependências declarados como verificados",
        "performanceChecked": "Performance declarada como verificada",
        "rollbackReady": "Rollback declarado como preparado",
        "monitoringReady": "Monitoramento declarado como preparado",
        "documentationUpdated": "Documentação declarada como atualizada",
    }
    required = ["testsPassed", "buildPassed", "reviewApproved", "securityChecked", "rollbackReady", "monitoringReady"]
    if user_facing:
        required.append("performanceChecked")
    blockers = [key for key in required if not checks[key]]
    if not evidence.strip():
        blockers.append("evidence")
    warnings = [] if checks["documentationUpdated"] else ["Documentação não foi marcada como atualizada; confirme se há impacto para usuários ou operação."]
    decision = "READY_FOR_HUMAN_APPROVAL" if not blockers else "BLOCKED"
    markdown = "\n".join([
        f"# Gate de release: {release.strip()}",
        "",
        f"**Decisão: {decision}**",
        "",
        "> Este gate não executou testes, build, auditoria, deploy ou rollback. Ele organiza declarações do usuário; toda evidência precisa ser conferida.",
        "",
        "## Checklist declarado",
        *(f"- [{'x' if checks[key] else ' '}] {label}{' (obrigatório)' if key in required else ''}" for key, label in labels.items() if key != "performanceChecked" or user_facing),
        "",
        "## Evidências fornecidas",
        evidence.strip() or "Nenhuma evidência fornecida.",
        "",
        "## Bloqueadores",
        *(f"- {labels.get(key, 'Evidências de verificação ausentes')}" for key in (blockers or ["Nenhum bloqueador do checklist; ainda é necessária aprovação humana."])),
        "",
        "## Alertas",
        *(f"- {item}" for item in (warnings or ["Nenhum alerta adicional do checklist."])),
        "",
        "Nenhum deploy ou ação de publicação foi executado.",
    ])
    return {"markdown": markdown, "decision": decision, "blockers": blockers, "warnings": warnings, "deployExecuted": False}
