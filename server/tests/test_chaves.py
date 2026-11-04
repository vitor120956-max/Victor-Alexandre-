"""Chaves pela tela: colar, guardar, testar e apagar — sem passar pelo `cmd`.

O que estes testes protegem, em uma frase cada:

- o texto que o dono colou de verdade (`api grok 1 gsk_…`) é aceito, e o rótulo
  não vira chave;
- a chave **nunca** volta numa resposta — nem em erro, nem em lista;
- sem chave colada, nada é gravado, e a mensagem diz o que faltava;
- quem chega de outra máquina lê o estado e **não** escreve;
- o resto do `.env` sobrevive à gravação, em CRLF e sem BOM.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import chaves
from server.app import create_app
from server.skill_registry import build_registry

# O bloco exato que o dono colou no prompt e recebeu "não é reconhecido".
COLADO = (
    "api grok 1 gsk_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\n"
    "api groq 2 gsk_BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB\n"
    "api cerebro 3 gsk_CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC\n"
    "api cerebro 4 gsk_DDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDDD\n"
)
CHAVES = [linha.rsplit(" ", 1)[1] for linha in COLADO.splitlines()]


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    caminho = tmp_path / ".env"
    caminho.write_bytes(
        b"# comentario do dono\r\n"
        b"JARVIS_DONO=1\r\n"
        b"JARVIS_AI_PROVIDER=OpenAI\r\n"
        b"JARVIS_AI_BASE_URL=https://api.openai.com/v1\r\n"
        b"JARVIS_AI_MODEL=gpt-4o-mini\r\n"
        b"JARVIS_AI_API_KEY=\r\n"
    )
    monkeypatch.setattr(chaves, "ENV_CAMINHO", caminho)
    for nome in chaves.CHAVES_IA:
        monkeypatch.delenv(nome, raising=False)
    return caminho


# ---------------------------------------------------------------------------
# Extração
# ---------------------------------------------------------------------------

def test_o_bloco_colado_no_prompt_vira_quatro_chaves():
    """O caso real: o dono colou as anotações no cmd e o Windows recusou."""
    achadas = chaves.chaves_do_texto(COLADO)
    assert achadas == CHAVES
    assert all(chave.startswith("gsk_") for chave in achadas)
    assert "api" not in "".join(achadas)


def test_so_a_chave_limpa_tambem_funciona():
    assert chaves.chaves_do_texto(CHAVES[0]) == [CHAVES[0]]
    assert chaves.chaves_do_texto(", ".join(CHAVES[:2])) == CHAVES[:2]


def test_texto_sem_chave_nao_inventa_nada():
    assert chaves.chaves_do_texto("api grok 1\ncomprar cafe\n") == []
    assert chaves.chaves_do_texto("") == []


def test_mascara_mostra_o_suficiente_e_nao_a_chave():
    mascarada = chaves.mascarar(CHAVES[0])
    assert CHAVES[0] not in mascarada
    assert mascarada.startswith("gsk_A")
    assert mascarada.endswith(f"({len(CHAVES[0])} caracteres)")


# ---------------------------------------------------------------------------
# Salvar
# ---------------------------------------------------------------------------

def test_salvar_grava_as_quatro_e_preenche_o_groq(env: Path):
    resultado = chaves.salvar(COLADO)
    assert resultado["quantidade"] == 4
    assert resultado["base"] == "https://api.groq.com/openai/v1"
    assert resultado["modelo"] == "llama-3.3-70b-versatile"
    bruto = env.read_bytes()
    assert not bruto.startswith(b"\xef\xbb\xbf")  # sem BOM
    assert bruto.count(b"\r\n") == bruto.count(b"\n")  # só CRLF
    linha = [l for l in bruto.split(b"\r\n") if l.startswith(b"JARVIS_AI_API_KEY=")][0]
    assert linha.count(b",") == 3


def test_salvar_preserva_o_resto_do_env(env: Path):
    chaves.salvar(COLADO)
    texto = env.read_text(encoding="utf-8")
    assert texto.startswith("# comentario do dono")
    assert "JARVIS_DONO=1" in texto
    assert texto.count("JARVIS_AI_API_KEY=") == 1


def test_salvar_aplica_no_ambiente_na_hora(env: Path, monkeypatch: pytest.MonkeyPatch):
    chaves.salvar(COLADO)
    import os

    assert len(os.environ["JARVIS_AI_API_KEY"].split(",")) == 4
    assert os.environ["JARVIS_AI_BASE_URL"] == "https://api.groq.com/openai/v1"


def test_salvar_acrescentar_mantem_as_antigas_sem_repetir(env: Path):
    chaves.salvar(CHAVES[0])
    resultado = chaves.salvar(COLADO, acrescentar=True)
    assert resultado["quantidade"] == 4
    # repetir a mesma lista não duplica nada
    de_novo = chaves.salvar(COLADO, acrescentar=True)
    assert de_novo["quantidade"] == 4


def test_salvar_sem_chave_recusa_e_nao_grava(env: Path):
    antes = env.read_bytes()
    with pytest.raises(ValueError, match="não encontrei nenhuma chave"):
        chaves.salvar("api grok 1\nsem chave aqui")
    assert env.read_bytes() == antes


def test_salvar_recusa_colagem_gigante(env: Path):
    with pytest.raises(ValueError, match="grande demais"):
        chaves.salvar("gsk_" + "a" * 30_000)


def test_salvar_respeita_o_limite_de_chaves(env: Path):
    muitas = "\n".join(f"gsk_{i:02d}" + "a" * 30 for i in range(15))
    with pytest.raises(ValueError, match="limite"):
        chaves.salvar(muitas)


def test_salvar_nao_troca_de_provedor_quem_ja_escolheu_outro(env: Path):
    """OpenRouter configurado de propósito não pode virar Groq por engano."""
    env.write_bytes(
        b"JARVIS_AI_PROVIDER=OpenRouter\r\n"
        b"JARVIS_AI_BASE_URL=https://openrouter.ai/api/v1\r\n"
        b"JARVIS_AI_MODEL=nvidia/nemotron-3-super:free\r\n"
        b"JARVIS_AI_API_KEY=\r\n"
    )
    chaves.salvar("sk-or-v1-" + "z" * 40)
    estado = chaves.estado()
    assert estado["base"] == "https://openrouter.ai/api/v1"
    assert estado["modelo"] == "nvidia/nemotron-3-super:free"


# ---------------------------------------------------------------------------
# Apagar e estado
# ---------------------------------------------------------------------------

def test_apagar_some_com_as_chaves_e_mantem_o_endereco(env: Path):
    chaves.salvar(COLADO)
    resultado = chaves.apagar()
    assert resultado["quantidade"] == 0
    assert resultado["base"] == "https://api.groq.com/openai/v1"
    assert b"JARVIS_AI_API_KEY=\r\n" in env.read_bytes()


def test_estado_nao_devolve_a_chave(env: Path):
    chaves.salvar(COLADO)
    texto = json.dumps(chaves.estado(), ensure_ascii=False)
    for chave in CHAVES:
        assert chave not in texto
    assert "4" in texto  # a quantidade sim


def test_estado_de_projeto_sem_env_cai_no_exemplo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(chaves, "ENV_CAMINHO", tmp_path / "nao-existe.env")
    monkeypatch.setattr(chaves.dados_locais, "PROJETO", tmp_path)
    (tmp_path / ".env.example").write_text("JARVIS_AI_API_KEY=\n", encoding="utf-8")
    assert chaves.estado()["quantidade"] == 0


# ---------------------------------------------------------------------------
# Testar (sem sair da máquina)
# ---------------------------------------------------------------------------

def test_testar_uma_chave_responde_e_nao_mostra_o_valor(env: Path):
    chaves.salvar(COLADO)
    calls = []

    def postar(url, corpo, cabecalho):
        calls.append(cabecalho["Authorization"])
        return 200

    resultado = chaves.testar(postar=postar)
    assert resultado["boas"] == 4 and resultado["total"] == 4
    assert "As 4 chaves responderam." == resultado["resumo"]
    assert len(calls) == 4
    assert CHAVES[0] not in json.dumps(resultado, ensure_ascii=False)


def test_testar_conta_so_as_que_respondem(env: Path):
    chaves.salvar(COLADO)
    respostas = {CHAVES[0]: 200, CHAVES[1]: 429, CHAVES[2]: 401, CHAVES[3]: 200}

    def postar(_url, _corpo, cabecalho):
        return respostas[cabecalho["Authorization"].removeprefix("Bearer ")]

    resultado = chaves.testar(postar=postar)
    assert resultado["boas"] == 2
    assert resultado["resultados"][1]["codigo"] == 429
    assert "cota" in resultado["resultados"][1]["motivo"]
    assert "2 de 4" in resultado["resumo"]


def test_testar_uma_so_por_indice(env: Path):
    chaves.salvar(COLADO)
    resultado = chaves.testar(indice=2, postar=lambda *_a: 200)
    assert resultado["total"] == 1
    assert resultado["resultados"][0]["indice"] == 2


def test_testar_indice_que_nao_existe_explica(env: Path):
    chaves.salvar(COLADO)
    with pytest.raises(ValueError, match="não existe chave 9"):
        chaves.testar(indice=9, postar=lambda *_a: 200)


def test_testar_sem_chave_guardada_recusa(env: Path):
    with pytest.raises(ValueError, match="não há chave"):
        chaves.testar(postar=lambda *_a: 200)


def test_testar_falha_de_rede_vira_motivo_em_portugues(env: Path):
    chaves.salvar(COLADO)

    def postar(*_a):
        raise OSError("sem rota")

    resultado = chaves.testar(indice=1, postar=postar)
    assert resultado["boas"] == 0
    assert "conexão" in resultado["resultados"][0]["motivo"]


# ---------------------------------------------------------------------------
# Pela API
# ---------------------------------------------------------------------------

def _cliente(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env: Path) -> TestClient:
    monkeypatch.setenv("JARVIS_DADOS", str(tmp_path / "dados"))
    return TestClient(create_app(registry=build_registry(tmp_path / "files")))


def test_api_le_o_estado_e_deixa_editar_da_propria_maquina(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env: Path):
    cliente = _cliente(tmp_path, monkeypatch, env)
    with cliente:
        corpo = cliente.get("/api/ai/chaves").json()
    assert corpo["ok"] is True
    assert corpo["quantidade"] == 0
    assert corpo["podeEditar"] is True


def test_api_salva_e_o_status_ja_reflete_as_chaves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env: Path):
    cliente = _cliente(tmp_path, monkeypatch, env)
    with cliente:
        resposta = cliente.post("/api/ai/chaves", json={"texto": COLADO})
        status = cliente.get("/api/ai/status").json()
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["ok"] is True
    assert corpo["result"]["quantidade"] == 4
    # o provedor em memória já enxerga as quatro, sem reiniciar
    assert status["configured"] is True
    assert status["keys"] == 4
    assert status["provider"] == "Groq"
    assert all(chave not in resposta.text for chave in CHAVES)


def test_api_recusa_texto_sem_chave_com_400(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env: Path):
    cliente = _cliente(tmp_path, monkeypatch, env)
    with cliente:
        resposta = cliente.post("/api/ai/chaves", json={"texto": "api grok 1 nada"})
    assert resposta.status_code == 400
    assert resposta.json()["error"]["code"] == "CHAVE_INVALIDA"
    assert "gsk_" in resposta.json()["error"]["message"]


def test_api_apaga(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env: Path):
    cliente = _cliente(tmp_path, monkeypatch, env)
    with cliente:
        cliente.post("/api/ai/chaves", json={"texto": COLADO})
        resposta = cliente.delete("/api/ai/chaves")
        status = cliente.get("/api/ai/status").json()
    assert resposta.status_code == 200
    assert resposta.json()["result"]["quantidade"] == 0
    assert status["configured"] is False


def test_api_testar_usa_a_funcao_injetada(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env: Path):
    chaves.salvar(COLADO)
    monkeypatch.setattr(chaves, "testar", lambda indice=None: {"ok": True, "boas": 1, "total": 1, "resultados": [], "resumo": "ok"})
    cliente = _cliente(tmp_path, monkeypatch, env)
    with cliente:
        resposta = cliente.post("/api/ai/chaves/testar", json={})
    assert resposta.status_code == 200
    assert resposta.json()["result"]["boas"] == 1


def test_api_nao_grava_pedido_de_outra_maquina(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env: Path):
    """Celular na rede local lê o estado, mas não troca a chave do dono."""
    cliente = _cliente(tmp_path, monkeypatch, env)
    with cliente:
        monkeypatch.setattr("server.app._veio_da_propria_maquina", lambda _request: False)
        resposta = cliente.post("/api/ai/chaves", json={"texto": COLADO})
    assert resposta.status_code == 403
    assert env.read_bytes().count(b"gsk_") == 0


def test_api_recusa_origem_de_fora(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env: Path):
    cliente = _cliente(tmp_path, monkeypatch, env)
    with cliente:
        resposta = cliente.post(
            "/api/ai/chaves",
            json={"texto": COLADO},
            headers={"origin": "https://site-malicioso.example"},
        )
    assert resposta.status_code == 403


def test_api_nao_devolve_a_chave_em_nenhuma_resposta(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env: Path):
    cliente = _cliente(tmp_path, monkeypatch, env)
    with cliente:
        textos = [
            cliente.get("/api/ai/chaves").text,
            cliente.post("/api/ai/chaves", json={"texto": COLADO}).text,
            cliente.get("/api/ai/chaves").text,
            cliente.get("/api/ai/status").text,
        ]
    for texto in textos:
        for chave in CHAVES:
            assert chave not in texto


def test_extrair_e_igual_ao_script_do_terminal():
    """Duas cópias da mesma regra divergem em silêncio — este teste é o alarme.

    `configurar-chave.py` roda sozinho (sem importar o servidor) e por isso tem
    a própria extração. Se uma ganhar um padrão novo e a outra não, o mesmo texto
    colado daria resultados diferentes na tela e no terminal.
    """
    import importlib.util

    from pathlib import Path as _Path

    caminho = _Path(__file__).resolve().parents[2] / "configurar-chave.py"
    spec = importlib.util.spec_from_file_location("cc_para_comparar", caminho)
    assert spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)

    amostras = [
        COLADO,
        "gsk_" + "a" * 40,
        "openai sk-abcdefghijklmnopqrstuvwxyz0123",
        "openrouter sk-or-v1-abcdefghijklmnopqrstuvwxyz",
        "google AIzaSyABCDEFGHIJKLMNOPQRSTUVWXYZ0123456",
        "texto qualquer, sem chave",
        "",
    ]
    for amostra in amostras:
        assert chaves.chaves_do_texto(amostra) == modulo.chaves_do_texto(amostra), amostra[:40]


# ------------------------------------------------------- a tela tem de existir

def test_a_tela_de_configuracoes_tem_o_cartao_e_nao_mente_a_versao():
    """Guarda de tela: o cartão precisa estar lá, e a versão não pode ser fixa.

    O cartão "Chaves de IA" existe desde a 0.77.0 — quem está em versão anterior
    abre Configurações e não encontra nada, o que já aconteceu. E o rodapé dizia
    `VERSÃO 0.5.0` fixo desde sempre: era impossível saber que versão estava
    rodando, e foi por isso que a ausência do cartão virou dúvida.
    """
    import re

    from pathlib import Path as _Path

    texto = (_Path(__file__).resolve().parents[2] / "src" / "pages" / "SettingsPage.tsx").read_text(encoding="utf-8")
    assert "Chaves de IA" in texto, "o cartão de chaves sumiu da tela"
    assert "Colar chaves" in texto
    assert "getChavesIA" in texto
    # Nenhum número de versão escrito à mão: vem do /api/health (backendVersion).
    assert re.search(r"<strong>\d+\.\d+\.\d+</strong>", texto) is None, "versão fixa voltou ao rodapé"
    assert "backendVersion" in texto
