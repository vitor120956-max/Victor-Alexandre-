"""Planos persistentes em três arquivos Markdown, confinados e versionados por hash.

Adaptação própria do padrão de OthmanAdi/planning-with-files (MIT). Não lê
histórico de agentes, não executa hooks nem comandos presentes nos arquivos.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import tempfile
import threading
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .workspace import download_url, regular_file, safe_path

PLAN_FILES = ("task_plan.md", "findings.md", "progress.md")
MAX_PLAN_BYTES = 100_000
MAX_PLANS = 100
_LOCK = threading.RLock()
_STATUSES = {"pending", "in_progress", "complete"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lines(value: str, *, allow_empty: bool = True) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()] if value.strip() or allow_empty else []


def _escape_headings(value: str) -> str:
    """Mantém texto do usuário inerte para o parser estrutural do plano."""
    return re.sub(r"(?m)^(#{1,6})(?= )", r"\\\1", value.replace("\x00", ""))


def _slug(value: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")[:48].strip("-")


def _validate_plan_id(plan_id: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,79}", plan_id) or plan_id.endswith("-"):
        raise ValueError("Use um ID com 2–80 caracteres: letras minúsculas, números e hífens internos.")
    return plan_id


def _directory(root: Path, plan_id: str) -> Path:
    return safe_path(root, f"planning/{_validate_plan_id(plan_id)}", allow_root=False)


def _bundle_hash(contents: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for name in PLAN_FILES:
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update(contents[name].encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _atomic_text(path: Path, content: str, *, allow_existing: bool) -> None:
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_PLAN_BYTES:
        raise ValueError(f"{path.name} excede o limite de {MAX_PLAN_BYTES // 1_000} KB por arquivo de planejamento.")
    if path.exists() and not allow_existing:
        raise ValueError("O plano já existe. Escolha outro ID em vez de sobrescrevê-lo.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as temporary:
            temporary_name = temporary.name
            temporary.write(encoded)
            temporary.flush()
            os.fsync(temporary.fileno())
        if path.exists() and not allow_existing:
            raise ValueError("O destino apareceu durante a gravação. Revise antes de continuar.")
        Path(temporary_name).replace(path)
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)


def _write_new_bundle(root: Path, plan_id: str, contents: dict[str, str]) -> None:
    directory = _directory(root, plan_id)
    if directory.exists():
        raise ValueError("O plano já existe. Escolha outro ID ou retome o plano existente.")
    created: list[Path] = []
    try:
        for name in PLAN_FILES:
            path = safe_path(root, f"planning/{plan_id}/{name}")
            _atomic_text(path, contents[name], allow_existing=False)
            created.append(path)
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        try:
            directory.rmdir()
            directory.parent.rmdir()
        except OSError:
            pass
        raise


def _load(root: Path, plan_id: str) -> tuple[dict[str, str], str]:
    directory = _directory(root, plan_id)
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("Plano não encontrado. O ID explícito não foi substituído por outro plano.")
    contents: dict[str, str] = {}
    for name in PLAN_FILES:
        path = regular_file(root, f"planning/{plan_id}/{name}", {".md"}, MAX_PLAN_BYTES)
        try:
            contents[name] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"{name} não é um Markdown UTF-8 válido.") from exc
    return contents, _bundle_hash(contents)


def _section(contents: str, heading: str) -> str:
    match = re.search(rf"(?ms)^## {re.escape(heading)}\s*\n(.*?)(?=^## |\Z)", contents)
    if not match:
        raise ValueError(f"task_plan.md não possui a seção obrigatória '{heading}'.")
    return match.group(1).strip()


def _replace_section(contents: str, heading: str, value: str) -> str:
    pattern = re.compile(rf"(?ms)^## {re.escape(heading)}\s*\n.*?(?=^## |\Z)")
    replacement = f"## {heading}\n\n{value.strip()}\n\n"
    updated, count = pattern.subn(lambda _match: replacement, contents, count=1)
    if count != 1:
        raise ValueError(f"Não foi possível atualizar a seção '{heading}'.")
    return updated


@dataclass(frozen=True)
class Phase:
    number: int
    title: str
    status: str
    criteria: list[tuple[str, bool]]
    start: int
    end: int


@dataclass(frozen=True)
class Plan:
    plan_id: str
    title: str
    goal: str
    next_step: str
    current_phase: int
    phases: list[Phase]
    contents: dict[str, str]
    sha256: str


def _parse(plan_id: str, contents: dict[str, str], sha256: str) -> Plan:
    raw = contents["task_plan.md"]
    title_match = re.search(r"(?m)^# Task Plan:\s*(.+)$", raw)
    if not title_match:
        raise ValueError("task_plan.md não possui o título esperado '# Task Plan: ...'.")
    phases_section = re.search(r"(?ms)^## Phases[ \t]*\n(.*?)(?=^## |\Z)", raw)
    if not phases_section:
        raise ValueError("task_plan.md não possui a seção obrigatória 'Phases'.")
    phase_matches = list(re.compile(r"(?m)^### Phase (\d+):[ \t]*(.+)$").finditer(raw, phases_section.start(1), phases_section.end(1)))
    if not 1 <= len(phase_matches) <= 50:
        raise ValueError("O plano precisa conter entre 1 e 50 fases reconhecíveis.")
    phases: list[Phase] = []
    for index, match in enumerate(phase_matches):
        end = phase_matches[index + 1].start() if index + 1 < len(phase_matches) else phases_section.end(1)
        block = raw[match.start():end]
        status_match = re.search(r"(?m)^- \*\*Status:\*\*\s*(\w+)\s*$", block)
        if not status_match or status_match.group(1) not in _STATUSES:
            raise ValueError(f"A fase {match.group(1)} possui status ausente ou inválido.")
        criteria = [(item.group(2).strip(), item.group(1).lower() == "x") for item in re.finditer(r"(?m)^- \[([ xX])\]\s+(.+)$", block)]
        if not criteria:
            raise ValueError(f"A fase {match.group(1)} não possui critérios verificáveis.")
        phases.append(Phase(int(match.group(1)), match.group(2).strip(), status_match.group(1), criteria, match.start(), end))
    numbers = [phase.number for phase in phases]
    if len(set(numbers)) != len(numbers):
        raise ValueError("O plano contém números de fase duplicados.")
    current_text = _section(raw, "Current Phase")
    current_match = re.search(r"(\d+)", current_text)
    if not current_match or int(current_match.group(1)) not in numbers:
        raise ValueError("Current Phase não aponta para uma fase existente.")
    return Plan(
        plan_id=plan_id,
        title=title_match.group(1).strip(),
        goal=_section(raw, "Goal"),
        next_step=_section(raw, "Next Step"),
        current_phase=int(current_match.group(1)),
        phases=phases,
        contents=contents,
        sha256=sha256,
    )


def _gate(plan: Plan) -> dict[str, Any]:
    pending = []
    for phase in plan.phases:
        unchecked = [criterion for criterion, checked in phase.criteria if not checked]
        if phase.status != "complete" or unchecked:
            pending.append({"phase": phase.number, "title": phase.title, "status": phase.status, "uncheckedCriteria": unchecked})
    return {
        "complete": not pending,
        "phaseCount": len(plan.phases),
        "completePhases": sum(phase.status == "complete" and all(checked for _criterion, checked in phase.criteria) for phase in plan.phases),
        "pending": pending,
        "rule": "Todas as fases devem ter status complete e todos os critérios marcados.",
        "commandsExecuted": False,
    }


def _downloads(plan_id: str) -> dict[str, str]:
    return {name: download_url(f"planning/{plan_id}/{name}") for name in PLAN_FILES}


def _summary(plan: Plan) -> dict[str, Any]:
    return {
        "planId": plan.plan_id,
        "title": plan.title,
        "goal": plan.goal,
        "nextStep": plan.next_step,
        "currentPhase": plan.current_phase,
        "phases": [{"number": phase.number, "title": phase.title, "status": phase.status, "criteria": [{"text": text, "checked": checked} for text, checked in phase.criteria]} for phase in plan.phases],
        "gate": _gate(plan),
        "sha256": plan.sha256,
        "downloadUrls": _downloads(plan.plan_id),
    }


def _initial_contents(title: str, goal: str, phases: list[tuple[str, str]], requirements: list[str], timestamp: str) -> dict[str, str]:
    first_title = phases[0][0]
    phase_blocks = []
    for index, (phase_title, criterion) in enumerate(phases, start=1):
        phase_blocks.append("\n".join([
            f"### Phase {index}: {phase_title}",
            "",
            f"- [ ] {criterion}",
            f"- **Status:** {'in_progress' if index == 1 else 'pending'}",
        ]))
    requirement_markdown = "\n".join(f"- {item}" for item in requirements) or "- Nenhum requisito adicional registrado na criação."
    task_plan = f"""# Task Plan: {title}

## Goal

{goal}

## Next Step

Executar fase 1: {first_title}

## Current Phase

Phase 1

## Phases

{(chr(10) * 2).join(phase_blocks)}

## Requirements

{requirement_markdown}

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Plano persistente em três arquivos | Recuperação explícita pelo ID, sem histórico oculto do agente |

## Errors Encountered

| Error | Attempt | Resolution |
|-------|---------|------------|
"""
    findings = f"""# Findings & Decisions

Plano: {title}

## Requirements

{requirement_markdown}

## Research Findings

- Nenhuma descoberta adicional registrada.

## Technical Decisions

| Decision | Rationale |
|----------|-----------|
| Seleção explícita por ID | Evita retomar um plano ambíguo |

## Issues Encountered

| Issue | Resolution |
|-------|------------|

## Resources

- Conteúdo fornecido pelo usuário; nenhuma pesquisa externa automática.

## Visual/Browser Findings

- Nenhum registro.
"""
    progress = f"""# Progress Log

Plano: {title}

## Session: {timestamp}

### Phase 1: {first_title}

- **Status:** in_progress
- **Started:** {timestamp}
- Actions taken:
  - Plano criado após simulação e confirmação.
- Files created/modified:
  - `task_plan.md`, `findings.md`, `progress.md`

## Test Results

| Test | Input | Expected | Actual | Status |
|------|-------|----------|--------|--------|

## Error Log

| Timestamp | Error | Attempt | Resolution |
|-----------|-------|---------|------------|

## Reboot Check

| Question | Answer |
|----------|--------|
| Where am I? | Phase 1 |
| Where am I going? | {len(phases)} fases registradas |
| What's the goal? | {goal} |
| What have I learned? | See findings.md |
| What have I done? | Plano inicializado |
| What am I about to do? | Executar fase 1: {first_title} |
"""
    return {"task_plan.md": task_plan, "findings.md": findings, "progress.md": progress}


def create_plan(root: Path, requested_id: str, title: str, goal: str, phase_input: str, requirements: str, dry_run: bool) -> dict[str, Any]:
    title = " ".join(title.replace("\x00", "").split())
    goal = _escape_headings(goal.strip())
    if not title or not goal:
        raise ValueError("Informe título e objetivo válidos.")
    raw_phases = _lines(phase_input)
    if not 2 <= len(raw_phases) <= 7:
        raise ValueError("Use de 2 a 7 fases, uma por linha, no formato 'Título | critério verificável'.")
    phases: list[tuple[str, str]] = []
    for line in raw_phases:
        parts = [part.strip() for part in line.split("|", 1)]
        if len(parts) != 2 or not all(parts):
            raise ValueError("Cada fase precisa de título e critério separados por '|'.")
        phases.append((" ".join(parts[0].split()), " ".join(parts[1].split())))
    plan_id = _validate_plan_id(requested_id.strip() or _slug(title))
    if not _slug(title) and not requested_id.strip():
        raise ValueError("Não foi possível derivar um ID do título; informe um ID manualmente.")
    contents = _initial_contents(title, goal, phases, _lines(requirements), _now())
    predicted_hash = _bundle_hash(contents)
    files = [f"planning/{plan_id}/{name}" for name in PLAN_FILES]
    with _LOCK:
        if dry_run:
            if _directory(root, plan_id).exists():
                raise ValueError("O plano já existe. Escolha outro ID ou retome o plano existente.")
            return {"dryRun": True, "planId": plan_id, "wouldWrite": files, "preview": contents["task_plan.md"], "markdown": contents["task_plan.md"], "sha256": predicted_hash}
        _write_new_bundle(root, plan_id, contents)
        loaded, sha256 = _load(root, plan_id)
        plan = _parse(plan_id, loaded, sha256)
        return {"dryRun": False, "created": files, **_summary(plan)}


def list_plans(root: Path) -> dict[str, Any]:
    planning_root = safe_path(root, "planning", allow_root=True)
    if not planning_root.exists():
        return {"plans": [], "count": 0, "limit": MAX_PLANS, "selection": "explicit-id"}
    plans: list[dict[str, Any]] = []
    with _LOCK:
        directories = [item for item in planning_root.iterdir() if item.is_dir() and not item.is_symlink() and not item.name.startswith(".")]
        for directory in sorted(directories, key=lambda item: item.stat().st_mtime, reverse=True)[:MAX_PLANS]:
            try:
                contents, sha256 = _load(root, directory.name)
                plan = _parse(directory.name, contents, sha256)
                plans.append({**_summary(plan), "updatedAt": datetime.fromtimestamp(max((directory / name).stat().st_mtime for name in PLAN_FILES), timezone.utc).isoformat(), "invalid": False})
            except ValueError as exc:
                plans.append({"planId": directory.name, "title": directory.name, "invalid": True, "error": str(exc), "gate": {"complete": False}})
    return {"plans": plans, "count": len(plans), "limit": MAX_PLANS, "selection": "explicit-id"}


def resume_plan(root: Path, plan_id: str) -> dict[str, Any]:
    with _LOCK:
        contents, sha256 = _load(root, plan_id)
        plan = _parse(plan_id, contents, sha256)
        gate = _gate(plan)
        recovery = {
            "Onde estou?": f"Fase {plan.current_phase}",
            "Para onde vou?": f"{gate['phaseCount'] - gate['completePhases']} fases ainda não concluídas",
            "Qual é o objetivo?": plan.goal,
            "O que aprendi?": "Consulte findings.md",
            "O que já fiz?": "Consulte progress.md",
            "Qual é o próximo passo?": plan.next_step,
        }
        markdown = "\n".join([f"# {plan.title}", "", f"Próximo passo: {plan.next_step}", f"Fase atual: {plan.current_phase}", f"Gate completo: {'sim' if gate['complete'] else 'não'}"])
        return {**_summary(plan), "contents": contents, "recovery": recovery, "markdown": markdown, "historyRead": False}


def completion_gate(root: Path, plan_id: str) -> dict[str, Any]:
    with _LOCK:
        contents, sha256 = _load(root, plan_id)
        plan = _parse(plan_id, contents, sha256)
        gate = _gate(plan)
        markdown = "\n".join([
            f"# Gate: {plan.title}",
            "",
            f"**{'COMPLETE' if gate['complete'] else 'INCOMPLETE'}** — {gate['completePhases']}/{gate['phaseCount']} fases concluídas.",
            "",
            *(f"- Fase {item['phase']}: {item['title']} · {item['status']} · {len(item['uncheckedCriteria'])} critérios pendentes" for item in gate["pending"]),
            "",
            "Nenhum comando foi executado por esta verificação.",
        ])
        return {"planId": plan.plan_id, "title": plan.title, "sha256": sha256, "gate": gate, "markdown": markdown}


def _append_to_section(contents: str, heading: str, addition: str) -> str:
    match = re.search(rf"(?ms)^## {re.escape(heading)}\s*\n.*?(?=^## |\Z)", contents)
    if not match:
        raise ValueError(f"Arquivo não possui a seção '{heading}'.")
    block = match.group(0).rstrip() + "\n\n" + addition.strip() + "\n\n"
    return contents[:match.start()] + block + contents[match.start() + len(match.group(0)):]


def _render_phase(block: str, status: str) -> str:
    block = re.sub(r"(?m)^- \*\*Status:\*\*[ \t]*\w+[ \t]*$", f"- **Status:** {status}", block, count=1)
    if status == "complete":
        return re.sub(r"(?m)^- \[ \]", "- [x]", block)
    return re.sub(r"(?m)^- \[[xX]\]", "- [ ]", block)


def update_plan(root: Path, plan_id: str, expected_sha256: str, phase_number: int, status: str, next_step: str, evidence: str, note_type: str, note: str, dry_run: bool) -> dict[str, Any]:
    with _LOCK:
        contents, current_hash = _load(root, plan_id)
        if not hmac.compare_digest(current_hash, expected_sha256.lower()):
            raise ValueError("O plano mudou desde a leitura. Retome o estado atual antes de atualizar.")
        plan = _parse(plan_id, contents, current_hash)
        note = note.strip()
        evidence = evidence.strip()
        next_step = _escape_headings(next_step.strip())
        if not phase_number and not next_step and not note:
            raise ValueError("Informe uma mudança de fase, próximo passo ou anotação.")
        if bool(phase_number) != bool(status):
            raise ValueError("Informe fase e status juntos.")
        if note and not note_type or note_type and not note:
            raise ValueError("Informe o tipo e o conteúdo da anotação.")
        if phase_number and phase_number not in {phase.number for phase in plan.phases}:
            raise ValueError("A fase informada não existe.")
        if status == "complete" and not evidence:
            raise ValueError("Concluir uma fase exige evidência verificável.")

        updated = dict(contents)
        changes: list[str] = []
        statuses = {phase.number: phase.status for phase in plan.phases}
        new_current = plan.current_phase
        new_next_step = next_step
        if phase_number:
            if status == "in_progress" and any(phase.status == "in_progress" and phase.number != phase_number for phase in plan.phases):
                raise ValueError("Já existe outra fase em andamento. Conclua ou pause essa fase antes de continuar.")
            statuses[phase_number] = status
            new_current = phase_number
            changes.append(f"Fase {phase_number}: {status}")
            if status == "complete":
                following = next((phase for phase in plan.phases if statuses[phase.number] != "complete"), None)
                if following:
                    statuses[following.number] = "in_progress"
                    new_current = following.number
                    changes.append(f"Fase {following.number}: in_progress automático")
                    if not new_next_step:
                        new_next_step = f"Executar fase {following.number}: {following.title}"
                elif not new_next_step:
                    new_next_step = "Revisar o gate de conclusão e entregar o resultado."
            elif not new_next_step:
                new_next_step = f"Executar fase {phase_number}: {next(phase.title for phase in plan.phases if phase.number == phase_number)}"
        raw = updated["task_plan.md"]
        for phase in sorted(plan.phases, key=lambda item: item.start, reverse=True):
            if statuses[phase.number] != phase.status:
                block = _render_phase(raw[phase.start:phase.end], statuses[phase.number])
                raw = raw[:phase.start] + block + raw[phase.end:]
        raw = _replace_section(raw, "Current Phase", f"Phase {new_current}")
        if new_next_step:
            if new_next_step != plan.next_step:
                changes.append("Próximo passo atualizado")
            raw = _replace_section(raw, "Next Step", new_next_step)
        updated["task_plan.md"] = raw
        timestamp = _now()
        if evidence:
            updated["progress.md"] += f"\n### Evidence · {timestamp}\n\n- Phase: {phase_number}\n- Status: {status}\n- Evidence: {evidence}\n"
            changes.append("Evidência registrada em progress.md")
        if note:
            clean_note = _escape_headings(note.strip())
            if note_type == "finding":
                updated["findings.md"] = _append_to_section(updated["findings.md"], "Research Findings", f"- {timestamp} — {clean_note}")
                changes.append("Descoberta anexada a findings.md")
            elif note_type == "progress":
                updated["progress.md"] += f"\n### Progress · {timestamp}\n\n{clean_note}\n"
                changes.append("Progresso anexado a progress.md")
            elif note_type == "test":
                updated["progress.md"] += f"\n### Validation · {timestamp}\n\n- Declared result: {clean_note}\n- Executed by planning skill: no\n"
                changes.append("Resultado declarado anexado a progress.md")
            elif note_type == "error":
                attempts = len(re.findall(r"(?m)^\|.*\|\s*\d+\s*\|", updated["progress.md"])) + 1
                updated["task_plan.md"] = _append_to_section(updated["task_plan.md"], "Errors Encountered", f"| {clean_note.replace('|', '/') } | {attempts} | Em investigação |")
                updated["progress.md"] += f"\n### Error · {timestamp}\n\n- Error: {clean_note}\n- Attempt: {attempts}\n- Resolution: Em investigação\n"
                changes.append("Erro registrado; revise a abordagem antes de repetir")
            else:
                raise ValueError("Tipo de anotação não suportado.")
        for name, content in updated.items():
            if len(content.encode("utf-8")) > MAX_PLAN_BYTES:
                raise ValueError(f"{name} excede o limite de {MAX_PLAN_BYTES // 1_000} KB.")
        new_hash = _bundle_hash(updated)
        predicted = _parse(plan_id, updated, new_hash)
        files = [f"planning/{plan_id}/{name}" for name in PLAN_FILES if updated[name] != contents[name]]
        if dry_run:
            return {"dryRun": True, "planId": plan_id, "wouldWrite": files, "changes": changes, "previousSha256": current_hash, "sha256": new_hash, "gate": _gate(predicted), "preview": updated["task_plan.md"], "markdown": "\n".join(changes)}
        backups = dict(contents)
        written: list[str] = []
        try:
            for name in PLAN_FILES:
                if updated[name] != contents[name]:
                    _atomic_text(safe_path(root, f"planning/{plan_id}/{name}"), updated[name], allow_existing=True)
                    written.append(name)
        except Exception:
            for name in written:
                _atomic_text(safe_path(root, f"planning/{plan_id}/{name}"), backups[name], allow_existing=True)
            raise
        loaded, sha256 = _load(root, plan_id)
        if not hmac.compare_digest(sha256, new_hash):
            raise ValueError("A verificação posterior à gravação divergiu. Retome o plano e revise os arquivos.")
        result = _parse(plan_id, loaded, sha256)
        return {"dryRun": False, "written": files, "changes": changes, **_summary(result), "markdown": "\n".join(changes)}
