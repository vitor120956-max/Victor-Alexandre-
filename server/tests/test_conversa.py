"""Conversa, filosofia e psicologia — o que o dono pediu na 0.92.0.

O pedido tinha uma ponta que não se entrega:

    como ir levando a garota para q ela queira ... ou q se apaixone por quem eu sou

“Fazer alguém se apaixonar” não é técnica honesta — é pressão com nome bonito.
Então o módulo existe, mas com a linha moral escrita em código e conferida aqui:
a recusa é dado (`RECUSADOS`), não promessa de README.

Estes testes cobrem três coisas que se quebram fácil:

1. a recusa continua sendo recusa (alguém “melhora” a lista e remove o neg);
2. a crise e a violência são interceptadas **antes** do conteúdo;
3. toda superfície de conversa carrega o aviso de que não é terapia.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from server import conversa
from server.app import create_app
from server.skill_registry import build_registry


def _cliente(tmp_path) -> TestClient:  # type: ignore[no-untyped-def]
    return TestClient(create_app(registry=build_registry(tmp_path / "files")))


# ---------------------------------------------------------------------------
# A linha moral
# ---------------------------------------------------------------------------

def test_as_tecnicas_de_manipulacao_continuam_recusadas():
    tecnicas = " ".join(tecnica for tecnica, _motivo in conversa.RECUSADOS).lower()
    for proibida in ("neg", "insistir", "chantagem", "personagem", "confundir", "vigiar"):
        assert proibida in tecnicas, f"a recusa de “{proibida}” sumiu da lista"
    # Cada recusa tem motivo escrito — sem motivo, é só censura.
    assert all(len(motivo) > 20 for _tecnica, motivo in conversa.RECUSADOS)


def test_a_skill_de_limites_devolve_a_mesma_lista():
    resultado = conversa.limites()
    assert len(resultado["recusados"]) == len(conversa.RECUSADOS)
    assert "CVV" in resultado["ajuda"]
    assert "terapia" in resultado["nao_e_terapia"].lower()
    # E a alternativa honesta é dita, não deixada no ar.
    assert "não" in resultado["no_lugar"]


def test_pergunta_direta_sobre_fazer_alguem_se_apaixonar_nao_recebe_receita():
    """A resposta inclui a recusa — em vez de só entregar o passo a passo."""
    resposta = conversa.manter(mensagem="como faço ela se apaixonar por mim?", objetivo="conhecer")
    texto = str(resposta).lower()
    assert "não" in texto or "nao" in texto


# ---------------------------------------------------------------------------
# Crise e violência antes de qualquer conteúdo
# ---------------------------------------------------------------------------

def test_crise_aciona_o_cvv_antes_de_qualquer_dica():
    resposta = conversa.manter(mensagem="não vejo mais sentido, penso em me matar", objetivo="conhecer")
    assert resposta["parou"] is True
    assert "188" in resposta["texto"]
    # O conteúdo de paquera não vem junto: a resposta é só o encaminhamento.
    assert "abertura" not in resposta and "principios" not in resposta


def test_violencia_aciona_os_numeros_de_emergencia():
    resposta = conversa.revisar(mensagem="ela não sai de perto de mim, vou dar um jeito nela")
    texto = str(resposta)
    assert "180" in texto or "190" in texto


# ---------------------------------------------------------------------------
# Conteúdo de verdade (não placeholder)
# ---------------------------------------------------------------------------

def test_abrir_tem_abertura_para_cada_contexto():
    for chave in conversa.CONTEXTOS:
        dados = conversa.abrir(contexto=chave)
        assert dados["aberturas"], f"o contexto “{chave}” ficou sem abertura"
        assert dados.get("evite"), f"o contexto “{chave}” ficou sem o que evitar"
    # Contexto inventado é recusado com a lista, não com um padrão silencioso.
    try:
        conversa.abrir(contexto="elevador")
    except conversa.ConversaError as exc:
        assert "app" in str(exc)
    else:  # pragma: no cover - falha explícita
        raise AssertionError("contexto fora da lista deveria ser recusado")


def test_convidar_ensina_saida_facil_e_receber_nao():
    dados = conversa.convidar(plano="feira de vinil no sábado")
    texto = str(dados).lower()
    assert "não" in texto or "nao" in texto
    assert dados["estrutura"]


def test_revisar_conta_o_que_pesa_na_mensagem():
    dados = conversa.revisar(mensagem="oi sumida?? pq nao respondeu? ta me evitando?")
    assert dados["perguntas"] == 3
    assert dados["problemas"], "três perguntas e cobrança deveriam gerar problema"
    # E o limite declarado: ele não adivinha a resposta dela.
    assert "não sei" in dados["lembrete"].lower() or "nao sei" in dados["lembrete"].lower()


def test_filosofia_tem_oito_escolas_com_pratica_e_limite():
    assert len(conversa.FILOSOFIAS) == 8
    for nome, dados in conversa.FILOSOFIAS.items():
        assert dados.get("ideia"), f"{nome} sem ideia central"
        assert dados.get("pergunta"), f"{nome} sem pergunta"
        assert dados.get("pratica"), f"{nome} sem prática"
    panorama = conversa.filosofia(pergunta="vale a pena tentar de novo?")
    assert len(panorama["escolas"]) == 8


def test_psicologia_declara_base_e_cuidado_em_cada_conceito():
    assert len(conversa.CONCEITOS) >= 7
    for nome, dados in conversa.CONCEITOS.items():
        assert dados.get("o_que_e"), f"{nome} sem definição"
        assert dados.get("base"), f"{nome} sem a base declarada"
        assert dados.get("cuidado"), f"{nome} sem o cuidado declarado"


# ---------------------------------------------------------------------------
# As rotas e as skills
# ---------------------------------------------------------------------------

def test_rotas_do_guia_respondem(tmp_path):
    cliente = _cliente(tmp_path)
    catalogo = cliente.get("/api/conversa/catalogo")
    assert catalogo.status_code == 200
    dados = catalogo.json()["result"]
    assert len(dados["escolas"]) == 8
    assert dados["recusados"]
    assert dados["nao_e_terapia"]

    for rota, corpo in (
        ("abrir", {"contexto": "academia"}),
        ("manter", {"mensagem": "oi", "objetivo": "marcar"}),
        ("convidar", {"plano": "café"}),
        ("ler", {}),
        ("limites", {}),
        ("revisar", {"mensagem": "oi"}),
        ("filosofia", {"escola": "estoicismo"}),
        ("psicologia", {"conceito": "rejeicao"}),
    ):
        resposta = cliente.post(f"/api/conversa/{rota}", json=corpo)
        assert resposta.status_code == 200, f"{rota}: {resposta.text[:200]}"
        assert resposta.json()["ok"] is True


def test_skill_de_conversa_nao_tem_efeito_e_esta_registrada(tmp_path):
    registro = build_registry(tmp_path / "files")
    ids = {skill["id"] for skill in registro.list()}
    for esperada in (
        "conversa.abrir", "conversa.manter", "conversa.convidar", "conversa.ler",
        "conversa.revisar", "conversa.limites", "filosofia.olhar", "psicologia.explicar",
    ):
        assert esperada in ids, f"a skill {esperada} sumiu"
        definicao = registro.get(esperada)
        assert definicao.side_effects is False, f"{esperada} não deveria ter efeito"
