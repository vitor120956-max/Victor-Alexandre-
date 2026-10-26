"""Testes do `configurar-chave.py` (0.51.0).

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


# ---------------------------------------------------------------------------
# --testar: faz uma chamada real e traduz o erro em português.
# Os testes usam um servidor falso no lugar da rede.
# ---------------------------------------------------------------------------

class RespostaFalsa:
    def __init__(self, status, corpo=None):
        self.status_code = status
        self._corpo = corpo

    def json(self):
        if self._corpo is None:
            raise ValueError("sem json")
        return self._corpo


@pytest.fixture()
def httpx_falso(monkeypatch):
    import httpx

    caixa = {"resposta": RespostaFalsa(200, {"choices": [{"message": {"content": "ok"}}]}), "erro": None, "pedido": None}

    def post(url, headers=None, json=None, timeout=None):
        caixa["pedido"] = {"url": url, "headers": headers, "json": json, "timeout": timeout}
        if caixa["erro"] is not None:
            raise caixa["erro"]
        return caixa["resposta"]

    monkeypatch.setattr(httpx, "post", post)
    return caixa


def test_tester_sucesso_mostra_a_resposta(script, httpx_falso, capsys):
    assert script.tester("https://api.exemplo.com/v1", "modelo-x", "sk-teste-1234567890") is True
    saida = capsys.readouterr().out
    assert "FUNCIONOU" in saida
    assert "ok" in saida
    assert "sk-teste-1234567890" not in saida


def test_tester_nao_vaza_a_chave_no_cabecalho(script, httpx_falso, capsys):
    script.tester("https://api.exemplo.com/v1", "modelo-x", "sk-segredo-abcdefgh")
    assert "sk-segredo-abcdefgh" not in capsys.readouterr().out
    assert httpx_falso["pedido"]["headers"]["Authorization"] == "Bearer sk-segredo-abcdefgh"


def test_tester_monta_a_url_sem_barra_dupla(script, httpx_falso):
    script.tester("https://api.exemplo.com/v1/", "modelo-x", "sk-1")
    assert httpx_falso["pedido"]["url"] == "https://api.exemplo.com/v1/chat/completions"


def test_tester_sem_chave_nao_chama_a_rede(script, httpx_falso, capsys):
    assert script.tester("https://api.exemplo.com/v1", "modelo-x", "") is False
    assert httpx_falso["pedido"] is None
    assert "Não há chave" in capsys.readouterr().out


@pytest.mark.parametrize(
    "status,esperado",
    [
        (401, "recusada"),
        (404, "não encontrado"),
        (429, "limite"),
        (500, "HTTP 500"),
    ],
)
def test_tester_traduz_os_erros(script, httpx_falso, capsys, status, esperado):
    httpx_falso["resposta"] = RespostaFalsa(status)
    assert script.tester("https://api.exemplo.com/v1", "modelo-x", "sk-1") is False
    assert esperado in capsys.readouterr().out


def test_tester_com_falha_de_rede(script, httpx_falso, capsys):
    import httpx

    httpx_falso["erro"] = httpx.ConnectError("sem rede")
    assert script.tester("https://api.exemplo.com/v1", "modelo-x", "sk-1") is False
    assert "conexão" in capsys.readouterr().out


def test_testar_sozinho_confere_sem_gravar(script, httpx_falso, tmp_path, capsys):
    script.principal(["--chave", "sk-teste-1234567890"])
    antes = (tmp_path / ".env").read_bytes()
    assert script.principal(["--testar"]) == 0
    assert (tmp_path / ".env").read_bytes() == antes
    assert "FUNCIONOU" in capsys.readouterr().out


def test_testar_junto_com_chave_grava_e_confere(script, httpx_falso, tmp_path, capsys):
    assert script.principal(["--chave", "sk-teste-1234567890", "--testar"]) == 0
    assert b"JARVIS_AI_API_KEY=sk-teste-1234567890" in (tmp_path / ".env").read_bytes()
    assert "FUNCIONOU" in capsys.readouterr().out


def test_script_oferece_o_teste_de_verdade():
    texto = CAMINHO.read_text(encoding="utf-8")
    assert "--testar" in texto
    assert "FUNCIONOU" in texto
    assert "429" in texto


def test_doc_ensina_onde_conseguir_chave_sem_pagar():
    texto = (RAIZ / "docs" / "CONFIGURAR-IA.md").read_text(encoding="utf-8")
    baixo = texto.lower()
    for provedor in ("groq", "aistudio.google.com", "openrouter"):
        assert provedor in baixo, f"falta {provedor} na lista de provedores gratuitos"
    assert "não existe chave grátis da openai" in baixo
    assert "nenhum" in baixo and "cartão" in baixo


def test_doc_do_pendrive_aponta_para_os_provedores():
    texto = (RAIZ / "docs" / "PENDRIVE.md").read_text(encoding="utf-8")
    assert "console.groq.com/keys" in texto
    assert "CONFIGURAR-IA.md" in texto


def test_local_grava_chave_marcadora_e_base_padrao(script, tmp_path):
    assert script.principal(["--local", "--modelo", "qwen2.5-1.5b-instruct-q4_k_m.gguf"]) == 0
    bruto = (tmp_path / ".env").read_bytes()
    assert b"JARVIS_AI_BASE_URL=http://127.0.0.1:8080/v1\r\n" in bruto
    assert b"JARVIS_AI_API_KEY=local\r\n" in bruto
    assert b"qwen2.5-1.5b-instruct-q4_k_m.gguf" in bruto


def test_local_aceita_outra_porta(script, tmp_path):
    script.principal(["--local", "http://127.0.0.1:5001/v1", "--modelo", "m.gguf"])
    bruto = (tmp_path / ".env").read_bytes()
    assert b"JARVIS_AI_BASE_URL=http://127.0.0.1:5001/v1\r\n" in bruto


def test_local_nao_sobrescreve_chave_informada(script, tmp_path):
    script.principal(["--local", "--modelo", "m.gguf", "--chave", "sk-de-verdade-1234567"])
    bruto = (tmp_path / ".env").read_bytes()
    assert b"JARVIS_AI_API_KEY=sk-de-verdade-1234567\r\n" in bruto


def test_doc_explica_ia_local_e_a_limitacao_do_windows_1607():
    texto = (RAIZ / "docs" / "CONFIGURAR-IA.md").read_text(encoding="utf-8")
    assert "--local" in texto
    assert "22H2" in texto
    assert "llama.cpp" in texto
    assert "não é obrigado" in texto.lower() or "não é obrigado" in texto


def test_doc_cobre_maquina_antiga_e_noavx():
    texto = (RAIZ / "docs" / "CONFIGURAR-IA.md").read_text(encoding="utf-8")
    assert "noavx" in texto, "faltam instruções para CPU sem AVX"
    assert "Core 2" in texto
    assert "Google Drive" in texto
    assert "armazenamento" in texto


def test_doc_de_pesquisa_explica_o_que_existe_e_o_que_falta():
    caminho = RAIZ / "docs" / "PESQUISA.md"
    assert caminho.is_file()
    texto = caminho.read_text(encoding="utf-8")
    assert "JARVIS_HOST_REDE=1" in texto
    assert "DuckDuckGo" in texto
    assert "material" in texto, "o doc precisa dizer que o canal existe e nada o alimenta"
    assert "não" in texto
    assert "docs/PESQUISA.md" in (RAIZ / "README.md").read_text(encoding="utf-8")
