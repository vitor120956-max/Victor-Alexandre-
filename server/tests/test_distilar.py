"""Testes da camada de perfil de pessoa (0.34.0), inspirada em titanwings/distilly.

Nada aqui chama modelo: a camada é medição, busca lexical e gate. Os testes
verificam o que dá para provar — contagem, marcação, recusa — e não a qualidade
de um perfil escrito.
"""
from __future__ import annotations

import importlib
import json

import pytest
from fastapi.testclient import TestClient

from server import distilar as D
from server.app import create_app

CORPUS = """>>> conversa-ana.txt
Ana: eu sempre prefiro revisar o PR antes de subir, porque já quebrou produção uma vez
Ana: teste primeiro, depois deploy — não tem atalho nesse processo
Ana: nessa reunião eu discordei do prazo, mas falei na hora e não depois
Ana: desculpa a resposta seca de ontem, foi mal, vamos resolver juntos
Ana: não sei nada de kubernetes, isso é com o time de infra
Ana: acho que o fluxo tem que ser primeiro escrever o teste, depois codar
Ana: na verdade eu prefiro que a gente combine o formato antes da reunião
Ana: meu processo é sempre abrir o chamado, revisar o diff e só então pedir revisão
>>> email-ana.md
Ana: sobre o deploy, prefiro fazer na terça porque segunda é dia de plantão
Ana: não posso assumir o plantão de sexta, tenho compromisso de família
"""

PERFIL_BOM = """# Ana

## Modelos mentais

- Teste antes de deploy: o processo dela sempre começa pelo teste.
- Combinar formato antes da reunião, para não discutir forma no encontro.
- Revisão de diff antes de pedir revisão de alguém.

## Voz

- Ritmo curto, frase direta, metáfora rara.
- Diz "na verdade" antes de corrigir alguém.

## Tensão interna

- Discordou do prazo na reunião e mesmo assim defendeu o prazo depois.
- Contradiz a própria pressa quando o assunto é plantão.

## Limites honestos

- Não sabe kubernetes e delega para o time de infra.
- O perfil não afirma nada sobre a vida pessoal além do que está nas fontes.

## Limitações

- Limite de cobertura: seis meses de conversa.

## Fontes

- https://exemplo.org/conversa-ana fonte primária
- https://exemplo.org/email-ana fonte primária

source weight: 2
source weight: 3
"""


# ---------------------------------------------------------------------------
# Perfil
# ---------------------------------------------------------------------------


def test_perfil_mede_o_corpus():
    dados = D.perfil(corpus=CORPUS, familia="colleague")
    assert dados["metrics"]["mensagens"] == 10
    assert dados["metrics"]["fontes"] == 2
    assert dados["metrics"]["evidencias"] >= 5
    assert dados["executed"] is False and dados["readOnly"] is True


def test_perfil_conta_dimensoes_por_familia():
    dados = D.perfil(corpus=CORPUS, familia="relationship")
    assert len(dados["rows"]) == len(D.FAMILIAS["relationship"]["dimensoes"])


def test_perfil_corpus_curto_bloqueia():
    dados = D.perfil(corpus="Ana: oi\nAna: tudo bem?")
    assert dados["counts"]["must"] >= 1
    assert "insuficiente" in " ".join(item["title"].lower() for item in dados["findings"])


def test_perfil_lista_citacoes_candidatas():
    dados = D.perfil(corpus=CORPUS)
    assert "## Citações candidatas" in dados["markdown"]
    assert any("conversa-ana.txt:" in linha for linha in dados["markdown"].splitlines())


def test_perfil_marca_dimensao_ausente():
    dados = D.perfil(corpus=CORPUS, familia="celebrity")
    assert dados["metrics"]["ausentes"] >= 1
    assert any("sem nenhuma evidência" in item["title"].lower() for item in dados["findings"])


def test_perfil_recusa_corpus_vazio():
    with pytest.raises(D.DistilarError, match="Texto vazio"):
        D.perfil(corpus="   ")


def test_perfil_recusa_familia_invalida():
    with pytest.raises(D.DistilarError, match="Família inválida"):
        D.perfil(corpus=CORPUS, familia="inimigo")


def test_perfil_recusa_corpus_acima_do_teto():
    with pytest.raises(D.DistilarError, match="teto"):
        D.perfil(corpus="a" * (D.MAX_CORPUS + 1))


def test_perfil_aceita_modo_lite():
    dados = D.perfil(corpus=CORPUS, modo="lite")
    assert all(item["group"] == "must" for item in dados["findings"])


# ---------------------------------------------------------------------------
# Dimensões
# ---------------------------------------------------------------------------


def test_dimensoes_lista_as_quatro_familias():
    dados = D.dimensoes()
    assert dados["metrics"]["familias"] == 4
    assert dados["metrics"]["dimensoes"] == sum(len(dados["dimensoes"]) for dados in D.FAMILIAS.values())


def test_dimensoes_filtra_por_familia():
    dados = D.dimensoes(familia="celebrity")
    assert dados["metrics"]["familias"] == 1
    assert {linha["familia"] for linha in dados["rows"]} == {"celebrity"}


def test_dimensoes_recusa_familia_desconhecida():
    with pytest.raises(D.DistilarError, match="Família inválida"):
        D.dimensoes(familia="pet")


# ---------------------------------------------------------------------------
# Esqueleto
# ---------------------------------------------------------------------------


def test_esboco_gera_slug_e_front_matter():
    dados = D.esboco(nome="Ana Souza", familia="colleague", corpus=CORPUS)
    assert dados["slug"] == "ana-souza"
    assert dados["conteudo"].startswith("---\nname: distilly-ana-souza")
    assert dados["destino"] == "skills/colleague/ana-souza/"


def test_esboco_manifesto_tem_hash_e_fontes():
    dados = D.esboco(nome="Ana Souza", familia="colleague", corpus=CORPUS)
    manifesto = dados["manifesto"]
    assert len(manifesto["sha256"]) == 64
    assert "conversa-ana.txt" in manifesto["fontes"]
    assert manifesto["artefatos"] == ["SKILL.md", "manifest.json"]


def test_esboco_marca_secao_sem_evidencia():
    dados = D.esboco(nome="Ana", familia="celebrity", corpus=CORPUS)
    assert "sem evidência" in dados["conteudo"] or "Não há evidência" in dados["conteudo"]


def test_esboco_sem_corpus_exige_fonte():
    dados = D.esboco(nome="Ana", familia="colleague")
    assert dados["counts"]["must"] >= 1
    assert "sem fonte" in " ".join(item["title"].lower() for item in dados["findings"])


def test_esboco_recusa_nome_vazio():
    with pytest.raises(D.DistilarError, match="Informe o nome"):
        D.esboco(nome="   ")


def test_esboco_recusa_nome_sem_slug():
    with pytest.raises(D.DistilarError, match="slug"):
        D.esboco(nome="!!!")


def test_esboco_recusa_nome_reservado_do_windows():
    with pytest.raises(D.DistilarError, match="reservado"):
        D.esboco(nome="CON")


def test_esboco_normaliza_acento_e_caixa():
    dados = D.esboco(nome="João da Silva Ção")
    assert dados["slug"] == "joao-da-silva-cao"


def test_esboco_limita_slug_a_quarenta():
    dados = D.esboco(nome="a" * 80)
    assert len(dados["slug"]) <= D.MAX_SLUG


# ---------------------------------------------------------------------------
# Qualidade
# ---------------------------------------------------------------------------


def test_qualidade_aprova_perfil_completo():
    dados = D.qualidade(perfil_texto=PERFIL_BOM)
    assert dados["aprovado"] is True
    assert dados["metrics"]["reprovam"] == 0


def test_qualidade_reprova_texto_vazio_de_marcas():
    dados = D.qualidade(perfil_texto="Uma pessoa legal que trabalha bem com todos.")
    assert dados["aprovado"] is False
    assert dados["metrics"]["obrigatorias"] >= 1


def test_qualidade_reprova_bloco_de_codigo():
    texto = PERFIL_BOM + "\n```text\n00:01:22 fala literal inteira\n```\n"
    dados = D.qualidade(perfil_texto=texto)
    assert dados["aprovado"] is False
    assert any("transcrição" in item["title"].lower() for item in dados["findings"])


def test_qualidade_reprova_citacao_em_bloco():
    texto = PERFIL_BOM + "\n> fala copiada com mais de vinte e cinco palavras aqui dentro do bloco citado\n"
    dados = D.qualidade(perfil_texto=texto)
    assert dados["metrics"]["citacoesLongas"] >= 1


def test_qualidade_referencia_estrita_exige_mais():
    dados = D.qualidade(perfil_texto=PERFIL_BOM, referencia="budget-unfriendly")
    assert dados["aprovado"] is False
    assert dados["metrics"]["obrigatorias"] >= 1


def test_qualidade_recusa_referencia_desconhecida():
    with pytest.raises(D.DistilarError, match="Referência inválida"):
        D.qualidade(perfil_texto=PERFIL_BOM, referencia="strict")


def test_qualidade_conta_pesos_de_fonte():
    dados = D.qualidade(perfil_texto=PERFIL_BOM)
    assert dados["metrics"]["urls"] == 2


# ---------------------------------------------------------------------------
# Lastro
# ---------------------------------------------------------------------------


def test_lastro_acha_apoio():
    dados = D.lastro(
        perfil_texto="- Teste antes de deploy: o processo dela sempre começa pelo teste.",
        corpus=CORPUS,
    )
    assert dados["metrics"]["afirmacoes"] == 1
    assert dados["metrics"]["comLastro"] == 1
    assert dados["rows"][0]["fonte"] != "—"


def test_lastro_aponta_afirmacao_sem_origem():
    dados = D.lastro(perfil_texto="- Ela adora viajar para a Islândia em janeiro.", corpus=CORPUS)
    assert dados["metrics"]["semLastro"] == 1
    assert dados["semLastro"][0].startswith("Ela adora")


def test_lastro_recusa_citacao_longa():
    longa = "x" * (D.CITACAO_MAXIMA + 40)
    dados = D.lastro(perfil_texto=f'- Fala literal: "{longa}"', corpus=CORPUS)
    assert dados["metrics"]["citacoesLongas"] == 1
    assert dados["counts"]["must"] >= 1


def test_lastro_aponta_citacao_fora_do_corpus():
    dados = D.lastro(perfil_texto='- Disse: "frase que ninguém falou neste material"', corpus=CORPUS)
    assert dados["metrics"]["citacoesFora"] == 1


def test_lastro_sem_bullets_avisa():
    dados = D.lastro(perfil_texto="Texto corrido sem afirmação em lista.", corpus=CORPUS)
    assert dados["metrics"]["afirmacoes"] == 0
    assert any("nenhuma afirmação" in item["title"].lower() for item in dados["findings"])


def test_lastro_recusa_corpus_vazio():
    with pytest.raises(D.DistilarError, match="Texto vazio"):
        D.lastro(perfil_texto="- algo aqui com mais de vinte letras", corpus="")


# ---------------------------------------------------------------------------
# Correção
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texto,tipo",
    [
        ("na verdade a data estava errada, foi em maio", "fato"),
        ("ele não fala assim, soa artificial", "voz"),
        ("ele não faria isso, ele pede opinião antes", "julgamento"),
        ("ele não sabe nada de kubernetes", "limite"),
    ],
)
def test_correcao_classifica(texto, tipo):
    dados = D.correcao(correcao=texto, secao="voz", evidencia="linha 12: ele pede opinião antes de decidir")
    assert dados["tipo"] == tipo
    assert dados["metrics"]["comLastro"] is True


def test_correcao_sem_evidencia_bloqueia():
    dados = D.correcao(correcao="ele não faria isso de jeito nenhum", secao="padroes_de_decisao")
    assert dados["metrics"]["comLastro"] is False
    assert dados["counts"]["must"] >= 1


def test_correcao_sem_secao_avisa():
    dados = D.correcao(correcao="na verdade o nome dele é outro", evidencia="linha 4 do cadastro")
    assert dados["counts"]["should"] >= 1


def test_correcao_recusa_secao_desconhecida():
    with pytest.raises(D.DistilarError, match="Seção desconhecida"):
        D.correcao(correcao="na verdade está errado o nome", secao="infancia")


def test_correcao_recusa_texto_curto():
    with pytest.raises(D.DistilarError, match="pelo menos 10"):
        D.correcao(correcao="errado")


def test_correcao_devolve_registro_json():
    dados = D.correcao(
        correcao="na verdade a reunião foi em maio, não em abril",
        secao="retrato",
        evidencia="linha 22: reunião de 3 de maio",
    )
    json.dumps(dados["registro"])
    assert dados["registro"]["com_lastro"] is True


# ---------------------------------------------------------------------------
# Hospedeiros
# ---------------------------------------------------------------------------


def test_hospedeiros_lista_os_oito():
    dados = D.hospedeiros()
    assert dados["metrics"]["hospedeiros"] == 8
    assert {linha["host"] for linha in dados["rows"]} == set(D.HOSPEDEIROS)


def test_hospedeiros_respeita_a_raiz():
    dados = D.hospedeiros(host="claude-code", raiz="/home/ana")
    assert dados["rows"][0]["skills"] == "/home/ana/.claude/skills"


def test_hospedeiros_usa_env_do_deepseek(monkeypatch):
    monkeypatch.setenv("DSH_HOME", "/opt/dsh")
    dados = D.hospedeiros(host="deepseek-harness")
    assert dados["rows"][0]["skills"].startswith("/opt/dsh")


def test_hospedeiros_hermes_tem_pasta_gerada():
    dados = D.hospedeiros(host="hermes", raiz="/home/ana")
    assert dados["rows"][0]["gerado"].endswith("distilly-generated")


def test_hospedeiros_recusa_host_desconhecido():
    with pytest.raises(D.DistilarError, match="Hospedeiro desconhecido"):
        D.hospedeiros(host="cursor")


# ---------------------------------------------------------------------------
# Catálogo e API
# ---------------------------------------------------------------------------


def test_catalogo_publica_origem_e_recusas():
    dados = D.catalogo()
    assert dados["origem"]["projeto"] == "titanwings/distilly"
    assert dados["origem"]["licenca"] == "MIT"
    assert len(dados["familias"]) == 4
    assert len(dados["hospedeiros"]) == 8
    assert len(dados["nao_faz"]) >= 5


@pytest.fixture
def client():
    return TestClient(create_app(registry=None))


def test_api_lista_as_nove_skills_de_pessoa(client):
    ids = {item["id"] for item in client.get("/api/skills").json()["skills"]}
    assert len([item for item in ids if item.startswith("distilar.")]) == 9





def test_api_perfil_responde(client):
    resposta = client.post(
        "/api/skills/distilar.perfil/execute",
        json={"parameters": {"corpus": CORPUS, "familia": "colleague"}},
    )
    corpo = resposta.json()
    assert corpo["ok"] is True
    assert corpo["result"]["metrics"]["mensagens"] == 10


def test_api_erro_de_entrada_vira_skill_error(client):
    resposta = client.post(
        "/api/skills/distilar.perfil/execute",
        json={"parameters": {"corpus": CORPUS, "familia": "pet"}},
    )
    assert resposta.status_code == 422 or resposta.json()["ok"] is False


def test_api_regras_nao_exige_token(client):
    resposta = client.post("/api/skills/distilar.regras/execute", json={"parameters": {}})
    assert resposta.json()["ok"] is True


def test_api_esboco_devolve_conteudo(client):
    resposta = client.post(
        "/api/skills/distilar.esboco/execute",
        json={"parameters": {"nome": "Ana Souza", "familia": "colleague", "corpus": CORPUS}},
    )
    corpo = resposta.json()["result"]
    assert corpo["slug"] == "ana-souza"
    assert corpo["conteudo"].startswith("---")


# ---------------------------------------------------------------------------
# Geração com provedor externo (0.35.0)
# ---------------------------------------------------------------------------

PERFIL_GERADO = """## Padrões de decisão

- Revisa o PR antes de subir porque já quebrou produção (conversa-ana.txt:1).
- Prefere combinar o formato antes da reunião (conversa-ana.txt:7).

## Padrão técnico

- Teste antes de deploy, sem atalho (conversa-ana.txt:2).

## Fluxo de trabalho

- Abre o chamado, revisa o diff e só então pede revisão (conversa-ana.txt:8).

## Voz

- Frase curta, ritmo direto, sem metáfora (conversa-ana.txt:3).

## Comportamento no time

- Discordou do prazo na reunião, mas falou na hora (conversa-ana.txt:3).

## Limites

- Não sabe kubernetes e delega para o time de infra (conversa-ana.txt:5).

## Limites honestos

- O perfil não afirma nada sobre a vida pessoal além do que está nas fontes.
- Não há evidência sobre este ponto no material fornecido.

## Fontes

- https://exemplo.org/conversa-ana
- https://exemplo.org/email-ana

source weight: 2
source weight: 3
"""


class ProvedorFalso:
    def __init__(self, resposta: str = PERFIL_GERADO, configured: bool = True):
        self.resposta = resposta
        self._configured = configured
        self.pedidos: list = []

    @property
    def configured(self) -> bool:
        return self._configured

    def status(self):
        return {"configured": self._configured, "provider": "falso", "model": "falso-1", "external": True}

    async def generate(self, request):
        self.pedidos.append(request)
        return self.resposta


def test_persona_sem_provedor_recusa():
    with pytest.raises(D.DistilarError, match="IA externa não configurada"):
        importlib.import_module("server.distilar_ia").persona(corpus=CORPUS, ai_provider=None)


def test_persona_com_provedor_desconfigurado_recusa():
    with pytest.raises(D.DistilarError, match="JARVIS_AI_API_KEY"):
        importlib.import_module("server.distilar_ia").persona(corpus=CORPUS, ai_provider=ProvedorFalso(configured=False))


def test_persona_exporta_material_e_devolve_rascunho():
    falso = ProvedorFalso()
    dados = importlib.import_module("server.distilar_ia").persona(corpus=CORPUS, nome="Ana Souza", ai_provider=falso)
    assert dados["exportado"] is True
    assert dados["executed"] is False and dados["readOnly"] is True
    assert dados["slug"] == "ana-souza"
    assert dados["conteudo"].startswith("---\nname: distilly-ana-souza")
    assert dados["metrics"]["caracteresEnviados"] == len(CORPUS.strip()[:24_000])
    assert len(falso.pedidos) == 1


def test_persona_envia_material_como_dado():
    falso = ProvedorFalso()
    importlib.import_module("server.distilar_ia").persona(corpus=CORPUS, ai_provider=falso)
    pedido = falso.pedidos[0]
    assert "conversa-ana.txt" in pedido.material
    assert pedido.max_tokens >= 2_000
    assert "dados citáveis" not in pedido.message


def test_persona_roda_lastro_e_gate():
    dados = importlib.import_module("server.distilar_ia").persona(corpus=CORPUS, ai_provider=ProvedorFalso())
    assert dados["verificacao"]["lastro"]["afirmacoes"] >= 5
    assert dados["verificacao"]["qualidade"]["checagens"] == 13
    assert "gatePassam" in dados["metrics"]


def test_persona_recusa_resposta_curta():
    with pytest.raises(D.DistilarError, match="abaixo do mínimo"):
        importlib.import_module("server.distilar_ia").persona(corpus=CORPUS, ai_provider=ProvedorFalso("curto"))


def test_persona_limpa_cerca_de_codigo():
    falso = ProvedorFalso("```markdown\n" + PERFIL_GERADO + "\n```")
    dados = importlib.import_module("server.distilar_ia").persona(corpus=CORPUS, ai_provider=falso)
    assert "```" not in dados["corpo"]


def test_persona_trunca_material_grande():
    falso = ProvedorFalso()
    grande = CORPUS + "\n" + ("Ana: linha de recheio para testar o corte do envio\n" * 900)
    dados = importlib.import_module("server.distilar_ia").persona(corpus=grande, ai_provider=falso)
    assert dados["metrics"]["truncado"] is True
    assert dados["metrics"]["caracteresEnviados"] == 24_000
    assert any("truncado" in item["title"].lower() for item in dados["findings"])


def test_persona_sempre_avisa_que_foi_modelo():
    dados = importlib.import_module("server.distilar_ia").persona(corpus=CORPUS, ai_provider=ProvedorFalso())
    assert any("gerado por modelo" in item["title"].lower() for item in dados["findings"])


def test_persona_recusa_corpus_vazio():
    with pytest.raises(D.DistilarError, match="Texto vazio"):
        importlib.import_module("server.distilar_ia").persona(corpus="   ", ai_provider=ProvedorFalso())


def test_persona_aceita_provedor_sincrono():
    class Sincrono:
        configured = True

        def status(self):
            return {"provider": "sincrono", "model": "s1"}

        def generate(self, request):
            return PERFIL_GERADO

    dados = importlib.import_module("server.distilar_ia").persona(corpus=CORPUS, ai_provider=Sincrono())
    assert dados["metrics"]["caracteresRecebidos"] > 200


def test_api_persona_exige_confirmacao(tmp_path):
    from server.skill_registry import build_registry

    registry = build_registry(tmp_path / "files", ai_provider=ProvedorFalso())
    cliente = TestClient(create_app(registry=registry))
    resposta = cliente.post(
        "/api/skills/distilar.persona/execute",
        json={"parameters": {"corpus": CORPUS, "nome": "Ana"}},
    )
    corpo = resposta.json()
    assert corpo["ok"] is False
    assert corpo["error"]["code"] == "CONFIRMATION_REQUIRED"


def test_api_persona_confirma_e_gera(tmp_path):
    from server.skill_registry import build_registry

    registry = build_registry(tmp_path / "files", ai_provider=ProvedorFalso())
    cliente = TestClient(create_app(registry=registry))
    resposta = cliente.post(
        "/api/skills/distilar.persona/execute",
        json={"parameters": {"corpus": CORPUS, "nome": "Ana"}, "confirmed": True},
    )
    corpo = resposta.json()
    assert corpo["ok"] is True
    assert corpo["result"]["exportado"] is True


def test_api_persona_sem_chave_recusa(tmp_path):
    from server.skill_registry import build_registry

    registry = build_registry(tmp_path / "files")
    cliente = TestClient(create_app(registry=registry))
    resposta = cliente.post(
        "/api/skills/distilar.persona/execute",
        json={"parameters": {"corpus": CORPUS, "nome": "Ana"}, "confirmed": True},
    )
    corpo = resposta.json()
    assert corpo["ok"] is False
    assert "JARVIS_AI_API_KEY" in corpo["error"]["message"]


def test_api_registro_conta_209(client):
    assert len(client.get("/api/skills").json()["skills"]) == 231
