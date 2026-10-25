"""Testes do verificador de ambiente que acompanha o guia do pendrive (0.36.0).

O script é Node puro, de propósito: precisa funcionar antes de existir `.venv`
ou `node_modules`. Aqui ele é chamado como processo, do mesmo jeito que o
usuário chama, e a saída JSON é conferida item por item.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
SCRIPT = RAIZ / "scripts" / "checar-pendrive.mjs"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="Node não está instalado nesta máquina")


def rodar(script: Path = SCRIPT, cwd: Path = RAIZ) -> tuple[int, dict]:
    processo = subprocess.run(
        [NODE, str(script), "--json"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    dados = json.loads(processo.stdout or "{}")
    return processo.returncode, dados


def test_script_existe_e_e_executavel_pelo_node():
    assert SCRIPT.is_file()
    codigo, dados = rodar()
    assert codigo in (0, 1)
    assert dados["raiz"].rstrip("/").endswith("Victor-Alexandre-")
    assert isinstance(dados["itens"], list)


def test_mede_os_itens_que_importam():
    _codigo, dados = rodar()
    ids = {item["id"] for item in dados["itens"]}
    for esperado in {"node", "python", "deps-python", "deps-node", "env", "chave", "storage", "espaco", "fs", "git", "portas"}:
        assert esperado in ids


def test_cada_item_tem_estado_valido_e_explicacao():
    _codigo, dados = rodar()
    for item in dados["itens"]:
        assert item["estado"] in {"ok", "aviso", "falha"}
        assert item["titulo"].strip()
        assert item["detalhe"].strip()
        if item["estado"] == "falha":
            assert item["conserto"].strip(), f"{item['id']} falhou sem dizer como resolver"


def test_este_projeto_nao_tem_falta_obrigatoria():
    codigo, dados = rodar()
    assert dados["falhas"] == 0
    assert codigo == 0
    assert dados["pronto"] is True


def test_pasta_que_nao_e_projeto_reprova(tmp_path):
    (tmp_path / "scripts").mkdir()
    shutil.copy2(SCRIPT, tmp_path / "scripts" / "checar-pendrive.mjs")
    codigo, dados = rodar(script=tmp_path / "scripts" / "checar-pendrive.mjs", cwd=tmp_path)
    assert codigo == 1
    assert dados["pronto"] is False
    faltas = {item["id"] for item in dados["itens"] if item["estado"] == "falha"}
    assert {"deps-node", "env"} <= faltas


def test_saida_humana_tem_uma_linha_por_item():
    processo = subprocess.run(
        [NODE, str(SCRIPT)], cwd=str(RAIZ), capture_output=True, text=True, timeout=120, check=False
    )
    assert "JARVIS — checagem desta pasta" in processo.stdout
    assert processo.stdout.count("OK") + processo.stdout.count("ATENÇÃO") + processo.stdout.count("FALTA") >= 10
    assert processo.returncode == 0
