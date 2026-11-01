"""Primeira execução sem Node: o erro que o usuário viu, e o atalho que o evita.

O caso real, copiado da tela dele:

    D:\\JARVIS>git pull
    fatal: not a git repository (or any of the parent directories): .git

    D:\\JARVIS>npm run dev
    'concurrently' não é reconhecido como um comando interno

Duas mensagens, nenhuma delas dizendo o que fazer. A pasta veio do zip (sem
`.git`) e o `node_modules` nunca existiu ali. O JARVIS tinha, o tempo todo, um
caminho que não precisa de Node nenhum: `iniciar.py` serve a API com a interface
compilada de `web-dist/`.

O que estes testes travam:

- `iniciar-jarvis.bat` existe, é **ASCII puro** (o console do Windows 10 1607 com
  `chcp 65001` embaralha acento), está em **CRLF** (o Notepad antigo amassa LF),
  todo `goto` tem rótulo e ele **não** chama git, npm nem instala nada sem avisar;
- `npm run dev` deixou de cuspir o erro cru do Windows: agora explica e oferece
  o caminho sem Node;
- o `package.json` aponta `dev` para o script novo.

Nada aqui executa os servidores: os testes leem os arquivos e rodam o Node só no
caso em que ele deve falhar rápido.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
BAT = RAIZ / "iniciar-jarvis.bat"
DEV = RAIZ / "scripts" / "dev.mjs"
NODE = shutil.which("node")


# ------------------------------------------------------------------ o .bat


def test_o_atalho_existe():
    assert BAT.is_file()


def test_o_atalho_e_ascii_puro_e_crlf():
    bruto = BAT.read_bytes()
    estranhos = [b for b in bruto if b > 127]
    assert estranhos == [], f"{len(estranhos)} bytes fora de ASCII"
    assert b"\r\n" in bruto
    assert bruto.count(b"\n") == bruto.count(b"\r\n"), "tem linha só com LF"


def test_todo_goto_tem_rotulo():
    texto = BAT.read_text(encoding="ascii")
    rotulos = set(re.findall(r"^:([A-Za-z_][\w]*)", texto, flags=re.MULTILINE))
    destinos = set(re.findall(r"goto\s+([A-Za-z_][\w]*)", texto, flags=re.IGNORECASE))
    faltando = destinos - rotulos
    assert faltando == set(), f"goto sem rótulo: {sorted(faltando)}"


def test_o_atalho_nao_chama_git_nem_npm():
    """Ele pode *citar* npm na explicação; o que não pode é executar."""
    comandos = [
        linha.strip().lower()
        for linha in BAT.read_text(encoding="ascii").splitlines()
        if not linha.strip().lower().startswith(("echo", "rem", "::"))
    ]
    for linha in comandos:
        for proibido in ("git pull", "git fetch", "git clone", "npm install", "npm run", "npm ci"):
            assert proibido not in linha, linha


def test_o_atalho_usa_iniciar_py_e_o_python_do_venv():
    texto = BAT.read_text(encoding="ascii")
    assert "iniciar.py" in texto
    assert r'".venv\Scripts\python.exe" iniciar.py' in texto


def test_o_atalho_avisa_antes_de_cada_passo_e_nao_pede_ctrl_c():
    texto = BAT.read_text(encoding="ascii")
    for passo in ("[1/3]", "[2/3]", "[3/3]"):
        assert passo in texto, passo
    assert "Ctrl+C" not in texto and "CTRL+C" not in texto
    assert "feche esta janela no X" in texto


def test_o_atalho_sabe_criar_o_venv_e_instalar_as_bibliotecas():
    texto = BAT.read_text(encoding="ascii")
    assert "%PYCMD% -m venv .venv" in texto
    assert "-m pip install -r requirements.txt" in texto
    assert "import uvicorn, fastapi, dotenv" in texto


def test_o_atalho_nao_abre_o_navegador_antes_da_api_responder():
    """Abrir antes mostra 'não foi possível acessar' e o usuário acha que quebrou."""
    texto = BAT.read_text(encoding="ascii")
    linha = next((l for l in texto.splitlines() if "api/health" in l and "start" in l), "")
    assert linha, "não há espera pela API"
    assert "Start-Process 'http://127.0.0.1:8000'" in linha
    assert "Invoke-WebRequest" in linha
    assert "Start-Sleep" in linha


def test_o_atalho_termina_com_pause_para_ler_o_erro():
    texto = BAT.read_text(encoding="ascii")
    assert texto.count("pause") >= 4


# ------------------------------------------------------- npm run dev


def test_o_package_aponta_dev_para_o_script_novo():
    dados = json.loads((RAIZ / "package.json").read_text(encoding="utf-8"))
    assert dados["scripts"]["dev"] == "node scripts/dev.mjs"


def test_o_script_do_dev_explica_antes_de_falhar():
    texto = DEV.read_text(encoding="utf-8")
    assert "node_modules" in texto
    assert "iniciar.py" in texto
    assert "npm install" in texto


def test_o_script_do_dev_nao_instala_nada_sozinho():
    """Baixar 140 MB sem pedir é o que este atalho não faz."""
    texto = DEV.read_text(encoding="utf-8")
    assert "execFile" not in texto
    assert "execSync" not in texto
    for linha in texto.splitlines():
        sem_comentario = linha.split("//")[0]
        if "spawn" in sem_comentario or "exec" in sem_comentario:
            assert "npm" not in sem_comentario or "binConcurrently" in sem_comentario, linha
    assert "spawn(binConcurrently" in texto


@pytest.mark.skipif(NODE is None, reason="Node não está instalado nesta máquina")
def test_sem_node_modules_o_dev_diz_o_que_fazer(tmp_path):
    (tmp_path / "package.json").write_text('{"version": "9.9.9"}', encoding="utf-8")
    pasta = tmp_path / "scripts"
    pasta.mkdir()
    shutil.copy(DEV, pasta / "dev.mjs")
    processo = subprocess.run(
        [NODE, str(pasta / "dev.mjs")],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert processo.returncode == 1
    saida = processo.stdout + processo.stderr
    assert "node_modules" in saida
    assert "iniciar.py" in saida
    assert "9.9.9" in saida, "a mensagem deve citar a versão desta pasta"
    assert "quebrado" in saida
