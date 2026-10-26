"""Testes do correio exportado: triagem, padrões de escrita e rascunho."""
from __future__ import annotations

import mailbox
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

import pytest

from server import correio

AGORA = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


def eml(
    pasta: Path,
    nome: str,
    *,
    de: str = "alguem@exemplo.com",
    assunto: str = "Assunto",
    corpo: str = "Corpo",
    rotulos: str = "",
    data: str = "Mon, 20 Oct 2026 10:00:00 -0300",
) -> Path:
    mensagem = EmailMessage()
    mensagem["From"] = de
    mensagem["To"] = "victor@exemplo.com"
    mensagem["Subject"] = assunto
    mensagem["Date"] = data
    if rotulos:
        mensagem["X-Gmail-Labels"] = rotulos
    mensagem.set_content(corpo)
    caminho = pasta / nome
    caminho.write_bytes(bytes(mensagem))
    return caminho


@pytest.fixture()
def caixa(tmp_path: Path) -> Path:
    eml(
        tmp_path,
        "fatura.eml",
        de="financeiro@energia.com.br",
        assunto="Sua fatura de outubro",
        corpo="Prezado cliente, o vencimento é 30/10/2026. Valor R$ 210,33.",
        rotulos="Inbox",
    )
    eml(
        tmp_path,
        "intimacao.eml",
        de="contato@tjsc.jus.br",
        assunto="Intimação — processo nº 0001234",
        corpo="Fica a parte intimada a se manifestar no prazo de 5 dias.",
        rotulos="Inbox",
    )
    eml(
        tmp_path,
        "governo.eml",
        de="nao-responda@gov.br",
        assunto="Declaração do imposto de renda",
        corpo="Acesse o e-CAC para enviar sua declaração.",
        rotulos="Inbox",
    )
    eml(
        tmp_path,
        "promo.eml",
        de="promo@loja.com",
        assunto="Promoção de outubro",
        corpo="Descadastrar. Oferta válida hoje.",
        rotulos="Inbox",
    )
    eml(
        tmp_path,
        "enviado.eml",
        de="victor@exemplo.com",
        assunto="Re: reunião de sexta",
        corpo="Olá, Ana.\n\nSegue o resumo:\n- item 1\n- item 2\n\nAbraços\nVictor",
        rotulos="Sent",
    )
    return tmp_path


# ------------------------------------------------------------------ leitura


def test_ler_eml(caixa: Path):
    mensagens = correio.ler(caixa)
    assert len(mensagens) == 5
    assert {m["assunto"] for m in mensagens} >= {"Sua fatura de outubro", "Promoção de outubro"}
    assert all(m["de"] for m in mensagens)


def test_ler_mbox(tmp_path: Path):
    caixa = mailbox.mbox(str(tmp_path / "tudo.mbox"), create=True)
    for assunto in ("Um", "Dois"):
        mensagem = EmailMessage()
        mensagem["From"] = "a@b.com"
        mensagem["Subject"] = assunto
        mensagem["Date"] = "Mon, 20 Oct 2026 10:00:00 -0300"
        mensagem.set_content("texto")
        caixa.add(mensagem)
    caixa.flush()
    caixa.close()
    lidas = correio.ler(tmp_path)
    assert [m["assunto"] for m in lidas] == ["Um", "Dois"]


def test_pasta_que_nao_existe_explica(tmp_path: Path):
    with pytest.raises(correio.CorreioError) as erro:
        correio.ler(tmp_path / "nao-existe")
    assert "Takeout" in str(erro.value)


def test_pasta_vazia_explica(tmp_path: Path):
    with pytest.raises(correio.CorreioError) as erro:
        correio.ler(tmp_path)
    assert ".eml" in str(erro.value)


def test_arquivos_lista_formato_e_tamanho(caixa: Path):
    itens = correio.arquivos(caixa)
    assert len(itens) == 5
    assert {item["formato"] for item in itens} == {"eml"}
    assert all(item["bytes"] > 0 for item in itens)


# ---------------------------------------------------------------- triagem


def test_intimacao_tem_prioridade_maxima(caixa: Path):
    achado = correio.triar(caixa, agora=AGORA)
    primeira = achado["mensagens"][0]
    assert primeira["categoria"] == "intimacao"
    assert primeira["prioridade"] == 100


def test_fatura_com_vencimento_sobe_de_prioridade(tmp_path: Path):
    eml(
        tmp_path,
        "fatura.eml",
        assunto="Boleto da academia",
        corpo="Segue o boleto. Vencimento: 29/10/2026.",
    )
    item = correio.triar(tmp_path, agora=AGORA)["mensagens"][0]
    assert item["categoria"] == "fatura"
    assert item["vencimento"] == "2026-10-29"
    assert item["dias_para_vencer"] == 3
    assert item["prioridade"] > correio.CATEGORIAS["fatura"]["prioridade"]


def test_vencimento_distante_nao_sobe(tmp_path: Path):
    eml(tmp_path, "f.eml", assunto="Boleto", corpo="Vencimento: 20/12/2026.")
    item = correio.triar(tmp_path, agora=AGORA)["mensagens"][0]
    assert item["prioridade"] == correio.CATEGORIAS["fatura"]["prioridade"]


def test_data_solta_nao_vira_vencimento():
    assert correio.achar_vencimento("Nota fiscal emitida em 20/10/2026", AGORA) is None


def test_governo_e_newsletter(caixa: Path):
    resumo = correio.triar(caixa, agora=AGORA)
    categorias = {item["categoria"] for item in resumo["mensagens"]}
    assert {"governo", "newsletter"} <= categorias


def test_remetente_humano_sem_termo_e_pessoal(tmp_path: Path):
    eml(tmp_path, "pessoal.eml", de="ana@empresa.com", assunto="Almoço amanhã?", corpo="Podemos às 12h?")
    item = correio.triar(tmp_path, agora=AGORA)["mensagens"][0]
    assert item["categoria"] == "pessoal"
    assert item["prioridade"] == correio.PRIORIDADE_PESSOAL


def test_remetente_automatico_sem_termo_e_outro(tmp_path: Path):
    eml(tmp_path, "auto.eml", de="no-reply@sistema.com", assunto="Seu relatório está pronto", corpo="Baixe no painel.")
    item = correio.triar(tmp_path, agora=AGORA)["mensagens"][0]
    assert item["categoria"] in {"newsletter", "outro"}
    assert item["prioridade"] <= correio.PRIORIDADE_OUTRO


def test_triagem_ordena_e_resume(caixa: Path):
    resumo = correio.triar(caixa, agora=AGORA)
    prioridades = [item["prioridade"] for item in resumo["mensagens"]]
    assert prioridades == sorted(prioridades, reverse=True)
    assert resumo["total"] == 5
    assert resumo["urgentes"] >= 2
    assert sum(resumo["por_categoria"].values()) == resumo["total"]


def test_limite_de_mensagens_mostradas(caixa: Path):
    assert len(correio.triar(caixa, limite=2, agora=AGORA)["mensagens"]) == 2


# ---------------------------------------------------------------- padrões


def test_padroes_olham_so_as_enviadas(caixa: Path):
    estilo = correio.padroes(caixa)
    assert estilo["total_enviadas"] == 1
    assert estilo["saudacao"] == "olá"
    assert estilo["fecho"] == "abraços"
    assert estilo["assinatura"] == "Victor"
    assert estilo["usa_lista"] == 100


def test_padroes_sem_enviadas_explicam(tmp_path: Path):
    eml(tmp_path, "recebida.eml", rotulos="Inbox")
    with pytest.raises(correio.CorreioError) as erro:
        correio.padroes(tmp_path)
    assert "Enviados" in str(erro.value)


def test_padroes_por_nome_de_arquivo(tmp_path: Path):
    eml(tmp_path, "sent-2026.eml", de="eu@x.com", corpo="Bom dia,\n\nSegue.\n\nAtt\nVictor")
    estilo = correio.padroes(tmp_path)
    assert estilo["total_enviadas"] == 1
    assert estilo["saudacao"] == "bom dia"
    assert estilo["fecho"] == "att"


# --------------------------------------------------------------- rascunho


def test_rascunho_copia_o_padrao(caixa: Path):
    rascunho = correio.rascunho(
        "ana@empresa.com", "entrega do relatório", ["envio o relatório revisado", "preciso do retorno"], pasta=caixa
    )
    assert rascunho["corpo"].startswith("Olá,")
    assert "- envio o relatório revisado" in rascunho["corpo"]
    assert "Abraços," in rascunho["corpo"]
    assert rascunho["corpo"].rstrip().endswith("Victor")
    assert rascunho["baseado_em"] == 1
    assert any("nada foi enviado" in aviso.lower() for aviso in rascunho["avisos"])


def test_rascunho_sem_enviados_usa_generico(tmp_path: Path):
    eml(tmp_path, "recebida.eml", rotulos="Inbox")
    rascunho = correio.rascunho("ana@empresa.com", "reunião", [], pasta=tmp_path)
    assert rascunho["corpo"].startswith("Olá,")
    assert "atenciosamente" in rascunho["corpo"].lower()
    assert any("genéricos" in aviso for aviso in rascunho["avisos"])


def test_rascunho_um_ponto_vira_frase(tmp_path: Path):
    eml(tmp_path, "recebida.eml", rotulos="Inbox")
    rascunho = correio.rascunho("ana@empresa.com", "entrega", ["segue em anexo"], pasta=tmp_path)
    assert "Escrevo sobre o assunto: entrega." in rascunho["corpo"]
    assert "segue em anexo" in rascunho["corpo"]


def test_rascunho_separa_pontos_por_ponto_e_virgula(tmp_path: Path):
    eml(tmp_path, "recebida.eml", rotulos="Inbox")
    rascunho = correio.rascunho("ana@x.com", "entrega", ["um item; outro item"], pasta=tmp_path)
    assert "- um item" in rascunho["corpo"]
    assert "- outro item" in rascunho["corpo"]


def test_rascunho_sem_destino_recusa():
    with pytest.raises(correio.CorreioError):
        correio.rascunho("", "assunto", [])


def test_rascunho_sem_assunto_recusa():
    with pytest.raises(correio.CorreioError):
        correio.rascunho("ana@x.com", "", [])


def test_arquivo_quebrado_nao_derruba_a_leitura(caixa: Path):
    (caixa / "quebrado.eml").write_bytes(b"\xff\xfe nao e email")
    mensagens = correio.ler(caixa)
    assert len(mensagens) >= 5


def test_modulo_nao_esta_no_gitignore():
    raiz = Path(__file__).resolve().parents[2]
    ignorados = {linha.strip() for linha in (raiz / ".gitignore").read_text(encoding="utf-8").splitlines()}
    assert "server/correio.py" not in ignorados
