"""Testes do `configurar-chave.py` (0.37.2).

O script existe porque o Bloco de Notas do Windows 10 antigo (1607) não lê
quebra de linha Unix e amassa o `.env`. Ele grava em CRLF, preserva as outras
variáveis e nunca imprime a chave inteira.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
CAMINHO = RAIZ / "configurar-chave.py"


def carregar():
    spec = importlib.util.spec_from_file_location("configurar_chave", CAMINHO)
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture()
def script(tmp_path, monkeypatch):
    modulo = carregar()
    env = tmp_path / ".env"
    exemplo = tmp_path / ".env.example"
    exemplo.write_bytes(
        b"# comentario\r\nJARVIS_AI_PROVIDER=OpenAI\r\n"
        b"JARVIS_AI_BASE_URL=https://api.openai.com/v1\r\n"
        b"JARVIS_AI_MODEL=gpt-4o-mini\r\nJARVIS_AI_API_KEY=\r\n"
        b"JARVIS_HOST_REDE=0\r\n"
    )
    monkeypatch.setattr(modulo, "ENV", env)
    monkeypatch.setattr(modulo, "EXEMPLO", exemplo)
    monkeypatch.setattr(modulo, "interativo", lambda: False)
    return modulo


def test_ler_valor_devolve_none_quando_nao_existe(script):
    assert script.ler_valor("A=1\n", "B") is None
    assert script.ler_valor("JARVIS_AI_MODEL=x\n", "JARVIS_AI_MODEL") == "x"


def test_definir_troca_o_valor_existente(script):
    texto = "A=1\nJARVIS_AI_MODEL=velho\nZ=9\n"
    novo = script.definir(texto, "JARVIS_AI_MODEL", "novo")
    assert "JARVIS_AI_MODEL=novo" in novo
    assert "velho" not in novo
    assert novo.count("JARVIS_AI_MODEL=") == 1
    assert "A=1" in novo and "Z=9" in novo


def test_definir_acrescenta_quando_nao_existe(script):
    novo = script.definir("A=1\n", "JARVIS_AI_API_KEY", "sk-1")
    assert novo.splitlines()[-1] == "JARVIS_AI_API_KEY=sk-1"
    assert novo.startswith("A=1")


def test_gravar_usa_crlf_sem_bom(script, tmp_path):
    destino = tmp_path / "saida.env"
    script.gravar("A=1\nB=2\n", destino)
    bruto = destino.read_bytes()
    assert bruto.count(b"\r\n") == 2
    assert bruto.replace(b"\r\n", b"").count(b"\n") == 0
    assert not bruto.startswith(b"\xef\xbb\xbf")


def test_gravar_nao_duplica_o_cr(script, tmp_path):
    destino = tmp_path / "saida.env"
    script.gravar("A=1\r\nB=2\r\n", destino)
    assert destino.read_bytes() == b"A=1\r\nB=2\r\n"


def test_mascarar_nao_mostra_a_chave_inteira(script):
    chave = "sk-abcdefghijklmnopqrstuvwxyz123456"
    mascarada = script.mascarar(chave)
    assert chave not in mascarada
    assert mascarada.startswith("sk-ab")
    assert "3456" in mascarada
    assert "(35 caracteres)" in mascarada


def test_ver_nao_cria_arquivo(script, tmp_path, capsys):
    assert script.principal(["--ver"]) == 0
    assert not (tmp_path / ".env").exists()
    saida = capsys.readouterr().out
    assert "JARVIS_AI_PROVIDER" in saida


def test_chave_declara_grava_e_preserva_o_resto(script, tmp_path, capsys):
    codigo = script.principal(["--provedor", "OpenAI", "--modelo", "gpt-4o-mini", "--chave", "sk-teste-1234567890"])
    assert codigo == 0
    bruto = (tmp_path / ".env").read_bytes()
    assert b"JARVIS_AI_API_KEY=sk-teste-1234567890" in bruto
    assert b"JARVIS_HOST_REDE=0" in bruto
    assert bruto.count(b"\r\n") == bruto.count(b"\n")
    assert "sk-teste-1234567890" not in capsys.readouterr().out, "a chave inteira não pode ir para a tela"


def test_sem_chave_e_sem_arquivo_nao_cria_nada(script, tmp_path, capsys):
    assert script.principal([]) == 1
    assert not (tmp_path / ".env").exists()
    assert "Nada foi alterado" in capsys.readouterr().out


def test_limpar_apaga_so_a_chave(script, tmp_path):
    script.principal(["--chave", "sk-teste-1234567890"])
    assert script.principal(["--limpar"]) == 0
    bruto = (tmp_path / ".env").read_bytes()
    assert b"JARVIS_AI_API_KEY=\r\n" in bruto
    assert b"sk-teste-1234567890" not in bruto
    assert b"JARVIS_AI_MODEL=gpt-4o-mini" in bruto


def test_base_com_chat_completions_e_corrigida(script, tmp_path):
    script.principal(["--base", "https://api.openai.com/v1/chat/completions", "--chave", "sk-teste-1234567890"])
    bruto = (tmp_path / ".env").read_bytes()
    assert b"JARVIS_AI_BASE_URL=https://api.openai.com/v1\r\n" in bruto
    assert b"chat/completions" not in bruto


def test_base_com_barra_no_fim_nao_atrapalha(script, tmp_path):
    script.principal(["--base", "https://api.exemplo.com/v1/", "--chave", "sk-teste-1234567890"])
    bruto = (tmp_path / ".env").read_bytes()
    assert b"JARVIS_AI_BASE_URL=https://api.exemplo.com/v1\r\n" in bruto
    assert b".com/v1//" not in bruto


def test_le_env_salvo_em_ansi_pelo_notepad(script, tmp_path):
    alvo = tmp_path / ".env"
    alvo.write_bytes("# Já está no .gitignore\r\nJARVIS_AI_MODEL=gpt-4o\r\n".encode("cp1252"))
    texto = script.ler_texto(alvo)
    assert "Já está no .gitignore" in texto
    assert script.ler_valor(texto, "JARVIS_AI_MODEL") == "gpt-4o"


def test_script_nao_esta_no_gitignore_e_e_versionado():
    texto = (RAIZ / ".gitignore").read_text(encoding="utf-8")
    linhas = {linha.strip() for linha in texto.splitlines()}
    assert "configurar-chave.py" not in linhas
    assert CAMINHO.is_file()
