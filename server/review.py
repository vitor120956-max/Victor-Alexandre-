"""Primitivas compartilhadas das revisões estáticas do JARVIS.

As skills de governo de agentes e de estúdio de design devolvem o mesmo
formato: achados em quatro partes, contagens por grupo, veredito deterministico
e limites declarados. Este módulo concentra essa montagem para que os dois
domínios não divirjam no contrato apresentado pela interface.
"""
from __future__ import annotations

from typing import Any

GROUPS = ("must", "should", "nice")
GROUP_LABELS = {"must": "Corrigir obrigatoriamente", "should": "Corrigir", "nice": "Opcional"}


def finding(
    group: str,
    kind: str,
    title: str,
    location: str,
    what: str,
    problem: str,
    fix: str,
    if_skipped: str,
) -> dict[str, Any]:
    return {
        "id": 0,
        "group": group,
        "kind": kind,
        "title": title,
        "location": location,
        "what": what,
        "problem": problem,
        "fix": fix,
        "ifSkipped": if_skipped,
    }


def join_ids(values: list[int]) -> str:
    if len(values) == 1:
        return str(values[0])
    return f"{', '.join(str(value) for value in values[:-1])} e {values[-1]}"


def verdict(findings: list[dict[str, Any]]) -> str:
    must = [item["id"] for item in findings if item["group"] == "must"]
    if must:
        return f"Corrija {join_ids(must)} antes de liberar o trabalho."
    should = [item["id"] for item in findings if item["group"] == "should"]
    if should:
        return f"Corrija {join_ids(should)} antes de liberar o trabalho."
    return "Nenhum bloqueio pelas regras estáticas."


def finalize(
    findings: list[dict[str, Any]], mode: str, questions: list[str]
) -> tuple[list[dict[str, Any]], dict[str, int], str, list[str]]:
    order = {group: index for index, group in enumerate(GROUPS)}
    findings.sort(key=lambda item: order[item["group"]])
    for index, item in enumerate(findings, start=1):
        item["id"] = index
    if mode == "lite":
        findings = [item for item in findings if item["group"] == "must"]
    counts = {
        "must": sum(1 for item in findings if item["group"] == "must"),
        "should": sum(1 for item in findings if item["group"] == "should"),
        "nice": sum(1 for item in findings if item["group"] == "nice"),
        "total": len(findings),
    }
    return findings, counts, verdict(findings), questions if mode == "ultra" else []


def findings_markdown(findings: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for group in GROUPS:
        group_findings = [item for item in findings if item["group"] == group]
        if not group_findings:
            continue
        lines += ["", f"## {GROUP_LABELS[group]}", ""]
        for item in group_findings:
            lines += [
                f"{item['id']}. **{item['title']}** (`{item['location']}`)",
                f"   - **O que é:** {item['what']}",
                f"   - **Problema:** {item['problem']}",
                f"   - **Correção:** {item['fix']}",
                f"   - **Se ignorar:** {item['ifSkipped']}",
                "",
            ]
    return lines


def common(
    *,
    analysis: str,
    mode: str,
    title: str,
    summary: list[str],
    findings: list[dict[str, Any]],
    counts: dict[str, int],
    verdict: str,
    questions: list[str],
    rows: list[dict[str, Any]],
    metrics: dict[str, Any],
    limitations: list[str],
    extra_sections: list[str] | None = None,
) -> dict[str, Any]:
    markdown = [f"# {title}", "", *summary, "", f"**Veredito:** {verdict}"]
    if questions:
        markdown += ["", "## Perguntas antes de liberar", ""]
        markdown += [f"- {question}" for question in questions]
    markdown += findings_markdown(findings)
    if extra_sections:
        markdown += extra_sections
    markdown += ["", "## Não verificado", ""]
    markdown += [f"- {limitation}" for limitation in limitations]
    return {
        "analysis": analysis,
        "mode": mode,
        "metrics": metrics,
        "rows": rows,
        "findings": findings,
        "counts": counts,
        "verdict": verdict,
        "questions": questions,
        "executed": False,
        "readOnly": True,
        "markdown": "\n".join(markdown),
        "limitations": limitations,
    }
