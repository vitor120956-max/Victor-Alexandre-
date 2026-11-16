"""A regra do projeto, cobrada por máquina (0.91.21).

O dono pediu: *“toda vez q corrigir um bug crie um teste de regressao”*. Uma
regra que depende de alguém lembrar não é uma regra — é uma intenção. Este
arquivo transforma o pedido em três verificações que rodam junto com a suíte:

1. cada versão que saiu com correção tem uma linha em `docs/TESTES.md`
   dizendo **qual teste** a cobre;
2. o teste citado existe de verdade (nome de arquivo errado não passa);
3. o documento da regra continua lá.

Não é sobre estilo de código: é para o defeito consertado não voltar em
silêncio três versões depois — foi o que quase aconteceu entre a 0.91.17 e a
0.91.20.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
DOC = RAIZ / "docs" / "TESTES.md"
TESTS = RAIZ / "server" / "tests"

# A regra vale a partir daqui: antes disso, as correções não tinham esse
# compromisso (e reescrever o histórico não tornaria nada mais seguro).
PRIMEIRA_VERSAO_COM_REGRA = (0, 91, 13)


def _versao(texto: str) -> tuple[int, ...]:
    return tuple(int(parte) for parte in texto.split("."))


def _versoes_com_nota() -> list[str]:
    """As versões que têm `NOVO-<versão>.md` — as que foram entregues ao dono."""
    achadas = []
    for caminho in RAIZ.glob("NOVO-*.md"):
        achado = re.fullmatch(r"NOVO-(\d+\.\d+\.\d+)\.md", caminho.name)
        if achado:
            achadas.append(achado.group(1))
    return sorted(achadas, key=_versao)


def _linhas_da_tabela() -> dict[str, str]:
    """As linhas da seção 3: `| 0.91.17 | testes... |`."""
    texto = DOC.read_text(encoding="utf-8")
    linhas: dict[str, str] = {}
    for linha in texto.splitlines():
        achado = re.match(r"\|\s*(\d+\.\d+\.\d+)\s*\|(.*)\|\s*$", linha.strip())
        if achado:
            linhas[achado.group(1)] = achado.group(2)
    return linhas


def test_o_documento_da_regra_existe():
    assert DOC.is_file(), "docs/TESTES.md sumiu — a regra mora nele"
    texto = DOC.read_text(encoding="utf-8")
    assert "teste que reproduz" in texto.lower()
    assert "ponta a ponta" in texto.lower()


def test_toda_versao_corrigida_tem_um_teste_de_regressao_listado():
    """Cada `NOVO-x.y.z.md` a partir da 0.91.13 precisa de uma linha na tabela."""
    tabela = _linhas_da_tabela()
    faltando = [
        versao
        for versao in _versoes_com_nota()
        if _versao(versao) >= PRIMEIRA_VERSAO_COM_REGRA and versao not in tabela
    ]
    assert not faltando, (
        "sem teste de regressão listado em docs/TESTES.md para: "
        + ", ".join(faltando)
        + ". Toda correção entra com o teste que reproduz o defeito."
    )


def test_os_testes_citados_existem():
    """Nome de arquivo de teste errado não passa: o documento não pode mentir."""
    tabela = _linhas_da_tabela()
    problemas: list[str] = []
    for versao, conteudo in tabela.items():
        citados = set(re.findall(r"(test_[a-z0-9_]+\.py)", conteudo))
        if not citados:
            problemas.append(f"{versao}: nenhum arquivo de teste citado")
            continue
        for nome in sorted(citados):
            if not (TESTS / nome).is_file():
                problemas.append(f"{versao}: cita {nome}, que não existe")
    assert not problemas, "\n".join(problemas)


def test_o_manual_da_pagina_existe_e_esta_no_readme():
    """O dono pediu o manual da página (“onde é o nome, onde clicar, passo a passo”).

    Manual que ninguém acha não serve: ele fica no README, e o texto tem de
    cobrir os campos que a página realmente mostra.
    """
    manual = RAIZ / "docs" / "CHAVE-OPENROUTER.md"
    assert manual.is_file(), "o manual da página da chave tem de existir"

    texto = manual.read_text(encoding="utf-8")
    for campo in ("Name", "Expiration", "Credit limit", "Create", "Copy", "No expiration", "No limit"):
        assert campo in texto, f"o manual não fala de “{campo}”"

    readme = (RAIZ / "README.md").read_text(encoding="utf-8")
    assert "docs/CHAVE-OPENROUTER.md" in readme, "o README aponta para o manual da página"
    assert "diagnostico-chave.bat" in texto, "o manual ensina como pedir o diagnóstico"


def test_a_regra_esta_no_readme():
    """Quem chega no projeto pelo README tem de encontrar a regra."""
    readme = (RAIZ / "README.md").read_text(encoding="utf-8")
    assert "docs/TESTES.md" in readme, "o README aponta para a regra dos testes"
