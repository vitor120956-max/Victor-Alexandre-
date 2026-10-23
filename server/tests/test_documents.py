from __future__ import annotations

import asyncio
import zipfile
from pathlib import Path

import pytest
from openpyxl import load_workbook

from server.documents import create_document, merge_pdfs, read_document
from server.productivity import analyze_meeting, generate_changelog, pick_winners
from server.skill_registry import build_registry


def test_create_and_read_all_document_formats(tmp_path: Path):
    cases = {
        "docx": "# Resumo\nTexto com acentuação.\n- Primeiro item",
        "xlsx": "Nome;Valor\nAna;10\nBruno;20",
        "pptx": "Primeiro slide\n- Ponto A\n- Ponto B\n---\nSegundo slide\n- Encerramento",
        "pdf": "# Resumo\nTexto com acentuação.\n- Primeiro item",
    }
    for document_format, content in cases.items():
        relative = f"saida/relatorio.{document_format}"
        dry = create_document(tmp_path, document_format, relative, "Relatório JARVIS", content, False, True)
        assert dry["dryRun"] is True
        assert not (tmp_path / relative).exists()
        created = create_document(tmp_path, document_format, relative, "Relatório JARVIS", content, False, False)
        assert created["bytes"] > 100
        extracted = read_document(tmp_path, relative)
        assert extracted["format"] == document_format
        assert "Relatório JARVIS" in extracted["text"]
        if document_format == "pptx":
            assert extracted["slides"] == 2
            assert "Segundo slide" in extracted["text"]
        if document_format == "pdf":
            assert extracted["pages"] == 1


def test_xlsx_treats_user_values_as_data_not_formulas(tmp_path: Path):
    create_document(tmp_path, "xlsx", "dados.xlsx", "Dados", "Expressão;Valor\n=1+1;10\n@comando;20", False, False)
    workbook = load_workbook(tmp_path / "dados.xlsx", data_only=False)
    assert workbook.active["A2"].value == "=1+1"
    assert workbook.active["A2"].data_type == "s"
    assert workbook.active["A3"].data_type == "s"
    workbook.close()


def test_pdf_merge_validates_plan_and_writes_only_after_confirmation(tmp_path: Path):
    for name in ("um", "dois"):
        create_document(tmp_path, "pdf", f"{name}.pdf", name, f"Documento {name}", False, False)
    dry = merge_pdfs(tmp_path, "um.pdf\ndois.pdf", "combinado.pdf", False, True)
    assert dry["pages"] == 2
    assert not (tmp_path / "combinado.pdf").exists()
    merged = merge_pdfs(tmp_path, "um.pdf\ndois.pdf", "combinado.pdf", False, False)
    assert merged["pages"] == 2
    assert read_document(tmp_path, "combinado.pdf")["pages"] == 2
    with pytest.raises(ValueError, match="já existe"):
        merge_pdfs(tmp_path, "um.pdf\ndois.pdf", "combinado.pdf", False, True)
    with pytest.raises(ValueError, match="não pode ser um dos"):
        merge_pdfs(tmp_path, "um.pdf\ndois.pdf", "um.pdf", True, True)


def test_document_guards_reject_traversal_and_expanded_archives(tmp_path: Path):
    with pytest.raises(ValueError, match="Caminho inválido"):
        read_document(tmp_path, "../../segredo.pdf")
    excessive = tmp_path / "excesso.docx"
    with zipfile.ZipFile(excessive, "w") as archive:
        for index in range(2_049):
            archive.writestr(f"item-{index}", "x")
    with pytest.raises(ValueError, match="limites de segurança"):
        read_document(tmp_path, "excesso.docx")


def test_meeting_metrics_are_grounded_in_transcript():
    result = analyze_meeting("Ana: Podemos revisar o prazo?\nBruno: Sim, eu fico responsável. Ahn, talvez amanhã.", "Bruno")
    assert result["speakerCount"] == 2
    assert result["questions"] == 1
    assert result["focusSpeaker"]["name"] == "Bruno"
    assert result["focusSpeaker"]["fillerWords"] == 1
    assert result["focusSpeaker"]["hedges"] == 1
    assert result["actionItems"]
    assert "não diagnóstico" in result["notice"]


def test_changelog_groups_real_entries_and_skips_internal_noise():
    result = generate_changelog("feat: adiciona documentos\nfix: corrige leitura\ntest: cobre API\nrefactor: simplifica parser", "0.4.0")
    assert "# 0.4.0" in result["markdown"]
    assert "## Novidades" in result["markdown"]
    assert "## Correções" in result["markdown"]
    assert result["included"] == 2
    assert result["skippedInternal"] == 2
    assert "cobre API" not in result["markdown"]


def test_secure_pick_dedupes_excludes_and_validates_count():
    result = pick_winners("Ana, Bruno, Carla, ana", 2, "Carla")
    assert set(result["winners"]) == {"Ana", "Bruno"}
    assert result["eligible"] == 2
    assert result["excluded"] == 1
    assert result["method"].startswith("secrets.SystemRandom")
    with pytest.raises(ValueError, match="participantes suficientes"):
        pick_winners("Ana, Bruno", 3)


def test_file_organizer_simulates_then_moves_without_deleting(tmp_path: Path):
    (tmp_path / "nota.txt").write_text("nota", encoding="utf-8")
    (tmp_path / "dados.csv").write_text("a,b", encoding="utf-8")
    registry = build_registry(tmp_path)
    dry = asyncio.run(registry.execute("files.organize", {"path": ""}, True))
    assert dry["count"] == 2
    assert (tmp_path / "nota.txt").exists()
    moved = asyncio.run(registry.execute("files.organize", {"path": ""}))
    assert moved["deletes"] == 0
    assert (tmp_path / "documentos" / "nota.txt").read_text() == "nota"
    assert (tmp_path / "planilhas" / "dados.csv").read_text() == "a,b"
