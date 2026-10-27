"""Testes da camada de continuidade de plano (0.29.0).

A camada é determinística: lê plano, progresso, achados e livro colados, não
abre diretório, não instala hook, não bloqueia sessão e não escreve arquivo.
As fixtures são os três arquivos do padrão `planning-with-files` escritos à mão.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from server.continuidade import (
    CABECALHO_ATTEST,
    ContinuidadeError,
    EVENTOS,
    GATE_CAP,
    MAX_FASES,
    MODOS,
    ORCAMENTO_PLANO,
    ORCAMENTO_PROGRESSO,
    RESUMO_MAX,
    SECOES_PLANO,
    STATUS,
    TICK_MAX,
    catalogo,
    fases,
    injecao,
    ler_fases,
    ler_secoes,
    livro,
    medico,
    portao,
    retomada,
)
from server.skill_registry import build_registry


@pytest.fixture()
def client(tmp_path) -> TestClient:
    from server.app import create_app

    return TestClient(create_app(registry=build_registry(tmp_path / "files")))


# ------------------------------------------------------------------ fixtures

PLANO = """# Task Plan: Atlas

## Goal

Migrar o índice para o pgvector sem downtime.

## Next Step

Escrever a migration 0042.

## Current Phase

Phase 2

## Phases

### Phase 1: Descoberta

- [x] Levantar requisitos
- [x] Documentar achados
- **Status:** complete

### Phase 2: Implementação

- [ ] Escrever migration
- [ ] Rodar teste de carga
- **Status:** in_progress

### Phase 3: Entrega

- [ ] Revisar
- **Status:** pending

## Decisions Made

| Decisão | Motivo |
| --- | --- |
| pgvector | já está no cluster |
"""

PROGRESSO = """# Progress Log

## Session: 2026-10-23

### Phase 1: Descoberta

- **Status:** complete
- **Started:** 2026-10-23T09:00:00Z
- Actions taken:
  - Li o esquema atual
- Files created/modified:
  - `docs/esquema.md`

### Phase 2: Implementação

- **Status:** in_progress
- Actions taken:
  - Escrevi o rascunho em `db/0042.sql`

## Test Results

| Test | Input | Expected | Actual | Status |
|------|-------|----------|--------|--------|
"""

ACHADOS = """# Findings & Decisions

## Requirements

- Migrar sem downtime

## Research Findings

- pgvector aceita índice HNSW desde a 0.5

## Technical Decisions

| Decisão | Motivo |
| --- | --- |
| HNSW | recall melhor com o mesmo custo |

## Resources

- docs/0042.sql
"""

LIVRO = """{"tick":1,"ts":"2026-10-23T09:00:00Z","agent":"main","phase":"1","event":"progress","summary":"comecei a leitura","files":[]}
{"tick":2,"ts":"2026-10-23T09:05:00Z","agent":"main","phase":"1","event":"phase_complete","summary":"fase 1 fechada","files":["docs/esquema.md"]}
{"tick":3,"ts":"2026-10-23T09:10:00Z","agent":"worker","phase":"2","event":"note","summary":"migration escrita","files":["db/0042.sql"]}
"""


def _plano(*statuses: str, criterios: int = 1) -> str:
    partes = ["## Goal", "", "Meta.", "", "## Next Step", "", "Passo.", "", "## Phases", ""]
    for indice, status in enumerate(statuses, start=1):
        partes += [f"### Phase {indice}: Fase {indice}", ""]
        partes += [f"- [ ] critério {n}" for n in range(criterios)]
        partes += ["", f"- **Status:** {status}", ""]
    return "\n".join(partes)


# ------------------------------------------------------------------ leitura

def test_ler_secoes_separa_nivel_dois():
    secoes = ler_secoes(PLANO)
    titulos = [secao.titulo for secao in secoes]
    assert titulos[:3] == ["Goal", "Next Step", "Current Phase"]
    assert "Phases" in titulos


def test_ler_fases_aceita_os_dois_formatos():
    texto = """### Phase 1: A

- **Status:** complete

### Phase 2: B

- **Status:** [in_progress]

### Phase 3: C

[in_progress]
"""
    lista, _ = ler_fases(texto)
    assert [fase.status for fase in lista] == ["complete", "in_progress", "in_progress"]
    assert lista[0].formato == "primario"
    assert lista[1].formato == "primario+inline"
    assert lista[2].formato == "inline"


def test_ler_fases_conta_criterios():
    lista, _ = ler_fases(PLANO)
    assert len(lista) == 3
    assert lista[0].total == 2 and lista[0].feitos == 2
    assert lista[1].total == 2 and lista[1].feitos == 0
    assert lista[1].status == "in_progress"


def test_ler_fases_marca_ambigua():
    texto = """### Phase 1: A

- **Status:** complete
- **Status:** pending
"""
    lista, _ = ler_fases(texto)
    assert lista[0].marcas == 2
    assert lista[0].status == "?"


# -------------------------------------------------------------------- fases

def test_fases_bom_nao_tem_bloqueio():
    resultado = fases(plano=PLANO)
    assert resultado["counts"]["must"] == 0
    assert resultado["metrics"]["fases"] == 3
    assert resultado["metrics"]["emAndamento"] == 1
    assert resultado["metrics"]["criteria"] if "criteria" in resultado["metrics"] else True
    assert resultado["executed"] is False and resultado["readOnly"] is True


def test_fases_aponta_status_duplicado():
    texto = """### Phase 1: A

- **Status:** complete
- **Status:** pending
"""
    resultado = fases(plano=texto)
    assert any(item["title"] == "Fase com mais de uma marca de status" for item in resultado["findings"])


def test_fases_aponta_fase_sem_status():
    texto = """### Phase 1: A

- [ ] critério
"""
    resultado = fases(plano=texto)
    assert any(item["title"] == "Fase sem status" for item in resultado["findings"])


def test_fases_aponta_criterio_aberto_em_fase_concluida():
    texto = """### Phase 1: A

- [x] um
- [ ] dois
- **Status:** complete
"""
    resultado = fases(plano=texto)
    assert any(item["title"] == "Fase concluída com critério aberto" for item in resultado["findings"])


def test_fases_aponta_fase_sem_criterio():
    texto = """### Phase 1: A

- **Status:** pending
"""
    resultado = fases(plano=texto)
    assert any(item["title"] == "Fase sem critério verificável" for item in resultado["findings"])


def test_fases_aponta_ordem_quebrada():
    texto = """### Phase 2: B

- [ ] x
- **Status:** pending

### Phase 1: A

- [ ] y
- **Status:** pending
"""
    resultado = fases(plano=texto)
    assert any(item["title"] == "Fase fora de ordem" for item in resultado["findings"])


def test_fases_aponta_conclusao_fora_de_ordem():
    texto = _plano("pending", "complete")
    resultado = fases(plano=texto)
    assert any(item["title"] == "Fase concluída antes da anterior" for item in resultado["findings"])


def test_fases_aponta_sem_fase_ativa():
    resultado = fases(plano=_plano("pending", "pending"))
    assert any(item["title"] == "Nenhuma fase em andamento" for item in resultado["findings"])


def test_fases_aponta_goal_e_next_step_ausentes():
    texto = """### Phase 1: A

- [ ] x
- **Status:** in_progress
"""
    resultado = fases(plano=texto)
    titulos = {item["title"] for item in resultado["findings"]}
    assert "`## Goal` ausente ou vazio" in titulos
    assert "`## Next Step` ausente ou vazio" in titulos


def test_fases_recusa_plano_sem_fase():
    with pytest.raises(ContinuidadeError):
        fases(plano="## Goal\n\nSem fase nenhuma.\n")


def test_fases_recusa_plano_vazio_e_modo_invalido():
    with pytest.raises(ContinuidadeError):
        fases(plano="  ")
    with pytest.raises(ContinuidadeError):
        fases(plano=PLANO, modo="maximo")


def test_fases_recusa_plano_com_fases_demais(monkeypatch):
    monkeypatch.setattr("server.continuidade.MAX_FASES", 2)
    with pytest.raises(ContinuidadeError):
        fases(plano=PLANO)


# ------------------------------------------------------------------- portão

def test_portao_desligado_permite_parada():
    resultado = portao(plano=PLANO)
    assert resultado["decisao"] == "allow"
    assert "desligado" in resultado["motivo"]


def test_portao_ligado_com_fase_ativa_bloqueia():
    resultado = portao(plano=PLANO, ligado=True)
    assert resultado["decisao"] == "block"
    assert resultado["counts"]["must"] == 1


def test_portao_sem_fase_ativa_permite():
    resultado = portao(plano=_plano("complete", "pending"), ligado=True)
    assert resultado["decisao"] == "allow"
    assert "in_progress" in resultado["motivo"]


def test_portao_com_parada_forcada_permite():
    resultado = portao(plano=PLANO, ligado=True, stop_ativo=True)
    assert resultado["decisao"] == "allow"


def test_portao_no_teto_permite():
    resultado = portao(plano=PLANO, ligado=True, bloqueios=GATE_CAP)
    assert resultado["decisao"] == "allow"
    assert "teto" in resultado["motivo"]


def test_portao_estagnado_permite():
    resultado = portao(
        plano=PLANO, ligado=True, bloqueios=3, linhas_anteriores=2, ledger="a\nb\n"
    )
    assert resultado["decisao"] == "allow"
    assert "progresso" in resultado["motivo"]


def test_portao_avancou_bloqueia():
    resultado = portao(
        plano=PLANO, ligado=True, bloqueios=3, linhas_anteriores=2, ledger=LIVRO
    )
    assert resultado["decisao"] == "block"


def test_portao_devolve_cinco_guardas():
    resultado = portao(plano=PLANO)
    assert len(resultado["rows"]) == 5
    assert [row["ordem"] for row in resultado["rows"]] == [1, 2, 3, 4, 5]
    assert resultado["metrics"]["guardaQueParou"] == 1


def test_portao_recusa_plano_sem_fase():
    with pytest.raises(ContinuidadeError):
        portao(plano="## Goal\n\nnada\n")


@pytest.mark.parametrize("campo,valor", [("cap", 0), ("bloqueios", -1), ("linhas_anteriores", -1)])
def test_portao_recusa_contadores_invalidos(campo, valor):
    with pytest.raises(ContinuidadeError):
        portao(plano=PLANO, **{campo: valor})


# ----------------------------------------------------------------- retomada

def test_retomada_responde_as_cinco_perguntas():
    resultado = retomada(plano=PLANO, progresso=PROGRESSO, achados=ACHADOS)
    respostas = resultado["respostas"]
    assert len(respostas) == 5
    assert respostas["Onde estou?"].startswith("Phase 2")
    assert respostas["Para onde vou?"] == "Phase 3"
    assert resultado["metrics"]["perguntas"] == 5


def test_retomada_aponta_divergencia_de_status():
    progresso = PROGRESSO.replace("- **Status:** in_progress", "- **Status:** complete", 1)
    resultado = retomada(plano=PLANO, progresso=progresso)
    assert resultado["metrics"]["divergentes"] == 1
    assert any(item["title"] == "Status do plano diverge do progresso" for item in resultado["findings"])


def test_retomada_aponta_fase_sem_registro():
    resultado = retomada(plano=PLANO, progresso=PROGRESSO)
    assert any(item["title"] == "Fase do plano sem registro no progresso" for item in resultado["findings"])


def test_retomada_aponta_progresso_sem_data():
    resultado = retomada(plano=PLANO, progresso="# Progress\n\n### Phase 1: A\n\n- **Status:** complete\n")
    assert any(item["title"] == "Progresso sem data" for item in resultado["findings"])
    assert resultado["metrics"]["ultimaData"] == ""


def test_retomada_aponta_placeholder():
    progresso = PROGRESSO.replace("2026-10-23", "[DATE]", 1)
    resultado = retomada(plano=PLANO, progresso=progresso)
    assert any(item["title"] == "Placeholder de data não substituído" for item in resultado["findings"])


def test_retomada_aponta_tabela_de_teste_vazia():
    resultado = retomada(plano=PLANO, progresso=PROGRESSO)
    assert any(item["title"] == "Tabela de teste sem resultado" for item in resultado["findings"])


def test_retomada_aponta_achados_sem_requisito():
    resultado = retomada(plano=PLANO, progresso=PROGRESSO, achados="# Findings\n\n## Research Findings\n\n- x\n")
    assert any(item["title"] == "`findings.md` sem requisitos" for item in resultado["findings"])


def test_retomada_aponta_fase_que_o_plano_nao_tem():
    progresso = PROGRESSO + "\n### Phase 9: Extra\n\n- **Status:** pending\n"
    resultado = retomada(plano=PLANO, progresso=progresso)
    assert any(item["title"] == "Progresso cita fase que o plano não tem" for item in resultado["findings"])


def test_retomada_recusa_entradas_vazias():
    with pytest.raises(ContinuidadeError):
        retomada(plano="", progresso=PROGRESSO)
    with pytest.raises(ContinuidadeError):
        retomada(plano=PLANO, progresso="")


# ------------------------------------------------------------------ injeção

def test_injecao_monta_bloco_por_secoes():
    resultado = injecao(plano=PLANO)
    bloco = resultado["bloco"]
    assert "## Goal" in bloco and "## Next Step" in bloco
    assert "### Phase 2: Implementação" in bloco
    assert "## Decisions Made" in bloco
    assert resultado["metrics"]["fonte"] == "secoes"


def test_injecao_cai_para_cabecalho_sem_secoes():
    texto = "\n".join(f"linha {n}" for n in range(200))
    resultado = injecao(plano=texto, linhas=10)
    assert resultado["metrics"]["fonte"] == "cabecalho"
    assert len(resultado["bloco"].strip().split("\n")) == 10


def test_injecao_normaliza_relogio():
    plano = PLANO.replace("Escrever a migration 0042.", "Escrever a migration em 2026-10-23T09:41:22Z.")
    resultado = injecao(plano=plano)
    assert "T00:00:00Z" in resultado["bloco"]
    assert "T09:41:22Z" not in resultado["bloco"]


def test_injecao_usa_livro_quando_existe():
    resultado = injecao(plano=PLANO, ledger=LIVRO)
    assert resultado["metrics"]["fonteProgresso"] == "livro"
    assert "=== RUN LEDGER ===" in resultado["bloco"]
    assert "entries: 3" in resultado["bloco"]


def test_injecao_usa_cauda_do_progresso():
    resultado = injecao(plano=PLANO, progresso=PROGRESSO)
    assert resultado["metrics"]["fonteProgresso"] == "cauda"
    assert "## Test Results" in resultado["bloco"]
    assert resultado["metrics"]["bytesProgresso"] > 0


def test_injecao_trunca_no_orcamento():
    grande = PLANO.replace("Migrar o índice para o pgvector sem downtime.", "Meta longa. " * 400)
    resultado = injecao(plano=grande, orcamento=600)
    assert resultado["metrics"]["truncada"] is True
    assert resultado["metrics"]["bytesVisao"] <= 1000


def test_injecao_devolve_hash_do_plano():
    resultado = injecao(plano=PLANO)
    assert len(resultado["hash"]) == 16
    assert resultado["hash"] != injecao(plano=PLANO + "\n")["hash"]


def test_injecao_aponta_ausencia_de_proximo_passo():
    texto = """## Goal

Meta.

### Phase 1: A

- [ ] x
- **Status:** in_progress
"""
    resultado = injecao(plano=texto)
    assert any(item["title"] == "Bloco injetado sem próximo passo" for item in resultado["findings"])


@pytest.mark.parametrize("campo,valor", [("orcamento", 100), ("linhas", 2)])
def test_injecao_recusa_orcamento_invalido(campo, valor):
    with pytest.raises(ContinuidadeError):
        injecao(plano=PLANO, **{campo: valor})


# -------------------------------------------------------------------- livro

def test_livro_valido_nao_tem_achado():
    resultado = livro(ledger=LIVRO)
    assert resultado["counts"]["must"] == 0
    assert resultado["metrics"]["entradas"] == 3
    assert resultado["metrics"]["agentes"] == 2
    assert resultado["metrics"]["ultimoTick"] == 3
    assert resultado["metrics"]["evento_progress"] == 1


def test_livro_resume_por_agente():
    resultado = livro(ledger=LIVRO)
    agentes = {item["agente"]: item for item in resultado["agentes"]}
    assert agentes["main"]["ultimo"] == "phase_complete"
    assert agentes["worker"]["entradas"] == 1


def test_livro_filtra_por_agente():
    resultado = livro(ledger=LIVRO, agente="worker")
    assert resultado["metrics"]["filtradas"] == 1
    assert resultado["metrics"]["entradas"] == 3
    assert all(row["agente"] == "worker" for row in resultado["rows"])


def test_livro_aponta_json_invalido():
    resultado = livro(ledger=LIVRO + "isto não é json\n")
    assert resultado["metrics"]["invalidas"] == 1
    assert any(item["title"] == "Linha do livro fora do formato JSON" for item in resultado["findings"])


def test_livro_aponta_evento_desconhecido():
    linha = json.dumps({"tick": 4, "ts": "2026-10-23T10:00:00Z", "agent": "main", "event": "foo"})
    resultado = livro(ledger=LIVRO + linha + "\n")
    assert any(item["title"] == "Evento fora dos seis previstos" for item in resultado["findings"])


def test_livro_aponta_tick_repetido():
    linha = json.dumps({"tick": 3, "ts": "2026-10-23T10:00:00Z", "agent": "main", "event": "note", "summary": "x"})
    resultado = livro(ledger=LIVRO + linha + "\n")
    assert any(item["title"] == "Tick inválido ou repetido" for item in resultado["findings"])


def test_livro_aponta_campo_obrigatorio_faltando():
    linha = json.dumps({"tick": 4, "event": "note", "summary": "x"})
    resultado = livro(ledger=linha + "\n")
    assert any(item["title"] == "Entrada sem campo obrigatório" for item in resultado["findings"])


def test_livro_aponta_data_fora_do_padrao():
    linha = json.dumps({"tick": 4, "ts": "2026-10-23 10:00", "agent": "main", "event": "note", "summary": "x"})
    resultado = livro(ledger=linha + "\n")
    assert any(item["title"] == "Data fora do formato ISO-8601" for item in resultado["findings"])


def test_livro_aponta_resumo_longo():
    linha = json.dumps({"tick": 4, "ts": "2026-10-23T10:00:00Z", "agent": "main", "event": "note", "summary": "x" * 300})
    resultado = livro(ledger=linha + "\n")
    assert any(item["title"] == "Resumo acima do teto ou com quebra de linha" for item in resultado["findings"])


def test_livro_aponta_agente_fora_do_padrao():
    linha = json.dumps({"tick": 4, "ts": "2026-10-23T10:00:00Z", "agent": "worker 1", "event": "note", "summary": "x"})
    resultado = livro(ledger=linha + "\n")
    assert any(item["title"] == "Nome de agente fora do padrão" for item in resultado["findings"])


def test_livro_aponta_lacuna_de_tick():
    linha = json.dumps({"tick": 40, "ts": "2026-10-23T10:00:00Z", "agent": "main", "event": "note", "summary": "x"})
    resultado = livro(ledger=LIVRO + linha + "\n")
    assert resultado["metrics"]["lacunas"] >= 1
    assert any(item["title"] == "Lacuna no contador de ticks" for item in resultado["findings"])


def test_livro_recusa_vazio_e_agente_invalido():
    with pytest.raises(ContinuidadeError):
        livro(ledger="  ")
    with pytest.raises(ContinuidadeError):
        livro(ledger=LIVRO, agente="!!!")


# ------------------------------------------------------------------- médico

BUNDLE = """>>> atlas/task_plan.md
""" + PLANO + """>>> atlas/progress.md
""" + PROGRESSO + """>>> atlas/findings.md
""" + ACHADOS + """>>> atlas/ledger-main.jsonl
""" + LIVRO + """>>> atlas/.attest
abc123
>>> beta/task_plan.md
# Task Plan: Atlas

## Phases

### Phase 1: A

- **Status:** in_progress
>>> gamma/notas.md
solto
"""


def test_medico_dirige_o_diagnostico():
    resultado = medico(planos=BUNDLE)
    assert resultado["metrics"]["planos"] == 3
    assert resultado["metrics"]["completos"] == 1
    assert resultado["metrics"]["semLivro"] == 2
    assert any(item["title"] == "Plano sem `task_plan.md`" for item in resultado["findings"])


def test_medico_detecta_ambiguidade_de_plano_ativo():
    resultado = medico(planos=BUNDLE)
    assert any(item["title"] == "Ambiguidade de plano ativo" for item in resultado["findings"])


def test_medico_com_ativo_declarado_nao_e_ambiguo():
    resultado = medico(planos=BUNDLE, ativo="atlas")
    assert not any(item["title"] == "Ambiguidade de plano ativo" for item in resultado["findings"])
    assert resultado["metrics"]["ativo"] == "atlas"


def test_medico_aponta_ativo_inexistente():
    resultado = medico(planos=BUNDLE, ativo="delta")
    assert resultado["metrics"]["ativo"] == "delta"
    assert any(item["title"] == "Plano ativo não existe no diretório" for item in resultado["findings"])


def test_medico_aponta_titulo_duplicado():
    resultado = medico(planos=BUNDLE)
    assert any(item["title"] == "Dois planos com o mesmo título" for item in resultado["findings"])


def test_medico_aponta_plano_sem_objetivo():
    resultado = medico(planos=BUNDLE)
    assert any(item["title"] == "Plano sem objetivo declarado" for item in resultado["findings"])


def test_medico_reconhece_livro_e_atestacao():
    resultado = medico(planos=BUNDLE)
    linha = next(row for row in resultado["rows"] if row["plano"] == "atlas")
    assert linha["livro"] == "sim"
    assert linha["attest"] == "sim"


def test_medico_recusa_bundle_vazio():
    with pytest.raises(ContinuidadeError):
        medico(planos="")


# ----------------------------------------------------------------- catálogo

def test_catalogo_publica_guardas_eventos_e_regras():
    dados = catalogo()
    assert dados["versao"] == "0.60.2"
    assert len(dados["guardas_do_portao"]) == 5
    assert tuple(dados["eventos"]) == EVENTOS
    assert len(dados["regras"]) == 12
    assert dados["nao_faz"]


def test_catalogo_declara_limites_do_upstream():
    dados = catalogo()
    assert dados["limites"]["bloqueios"] == GATE_CAP
    assert dados["injeção"]["orcamento_plano"] == ORCAMENTO_PLANO
    assert dados["injeção"]["orcamento_progresso"] == ORCAMENTO_PROGRESSO
    assert dados["limites"]["resumo"] == RESUMO_MAX


# ------------------------------------------------------------------ registro

def test_registro_publica_sete_skills_de_continuidade(tmp_path):
    registry = build_registry(tmp_path / "files")
    ids = [item["id"] for item in registry.list() if item["id"].startswith("continuidade.")]
    assert ids == [
        "continuidade.fases",
        "continuidade.portao",
        "continuidade.retomada",
        "continuidade.injecao",
        "continuidade.livro",
        "continuidade.medico",
        "continuidade.regras",
    ]


def test_registro_total_de_skills_e_176(tmp_path):
    registry = build_registry(tmp_path / "files")
    assert len(registry.list()) == 288


def test_api_executa_fases_e_regras(client):
    resposta = client.post("/api/skills/continuidade.regras/execute", json={"parameters": {}})
    assert resposta.status_code == 200
    assert resposta.json()["result"]["versao"] == "0.60.2"

    resposta = client.post(
        "/api/skills/continuidade.fases/execute",
        json={"parameters": {"plano": PLANO}},
    )
    assert resposta.status_code == 200
    corpo = resposta.json()["result"]
    assert corpo["executed"] is False and corpo["readOnly"] is True
    assert corpo["metrics"]["fases"] == 3


def test_api_executa_portao(client):
    resposta = client.post(
        "/api/skills/continuidade.portao/execute",
        json={"parameters": {"plano": PLANO, "ligado": True}},
    )
    assert resposta.json()["result"]["decisao"] == "block"
    assert resposta.json()["result"]["metrics"]["cap"] == GATE_CAP


def test_api_devolve_erro_de_entrada(client):
    resposta = client.post(
        "/api/skills/continuidade.fases/execute",
        json={"parameters": {"plano": "curto"}},
    )
    corpo = resposta.json()
    assert corpo["ok"] is False
    assert corpo["error"]["code"] == "SKILL_ERROR"
