"""Estudo com repetição espaçada — o laço que faltava.

A ideia veio do DeepTutor (HKUDS): aprender é laço, não pergunta única. O que
sobrevive aqui sem GPU, sem chave e sem modelo é o miolo do laço — material vira
cartão por padrão de frase, a resposta agenda o retorno pelo SM-2, e o boletim
mede retenção de verdade.

Dois cuidados que estes testes travam:

- **nada de adivinhar**: frase longa com “porque é” no meio não vira cartão, e o
  relatório diz quantas linhas foram ignoradas em vez de fingir aproveitamento;
- **SM-2 puro**: nota baixa zera a sequência e o cartão volta amanhã, mas a
  facilidade cai nos dois sentidos — é o algoritmo do SuperMemo, não “+1 dia”.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from server import estudo

HOJE = date(2026, 10, 30)
AGORA = datetime(2026, 10, 30, 9, 0)
MATERIAL = """# Direito Civil

Direito civil é o ramo do direito privado que regula as relações entre particulares.

**Posse**: é o exercício de fato de um dos poderes da propriedade sobre a coisa.

- Prescrição — perda do direito de ação pelo decurso do tempo.

Este trecho final fala de outra coisa completamente diferente e por isso não vira cartão.
"""


# ---------------------------------------------------------------- geração


def test_material_vira_cartao_pelos_tres_padroes():
    gerado = estudo.cartoes_de_texto(MATERIAL)
    tipos = {c["tipo"] for c in gerado["cartoes"]}
    assert "definicao" in tipos
    assert "verbete" in tipos
    frentes = [c["frente"] for c in gerado["cartoes"]]
    assert any("Direito civil" in f for f in frentes)
    assert any("Posse" in f for f in frentes)
    assert any("Prescrição" in f for f in frentes)


def test_frase_longa_com_porque_no_meio_nao_vira_pergunta():
    """Sem o filtro de 6 palavras sai “O que é Segundo parágrafo que … porque?”."""
    frase = (
        "Segundo parágrafo que não deve virar cartão de título nenhum porque é longo "
        "demais e trata de outro assunto completamente diferente do resto."
    )
    gerado = estudo.cartoes_de_texto("Termo curto é uma definição válida e comprida.\n\n" + frase)
    for cartao in gerado["cartoes"]:
        assert "Segundo parágrafo" not in cartao["frente"], cartao["frente"]


def test_o_verso_nao_repete_o_verbo_da_pergunta():
    gerado = estudo.cartoes_de_texto(MATERIAL)
    posse = [c for c in gerado["cartoes"] if "Posse" in c["frente"]][0]
    assert not posse["verso"].startswith("é ")
    assert posse["verso"].startswith("o exercício")


def test_relatorio_diz_quantas_linhas_foram_ignoradas():
    gerado = estudo.cartoes_de_texto(MATERIAL)
    assert gerado["ignoradas"] >= 1
    assert gerado["gerados"] == len(gerado["cartoes"])
    assert "não por modelo" in gerado["aviso"]


def test_texto_sem_padrao_recusa_em_vez_de_inventar():
    with pytest.raises(estudo.EstudoError):
        estudo.cartoes_de_texto("blá blá blá\n\nnada aqui\n")


def test_texto_vazio_recusa():
    with pytest.raises(estudo.EstudoError):
        estudo.cartoes_de_texto("   ")


def test_respeita_o_teto_de_cartoes():
    linhas = "\n\n".join(f"Termo {i} é uma definição comprida o suficiente para virar cartão." for i in range(80))
    gerado = estudo.cartoes_de_texto(linhas, maximo=5)
    assert len(gerado["cartoes"]) == 5


# ---------------------------------------------------------------- baralho


def test_criar_e_listar_baralho(tmp_path):
    criado = estudo.criar("Civil", raiz=tmp_path, agora=AGORA)
    assert criado["criado"] is True
    assert criado["baralho"] == "civil"
    assert estudo.criar("Civil", raiz=tmp_path)["criado"] is False
    lista = estudo.baralhos(tmp_path)
    assert len(lista) == 1
    assert lista[0]["cartoes"] == 0


def test_adicionar_material_e_deduplicar(tmp_path):
    primeiro = estudo.adicionar("civil", texto=MATERIAL, raiz=tmp_path, agora=AGORA)
    assert primeiro["adicionados"] >= 3
    segundo = estudo.adicionar("civil", texto=MATERIAL, raiz=tmp_path, agora=AGORA)
    assert segundo["adicionados"] == 0
    assert segundo["pulados"] == primeiro["adicionados"]
    assert segundo["total"] == primeiro["total"]


def test_cartao_a_mao(tmp_path):
    resultado = estudo.adicionar(
        "idiomas", frente="Como se diz livro?", verso="book", raiz=tmp_path, agora=AGORA
    )
    assert resultado["adicionados"] == 1
    cartao = estudo.carregar(tmp_path)["baralhos"]["idiomas"]["cartoes"][0]
    assert cartao["frente"] == "Como se diz livro?"
    assert cartao["tipo"] == "manual"


def test_cartao_a_mao_incompleto_recusa(tmp_path):
    with pytest.raises(estudo.EstudoError):
        estudo.adicionar("idiomas", frente="Só a frente", raiz=tmp_path, agora=AGORA)


def test_arquivo_corrompido_vira_estudo_vazio(tmp_path):
    (tmp_path / estudo.ARQUIVO).write_text("{isso não é json", encoding="utf-8")
    assert estudo.carregar(tmp_path)["baralhos"] == {}
    assert estudo.progresso(raiz=tmp_path)["cartoes"] == 0


# ---------------------------------------------------------------- SM-2


def _cartao(**extra):
    base = {"id": "abc123", "frente": "q", "verso": "a", "facilidade": 2.5, "intervalo": 0, "reps": 0,
            "vence": "2026-10-30", "acertos": 0, "erros": 0}
    base.update(extra)
    return base


def test_primeira_resposta_boa_volta_amanha():
    novo = estudo.agendar(_cartao(), 4, HOJE)
    assert novo["intervalo"] == 1
    assert novo["vence"] == "2026-10-31"
    assert novo["reps"] == 1
    assert novo["acertos"] == 1


def test_segunda_resposta_boa_volta_em_seis_dias():
    novo = estudo.agendar(_cartao(reps=1, intervalo=1), 4, HOJE)
    assert novo["intervalo"] == 6


def test_terceira_usa_a_facilidade():
    novo = estudo.agendar(_cartao(reps=2, intervalo=6, facilidade=2.5), 5, HOJE)
    assert novo["intervalo"] == 15  # 6 * 2.6


def test_errar_zera_a_sequencia_e_volta_amanha():
    novo = estudo.agendar(_cartao(reps=4, intervalo=40, facilidade=2.5), 0, HOJE)
    assert novo["reps"] == 0
    assert novo["intervalo"] == 1
    assert novo["erros"] == 1
    assert novo["facilidade"] < 2.5


def test_facilidade_tem_piso():
    cartao = _cartao()
    for _ in range(30):
        cartao = estudo.agendar(cartao, 0, HOJE)
    assert cartao["facilidade"] == pytest.approx(estudo.FACILIDADE_MIN)


def test_nota_por_nome_ou_numero():
    assert estudo._nota("errei") == 0
    assert estudo._nota("Difícil") == 3
    assert estudo._nota("facil") == 5
    assert estudo._nota("4") == 4
    with pytest.raises(estudo.EstudoError):
        estudo._nota("mais ou menos")
    with pytest.raises(estudo.EstudoError):
        estudo._nota(9)


# ---------------------------------------------------------------- o laço completo


def test_revisar_traz_vencidos_do_mais_atrasado(tmp_path):
    estudo.adicionar("civil", frente="Frente A", verso="Resposta 1", raiz=tmp_path, agora=AGORA)
    estado = estudo.carregar(tmp_path)
    estado["baralhos"]["civil"]["cartoes"][0]["vence"] = "2026-10-25"
    estudo._salvar(tmp_path, estado)
    estudo.adicionar("civil", frente="Frente B", verso="Resposta 2", raiz=tmp_path, agora=AGORA)

    revisao = estudo.revisar("civil", raiz=tmp_path, agora=AGORA)
    assert revisao["total_vencidos"] == 2
    assert revisao["cartoes"][0]["vencido_ha"] == 5
    assert {n["rotulo"] for n in revisao["notas"]} == {"errei", "difícil", "bom", "fácil"}


def test_responder_move_o_cartao_e_tira_da_fila(tmp_path):
    estudo.adicionar("civil", frente="Frente A", verso="Resposta 1", raiz=tmp_path, agora=AGORA)
    cartao = estudo.revisar("civil", raiz=tmp_path, agora=AGORA)["cartoes"][0]
    resposta = estudo.responder(cartao["id"], "bom", raiz=tmp_path, agora=AGORA)
    assert resposta["volta_em"] == "2026-10-31"
    assert estudo.revisar("civil", raiz=tmp_path, agora=AGORA)["total_vencidos"] == 0


def test_responder_cartao_inexistente_recusa(tmp_path):
    with pytest.raises(estudo.EstudoError):
        estudo.responder("naoexiste", "bom", raiz=tmp_path, agora=AGORA)


def test_baralho_inexistente_recusa_com_dica(tmp_path):
    estudo.adicionar("civil", frente="Frente A", verso="Resposta 1", raiz=tmp_path, agora=AGORA)
    with pytest.raises(estudo.EstudoError) as erro:
        estudo.revisar("matematica", raiz=tmp_path, agora=AGORA)
    assert "estudo.progresso" in str(erro.value)


def test_aceita_nome_com_acento_e_parcial(tmp_path):
    estudo.criar("Inglês Básico", raiz=tmp_path, agora=AGORA)
    estudo.adicionar("ingles basico", frente="house", verso="casa", raiz=tmp_path, agora=AGORA)
    revisao = estudo.revisar("Inglês", raiz=tmp_path, agora=AGORA)
    assert revisao["total_vencidos"] == 1


# ---------------------------------------------------------------- boletim


def test_progresso_mede_retencao_e_sequencia(tmp_path):
    estudo.adicionar("civil", frente="Frente A", verso="Resposta 1", raiz=tmp_path, agora=AGORA)
    estudo.adicionar("civil", frente="Frente B", verso="Resposta 2", raiz=tmp_path, agora=AGORA)
    ids = [c["id"] for c in estudo.revisar("civil", raiz=tmp_path, agora=AGORA)["cartoes"]]
    estudo.responder(ids[0], "bom", raiz=tmp_path, agora=AGORA)
    estudo.responder(ids[1], "errei", raiz=tmp_path, agora=AGORA)

    boletim = estudo.progresso(raiz=tmp_path, agora=AGORA)
    assert boletim["respostas"] == 2
    assert boletim["retencao"] == 50
    assert boletim["sequencia_dias"] == 1
    assert boletim["dias_estudados"] == 1


def test_progresso_aponta_os_cartoes_que_mais_erram(tmp_path):
    estudo.adicionar("civil", frente="Difícil", verso="Resposta", raiz=tmp_path, agora=AGORA)
    cartao = estudo.revisar("civil", raiz=tmp_path, agora=AGORA)["cartoes"][0]
    for _ in range(3):
        estudo.responder(cartao["id"], "errei", raiz=tmp_path, agora=datetime(2026, 10, 30, 9, 0))
    boletim = estudo.progresso(raiz=tmp_path, agora=AGORA)
    assert boletim["fracos"][0]["frente"] == "Difícil"
    assert boletim["fracos"][0]["erros"] == 3


def test_sequencia_conta_dias_seguidos(tmp_path):
    estudo.adicionar("civil", frente="Frente A", verso="Resposta 1", raiz=tmp_path, agora=AGORA)
    cartao = estudo.revisar("civil", raiz=tmp_path, agora=AGORA)["cartoes"][0]
    estudo.responder(cartao["id"], "bom", raiz=tmp_path, agora=datetime(2026, 10, 28, 9, 0))
    estudo.responder(cartao["id"], "bom", raiz=tmp_path, agora=datetime(2026, 10, 29, 9, 0))
    estudo.responder(cartao["id"], "bom", raiz=tmp_path, agora=datetime(2026, 10, 30, 9, 0))
    assert estudo.progresso(raiz=tmp_path, agora=AGORA)["sequencia_dias"] == 3


def test_resumo_do_boletim_fala_o_que_fazer(tmp_path):
    assert "Nenhum cartão" in estudo.resumo(estudo.progresso(raiz=tmp_path))
    estudo.adicionar("civil", frente="Frente A", verso="Resposta 1", raiz=tmp_path, agora=AGORA)
    assert "vencidos" in estudo.resumo(estudo.progresso(raiz=tmp_path, agora=AGORA))


# ---------------------------------------------------------------- ligação com o registro


def test_as_cinco_skills_estao_no_registro():
    from pathlib import Path

    from server.skill_registry import build_registry

    registro = build_registry(Path(__file__).resolve().parents[2])
    ids = {s["id"] for s in registro.list() if s["category"] == "Estudo"}
    assert ids == {"estudo.baralhos", "estudo.adicionar", "estudo.revisar", "estudo.responder", "estudo.progresso"}


def test_responder_pede_confirmacao_porque_grava():
    from pathlib import Path

    from server.skill_registry import build_registry

    registro = build_registry(Path(__file__).resolve().parents[2])
    for skill_id in ("estudo.adicionar", "estudo.responder"):
        skill = registro.get(skill_id)
        assert skill.requires_confirmation is True, skill_id
    assert registro.get("estudo.revisar").requires_confirmation is False
