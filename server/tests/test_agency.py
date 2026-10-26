"""Testes da governança de agentes inspirada em paperclipai/paperclip (MIT).

A análise é estática: nenhum agente, heartbeat, adapter ou plugin é executado.
As fixtures declaram equipes, quadros, orçamentos e subárvores em texto.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server.agency import (
    AgencyError,
    audit_board,
    audit_budget,
    audit_permissions,
    audit_roster,
    default_permissions,
    verify_watchdog,
)
from server.app import create_app
from server.skill_registry import build_registry

ROSTER = """# nome | papel | responde a | orçamento | permissões | estado
Ana | Tech lead | board | 900 | deploy, shell | ativo
Bruno | Backend | Ana | 600 | shell | ativo
Carla | Pesquisa | Ana | 350 | network | pausado
Dora | QA | Bruno | 120 | tasks:assign | ativo
"""

BOARD = """# id | título | dono | estado | objetivo | bloqueadores | evidência | atualizado
ENG-1 | Login | Ana | in_progress | lançar beta | — | — | 2026-10-21
ENG-2 | Testes de login | Bruno | in_review | lançar beta | — | @ana revisou a suíte | 2026-10-21
ENG-3 | Documentação | Carla | done | lançar beta | — | PR #12 e revisão de Ana | 2026-10-20
ENG-4 | Onboarding | Dora | blocked | lançar beta | ENG-2 | — | 2026-10-22
"""

BUDGET = """# agente | limite | gasto | alerta% | parada automática
Ana | 900 | 740 | 80 | sim
Bruno | 600 | 610 | 80 | sim
Carla | 350 | 40 | 80 | sim
Dora | 120 | 96 | 80 | sim
"""

SUBTREE = """# id | estado | dono | evidência | bloqueador | interação | atualizado
ENG-1 | done | Ana | PR #3 e teste verde | — | — | 2026-10-20
ENG-2 | in_review | Bruno | — | — | — | 2026-10-19
ENG-3 | blocked | Carla | — | @ana marketing | — | 2026-10-18
ENG-4 | done | Dora | PR #9 | ENG-5 | — | 2026-10-18
ENG-5 | done | Dora | teste verde | — | — | 2026-10-20
"""

PERMISSIONS = """# agente | concedidas | negadas | flags
Ana | tasks:assign, tools:use, agents:configure | users:invite, chave:estranha | cota:3, criados:4
Bruno | agents:create, tasks:assign | |
Carla | * | | baixa_confianca
Dora | canCreateAgents, tools:use | | adapter:claude
"""


def kinds(result: dict) -> list[str]:
    return [finding["kind"] for finding in result["findings"]]


@pytest.fixture()
def client(tmp_path):
    registry = build_registry(tmp_path / "files")
    app = create_app(registry=registry)
    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------- equipe


def test_roster_accepts_a_healthy_team() -> None:
    result = audit_roster(roster=ROSTER)

    assert result["counts"]["must"] == 0
    assert result["metrics"]["agents"] == 4
    assert result["metrics"]["active"] == 3
    assert result["metrics"]["roots"] == 1
    assert result["metrics"]["monthlyBudget"] == 1970.0
    assert result["executed"] is False
    assert result["readOnly"] is True


def test_roster_requires_manager_role_and_identity() -> None:
    roster = """Ana | | board | 100 | tools:use | ativo
 | QA | Ana | 50 | tools:use | ativo
Dora | QA | Bruno | 50 | tools:use | ativo
"""
    result = audit_roster(roster=roster)
    found = kinds(result)
    assert "missing-role" in found
    assert "missing-name" in found
    assert "unknown-manager" in found
    assert result["counts"]["must"] >= 3


def test_roster_detects_report_cycles_and_inactive_managers() -> None:
    roster = """Ana | Lead | Bruno | 100 | tools:use | ativo
Bruno | Dev | Ana | 100 | tools:use | ativo
Carla | QA | Eva | 100 | tools:use | ativo
Eva | Ops | board | 100 | tools:use | encerrado
"""
    result = audit_roster(roster=roster)
    cycle = next(finding for finding in result["findings"] if finding["kind"] == "report-cycle")
    assert cycle["location"] == "Ana → Bruno → Ana"
    assert "inactive-manager" in kinds(result)
    assert "no-human-root" not in kinds(result)


def test_roster_requires_a_human_root_and_unique_names() -> None:
    roster = """Ana | Lead | Bruno | 100 | tools:use | ativo
Bruno | Dev | Ana | 100 | tools:use | ativo
Ana | QA | board | 10 | tools:use | ativo
"""
    result = audit_roster(roster=roster)
    found = kinds(result)
    assert "duplicate" in found
    assert "no-human-root" in found


def test_roster_flags_wildcard_and_sensitive_permissions() -> None:
    roster = """Ana | Lead | board | 100 | shell, deploy | ativo
Bruno | Dev | Ana | 100 | * | ativo
Carla | QA | Ana | 100 | tools:use | encerrado
"""
    result = audit_roster(roster=roster)
    assert "wildcard-permission" in kinds(result)
    assert next(finding for finding in result["findings"] if finding["kind"] == "wildcard-permission")["location"] == "linha 2"
    sensitive = [finding["location"] for finding in result["findings"] if finding["kind"] == "critical-permission"]
    assert sensitive == ["linha 1"]


def test_roster_budget_rules_and_lite_mode() -> None:
    roster = """Ana | Lead | board | 900 | tools:use | ativo
Bruno | Dev | Ana | 0 | tools:use | ativo
Carla | QA | Ana | 200 | tools:use | encerrado
"""
    full = audit_roster(roster=roster)
    found = kinds(full)
    assert "zero-budget" in found
    assert "stale-budget" in found

    lite = audit_roster(roster=roster, mode="lite")
    assert lite["findings"] == []


def test_roster_rejects_invalid_input() -> None:
    with pytest.raises(AgencyError, match="agente"):
        audit_roster(roster="   ")
    with pytest.raises(AgencyError, match="Nível"):
        audit_roster(roster=ROSTER, mode="turbo")
    with pytest.raises(AgencyError, match="campos"):
        audit_roster(roster="Ana | Lead | board | 100 | tools:use | ativo | extra")


# ---------------------------------------------------------------- quadro


def test_board_accepts_a_healthy_board() -> None:
    result = audit_board(tasks=BOARD, reference_date="2026-10-23")
    assert result["counts"]["must"] == 0
    assert result["metrics"]["tasks"] == 4
    assert result["metrics"]["wip"] == 2
    assert result["metrics"]["blocked"] == 1
    assert result["metrics"]["stale"] == 0


def test_board_requires_owner_evidence_and_blocker_cause() -> None:
    board = """ENG-1 | Login | | in_progress | beta | — | — | 2026-10-22
ENG-2 | Deploy | Ana | done | beta | — | — | 2026-10-22
ENG-3 | Docs | Ana | blocked | beta | — | — | 2026-10-22
"""
    result = audit_board(tasks=board, reference_date="2026-10-23")
    found = kinds(result)
    assert "missing-owner" in found
    assert "done-without-evidence" in found
    assert "blocked-without-blocker" in found
    assert result["counts"]["must"] == 3


def test_board_detects_dependency_cycles_and_dangling_blockers() -> None:
    board = """A-1 | Primeira | Ana | blocked | beta | A-2 | — | 2026-10-22
A-2 | Segunda | Ana | blocked | beta | A-1 | — | 2026-10-22
A-3 | Terceira | Ana | blocked | beta | A-9 | — | 2026-10-22
A-4 | Quarta | Ana | blocked | beta | A-4 | — | 2026-10-22
"""
    result = audit_board(tasks=board, reference_date="2026-10-23")
    found = kinds(result)
    cycle = next(finding for finding in result["findings"] if finding["kind"] == "dependency-cycle")
    assert cycle["location"] == "A-1 → A-2 → A-1"
    assert "dangling-blocker" in found
    assert "self-block" in found


def test_board_rejects_conclusion_against_open_blocker_and_stale_review() -> None:
    board = """ENG-1 | Base | Bruno | blocked | beta | — | falta dono | 2026-10-22
ENG-2 | Entrega | Ana | done | beta | ENG-1 | PR #2 | 2026-10-22
ENG-3 | Revisão | Ana | in_review | beta | — | protótipo pronto | 2026-10-19
"""
    result = audit_board(tasks=board, reference_date="2026-10-23", stale_days=2)
    found = kinds(result)
    assert "blocked-without-blocker" in found
    assert "done-with-open-blocker" in found
    assert "review-without-reviewer" in found
    assert "stale" in found


def test_board_flags_inactivity_wip_and_future_dates() -> None:
    board = """ENG-1 | A | Ana | in_progress | beta | — | — | 2026-10-10
ENG-2 | B | Ana | in_progress | beta | — | — | 2026-10-12
ENG-3 | C | Ana | in_progress | beta | — | — | 2026-10-25
"""
    result = audit_board(tasks=board, reference_date="2026-10-23", wip_limit=2, stale_days=3)
    found = kinds(result)
    assert "wip-limit" in found
    assert "stale" in found
    assert "future-date" in found
    assert result["metrics"]["stale"] == 2


def test_board_validates_ids_status_and_limits() -> None:
    board = """ENG-1 | A | Ana | in_progress | beta | — | — | 2026-10-22
ENG-1 | B | Ana | doing | beta | — | — | 2026-10-22
ENG-2 | C | Ana | moonlight | beta | — | — | 2026-10-22
"""
    result = audit_board(tasks=board, reference_date="2026-10-23")
    found = kinds(result)
    assert "duplicate" in found
    assert "invalid-status" in found
    with pytest.raises(AgencyError, match="trabalho em andamento"):
        audit_board(tasks=BOARD, wip_limit=0)
    with pytest.raises(AgencyError, match="Data de referência"):
        audit_board(tasks=BOARD, reference_date="23/10/2026")


# ---------------------------------------------------------------- orçamento


def test_budget_detects_overspend_and_missing_hard_stop() -> None:
    result = audit_budget(entries=BUDGET, company_budget="2000")

    assert result["counts"]["must"] == 1
    assert result["metrics"]["overBudget"] == 1
    assert result["metrics"]["totalLimit"] == 1970.0
    assert result["metrics"]["totalSpent"] == 1486.0
    assert result["metrics"]["utilization"] == 75.4
    assert "over-budget" in kinds(result)


def test_budget_projection_and_company_ceiling() -> None:
    entries = """Ana | 1000 | 700 | 80 | sim
Bruno | 500 | 100 | 80 | sim
"""
    result = audit_budget(entries=entries, company_budget="1200", period_day=20, days_in_month=30)

    assert result["metrics"]["projected"] == 1200.0
    assert result["metrics"]["companyBudget"] == 1200.0
    assert "projected-company" not in kinds(result)
    assert "limits-above-company" in kinds(result)
    assert "projected-over" in kinds(result)


def test_budget_requires_stop_at_the_ceiling_and_reports_alert() -> None:
    entries = """Ana | 100 | 100 | 50 | nao
Bruno | 100 | 90 | 80 | nao
"""
    result = audit_budget(entries=entries)
    found = kinds(result)
    assert "limit-without-stop" in found
    assert "alert-threshold" in found
    assert "no-hard-stop" in found


def test_budget_rejects_spending_without_limit() -> None:
    entries = """Ana | 0 | 20 | 80 | sim
"""
    result = audit_budget(entries=entries)
    assert "spend-without-limit" in kinds(result)
    assert "over-budget" not in kinds(result)


def test_budget_validates_money_and_period() -> None:
    invalid_money = audit_budget(entries="Ana | 1.234,56 | 0 | 80 | sim")
    assert "invalid-limit" in kinds(invalid_money)
    assert "separador de milhar" in invalid_money["findings"][0]["what"]

    invalid_alert = audit_budget(entries="Ana | 100 | 0 | 120 | sim")
    assert "invalid-alert" in kinds(invalid_alert)

    with pytest.raises(AgencyError, match="teto da empresa"):
        audit_budget(entries="Ana | 100 | 0 | 80 | sim", company_budget="-1")
    with pytest.raises(AgencyError, match="dia do período"):
        audit_budget(entries="Ana | 100 | 0 | 80 | sim", period_day=31, days_in_month=30)


# ---------------------------------------------------------------- watchdog


def test_watchdog_does_not_fire_while_a_path_is_live() -> None:
    live = """ENG-1 | done | Ana | PR #1 | — | — | 2026-10-20
ENG-2 | in_progress | Bruno | — | — | — | 2026-10-22
"""
    result = verify_watchdog(watched="ENG-1", tasks=live)

    assert result["fired"] is False
    assert result["suppressed"] is False
    assert result["fingerprint"] is None
    assert result["reviewTask"] == ""
    assert result["metrics"]["live"] == 1
    assert "Não dispara" in result["verdict"]


def test_watchdog_fires_for_a_stopped_subtree_with_unverified_claims() -> None:
    result = verify_watchdog(watched="ENG-1", tasks=SUBTREE)

    assert result["fired"] is True
    assert len(result["fingerprint"]) == 64
    assert result["reviewTask"].startswith("watchdog-eng-1-")
    assert result["reviewTask"].endswith(result["fingerprint"][:8])
    found = kinds(result)
    assert "review-without-evidence" in found
    assert "blocked-without-blocker" not in found
    assert result["metrics"]["unverified"] == 1
    assert result["executed"] is False


def test_watchdog_suppresses_the_same_fingerprint_only() -> None:
    first = verify_watchdog(watched="ENG-1", tasks=SUBTREE)
    repeated = verify_watchdog(watched="ENG-1", tasks=SUBTREE, last_fingerprint=first["fingerprint"])

    assert repeated["fingerprint"] == first["fingerprint"]
    assert repeated["suppressed"] is True
    assert repeated["fired"] is False
    assert "suprimida" in repeated["verdict"]

    changed = verify_watchdog(
        watched="ENG-1", tasks=SUBTREE.replace("ENG-2 | in_review | Bruno | —", "ENG-2 | in_review | Bruno | diff revisado"),
    )
    assert changed["fingerprint"] != first["fingerprint"]
    assert changed["fired"] is True


def test_watchdog_rejects_widening_instructions_but_accepts_negations() -> None:
    widened = verify_watchdog(
        watched="ENG-1", tasks=SUBTREE,
        instructions="Você pode aprovar o deploy, criar outro watchdog e acordar a si mesmo.",
    )
    assert kinds(widened).count("widening-instruction") >= 3
    assert widened["counts"]["must"] >= 1

    negated = verify_watchdog(
        watched="ENG-1", tasks=SUBTREE,
        instructions="Nunca aprove gastos e não crie outro watchdog.",
    )
    assert "widening-instruction" not in kinds(negated)

    narrowed = verify_watchdog(watched="ENG-1", tasks=SUBTREE, instructions="Cheque o CI verde antes de aceitar a conclusão.")
    assert "widening-instruction" not in kinds(narrowed)


def test_watchdog_honors_exclusions_and_reports_blocked_owner() -> None:
    excluded = verify_watchdog(watched="ENG-1", tasks=SUBTREE, exclude="ENG-2, ENG-5")
    assert "ENG-2" not in [claim["id"] for claim in excluded["claims"]]
    assert excluded["excluded"] == ["eng-2", "eng-5"]

    blocked = """ENG-1 | blocked | Ana | — | marketing sem dono | — | 2026-10-20
"""
    result = verify_watchdog(watched="ENG-1", tasks=blocked)
    assert "blocker-without-owner" in kinds(result)

    owned = """ENG-1 | blocked | Ana | — | @ana marketing | — | 2026-10-20
"""
    assert verify_watchdog(watched="ENG-1", tasks=owned)["claims"][0]["verified"] is True


def test_watchdog_requires_watched_task_and_valid_fingerprint() -> None:
    with pytest.raises(AgencyError, match="tarefa observada"):
        verify_watchdog(watched="  ", tasks=SUBTREE)
    with pytest.raises(AgencyError, match="64 caracteres"):
        verify_watchdog(watched="ENG-1", tasks=SUBTREE, last_fingerprint="abc")
    with pytest.raises(AgencyError, match="Nenhuma tarefa"):
        verify_watchdog(watched="ENG-1", tasks="ENG-1 | done | Ana | ok | — | — | 2026-10-20", exclude="ENG-1")


def test_watchdog_lite_keeps_only_blockers() -> None:
    result = verify_watchdog(watched="ENG-1", tasks=SUBTREE, mode="lite")
    assert result["findings"]
    assert all(finding["group"] == "must" for finding in result["findings"])
    assert result["questions"] == []


# ---------------------------------------------------------------- permissões


def test_permission_baseline_matches_the_documented_lists() -> None:
    baseline = default_permissions()
    assert baseline["metrics"] == {"granted": 18, "denied": 6, "newGrants": 11}
    assert {item["key"] for item in baseline["granted"]} >= {"tasks:assign", "self:wake", "canCreateAgents"}
    assert {item["key"] for item in baseline["denied"]} == {
        "agents:create", "environments:manage", "tools:admin",
        "users:invite", "users:manage_permissions", "joins:approve",
    }
    assert any("backfill" in item for item in baseline["exceptions"])


def test_permissions_detect_denied_granted_conflict_and_unknown_keys() -> None:
    result = audit_permissions(entries=PERMISSIONS)
    found = kinds(result)
    assert "denied-granted" in found
    assert "wildcard-permission" in found
    assert "unknown-key" in found
    assert result["metrics"]["deniedGranted"] == 1

    conflict = audit_permissions(entries="Ana | users:invite, tasks:assign | users:invite |\n")
    assert "grant-deny-conflict" in kinds(conflict)


def test_permissions_flag_runtime_override_and_exception_expansion() -> None:
    result = audit_permissions(entries=PERMISSIONS)
    found = kinds(result)
    assert "runtime-override" in found

    only_managed = audit_permissions(entries="Ana | agents:configure, tasks:assign | |\n", managed=True)
    assert "exception-expanded" in kinds(only_managed)


def test_permissions_check_quota_and_creation() -> None:
    result = audit_permissions(entries=PERMISSIONS)
    found = kinds(result)
    assert "quota-exceeded" in found
    assert "create-without-quota" in found

    without_quota = audit_permissions(entries="Ana | canCreateAgents, tasks:assign | |\n")
    assert "create-without-quota" in kinds(without_quota)

    quota_only = audit_permissions(entries="Ana | tasks:assign | | cota:3\n")
    assert "quota-without-grant" in kinds(quota_only)


def test_permissions_reject_duplicates_and_empty_entries() -> None:
    with pytest.raises(AgencyError, match="agente"):
        audit_permissions(entries="   ")
    duplicate = audit_permissions(entries="Ana | tasks:assign | |\nAna | tools:use | |\n")
    assert "duplicate" in kinds(duplicate)


# ---------------------------------------------------------------- API


def test_api_exposes_the_agency_catalog_and_baseline(client: TestClient) -> None:
    health = client.get("/api/health").json()
    assert health["version"] == "0.42.1"
    assert health["skills"] == 223

    catalog = client.get("/api/skills").json()["skills"]
    agency = {skill["id"] for skill in catalog if skill["id"].startswith("agency.")}
    assert agency == {
        "agency.roster", "agency.board", "agency.budget",
        "agency.watchdog", "agency.permissions", "agency.defaults",
    }

    baseline = client.post("/api/skills/agency.defaults/execute", json={"parameters": {}})
    assert baseline.status_code == 200
    assert baseline.json()["result"]["metrics"]["granted"] == 18


def test_api_executes_roster_and_watchdog_without_side_effects(client: TestClient) -> None:
    roster = client.post("/api/skills/agency.roster/execute", json={"parameters": {"roster": ROSTER}})
    assert roster.status_code == 200
    body = roster.json()
    assert body["ok"] is True
    assert body["result"]["metrics"]["agents"] == 4
    assert body["result"]["executed"] is False

    first = client.post("/api/skills/agency.watchdog/execute", json={"parameters": {"watched": "ENG-1", "tasks": SUBTREE}})
    assert first.json()["ok"] is True
    fingerprint = first.json()["result"]["fingerprint"]

    second = client.post(
        "/api/skills/agency.watchdog/execute",
        json={"parameters": {"watched": "ENG-1", "tasks": SUBTREE, "lastFingerprint": fingerprint}},
    )
    assert second.json()["result"]["suppressed"] is True
    assert second.json()["result"]["reviewTask"] == first.json()["result"]["reviewTask"]


def test_api_rejects_invalid_agency_parameters(client: TestClient) -> None:
    invalid_mode = client.post("/api/skills/agency.roster/execute", json={"parameters": {"roster": ROSTER, "mode": "turbo"}})
    assert invalid_mode.json()["ok"] is False
    assert "mode" in invalid_mode.json()["error"]["message"]

    empty = client.post("/api/skills/agency.roster/execute", json={"parameters": {"roster": "  "}})
    assert empty.json()["ok"] is False

    bad_fingerprint = client.post(
        "/api/skills/agency.watchdog/execute",
        json={"parameters": {"watched": "ENG-1", "tasks": SUBTREE, "lastFingerprint": "abc"}},
    )
    assert bad_fingerprint.json()["ok"] is False
    assert "lastFingerprint" in bad_fingerprint.json()["error"]["message"]
