"""O atualizador por zip: progresso de verdade na tela.

Estes testes não rodam PowerShell — eles garantem o contrato que dói quando
quebra: o `.bat` acha o auxiliar, os rótulos existem, o script é ASCII puro
(console com `chcp 65001` embaralha acento vindo do PowerShell), nunca toca em
`.env`/`storage`/`.venv`/`node_modules`/`.git` e devolve código 0 ou 1.

Quando o parser de PowerShell está instalado (`tree_sitter_powershell`), o
script é analisado sintaticamente de verdade; sem ele, esse teste é pulado.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
BAT = RAIZ / "atualizar.bat"
PS1 = RAIZ / "atualizar-baixar.ps1"


def _texto(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8", errors="replace")


# ------------------------------------------------------------------ arquivos

def test_o_auxiliar_existe_ao_lado_do_bat():
    assert PS1.is_file()


def test_o_auxiliar_e_ascii_puro():
    """Acento vindo do PowerShell vira lixo no console do Windows."""
    bruto = PS1.read_bytes()
    estranhos = [(i, b) for i, b in enumerate(bruto) if b > 127]
    assert estranhos == [], estranhos[:5]


def test_o_auxiliar_nao_tem_erro_de_sintaxe_powershell():
    sintaxe = pytest.importorskip("tree_sitter_powershell", reason="parser de PowerShell opcional")
    from tree_sitter import Language, Parser

    arvore = Parser(Language(sintaxe.language())).parse(PS1.read_bytes())
    assert arvore.root_node.has_error is False


# ------------------------------------------------------------------ progresso

def test_mostra_porcentagem_mb_velocidade_e_tempo():
    texto = _texto(PS1)
    assert "%" in texto
    assert "MB/s" in texto or "MB/s}" in texto
    assert "faltam" in texto
    assert "Formatar-Tempo" in texto


def test_usa_streaming_em_vez_de_baixar_de_uma_vez():
    """`Invoke-WebRequest` não dá progresso útil com o zip em streaming."""
    texto = _texto(PS1)
    assert "HttpWebRequest" in texto
    assert "GetResponseStream" in texto
    # a citação em comentário não conta: só o código de verdade importa
    codigo = "\n".join(linha for linha in texto.splitlines() if not linha.lstrip().startswith("#"))
    assert "Invoke-WebRequest" not in codigo


def test_trata_zip_sem_tamanho_declarado():
    """O codeload manda chunked, sem Content-Length: precisa de estimativa."""
    texto = _texto(PS1)
    assert "ContentLength" in texto
    assert "estimad" in texto  # "estimado"
    assert "jarvis-zip-bytes.txt" in texto
    assert "Gravar-Tamanho" in texto


def test_reescreve_a_linha_sem_encher_a_tela():
    texto = _texto(PS1)
    assert texto.count('"`r" + $linha') >= 1 or texto.count('`r') >= 3


# ------------------------------------------------------------------ seguranca

def test_nunca_copia_por_cima_do_que_e_do_usuario():
    texto = _texto(PS1)
    for protegido in ('.env', 'storage', 'node_modules', '.venv', '.git'):
        assert protegido in texto, protegido
    assert "pastasIgnoradas" in texto


def test_devolve_codigo_de_saida_para_o_bat_decidir():
    texto = _texto(PS1)
    assert re.search(r"^\s*exit 0", texto, re.M)
    assert re.search(r"^\s*exit 1", texto, re.M)


def test_falha_nao_apaga_nada():
    assert "Nada do que ja estava na pasta foi apagado" in _texto(PS1)


# ------------------------------------------------------------------ o .bat

def test_bat_chama_o_auxiliar_e_tem_caminho_de_volta():
    texto = _texto(BAT)
    assert 'if exist "%~dp0atualizar-baixar.ps1"' in texto
    assert "atualizar-baixar.ps1\" -Destino" in texto
    # sem o auxiliar, ainda atualiza (barra do próprio PowerShell)
    assert ":sem_progresso" in texto
    assert "Invoke-WebRequest" in texto  # só no caminho de volta


def test_todo_goto_do_bat_tem_rotulo():
    texto = _texto(BAT)
    rotulos = set(re.findall(r"^:(\w+)", texto, re.M))
    destinos = set(re.findall(r"goto\s+(\w+)", texto))
    faltando = {destino for destino in destinos if destino not in rotulos}
    assert faltando == set()


def test_bat_nao_manda_digitar_ctrl_c():
    assert "Ctrl+C" not in _texto(BAT)
