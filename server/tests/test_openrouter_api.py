"""Criar a chave sem navegador — testado contra um OpenRouter falso (0.91.29).

O caminho novo troca Chrome por um `POST`. O que dá para provar sem o PC do
dono, e é o que estes testes fazem:

1. o pedido é **bem formado** (endereço, cabeçalho, corpo) — nome vai, limite e
   validade **não** vão quando não foram pedidos;
2. a chave que volta é a que é gravada, e chave que volta sem `key` é erro, não
   `.env` vazio;
3. os erros do site viram frases em português que dizem **o que fazer** —
   401, 403, 429, servidor fora, internet fora;
4. a chave de gestão é **conferida** antes de ser guardada: uma chave comum
   copiada por engano é recusada com a explicação certa.
"""
from __future__ import annotations

import importlib.util
import io
import json
import types
import urllib.error
from pathlib import Path

import pytest

from server import openrouter_api

RAIZ = Path(__file__).resolve().parents[2]
CHAVE = "sk-or-v1-" + "a" * 64


class Resposta:
    """O que o `urlopen` devolveria: um corpo e um `with`."""

    def __init__(self, corpo: dict | str, codigo: int = 200) -> None:
        self.codigo = codigo
        self._bruto = (corpo if isinstance(corpo, str) else json.dumps(corpo)).encode("utf-8")

    def read(self) -> bytes:
        return self._bruto

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _abrir_de(resposta):
    """Um `abrir` que devolve sempre a mesma resposta e anota o pedido."""
    pedidos: list = []

    def abrir(pedido, _segundos=30.0):
        pedidos.append(pedido)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    abrir.pedidos = pedidos  # type: ignore[attr-defined]
    return abrir


def _erro(codigo: int, corpo: dict | str = "") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://openrouter.ai/api/v1/keys", codigo, "erro", {}, io.BytesIO(
            (corpo if isinstance(corpo, str) else json.dumps(corpo)).encode()
        )
    )


# ---------------------------------------------------------------------------
# O pedido
# ---------------------------------------------------------------------------

def test_o_pedido_leva_o_nome_e_nao_leva_limite_nem_validade():
    """“Sem limite e sem tempo de expiração” é o que se pede não mandando nada."""
    abrir = _abrir_de(Resposta({"data": {"name": "jarvis"}, "key": CHAVE}))

    chave = openrouter_api.criar_chave("gestao-123", "jarvis-teste", abrir=abrir)

    assert chave == CHAVE
    pedido = abrir.pedidos[0]
    assert pedido.full_url == "https://openrouter.ai/api/v1/keys"
    assert pedido.get_method() == "POST"
    assert pedido.get_header("Authorization") == "Bearer gestao-123"
    corpo = json.loads(pedido.data.decode())
    assert corpo == {"name": "jarvis-teste"}
    assert "limit" not in corpo and "expires_at" not in corpo


def test_limite_e_validade_entram_quando_pedidos():
    abrir = _abrir_de(Resposta({"key": CHAVE}))
    openrouter_api.criar_chave(
        "g", "n", limite=10.0, expira_em="2026-12-31T00:00:00Z", abrir=abrir
    )
    corpo = json.loads(abrir.pedidos[0].data.decode())
    assert corpo["limit"] == 10.0
    assert corpo["expires_at"] == "2026-12-31T00:00:00Z"


def test_o_endereco_base_pode_ser_trocado_para_teste():
    abrir = _abrir_de(Resposta({"key": CHAVE}))
    openrouter_api.criar_chave("g", "n", base="http://127.0.0.1:9/api/v1", abrir=abrir)
    assert abrir.pedidos[0].full_url == "http://127.0.0.1:9/api/v1/keys"


# ---------------------------------------------------------------------------
# A resposta
# ---------------------------------------------------------------------------

def test_resposta_sem_chave_e_erro_e_nao_um_env_vazio():
    abrir = _abrir_de(Resposta({"data": {"name": "x"}}))
    with pytest.raises(openrouter_api.OpenRouterError) as erro:
        openrouter_api.criar_chave("g", "x", abrir=abrir)
    assert "sem a chave" in str(erro.value)


def test_resposta_que_nao_e_json_e_erro_com_explicacao():
    abrir = _abrir_de(Resposta("<html>manutenção</html>"))
    with pytest.raises(openrouter_api.OpenRouterError) as erro:
        openrouter_api.criar_chave("g", "x", abrir=abrir)
    assert "não é JSON" in str(erro.value)


# ---------------------------------------------------------------------------
# Os erros, em português e com o que fazer
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("codigo", "trecho"),
    [
        (401, "não aceitou essa chave de gestão"),
        (403, "não pode criar outras chaves"),
        (429, "esperar um pouco"),
        (503, "problema no servidor"),
    ],
)
def test_o_codigo_do_site_vira_frase_com_o_proximo_passo(codigo, trecho):
    abrir = _abrir_de(_erro(codigo, {"error": {"message": "detalhe do site"}}))
    with pytest.raises(openrouter_api.OpenRouterError) as erro:
        openrouter_api.criar_chave("g", "x", abrir=abrir)
    assert trecho in str(erro.value)


def test_a_mensagem_do_site_entra_no_erro_sem_substituir_a_explicacao():
    abrir = _abrir_de(_erro(400, {"error": {"message": "name is required"}}))
    with pytest.raises(openrouter_api.OpenRouterError) as erro:
        openrouter_api.criar_chave("g", "", abrir=abrir)
    assert "name is required" in str(erro.value)


def test_sem_internet_o_erro_diz_para_conferir_a_internet():
    erro = urllib.error.URLError("getaddrinfo failed")
    abrir = _abrir_de(erro)
    with pytest.raises(openrouter_api.OpenRouterError) as capturado:
        openrouter_api.criar_chave("g", "x", abrir=abrir)
    assert "internet" in str(capturado.value)


# ---------------------------------------------------------------------------
# A chave de gestão vale?
# ---------------------------------------------------------------------------

def test_uma_chave_comum_copiada_por_engano_e_recusada_com_a_explicacao():
    """A chave comum só dá 403 na criação. Antes de gravar, a lista já denuncia."""
    abrir = _abrir_de(_erro(403, {"error": {"message": "insufficient permissions"}}))
    ok, motivo = openrouter_api.chave_de_gestao_vale(CHAVE, abrir=abrir)
    assert ok is False
    assert "não pode criar outras chaves" in motivo


def test_a_chave_de_gestao_boa_passa_e_a_lista_e_lida():
    abrir = _abrir_de(Resposta({"data": [{"name": "jarvis"}, {"name": "outra"}]}))
    ok, motivo = openrouter_api.chave_de_gestao_vale("gestao", abrir=abrir)
    assert ok is True and motivo == ""
    assert abrir.pedidos[0].get_method() == "GET"
    assert abrir.pedidos[0].full_url.endswith("/api/v1/keys")
    assert openrouter_api.listar_chaves("gestao", abrir=abrir) == [{"name": "jarvis"}, {"name": "outra"}]


# ---------------------------------------------------------------------------
# O comando do JARVIS que usa isso
# ---------------------------------------------------------------------------

def _script():
    spec = importlib.util.spec_from_file_location("chave_no_navegador_api", RAIZ / "chave-no-navegador.py")
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modulo)
    return modulo


def _configurador_falso(tmp_path: Path, linhas: dict[str, str]):
    """Um configurador mínimo, com `.env` de verdade no disco."""
    env = tmp_path / ".env"
    env.write_bytes(
        "\r\n".join(f"{nome}={valor}" for nome, valor in linhas.items()).encode() + b"\r\n"
    )
    import re

    modulo = types.SimpleNamespace(
        ENV=env,
        CHAVE="JARVIS_AI_API_KEY",
        texto_base=lambda: "",
        ler_texto=lambda caminho: Path(caminho).read_text(encoding="utf-8"),
        gravar=lambda texto: env.write_bytes(texto.replace("\n", "\r\n").encode()),
        mascarar=lambda chave: (chave[:6] + "…" + chave[-4:]) if chave else "",
        ler_valor=lambda texto, nome: (
            (m.group(1).strip() if (m := re.search(rf"(?m)^\s*{re.escape(nome)}\s*=(.*)$", texto)) else None)
        ),
        definir=lambda texto, nome, valor: texto.rstrip("\r\n") + f"\r\n{nome}={valor}\r\n",
    )
    return modulo, env


def _args(**extra):
    base = {"nome": "", "autorizar": True, "espera_colar": 0.3}
    base.update(extra)
    return types.SimpleNamespace(**base)


def test_sem_a_chave_de_gestao_o_comando_ensina_onde_pegar(monkeypatch, tmp_path, capsys):
    script = _script()
    modulo, env = _configurador_falso(tmp_path, {"JARVIS_AI_PROVIDER": "OpenRouter"})
    monkeypatch.setattr(script, "_modulo_do_configurador", lambda: modulo)

    codigo = script.passo_api(_args())
    texto = capsys.readouterr().out

    assert codigo == 1
    assert "chave-pela-api.bat" in texto
    assert "JARVIS_AI_API_KEY" not in env.read_text()


def test_com_a_chave_de_gestao_a_chave_nova_e_criada_e_gravada(monkeypatch, tmp_path, capsys):
    script = _script()
    modulo, env = _configurador_falso(
        tmp_path,
        {"JARVIS_AI_PROVIDER": "OpenRouter", "JARVIS_OPENROUTER_GESTAO": "gestao-abc"},
    )
    monkeypatch.setattr(script, "_modulo_do_configurador", lambda: modulo)
    monkeypatch.setattr(script, "_avisar_jarvis_aberto", lambda: False, raising=False)
    pedidos = []

    def criar(gestao, nome):
        pedidos.append((gestao, nome))
        return CHAVE

    from server import openrouter_api as api

    monkeypatch.setattr(api, "criar_chave", criar)

    codigo = script.passo_api(_args(nome="jarvis-teste"))
    salvo = env.read_text(encoding="utf-8")

    assert codigo == 0, capsys.readouterr().out
    assert pedidos == [("gestao-abc", "jarvis-teste")]
    assert f"JARVIS_AI_API_KEY={CHAVE}" in salvo
    assert "JARVIS_OPENROUTER_GESTAO=gestao-abc" in salvo, "as outras linhas não podem sumir"


def test_sem_autorizar_o_comando_da_api_nao_cria_nada(monkeypatch, tmp_path, capsys):
    script = _script()
    modulo, _env = _configurador_falso(
        tmp_path, {"JARVIS_OPENROUTER_GESTAO": "gestao-abc"}
    )
    monkeypatch.setattr(script, "_modulo_do_configurador", lambda: modulo)

    from server import openrouter_api as api

    def explodir(*_a, **_k):
        raise AssertionError("criou sem autorização")

    monkeypatch.setattr(api, "criar_chave", explodir)

    assert script.passo_api(_args(authorize=False, autorizar=False)) == 1
    assert "Sem --autorizar" in capsys.readouterr().out


def test_a_chave_de_gestao_e_conferida_antes_de_ser_guardada(monkeypatch, tmp_path, capsys):
    """Chave comum copiada por engano não pode ir para o `.env` como de gestão."""
    script = _script()
    modulo, env = _configurador_falso(tmp_path, {"JARVIS_AI_PROVIDER": "OpenRouter"})
    monkeypatch.setattr(script, "_modulo_do_configurador", lambda: modulo)
    monkeypatch.setattr(script, "_texto_da_area", lambda: f"copiei: {CHAVE}")
    monkeypatch.setattr(script, "_esperar_chave", lambda *_a, **_k: ("", CHAVE))

    from server import openrouter_api as api

    monkeypatch.setattr(api, "chave_de_gestao_vale", lambda _c: (False, "é uma chave comum"))

    codigo = script.passo_gestao(_args())
    texto = capsys.readouterr().out

    assert codigo == 1
    assert "chave comum" in texto
    assert "JARVIS_OPENROUTER_GESTAO" not in env.read_text(encoding="utf-8")


def test_a_chave_de_gestao_boa_e_guardada_e_o_resto_do_env_fica(monkeypatch, tmp_path):
    script = _script()
    modulo, env = _configurador_falso(
        tmp_path, {"JARVIS_AI_PROVIDER": "OpenRouter", "JARVIS_AI_MODEL": "x/y"}
    )
    monkeypatch.setattr(script, "_modulo_do_configurador", lambda: modulo)
    monkeypatch.setattr(script, "_texto_da_area", lambda: "")
    monkeypatch.setattr(script, "_esperar_chave", lambda *_a, **_k: ("", "gestao-boa"))

    from server import openrouter_api as api

    monkeypatch.setattr(api, "chave_de_gestao_vale", lambda _c: (True, ""))

    assert script.passo_gestao(_args()) == 0
    salvo = env.read_text(encoding="utf-8")
    assert "JARVIS_OPENROUTER_GESTAO=gestao-boa" in salvo
    assert "JARVIS_AI_MODEL=x/y" in salvo


def test_a_chave_de_gestao_que_ja_esta_guardada_nao_e_pedida_de_novo(monkeypatch, tmp_path, capsys):
    script = _script()
    modulo, _env = _configurador_falso(tmp_path, {"JARVIS_OPENROUTER_GESTAO": "gestao-boa"})
    monkeypatch.setattr(script, "_modulo_do_configurador", lambda: modulo)
    monkeypatch.setattr(script, "_esperar_chave", lambda *_a, **_k: pytest.fail("pediu de novo"))

    assert script.passo_gestao(_args()) == 0
    assert "já está guardada" in capsys.readouterr().out




# ---------------------------------------------------------------------------
# Os atalhos (0.91.29)
# ---------------------------------------------------------------------------
# Dois atalhos novos, e o que eles prometem é verificável no texto deles: o da
# API não abre o chrome.exe; o do protocolo confere a porta **antes** de abrir
# o Chrome, para não recarregar a página lenta de novo.

def _bat(nome: str) -> str:
    return (RAIZ / nome).read_text(encoding="ascii")


@pytest.mark.parametrize("nome", ["chave-pela-api.bat", "chrome-cdp.bat"])
def test_todo_goto_dos_atalhos_tem_rotulo(nome):
    import re

    texto = _bat(nome)
    rotulos = set(re.findall(r"^:([A-Za-z_][\w]*)", texto, flags=re.MULTILINE))
    destinos = set(re.findall(r"goto\s+([A-Za-z_][\w]*)", texto, flags=re.IGNORECASE))
    assert destinos - rotulos == set(), f"goto sem rótulo em {nome}: {sorted(destinos - rotulos)}"


def test_o_atalho_da_api_nao_abre_o_chrome_do_jarvis():
    """Ele pede a chave por HTTPS. Abrir o `chrome.exe` aqui seria voltar ao problema."""
    texto = _bat("chave-pela-api.bat").lower()
    assert "chrome.exe" not in texto
    assert "--cdp" not in texto
    assert "--api --autorizar" in texto


def test_o_chrome_cdp_confere_a_porta_antes_de_abrir_o_chrome():
    """Janela já aberta = não abrir outra nem recarregar a página (0.91.29)."""
    texto = _bat("chrome-cdp.bat")
    assert "call :testa_porta" in texto
    assert texto.index("call :testa_porta") < texto.index('start "" "%CHROME%"')
    assert ":ja_aberto" in texto


def test_o_chrome_cdp_abre_o_chrome_sem_trabalho_de_fundo():
    """As opções que tiram sincronização, extensões e pedidos de segundo plano."""
    texto = _bat("chrome-cdp.bat")
    for opcao in ("--disable-sync", "--disable-extensions", "--disable-background-networking"):
        assert opcao in texto, f"falta {opcao}"


# ---------------------------------------------------------------------------
# O perfil do Chrome do JARVIS não é do projeto (0.91.29)
# ---------------------------------------------------------------------------

def test_o_perfil_do_chrome_do_jarvis_fica_fora_do_atualizador():
    """Milhares de arquivos e dados de login não podem entrar no manifesto.

    O `chrome-cdp.bat` cria a pasta `perfil-cdp` ao lado do programa. Se ela
    entrasse no manifesto, toda atualização tentaria baixar (e sobrescrever) o
    perfil do dono — e o zip ficaria com centenas de MB.
    """
    from server import atualizacao

    assert atualizacao.gerenciado(Path("perfil-cdp/Default/Cookies")) is False
    assert atualizacao.gerenciado(Path("perfil-cdp/Local State")) is False
    assert atualizacao.gerenciado(Path("chave-no-navegador.py")) is True
    assert "perfil-cdp/" in (RAIZ / ".gitignore").read_text(encoding="utf-8")
