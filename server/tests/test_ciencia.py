"""Testes do rigor científico inspirado em K-Dense-AI/scientific-agent-skills (MIT).

Nada do upstream é executado, baixado ou importado: as fixtures são trechos de
métodos, tabelas de validação e números de poder, e as contas são feitas em
Python sobre eles. Nenhum modelo de linguagem participa.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server.app import create_app
from server.ciencia import (
    BENCHMARKS,
    CienciaError,
    DIRETRIZES,
    ITENS_REPRO,
    auditar_desenho,
    auditar_estatistica,
    auditar_manuscrito,
    auditar_reprodutibilidade,
    ciencia_catalogo,
    dimensionar_estudo,
    validar_metodo,
)
from server.skill_registry import build_registry

# ------------------------------------------------------------------ fixtures

RESULTADOS = (
    "Houve diferença significativa entre os grupos (t = 3,82; p < 0,05), com "
    "média de 75,2 e desvio de 8,5 no grupo A. A correlação entre dose e resposta "
    "foi forte. Não houve diferença entre B e C, portanto os tratamentos são "
    "equivalentes. O intervalo foi IC 95% [1,18; 2,42] e n = 48."
)

METODOS_COMPLETOS = (
    "Ensaio randomizado com alocação oculta em envelopes opacos. A randomização "
    "foi feita em blocos de quatro por sorteio. O cegamento foi duplo: participante, "
    "quem aplicou e quem mediu não sabiam o grupo. Havia grupo controle concorrente "
    "com placebo. A unidade experimental foi cada paciente, e cada animal recebeu "
    "só um tratamento. O desfecho primário foi dor aos 30 dias. O tamanho amostral "
    "foi calculado com poder de 80%, alfa 0,05 e efeito de 0,5. O protocolo foi "
    "pré-registrado no ClinicalTrials.gov (NCT01234567). Critérios de inclusão: "
    "adultos; exclusão: gestantes. Perdidos: 2 por desistência. A análise primária "
    "foi pré-especificada."
)

METODOS_FRACOS = (
    "Os pacientes foram alocados por conveniência, conforme chegavam ao ambulatório. "
    "Todas as amostras do grupo tratado foram processadas na segunda-feira e as do "
    "controle na terça. Foram usados 3 camundongos com 100 células cada. "
    "O resultado foi medido pelo pesquisador que aplicou o tratamento."
)

REPRO_COMPLETO = (
    "Os dados estão disponíveis no Zenodo (doi 10.5281/zenodo.1234567) e o código "
    "em https://github.com/exemplo/analise, commit 4f2a1c. As versões foram Python "
    "3.11.4, numpy 2.1.0 e statsmodels 0.14.2. A semente foi fixada em 42. O "
    "ambiente está em Docker (imagem exemplo/analise:1.0). O protocolo foi "
    "pré-registrado no OSF. Os dados brutos têm accession GSE123456. Licença CC BY 4.0. "
    "Reagentes: Sigma, catálogo 12345, lote 67."
)

REPRO_RESTRITO = (
    "Os métodos seguiram o protocolo interno. Os dados estão disponíveis sob "
    "solicitação aos autores. Não há repositório de código."
)

DADOS_VALIDACAO = """1,9.8,10,1
1,10.2,10,1
1,10.0,10,2
1,10.1,10,2
1,9.9,10,2
10,49.0,50,1
10,51.0,50,1
10,50.0,50,2
10,49.5,50,2
10,50.5,50,2
"""

CURVA_BOA = """0,0.02
5,5.1
10,10.1
20,19.9
40,40.2
"""

CURVA_RUIM = """0,0.5
5,5.9
10,7.4
20,24.8
40,33.1
"""

MANUSCRITO = """Resumo
Ensaio randomizado, duplo-cego, com 80 participantes.

Introdução
O tratamento é tema de interesse clínico.

Métodos
Randomização por sorteio em blocos, alocação oculta em envelopes, cegamento duplo,
grupo controle com placebo, fluxo de participantes: 88 triados, 80 alocados.
Desfecho primário: dor aos 30 dias. Tamanho amostral calculado com poder de 80%.

Resultados
A diferença foi significativa (t(78) = 3,1; p = 0,003), d = 0,7, IC 95% [0,2; 1,2], n = 80.

Discussão
O achado é compatível com a literatura e limitações incluem seguimento curto.

Conclusão
O tratamento é promissor.

Financiamento
FAPESP 2024/12345-6.

Conflito de interesse
Nenhum declarado.

Ética
Aprovado pelo CEP 1234, com consentimento livre e esclarecido.

Disponibilidade de dados
Dados no Zenodo (doi 10.5281/zenodo.1).

Contribuições
Concepção e desenho por A; análise por B.

Referências
1. Silva et al., 2024.
"""


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> TestClient:
    return TestClient(create_app(registry=build_registry(tmp_path_factory.mktemp("ciencia"))))


def kinds(resultado: dict) -> set[str]:
    return {achado["kind"] for achado in resultado["findings"]}


# ------------------------------------------------------------------- amostra


def test_proportions_match_the_two_proportion_formula() -> None:
    """3% → 3,6% é a mesma conta que o módulo de marketing faz para 3% com ganho de 20%."""
    resultado = dimensionar_estudo(teste="proporcoes", baseline=3.0, efeito=20.0)
    assert resultado["metrics"]["n1"] == 13_914
    assert resultado["metrics"]["n2"] == 13_914
    assert resultado["metrics"]["total"] == 27_828
    assert resultado["metrics"]["poder_calculado"] >= 0.80


def test_means_follow_cohens_d() -> None:
    resultado = dimensionar_estudo(teste="medias", cohen_d=0.5)
    assert resultado["metrics"]["n1"] == 63
    assert resultado["metrics"]["n2"] == 63
    assert "d = 0,50" in resultado["metrics"]["efeito"]


def test_dropout_inflates_the_enrolled_sample() -> None:
    resultado = dimensionar_estudo(teste="medias", cohen_d=0.5, perda=0.20)
    assert resultado["metrics"]["total"] == 126
    assert resultado["metrics"]["matricula"] == 158
    assert any("matrícula" in linha["etapa"].lower() for linha in resultado["rows"])


def test_bonferroni_divides_alpha_and_raises_n() -> None:
    simples = dimensionar_estudo(teste="medias", cohen_d=0.5)
    multiplo = dimensionar_estudo(teste="medias", cohen_d=0.5, comparacoes=4)
    assert multiplo["metrics"]["alfa_ajustado"] == pytest.approx(0.0125)
    assert multiplo["metrics"]["n1"] > simples["metrics"]["n1"]
    assert "multiplicidade" in kinds(multiplo)


def test_cluster_design_effect_multiplies_the_sample() -> None:
    resultado = dimensionar_estudo(teste="medias", cohen_d=0.5, tamanho_cluster=20, icc=0.05)
    assert resultado["metrics"]["deff"] == pytest.approx(1.95)
    assert resultado["metrics"]["n1"] > 63


def test_small_effect_is_flagged_as_a_convention_problem() -> None:
    resultado = dimensionar_estudo(teste="medias", cohen_d=0.12)
    assert "efeito-pequeno" in kinds(resultado)


def test_fixed_n_reports_realized_power_and_can_be_under_80() -> None:
    resultado = dimensionar_estudo(teste="medias", cohen_d=0.3, n_por_grupo=40)
    assert resultado["metrics"]["n1"] == 40
    assert resultado["metrics"]["poder_calculado"] < 0.8
    assert "poder-baixo" in kinds(resultado)


def test_proportions_effect_uses_percentage_points() -> None:
    resultado = dimensionar_estudo(teste="proporcoes", baseline=10.0, efeito=50.0)
    assert resultado["metrics"]["efeito"] == "5,00 p.p."


def test_sample_validation_rejects_impossible_input() -> None:
    with pytest.raises(CienciaError):
        dimensionar_estudo(teste="anova")
    with pytest.raises(CienciaError):
        dimensionar_estudo(teste="proporcoes", baseline=3.0, efeito=20.0, alfa=0.9)
    with pytest.raises(CienciaError):
        dimensionar_estudo(teste="proporcoes", baseline=3.0, efeito=20.0, poder=0.3)
    with pytest.raises(CienciaError):
        dimensionar_estudo(teste="medias")


# --------------------------------------------------------------- estatística


def test_statistics_audit_flags_the_classic_errors() -> None:
    resultado = auditar_estatistica(texto=RESULTADOS)
    encontrados = kinds(resultado)
    assert "p-zero" not in encontrados
    assert "limiar-em-vez-de-valor" in encontrados
    assert "sem-graus-de-liberdade" in encontrados
    assert "sem-efeito" in encontrados
    assert "equivalencia-sem-margem" in encontrados
    assert "correlacao-sem-r" in encontrados
    assert resultado["metrics"]["p_citados"] == 1


def test_statistics_audit_refuses_p_zero_and_p_above_one() -> None:
    assert "p-zero" in kinds(auditar_estatistica(texto="O efeito foi significativo, p = 0,000, com n = 40."))
    assert "p-impossivel" in kinds(auditar_estatistica(texto="O efeito foi significativo, p = 1,4, com n = 40."))


def test_statistics_audit_flags_trend_language() -> None:
    texto = "A diferença foi marginalmente significativa (p = 0,07), com n = 30 e d = 0,3."
    assert "tendencia" in kinds(auditar_estatistica(texto=texto))


def test_statistics_audit_flags_inverted_interval() -> None:
    texto = "A diferença foi d = 0,5, IC 95% [2,42; 1,18], com n = 48."
    assert "ic-invertido" in kinds(auditar_estatistica(texto=texto))


def test_statistics_audit_flags_zero_dispersion_and_percent_with_small_n() -> None:
    texto = "A média foi 12,4 ± 0,0 em 8 pacientes, o que representa 62,5% da amostra (n = 8)."
    resultado = auditar_estatistica(texto=texto)
    assert "dispersao-zero" in kinds(resultado)
    assert "percentual-n-baixo" in kinds(resultado)


def test_statistics_audit_requires_effect_and_interval() -> None:
    texto = "O grupo tratado diferiu do controle (p = 0,004) em 40 participantes."
    resultado = auditar_estatistica(texto=texto)
    assert "sem-efeito" in kinds(resultado)
    assert "sem-intervalo" in kinds(resultado)


def test_statistics_audit_accepts_a_complete_paragraph() -> None:
    texto = ("O grupo tratado apresentou média 75,2 (DP 8,5) contra 68,3 (DP 9,2) no controle, "
             "t(98) = 3,82, p = 0,0002, d = 0,77, IC 95% [0,36; 1,18], n = 100.")
    resultado = auditar_estatistica(texto=texto)
    assert resultado["counts"]["must"] == 0
    assert resultado["metrics"]["n_declarado"] == 100


def test_statistics_validation_requires_enough_text() -> None:
    with pytest.raises(CienciaError):
        auditar_estatistica(texto="p = 0,03")


# -------------------------------------------------------------------- desenho


def test_design_audit_accepts_complete_methods() -> None:
    resultado = auditar_desenho(texto=METODOS_COMPLETOS, tipo="ensaio")
    assert resultado["metrics"]["cobertura"] >= 90
    assert resultado["counts"]["must"] == 0


def test_design_audit_flags_convenience_and_pseudoreplication() -> None:
    resultado = auditar_desenho(texto=METODOS_FRACOS, tipo="animal")
    encontrados = kinds(resultado)
    assert "atribuicao-por-conveniencia" in encontrados
    assert "pseudorreplicacao" in encontrados
    assert "sem-randomizacao" in encontrados
    assert "sem-controle" in encontrados


def test_observational_design_requires_confounding_control_not_randomization() -> None:
    resultado = auditar_desenho(texto=METODOS_COMPLETOS, tipo="observacional")
    encontrados = kinds(resultado)
    assert "sem-confundimento" in encontrados
    assert "sem-randomizacao" not in encontrados

    ajustado = METODOS_COMPLETOS + " Os confundidores foram idade e sexo, com ajuste por regressão."
    resultado2 = auditar_desenho(texto=ajustado, tipo="observacional")
    assert "sem-confundimento" not in kinds(resultado2)


def test_design_audit_reports_coverage_and_evidence() -> None:
    resultado = auditar_desenho(texto=METODOS_COMPLETOS)
    assert resultado["metrics"]["presentes"] >= 10
    assert all("evidencia" in linha for linha in resultado["rows"])
    assert resultado["executed"] is False


def test_design_validation_rejects_short_text_and_bad_type() -> None:
    with pytest.raises(CienciaError):
        auditar_desenho(texto="randomizado")
    with pytest.raises(CienciaError):
        auditar_desenho(texto=METODOS_COMPLETOS, tipo="meta-analise")


# ----------------------------------------------------------- reprodutibilidade


def test_reproducibility_audit_accepts_complete_material() -> None:
    resultado = auditar_reprodutibilidade(texto=REPRO_COMPLETO)
    assert resultado["metrics"]["ausentes"] == 0
    assert resultado["counts"]["must"] == 0


def test_reproducibility_audit_flags_request_only_access() -> None:
    resultado = auditar_reprodutibilidade(texto=REPRO_RESTRITO)
    encontrados = kinds(resultado)
    assert "acesso-por-solicitacao" in encontrados
    assert "sem-codigo" in encontrados
    assert "cobertura-baixa" in encontrados


def test_reproducibility_version_requires_a_number() -> None:
    texto = "O protocolo foi aprovado. A versão do comitê é a vigente. Os dados estão no Zenodo."
    resultado = auditar_reprodutibilidade(texto=texto)
    assert "sem-versao" in kinds(resultado)


def test_reproducibility_requires_minimum_text() -> None:
    with pytest.raises(CienciaError):
        auditar_reprodutibilidade(texto="Dados no Zenodo.")


# ----------------------------------------------------------------- validação


def test_method_validation_computes_recovery_and_precision() -> None:
    resultado = validar_metodo(dados=DADOS_VALIDACAO, curva=CURVA_BOA)
    assert resultado["metrics"]["niveis"] == 2
    assert resultado["metrics"]["r2"] >= 0.999
    assert resultado["metrics"]["lod"] > 0
    assert resultado["counts"]["must"] == 0


def test_method_validation_flags_recovery_out_of_criteria() -> None:
    dados = "1,7.0,10,1\n1,7.2,10,1\n1,7.1,10,2\n10,70.0,100,1\n10,71.0,100,1\n10,70.5,100,2"
    resultado = validar_metodo(dados=dados, tipo="cromatografico")
    assert "recuperacao-fora" in kinds(resultado)
    assert resultado["counts"]["must"] >= 1


def test_method_validation_widens_the_limit_at_the_lowest_level() -> None:
    dados = "1,11.4,10,1\n1,11.6,10,1\n1,11.5,10,2\n10,100.0,100,1\n10,100.2,100,1\n10,99.9,100,2"
    resultado = validar_metodo(dados=dados, tipo="cromatografico")
    primeiro = resultado["rows"][0]
    assert primeiro["limite"] == "±20% / RSD 20%"
    assert resultado["counts"]["must"] == 0


def test_method_validation_flags_bad_linearity() -> None:
    resultado = validar_metodo(dados=DADOS_VALIDACAO, curva=CURVA_RUIM)
    assert "r2-baixo" in kinds(resultado)


def test_method_validation_flags_missing_curve_and_single_replicate() -> None:
    dados = "1,10.0,10,1\n1,10.1,10,1\n10,50.0,50,1\n10,50.2,50,1"
    resultado = validar_metodo(dados=dados)
    assert "sem-curva" in kinds(resultado)
    assert "replicatas-insuficientes" in kinds(resultado)


def test_method_validation_detects_intermediate_precision_gap() -> None:
    dados = (
        "10,50.0,50,dia1\n10,50.1,50,dia1\n10,50.2,50,dia1\n"
        "10,54.0,50,dia2\n10,54.1,50,dia2\n10,54.2,50,dia2\n"
        "10,52.0,50,dia3\n10,52.1,50,dia3\n10,52.2,50,dia3"
    )
    resultado = validar_metodo(dados=dados, limite_rsd=2.0)
    assert "precisao-intermediaria" in kinds(resultado) or "precisao-total-fora" in kinds(resultado)


def test_method_validation_rejects_bad_rows_and_negative_slope() -> None:
    with pytest.raises(CienciaError):
        validar_metodo(dados="1,10")
    with pytest.raises(CienciaError):
        validar_metodo(dados=DADOS_VALIDACAO, curva="0,0\n1,1")
    queda = "0,40\n5,30\n10,20\n20,12"
    assert "inclinacao-nao-positiva" in kinds(validar_metodo(dados=DADOS_VALIDACAO, curva=queda))


def test_method_validation_lba_uses_wider_criteria() -> None:
    dados = "1,12.0,10,1\n1,12.1,10,1\n1,12.2,10,2\n100,110.0,100,1\n100,110.5,100,1\n100,111.0,100,2"
    resultado = validar_metodo(dados=dados, tipo="lba")
    assert resultado["metrics"]["limite_recuperacao"] == 20.0
    assert resultado["counts"]["must"] == 0


# ---------------------------------------------------------------- manuscrito


def test_manuscript_audit_counts_sections_and_guideline_items() -> None:
    resultado = auditar_manuscrito(texto=MANUSCRITO, tipo="ensaio")
    assert resultado["metrics"]["diretriz"] == "CONSORT 2025"
    assert resultado["metrics"]["secoes_presentes"] >= 11
    assert resultado["metrics"]["itens_presentes"] >= 4
    assert resultado["counts"]["must"] == 0


def test_manuscript_audit_flags_claims_that_exceed_the_design() -> None:
    texto = MANUSCRITO.replace("O tratamento é promissor.", "O tratamento curou os pacientes.")
    assert "claim-cura" in kinds(auditar_manuscrito(texto=texto))


def test_manuscript_audit_selects_the_guideline_by_type() -> None:
    revisao = MANUSCRITO + "\nA estratégia de busca cobriu PubMed e Scopus."
    resultado = auditar_manuscrito(texto=revisao, tipo="revisao")
    assert resultado["metrics"]["diretriz"] == "PRISMA 2020"


def test_manuscript_audit_flags_missing_required_sections() -> None:
    texto = ("Resumo\nUm estudo curto, com 12 participantes e desfecho único, sem grupo de comparação.\n"
             "Introdução\nO tema importa porque a condição é frequente e o tratamento disponível é limitado.\n"
             "Discussão\nNada a declarar além do que já foi dito na introdução e no resumo deste texto.")
    resultado = auditar_manuscrito(texto=texto)
    encontrados = kinds(resultado)
    assert "sem-secao-metodos" in encontrados
    assert "sem-secao-resultados" in encontrados


def test_manuscript_validation_rejects_short_text() -> None:
    with pytest.raises(CienciaError):
        auditar_manuscrito(texto="Resumo. Métodos. Resultados.")


# ------------------------------------------------------------------ catálogo


def test_catalog_publishes_rules_and_formulas() -> None:
    catalogo = ciencia_catalogo()
    assert catalogo["fonte"].startswith("K-Dense-AI/scientific-agent-skills")
    assert catalogo["executado"] is False
    assert len(catalogo["formulas"]) >= 10
    assert len(catalogo["diretrizes"]) == 5
    assert len(catalogo["reprodutibilidade"]) == len(ITENS_REPRO)
    assert catalogo["benchmarks"]["d"] == list(BENCHMARKS["d"])
    assert catalogo["deixado_de_fora"]


def test_catalog_lists_every_design_item() -> None:
    catalogo = ciencia_catalogo()
    for tipo, itens in catalogo["desenho"].items():
        assert itens, tipo
        assert all(item["peso"] in {"must", "should", "nice"} for item in itens)
        assert len({item["id"] for item in itens}) == len(itens)


# ------------------------------------------------------------------ registry


def test_registry_exposes_seven_ciencia_skills(client: TestClient) -> None:
    corpo = client.get("/api/skills").json()
    itens = corpo if isinstance(corpo, list) else corpo.get("skills", corpo.get("items", []))
    ids = {item["id"] for item in itens}
    assert {
        "ciencia.amostra", "ciencia.estatistica", "ciencia.desenho",
        "ciencia.reprodutibilidade", "ciencia.validacao", "ciencia.manuscrito",
        "ciencia.regras",
    } <= ids


def test_skill_endpoints_are_read_only_and_prefixed(client: TestClient) -> None:
    chamadas = [
        ("ciencia.amostra", {"teste": "medias", "cohen_d": 0.5}),
        ("ciencia.estatistica", {"texto": RESULTADOS}),
        ("ciencia.desenho", {"texto": METODOS_COMPLETOS}),
        ("ciencia.reprodutibilidade", {"texto": REPRO_COMPLETO}),
        ("ciencia.validacao", {"dados": DADOS_VALIDACAO, "curva": CURVA_BOA}),
        ("ciencia.manuscrito", {"texto": MANUSCRITO}),
        ("ciencia.regras", {}),
    ]
    for skill, parametros in chamadas:
        resposta = client.post(f"/api/skills/{skill}/execute", json={"parameters": parametros})
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["ok"] is True, skill
        resultado = corpo["result"]
        if skill != "ciencia.regras":
            assert resultado["analysis"] == skill
            assert resultado["executed"] is False
            assert resultado["readOnly"] is True
            assert resultado["markdown"].startswith("# ")
            assert resultado["limitations"]
        assert resultado["executado"] is False


def test_skill_endpoint_reports_validation_errors(client: TestClient) -> None:
    resposta = client.post(
        "/api/skills/ciencia.amostra/execute",
        json={"parameters": {"teste": "medias", "cohen_d": 0.5, "alfa": 2.0}},
    )
    corpo = resposta.json()
    assert corpo["ok"] is False
    assert "alfa" in corpo["error"]["message"].lower() or "inválidos" in corpo["error"]["message"].lower()
