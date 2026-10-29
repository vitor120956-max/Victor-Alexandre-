"""`iniciar.py`: o que a pessoa vê quando a API não sobe (ou já está de pé).

O sintoma que gerou estes testes: a interface dizia "A API Python está offline"
e mandava rodar `npm run dev` — comando que não existe numa instalação por zip.
Aqui ficam presos o caminho de subida, a porta ocupada e o banner único.
"""
from __future__ import annotations

import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

import pytest

RAIZ = Path(__file__).resolve().parents[2]
INICIAR = RAIZ / "iniciar.py"


def _texto() -> str:
    return INICIAR.read_text(encoding="utf-8")


def test_usa_a_instancia_do_modulo_e_nao_a_factory():
    """`create_app` no import + factory chamava create_app duas vezes (banner x2)."""
    texto = _texto()
    assert 'uvicorn.run("server.app:app"' in texto
    assert "factory=True" not in texto


def test_procura_a_interface_sem_importar_o_servidor():
    texto = _texto()
    assert "def _pasta_da_interface" in texto
    assert "def _ja_esta_rodando" in texto
    assert "def _porta_livre" in texto
    # importar server.app antes do uvicorn era o que duplicava o banner
    assert "from server.app import pasta_da_interface" not in texto


def test_nao_manda_mais_digitar_ctrl_c():
    assert "Ctrl+C" not in _texto()


def test_porta_ocupada_por_outro_programa_avisa_e_sai_com_erro():
    with socket.socket() as ocupada:
        ocupada.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        ocupada.bind(("127.0.0.1", 0))
        ocupada.listen(1)
        porta = ocupada.getsockname()[1]
        processo = subprocess.run(
            [sys.executable, str(INICIAR), "--porta", str(porta)],
            cwd=str(RAIZ),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    assert processo.returncode == 1
    assert "está ocupada por outro programa" in processo.stdout
    assert "--porta" in processo.stdout


def test_jarvis_ja_rodando_nao_sobe_outro():
    with socket.socket() as livre:
        livre.bind(("127.0.0.1", 0))
        porta = livre.getsockname()[1]
    processo = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server.app:app", "--host", "127.0.0.1", "--port", str(porta)],
        cwd=str(RAIZ),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={"JARVIS_HOST_TOKEN_SILENCIOSO": "1", "PATH": "/usr/bin:/bin", "HOME": "/tmp"},
    )
    try:
        for _ in range(60):
            try:
                with urlopen(f"http://127.0.0.1:{porta}/api/health", timeout=1) as resposta:
                    if resposta.status == 200:
                        break
            except OSError:
                time.sleep(0.5)
        else:
            pytest.skip("não consegui subir a API para o teste")

        segundo = subprocess.run(
            [sys.executable, str(INICIAR), "--porta", str(porta)],
            cwd=str(RAIZ),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    finally:
        processo.terminate()
        processo.wait(timeout=20)

    assert segundo.returncode == 0
    assert "Já existe uma API respondendo" in segundo.stdout


def test_o_front_nao_manda_rodar_npm_em_instalacao_por_zip():
    """Quem instalou pelo zip não tem Node: o comando tem de ser o do Python."""
    for caminho in (RAIZ / "src").rglob("*.ts*"):
        assert "npm run dev" not in caminho.read_text(encoding="utf-8"), caminho


def test_mensagem_offline_traz_o_comando_certo():
    texto = (RAIZ / "src" / "context" / "AppContext.tsx").read_text(encoding="utf-8")
    trecho = re.search(r"A API Python não respondeu em http://127\.0\.0\.1:8000.{0,400}", texto, re.S)
    assert trecho, "mensagem de offline não encontrada"
    assert "iniciar.py" in trecho.group(0)
