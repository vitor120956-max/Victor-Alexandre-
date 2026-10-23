"""Governança estática de agentes inspirada em paperclipai/paperclip (MIT).

Implementação própria e determinística. Nenhum servidor, adapter, plugin,
heartbeat, MCP ou comando do upstream é instalado ou executado. As skills leem
apenas declarações coladas pelo usuário (equipe, quadro, orçamento e parada de
trabalho) e devolvem candidatos com evidência, veredito e limites explícitos.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from .review import common as _common, finalize as _finalize, verdict as _verdict

MAX_ROWS = 200
MAX_FIELD_CHARS = 300
MAX_INPUT_CHARS = 50_000
MONEY = Decimal("0.01")
RATIO = Decimal("0.1")

HUMAN_ROOTS = {"board", "conselho", "humano", "human", "diretoria", "diretoria_executiva"}

_AGENT_STATUS = {
    "ativo": "active", "active": "active", "operando": "active", "em_operacao": "active",
    "pausado": "paused", "paused": "paused", "em_pausa": "paused",
    "pendente": "pending", "pending": "pending", "em_aprovacao": "pending", "contratando": "pending",
    "encerrado": "terminated", "terminated": "terminated", "demitido": "terminated", "desligado": "terminated",
    "rejeitado": "rejected", "rejected": "rejected",
    "sem_orcamento": "budget_blocked", "budget_blocked": "budget_blocked",
}

_TASK_STATUS = {
    "triagem": "triage", "triage": "triage",
    "backlog": "unstarted", "todo": "unstarted", "a_fazer": "unstarted", "icebox": "unstarted",
    "ready": "unstarted", "pronto": "unstarted", "nao_iniciado": "unstarted",
    "em_andamento": "started", "in_progress": "started", "doing": "started", "started": "started",
    "executando": "started", "running": "started",
    "em_revisao": "review", "in_review": "review", "review": "review", "revisao": "review", "qa": "review",
    "bloqueado": "blocked", "blocked": "blocked",
    "aguardando": "waiting", "waiting": "waiting", "waiting_on_interaction": "waiting",
    "concluido": "done", "done": "done", "completed": "done", "feito": "done", "shipped": "done", "entregue": "done",
    "cancelado": "cancelled", "cancelled": "cancelled", "wontfix": "cancelled", "duplicate": "cancelled",
    "abandonado": "cancelled",
    "na_fila": "queued", "queued": "queued",
    "reagendado": "retry", "scheduled_retry": "retry", "retry": "retry",
}

_LIVE_STATUSES = {"started", "queued", "retry"}
_REVIEW_HINT = re.compile(r"@[A-Za-z0-9_.-]+|\b(?:revisor|revisora|reviewer|review|revis[aã]o|revisado|aprovad[oa]?|approved|qa)\b", re.I)
_OWNER_HINT = re.compile(r"@[A-Za-z0-9_.-]+|\b(?:dono|dona|owner|respons[aá]vel)\s*[:\-]", re.I)
_CRITICAL_PERMISSIONS = {
    "*", "all", "admin", "root", "sudo", "exec", "shell", "secrets", "billing", "deploy",
    "users:manage", "agents:create", "tools:admin", "network:*",
}
_WILDCARD_PERMISSIONS = {"*", "all", "admin", "root", "sudo"}

_AMOUNT = re.compile(r"^-?\d+(?:[.,]\d{1,2})?$")
_PERCENT = re.compile(r"^\d+(?:[.,]\d{1,2})?$")
_HEX64 = re.compile(r"^[a-fA-F0-9]{64}$")

_TRUE = {"sim", "s", "yes", "y", "true", "1", "ligado", "ligada"}
_FALSE = {"nao", "n", "no", "false", "0", "desligado", "desligada", "off"}
_EMPTY = {"", "-", "n/a", "na", "none", "nenhum", "nenhuma", "nil"}


class AgencyError(ValueError):
    """Erro esperado da governança de agentes, seguro para o usuário."""


def _norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return text.strip().lower()


def _cell(value: str) -> str:
    text = value.strip()
    return "" if _norm(text) in _EMPTY else text


def _lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _split_rows(text: str, expected: int, label: str) -> list[tuple[int, list[str]]]:
    if not text.strip():
        raise AgencyError(f"Informe ao menos um {label}.")
    if len(text) > MAX_INPUT_CHARS:
        raise AgencyError(f"A entrada excede {MAX_INPUT_CHARS:,} caracteres; divida em partes.".replace(",", "."))
    rows: list[tuple[int, list[str]]] = []
    for number, raw in enumerate(_lines(text), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        cells = [cell.strip() for cell in stripped.split("|")]
        if len(cells) > expected:
            raise AgencyError(f"Linha {number}: use no máximo {expected} campos separados por |.")
        if any(len(cell) > MAX_FIELD_CHARS for cell in cells):
            raise AgencyError(f"Linha {number}: cada campo deve ter até {MAX_FIELD_CHARS} caracteres.")
        cells += [""] * (expected - len(cells))
        rows.append((number, cells))
    if not rows:
        raise AgencyError(f"Informe ao menos um {label}.")
    if len(rows) > MAX_ROWS:
        raise AgencyError(f"A entrada tem {len(rows)} linhas; o limite é {MAX_ROWS}.")
    return rows


def _money(raw: str, label: str) -> Decimal:
    value = _cell(raw)
    for token in ("US$", "R$", "USD", "BRL", "$"):
        value = value.replace(token, "")
    value = value.replace(" ", "")
    if not value:
        raise AgencyError(f"{label}: informe um valor, por exemplo 900 ou 900.50.")
    if not _AMOUNT.match(value):
        raise AgencyError(f"{label}: use apenas dígitos e até duas casas decimais, sem separador de milhar (ex.: 1200.00).")
    try:
        return Decimal(value.replace(",", "."))
    except InvalidOperation as exc:
        raise AgencyError(f"{label}: valor inválido.") from exc


def _percent(raw: str, label: str) -> Decimal:
    value = _cell(raw).replace("%", "").strip()
    if not _PERCENT.match(value):
        raise AgencyError(f"{label}: informe um percentual entre 0 e 100.")
    number = Decimal(value.replace(",", "."))
    if number < 0 or number > 100:
        raise AgencyError(f"{label}: informe um percentual entre 0 e 100.")
    return number


def _flag(raw: str) -> bool | None:
    value = _norm(_cell(raw))
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    return None


def _iso_date(raw: str, label: str) -> date:
    value = _cell(raw)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise AgencyError(f"{label}: use uma data ISO, como 2026-10-20.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise AgencyError(f"{label}: data inválida; use uma data ISO real.") from exc


def _reference_date(raw: str) -> date:
    value = _cell(raw)
    if not value:
        return datetime.now(timezone.utc).date()
    return _iso_date(value, "Data de referência")


def _decimal_out(value: Decimal) -> float:
    return float(value.quantize(MONEY, rounding=ROUND_HALF_UP))


def _ratio_out(part: Decimal, whole: Decimal) -> float:
    if whole <= 0:
        return 0.0
    return float((part / whole * 100).quantize(RATIO, rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------- equipe


def audit_roster(*, roster: str, mode: str = "full") -> dict[str, Any]:
    if mode not in {"lite", "full", "ultra"}:
        raise AgencyError("Nível inválido: use lite, full ou ultra.")
    source = _split_rows(roster, 6, "agente")
    findings: list[dict[str, Any]] = []

    def add(group: str, kind: str, title: str, location: str, what: str, problem: str, fix: str, if_skipped: str) -> None:
        findings.append({
            "id": 0, "group": group, "kind": kind, "title": title, "location": location,
            "what": what, "problem": problem, "fix": fix, "ifSkipped": if_skipped,
        })

    agents: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for number, cells in source:
        name, role, manager_raw, budget_raw, permissions_raw, status_raw = cells
        name = _cell(name)
        if not name:
            add("must", "missing-name", "Agente sem nome", f"linha {number}", "A linha não declara um nome.",
                "Sem identidade, o agente não pode ser responsabilizado nem receber trabalho.",
                "Informe o nome na primeira coluna.", "O agente existe apenas em uma planilha paralela.")
            continue
        key = name.casefold()
        if key in seen:
            add("must", "duplicate", f"Agente repetido: {name}", f"linha {number}",
                f"`{name}` já foi declarado na linha {seen[key]}.",
                "Duas linhas para o mesmo agente tornam orçamento e permissões ambíguos.",
                "Mantenha uma única linha por agente.", "Decisões de acesso e custo divergem entre as cópias.")
            continue
        seen[key] = number

        manager = _cell(manager_raw)
        role = _cell(role)
        permissions = [item.strip() for item in re.split(r"[,;]", permissions_raw) if item.strip()]
        status = _AGENT_STATUS.get(_norm(_cell(status_raw)), "unknown") if _cell(status_raw) else "unknown"
        budget = Decimal("0")
        if _cell(budget_raw):
            try:
                budget = _money(budget_raw, f"Orçamento de {name}")
            except AgencyError as exc:
                add("must", "invalid-budget", f"Orçamento inválido: {name}", f"linha {number}", str(exc),
                    "Um valor inválido impede somar o custo da equipe.",
                    "Use dígitos e até duas casas decimais, como 900.00.", "O orçamento real fica desconhecido.")
        if budget < 0:
            add("must", "negative-budget", f"Orçamento negativo: {name}", f"linha {number}", f"`{budget}` é negativo.",
                "Limite negativo não representa um teto de gasto.", "Use zero ou um valor positivo.", "O agente nunca deveria executar.")
        if not role:
            add("must", "missing-role", f"Papel não declarado: {name}", f"linha {number}", "A coluna de papel está vazia.",
                "Sem papel, ninguém sabe o que o agente pode decidir ou entregar.",
                "Declare a responsabilidade principal, como Backend ou Pesquisa.", "O agente vira um executor genérico sem fronteira.")
        if not manager:
            add("must", "missing-manager", f"Sem responsável: {name}", f"linha {number}", "A coluna 'responde a' está vazia.",
                "Todo agente precisa de uma linha de reporte até um humano ou conselho.",
                "Use `board` para o topo ou o nome de outro agente.", "Não há caminho de escalada para uma decisão humana.")
        if not permissions:
            add("must", "missing-permissions", f"Permissões não declaradas: {name}", f"linha {number}", "A coluna de permissões está vazia.",
                "Permissão implícita é permissão desconhecida; a revisão de acesso fica impossível.",
                "Declare as ferramentas permitidas ou `nenhuma`.", "O agente pode receber acesso sem registro.")
        else:
            normalized = {_norm(permission) for permission in permissions}
            wildcard = sorted(normalized & _WILDCARD_PERMISSIONS)
            critical = sorted(normalized & (_CRITICAL_PERMISSIONS - _WILDCARD_PERMISSIONS))
            if wildcard:
                add("must", "wildcard-permission", f"Permissão curinga: {name}", f"linha {number}",
                    f"Permissões declaradas: {', '.join(permissions)}.",
                    "Curinga elimina o menor privilégio e não pode ser revisado por ferramenta.",
                    "Substitua por permissões nomeadas e específicas.", "Uma única credencial pode fazer tudo.")
            elif critical and status not in {"terminated", "rejected"}:
                add("should", "critical-permission", f"Permissões sensíveis: {name}", f"linha {number}",
                    f"Permissões declaradas: {', '.join(critical)}.",
                    "Execução, segredos, cobrança ou deploy exigem aprovação e escopo explícitos.",
                    "Confirme se cada permissão é necessária e registre quem aprova.", "O agente amplia a superfície de ataque da operação.")
        if status == "unknown":
            add("must", "invalid-status", f"Estado inválido: {name}", f"linha {number}",
                f"`{_cell(status_raw) or '(vazio)'}` não é um estado conhecido.",
                "Sem estado, a escala e o orçamento não sabem se o agente pode executar.",
                "Use ativo, pausado, pendente, encerrado, rejeitado ou sem_orcamento.", "O agente fica em um limbo operacional.")
        if status == "active" and budget == 0:
            add("should", "zero-budget", f"Agente ativo sem orçamento: {name}", f"linha {number}", "O limite mensal é zero.",
                "Sem teto positivo, o trabalho para no primeiro heartbeat ou consome sem controle.",
                "Defina um limite ou marque o agente como pausado.", "O agente parece ativo, mas não consegue operar.")
        if status in {"terminated", "rejected"} and budget > 0:
            add("should", "stale-budget", f"Orçamento de agente inativo: {name}", f"linha {number}",
                f"Estado `{status}` com limite {budget}.",
                "Orçamento reservado para quem não trabalha distorce o total da equipe.",
                "Zere o limite ou reative o agente.", "O teto da empresa fica maior do que o necessário.")
        agents.append({
            "name": name, "role": role, "manager": manager, "budget": _decimal_out(budget),
            "permissions": permissions, "status": status, "line": number,
        })

    names = {agent["name"].casefold(): agent for agent in agents}
    edges: dict[str, str] = {}
    roots = [agent for agent in agents if _norm(agent["manager"]) in HUMAN_ROOTS]
    for agent in agents:
        manager = agent["manager"]
        manager_key = manager.casefold()
        if not manager:
            continue
        if manager_key == agent["name"].casefold():
            add("must", "self-manager", f"Agente reporta a si mesmo: {agent['name']}", f"linha {agent['line']}",
                f"`{agent['name']}` aparece como seu próprio responsável.",
                "Auto-reporte elimina a revisão independente.", "Aponte para outro agente ou para `board`.", "Não existe segunda opinião.")
            continue
        if _norm(manager) in HUMAN_ROOTS:
            continue
        if manager_key not in names:
            add("must", "unknown-manager", f"Responsável desconhecido: {agent['name']}", f"linha {agent['line']}",
                f"`{manager}` não está na equipe declarada.",
                "Uma linha de reporte quebrada deixa o agente sem supervisão.",
                "Declare o responsável ou use `board`.", "O agente não tem caminho de escalada.")
            continue
        edges[agent["name"]] = names[manager_key]["name"]
        if names[manager_key]["status"] in {"terminated", "rejected"} and agent["status"] == "active":
            add("must", "inactive-manager", f"Responsável inativo: {agent['name']}", f"linha {agent['line']}",
                f"`{manager}` está `{names[manager_key]['status']}` e ainda supervisiona um agente ativo.",
                "Um supervisor encerrado não pode rever nem desbloquear trabalho.",
                "Reaponte o agente para alguém ativo.", "O trabalho fica sem revisão real.")

    if not roots:
        add("must", "no-human-root", "Nenhum agente responde a humano ou conselho", "equipe",
            "Todos os responsáveis declarados são agentes.",
            "Sem raiz humana, nenhuma decisão de gasto, contratação ou risco chega a uma pessoa.",
            "Faça ao menos um agente reportar a `board`.", "A operação se torna circular e sem prestação de contas.")

    cycles: list[list[str]] = []
    seen_cycles: set[frozenset[str]] = set()
    for start in sorted(edges):
        path: list[str] = []
        positions: dict[str, int] = {}
        node = start
        while node in edges and node not in positions:
            positions[node] = len(path)
            path.append(node)
            node = edges[node]
        if node in positions:
            cycle = path[positions[node]:]
            key = frozenset(cycle)
            if key not in seen_cycles:
                seen_cycles.add(key)
                cycles.append(cycle)
    for cycle in cycles:
        add("must", "report-cycle", "Ciclo de reporte", " → ".join(cycle + [cycle[0]]),
            "Os agentes se supervisionam em círculo.",
            "Em um ciclo, nenhum agente é a autoridade final e a escalada nunca chega a um humano.",
            "Escolha um responsável fora do ciclo ou aponte para `board`.", "A revisão fica travada entre os mesmos agentes.")

    span: dict[str, int] = {}
    for agent in agents:
        if agent["manager"].casefold() in names and _norm(agent["manager"]) not in HUMAN_ROOTS:
            span[agent["manager"]] = span.get(agent["manager"], 0) + 1
    for manager, total in sorted(span.items()):
        if total > 8:
            add("should", "span-of-control", f"Amplitude alta: {manager}", manager,
                f"{total} agentes reportam diretamente a `{manager}`.",
                "Um supervisor com muitos reportes revisa menos e aprova por atacado.",
                "Divida a supervisão em sub-líderes ou limite o quadro.", "Revisões viram carimbo.")

    active = sum(1 for agent in agents if agent["status"] == "active")
    inactive = sum(1 for agent in agents if agent["status"] in {"paused", "pending", "terminated", "rejected", "budget_blocked"})
    dangerous = sum(1 for agent in agents if {_norm(permission) for permission in agent["permissions"]} & _CRITICAL_PERMISSIONS)
    total_budget = sum((Decimal(str(agent["budget"])) for agent in agents), Decimal("0"))
    questions = [
        "Cada agente tem um responsável humano nomeado, e não apenas outro agente?",
        "Quem aprova contratações, gastos e permissões sensíveis?",
        "Existe alguma função sem dono ou com dois donos na prática?",
    ]
    limitations = [
        "A revisão lê apenas a equipe declarada; permissões reais do runtime não são consultadas.",
        "Orçamento é uma soma declarada, sem consumo, fatura ou conversão de moeda.",
    ]
    summary = [
        f"**Equipe:** {len(agents)} agentes · {active} ativos · {inactive} inativos · {len(roots)} raiz(es) humana(s).",
        f"**Orçamento mensal declarado:** {_decimal_out(total_budget):.2f} · {dangerous} agente(s) com permissão sensível.",
    ]
    findings, counts, verdict, questions = _finalize(findings, mode, questions)
    return _common(
        analysis="roster", mode=mode, title="Revisão da equipe de agentes", summary=summary,
        findings=findings, counts=counts, verdict=verdict, questions=questions, rows=agents,
        metrics={
            "agents": len(agents), "active": active, "inactive": inactive, "roots": len(roots),
            "monthlyBudget": _decimal_out(total_budget), "dangerous": dangerous, "cycles": len(cycles),
        },
        limitations=limitations,
    )


# ---------------------------------------------------------------- quadro


def _blocker_status(blocker_id: str, tasks: dict[str, dict[str, Any]]) -> str:
    task = tasks.get(blocker_id.casefold())
    return task["status"] if task else "unknown"


def _cycles_multi(graph: dict[str, list[str]]) -> list[list[str]]:
    state: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    cycles: list[list[str]] = []
    seen: set[frozenset[str]] = set()

    def walk(node: str) -> None:
        state[node] = 1
        stack.append(node)
        on_stack.add(node)
        for next_node in graph.get(node, []):
            if next_node not in graph:
                continue
            if state.get(next_node, 0) == 0:
                walk(next_node)
            elif next_node in on_stack:
                index = stack.index(next_node)
                cycle = stack[index:]
                key = frozenset(cycle)
                if key not in seen:
                    seen.add(key)
                    cycles.append(cycle[:])
        stack.pop()
        on_stack.discard(node)
        state[node] = 2

    for node in sorted(graph):
        if state.get(node, 0) == 0:
            walk(node)
    return cycles


def audit_board(*, tasks: str, mode: str = "full", wip_limit: int = 5, stale_days: int = 3, reference_date: str = "") -> dict[str, Any]:
    if mode not in {"lite", "full", "ultra"}:
        raise AgencyError("Nível inválido: use lite, full ou ultra.")
    if not 1 <= wip_limit <= 50:
        raise AgencyError("O limite de trabalho em andamento deve ficar entre 1 e 50.")
    if not 1 <= stale_days <= 90:
        raise AgencyError("O limite de dias parados deve ficar entre 1 e 90.")
    reference = _reference_date(reference_date)
    source = _split_rows(tasks, 8, "tarefa")
    findings: list[dict[str, Any]] = []

    def add(group: str, kind: str, title: str, location: str, what: str, problem: str, fix: str, if_skipped: str) -> None:
        findings.append({
            "id": 0, "group": group, "kind": kind, "title": title, "location": location,
            "what": what, "problem": problem, "fix": fix, "ifSkipped": if_skipped,
        })

    parsed: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for number, cells in source:
        raw_id, title, owner, status_raw, goal, blockers_raw, evidence, updated_raw = cells
        task_id = _cell(raw_id)
        if not task_id:
            add("must", "missing-id", "Tarefa sem ID", f"linha {number}", "A primeira coluna está vazia.",
                "Sem ID, bloqueios e referências não podem apontar para esta tarefa.",
                "Use um identificador estável, como ENG-12.", "O quadro perde rastreabilidade.")
            continue
        key = task_id.casefold()
        if key in seen:
            add("must", "duplicate", f"ID repetido: {task_id}", f"linha {number}", f"`{task_id}` já foi usado na linha {seen[key]}.",
                "Dois donos e dois estados para o mesmo ID tornam o quadro ambíguo.",
                "Mantenha um único registro por ID.", "Uma conclusão pode sobrescrever a outra.")
            continue
        seen[key] = number
        status = _TASK_STATUS.get(_norm(_cell(status_raw)), "unknown") if _cell(status_raw) else "unknown"
        blockers = [item.strip() for item in re.split(r"[,;]", blockers_raw) if _cell(item)]
        updated: date | None = None
        if _cell(updated_raw):
            try:
                updated = _iso_date(updated_raw, f"Atualização de {task_id}")
            except AgencyError as exc:
                add("must", "invalid-date", f"Data inválida: {task_id}", task_id, str(exc),
                    "Sem data confiável, a inatividade não pode ser medida.",
                    "Use o formato AAAA-MM-DD.", "A tarefa pode parecer fresca para sempre.")
        parsed.append({
            "id": task_id, "title": _cell(title), "owner": _cell(owner), "status": status,
            "goal": _cell(goal), "blockers": blockers, "evidence": _cell(evidence),
            "updated": _cell(updated_raw), "updatedDate": updated, "line": number,
        })

    by_id = {task["id"].casefold(): task for task in parsed}
    graph: dict[str, list[str]] = {}
    for task in parsed:
        task_id = task["id"]
        if task["status"] == "unknown":
            add("must", "invalid-status", f"Estado inválido: {task_id}", task_id,
                f"`{task['status']}` não é um estado reconhecido.", "O quadro não sabe se a tarefa está parada ou viva.",
                "Use todo, in_progress, in_review, blocked, done ou cancelled.", "A tarefa escapa do watchdog e do WIP.")
        if not task["title"]:
            add("must", "missing-title", f"Tarefa sem título: {task_id}", task_id, "A coluna de título está vazia.",
                "Sem título, a intenção do trabalho não é recuperável.", "Resuma a entrega em uma frase.", "A tarefa vira um ID opaco.")
        if not task["owner"] and task["status"] in {"started", "review", "blocked"}:
            add("must", "missing-owner", f"Tarefa sem dono: {task_id}", task_id, "O trabalho está em andamento sem responsável.",
                "Sem dono único, ninguém responde pela entrega ou pelo desbloqueio.",
                "Atribua exatamente um agente ou pessoa.", "O trabalho para no próximo heartbeat.")
        if not task["owner"] and task["status"] in {"done"}:
            add("should", "missing-owner", f"Entrega sem dono: {task_id}", task_id, "A tarefa foi concluída sem responsável declarado.",
                "Não há como reconhecer quem entregou nem quem revisou.", "Registre o dono da entrega.", "A autoria se perde.")
        if task["status"] == "done" and not task["evidence"]:
            add("must", "done-without-evidence", f"Concluída sem evidência: {task_id}", task_id, "O estado é `done`, mas a coluna de evidência está vazia.",
                "Declarar conclusão sem prova é a falha que o watchdog existe para pegar.",
                "Anexe teste, diff, link, captura ou revisão que sustente a conclusão.", "A conclusão é uma alegação sem verificação.")
        if task["status"] == "review" and not task["evidence"]:
            add("must", "review-without-evidence", f"Revisão sem evidência: {task_id}", task_id, "O estado é `in_review`, mas não há evidência nem revisor declarado.",
                "Revisão sem revisor real costuma ser um estado estacionado para sempre.",
                "Nomeie o revisor e o artefato que ele deve verificar.", "A tarefa fica parada parecendo viva.")
        if task["status"] == "review" and task["evidence"] and not _REVIEW_HINT.search(task["evidence"]):
            add("should", "review-without-reviewer", f"Revisor não identificado: {task_id}", task_id,
                f"Evidência declarada: `{task['evidence'][:160]}`.",
                "Há um artefato, mas nenhum nome ou papel que prove quem revisa.",
                "Inclua `@revisor` ou o papel responsável pela revisão.", "A revisão pode ser autoaprovada em silêncio.")
        if task["status"] == "blocked" and not task["blockers"]:
            add("must", "blocked-without-blocker", f"Bloqueio sem causa: {task_id}", task_id, "O estado é `blocked`, mas nenhum ID bloqueador foi declarado.",
                "Sem bloqueador nomeado, o desbloqueio não tem próximo passo.", "Informe o ID que bloqueia ou o dono externo.",
                "A tarefa fica bloqueada por prazo indeterminado.")
        if task["status"] == "blocked" and task["blockers"]:
            resolved = [blocker for blocker in task["blockers"] if _blocker_status(blocker, by_id) in {"done", "cancelled"}]
            if len(resolved) == len(task["blockers"]):
                add("should", "stale-blocker", f"Bloqueio já resolvido: {task_id}", task_id,
                    f"Todos os bloqueadores estão concluídos ou cancelados: {', '.join(resolved)}.",
                    "A tarefa continua marcada como bloqueada sem motivo atual.", "Reabra ou conclua a tarefa.", "O quadro atrasa uma entrega já liberada.")
        dangling = [blocker for blocker in task["blockers"] if blocker.casefold() not in by_id]
        if dangling:
            add("must", "dangling-blocker", f"Bloqueador inexistente: {task_id}", task_id,
                f"IDs não encontrados: {', '.join(dangling)}.", "Um bloqueio que aponta para o vazio nunca será resolvido.",
                "Corrija o ID ou declare o bloqueio como externo no título.", "O trabalho fica preso sem dono.")
        if task["id"].casefold() in {blocker.casefold() for blocker in task["blockers"]}:
            add("must", "self-block", f"Tarefa bloqueia a si mesma: {task_id}", task_id, "O ID aparece na própria lista de bloqueadores.",
                "Auto-bloqueio é um ciclo de um nó e nunca termina.", "Remova o auto-bloqueio.", "A tarefa nunca sai de blocked.")
        if task["status"] == "done":
            open_blockers = [blocker for blocker in task["blockers"] if _blocker_status(blocker, by_id) not in {"done", "cancelled", "unknown"}]
            if open_blockers:
                add("must", "done-with-open-blocker", f"Concluída com bloqueio aberto: {task_id}", task_id,
                    f"Bloqueadores ainda abertos: {', '.join(open_blockers)}.", "A conclusão contradiz a dependência declarada.",
                    "Reabra a tarefa ou conclua o bloqueador primeiro.", "A entrega é aceita sem a base necessária.")
        if task["status"] not in {"cancelled"} and not task["goal"]:
            add("should", "no-goal", f"Sem objetivo: {task_id}", task_id, "A coluna de objetivo está vazia.",
                "Sem vínculo com um objetivo, o agente não recebe o porquê do trabalho.",
                "Vincule a tarefa a um objetivo ou iniciativa.", "O trabalho pode otimizar a coisa errada.")
        if task["status"] in {"started", "review", "blocked"}:
            if not task["updated"]:
                add("should", "no-update", f"Sem atualização: {task_id}", task_id, "A tarefa está ativa, mas não declara a última atualização.",
                    "Sem data, a inatividade não pode ser distinguida de trabalho recente.",
                    "Registre a data ISO da última mudança.", "O watchdog não detecta trabalho parado.")
            elif task["updatedDate"]:
                age = (reference - task["updatedDate"]).days
                if age < 0:
                    add("should", "future-date", f"Data futura: {task_id}", task_id,
                        f"A atualização `{task['updated']}` está no futuro em relação a {reference.isoformat()}.",
                        "Uma data futura mascara a inatividade.", "Corrija a data.", "A tarefa parece sempre fresca.")
                elif age > stale_days:
                    add("should", "stale", f"Trabalho parado: {task_id}", task_id,
                        f"Sem atualização há {age} dias (limite {stale_days}).", "Trabalho ativo sem sinal pode estar travado.",
                        "Peça uma atualização, reatribua ou abra um bloqueio explícito.", "O trabalho fica parado parecendo em andamento.")
        graph[task["id"]] = [by_id[blocker.casefold()]["id"] for blocker in task["blockers"] if blocker.casefold() in by_id]

    for cycle in _cycles_multi(graph):
        add("must", "dependency-cycle", "Ciclo de dependências", " → ".join(cycle + [cycle[0]]),
            "As tarefas se bloqueiam mutuamente.", "Em um ciclo, nenhuma das tarefas pode começar.",
            "Quebre o ciclo removendo uma dependência artificial.", "Todas as tarefas ficam bloqueadas para sempre.")

    wip = sum(1 for task in parsed if task["status"] in {"started", "review"})
    if wip > wip_limit:
        add("should", "wip-limit", f"WIP acima do limite: {wip}", "quadro",
            f"{wip} tarefas em andamento ou revisão; o limite declarado é {wip_limit}.",
            "Muito trabalho simultâneo reduz a chance de revisão real em cada entrega.",
            "Conclua ou pause trabalho antes de começar outro.", "O quadro acumula trabalhos pela metade.")

    stale = sum(
        1 for task in parsed
        if task["status"] in {"started", "review", "blocked"} and task["updatedDate"]
        and 0 <= (reference - task["updatedDate"]).days
        and (reference - task["updatedDate"]).days > stale_days
    )
    without_goal = sum(1 for task in parsed if task["status"] != "cancelled" and not task["goal"])
    unowned = sum(1 for task in parsed if not task["owner"])
    questions = [
        "Quem revisa cada tarefa que está em revisão?",
        "Qual trabalho está parado esperando uma decisão humana e quem decide?",
        "O objetivo de cada tarefa ainda é o mesmo que justificou o trabalho?",
    ]
    limitations = [
        "O quadro é a declaração colada; comentários, anexos e histórico real não são lidos.",
        "A idade usa a data de referência informada ou o dia atual em UTC, não o relógio de outro fuso.",
    ]
    summary = [
        f"**Quadro:** {len(parsed)} tarefas · {wip} em andamento/revisão · {sum(1 for task in parsed if task['status'] == 'blocked')} bloqueadas · {sum(1 for task in parsed if task['status'] == 'done')} concluídas.",
        f"**Higiene:** {unowned} sem dono · {without_goal} sem objetivo · {stale} paradas há mais de {stale_days} dias · WIP {wip}/{wip_limit}.",
    ]
    findings, counts, verdict, questions = _finalize(findings, mode, questions)
    for task in parsed:
        task.pop("updatedDate", None)
    return _common(
        analysis="board", mode=mode, title="Revisão do quadro de trabalho", summary=summary,
        findings=findings, counts=counts, verdict=verdict, questions=questions, rows=parsed,
        metrics={
            "tasks": len(parsed), "wip": wip, "wipLimit": wip_limit, "blocked": sum(1 for task in parsed if task["status"] == "blocked"),
            "done": sum(1 for task in parsed if task["status"] == "done"), "unowned": unowned,
            "withoutGoal": without_goal, "stale": stale, "staleDays": stale_days,
        },
        limitations=limitations,
    )


# ---------------------------------------------------------------- orçamento


def audit_budget(*, entries: str, mode: str = "full", company_budget: str = "", currency: str = "US$", period_day: int = 0, days_in_month: int = 30) -> dict[str, Any]:
    if mode not in {"lite", "full", "ultra"}:
        raise AgencyError("Nível inválido: use lite, full ou ultra.")
    if not 0 <= period_day <= 31:
        raise AgencyError("O dia do período deve ficar entre 0 e 31 (0 desliga a projeção).")
    if not 28 <= days_in_month <= 31:
        raise AgencyError("O mês deve ter entre 28 e 31 dias.")
    if period_day > days_in_month:
        raise AgencyError("O dia do período não pode passar do último dia do mês.")
    currency = _cell(currency) or "US$"
    if len(currency) > 8:
        raise AgencyError("Use uma unidade de moeda curta, como US$ ou BRL.")
    company: Decimal | None = None
    if _cell(company_budget):
        company = _money(company_budget, "Teto da empresa")
        if company < 0:
            raise AgencyError("O teto da empresa não pode ser negativo.")
    source = _split_rows(entries, 5, "orçamento")
    findings: list[dict[str, Any]] = []

    def add(group: str, kind: str, title: str, location: str, what: str, problem: str, fix: str, if_skipped: str) -> None:
        findings.append({
            "id": 0, "group": group, "kind": kind, "title": title, "location": location,
            "what": what, "problem": problem, "fix": fix, "ifSkipped": if_skipped,
        })

    rows: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for number, cells in source:
        name_raw, limit_raw, spent_raw, alert_raw, hard_raw = cells
        name = _cell(name_raw)
        if not name:
            add("must", "missing-agent", "Orçamento sem agente", f"linha {number}", "A primeira coluna está vazia.",
                "Sem dono, o limite não pode ser aplicado.", "Informe o agente.", "O valor fica órfão.")
            continue
        key = name.casefold()
        if key in seen:
            add("must", "duplicate", f"Orçamento repetido: {name}", f"linha {number}", f"`{name}` já aparece na linha {seen[key]}.",
                "Dois limites para o mesmo agente tornam a parada automática imprevisível.",
                "Mantenha uma linha por agente.", "O agente pode escapar do teto real.")
            continue
        seen[key] = number
        try:
            limit = _money(limit_raw, f"Limite de {name}")
        except AgencyError as exc:
            add("must", "invalid-limit", f"Limite inválido: {name}", f"linha {number}", str(exc),
                "Sem limite numérico, a parada automática não tem gatilho.", "Use um valor decimal positivo.", "O gasto corre sem teto.")
            limit = Decimal("0")
        try:
            spent = _money(spent_raw, f"Gasto de {name}")
        except AgencyError as exc:
            add("must", "invalid-spend", f"Gasto inválido: {name}", f"linha {number}", str(exc),
                "Sem o gasto declarado, a utilização não pode ser calculada.", "Informe o gasto acumulado no período.", "O risco de estouro fica invisível.")
            spent = Decimal("0")
        alert = Decimal("80")
        if _cell(alert_raw):
            try:
                alert = _percent(alert_raw, f"Alerta de {name}")
            except AgencyError as exc:
                add("must", "invalid-alert", f"Alerta inválido: {name}", f"linha {number}", str(exc),
                    "Um gatilho de alerta inválido nunca dispara.", "Use um percentual entre 0 e 100.", "O estouro chega sem aviso.")
        hard_stop = _flag(hard_raw)
        if hard_stop is None:
            add("should", "undeclared-hard-stop", f"Parada não declarada: {name}", f"linha {number}",
                f"`{_cell(hard_raw) or '(vazio)'}` não é sim ou não.",
                "Sem declarar a parada, o limite é apenas informativo.", "Use `sim` ou `não`.", "O gasto pode continuar após o teto.")
            hard_stop = False
        if limit < 0 or spent < 0:
            add("must", "negative", f"Valor negativo: {name}", f"linha {number}", f"Limite {limit} e gasto {spent}.",
                "Valores negativos não representam um orçamento real.", "Use zero ou valores positivos.", "A soma da empresa fica distorcida.")
        utilization = _ratio_out(spent, limit)
        projected: Decimal | None = None
        if period_day:
            projected = (spent / Decimal(period_day) * Decimal(days_in_month)).quantize(MONEY, rounding=ROUND_HALF_UP)
        if limit <= 0 and spent > 0:
            add("must", "spend-without-limit", f"Gasto sem limite: {name}", name,
                f"Limite {_decimal_out(limit):.2f} com gasto {_decimal_out(spent):.2f}.",
                "Não existe teto positivo para sustentar o gasto.", "Defina um limite ou zere o consumo.", "O gasto não pode ser contido.")
        elif spent > limit:
            add("must", "over-budget", f"Orçamento estourado: {name}", name,
                f"Gasto {currency} {_decimal_out(spent):.2f} contra limite {currency} {_decimal_out(limit):.2f}.",
                "O agente já consumiu mais do que o teto declarado.", "Pause o agente e revise o limite antes de retomar.",
                "O custo continua crescendo sem autorização.")
        elif spent == limit and limit > 0 and not hard_stop:
            add("must", "limit-without-stop", f"No teto sem parada: {name}", name,
                f"Gasto igual ao limite ({currency} {_decimal_out(spent):.2f}) e parada automática desligada.",
                "Sem parada, o próximo heartbeat ultrapassa o teto.", "Ative a parada automática ou aumente o limite com aprovação.",
                "O estouro acontece no próximo ciclo.")
        elif limit > 0 and utilization >= float(alert) and spent < limit:
            add("should", "alert-threshold", f"Alerta de orçamento: {name}", name,
                f"Utilização de {utilization:.1f}% (alerta em {alert}%).",
                "O agente está perto do teto e ainda pode iniciar trabalho caro.", "Reduza o escopo ou prepare a renovação.",
                "O estouro pega a operação sem plano.")
        if not hard_stop and spent <= limit and limit > 0:
            add("should" if utilization >= 50 else "nice", "no-hard-stop", f"Sem parada automática: {name}", name,
                "A parada automática não está declarada como ativa.",
                "Um limite sem parada depende de alguém olhar o painel a tempo.", "Ative a parada automática no limite.",
                "O controle é reativo e falha fora do horário.")
        if projected is not None and limit > 0 and projected > limit:
            add("should", "projected-over", f"Projeção acima do limite: {name}", name,
                f"No ritmo atual, o mês fecha em {currency} {_decimal_out(projected):.2f}, acima do limite {currency} {_decimal_out(limit):.2f}.",
                "O gasto atual ainda cabe, mas a tendência não cabe.", "Reduza o ritmo, o escopo ou renegocie o teto.",
                "O estouro aparece perto do fim do mês, sem tempo de reação.")
        rows.append({
            "agent": name, "limit": _decimal_out(limit), "spent": _decimal_out(spent),
            "alert": float(alert), "hardStop": hard_stop, "utilization": utilization,
            "projected": None if projected is None else _decimal_out(projected), "line": number,
        })

    total_limit = sum((Decimal(str(row["limit"])) for row in rows), Decimal("0"))
    total_spent = sum((Decimal(str(row["spent"])) for row in rows), Decimal("0"))
    total_projected = sum((Decimal(str(row["projected"])) for row in rows if row["projected"] is not None), Decimal("0")) if period_day else None
    if company is not None:
        if total_limit > company:
            add("should", "limits-above-company", "Limites acima do teto da empresa", "empresa",
                f"A soma dos limites é {currency} {_decimal_out(total_limit):.2f}; o teto da empresa é {currency} {_decimal_out(company):.2f}.",
                "Os agentes podem gastar, somados, mais do que a empresa autorizou.",
                "Reduza os limites individuais ou aumente o teto com aprovação.", "O teto da empresa não é o teto real.")
        if total_spent > company:
            add("must", "company-overspend", "Gasto acima do teto da empresa", "empresa",
                f"Gasto total {currency} {_decimal_out(total_spent):.2f} contra teto {currency} {_decimal_out(company):.2f}.",
                "A operação já consome mais do que o orçamento da empresa.", "Pause os agentes maiores e revise o teto.",
                "O custo fica sem autorização de alto nível.")
        if total_projected is not None and total_projected > company:
            add("should", "projected-company", "Projeção acima do teto da empresa", "empresa",
                f"Projeção total {currency} {_decimal_out(total_projected):.2f} contra teto {currency} {_decimal_out(company):.2f}.",
                "A tendência do mês excede o orçamento da empresa.", "Ajuste o ritmo antes do fechamento.",
                "O estouro corporativo aparece no fim do período.")

    over = sum(1 for row in rows if Decimal(str(row["spent"])) > Decimal(str(row["limit"])))
    without_stop = sum(1 for row in rows if not row["hardStop"])
    questions = [
        "Quem aprova aumentar um limite quando o alerta dispara?",
        "O que acontece exatamente ao atingir 100%: pausa, fila ou continuação silenciosa?",
        "A projeção usa o ritmo real de consumo ou apenas uma média otimista?",
    ]
    limitations = [
        "Os valores são declarados; faturas, tokens e preços de provedor não são consultados.",
        "Não há conversão de moeda: a unidade informada é tratada como única.",
        "A projeção é linear e ignora picos, retries e mudança de modelo.",
    ]
    summary = [
        f"**Orçamento:** {len(rows)} agentes · limite total {currency} {_decimal_out(total_limit):.2f} · gasto {currency} {_decimal_out(total_spent):.2f} · utilização {_ratio_out(total_spent, total_limit):.1f}%.",
        f"**Risco:** {over} acima do limite · {without_stop} sem parada automática" + (f" · projeção {currency} {_decimal_out(total_projected):.2f}." if total_projected is not None else "."),
    ]
    findings, counts, verdict, questions = _finalize(findings, mode, questions)
    return _common(
        analysis="budget", mode=mode, title="Revisão de orçamento dos agentes", summary=summary,
        findings=findings, counts=counts, verdict=verdict, questions=questions, rows=rows,
        metrics={
            "agents": len(rows), "currency": currency, "totalLimit": _decimal_out(total_limit),
            "totalSpent": _decimal_out(total_spent), "utilization": _ratio_out(total_spent, total_limit),
            "overBudget": over, "withoutHardStop": without_stop,
            "projected": None if total_projected is None else _decimal_out(total_projected),
            "companyBudget": None if company is None else _decimal_out(company),
            "periodDay": period_day, "daysInMonth": days_in_month,
        },
        limitations=limitations,
    )


# ---------------------------------------------------------------- parada


_MANDATE = [
    "Trate cada folha parada como uma alegação que precisa ser verificada contra evidência, não como um fato.",
    "Aceite a parada quando a evidência sustenta a conclusão; registre o que foi checado.",
    "Se a folha não estiver concluída, restaure um caminho vivo: reabra, reatribua, comente instruções ou crie uma tarefa-filha dentro do recorte.",
    "Se o bloqueio for real, exija o dono do desbloqueio e o próximo passo nomeados.",
    "Fique dentro do recorte observado; não altere nada fora da árvore declarada.",
    "Não impersone aprovação formal, gasto, contratação ou decisão de política.",
    "Não crie outro watchdog para o mesmo recorte e não acorde a si mesmo.",
    "Exatamente uma tarefa de revisão por impressão digital de parada.",
]


_WIDENING = [
    ("aprovacao", re.compile(r"\b(aprovar|aprove|aprovado|autorizar|autorize|liberar|libere|impersonar)\b", re.I), "Aprovação formal é decisão humana; instruções não podem concedê-la."),
    ("gasto", re.compile(r"\b(gastar|gaste|comprar|compre|contratar|contrate|pagar|pague|aumentar\s+o\s+or[cç]amento)\b", re.I), "Gasto e contratação exigem aprovação fora do mandato do watchdog."),
    ("watchdog", re.compile(r"\b(criar?|crie)\s+(um\s+|outro\s+)?watchdog\b", re.I), "Um watchdog não pode criar outro watchdog."),
    ("autoacordar", re.compile(r"\b(acordar?|acorde|despertar?)\s+(a\s+si|voc[eê]\s+mesm[oa])\b", re.I), "O watchdog não pode acordar a si mesmo."),
    ("escopo", re.compile(r"\b(qualquer|todas?\s+as?)\s+(tarefa|issue|atividade)\b|\bfora\s+da\s+(sub)?[aá]rvore\b", re.I), "O recorte é fechado: instruções não podem ampliá-lo."),
]
_NEGATIONS = ("nao", "não", "nunca", "jamais", "proibido", "proibida", "sem")


def _mandate_risks(instructions: str) -> list[tuple[str, str, str]]:
    risks: list[tuple[str, str, str]] = []
    for kind, pattern, problem in _WIDENING:
        for match in pattern.finditer(instructions):
            window = _norm(instructions[max(0, match.start() - 25):match.start()])
            if any(negation in window for negation in _NEGATIONS):
                continue
            clause = instructions[max(0, match.start() - 40):match.end() + 40].replace("\n", " ").strip()
            risks.append((kind, clause, problem))
            break
    return risks


def _fingerprint(watched: str, instructions: str, rows: list[dict[str, Any]]) -> str:
    payload = {
        "watched": watched.strip(),
        "instructions": instructions.strip(),
        "tasks": [
            {key: row[key] for key in ("id", "status", "owner", "evidence", "blocker", "interaction", "updated")}
            for row in sorted(rows, key=lambda row: row["id"].casefold())
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verify_watchdog(
    *,
    watched: str,
    tasks: str,
    instructions: str = "",
    exclude: str = "",
    last_fingerprint: str = "",
    mode: str = "full",
) -> dict[str, Any]:
    if mode not in {"lite", "full", "ultra"}:
        raise AgencyError("Nível inválido: use lite, full ou ultra.")
    watched = _cell(watched)
    if not watched:
        raise AgencyError("Informe o ID da tarefa observada.")
    if len(watched) > 80:
        raise AgencyError("O ID observado deve ter até 80 caracteres.")
    if len(instructions) > 4000:
        raise AgencyError("As instruções devem ter até 4.000 caracteres.")
    fingerprint_input = _cell(last_fingerprint)
    if fingerprint_input and not _HEX64.match(fingerprint_input):
        raise AgencyError("A impressão digital anterior deve ter 64 caracteres hexadecimais.")
    excluded = {item.casefold() for item in re.split(r"[,;\s]+", exclude) if item.strip()}
    source = _split_rows(tasks, 7, "tarefa observada")
    findings: list[dict[str, Any]] = []

    def add(group: str, kind: str, title: str, location: str, what: str, problem: str, fix: str, if_skipped: str) -> None:
        findings.append({
            "id": 0, "group": group, "kind": kind, "title": title, "location": location,
            "what": what, "problem": problem, "fix": fix, "ifSkipped": if_skipped,
        })

    rows: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for number, cells in source:
        raw_id, status_raw, owner, evidence, blocker, interaction, updated_raw = cells
        task_id = _cell(raw_id)
        if not task_id:
            add("must", "missing-id", "Tarefa sem ID", f"linha {number}", "A primeira coluna está vazia.",
                "Sem ID, a folha não pode ser citada na revisão.", "Informe o identificador.", "A revisão perde a referência.")
            continue
        if task_id.casefold() in excluded:
            continue
        if task_id.casefold() in seen:
            add("must", "duplicate", f"Tarefa repetida: {task_id}", f"linha {number}", f"`{task_id}` já aparece na linha {seen[task_id.casefold()]}.",
                "Duas versões da mesma folha tornam a impressão digital instável.",
                "Mantenha uma linha por tarefa.", "A revisão pode ser disparada duas vezes.")
            continue
        seen[task_id.casefold()] = number
        status = _TASK_STATUS.get(_norm(_cell(status_raw)), "unknown") if _cell(status_raw) else "unknown"
        updated = _cell(updated_raw)
        if updated:
            try:
                _iso_date(updated, f"Atualização de {task_id}")
            except AgencyError as exc:
                add("must", "invalid-date", f"Data inválida: {task_id}", task_id, str(exc),
                    "A impressão digital precisa de uma data canônica.", "Use AAAA-MM-DD.", "A comparação com a revisão anterior falha.")
        rows.append({
            "id": task_id, "status": status, "owner": _cell(owner), "evidence": _cell(evidence),
            "blocker": _cell(blocker), "interaction": _cell(interaction), "updated": updated, "line": number,
        })
    if not rows:
        raise AgencyError("Nenhuma tarefa sobrou depois de aplicar as exclusões.")
    if len(rows) > MAX_ROWS:
        raise AgencyError(f"A árvore tem {len(rows)} tarefas; o limite é {MAX_ROWS}.")

    for kind, clause, problem in _mandate_risks(instructions):
        add("must", "widening-instruction", "Instrução amplia o mandato", f"instruções · {kind}",
            f"Trecho declarado: `{clause[:180]}`.",
            problem + " Instruções customizadas só podem estreitar o mandato.",
            "Reescreva o trecho como restrição ou remova-o das instruções.",
            "O watchdog passa a agir fora do recorte aprovado.")

    by_id = {row["id"].casefold(): row for row in rows}
    live = [row["id"] for row in rows if row["status"] in _LIVE_STATUSES]
    fingerprint: str | None = None
    claims: list[dict[str, Any]] = []
    fired = False
    suppressed = False
    if live:
        verdict = f"Não dispara: {len(live)} tarefa(s) ainda têm caminho vivo ({', '.join(live[:5])})."
    else:
        fingerprint = _fingerprint(watched, instructions, rows)
        suppressed = bool(fingerprint_input) and fingerprint_input.casefold() == fingerprint
        fired = not suppressed
        for row in rows:
            task_id = row["id"]
            status = row["status"]
            verified = False
            reason = ""
            action = ""
            if status == "done":
                if not row["evidence"]:
                    action = "reabrir e exigir evidência"
                    add("must", "done-without-evidence", f"Concluída sem evidência: {task_id}", task_id,
                        "O estado é `done`, mas não há prova anexada.", "A conclusão é uma alegação não verificada.",
                        "Reabra e exija teste, diff, link ou revisão.", "O trabalho pode estar incompleto e ninguém percebe.")
                elif row["blocker"]:
                    blocker_status = _blocker_status(re.split(r"[,;\s]+", row["blocker"])[0], by_id)
                    if blocker_status == "unknown":
                        action = "confirmar bloqueador fora do recorte"
                        add("should", "external-blocker", f"Bloqueador fora do recorte: {task_id}", task_id,
                            f"`{row['blocker']}` não está na árvore observada.", "A conclusão não pode ser confirmada contra um bloqueador fora do recorte.",
                            "Inclua a tarefa bloqueadora na árvore ou declare a evidência que a resolve.", "A verificação fica incompleta.")
                    elif blocker_status not in {"done", "cancelled"}:
                        action = "reabrir até concluir o bloqueador"
                        add("must", "done-with-open-blocker", f"Concluída com bloqueio aberto: {task_id}", task_id,
                            f"O bloqueador `{row['blocker']}` ainda está `{blocker_status}`.", "A conclusão contradiz a dependência.",
                            "Reabra a tarefa ou conclua o bloqueador.", "A entrega é aceita sem a base necessária.")
                    else:
                        verified = True
                        reason = "Conclusão com evidência e bloqueadores resolvidos."
                else:
                    verified = True
                    reason = "Conclusão com evidência declarada."
            elif status == "cancelled":
                if row["evidence"]:
                    verified = True
                    reason = "Cancelamento com motivo declarado."
                else:
                    action = "registrar o motivo do cancelamento"
                    add("should", "cancel-without-reason", f"Cancelamento sem motivo: {task_id}", task_id,
                        "O estado é `cancelled`, mas não há motivo ou referência.", "Cancelar sem motivo apaga a decisão do registro.",
                        "Registre por que o trabalho foi abandonado.", "A decisão não pode ser auditada depois.")
            elif status == "blocked":
                if not row["blocker"]:
                    action = "nomear bloqueador e dono"
                    add("must", "blocked-without-blocker", f"Bloqueio sem causa: {task_id}", task_id,
                        "O estado é `blocked`, mas não há bloqueador nomeado.", "Sem causa, o desbloqueio não tem próximo passo.",
                        "Nomeie o bloqueador e o dono do desbloqueio.", "A tarefa fica parada sem prazo.")
                elif not _OWNER_HINT.search(row["blocker"]):
                    action = "nomear o dono do desbloqueio"
                    add("should", "blocker-without-owner", f"Bloqueio sem dono: {task_id}", task_id,
                        f"Bloqueador declarado: `{row['blocker']}`.", "Ninguém está nomeado para desbloquear.",
                        "Inclua `@dono` ou `dono:` no motivo do bloqueio.", "A espera não tem responsável.")
                else:
                    verified = True
                    reason = "Bloqueio com causa e dono declarados."
            elif status == "review":
                if not row["evidence"]:
                    action = "nomear revisor e artefato"
                    add("must", "review-without-evidence", f"Revisão sem evidência: {task_id}", task_id,
                        "O estado é `in_review`, mas não há artefato nem revisor.", "Revisão sem prova costuma ser um estado estacionado.",
                        "Nomeie o revisor e o artefato revisado.", "A tarefa fica parada parecendo viva.")
                elif not _REVIEW_HINT.search(row["evidence"]):
                    action = "identificar quem revisa"
                    add("should", "review-without-reviewer", f"Revisor não identificado: {task_id}", task_id,
                        f"Evidência declarada: `{row['evidence'][:160]}`.", "Falta um nome ou papel que prove quem revisa.",
                        "Inclua `@revisor` ou o papel responsável.", "A revisão pode ser autoaprovada.")
                else:
                    verified = True
                    reason = "Revisão com evidência e revisor identificados."
            elif status == "waiting":
                if row["interaction"]:
                    verified = True
                    reason = "Espera com interação nomeada."
                else:
                    action = "nomear a interação e quem responde"
                    add("must", "waiting-without-target", f"Espera sem alvo: {task_id}", task_id,
                        "O estado é `waiting`, mas não há interação ou pergunta declarada.", "A espera não tem destinatário nem critério de retomada.",
                        "Nomeie a interação, quem responde e o que destrava.", "A tarefa espera para sempre.")
            elif status == "unknown":
                action = "corrigir o estado"
                add("must", "invalid-status", f"Estado inválido: {task_id}", task_id, "O estado declarado não é reconhecido.",
                    "A folha não pode ser classificada como viva, concluída ou parada.", "Use um estado do quadro.", "A revisão ignora a tarefa.")
            elif status in {"triage", "unstarted"}:
                action = "atribuir, agendar ou cancelar"
                add("should", "never-started", f"Parada sem início: {task_id}", task_id,
                    f"O estado é `{status}` e a árvore está parada.", "Trabalho nunca iniciado também é uma parada que ninguém percebe.",
                    "Atribua, agende ou cancele explicitamente.", "A tarefa envelhece no quadro sem dono.")
            else:
                verified = True
                reason = "Estado de parada reconhecido."
            claims.append({"id": task_id, "status": status, "verified": verified, "reason": reason, "action": action})
        unverified = [claim["id"] for claim in claims if not claim["verified"]]
        if suppressed:
            verdict = "Revisão suprimida: a impressão digital não mudou desde a última revisão."
        elif unverified:
            verdict = f"Revisão devida: {len(unverified)} alegação(ões) sem verificação ({', '.join(unverified[:5])})."
        else:
            verdict = "Parada legítima pelas evidências declaradas; nenhuma alegação em aberto."

    slug = re.sub(r"[^a-z0-9-]+", "-", watched.lower()).strip("-")[:40] or "watchdog"
    review_task = f"watchdog-{slug}-{fingerprint[:8]}" if fingerprint else ""
    questions = [
        "Quem é a pessoa responsável por aceitar esta parada?",
        "Alguma evidência foi produzida fora da árvore e não está declarada aqui?",
        "O bloqueio real está dentro do recorte ou depende de outro time?",
    ]
    limitations = [
        "A verificação usa apenas as linhas coladas; comentários, anexos e histórico de execução não são lidos.",
        "A impressão digital cobre a parada e as instruções, não o conteúdo de arquivos ou testes.",
        "Nada é acordado, reaberto ou executado: a skill apenas indica se uma revisão é devida.",
        "A varredura de instruções é lexical; ela encontra ampliações explícitas, não intenções implícitas.",
    ]
    summary = [
        f"**Observado:** `{watched}` · {len(rows)} tarefa(s) · {len(live)} caminho(s) vivo(s) · {len(claims)} folha(s) parada(s).",
        f"**Impressão digital:** `{fingerprint}`." if fingerprint else "**Impressão digital:** não calculada enquanto houver caminho vivo.",
        f"**Revisão:** {'dispara' if fired else 'suprimida' if suppressed else 'não dispara'} · tarefa `{review_task or '—'}`.",
    ]
    stop_verdict = verdict
    findings, counts, verdict, questions = _finalize(findings, mode, questions)
    verdict = f"{verdict} {stop_verdict}" if counts["must"] else stop_verdict
    extra = ["", "## Mandato padrão", ""]
    extra += [f"- {item}" for item in _MANDATE]
    if instructions.strip():
        extra += ["", "## Instruções declaradas", "", instructions.strip()[:4000]]
    extra += ["", "## Folhas verificadas", ""]
    verified_claims = [claim for claim in claims if claim["verified"]]
    if verified_claims:
        extra += [f"- `{claim['id']}` — {claim['reason']}" for claim in verified_claims]
    elif claims:
        extra.append("- Nenhuma folha foi aceita sem ressalva.")
    else:
        extra.append("- Nenhuma folha parada: a árvore ainda tem caminho vivo.")
    return {
        **_common(
            analysis="watchdog", mode=mode, title="Verificação de parada (watchdog)", summary=summary,
            findings=findings, counts=counts, verdict=verdict, questions=questions, rows=rows,
            metrics={
                "watched": watched, "leaves": len(claims), "live": len(live),
                "unverified": len([claim for claim in claims if not claim["verified"]]),
                "fired": fired, "suppressed": suppressed,
            },
            limitations=limitations, extra_sections=extra,
        ),
        "watched": watched,
        "fingerprint": fingerprint,
        "lastFingerprint": fingerprint_input or None,
        "suppressed": suppressed,
        "fired": fired,
        "reviewTask": review_task,
        "claims": claims,
        "live": live,
        "excluded": sorted(excluded),
        "instructions": instructions.strip(),
    }


# ---------------------------------------------------------------- permissões

DEFAULT_GRANTS: list[tuple[str, str]] = [
    ("agents:configure", "Configurar agentes subordinados dentro do próprio escopo"),
    ("agents:suggest-changes", "Sugerir mudanças em agentes sem aplicá-las"),
    ("skills:create", "Criar skills dentro do escopo"),
    ("skills:suggest-changes", "Sugerir mudanças em skills"),
    ("tools:manage_connections", "Gerenciar conexões de ferramentas da equipe"),
    ("tools:profiles", "Criar e editar perfis de ferramentas"),
    ("tools:view_audit", "Ver a auditoria das próprias ferramentas"),
    ("tools:use", "Usar ferramentas conectadas"),
    ("tools:manage_runtime", "Gerenciar o runtime das ferramentas"),
    ("audit:view_agent_actions", "Ver ações de agentes no escopo"),
    ("inbox:manage", "Gerenciar a caixa de entrada de trabalho"),
    ("tasks:assign", "Atribuir tarefas"),
    ("tasks:assign_scope", "Atribuir escopo de tarefas"),
    ("tasks:manage_active_checkouts", "Gerenciar checkouts ativos"),
    ("canCreateAgents", "Criar agentes dentro da cota"),
    ("canCreateSkills", "Criar skills"),
    ("config:read_own", "Ler a própria configuração"),
    ("self:wake", "Acordar a si mesmo pelo heartbeat"),
]

DEFAULT_DENIALS: list[tuple[str, str]] = [
    ("agents:create", "Criar agentes fora do fluxo gerenciado"),
    ("environments:manage", "Criar ou alterar ambientes de execução"),
    ("tools:admin", "Administrar ferramentas da empresa"),
    ("users:invite", "Convidar pessoas"),
    ("users:manage_permissions", "Alterar permissões de pessoas"),
    ("joins:approve", "Aprovar entrada de novos membros"),
]

NEW_GRANTS = {
    "agents:configure", "skills:create", "tools:manage_connections", "tools:profiles",
    "tools:manage_runtime", "canCreateAgents", "canCreateSkills", "tasks:assign_scope",
    "tasks:manage_active_checkouts", "agents:suggest-changes", "skills:suggest-changes",
}
RUNTIME_FIELDS = {"adapter", "adaptador", "command", "comando", "cwd", "env", "ambiente", "sandbox", "filesystem"}
_RUNTIME_FIELD_NAMES = {
    "adapter": "adapter de processo", "adaptador": "adapter de processo", "command": "comando de host",
    "comando": "comando de host", "cwd": "diretório de trabalho", "env": "variáveis de ambiente",
    "ambiente": "variáveis de ambiente", "sandbox": "sandbox de filesystem", "filesystem": "sandbox de filesystem",
}


def default_permissions() -> dict[str, Any]:
    granted = [{"key": key, "reason": reason} for key, reason in DEFAULT_GRANTS]
    denied = [{"key": key, "reason": reason} for key, reason in DEFAULT_DENIALS]
    return {
        "analysis": "permissions",
        "mode": "reference",
        "granted": granted,
        "denied": denied,
        "metrics": {"granted": len(granted), "denied": len(denied), "newGrants": len(NEW_GRANTS)},
        "exceptions": [
            "Agentes de baixa confiança não recebem os grants novos.",
            "Agentes gerenciados pela plataforma não recebem os grants novos.",
            "Sem backfill: agentes existentes mantêm o que têm até uma revisão explícita.",
            "Agentes não definem adapter de processo, comando de host, cwd, env arbitrário nem sandbox de filesystem.",
        ],
        "executed": False,
        "readOnly": True,
        "limitations": [
            "É uma linha de base declarada, não uma leitura do provedor de identidade.",
            "A aplicação real depende de o runtime validar cada chave no servidor.",
        ],
    }


def audit_permissions(*, entries: str, low_trust: bool = False, managed: bool = False, mode: str = "full") -> dict[str, Any]:
    if mode not in {"lite", "full", "ultra"}:
        raise AgencyError("Nível inválido: use lite, full ou ultra.")
    source = _split_rows(entries, 4, "agente")
    findings: list[dict[str, Any]] = []

    def add(group: str, kind: str, title: str, location: str, what: str, problem: str, fix: str, if_skipped: str) -> None:
        findings.append({
            "id": 0, "group": group, "kind": kind, "title": title, "location": location,
            "what": what, "problem": problem, "fix": fix, "ifSkipped": if_skipped,
        })

    granted_keys = {_norm(key) for key, _ in DEFAULT_GRANTS}
    denied_keys = {_norm(key) for key, _ in DEFAULT_DENIALS}
    rows: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    total_grants = 0
    approvals = 0
    for number, cells in source:
        name_raw, granted_raw, denied_raw, flags_raw = cells
        name = _cell(name_raw)
        if not name:
            add("must", "missing-agent", "Linha sem agente", f"linha {number}", "A primeira coluna está vazia.",
                "Sem dono, a permissão não pode ser revisada.", "Informe o agente.", "A permissão fica sem responsável.")
            continue
        key = name.casefold()
        if key in seen:
            add("must", "duplicate", f"Agente repetido: {name}", f"linha {number}", f"`{name}` já aparece na linha {seen[key]}.",
                "Dois conjuntos de permissões para o mesmo agente tornam o acesso imprevisível.",
                "Mantenha uma linha por agente.", "O runtime pode aplicar o conjunto errado.")
            continue
        seen[key] = number
        granted = [item.strip() for item in re.split(r"[,;]", granted_raw) if _cell(item)]
        denied = [item.strip() for item in re.split(r"[,;]", denied_raw) if _cell(item)]
        flags = [item.strip() for item in re.split(r"[,;]", flags_raw) if _cell(item)]
        normalized = {_norm(item) for item in granted}
        flag_map: dict[str, str] = {}
        for flag in flags:
            if ":" in flag:
                flag_key, flag_value = flag.split(":", 1)
                flag_map[_norm(flag_key)] = flag_value.strip()
            else:
                flag_map[_norm(flag)] = ""
        agent_low_trust = low_trust or "baixa_confianca" in flag_map or "low_trust" in flag_map or "low-trust" in flag_map
        agent_managed = managed or "gerenciado" in flag_map or "managed" in flag_map

        wildcard = sorted(normalized & _WILDCARD_PERMISSIONS)
        if wildcard:
            add("must", "wildcard-permission", f"Permissão curinga: {name}", name,
                f"Concedido: {', '.join(granted)}.", "Curinga elimina o menor privilégio e não pode ser auditado por chave.",
                "Substitua por chaves nomeadas.", "Qualquer ferramenta pode ser usada sem revisão.")
        denied_granted = sorted({item for item in granted if _norm(item) in denied_keys})
        if denied_granted:
            approvals += len(denied_granted)
            add("must", "denied-granted", f"Permissão negada por padrão concedida: {name}", name,
                f"Chaves negadas por padrão presentes: {', '.join(denied_granted)}.",
                "Essas chaves ampliam o poder do agente sobre a empresa, não apenas sobre o próprio trabalho.",
                "Remova a chave ou registre uma aprovação explícita do conselho com escopo e prazo.",
                "O agente passa a administrar pessoas, ambientes ou ferramentas da empresa.")
        conflict = sorted({item for item in granted if _norm(item) in {_norm(other) for other in denied}})
        if conflict:
            add("must", "grant-deny-conflict", f"Permissão concedida e negada: {name}", name,
                f"Chaves nos dois lados: {', '.join(conflict)}.",
                "Conflito entre listas torna o acesso dependente da ordem de avaliação do runtime.",
                "Deixe a chave em um único lado.", "O resultado real é imprevisível.")
        unknown = sorted({item for item in granted + denied if _norm(item) not in granted_keys and _norm(item) not in denied_keys and _norm(item) not in _WILDCARD_PERMISSIONS})
        if unknown:
            add("should", "unknown-key", f"Chave fora do catálogo: {name}", name,
                f"Chaves desconhecidas: {', '.join(unknown)}.",
                "Uma chave que não está na linha de base não foi revisada por ninguém.",
                "Alinhe o nome à linha de base ou registre a nova chave com dono.", "Acesso não catalogado pode passar despercebido.")
        if agent_low_trust or agent_managed:
            expanded = sorted({item for item in granted if _norm(item) in NEW_GRANTS})
            if expanded:
                add("must", "exception-expanded", f"Exceção com grants novos: {name}", name,
                    f"{'Baixa confiança' if agent_low_trust else 'Agente gerenciado'} recebeu: {', '.join(expanded)}.",
                    "Baixa confiança e agentes gerenciados ficam de fora dos grants novos até revisão explícita.",
                    "Remova as chaves ou registre a exceção com aprovação.", "A exceção vira a regra sem ninguém decidir.")
        runtime_flags = sorted(
            (flag, value) for flag, value in flag_map.items()
            if flag in RUNTIME_FIELDS or any(flag.startswith(field + ":") for field in RUNTIME_FIELDS)
        )
        if runtime_flags:
            details = ", ".join(f"{_RUNTIME_FIELD_NAMES.get(flag, flag)}={value or '(vazio)'}" for flag, value in runtime_flags)
            add("must", "runtime-override", f"Agente define runtime: {name}", name,
                f"Campos declarados: {details}.",
                "Adapter de processo, comando de host, cwd, env e sandbox são decisão do operador, não do agente.",
                "Mova a configuração para o nível da empresa e remova do agente.", "O agente pode escapar do sandbox e do comando aprovado.")
        quota_raw = flag_map.get("cota") or flag_map.get("quota")
        created_raw = flag_map.get("criados") or flag_map.get("created")
        quota = None
        created = None
        if quota_raw:
            try:
                quota = int(quota_raw)
            except ValueError:
                add("should", "invalid-quota", f"Cota inválida: {name}", name, f"`{quota_raw}` não é inteiro.",
                    "Sem cota numérica, o limite de agentes criados não pode ser aplicado.", "Use um inteiro, como 3.", "A cota vira decorativa.")
        if created_raw:
            try:
                created = int(created_raw)
            except ValueError:
                add("should", "invalid-created", f"Criados inválidos: {name}", name, f"`{created_raw}` não é inteiro.",
                    "Sem o número de agentes criados, a cota não pode ser conferida.", "Use um inteiro.", "A cota não é verificada.")
        can_create = "cancreateagents" in normalized
        if can_create and quota is None:
            add("should", "create-without-quota", f"Criação sem cota: {name}", name,
                "`canCreateAgents` concedido sem cota declarada.",
                "Criar agentes sem limite multiplica custo e superfície de acesso.",
                "Declare `cota:N` junto da chave.", "A criação de agentes não tem teto.")
        if quota is not None and not can_create:
            add("nice", "quota-without-grant", f"Cota sem chave de criação: {name}", name,
                f"Cota {quota} declarada sem `canCreateAgents`.", "A cota não tem efeito sem a chave correspondente.",
                "Remova a cota ou conceda a chave.", "A configuração sugere um limite que não existe.")
        if quota is not None and created is not None and created > quota:
            add("must", "quota-exceeded", f"Cota excedida: {name}", name,
                f"{created} agentes criados contra cota {quota}.", "O agente já criou mais do que a empresa autorizou.",
                "Pause a criação e revise a cota com aprovação.", "Novos agentes continuam nascendo sem controle.")
        if not granted:
            add("should", "no-grants", f"Agente sem permissões: {name}", name,
                "Nenhuma permissão declarada.", "Sem grants, o agente não consegue trabalhar; com grants implícitos, ninguém sabe o que ele pode.",
                "Declare o conjunto mínimo necessário.", "O agente para ou opera com acesso desconhecido.")
        elif not denied:
            add("nice", "no-denials", f"Sem negações explícitas: {name}", name,
                "Só há permissões concedidas.", "O menor privilégio fica implícito e não revisável.",
                "Registre ao menos as chaves que o agente não pode ter.", "A revisão de acesso perde o contraste.")
        if len(granted) > 12:
            add("nice", "broad-grants", f"Conjunto amplo: {name}", name,
                f"{len(granted)} permissões concedidas.", "Conjuntos muito grandes raramente são revisados por completo.",
                "Divida em papéis menores.", "A revisão vira aprovação por atacado.")
        total_grants += len(granted)
        rows.append({
            "agent": name, "granted": granted, "denied": denied, "lowTrust": agent_low_trust,
            "managed": agent_managed, "quota": quota, "created": created, "line": number,
        })

    baseline_denied = {_norm(item) for row in rows for item in row["granted"]} & denied_keys
    questions = [
        "Quem pode conceder uma chave negada por padrão, e por quanto tempo?",
        "As exceções de baixa confiança e de agentes gerenciados têm dono e prazo?",
        "O runtime valida essas chaves no servidor ou apenas esconde botões na interface?",
    ]
    limitations = [
        "A auditoria compara com a linha de base embutida, não com o provedor de identidade real.",
        "Flags de cota e criação vêm da declaração; nada é contado em runtime.",
        "Não há backfill: a revisão não altera permissões existentes.",
    ]
    summary = [
        f"**Permissões:** {len(rows)} agentes · {total_grants} grants declarados · {len(baseline_denied)} chave(s) negada(s) por padrão concedida(s).",
        f"**Linha de base:** {len(DEFAULT_GRANTS)} concedidas · {len(DEFAULT_DENIALS)} negadas · sem backfill.",
    ]
    findings, counts, verdict, questions = _finalize(findings, mode, questions)
    return _common(
        analysis="permissions", mode=mode, title="Revisão de permissões de agentes", summary=summary,
        findings=findings, counts=counts, verdict=verdict, questions=questions, rows=rows,
        metrics={
            "agents": len(rows), "grants": total_grants, "deniedGranted": len(baseline_denied),
            "lowTrust": sum(1 for row in rows if row["lowTrust"]), "managed": sum(1 for row in rows if row["managed"]),
            "baselineGranted": len(DEFAULT_GRANTS), "baselineDenied": len(DEFAULT_DENIALS),
        },
        limitations=limitations,
        extra_sections=["", "## Linha de base", ""] + [
            f"- **Concedido:** `{key}` — {reason}" for key, reason in DEFAULT_GRANTS
        ] + [f"- **Negado:** `{key}` — {reason}" for key, reason in DEFAULT_DENIALS],
    )
