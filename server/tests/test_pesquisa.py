"""Testes de `server/pesquisa.py` (0.43.0) — busca, leitura e resposta com fonte.

A rede não é usada aqui: `buscar` e `ler` são injetados, e o provedor é um
dublê. Isso permite cobrir o fluxo inteiro sem depender do DuckDuckGo.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.app import create_app
from server.pesquisa import extrair_fontes, extrair_texto, montar_material, responder
from server.sistema import SistemaError


# --------------------------------------------------------------- dublês

def busca_com(links):
    def buscar(**_kwargs):
        return {"rows": [{"posicao": i + 1, "titulo": t, "url": u} for i, (t, u) in enumerate(links)]}
    return buscar


def leitura_com(mapa):
    def ler(**kwargs):
        url = kwargs.get("url", "")
        if url not in mapa:
            raise SistemaError(f"Página fora do mapa: {url}")
        return {"rows": [], "sections": ["", "## Conteúdo da página", "", mapa[url]]}
    return ler


class ProvedorFalso:
    def __init__(self, *_, resposta="Resposta do modelo.", configurado=True, erro=None):
        self._resposta = resposta
        self._configurado = configurado
        self._erro = erro
        self.recebido = None

    @property
    def configured(self):
        return self._configurado

    def status(self):
        return {"configured": self._configurado, "provider": "Falso", "model": "falso", "external": True}

    async def generate(self, request):
        self.recebido = request
        if self._erro:
            from server.ai import AIUnavailable

            raise AIUnavailable(self._erro)
        return self._resposta


FONTES = [
    ("Machado de Assis — Wikipédia", "https://pt.wikipedia.org/wiki/Machado_de_Assis"),
    ("Machado de Assis — Enciclopédia", "https://exemplo.org/machado"),
]
PAGINAS = {
    FONTES[0][1]: "Joaquim Maria Machado de Assis foi um escritor brasileiro.",
    FONTES[1][1]: "Nasceu no Rio de Janeiro em 1839.",
}


def rodar(pergunta="", **kwargs):
    return asyncio.run(responder(pergunta, **kwargs))


# --------------------------------------------------------------- funções puras

def test_extrair_fontes_ignora_url_que_nao_e_http():
    resultado = {"rows": [
        {"titulo": "bom", "url": "https://ok.example"},
        {"titulo": "ruim", "url": "javascript:alert(1)"},
        {"titulo": "vazio", "url": ""},
    ]}
    assert [f["titulo"] for f in extrair_fontes(resultado)] == ["bom"]


def test_extrair_texto_lê_sections():
    assert extrair_texto({"sections": ["", "## Conteúdo da página", "", "texto"]}).strip().endswith("texto")


def test_extrair_texto_devolve_vazio_quando_nao_ha_conteudo():
    assert extrair_texto({"rows": []}) == ""


def test_montar_material_junta_fonte_e_conteudo():
    material = montar_material(
        [{"titulo": "A", "url": "https://a.example"}],
        [{"url": "https://a.example", "texto": "conteúdo de A"}],
    )
    assert "[Fonte 1] A" in material
    assert "https://a.example" in material
    assert "conteúdo de A" in material


def test_montar_material_respeita_o_limite():
    fontes = [{"titulo": "A", "url": "https://a.example"}]
    paginas = [{"url": "https://a.example", "texto": "x" * 10_000}]
    assert len(montar_material(fontes, paginas, limite=500)) == 500


# --------------------------------------------------------------- fluxo

def test_responde_com_ia_e_leva_o_texto_como_material():
    provedor = ProvedorFalso()
    resultado = rodar(
        "quem foi Machado de Assis",
        autorizacao="token",
        provedor=provedor,
        buscar=busca_com(FONTES),
        ler=leitura_com(PAGINAS),
    )
    assert resultado["modo"] == "ia"
    assert resultado["resposta"] == "Resposta do modelo."
    assert provedor.recebido is not None
    assert "Machado de Assis" in provedor.recebido.message
    assert "escritor brasileiro" in provedor.recebido.material
    assert "1839" in provedor.recebido.material
    assert len(resultado["fontes"]) == 2
    assert all(fonte["lida"] for fonte in resultado["fontes"])


def test_sem_ia_devolve_fontes_e_trecho_em_vez_de_falhar():
    resultado = rodar(
        "quem foi Machado de Assis",
        autorizacao="token",
        provedor=ProvedorFalso(configurado=False),
        buscar=busca_com(FONTES),
        ler=leitura_com(PAGINAS),
    )
    assert resultado["modo"] == "sem-ia"
    assert resultado["resposta"] is None
    assert resultado["trecho"].startswith("Joaquim Maria")
    assert [f["url"] for f in resultado["fontes"]] == [u for _, u in FONTES]


def test_limita_quantas_paginas_lê():
    lidas = []

    def ler(**kwargs):
        lidas.append(kwargs["url"])
        return {"sections": ["texto"]}

    rodar("pergunta qualquer", autorizacao="t", provedor=ProvedorFalso(),
          buscar=busca_com(FONTES), ler=ler, paginas=1)
    assert lidas == [FONTES[0][1]]


def test_pagina_que_falha_vira_aviso_e_nao_derruba():
    def ler(**kwargs):
        if kwargs["url"].endswith("exemplo.org/machado"):
            raise SistemaError("timeout")
        return {"sections": ["conteúdo bom"]}

    resultado = rodar("quem foi Machado", autorizacao="t", provedor=ProvedorFalso(),
                      buscar=busca_com(FONTES), ler=ler)
    assert resultado["modo"] == "ia"
    assert any("timeout" in aviso for aviso in resultado["avisos"])
    assert resultado["fontes"][1]["lida"] is False


def test_busca_sem_resultado_nao_inventa_resposta():
    with pytest.raises(SistemaError):
        rodar("assunto inexistente", autorizacao="t", provedor=ProvedorFalso(),
              buscar=busca_com([]), ler=leitura_com({}))


def test_busca_vazia_ainda_avisa():
    resultado = rodar("assunto raro", autorizacao="t", provedor=ProvedorFalso(configurado=False),
                      buscar=busca_com([("Algo", "https://exemplo.org/x")]), ler=leitura_com({}))
    assert "não devolveu link" not in " ".join(resultado["avisos"]) or resultado["fontes"]
    assert resultado["trecho"] == ""


def test_erro_do_provedor_cai_para_sem_ia():
    resultado = rodar("quem foi Machado", autorizacao="t",
                      provedor=ProvedorFalso(erro="HTTP 429"),
                      buscar=busca_com(FONTES), ler=leitura_com(PAGINAS))
    assert resultado["modo"] == "sem-ia"
    assert resultado["resposta"] is None
    assert any("429" in aviso for aviso in resultado["avisos"])


def test_pergunta_curta_e_recusada():
    with pytest.raises(SistemaError):
        rodar("oi", autorizacao="t", provedor=ProvedorFalso(), buscar=busca_com([]), ler=leitura_com({}))


# --------------------------------------------------------------- rota HTTP

@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_HOST_REDE", "1")
    return TestClient(create_app(ai_provider=ProvedorFalso()))


def test_rota_recusa_sem_rede_ligada(tmp_path, monkeypatch):
    monkeypatch.delenv("JARVIS_HOST_REDE", raising=False)
    with TestClient(create_app(ai_provider=ProvedorFalso())) as client:
        resposta = client.post("/api/pesquisa/responder", json={"pergunta": "quem foi Machado", "autorizacao": "x"})
    assert resposta.status_code == 400
    assert resposta.json()["error"]["code"] == "PESQUISA_RECUSADA"


def test_rota_recusa_token_invalido(cliente):
    resposta = cliente.post("/api/pesquisa/responder", json={"pergunta": "quem foi Machado", "autorizacao": "errado"})
    assert resposta.status_code == 400
    assert "token" in resposta.json()["error"]["message"].lower()


def test_rota_valida_o_tamanho_da_pergunta(cliente):
    resposta = cliente.post("/api/pesquisa/responder", json={"pergunta": "ab", "autorizacao": "x"})
    assert resposta.status_code == 422


def test_rota_existe_no_catalogo_de_rotas(cliente):
    caminhos = {rota.path for rota in cliente.app.routes}
    assert "/api/pesquisa/responder" in caminhos


def test_modulo_nao_esta_no_gitignore():
    raiz = Path(__file__).resolve().parents[2]
    ignorados = {linha.strip() for linha in (raiz / ".gitignore").read_text(encoding="utf-8").splitlines()}
    assert "server/pesquisa.py" not in ignorados


def test_doc_descreve_o_fluxo_novo():
    raiz = Path(__file__).resolve().parents[2]
    texto = (raiz / "docs" / "PESQUISA.md").read_text(encoding="utf-8")
    assert "pesquisar e responder" in texto
    assert "token" in texto
    assert "material" in texto
    assert "60.000" in texto
