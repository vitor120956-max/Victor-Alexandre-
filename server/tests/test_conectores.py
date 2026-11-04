"""Conectores: ler a caixa por IMAP e falar com o WhatsApp sem prometer demais.

O que estes testes prendem, em uma frase cada:

- a leitura é **somente leitura** de verdade: `EXAMINE`, `BODY.PEEK`, e nenhum
  comando que marque como lido;
- a senha nunca volta numa resposta, nem quando o provedor recusa o login;
- a triagem ao vivo aplica as mesmas regras do `correio`, na mesma ordem;
- o link do WhatsApp põe o 55 do Brasil e não envia nada;
- a conversa exportada (`.txt`) é lida nos dois formatos que o app usa.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from server import chaves, conectores


# ---------------------------------------------------------------------------
# Falso: um servidor IMAP que registra o que foi pedido
# ---------------------------------------------------------------------------

CABECALHO_INTIMACAO = (
    b"From: Tribunal de Justica <intimacao@tjsc.jus.br>\r\n"
    b"To: dono@example.com\r\n"
    b"Subject: Intimacao para audiencia\r\n"
    b"Date: Mon, 03 Nov 2026 10:00:00 -0300\r\n\r\n"
)
CABECALHO_FATURA = (
    b"From: Energia Sul <fatura@energiasul.com.br>\r\n"
    b"To: dono@example.com\r\n"
    b"Subject: Sua fatura de energia vence em 05/11/2026\r\n"
    b"Date: Tue, 04 Nov 2026 08:00:00 -0300\r\n\r\n"
)
CABECALHO_PROMO = (
    b"From: Loja <noreply@loja.com.br>\r\n"
    b"To: dono@example.com\r\n"
    b"Subject: Promocao da semana\r\n"
    b"Date: Tue, 04 Nov 2026 09:00:00 -0300\r\n\r\n"
)


class FakeIMAP:
    """Imita o `imaplib.IMAP4_SSL` no que o conector usa — e nada mais.

    `store` existe só para provar que **não** é chamado: marcar como lido é
    exatamente o que o conector promete não fazer.
    """

    def __init__(self, mensagens: list[bytes] | None = None, falha_login: bool = False) -> None:
        self.mensagens = mensagens if mensagens is not None else [CABECALHO_INTIMACAO, CABECALHO_FATURA, CABECALHO_PROMO]
        self.falha_login = falha_login
        self.selects: list[tuple[str, bool]] = []
        self.fetches: list[str] = []
        self.buscas: list[str] = []
        self.store_chamado = False
        self.logout_chamado = False
        self.fechou = False

    def login(self, usuario: str, senha: str) -> tuple[str, list[bytes]]:
        if self.falha_login:
            raise __import__("imaplib").IMAP4.error("AUTHENTICATIONFAILED senha errada")
        return "OK", [b"logged in"]

    def select(self, pasta: str = "INBOX", readonly: bool = False) -> tuple[str, list[bytes]]:
        self.selects.append((pasta, readonly))
        return "OK", [str(len(self.mensagens)).encode()]

    def search(self, charset: str, criterio: str) -> tuple[str, list[bytes]]:
        self.buscas.append(criterio)
        ids = b" ".join(str(i + 1).encode() for i in range(len(self.mensagens)))
        return "OK", [ids]

    def fetch(self, uid: bytes, spec: str) -> tuple[str, list[tuple[bytes, bytes]]]:
        self.fetches.append(spec)
        indice = int(uid) - 1
        return "OK", [(b"1 (BODY[HEADER.FIELDS ...] {0}", self.mensagens[indice])]

    def store(self, *_args: object) -> tuple[str, list[bytes]]:
        self.store_chamado = True
        return "OK", []

    def close(self) -> tuple[str, list[bytes]]:
        self.fechou = True
        return "OK", []

    def logout(self) -> tuple[str, list[bytes]]:
        self.logout_chamado = True
        return "OK", []


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    caminho = tmp_path / ".env"
    caminho.write_bytes(b"JARVIS_DONO=1\r\nJARVIS_EMAIL_USUARIO=\r\nJARVIS_EMAIL_SENHA=\r\n")
    monkeypatch.setattr(chaves, "ENV_CAMINHO", caminho)
    for nome in ("JARVIS_EMAIL_IMAP", "JARVIS_EMAIL_USUARIO", "JARVIS_EMAIL_SENHA", "JARVIS_EMAIL_PASTA"):
        monkeypatch.delenv(nome, raising=False)
    return caminho


def _configurar(senha: str = "abcdefghijklmnop") -> dict[str, object]:
    return conectores.configurar_email("dono@gmail.com", senha)


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

def test_o_servidor_sai_do_dominio_do_email(env: Path):
    resultado = _configurar()
    assert resultado["email_configurado"] is True
    assert resultado["conectores"][0]["servidor"] == "imap.gmail.com"
    assert b"JARVIS_EMAIL_IMAP=imap.gmail.com\r\n" in env.read_bytes()


def test_outros_dominios_conhecidos(env: Path):
    conectores.configurar_email("dono@outlook.com", "abcdefghijklmnop")
    assert conectores.estado()["conectores"][0]["servidor"] == "outlook.office365.com"


def test_dominio_desconhecido_pede_o_servidor(env: Path):
    with pytest.raises(conectores.ConectorError, match="servidor IMAP"):
        conectores.configurar_email("dono@dominio-estranho.dev", "abcdefghijklmnop")
    # Com o servidor dito à mão, funciona.
    assert conectores.configurar_email("dono@dominio-estranho.dev", "abcdefghijklmnop", "imap.estranho.dev")["email_configurado"]


def test_senha_curta_e_recusada_com_a_dica_da_senha_de_app(env: Path):
    with pytest.raises(conectores.ConectorError, match="senha de app"):
        conectores.configurar_email("dono@gmail.com", "1234")
    assert b"JARVIS_EMAIL_SENHA=\r\n" in env.read_bytes()


def test_a_senha_nao_volta_na_resposta(env: Path):
    segredo = "abcdefghijklmnop"
    resultado = _configurar(segredo)
    import json

    assert segredo not in json.dumps(resultado)


def test_esquecer_apaga_so_o_email(env: Path):
    _configurar()
    conectores.esquecer_email()
    bruto = env.read_bytes()
    assert b"JARVIS_EMAIL_USUARIO=\r\n" in bruto
    assert b"JARVIS_DONO=1" in bruto  # o resto do `.env` fica
    assert conectores.estado()["email_configurado"] is False


# ---------------------------------------------------------------------------
# Leitura: somente leitura, de verdade
# ---------------------------------------------------------------------------

def test_a_caixa_e_aberta_em_modo_somente_leitura(env: Path):
    _configurar()
    falso = FakeIMAP()
    conectores.ler_caixa(limite=3, abrir=lambda _host: falso)
    assert falso.selects == [("INBOX", True)]  # EXAMINE
    assert falso.store_chamado is False  # nada foi marcado como lido
    assert falso.fechou and falso.logout_chamado


def test_o_fetch_pede_peek_e_so_cabecalhos(env: Path):
    _configurar()
    falso = FakeIMAP()
    conectores.ler_caixa(limite=3, abrir=lambda _host: falso)
    assert falso.fetches
    assert all("PEEK" in spec for spec in falso.fetches)
    assert all("HEADER.FIELDS" in spec for spec in falso.fetches)


def test_a_busca_respeita_a_janela_de_dias(env: Path):
    _configurar()
    falso = FakeIMAP()
    conectores.ler_caixa(limite=3, dias=2, abrir=lambda _host: falso)
    assert "SINCE" in falso.buscas[0]


def test_le_assunto_remetente_e_data(env: Path):
    _configurar()
    leitura = conectores.ler_caixa(limite=3, abrir=lambda _host: FakeIMAP())
    assert leitura["total"] == 3
    primeira = leitura["mensagens"][0]
    assert set(primeira) >= {"de", "assunto", "data", "arquivo"}
    assert any("Intimacao" in item["assunto"] for item in leitura["mensagens"])
    assert all(item["arquivo"].startswith("imap:") for item in leitura["mensagens"])


def test_sem_configuracao_a_frase_diz_o_que_falta(env: Path):
    with pytest.raises(conectores.ConectorError, match="cartão Conectores"):
        conectores.ler_caixa(abrir=lambda _host: FakeIMAP())


def test_login_recusado_nao_ecoa_a_senha_e_fala_de_senha_de_app(env: Path):
    _configurar("senhanormal12345")
    with pytest.raises(conectores.ConectorError) as erro:
        conectores.ler_caixa(abrir=lambda _host: FakeIMAP(falha_login=True))
    texto = str(erro.value)
    assert "senha de app" in texto
    assert "senhanormal" not in texto


# ---------------------------------------------------------------------------
# Triagem ao vivo
# ---------------------------------------------------------------------------

def test_triagem_ao_vivo_usa_as_regras_do_correio(env: Path):
    _configurar()
    triagem = conectores.triar_ao_vivo(limite=10, abrir=lambda _host: FakeIMAP())
    assert triagem["fonte"] == "imap"
    assert triagem["total"] == 3
    prioridades = [item["prioridade"] for item in triagem["mensagens"]]
    assert prioridades == sorted(prioridades, reverse=True)
    assert triagem["mensagens"][0]["categoria"] == "intimacao"
    assert triagem["urgentes"] >= 1


def test_o_texto_da_triagem_mostra_prioridade_e_motivo(env: Path):
    _configurar()
    triagem = conectores.triar_ao_vivo(limite=10, abrir=lambda _host: FakeIMAP())
    texto = conectores.texto_da_triagem(triagem)
    assert "intimacao" in texto.lower()
    assert texto.count("\n- ") >= 2


def test_caixa_vazia_nao_e_erro(env: Path):
    _configurar()
    triagem = conectores.triar_ao_vivo(abrir=lambda _host: FakeIMAP(mensagens=[]))
    assert triagem["total"] == 0
    assert "Nenhum e-mail" in triagem["resumo"]


def test_testar_email_responde_com_o_resumo_da_caixa(env: Path):
    _configurar()
    prova = conectores.testar_email(abrir=lambda _host: FakeIMAP())
    assert prova["ok"] is True
    assert "3 e-mail" in prova["resumo"]


# ---------------------------------------------------------------------------
# WhatsApp
# ---------------------------------------------------------------------------

def test_link_do_whatsapp_poe_o_55_e_o_texto(env: Path):
    link = conectores.whatsapp_link("48 99999-1234", "oi, tudo bem?")
    assert link["numero"] == "5548999991234"
    assert link["url"].startswith("https://web.whatsapp.com/send?phone=5548999991234")
    assert "text=oi%2C%20tudo%20bem%3F" in link["url"]
    assert link["enviado"] is False


def test_numero_que_ja_tem_55_nao_ganha_outro(env: Path):
    assert conectores.whatsapp_link("5548999991234")["numero"] == "5548999991234"


def test_numero_curto_e_recusado(env: Path):
    with pytest.raises(conectores.ConectorError, match="DDD"):
        conectores.whatsapp_link("1234")


def test_conversa_exportada_no_formato_antigo(env: Path, tmp_path: Path):
    arquivo = tmp_path / "Conversa do WhatsApp com Ana.txt"
    arquivo.write_text(
        "12/03/2024 14:05 - Ana: oi\n"
        "12/03/2024 14:06 - Voce: tudo bem?\n"
        "linha de sistema sem formato\n",
        encoding="utf-8",
    )
    conversa = conectores.ler_conversa(arquivo)
    assert conversa["total"] == 2
    assert conversa["participantes"] == {"Ana": 1, "Voce": 1}
    assert conversa["mensagens"][0]["texto"] == "oi"


def test_conversa_exportada_no_formato_novo(env: Path, tmp_path: Path):
    arquivo = tmp_path / "chat.txt"
    arquivo.write_text(
        "[12/03/2024, 14:05:32] Ana: mensagem nova\n[12/03/2024, 14:07:00] Ana: outra\n",
        encoding="utf-8",
    )
    conversa = conectores.ler_conversa(arquivo)
    assert conversa["total"] == 2
    assert conversa["participantes"]["Ana"] == 2


def test_arquivo_que_nao_e_whatsapp_e_recusado(env: Path, tmp_path: Path):
    arquivo = tmp_path / "qualquer.txt"
    arquivo.write_text("linha qualquer\noutra linha\n", encoding="utf-8")
    with pytest.raises(conectores.ConectorError, match="Exportar conversa"):
        conectores.ler_conversa(arquivo)


def test_estado_do_whatsapp_conta_as_conversas(env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "a.txt").write_text("12/03/2024 14:05 - Ana: oi\n", encoding="utf-8")
    monkeypatch.setattr(conectores, "pasta_whatsapp", lambda: tmp_path)
    estado = conectores.estado_whatsapp()
    assert estado["total"] == 1
    assert estado["arquivos"] == ["a.txt"]


# ---------------------------------------------------------------------------
# O cartão inteiro
# ---------------------------------------------------------------------------

def test_estado_lista_tres_conectores_com_nivel_e_preco(env: Path):
    dados = conectores.estado()
    ids = [item["id"] for item in dados["conectores"]]
    assert ids == ["email", "navegador", "whatsapp"]
    for item in dados["conectores"]:
        assert item["nivel"], item["id"]
        assert item["como"], item["id"]
        assert item["gratis"] == "sim", item["id"]
    assert "2 de 3" in dados["resumo"]
    # A honestidade sobre OAuth fica escrita, não escondida.
    assert "Google Cloud" in dados["nota"]


def test_a_variavel_do_email_nao_entra_na_lista_de_chaves(env: Path):
    """Senha de app não é chave de IA: não pode aparecer em `estado()` das chaves."""
    _configurar()
    assert "JARVIS_EMAIL_SENHA" not in chaves.estado()
    assert os.environ.get("JARVIS_EMAIL_USUARIO") == "dono@gmail.com"
