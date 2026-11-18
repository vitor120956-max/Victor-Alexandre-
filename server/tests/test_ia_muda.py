"""O teste disse “OK” para um modelo que não fala (0.91.35).

O console do dono, em 17/11, com a 0.91.34 recém-instalada:

    TESTE DE VERDADE (8 tokens por chave)...
    OK   chave 1: HTTP 200
         motivo: respondeu com raciocínio em vez de texto
         o provedor disse: “o modelo pode gastar o limite pensando e não sobrar resposta”

    Pronto: provedor, modelo e chave estão coerentes.

Três linhas que se contradizem. A 0.91.33 fez `_testar_uma_detalhado` marcar
`sem_texto` e `testar_modelo` recusar — mas o `chaves.testar()`, que é o que o
`--testar` e o botão da tela usam, continuou aprovando pelo **código HTTP**.
Resultado: “OK” e “coerentes” para um modelo que devolve 200 sem uma palavra.

Estes testes são a régua:

1. `chaves.testar()` não aprova 200 mudo — nem pelo modelo principal, nem pelo
   modelo de socorro;
2. o resumo separa as duas coisas (“a chave está válida” / “o modelo não fala”)
   e manda para o comando que troca;
3. `conferir-ia.py --testar` não termina com “estão coerentes” nesse caso, e diz
   o comando que conserta;
4. `--corrigir` pula o mudo e **continua** procurando (eram 3 tentativas; os 3
   primeiros do dono eram dois 429 e um mudo, e o script parava ali).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from server import chaves

RAIZ = Path(__file__).resolve().parents[2]

# A resposta exata que o nemotron devolveu: 200, nada de `content`, o
# pensamento em `reasoning`.
CORPO_MUDO = {
    "choices": [
        {
            "message": {"content": "", "reasoning": "Pensando em como responder…"},
            "finish_reason": "length",
        }
    ]
}
CORPO_OK = {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}

MODELO_MUDO = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"
MODELO_BOM = "google/gemma-4-26b-a4b-it:free"


def _conferir_ia():
    spec = importlib.util.spec_from_file_location("conferir_ia_035", RAIZ / "conferir-ia.py")
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    caminho = tmp_path / ".env"
    caminho.write_bytes(
        b"JARVIS_AI_PROVIDER=OpenRouter\r\n"
        b"JARVIS_AI_BASE_URL=https://openrouter.ai/api/v1\r\n"
        b"JARVIS_AI_MODEL=" + MODELO_MUDO.encode() + b"\r\n"
        b"JARVIS_AI_API_KEY=sk-or-v1-" + b"a" * 64 + b"\r\n"
    )
    monkeypatch.setattr(chaves, "ENV_CAMINHO", caminho)
    return caminho


def _postar_mudo(_url, _corpo, _cabecalho):
    return {"codigo": 200, "corpo": CORPO_MUDO}


# ---------------------------------------------------------------------------
# O teste da chave (o que o `--testar` e o botão da tela usam)
# ---------------------------------------------------------------------------

def test_http_200_sem_texto_nao_e_aprovado_pelo_teste_da_chave(env: Path):
    """O defeito do print, no lugar exato onde ele nasceu."""
    resultado = chaves.testar(postar=_postar_mudo, modelo_socorro="")

    assert resultado["ok"] is False, "um 200 mudo voltou a ser aprovado"
    assert resultado["boas"] == 0
    item = resultado["resultados"][0]
    assert item["codigo"] == 200
    assert item["sem_texto"] is True
    assert "raciocínio" in item["motivo"]


def test_o_resumo_diz_que_a_chave_e_boa_e_o_modelo_nao_fala(env: Path):
    """A frase precisa separar chave de modelo — e mandar para o conserto."""
    resumo = chaves.testar(postar=_postar_mudo, modelo_socorro="")["resumo"]

    assert "chave está válida" in resumo
    assert "sem texto" in resumo or "não mandou texto" in resumo
    assert "conferir-ia.py --corrigir" in resumo
    assert "As 1 chaves responderam" not in resumo
    assert "O cérebro está de pé" not in resumo


def test_o_modelo_de_socorro_tambem_precisa_falar(env: Path):
    """429 no principal + 200 mudo no socorro não prova que a chave está boa."""
    chaves.salvar("sk-or-v1-" + "a" * 64)
    caminho = chaves.env_path()
    caminho.write_bytes(
        caminho.read_bytes()
        .replace(b"JARVIS_AI_BASE_URL=https://openrouter.ai/api/v1", b"JARVIS_AI_BASE_URL=https://api.groq.com/openai/v1")
        .replace(b"JARVIS_AI_MODEL=" + MODELO_MUDO.encode(), b"JARVIS_AI_MODEL=llama-3.3-70b-versatile")
    )

    def postar(_url, corpo, _cabecalho):
        if corpo["model"] == chaves.MODELO_DE_SOCORRO:
            return {"codigo": 200, "corpo": CORPO_MUDO}
        return {"codigo": 429, "corpo": {"error": {"message": "rate limit"}}}

    resultado = chaves.testar(postar=postar, modelo_socorro=chaves.MODELO_DE_SOCORRO)
    assert resultado["ok"] is False
    assert resultado["boas"] == 0
    assert "raciocínio em vez de texto" in resultado["resultados"][0]["detalhe"]


def test_200_com_texto_continua_aprovando(env: Path):
    """A régua não pode virar “nada passa”: texto de verdade aprova."""
    resultado = chaves.testar(
        postar=lambda *_a: {"codigo": 200, "corpo": CORPO_OK}, modelo_socorro=""
    )
    assert resultado["ok"] is True
    assert resultado["resumo"] == "A chave respondeu. O cérebro está de pé."


# ---------------------------------------------------------------------------
# O comando que o dono rodou
# ---------------------------------------------------------------------------

def _preparar(monkeypatch, monkeypatch_env: Path, respostas: dict, disponiveis=None, gratis=True):
    from server import provedores

    modulo = _conferir_ia()
    lista = disponiveis if disponiveis is not None else [
        MODELO_MUDO, MODELO_BOM,
        "google/gemma-4-31b-it:free",
        "inclusionai/ling-3.2-flash:free",
        "liquid/lfm-2.5-8b:free",
        "qwen/qwen3-32b:free",
    ]
    monkeypatch.setattr(
        provedores,
        "listar_modelos",
        lambda **_k: {"modelos": [{"id": nome} for nome in lista], "total": len(lista)},
    )
    monkeypatch.setattr(modulo, "_conta_gratuita", lambda _base: gratis)
    testados: list[str] = []

    def testar_modelo(nome, **_k):
        testados.append(nome)
        codigo, texto = respostas.get(nome, (404, False))
        motivo = "" if texto else ("respondeu com raciocínio em vez de texto" if codigo == 200 else "não existe")
        return {
            "modelo": nome,
            "ok": texto,
            "codigo": codigo,
            "motivo": motivo,
            "detalhe": "",
            "sem_texto": codigo == 200 and not texto,
        }

    monkeypatch.setattr(chaves, "testar_modelo", testar_modelo)
    # O teste da chave também é dublê: aqui ele devolve o veredito do print.
    monkeypatch.setattr(
        chaves,
        "testar",
        lambda **_k: {
            "ok": False,
            "boas": 0,
            "total": 1,
            "modelo": MODELO_MUDO,
            "resultados": [
                {
                    "indice": 1,
                    "ok": False,
                    "codigo": 200,
                    "motivo": "respondeu com raciocínio em vez de texto",
                    "detalhe": "",
                    "sem_texto": True,
                }
            ],
            "resumo": "",
        },
    )
    return modulo, testados


def test_o_comando_nao_diz_coerentes_quando_o_modelo_nao_fala(monkeypatch, env, capsys):
    """O console inteiro do dono, reproduzido: 200 mudo não é “tudo certo”."""
    modulo = _conferir_ia()
    monkeypatch.setattr(
        chaves,
        "testar",
        lambda **_k: {
            "ok": False,
            "boas": 0,
            "total": 1,
            "modelos": [],
            "modelo": MODELO_MUDO,
            "resultados": [
                {
                    "indice": 1,
                    "ok": False,
                    "codigo": 200,
                    "motivo": "respondeu com raciocínio em vez de texto",
                    "detalhe": "o modelo pode gastar o limite pensando e não sobrar resposta",
                    "sem_texto": True,
                    "modelo": MODELO_MUDO,
                }
            ],
            "resumo": "",
        },
    )
    monkeypatch.setattr(chaves, "estado", lambda: {
        "provedor_id": "openrouter",
        "base": "https://openrouter.ai/api/v1",
        "modelo": MODELO_MUDO,
        "quantidade": 1,
        "mascaradas": ["sk-or…ae3e (73 caracteres)"],
        "arquivo": str(env),
        "suspeitas": [],
    })
    from server import provedores

    monkeypatch.setattr(
        provedores,
        "listar_modelos",
        lambda **_k: {"modelos": [{"id": MODELO_MUDO}], "total": 1},
    )

    codigo = modulo.main(["--testar"])
    texto = capsys.readouterr().out

    assert codigo == 1, "o comando voltou dizendo que estava tudo bem"
    assert "coerentes" not in texto
    assert "NÃO é problema de chave" in texto
    assert "conferir-ia.py --corrigir" in texto


def test_o_comando_continua_dizendo_coerentes_quando_ha_texto(monkeypatch, env, capsys):
    """A frase certa não pode desaparecer: com texto, ela volta."""
    modulo = _conferir_ia()
    monkeypatch.setattr(
        chaves,
        "testar",
        lambda **_k: {
            "ok": True,
            "boas": 1,
            "total": 1,
            "modelo": MODELO_MUDO,
            "resultados": [{"indice": 1, "ok": True, "codigo": 200, "motivo": "respondeu", "detalhe": ""}],
            "resumo": "",
        },
    )
    monkeypatch.setattr(chaves, "estado", lambda: {
        "provedor_id": "openrouter",
        "base": "https://openrouter.ai/api/v1",
        "modelo": MODELO_MUDO,
        "quantidade": 1,
        "mascaradas": ["sk-or…ae3e (73 caracteres)"],
        "arquivo": str(env),
        "suspeitas": [],
    })
    from server import provedores

    monkeypatch.setattr(
        provedores,
        "listar_modelos",
        lambda **_k: {"modelos": [{"id": MODELO_MUDO}], "total": 1},
    )

    assert modulo.main(["--testar"]) == 0
    assert "coerentes" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# O `--corrigir`: pular o mudo e não parar em 3
# ---------------------------------------------------------------------------

def test_o_corrigir_pula_o_modelo_mudo_e_grava_o_que_fala(monkeypatch, env, capsys):
    """Quem responde 200 sem texto não pode ser gravado — o próximo é testado."""
    from server import escolha_modelo

    disponiveis = [
        MODELO_MUDO,
        "google/gemma-4-26b-a4b-it:free",
        "google/gemma-4-31b-it:free",
        "inclusionai/ling-3.2-flash:free",
        "qwen/qwen3-32b:free",
    ]
    ordem = escolha_modelo.candidatos(disponiveis, limite=6, atual=MODELO_MUDO)
    mudo, falante = ordem[0], ordem[1]
    modulo, testados = _preparar(
        monkeypatch, env, {mudo: (200, False), falante: (200, True)}, disponiveis=disponiveis
    )

    codigo = modulo.main(["--corrigir"])
    texto = capsys.readouterr().out

    assert codigo == 0, texto
    assert mudo in texto and "sem texto" in texto
    assert f"JARVIS_AI_MODEL={falante}" in env.read_text(encoding="utf-8")
    assert testados[:2] == [mudo, falante]


def test_o_corrigir_vai_alem_dos_tres_primeiros(monkeypatch, env, capsys):
    """No console do dono os 3 primeiros falharam e o script desistiu ali."""
    disponiveis = [
        MODELO_MUDO,
        "google/gemma-4-26b-a4b-it:free",
        "google/gemma-4-31b-it:free",
        "inclusionai/ling-3.2-flash:free",
        "liquid/lfm-2.5-8b:free",
        "qwen/qwen3-32b:free",
    ]
    from server import escolha_modelo

    ordem = escolha_modelo.candidatos(disponiveis, limite=6, atual=MODELO_MUDO)
    # os quatro primeiros não respondem; o quinto é quem fala
    respostas = {nome: (429, False) for nome in ordem[:4]}
    falante = ordem[4] if len(ordem) > 4 else ordem[-1]
    respostas[falante] = (200, True)
    modulo, testados = _preparar(monkeypatch, env, respostas, disponiveis=disponiveis)

    codigo = modulo.main(["--corrigir"])
    texto = capsys.readouterr().out

    assert codigo == 0, texto
    assert len(testados) >= 5, f"parou cedo: testou {testados}"
    assert f"JARVIS_AI_MODEL={falante}" in env.read_text(encoding="utf-8")


def test_nenhum_mudo_e_gravado(monkeypatch, env, capsys):
    """Sem ninguém falando, o `.env` não pode mudar."""
    antes = env.read_bytes()
    modulo, testados = _preparar(monkeypatch, env, {MODELO_BOM: (200, False)})

    assert modulo.main(["--corrigir"]) == 1
    assert env.read_bytes() == antes
    assert testados, "nenhum candidato foi testado"
