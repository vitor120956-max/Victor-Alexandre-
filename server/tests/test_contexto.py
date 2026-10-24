"""Testes da camada de contexto inspirada em CherryHQ/cherry-studio (AGPL-3.0).

Nenhum código do upstream é copiado e nenhum tokenizador BPE é usado: as
fixtures são conversas em texto ou JSON, e as contas são aritmética explícita
sobre elas. Nenhum modelo de linguagem participa.
"""
from __future__ import annotations

import pytest

from server.contexto import (
    CAUDA_FERRAMENTA,
    MIN_SALA_ENTRADA,
    ContextoError,
    contabilizar_uso,
    contexto_catalogo,
    cortar_historico,
    estimar_conteudo,
    estimar_texto,
    ler_mensagens,
    planejar_orcamento,
    resumir_historico,
    sanear_historico,
)

# ------------------------------------------------------------------ fixtures

TRES = """system: Você é o JARVIS.
user: Qual é o prazo?
assistant: Trinta dias.
user: E o custo?
assistant: R$ 1.200 por mês.
"""

FERRAMENTA = """user: Busque o preço.
assistant(tools): c1=buscar_web
tool(c1): O preço é R$ 2.400.
assistant: Encontrei R$ 2.400.
user: Ótimo, decidimos usar esse fornecedor.
"""


def _kinds(resultado: dict) -> list[str]:
    return [item["kind"] for item in resultado["findings"]]


# ----------------------------------------------------------------- orçamento

def test_orcamento_sem_reserva_usa_a_janela() -> None:
    resultado = planejar_orcamento(janela=128_000, dialeto="openai")
    assert resultado["metrics"]["sala"] == 128_000
    assert resultado["metrics"]["disponivel"] == 128_000
    assert resultado["metrics"]["reserva"] == 0
    assert "Reserva" in resultado["verdict"]


def test_orcamento_reserva_explicita_sai_da_janela() -> None:
    resultado = planejar_orcamento(janela=16_000, reserva=4_000)
    assert resultado["metrics"]["sala"] == 12_000
    assert resultado["metrics"]["disponivel"] == 12_000


def test_orcamento_precedencia_explicita_sobre_assistente() -> None:
    resultado = planejar_orcamento(janela=16_000, reserva=2_000, saida_assistente=6_000, assistente_habilitado=True)
    assert resultado["metrics"]["reserva"] == 2_000


def test_orcamento_assistente_antes_do_modelo() -> None:
    resultado = planejar_orcamento(
        janela=16_000, saida_assistente=3_000, assistente_habilitado=True,
        max_saida_modelo=8_000, dialeto="anthropic",
    )
    assert resultado["metrics"]["reserva"] == 3_000


def test_orcamento_anthropic_usa_teto_do_modelo() -> None:
    resultado = planejar_orcamento(janela=16_000, max_saida_modelo=4_000, dialeto="anthropic")
    assert resultado["metrics"]["reserva"] == 4_000
    assert any("Anthropic" in linha["regra"] for linha in resultado["rows"])


def test_orcamento_openai_ignora_teto_do_modelo() -> None:
    resultado = planejar_orcamento(janela=16_000, max_saida_modelo=4_000, dialeto="openai")
    assert resultado["metrics"]["reserva"] == 0
    assert resultado["metrics"]["sala"] == 16_000
    assert "teto-ignorado" in _kinds(resultado)


def test_orcamento_piso_de_vinte_por_cento() -> None:
    resultado = planejar_orcamento(janela=10_000, reserva=9_500)
    assert resultado["metrics"]["sala"] == int(10_000 * MIN_SALA_ENTRADA)


def test_orcamento_prompt_acima_da_sala_bloqueia() -> None:
    conversa = "user: " + "a" * 8_400
    resultado = planejar_orcamento(janela=10_000, reserva=9_000, mensagens=conversa)
    assert "prompt-acima-da-sala" in _kinds(resultado)
    assert resultado["counts"]["must"] >= 1
    assert resultado["metrics"]["sobra"] < 0


def test_orcamento_teto_maior_que_janela_bloqueia() -> None:
    resultado = planejar_orcamento(
        janela=8_000, max_saida_modelo=8_000, dialeto="anthropic",
    )
    assert "max-saida-maior-que-janela" in _kinds(resultado)


def test_orcamento_acima_de_oitenta_por_cento_pede_compactacao() -> None:
    conversa = "user: " + "a" * 13_000
    resultado = planejar_orcamento(janela=4_000, mensagens=conversa)
    assert resultado["metrics"]["pressao"] >= 80
    assert "compactar-agora" in _kinds(resultado)


def test_orcamento_recusa_janela_absurda() -> None:
    with pytest.raises(ContextoError):
        planejar_orcamento(janela=10)
    with pytest.raises(ContextoError):
        planejar_orcamento(janela=8_000, margem=50)
    with pytest.raises(ContextoError):
        planejar_orcamento(janela=8_000, dialeto="gpt")


def test_orcamento_conta_mensagens() -> None:
    resultado = planejar_orcamento(janela=8_000, mensagens=TRES)
    assert resultado["metrics"]["mensagens"] == 5
    assert resultado["metrics"]["prompt"] > 0


# ---------------------------------------------------------------- estimativa

def test_texto_quatro_caracteres_por_token() -> None:
    assert estimar_texto("a" * 400) == 100
    assert estimar_texto("") == 0
    assert estimar_texto("   ") == 0


def test_cjk_um_token_por_caractere() -> None:
    assert estimar_texto("日本語のテキスト") == 8


def test_codigo_cercado_conta_mais_denso() -> None:
    codigo = "```python\nprint('oi')\n```"
    assert estimar_texto(codigo) > estimar_texto("x" * len(codigo)) // 2
    assert estimar_texto(codigo) >= 5


def test_imagem_anthropic_pela_formula() -> None:
    assert estimar_conteudo("[imagem 1024x768]", "anthropic")[0] == 1049


def test_imagem_openai_por_ladrilhos() -> None:
    assert estimar_conteudo("[imagem 1024x768]", "openai")[0] == 765


def test_imagem_google_pequena_e_barata() -> None:
    assert estimar_conteudo("[imagem 320x200]", "google")[0] == 258


def test_imagem_ollama_constante() -> None:
    assert estimar_conteudo("[imagem 4000x3000]", "ollama")[0] == 1000


def test_midia_por_duracao() -> None:
    assert estimar_conteudo("[áudio 90s]", "openai")[0] == 2_880
    assert estimar_conteudo("[vídeo 30s]", "google")[0] == 7_740


def test_midia_sem_duracao_usa_padrao() -> None:
    tokens, itens = estimar_conteudo("[áudio]", "google")
    assert tokens == 60 * 32
    assert itens[0]["detalhe"] == "duração padrão"


def test_documento_por_caracteres() -> None:
    assert estimar_conteudo("[documento 4000]", "anthropic")[0] == 1_000


def test_partes_estruturadas_em_json() -> None:
    partes = [{"type": "text", "text": "a" * 40}, {"type": "image", "width": 1024, "height": 768}]
    tokens, itens = estimar_conteudo(partes, "openai")
    assert tokens == 10 + 765
    assert itens[0]["tipo"] == "imagem"


def test_estimativa_marca_base64_como_bloqueio() -> None:
    conversa = "user: " + "QUJD" * 800
    resultado = estimar_conteudo(conversa, "openai")[0]
    assert resultado > 0
    from server.contexto import estimar_conversa  # import local para o teste
    analise = estimar_conversa(mensagens=conversa)
    assert "anexo-em-base64" in _kinds(analise)
    assert analise["counts"]["must"] == 1


def test_estimativa_imagem_sem_dimensao() -> None:
    from server.contexto import estimar_conversa
    analise = estimar_conversa(mensagens="user: [imagem] descreva")
    assert "imagem-sem-dimensao" in _kinds(analise)
    assert analise["metrics"]["imagem"] == 1


def test_estimativa_soma_por_papel() -> None:
    from server.contexto import estimar_conversa
    analise = estimar_conversa(mensagens=TRES)
    assert analise["metrics"]["mensagens"] == 5
    assert set(analise["metrics"]["por_papel"]) == {"sistema", "usuário", "assistente"}
    assert analise["metrics"]["tokens"] == sum(analise["metrics"]["por_papel"].values())


# ---------------------------------------------------------------------- corte

def test_corte_preserva_sistema_e_ultimos_turnos() -> None:
    resultado = cortar_historico(mensagens=TRES, janela=100_000, manter_ultimas=2)
    mantidos = [linha for linha in resultado["rows"] if linha["decisao"] == "mantido"]
    assert len(mantidos) == 3  # system + dois turnos
    assert mantidos[0]["motivo"] == "system"


def test_corte_nunca_parte_turno_de_ferramenta() -> None:
    inteiro = cortar_historico(mensagens=FERRAMENTA, janela=100_000, manter_ultimas=3)
    assert "ferramenta(c1)" in inteiro["markdown"]
    assert "assistente(c1=buscar_web)" in inteiro["markdown"]
    partido = cortar_historico(mensagens=FERRAMENTA, janela=100_000, manter_ultimas=2)
    assert "ferramenta(c1)" not in partido["markdown"]
    assert "orfa-no-corte" not in _kinds(partido)


def test_corte_respeita_o_orcamento() -> None:
    conversa = "\n".join(f"user: mensagem {i} " + "a" * 400 for i in range(10))
    resultado = cortar_historico(mensagens=conversa, janela=2_000, manter_ultimas=6)
    assert resultado["metrics"]["tokens_depois"] <= resultado["metrics"]["sala"]
    assert resultado["metrics"]["removidas"] > 0
    assert "sem-resumo" in _kinds(resultado)


def test_corte_admite_que_o_ultimo_turno_nao_cabe() -> None:
    conversa = "user: " + "a" * 20_000
    resultado = cortar_historico(mensagens=conversa, janela=1_000)
    assert "ultimo-turno-nao-cabe" in _kinds(resultado)
    assert resultado["counts"]["must"] == 1


def test_corte_por_limite_de_mensagens() -> None:
    resultado = cortar_historico(mensagens=TRES, janela=100_000, manter_ultimas=5, limite_mensagens=3)
    assert resultado["metrics"]["removidas"] >= 2
    assert "limite-mensagens-cortou" in _kinds(resultado)
    assert resultado["metrics"]["servidas"] < resultado["metrics"]["mensagens"] + 1


def test_corte_nada_a_cortar() -> None:
    resultado = cortar_historico(mensagens=TRES, janela=100_000, manter_ultimas=6)
    assert resultado["metrics"]["removidas"] == 0
    assert "nada-a-cortar" in _kinds(resultado)


def test_corte_marca_histórico_servido() -> None:
    conversa = "\n".join(f"user: pergunta {i} " + "b" * 300 for i in range(8))
    resultado = cortar_historico(mensagens=conversa, janela=2_000, manter_ultimas=3)
    assert "mensagem(ns) omitida(s)" in resultado["markdown"]
    assert resultado["mode"] == "full"


def test_corte_recusa_limites_invalidos() -> None:
    with pytest.raises(ContextoError):
        cortar_historico(mensagens=TRES, janela=8_000, manter_ultimas=0)
    with pytest.raises(ContextoError):
        cortar_historico(mensagens="", janela=8_000)
    with pytest.raises(ContextoError):
        cortar_historico(mensagens=TRES, janela=8_000, limite_mensagens=0)


# -------------------------------------------------------------------- higiene

def test_higiene_remove_resultado_orfao() -> None:
    resultado = sanear_historico(mensagens="user: veja\ntool(c9): resultado solto")
    assert "orfa-removida" in _kinds(resultado)
    assert resultado["metrics"]["orfas"] == 1
    assert "tool(c9)" not in resultado["markdown"].split("## Histórico saneado")[1]


def test_higiene_injeta_resultado_faltante() -> None:
    resultado = sanear_historico(mensagens="user: busque\nassistant(tools): c1=buscar_web\nuser: e aí?")
    assert "resultado-injetado" in _kinds(resultado)
    assert resultado["metrics"]["injetadas"] == 1
    assert "[Sem resultado da ferramenta]" in resultado["markdown"]


def test_higiene_abre_com_usuario() -> None:
    resultado = sanear_historico(mensagens="assistant: bom dia\nuser: oi")
    assert "abertura-inserida" in _kinds(resultado)
    assert resultado["metrics"]["abertura"] == 1
    assert "[Conversa continua]" in resultado["markdown"]


def test_higiene_historico_valido() -> None:
    resultado = sanear_historico(mensagens=TRES)
    assert "historico-valido" in _kinds(resultado)
    assert resultado["metrics"]["injetadas"] == 0


def test_higiene_id_duplicado() -> None:
    conversa = "user: a\nassistant(tools): c1=um, c1=dois\ntool(c1): ok"
    resultado = sanear_historico(mensagens=conversa)
    assert "id-duplicado" in _kinds(resultado)
    assert resultado["metrics"]["duplicados"] == 1


def test_higiene_ferramenta_sem_id() -> None:
    resultado = sanear_historico(mensagens="user: a\nassistant(tools): c1=x\ntool: resultado")
    assert "tool-sem-id" in _kinds(resultado)
    assert resultado["counts"]["must"] >= 1


def test_higiene_aceita_json() -> None:
    conversa = '[{"role":"user","content":"oi"},{"role":"assistant","content":"olá"}]'
    resultado = sanear_historico(mensagens=conversa)
    assert resultado["metrics"]["mensagens"] == 2
    assert resultado["metrics"]["abertura"] == 0


def test_higiene_tudo_removido_vira_placeholder() -> None:
    resultado = sanear_historico(mensagens="user: sistema sem nada\ntool(c1): x")
    assert resultado["metrics"]["saida"] >= 1
    assert resultado["metrics"]["orfas"] == 1


# --------------------------------------------------------------------- resumo

def test_resumo_extrai_decisao_numero_e_caminho() -> None:
    conversa = (
        "user: decidimos usar Postgres 16 em produção.\n"
        "assistant: o p95 ficou em 240ms e o custo em R$ 1.200 por mês.\n"
        "user: próximo passo é ajustar scripts/etl.py."
    )
    resultado = resumir_historico(mensagens=conversa)
    itens = [linha["tipo"] for linha in resultado["rows"]]
    assert "decisão" in itens
    assert "número" in itens
    assert "caminho" in itens
    assert "pendência" in itens
    assert "O que precisa sobreviver" in resultado["markdown"]


def test_resumo_estuba_saida_grande() -> None:
    conversa = "user: leia\nassistant(tools): c1=ler_arquivo\ntool(c1): " + "x" * 5_000
    resultado = resumir_historico(mensagens=conversa, limiar=4_000)
    assert resultado["metrics"]["stubs"] == 1
    assert "ler_arquivo" in resultado["markdown"]
    assert resultado["metrics"]["tokens_stub"] < resultado["metrics"]["tokens_antes"]


def test_resumo_limiar_zero_estuba_tudo() -> None:
    conversa = "user: leia\ntool(c1): conteúdo"
    resultado = resumir_historico(mensagens=conversa, limiar=0)
    assert "stub-total" in _kinds(resultado)


def test_resumo_sem_retencao_bloqueia() -> None:
    resultado = resumir_historico(mensagens="user: blá blá blá sem nada de útil aqui\nassistant: certo")
    assert "sem-retencao" in _kinds(resultado)
    assert resultado["counts"]["must"] == 1


def test_resumo_respeita_limite() -> None:
    conversa = "\n".join(f"user: decidimos a opção {i} e o custo é R$ {i}00 por mês em scripts/x{i}.py" for i in range(20))
    resultado = resumir_historico(mensagens=conversa, limite=150)
    assert resultado["metrics"]["tokens_resumo"] <= 150
    assert resultado["metrics"]["cortados"] > 0
    assert "itens-cortados" in _kinds(resultado)


def test_resumo_troca_anexo_por_placeholder() -> None:
    resultado = resumir_historico(mensagens="user: [imagem 800x600] o que é isso?\nassistant: um gráfico")
    assert resultado["metrics"]["anexos"] == 1
    assert "[imagem]" in resultado["markdown"]


def test_resumo_recusa_limite_absurdo() -> None:
    with pytest.raises(ContextoError):
        resumir_historico(mensagens="user: oi", limite=10)
    with pytest.raises(ContextoError):
        resumir_historico(mensagens="user: oi", limiar=-1)


# ------------------------------------------------------------------------ uso

def test_uso_ancora_contexto_pelo_total() -> None:
    resultado = contabilizar_uso(entrada=12_000, saida=800, total=12_800)
    assert resultado["metrics"]["contexto"] == 12_800


def test_uso_usa_prompt_inicial_quando_existe() -> None:
    resultado = contabilizar_uso(entrada=12_000, saida=800, total=15_000, inicial=13_000)
    assert resultado["metrics"]["contexto"] == 16_000


def test_uso_calcula_custo() -> None:
    resultado = contabilizar_uso(
        entrada=1_000_000, saida=100_000, preco_entrada=2.0, preco_saida=10.0,
    )
    assert resultado["metrics"]["custo"] == pytest.approx(3.0)


def test_uso_total_menor_que_entrada_bloqueia() -> None:
    resultado = contabilizar_uso(entrada=5_000, saida=100, total=4_000)
    assert "total-menor-que-entrada" in _kinds(resultado)
    assert resultado["metrics"]["contexto"] == 5_000


def test_uso_cache_maior_que_entrada_bloqueia() -> None:
    resultado = contabilizar_uso(entrada=1_000, saida=100, cache=2_000)
    assert "cache-acima-da-entrada" in _kinds(resultado)


def test_uso_sem_total_avisa() -> None:
    resultado = contabilizar_uso(entrada=3_000, saida=200)
    assert "sem-total" in _kinds(resultado)


def test_uso_janela_ultrapassada() -> None:
    resultado = contabilizar_uso(entrada=40_000, saida=100, janela=32_000)
    assert "janela-ultrapassada" in _kinds(resultado)
    assert resultado["metrics"]["pressao"] > 100


def test_uso_hop_multiplica_o_contexto() -> None:
    um = contabilizar_uso(entrada=10_000, saida=500, preco_entrada=3.0, preco_saida=15.0, hops=1)
    tres = contabilizar_uso(entrada=10_000, saida=500, preco_entrada=3.0, preco_saida=15.0, hops=3)
    assert tres["metrics"]["custo_hop"] == pytest.approx(um["metrics"]["custo_hop"] * 3)
    assert "hops-repetem-prompt" in _kinds(tres)


def test_uso_recusa_negativo() -> None:
    with pytest.raises(ContextoError):
        contabilizar_uso(entrada=-1, saida=10)
    with pytest.raises(ContextoError):
        contabilizar_uso(entrada=10, saida=10, hops=0)


# --------------------------------------------------------------------- leitura

def test_leitura_formato_de_linha_com_multilinha() -> None:
    mensagens = ler_mensagens("user: primeira linha\nsegunda linha\nassistant: ok")
    assert len(mensagens) == 2
    assert "segunda linha" in mensagens[0]["content"]


def test_leitura_json_com_ferramenta() -> None:
    conversa = (
        '[{"role":"user","content":"a"},'
        '{"role":"assistant","content":null,"tool_calls":[{"id":"c1","function":{"name":"buscar"}}]},'
        '{"role":"tool","tool_call_id":"c1","content":"ok"}]'
    )
    mensagens = ler_mensagens(conversa)
    assert mensagens[1]["tool_calls"][0]["name"] == "buscar"
    assert mensagens[2]["tool_call_id"] == "c1"


def test_leitura_recusa_json_quebrado() -> None:
    with pytest.raises(ContextoError):
        ler_mensagens('[{"role": "user"')
    with pytest.raises(ContextoError):
        ler_mensagens("linha sem papel")


# -------------------------------------------------------------------- catálogo

def test_catalogo_publica_formulas_e_limites() -> None:
    catalogo = contexto_catalogo()
    assert catalogo["fonte"].startswith("CherryHQ/cherry-studio")
    assert catalogo["dialetos"] == ["anthropic", "openai", "google", "ollama"]
    assert set(catalogo["imagem"]["formula"]) == set(catalogo["dialetos"])
    assert catalogo["midia"]["taxa_por_segundo"]["google"]["video"] == 258
    assert catalogo["orcamento"]["sala_minima"] == MIN_SALA_ENTRADA
    assert catalogo["resumo"]["escalada_de_stub"] == [4_000, 1_000, 200, 0]
    assert catalogo["ferramenta"]["cauda_preservada"] == CAUDA_FERRAMENTA
    assert len(catalogo["higiene"]["regras"]) == 4
    assert len(catalogo["deixado_de_fora"]) == 4
    assert catalogo["executado"] is False


def test_catalogo_declara_o_que_ficou_de_fora() -> None:
    catalogo = contexto_catalogo()
    fora = " ".join(catalogo["deixado_de_fora"]).lower()
    assert "bpe" in fora
    assert "nenhum modelo" in fora
    assert catalogo["limites"]["texto"] == 200_000
