"""Testes das listas de dependências (0.47.0).

O PyYAML não publica wheel para Python 3.15 no Windows (conferido no PyPI:
6.0 a 6.0.3, nenhuma `cp315`), e ele entra pela porta do `uvicorn[standard]`.
Sem wheel, o pip tenta compilar e o Windows pede Visual C++ Build Tools — erro
que já apareceu para um usuário real. Estes testes travam a regressão.
"""
from __future__ import annotations

from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
BASE = RAIZ / "requirements.txt"
RAPIDO = RAIZ / "requirements-rapido.txt"
DEV = RAIZ / "requirements-dev.txt"


def ler(caminho: Path) -> list[str]:
    linhas = []
    for bruta in caminho.read_text(encoding="utf-8").splitlines():
        linha = bruta.split("#", 1)[0].strip()
        if linha:
            linhas.append(linha)
    return linhas


def test_requirements_nao_pede_o_extra_standard():
    texto = BASE.read_text(encoding="utf-8")
    assert "uvicorn[standard]" not in texto, "o extra standard arrasta o PyYAML, que não compila em Python 3.15"
    assert any(item.startswith("uvicorn") for item in ler(BASE))


def test_requirements_nao_lista_pyyaml():
    for caminho in (BASE, RAPIDO, DEV):
        nomes = {item.split(">=")[0].split("==")[0].lower() for item in ler(caminho)}
        assert "pyyaml" not in nomes, f"{caminho.name} não deve pedir PyYAML"


def test_requirements_rapido_inclui_a_base_e_os_aceleradores():
    itens = ler(RAPIDO)
    assert "-r requirements.txt" in itens
    nomes = {item.split(">=")[0].split("<")[0] for item in itens}
    assert {"httptools", "websockets", "watchfiles"} <= nomes


def test_requirements_dev_inclui_a_base_e_o_pytest():
    itens = ler(DEV)
    assert "-r requirements.txt" in itens
    assert any(item.startswith("pytest") for item in itens)


def test_lista_essencial_cobre_o_que_o_servidor_importa():
    nomes = {item.split(">=")[0].split("<")[0] for item in ler(BASE)}
    for obrigatorio in {
        "fastapi",
        "uvicorn",
        "httpx",
        "pydantic",
        "python-dotenv",
        "python-docx",
        "openpyxl",
        "python-pptx",
        "pypdf",
        "reportlab",
        "python-multipart",
    }:
        assert obrigatorio in nomes, f"falta {obrigatorio}"


def test_iniciar_py_explica_o_erro_de_compilador():
    texto = (RAIZ / "iniciar.py").read_text(encoding="utf-8")
    assert "Visual C++" in texto
    assert "pyyaml" in texto.lower()


@pytest.mark.parametrize("nome", ["requirements.txt", "requirements-rapido.txt", "requirements-dev.txt"])
def test_arquivos_existem(nome):
    assert (RAIZ / nome).is_file()


def test_codigo_do_servidor_nao_importa_yaml_nem_websockets():
    for arquivo in (RAIZ / "server").glob("*.py"):
        texto = arquivo.read_text(encoding="utf-8", errors="replace")
        assert "import yaml" not in texto, f"{arquivo.name} importa yaml sem declarar dependência"
        assert "import websockets" not in texto, f"{arquivo.name} importa websockets sem declarar dependência"


# ---------------------------------------------------------------------------
# Quebra de linha: o Bloco de Notas do Windows 10 antigo (1607 = build 14393)
# não entende LF e mostra o arquivo inteiro como uma única linha. Se o usuário
# salvar nesse estado, ele grava tudo amassado e o pip não consegue ler.
# Estes quatro arquivos são os que ele abre no editor, então ficam em CRLF.
# ---------------------------------------------------------------------------

ARQUIVOS_DO_EDITOR = [
    "requirements.txt",
    "requirements-dev.txt",
    "requirements-rapido.txt",
    ".env.example",
]


@pytest.mark.parametrize("nome", ARQUIVOS_DO_EDITOR)
def test_arquivo_do_notepad_usa_crlf(nome):
    bruto = (RAIZ / nome).read_bytes()
    assert b"\r\n" in bruto, f"{nome} sem CRLF: no Bloco de Notas antigo aparece tudo numa linha"
    assert b"\n" not in bruto.replace(b"\r\n", b""), f"{nome} tem LF solto misturado com CRLF"


@pytest.mark.parametrize("nome", ARQUIVOS_DO_EDITOR)
def test_gitattributes_preserva_o_crlf(nome):
    atributos = (RAIZ / ".gitattributes").read_text(encoding="utf-8")
    linhas = [linha.split("#", 1)[0].split() for linha in atributos.splitlines()]
    declarados = {partes[0]: partes[1:] for partes in linhas if len(partes) >= 2}
    assert nome in declarados, f".gitattributes precisa declarar {nome} como -text"
    assert "-text" in declarados[nome], f"{nome} precisa de -text para o git não normalizar para LF"


def test_env_example_tem_a_chave_para_preencher():
    texto = (RAIZ / ".env.example").read_text(encoding="utf-8")
    assert "JARVIS_AI_API_KEY=" in texto
