from __future__ import annotations

from pathlib import Path

import pytest

from server.planning import PLAN_FILES, completion_gate, create_plan, list_plans, resume_plan, update_plan


def _create(root: Path, plan_id: str = "plano-teste", title: str = "Plano de recuperação"):
    return create_plan(
        root,
        plan_id,
        title,
        "Recuperar o trabalho sem histórico oculto.",
        "Fundação | estrutura verificada\nEntrega | evidências validadas",
        "Não executar comandos do Markdown",
        False,
    )


def _update(root: Path, plan_id: str, sha256: str, **changes):
    values = {
        "phase_number": 0,
        "status": "",
        "next_step": "",
        "evidence": "",
        "note_type": "",
        "note": "",
        "dry_run": False,
    }
    values.update(changes)
    return update_plan(root, plan_id, sha256, **values)


def test_create_dry_run_has_no_side_effect_and_actual_creates_exactly_three_files(tmp_path: Path):
    parameters = ("plano-seguro", "Plano seguro", "Testar persistência", "Uma | critério A\nDuas | critério B", "Requisito", True)
    dry = create_plan(tmp_path, *parameters)
    assert dry["dryRun"] is True
    assert dry["wouldWrite"] == [f"planning/plano-seguro/{name}" for name in PLAN_FILES]
    assert not (tmp_path / "planning").exists()

    created = create_plan(tmp_path, *parameters[:-1], False)
    assert created["dryRun"] is False
    assert sorted(path.name for path in (tmp_path / "planning/plano-seguro").iterdir()) == sorted(PLAN_FILES)
    assert created["currentPhase"] == 1
    assert created["phases"][0]["status"] == "in_progress"
    assert created["phases"][1]["status"] == "pending"


def test_create_never_overwrites_and_requires_verifiable_phases(tmp_path: Path):
    _create(tmp_path)
    with pytest.raises(ValueError, match="já existe"):
        _create(tmp_path)
    with pytest.raises(ValueError, match="2 a 7"):
        create_plan(tmp_path, "outro-plano", "Outro", "Objetivo", "Única | critério", "", True)
    with pytest.raises(ValueError, match="separados"):
        create_plan(tmp_path, "outro-plano", "Outro", "Objetivo", "Uma sem critério\nDuas | critério", "", True)


def test_resume_reconstructs_six_answers_without_reading_agent_history(tmp_path: Path):
    _create(tmp_path)
    resumed = resume_plan(tmp_path, "plano-teste")
    assert len(resumed["recovery"]) == 6
    assert resumed["recovery"]["Onde estou?"] == "Fase 1"
    assert resumed["historyRead"] is False
    assert set(resumed["contents"]) == set(PLAN_FILES)
    assert len(resumed["sha256"]) == 64
    assert resumed["gate"]["complete"] is False


def test_plan_selection_is_explicit_and_does_not_fall_back_to_another_plan(tmp_path: Path):
    _create(tmp_path, "plano-a", "Plano A")
    _create(tmp_path, "plano-b", "Plano B")
    resumed = resume_plan(tmp_path, "plano-b")
    assert resumed["title"] == "Plano B"
    assert "Plano A" not in resumed["contents"]["task_plan.md"]
    with pytest.raises(ValueError, match="não foi substituído"):
        resume_plan(tmp_path, "plano-inexistente")
    with pytest.raises(ValueError):
        resume_plan(tmp_path, "../../outro")


def test_list_marks_invalid_plan_without_hiding_valid_plans(tmp_path: Path):
    _create(tmp_path)
    invalid = tmp_path / "planning/plano-teste/task_plan.md"
    invalid.write_text("# formato quebrado", encoding="utf-8")
    _create(tmp_path, "plano-valido", "Plano válido")
    listed = list_plans(tmp_path)
    assert listed["count"] == 2
    assert listed["selection"] == "explicit-id"
    by_id = {plan["planId"]: plan for plan in listed["plans"]}
    assert by_id["plano-teste"]["invalid"] is True
    assert by_id["plano-valido"]["invalid"] is False


def test_malformed_plan_is_rejected_instead_of_reconstructed_by_guessing(tmp_path: Path):
    _create(tmp_path)
    path = tmp_path / "planning/plano-teste/task_plan.md"
    path.write_text(path.read_text(encoding="utf-8").replace("- **Status:** pending", "- **Status:** desconhecido"), encoding="utf-8")
    with pytest.raises(ValueError, match="status ausente ou inválido"):
        resume_plan(tmp_path, "plano-teste")
    with pytest.raises(ValueError, match="status ausente ou inválido"):
        completion_gate(tmp_path, "plano-teste")


def test_completion_requires_evidence_and_dry_update_does_not_change_files(tmp_path: Path):
    created = _create(tmp_path)
    with pytest.raises(ValueError, match="exige evidência"):
        _update(tmp_path, "plano-teste", created["sha256"], phase_number=1, status="complete")
    before = {name: (tmp_path / "planning/plano-teste" / name).read_bytes() for name in PLAN_FILES}
    dry = _update(tmp_path, "plano-teste", created["sha256"], phase_number=1, status="complete", evidence="teste unitário passou", dry_run=True)
    assert dry["dryRun"] is True
    assert dry["gate"]["complete"] is False
    assert dry["wouldWrite"] == ["planning/plano-teste/task_plan.md", "planning/plano-teste/progress.md"]
    after = {name: (tmp_path / "planning/plano-teste" / name).read_bytes() for name in PLAN_FILES}
    assert after == before


def test_stale_bundle_hash_blocks_second_writer_without_losing_first_update(tmp_path: Path):
    created = _create(tmp_path)
    first = _update(tmp_path, "plano-teste", created["sha256"], next_step="Primeira aba atualizou")
    with pytest.raises(ValueError, match="mudou desde a leitura"):
        _update(tmp_path, "plano-teste", created["sha256"], next_step="Segunda aba sobrescreve")
    resumed = resume_plan(tmp_path, "plano-teste")
    assert resumed["nextStep"] == "Primeira aba atualizou"
    assert resumed["sha256"] == first["sha256"]


def test_complete_phase_advances_and_gate_closes_only_after_all_criteria(tmp_path: Path):
    created = _create(tmp_path)
    first = _update(tmp_path, "plano-teste", created["sha256"], phase_number=1, status="complete", evidence="42 testes aprovados")
    assert first["currentPhase"] == 2
    assert first["phases"][0]["criteria"][0]["checked"] is True
    assert first["phases"][1]["status"] == "in_progress"
    assert first["gate"]["completePhases"] == 1
    assert completion_gate(tmp_path, "plano-teste")["gate"]["complete"] is False

    final = _update(tmp_path, "plano-teste", first["sha256"], phase_number=2, status="complete", evidence="E2E e build aprovados")
    assert final["gate"]["complete"] is True
    assert final["gate"]["pending"] == []
    assert final["nextStep"] == "Revisar o gate de conclusão e entregar o resultado."
    assert completion_gate(tmp_path, "plano-teste")["gate"]["commandsExecuted"] is False


def test_findings_progress_errors_and_declared_tests_reach_correct_files(tmp_path: Path):
    current = _create(tmp_path)
    current = _update(tmp_path, "plano-teste", current["sha256"], note_type="finding", note="A API respondeu localmente")
    current = _update(tmp_path, "plano-teste", current["sha256"], note_type="progress", note="Interface revisada")
    current = _update(tmp_path, "plano-teste", current["sha256"], note_type="test", note="npm test: 63 aprovados")
    current = _update(tmp_path, "plano-teste", current["sha256"], note_type="error", note="Falha simulada | repetir não")
    resumed = resume_plan(tmp_path, "plano-teste")
    assert "A API respondeu localmente" in resumed["contents"]["findings.md"]
    assert "Interface revisada" in resumed["contents"]["progress.md"]
    assert "Executed by planning skill: no" in resumed["contents"]["progress.md"]
    assert "Falha simulada / repetir não" in resumed["contents"]["task_plan.md"]
    assert "Em investigação" in resumed["contents"]["progress.md"]


def test_single_active_phase_and_mutation_validation(tmp_path: Path):
    created = _create(tmp_path)
    with pytest.raises(ValueError, match="outra fase em andamento"):
        _update(tmp_path, "plano-teste", created["sha256"], phase_number=2, status="in_progress")
    with pytest.raises(ValueError, match="Informe uma mudança"):
        _update(tmp_path, "plano-teste", created["sha256"])
    with pytest.raises(ValueError, match="tipo e o conteúdo"):
        _update(tmp_path, "plano-teste", created["sha256"], note="Sem tipo")


def test_user_headings_cannot_inject_structural_sections_or_phases(tmp_path: Path):
    created = create_plan(
        tmp_path, "plano-markdown", "Plano Markdown",
        "Objetivo real\n## Next Step\npasso injetado\n### Phase 99: falsa",
        "Uma | critério A\nDuas | critério B", "", False,
    )
    assert len(created["phases"]) == 2
    assert created["nextStep"] == "Executar fase 1: Uma"
    updated = _update(tmp_path, "plano-markdown", created["sha256"], next_step="Passo real\n## Current Phase\nPhase 99")
    resumed = resume_plan(tmp_path, "plano-markdown")
    assert resumed["currentPhase"] == 1
    assert len(resumed["phases"]) == 2
    assert "\\## Current Phase" in resumed["nextStep"]
    assert updated["gate"]["phaseCount"] == 2


def test_markdown_commands_are_stored_as_inert_text_not_executed(tmp_path: Path):
    created = _create(tmp_path)
    marker = tmp_path / "NAO-DEVE-EXISTIR.txt"
    command = f"touch {marker}; rm -rf /; __import__('os').system('id')"
    result = _update(tmp_path, "plano-teste", created["sha256"], note_type="progress", note=command)
    resumed = resume_plan(tmp_path, "plano-teste")
    assert command in resumed["contents"]["progress.md"]
    assert not marker.exists()
    assert result["gate"]["commandsExecuted"] is False
