"""Escolher um modelo que existe — e que responde (0.91.31).

O defeito que estes testes reproduzem, com o console do dono de 17/11:

    modelo: deepseek/deepseek-chat-v3-0324:free
    NÃO  o modelo … NÃO está na lista.
    Use um destes:
      deepseek/deepseek-chat-v3-0324      ← pago
      deepseek/deepseek-chat-v3.1         ← pago
      deepseek/deepseek-chat              ← pago

O `difflib` escolhia pelo nome mais parecido, e o mais parecido era o **pago**.
Numa conta gratuita isso troca um 404 por um 402 — o erro muda de lugar e o
dono não anda.

Aqui se prova três coisas:

1. a escolha (`escolha_modelo`) prefere grátis, ignora ferramenta e não aceita
   o modelo que já falhou;
2. o comando `conferir-ia.py --corrigir` **testa antes de gravar** e grava só a
   linha do modelo, com backup;
3. quando nenhum candidato responde, o `.env` **não** é tocado.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from server import chaves, escolha_modelo

RAIZ = Path(__file__).resolve().parents[2]

# A lista real que o dono viu (17/11), com os pagos que o `difflib` sugeria e
# duas ferramentas que nunca servem para conversar.
LISTA_DO_DONO = [
    "deepseek/deepseek-chat-v3-0324",
    "deepseek/deepseek-chat-v3.1",
    "deepseek/deepseek-chat",
    "baidu/ernie-5.5-flash-preview:free",
    "cohere/north-mini-code:free",
    "dots-studio/dots-3-note-preview:free",
    "google/gemma-4-26b-a4b-it:free",
    "google/gemma-4-31b-it:free",
    "inclusionai/ling-3.2-flash:free",
    "liquid/lfm-3-1.7b:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3.5-lightning:free",
    "qwen/qwen3-32b:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "openai/text-embedding-3-small",
    "openai/whisper-large-v3",
]

MORTO = "deepseek/deepseek-chat-v3-0324:free"


def _conferir_ia():
    spec = importlib.util.spec_from_file_location("conferir_ia_031", RAIZ / "conferir-ia.py")
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modulo)
    return modulo


# ---------------------------------------------------------------------------
# A escolha
# ---------------------------------------------------------------------------

def test_o_escolhido_e_gratuito_mesmo_com_pago_muito_mais_parecido():
    """O erro de 17/11: os três “parecidos” eram pagos."""
    escolhidos = escolha_modelo.sugestoes(LISTA_DO_DONO, MORTO)
    assert escolhidos, "tinha de sugerir alguma coisa"
    assert all(nome.endswith(":free") for nome in escolhidos), escolhidos
    assert "deepseek/deepseek-chat-v3-0324" not in escolhidos


def test_ferramenta_nunca_e_sugerida_para_conversar():
    """Embedding e transcrição respondem 400 num chat — não são modelo de conversa."""
    escolhidos = escolha_modelo.candidatos(LISTA_DO_DONO, limite=50)
    assert "openai/text-embedding-3-small" not in escolhidos
    assert "openai/whisper-large-v3" not in escolhidos
    assert escolha_modelo.serve_para_conversar("openai/whisper-large-v3") is False
    assert escolha_modelo.serve_para_conversar("meta-llama/llama-3.3-70b-instruct:free") is True


def test_conta_paga_pode_usar_modelo_pago():
    """Sem a restrição de conta grátis, o pago entra na frente? Não: grátis continua primeiro."""
    escolhidos = escolha_modelo.sugestoes(LISTA_DO_DONO, MORTO, so_gratis=False)
    assert escolhidos[0].endswith(":free"), "grátis primeiro é a regra, não um caso"


def test_sem_nenhum_gratuito_a_lista_cai_para_os_pagos_sem_mentir():
    pagos = ["deepseek/deepseek-chat-v3-0324", "qwen/qwen3-32b"]
    assert escolha_modelo.sugestoes(pagos, MORTO, so_gratis=True) == []
    assert escolha_modelo.sugestoes(pagos, MORTO, so_gratis=False)


def test_o_modelo_que_falhou_nao_volta_como_candidato():
    escolhidos = escolha_modelo.candidatos(LISTA_DO_DONO, limite=50, atual="qwen/qwen3-32b:free")
    assert "qwen/qwen3-32b:free" not in escolhidos


def test_modelo_pequeno_demais_fica_atras_de_um_de_verdade():
    """1.7b erra demais em português; o JARVIS tem de preferir 8b para cima."""
    lista = ["liquid/lfm-3-1.7b:free", "meta-llama/llama-3.3-70b-instruct:free"]
    assert escolha_modelo.candidatos(lista)[0] == "meta-llama/llama-3.3-70b-instruct:free"


def test_a_escolha_e_a_mesma_toda_vez():
    """A mesma lista tem de dar a mesma escolha — nada de sorteio."""
    primeira = escolha_modelo.candidatos(LISTA_DO_DONO, limite=3)
    segunda = escolha_modelo.candidatos(list(LISTA_DO_DONO), limite=3)
    assert primeira == segunda


def test_os_bilhoes_do_nome_sao_lidos_direito():
    assert escolha_modelo.parametros("meta-llama/llama-3.3-70b-instruct:free") == 70
    assert escolha_modelo.parametros("liquid/lfm-3-1.7b:free") == 1.7
    assert escolha_modelo.parametros("deepseek/deepseek-chat") == 0


# ---------------------------------------------------------------------------
# O comando: testar antes de gravar
# ---------------------------------------------------------------------------

@pytest.fixture
def env_falso(monkeypatch, tmp_path):
    """Um `.env` de verdade no disco, do jeito que o dono tem."""
    caminho = tmp_path / ".env"
    caminho.write_bytes(
        b"JARVIS_AI_PROVIDER=OpenRouter\r\n"
        b"JARVIS_AI_BASE_URL=https://openrouter.ai/api/v1\r\n"
        b"JARVIS_AI_MODEL=" + MORTO.encode() + b"\r\n"
        b"JARVIS_AI_API_KEY=sk-or-v1-" + b"a" * 64 + b"\r\n"
        b"JARVIS_OPENROUTER_GESTAO=sk-or-v1-" + b"b" * 64 + b"\r\n"
    )
    monkeypatch.setattr(chaves, "ENV_CAMINHO", caminho)
    return caminho


def _preparar(monkeypatch, respostas: dict[str, bool], disponiveis=None, gratis=False):
    """Monta o comando com provedor falso: a lista vem de um lado, o teste de outro."""
    from server import provedores

    modulo = _conferir_ia()
    lista = disponiveis if disponiveis is not None else LISTA_DO_DONO
    monkeypatch.setattr(
        provedores,
        "listar_modelos",
        lambda **_k: {"modelos": [{"id": nome} for nome in lista], "total": len(lista)},
    )
    monkeypatch.setattr(modulo, "_conta_gratuita", lambda _base: gratis)
    testados: list[str] = []

    def testar_modelo(nome, **_k):
        testados.append(nome)
        ok = respostas.get(nome, False)
        return {"modelo": nome, "ok": ok, "codigo": 200 if ok else 404, "motivo": "" if ok else "não existe"}

    monkeypatch.setattr(chaves, "testar_modelo", testar_modelo)
    return modulo, testados


def test_o_comando_testa_e_grava_o_primeiro_que_responde(monkeypatch, env_falso, capsys):
    escolhido = "meta-llama/llama-3.3-70b-instruct:free"
    modulo, testados = _preparar(monkeypatch, {escolhido: True})

    codigo = modulo.main(["--corrigir"])
    texto = capsys.readouterr().out
    salvo = env_falso.read_text(encoding="utf-8")

    assert codigo == 0, texto
    assert f"JARVIS_AI_MODEL={escolhido}" in salvo
    # só a linha do modelo mudou
    assert "JARVIS_OPENROUTER_GESTAO=sk-or-v1-" in salvo
    assert "JARVIS_AI_PROVIDER=OpenRouter" in salvo
    assert "Gravei JARVIS_AI_MODEL=" in texto
    assert testados[0] == escolhido


def test_se_o_primeiro_nao_responde_o_segundo_e_testado(monkeypatch, env_falso, capsys):
    """Escolher não é provar: o primeiro pode dar 404 mesmo estando na lista."""
    primeiro, segundo = (
        "meta-llama/llama-3.3-70b-instruct:free",
        "qwen/qwen3-32b:free",
    )
    modulo, testados = _preparar(monkeypatch, {segundo: True})

    assert modulo.main(["--corrigir"]) == 0
    assert testados[:2] == [primeiro, segundo]
    assert f"JARVIS_AI_MODEL={segundo}" in env_falso.read_text(encoding="utf-8")


def test_antes_de_mexer_o_env_tem_backup(monkeypatch, env_falso, capsys):
    """O dono pediu backup antes — e backup de verdade é arquivo com o conteúdo antigo."""
    escolhido = "meta-llama/llama-3.3-70b-instruct:free"
    modulo, _ = _preparar(monkeypatch, {escolhido: True})

    modulo.main(["--corrigir"])
    capsys.readouterr()

    copias = sorted(env_falso.parent.glob(".env.antes-*"))
    assert copias, "nenhum backup foi criado"
    assert MORTO in copias[-1].read_text(encoding="utf-8")


def test_se_nenhum_candidato_responde_o_env_fica_como_estava(monkeypatch, env_falso, capsys):
    antes = env_falso.read_bytes()
    modulo, _ = _preparar(monkeypatch, {})

    codigo = modulo.main(["--corrigir"])
    texto = capsys.readouterr().out

    assert codigo == 1
    assert env_falso.read_bytes() == antes, "nada pode ser gravado sem prova"
    assert "Nenhum dos testados respondeu" in texto


def test_com_o_modelo_bom_nada_e_testado_nem_gravado(monkeypatch, env_falso, capsys):
    bom = "meta-llama/llama-3.3-70b-instruct:free"
    env_falso.write_bytes(
        env_falso.read_bytes().replace(MORTO.encode(), bom.encode())
    )
    modulo, testados = _preparar(monkeypatch, {bom: True})

    assert modulo.main(["--corrigir"]) == 0
    assert "está na lista" in capsys.readouterr().out
    assert testados == [], "com o modelo certo não há o que testar"


def test_conta_gratuita_nao_recebe_sugestao_de_modelo_pago(monkeypatch, env_falso, capsys):
    """O defeito de 17/11, ponta a ponta: a sugestão tem de ser :free."""
    modulo, _ = _preparar(monkeypatch, {}, gratis=True)

    modulo.main([])
    texto = capsys.readouterr().out

    assert "conta é gratuita" in texto
    for linha in texto.splitlines():
        if linha.strip().startswith("deepseek/deepseek-chat-v3-0324") and ":free" not in linha:
            pytest.fail(f"sugeriu modelo pago numa conta gratuita: {linha!r}")


# ---------------------------------------------------------------------------
# Opção que a cópia não conhece (0.91.32)
# ---------------------------------------------------------------------------

def test_opcao_desconhecida_explica_em_vez_de_errar_com_usage(capsys):
    """O console de 17/11: `--corrigir` numa cópia 0.91.29.

    A resposta foi `unrecognized arguments: --corrigi`, que não diz nada a quem
    não programa. Aqui a opção desconhecida vira uma frase com o próximo passo.
    """
    modulo = _conferir_ia()

    codigo = modulo.main(["--opcao-que-nao-existe"])
    texto = capsys.readouterr().out

    assert codigo == 2
    assert "--opcao-que-nao-existe" in texto
    assert "atualizar.bat" in texto
    assert "usage:" not in texto


def test_o_cabecalho_mostra_a_versao(monkeypatch, env_falso, capsys):
    """Sem a versão na tela, “a opção não existe” nunca é entendido."""
    modulo, _ = _preparar(monkeypatch, {})
    modulo.main([])
    saida = capsys.readouterr().out
    assert "JARVIS — conferir a IA (" in saida


def test_nome_que_esta_na_lista_mas_da_404_tambem_e_consertado(monkeypatch, env_falso, capsys):
    """A lista do provedor demora a tirar o morto; o teste é que é a prova."""
    presente = "meta-llama/llama-3.3-70b-instruct:free"
    env_falso.write_bytes(env_falso.read_bytes().replace(MORTO.encode(), presente.encode()))
    bom = "qwen/qwen3-32b:free"
    modulo, testados = _preparar(monkeypatch, {bom: True})

    # `chaves.testar()` (o do --testar) falha; `testar_modelo` só aprova o bom.
    monkeypatch.setattr(
        chaves,
        "testar",
        lambda **_k: {
            "ok": False,
            "resultados": [{"indice": 1, "ok": False, "codigo": 404, "motivo": "não existe"}],
        },
    )
    monkeypatch.setattr(chaves, "testar_modelo", lambda nome, **_k: (
        testados.append(nome) or
        {"modelo": nome, "ok": nome == bom, "codigo": 200 if nome == bom else 404, "motivo": ""}
    ))

    codigo = modulo.main(["--testar", "--corrigir"])
    texto = capsys.readouterr().out

    assert codigo == 0, texto
    assert "respondeu com a sua chave" in texto
    assert f"JARVIS_AI_MODEL={bom}" in env_falso.read_text(encoding="utf-8")
