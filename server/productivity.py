"""Skills locais de produtividade inspiradas em fluxos públicos, sem código de terceiros."""
from __future__ import annotations

import hashlib
import re
import secrets
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

_WORD = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*|\d+(?:[.,]\d+)?", re.UNICODE)
_FILLERS = ("ahn", "hum", "né", "tipo assim", "quer dizer", "sabe", "entende")
_HEDGES = ("talvez", "acho que", "possivelmente", "quem sabe", "não sei se")


def _fold(value: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFD", value.lower()) if not unicodedata.combining(char))


def _count_phrase(text: str, phrase: str) -> int:
    return len(re.findall(rf"(?<![\wÀ-ÿ]){re.escape(phrase)}(?![\wÀ-ÿ])", text, re.IGNORECASE))


def analyze_meeting(transcript: str, focus_speaker: str = "") -> dict[str, Any]:
    raw_turns = [line.strip() for line in transcript.splitlines() if line.strip()]
    if len(raw_turns) <= 1 and ";" in transcript:
        raw_turns = [line.strip() for line in transcript.split(";") if line.strip()]
    speakers: dict[str, dict[str, Any]] = defaultdict(lambda: {"turns": 0, "words": 0, "questions": 0, "fillerWords": 0, "hedges": 0})
    action_items: list[str] = []
    labeled = False
    for raw_turn in raw_turns:
        match = re.match(r"^(?:\[[^\]]+\]\s*)?([\wÀ-ÿ .'-]{1,60}):\s*(.+)$", raw_turn)
        speaker = match.group(1).strip() if match else "Não identificado"
        content = match.group(2).strip() if match else raw_turn
        labeled = labeled or bool(match)
        data = speakers[speaker]
        data["turns"] += 1
        data["words"] += len(_WORD.findall(content))
        data["questions"] += content.count("?")
        data["fillerWords"] += sum(_count_phrase(content, phrase) for phrase in _FILLERS)
        data["hedges"] += sum(_count_phrase(content, phrase) for phrase in _HEDGES)
        if re.search(r"\b(?:vou|preciso|precisa|ficou de|ação|prazo|tarefa|responsável|responsavel)\b", content, re.IGNORECASE) and len(action_items) < 10:
            action_items.append(content[:300])
    total_words = sum(data["words"] for data in speakers.values())
    if not total_words:
        raise ValueError("A transcrição não contém palavras para analisar.")
    speaker_results = []
    for name, data in sorted(speakers.items(), key=lambda item: (-item[1]["words"], item[0])):
        speaker_results.append({
            "name": name,
            **data,
            "speakingShare": round(data["words"] * 100 / total_words, 1),
            "fillerPer100Words": round(data["fillerWords"] * 100 / data["words"], 1) if data["words"] else 0,
        })
    focus = focus_speaker.strip()
    focus_found = next((item for item in speaker_results if _fold(item["name"]) == _fold(focus)), None) if focus else None
    if focus and not focus_found:
        raise ValueError(f"O participante '{focus}' não aparece como rótulo de fala na transcrição.")
    return {
        "speakers": speaker_results,
        "speakerCount": len(speaker_results),
        "totalWords": total_words,
        "totalTurns": sum(data["turns"] for data in speakers.values()),
        "questions": sum(data["questions"] for data in speakers.values()),
        "actionItems": action_items,
        "focusSpeaker": focus_found,
        "labelsDetected": labeled,
        "notice": "Métricas determinísticas do texto, não diagnóstico de intenção, personalidade ou desempenho. Revise o contexto da reunião.",
    }


_CATEGORIES = {
    "feat": "Novidades",
    "fix": "Correções",
    "perf": "Desempenho",
    "security": "Segurança",
    "docs": "Documentação",
}
_IGNORED = {"test", "tests", "refactor", "chore", "style", "build", "ci"}


def generate_changelog(commits: str, version: str) -> dict[str, Any]:
    lines = [line.strip() for line in commits.splitlines() if line.strip()]
    if len(lines) <= 1 and ";" in commits:
        lines = [line.strip() for line in commits.split(";") if line.strip()]
    groups: dict[str, list[str]] = defaultdict(list)
    skipped = 0
    for line in lines[:500]:
        cleaned = re.sub(r"^[-*•]\s*", "", line)
        cleaned = re.sub(r"^[0-9a-f]{7,40}\s+", "", cleaned, flags=re.IGNORECASE)
        match = re.match(r"^([a-z]+)(?:\([^)]*\))?(!)?:\s*(.+)$", cleaned, re.IGNORECASE)
        breaking = False
        if match:
            kind = match.group(1).lower()
            breaking = bool(match.group(2)) or "BREAKING CHANGE" in cleaned.upper()
            cleaned = match.group(3).strip()
            if kind in _IGNORED:
                skipped += 1
                continue
            category = "Mudanças importantes" if breaking else _CATEGORIES.get(kind, "Outras mudanças")
        else:
            folded = _fold(cleaned)
            category = "Correções" if any(word in folded for word in ("corrige", "correcao", "bug", "erro")) else "Novidades" if any(word in folded for word in ("adiciona", "novo", "nova")) else "Outras mudanças"
        if cleaned and cleaned not in groups[category]:
            groups[category].append(cleaned[:300])
    if not groups:
        raise ValueError("Nenhuma mudança publicável foi encontrada nas linhas informadas.")
    order = ["Mudanças importantes", "Novidades", "Correções", "Desempenho", "Segurança", "Documentação", "Outras mudanças"]
    sections = []
    entries = []
    for category in order:
        if category not in groups:
            continue
        sections.append(f"## {category}\n" + "\n".join(f"- {text}" for text in groups[category]))
        entries.extend({"category": category, "text": text} for text in groups[category])
    markdown = f"# {version}\n\n" + "\n\n".join(sections) + "\n"
    return {
        "version": version,
        "markdown": markdown,
        "entries": entries,
        "included": len(entries),
        "skippedInternal": skipped,
        "notice": "Organização determinística das mensagens fornecidas, sem criar mudanças. Revise antes de publicar.",
    }


def _entries(value: str) -> list[str]:
    raw = value.splitlines() if len(value.splitlines()) > 1 else re.split(r"[,;]", value)
    result: list[str] = []
    seen: set[str] = set()
    for item in raw:
        cleaned = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", item).strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned[:200])
    return result


def pick_winners(entries: str, count: int, exclusions: str = "") -> dict[str, Any]:
    participants = _entries(entries)
    excluded = {item.casefold() for item in _entries(exclusions)}
    eligible = [item for item in participants if item.casefold() not in excluded]
    if len(eligible) < 2:
        raise ValueError("Informe ao menos dois participantes elegíveis e distintos.")
    if count > len(eligible):
        raise ValueError(f"Não há participantes suficientes: {len(eligible)} elegíveis para {count} vagas.")
    winners = secrets.SystemRandom().sample(eligible, count)
    timestamp = datetime.now(timezone.utc).isoformat()
    audit = hashlib.sha256((timestamp + "\n" + "\n".join(winners)).encode("utf-8")).hexdigest()[:20]
    return {
        "winners": winners,
        "count": count,
        "eligible": len(eligible),
        "excluded": len(participants) - len(eligible),
        "method": "secrets.SystemRandom.sample, sem reposição",
        "timestamp": timestamp,
        "auditId": audit,
        "notice": "Seleção aleatória local, sem pesos e sem reposição. Guarde a lista de entrada e o horário para auditoria.",
    }
