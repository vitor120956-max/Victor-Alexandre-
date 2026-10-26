"""Testes do `mover-dados.py --drive` (0.50.0): só livros e repos vão para o Drive."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent.parent


def _carregar() -> object:
    espec = importlib.util.spec_from_file_location("mover_dados_teste", RAIZ / "mover-dados.py")
    assert espec is not None and espec.loader is not None
    modulo = importlib.util.module_from_spec(espec)
    sys.modules["mover_dados_teste"] = modulo
    espec.loader.exec_module(modulo)
    return modulo


@pytest.fixture()
def mover(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> object:
    modulo = _carregar()
    monkeypatch.setattr(modulo, "RAIZ", tmp_path)
    monkeypatch.setattr(modulo, "STORAGE", tmp_path / "storage")
    monkeypatch.setattr(modulo, "ENV", tmp_path / ".env")
    for nome in ("JARVIS_DADOS", "JARVIS_BIBLIOTECA", "JARVIS_REPOS", "JARVIS_DRIVE"):
        monkeypatch.delenv(nome, raising=False)
    (tmp_path / "storage" / "biblioteca" / "fontes").mkdir(parents=True)
    (tmp_path / "storage" / "biblioteca" / "fontes" / "livro.json").write_text("{}", encoding="utf-8")
    (tmp_path / "storage" / "repos" / "r").mkdir(parents=True)
    (tmp_path / "storage" / "repos" / "r" / "README.md").write_text("# r", encoding="utf-8")
    (tmp_path / "storage" / "historico.json").write_text("[]", encoding="utf-8")
    (tmp_path / ".env").write_text("JARVIS_DADOS=\r\n", encoding="utf-8")
    drive = tmp_path / "Google Drive" / "Meu Drive"
    drive.mkdir(parents=True)
    # nunca deixar o teste enxergar o Drive de verdade da máquina
    monkeypatch.setattr(modulo.dados_mod, "detectar_drive", lambda: drive)
    return modulo


def test_drive_copia_biblioteca_e_repos(mover, tmp_path: Path) -> None:
    codigo = mover.main(["--drive", str(tmp_path / "Google Drive" / "Meu Drive")])
    assert codigo == 0
    base = tmp_path / "Google Drive" / "Meu Drive" / "JARVIS-DADOS"
    assert (base / "biblioteca" / "fontes" / "livro.json").is_file()
    assert (base / "repos" / "r" / "README.md").is_file()


def test_drive_deixa_o_estado_do_agente_no_pc(mover, tmp_path: Path) -> None:
    mover.main(["--drive", str(tmp_path / "Google Drive" / "Meu Drive")])
    base = tmp_path / "Google Drive" / "Meu Drive" / "JARVIS-DADOS"
    assert not (base / "historico.json").exists()
    assert (tmp_path / "storage" / "historico.json").is_file()


def test_drive_grava_as_variaveis_em_crlf(mover, tmp_path: Path) -> None:
    mover.main(["--drive", str(tmp_path / "Google Drive" / "Meu Drive")])
    bruto = (tmp_path / ".env").read_bytes()
    assert b"\r\n" in bruto
    assert bruto.count(b"\n") == bruto.count(b"\r\n")
    assert b"JARVIS_BIBLIOTECA=" in bruto
    assert b"JARVIS_REPOS=" in bruto


def test_drive_nao_apaga_origem(mover, tmp_path: Path) -> None:
    mover.main(["--drive", str(tmp_path / "Google Drive" / "Meu Drive")])
    assert (tmp_path / "storage" / "biblioteca" / "fontes" / "livro.json").is_file()
    assert (tmp_path / "storage" / "repos" / "r" / "README.md").is_file()


def test_drive_com_pasta_inexistente_nao_mexe_no_env(mover, tmp_path: Path) -> None:
    antes = (tmp_path / ".env").read_bytes()
    codigo = mover.main(["--drive", str(tmp_path / "nao-existe")])
    assert codigo == 1
    assert (tmp_path / ".env").read_bytes() == antes


def test_drive_sem_deteccao_pede_o_caminho(mover, tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setattr(mover.dados_mod, "detectar_drive", lambda: None)
    codigo = mover.main(["--drive"])
    assert codigo == 1
    assert "Informe na mão" in capsys.readouterr().out


def test_drive_acrescenta_as_linhas_sem_duplicar(mover, tmp_path: Path) -> None:
    mover.main(["--drive", str(tmp_path / "Google Drive" / "Meu Drive")])
    mover.main(["--drive", str(tmp_path / "Google Drive" / "Meu Drive")])
    texto = (tmp_path / ".env").read_text(encoding="utf-8")
    assert texto.count("JARVIS_BIBLIOTECA=") == 1
    assert texto.count("JARVIS_REPOS=") == 1


def test_area_vazia_so_aponta_a_variavel(mover, tmp_path: Path) -> None:
    import shutil

    shutil.rmtree(tmp_path / "storage" / "repos")
    codigo = mover.main(["--drive", str(tmp_path / "Google Drive" / "Meu Drive")])
    assert codigo == 0
    texto = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "JARVIS_REPOS=" in texto


def test_bat_do_drive_usa_crlf_e_chama_o_script() -> None:
    bruto = (RAIZ / "usar-drive.bat").read_bytes()
    assert b"\r\n" in bruto
    assert bruto.count(b"\n") == bruto.count(b"\r\n"), "arquivo .bat com LF solto quebra no Windows"
    texto = bruto.decode("utf-8")
    assert "mover-dados.py --drive %*" in texto
    assert '".venv\\Scripts\\python.exe"' in texto
    assert "chcp 65001" in texto


def test_docs_do_drive_existem_e_citam_as_variaveis() -> None:
    texto = (RAIZ / "docs" / "GOOGLE-DRIVE.md").read_text(encoding="utf-8")
    assert "JARVIS_BIBLIOTECA" in texto
    assert "JARVIS_REPOS" in texto
    assert "historico.json" in texto
