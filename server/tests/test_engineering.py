from __future__ import annotations

import pytest

from server.engineering import (
    create_adr,
    create_plan,
    create_spec,
    design_tests,
    evaluate_webvitals,
    release_gate,
    review_code,
    threat_model,
)


def test_spec_is_a_reviewable_draft_with_acceptance_and_ambiguity_warnings():
    result = create_spec(
        "Busca", "Permitir encontrar documentos.", "Usuários do núcleo",
        "Pesquisar rápido por título\nFiltrar por tipo", "A busca retorna apenas títulos correspondentes",
        "Nenhum serviço externo", "Qual deve ser o prazo?",
    )
    assert result["approvalRequired"] is True
    assert result["requirementCount"] == 2
    assert result["acceptanceCount"] == 1
    assert any("menos critérios" in warning for warning in result["warnings"])
    assert any("subjetivos" in warning for warning in result["warnings"])
    assert "Rascunho" in result["markdown"]


def test_plan_orders_declared_dependencies_and_marks_commands_as_not_executed():
    result = create_plan("Documentos", "Criar modelo\nExibir interface\nCriar API", "2:3\n3:1", "npm test", "npm run build")
    assert [task["originalTask"] for task in result["tasks"]] == [1, 3, 2]
    assert result["tasks"][2]["dependsOn"] == [3]
    assert result["commandsExecuted"] is False
    assert "Checkpoint humano" in result["markdown"]


def test_plan_rejects_cycles_and_invalid_dependency_references():
    with pytest.raises(ValueError, match="ciclo"):
        create_plan("Ciclo", "A\nB", "1:2\n2:1", "test", "build")
    with pytest.raises(ValueError, match="índice inexistente"):
        create_plan("Inválido", "A", "1:2", "test", "build")


def test_test_design_covers_positive_negative_integration_and_regression():
    result = design_tests("Upload", "Aceitar PDF válido\nRecusar arquivo acima do limite", "Arquivo corrompido", "pytest")
    assert result["criterionCount"] == 2
    assert result["testCaseCount"] == 8
    assert result["testsExecuted"] is False
    assert {case["level"] for case in result["cases"]} == {"Unitário", "Negativo", "Integração", "Regressão"}
    assert "Negativo" in result["markdown"] and "Regressão" in result["markdown"]


def test_static_review_reports_patterns_without_repeating_secret_values():
    result = review_code('token = "valor-sensivel-123"\neval(entrada)\nconst view = <div dangerouslySetInnerHTML={html} />;\nconst data: any = {};', "tsx", 350)
    assert result["counts"]["critical"] == 2
    assert result["counts"]["warning"] >= 2
    assert result["counts"]["info"] >= 1
    assert "valor-sensivel-123" not in result["markdown"]
    assert result["codeExecuted"] is False
    assert any(item["line"] == 2 for item in result["findings"])


def test_static_review_does_not_turn_no_pattern_into_approval():
    result = review_code("def soma(a, b):\n    return a + b", "python", 2)
    assert result["findingCount"] == 0
    assert "não equivale a aprovação" in result["markdown"]


def test_threat_model_applies_all_stride_lenses_to_each_boundary():
    result = threat_model("Upload", "Documentos pessoais", "Multipart HTTP\nLeitura do arquivo")
    assert result["boundaryCount"] == 2
    assert result["threatCount"] == 12
    assert result["auditCompleted"] is False
    assert "Spoofing" in result["markdown"] and "Elevation of privilege" in result["markdown"]


def test_webvitals_uses_thresholds_and_preserves_measurement_provenance():
    result = evaluate_webvitals(4_500, 180, 0.05, "lab", 0)
    assert result["ratings"] == {"LCP": "poor", "INP": "good", "CLS": "good"}
    assert result["overall"] == "poor"
    assert result["measurementTaken"] is False
    assert any("sintética" in warning for warning in result["warnings"])
    small_sample = evaluate_webvitals(2_000, 150, 0.05, "field", 50)
    assert any("pequena" in warning for warning in small_sample["warnings"])


def test_adr_marks_missing_tradeoffs_and_placeholder_numbering():
    result = create_adr("ADR-XXX", "Usar armazenamento local", "Proposed", "Precisamos preservar dados.", "Usar uma pasta confinada.", "Banco remoto", "Sem dependência externa\nPrecisamos de backup")
    assert result["approvalRequired"] is True
    assert len(result["warnings"]) == 2
    assert "Banco remoto" in result["markdown"]
    assert "Não informado" in result["markdown"]


def test_release_gate_blocks_missing_evidence_and_never_deploys():
    checks = {
        "testsPassed": True, "buildPassed": True, "reviewApproved": True, "securityChecked": True,
        "performanceChecked": True, "rollbackReady": True, "monitoringReady": True, "documentationUpdated": True,
    }
    blocked = release_gate("0.5.0", checks, True, "")
    assert blocked["decision"] == "BLOCKED"
    assert "evidence" in blocked["blockers"]
    ready = release_gate("0.5.0", checks, True, "npm test: 47 aprovados\nbuild: OK")
    assert ready["decision"] == "READY_FOR_HUMAN_APPROVAL"
    assert ready["deployExecuted"] is False
    checks["testsPassed"] = False
    assert release_gate("0.5.0", checks, True, "evidência")["decision"] == "BLOCKED"
