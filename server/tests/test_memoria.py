"""Testes da camada de memória de agente (0.27.0).

A camada é determinística: lê texto colado, não chama modelo, não gera
embedding, não abre banco de grafo e não grava sessão. As fixtures são
conversas e conjuntos de memória escritos à mão.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from server.memoria import (
    ESCOPOS_ESQUECIMENTO,
    LIMIAR_ROTA,
    MAX_ENTRADAS,
    MAX_RESULTADOS,
    MODOS,
    TIPOS_ENTIDADE,
    TIPOS_MEMORIA,
    VIAS,
    VIA_PADRAO,
    MemoriaError,
    consultar_memoria,
    destilar_sessao,
    esquecer,
    extrair_entidades,
    ler_grafo,
    ler_memorias,
    memoria_catalogo,
    montar_grafo,
    rotear_consulta,
)
from server.skill_registry import build_registry

# ------------------------------------------------------------------ fixtures

CONVERSA = """usuário: O deploy do Atlas usa o cluster de São Paulo e o banco é Postgres 16.
agente: Entendi.
usuário: decisão: o índice vetorial vai para o pgvector e não para um serviço externo.
usuário: ok
agente: regra: nunca rodar migration sem rollback escrito.
usuário: feedback: -1 prefiro manter a migration no mesmo PR do código.
usuário: aprendizado: o limite de 5 MB por asset é conferido no portão antes da revisão.
usuário: A retenção de 365 dias foi acordada com o jurídico em 12/03/2024.
"""

TEXTO = """Marie Curie nasceu em Warsaw em 1867-11-07 e trabalhou na University of Paris.
Pierre Curie foi professor na ESPCI e descobriu o polônio com Marie Curie.
O ticket SDM-2041 trata do orçamento de R$ 45.000 para o projeto Atlas em 12/03/2024.
O arquivo server/memoria.py implementa a rota e o datasource usa o Graphiti.
A política de retenção define 90% dos dados por 365 dias em São Paulo.
"""

ARESTAS = """Marie Curie -> trabalhou em -> University of Paris
Marie Curie -> descobriu -> polônio
Pierre Curie -> casado com -> Marie Curie
Marie Curie -> casado com -> Pierre Curie
polônio -> relaciona -> física
Nanismo
"""

MEMORIAS = """m1 | decisao | 2026-03-12 | ata.md | atlas | O índice vetorial do Atlas vai para o pgvector e não para serviço externo.
m2 | fato | 2025-11-02 | doc.md | atlas | Marie Curie nasceu em Warsaw em 1867-11-07.
m3 | regra | 2026-09-30 | runbook.md | atlas | Migration sempre com rollback escrito e testado no mesmo PR.
m4 | fato | 2024-01-05 | antigo.md | atlas | O deploy do Atlas roda no cluster de Dublin e em Warsaw.
m5 | procedimento | 2026-10-01 | runbook.md | outros | Como instalar o plugin do cognee no Claude Code com o marketplace.
"""

HOJE = "2026-10-24"


def kinds(resultado: dict) -> set[str]:
    return {item["kind"] for item in resultado["findings"]}


@pytest.fixture()
def client(tmp_path) -> TestClient:
    from server.app import create_app

    return TestClient(create_app(registry=build_registry(tmp_path / "files")))


# --------------------------------------------------------------- roteamento


@pytest.mark.parametrize(
    ("consulta", "via"),
    [
        ("Quem é Marie Curie?", "chunks"),
        ("Qual o valor do contrato?", "chunks"),
        ("Onde fica o índice vetorial do Atlas?", "chunks"),
        ("Como faço para instalar o plugin do cognee no Claude Code?", "procedimento"),
        ("Resuma os principais achados dos documentos de arquitetura", "resumo"),
        ("Qual foi a decisão sobre o banco vetorial e por que decidimos assim?", "regras"),
        ("Qual é a relação entre o dataset de cientistas e o grafo de publicações?", "grafo"),
        ("Onde está implementada a função rotear_consulta()?", "codigo"),
        ("O que mudou na política desde 2025?", "temporal"),
    ],
)
def test_roteador_escolhe_a_via_pela_forma_da_pergunta(consulta: str, via: str) -> None:
    resultado = rotear_consulta(consulta=consulta)
    assert resultado["metrics"]["via"] == via
    assert resultado["metrics"]["fallback"] == 0


def test_roteador_usa_o_padrao_quando_nada_passa_do_limiar() -> None:
    resultado = rotear_consulta(consulta="Xyzzy plugh frobnicate")
    assert resultado["metrics"]["via"] == VIA_PADRAO
    assert resultado["metrics"]["fallback"] == 1
    assert "sem-sinal" in kinds(resultado)
    assert resultado["metrics"]["pontuacao"] < LIMIAR_ROTA


def test_roteador_respeita_negacao() -> None:
    resultado = rotear_consulta(consulta="Não quero resumo, quero a fonte")
    assert resultado["metrics"]["negados"] == 1
    assert resultado["metrics"]["via"] != "resumo"
    assert "sinal-negado" in kinds(resultado)


def test_roteador_marca_ambiguidade_quando_duas_vias_empatam() -> None:
    resultado = rotear_consulta(consulta="O que mudou na política de retenção desde 2024?")
    assert resultado["metrics"]["via"] in {"temporal", "regras"}
    assert resultado["metrics"]["margem"] < 1.0
    assert "ambiguidade-de-via" in kinds(resultado)


def test_roteador_avisa_consulta_curta() -> None:
    resultado = rotear_consulta(consulta="Quem é?")
    assert "consulta-curta" in kinds(resultado)


def test_roteador_recusa_consulta_vazia() -> None:
    with pytest.raises(MemoriaError):
        rotear_consulta(consulta="   ")
    with pytest.raises(MemoriaError):
        rotear_consulta(consulta="Marie Curie?", modo="turbo")


def test_roteador_devolve_tabela_de_evidencia() -> None:
    resultado = rotear_consulta(consulta="Como faço para instalar o plugin?")
    assert resultado["rows"]
    assert {"via", "regra", "peso", "trecho", "situacao"} <= set(resultado["rows"][0])
    assert "## Evidência" in resultado["markdown"]


def test_roteador_lite_so_devolve_bloqueio() -> None:
    certo = rotear_consulta(consulta="Como faço para instalar o plugin?", modo="lite")
    assert certo["counts"]["total"] == 0
    errado = rotear_consulta(consulta="Xyzzy plugh", modo="lite")
    assert errado["counts"]["must"] == 0
    assert errado["counts"]["should"] == 0


# ------------------------------------------------------------------ extracao


def test_extracao_encontra_os_sete_tipos() -> None:
    resultado = extrair_entidades(texto=TEXTO)
    encontrados = {item["tipo"] for item in resultado["rows"]}
    assert {"nome", "sigla", "codigo", "arquivo", "data", "valor", "local"} <= encontrados
    assert resultado["metrics"]["entidades"] >= 10


def test_extracao_reconhece_valor_data_e_codigo() -> None:
    resultado = extrair_entidades(texto=TEXTO)
    valores = {item["entidade"] for item in resultado["rows"]}
    assert "1867-11-07" in valores
    assert "12/03/2024" in valores
    assert "R$ 45.000" in valores
    assert "SDM-2041" in valores
    assert "server/memoria.py" in valores


def test_extracao_conta_ocorrencia_repetida() -> None:
    resultado = extrair_entidades(texto=TEXTO)
    marie = next(item for item in resultado["rows"] if item["entidade"] == "Marie Curie")
    assert marie["ocorrencias"] == 2


def test_extracao_le_relacao_declarada() -> None:
    resultado = extrair_entidades(texto="Marie Curie nasceu em Warsaw.\nPierre Curie foi professor na ESPCI.\n")
    assert resultado["metrics"]["triplas"] == 2
    assert "## Relações declaradas" in resultado["markdown"]


def test_extracao_recusa_texto_sem_entidade() -> None:
    resultado = extrair_entidades(texto="nada aqui que possa ser lembrado")
    assert "sem-entidades" in kinds(resultado)
    assert resultado["counts"]["must"] == 1


def test_extracao_recusa_vazio_e_modo_invalido() -> None:
    with pytest.raises(MemoriaError):
        extrair_entidades(texto="  ")
    with pytest.raises(MemoriaError):
        extrair_entidades(texto=TEXTO, modo="turbo")


def test_extracao_nao_duplica_sigla_como_local() -> None:
    resultado = extrair_entidades(texto="Pierre Curie foi professor na ESPCI.\n")
    tipos = [item["tipo"] for item in resultado["rows"] if item["entidade"] == "ESPCI"]
    assert tipos == ["sigla"]


# --------------------------------------------------------------------- grafo


def test_grafo_le_linha_solta_como_no_isolado() -> None:
    grafo = ler_grafo(texto=ARESTAS)
    assert "nanismo" in grafo.nos
    assert len(grafo.arestas) == 5


def test_grafo_le_json_de_arestas() -> None:
    dados = json.dumps({"arestas": [{"de": "A", "relacao": "usa", "para": "B"}]})
    grafo = ler_grafo(texto=dados)
    assert len(grafo.nos) == 2
    assert grafo.arestas == [("a", "usa", "b")]


def test_grafo_recusa_linha_sem_aresta() -> None:
    with pytest.raises(MemoriaError):
        ler_grafo(texto="A -> B -> C -> D")
    with pytest.raises(MemoriaError):
        ler_grafo(texto=json.dumps({"arestas": []}))
    with pytest.raises(MemoriaError):
        ler_grafo(texto="")


def test_grafo_mede_no_componente_e_isolado() -> None:
    resultado = montar_grafo(arestas=ARESTAS)
    assert resultado["metrics"]["nos"] == 6
    assert resultado["metrics"]["isolados"] == 1
    assert resultado["metrics"]["componentes"] == 1
    assert "no-isolado" in kinds(resultado)


def test_grafo_detecta_ciclo_de_ida_e_volta() -> None:
    resultado = montar_grafo(arestas=ARESTAS)
    assert resultado["metrics"]["ciclos"] == 1
    assert "ciclo" in kinds(resultado)


def test_grafo_em_cadeia_nao_tem_ciclo() -> None:
    resultado = montar_grafo(arestas="A -> usa -> B\nB -> usa -> C")
    assert resultado["metrics"]["ciclos"] == 0
    assert "ciclo" not in kinds(resultado)


def test_grafo_fragmentado_conta_ilhas() -> None:
    resultado = montar_grafo(arestas="A -> liga -> B\nC -> liga -> D")
    assert resultado["metrics"]["componentes"] == 2
    assert resultado["metrics"]["cobertura"] == 50.0
    assert "grafo-fragmentado" in kinds(resultado)


def test_grafo_vazio_bloqueia() -> None:
    resultado = montar_grafo(arestas="A\nB")
    assert resultado["metrics"]["arestas"] == 0
    assert "grafo-vazio" in kinds(resultado)


def test_grafo_marca_hub() -> None:
    linhas = [f"Centro -> liga -> No{i}" for i in range(14)]
    resultado = montar_grafo(arestas="\n".join(linhas))
    assert resultado["metrics"]["hubs"] == 1
    assert "hub" in kinds(resultado)


def test_grafo_devolve_grau_de_entrada_e_saida() -> None:
    resultado = montar_grafo(arestas="A -> usa -> B\nC -> usa -> B")
    centro = next(row for row in resultado["rows"] if row["no"] == "B")
    assert centro["entrada"] == 2
    assert centro["saida"] == 0
    assert centro["situacao"] == "folha"


# -------------------------------------------------------------------- sessao


def test_sessao_promove_licao_com_marcador() -> None:
    resultado = destilar_sessao(conversa=CONVERSA)
    assert resultado["metrics"]["turnos"] == 8
    assert resultado["metrics"]["promovidos"] == 3
    assert "## Lições promovidas" in resultado["markdown"]


def test_sessao_marca_regra_declarada_pelo_agente() -> None:
    resultado = destilar_sessao(conversa=CONVERSA)
    assert resultado["metrics"]["do_agente"] == 1
    assert "regra-do-agente" in kinds(resultado)


def test_sessao_descarta_confirmacao_curta() -> None:
    resultado = destilar_sessao(conversa=CONVERSA)
    assert all(row["texto"] != "ok" for row in resultado["rows"])


def test_sessao_limiar_alto_nao_promove_nada() -> None:
    resultado = destilar_sessao(conversa=CONVERSA, limiar=9.0)
    assert resultado["metrics"]["promovidos"] == 0
    assert "sessao-sem-licao" in kinds(resultado)


def test_sessao_conta_pendentes_perto_do_limiar() -> None:
    resultado = destilar_sessao(conversa=CONVERSA, limiar=4.5)
    assert resultado["metrics"]["pendentes"] >= 1
    assert "quase-promovido" in kinds(resultado)


def test_sessao_recusa_conversa_sem_turno() -> None:
    with pytest.raises(MemoriaError):
        destilar_sessao(conversa="texto solto sem papel")
    with pytest.raises(MemoriaError):
        destilar_sessao(conversa=CONVERSA, limiar=0)
    with pytest.raises(MemoriaError):
        destilar_sessao(conversa=CONVERSA, modo="turbo")


# -------------------------------------------------------------------- recall


def test_recall_devolve_o_item_certo_em_primeiro() -> None:
    resultado = consultar_memoria(consulta="Onde fica o índice vetorial do Atlas?", memorias=MEMORIAS, hoje=HOJE)
    assert resultado["rows"][0]["id"] == "m1"
    assert resultado["metrics"]["via"] == "chunks"


def test_recall_abre_a_pontuacao_por_parcela() -> None:
    resultado = consultar_memoria(consulta="Onde fica o índice vetorial do Atlas?", memorias=MEMORIAS, hoje=HOJE)
    linha = resultado["rows"][0]
    assert {"bm25", "afinidade", "recencia", "pontuacao", "fonte", "texto"} <= set(linha)
    assert "## Lastro de cada resultado" in resultado["markdown"]


def test_recall_ignora_item_sem_termo_em_comum() -> None:
    resultado = consultar_memoria(consulta="Como instalar o plugin?", memorias=MEMORIAS, hoje=HOJE, limite=3)
    assert [row["id"] for row in resultado["rows"]] == ["m5"]
    assert "sem-lastro-descartado" in kinds(resultado)


def test_recall_sem_lastro_avisa() -> None:
    resultado = consultar_memoria(consulta="qual a cor do céu?", memorias=MEMORIAS, hoje=HOJE, limite=3)
    assert "resultado-fraco" in kinds(resultado)
    assert resultado["metrics"]["descartados"] == 5


def test_recall_filtra_por_dataset() -> None:
    resultado = consultar_memoria(consulta="instalar o plugin", memorias=MEMORIAS, hoje=HOJE, dataset="atlas")
    assert resultado["metrics"]["recorte"] == 4
    with pytest.raises(MemoriaError):
        consultar_memoria(consulta="instalar", memorias=MEMORIAS, dataset="inexistente")


def test_recall_aceita_via_declarada() -> None:
    resultado = consultar_memoria(consulta="instalar o plugin", memorias=MEMORIAS, hoje=HOJE, via="procedimento")
    assert resultado["metrics"]["via"] == "procedimento"
    assert resultado["metrics"]["roteada"] == 0


def test_recall_marca_memoria_vencida() -> None:
    resultado = consultar_memoria(consulta="cluster de Dublin", memorias=MEMORIAS, hoje=HOJE)
    assert resultado["metrics"]["vencidas"] >= 1
    assert "memoria-vencida" in kinds(resultado)


def test_recall_recencia_penaliza_item_antigo() -> None:
    resultado = consultar_memoria(consulta="Atlas", memorias=MEMORIAS, hoje=HOJE, limite=5)
    antigo = next(row for row in resultado["rows"] if row["id"] == "m4")
    novo = next(row for row in resultado["rows"] if row["id"] == "m1")
    assert antigo["recencia"] < novo["recencia"]


def test_recall_recusa_entrada_invalida() -> None:
    with pytest.raises(MemoriaError):
        consultar_memoria(consulta="", memorias=MEMORIAS)
    with pytest.raises(MemoriaError):
        consultar_memoria(consulta="Atlas", memorias=MEMORIAS, via="telepatia")
    with pytest.raises(MemoriaError):
        consultar_memoria(consulta="Atlas", memorias=MEMORIAS, hoje="24/10/2026")
    with pytest.raises(MemoriaError):
        consultar_memoria(consulta="Atlas", memorias=MEMORIAS, limite=0)


def test_recall_aceita_json_de_memorias() -> None:
    dados = json.dumps({"memorias": [{"id": "a1", "tipo": "fato", "texto": "O Atlas usa pgvector.", "criado": HOJE, "dataset": "atlas"}]})
    resultado = consultar_memoria(consulta="Atlas pgvector", memorias=dados, hoje=HOJE)
    assert resultado["rows"][0]["id"] == "a1"


def test_recall_recusa_id_repetido() -> None:
    with pytest.raises(MemoriaError):
        ler_memorias(texto="m1 | fato | 2026-01-01 | a.md | d | Um.\nm1 | fato | 2026-01-01 | a.md | d | Dois.")


# --------------------------------------------------------------- esquecimento


def test_esquecer_por_item_mede_raio_de_alcance() -> None:
    resultado = esquecer(memorias=MEMORIAS, ids="m2", escopo="item")
    assert resultado["metrics"]["apagadas"] == 1
    assert resultado["metrics"]["raio"] == 2
    assert "raio-de-alcance" in kinds(resultado)
    assert "dependentes" in kinds(resultado)


def test_esquecer_por_dataset_com_somente_memoria() -> None:
    resultado = esquecer(memorias=MEMORIAS, dataset="atlas", escopo="dataset", somente_memoria=True)
    assert resultado["metrics"]["apagadas"] == 4
    assert resultado["metrics"]["restantes"] == 1
    assert "somente-memoria" in kinds(resultado)


def test_esquecer_tudo_bloqueia() -> None:
    resultado = esquecer(memorias=MEMORIAS, escopo="tudo")
    assert "esquecimento-total" in kinds(resultado)
    assert "memoria-vazia" in kinds(resultado)
    assert resultado["counts"]["must"] == 2


def test_esquecer_recusa_entrada_ambigua() -> None:
    with pytest.raises(MemoriaError):
        esquecer(memorias=MEMORIAS, escopo="item")
    with pytest.raises(MemoriaError):
        esquecer(memorias=MEMORIAS, escopo="dataset")
    with pytest.raises(MemoriaError):
        esquecer(memorias=MEMORIAS, ids="nao-existe", escopo="item")
    with pytest.raises(MemoriaError):
        esquecer(memorias=MEMORIAS, ids="m1", escopo="planeta")


# ------------------------------------------------------------------ catalogo


def test_catalogo_publica_vias_pesos_e_limites() -> None:
    catalogo = memoria_catalogo()
    assert catalogo["versao"] == "0.42.0"
    assert [item["via"] for item in catalogo["vias"]] == list(VIAS)
    assert catalogo["roteamento"]["limiar"] == LIMIAR_ROTA
    assert catalogo["recall"]["bm25"]["k1"] == 1.2
    assert catalogo["limites"]["entradas"] == MAX_ENTRADAS
    assert catalogo["limites"]["resultados"] == MAX_RESULTADOS
    assert set(catalogo["entidades"]["tipos"]) == set(TIPOS_ENTIDADE)
    assert set(catalogo["entidades"]["tipos_memoria"]) == set(TIPOS_MEMORIA)
    assert catalogo["esquecimento"]["escopos"] == list(ESCOPOS_ESQUECIMENTO)
    assert catalogo["modos"] == list(MODOS)
    assert catalogo["executed"] is False and catalogo["readOnly"] is True


def test_catalogo_lista_todas_as_regras_de_roteamento() -> None:
    catalogo = memoria_catalogo()
    regras = catalogo["roteamento"]["regras"]
    assert len(regras) >= 25
    assert all(item["via"] in VIAS for item in regras)
    assert {item["via"] for item in regras} == set(VIAS)


# ------------------------------------------------------------------ registro


def test_registro_tem_as_sete_skills_de_memoria() -> None:
    registry = build_registry(__import__("pathlib").Path("/tmp/memoria-files"))  # noqa: F821
    itens = registry.list()
    memoria = [item for item in itens if item["id"].startswith("memoria.")]
    assert len(memoria) == 7
    assert len(itens) == 223
    assert all(item["category"] == "Memória" for item in memoria)
    assert all(item["sideEffects"] is False for item in memoria)


def test_registro_expoe_schema_de_entrada() -> None:
    registry = build_registry(__import__("pathlib").Path("/tmp/memoria-files"))  # noqa: F821
    roteamento = next(item for item in registry.list() if item["id"] == "memoria.roteamento")
    assert "consulta" in roteamento["inputSchema"]["properties"]
    assert roteamento["dryRunSupported"] is False


# ----------------------------------------------------------------- endpoints


def test_endpoint_de_roteamento_responde(client: TestClient) -> None:
    resposta = client.post(
        "/api/skills/memoria.roteamento/execute",
        json={"parameters": {"consulta": "Como faço para instalar o plugin?"}, "dryRun": False, "confirmed": True},
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["ok"] is True
    assert corpo["result"]["metrics"]["via"] == "procedimento"
    assert corpo["result"]["executed"] is False


def test_endpoint_de_recall_responde(client: TestClient) -> None:
    resposta = client.post(
        "/api/skills/memoria.recall/execute",
        json={"parameters": {"consulta": "índice vetorial", "memorias": MEMORIAS, "hoje": HOJE}, "dryRun": False, "confirmed": True},
    )
    assert resposta.json()["result"]["rows"][0]["id"] == "m1"


def test_endpoint_de_memoria_devolve_erro_de_entrada(client: TestClient) -> None:
    resposta = client.post(
        "/api/skills/memoria.roteamento/execute",
        json={"parameters": {"consulta": "  "}, "dryRun": False, "confirmed": True},
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["ok"] is False
    assert corpo["error"]["code"] == "SKILL_ERROR"


def test_endpoint_de_catalogo_nao_exige_parametro(client: TestClient) -> None:
    resposta = client.post("/api/skills/memoria.regras/execute", json={"parameters": {}})
    assert resposta.json()["result"]["vias"][0]["via"] == VIAS[0]
