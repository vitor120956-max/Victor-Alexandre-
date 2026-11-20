"""A camada de efeito da 0.92.0 — e a trava que a segura.

O dono pediu que os doze itens de “não faz por decisão” passassem a fazer. A
parte que não pode regredir é a outra: **sem `JARVIS_ACOES=1`, nada toca em
nada**. Um teste que só confere “a skill existe” não prova nada — o que prova é
chamar a ação com a trava desligada e ver o plano voltar, sem efeito.

Também estão aqui as guardas de segurança que são fáceis de perder numa
refatoração: senha que não pode vazar no erro, URL com credencial recusada,
conversão fora da tabela fechada, e o teto de destinatários.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import acoes
from server.app import create_app
from server.skill_registry import build_registry

AÇÕES_DA_092 = (
    "email.enviar",
    "google.email",
    "google.listar",
    "google.evento",
    "google.planilha",
    "navegador.abrir",
    "arquivo.converter",
    "diagrama.mermaid",
    "diagrama.dot",
    "reverse.descompilar",
    "lean.testar",
    "submissao.publicar",
    "memoria.embedding",
    "memoria.similaridade",
    "agencia.executar",
    "carreira.candidatar",
    "estudio.tokens",
    "estudio.previa",
)


@pytest.fixture(autouse=True)
def _sem_ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nenhuma variável da máquina do dono pode vazar para o teste."""
    for nome in (
        "JARVIS_ACOES", "JARVIS_SMTP_HOST", "JARVIS_SMTP_USUARIO", "JARVIS_SMTP_SENHA",
        "JARVIS_SMTP_REMETENTE", "JARVIS_GOOGLE_TOKEN", "JARVIS_GITHUB_TOKEN",
        "JARVIS_AI_API_KEY", "JARVIS_EMBEDDINGS_MODEL",
    ):
        monkeypatch.delenv(nome, raising=False)


# ---------------------------------------------------------------------------
# O registro
# ---------------------------------------------------------------------------

# Leitura pura: não grava, não envia, não abre — então não pede confirmação.
LEITURA = ("google.listar", "memoria.embedding", "memoria.similaridade", "acoes.estado")


def test_as_acoes_estao_registradas_com_efeito_e_confirmacao(tmp_path: Path) -> None:
    registro = build_registry(tmp_path / "files")
    ids = {skill["id"] for skill in registro.list()}
    for acao in AÇÕES_DA_092 + ("acoes.estado",):
        assert acao in ids, f"a ação {acao} sumiu do registro"
        definicao = registro.get(acao)
        if acao in LEITURA:
            assert definicao.side_effects is False, f"{acao} é leitura e não deveria ter efeito"
            continue
        assert definicao.side_effects is True, f"{acao} perdeu o aviso de efeito"
        assert definicao.requires_confirmation is True, f"{acao} perdeu a confirmação"


def test_estado_diz_o_que_falta_em_vez_de_fingir(tmp_path: Path) -> None:
    estado = acoes.estado()
    assert estado["ligado"] is False
    assert estado["trava"] == "JARVIS_ACOES"
    assert "JARVIS_SMTP_HOST" in estado["email"]["falta"]
    assert "JARVIS_GOOGLE_TOKEN" in estado["google"]["falta"]
    assert "JARVIS_GITHUB_TOKEN" in estado["github"]["falta"]
    assert isinstance(estado["ferramentas"], dict) and estado["ferramentas"]


# ---------------------------------------------------------------------------
# A trava: sem a variável, só plano
# ---------------------------------------------------------------------------

def test_email_sem_smtp_devolve_o_plano_com_o_que_falta() -> None:
    plano = acoes.enviar_email(para="alguem@exemplo.com", assunto="oi", corpo="teste")
    assert plano["executado"] is False
    assert "JARVIS_SMTP_HOST" in plano["falta"]
    assert "senha de app" in plano["aviso"]
    # Confirmar sem SMTP é erro declarado, não envio silencioso.
    with pytest.raises(acoes.AcoesError) as erro:
        acoes.enviar_email(para="alguem@exemplo.com", assunto="oi", corpo="teste", confirmado=True)
    assert "JARVIS_SMTP_HOST" in str(erro.value)


def test_abrir_sem_trava_nao_abre_navegador(monkeypatch: pytest.MonkeyPatch) -> None:
    chamou: list[str] = []
    monkeypatch.setattr(acoes.webbrowser, "open", lambda *a, **k: chamou.append("abriu") or True)
    # Sem confirmação: plano, sem tocar no navegador.
    plano = acoes.abrir_url("https://exemplo.com")
    assert plano["executado"] is False
    # Com confirmação e sem a trava: recusa nomeando a variável.
    with pytest.raises(acoes.AcoesError) as erro:
        acoes.abrir_url("https://exemplo.com", confirmado=True)
    assert "JARVIS_ACOES" in str(erro.value)
    assert chamou == [], "a aba foi aberta mesmo sem a trava"


def test_abrir_com_trava_chama_o_navegador(monkeypatch: pytest.MonkeyPatch) -> None:
    chamou: list[str] = []
    monkeypatch.setenv("JARVIS_ACOES", "1")
    monkeypatch.setattr(acoes.webbrowser, "open", lambda url, new=0: chamou.append(url) or True)
    resultado = acoes.abrir_url("https://exemplo.com", confirmado=True)
    assert resultado["executado"] is True
    assert chamou == ["https://exemplo.com"]


def test_abrir_recusa_esquema_e_credencial() -> None:
    for ruim in ("file:///etc/passwd", "javascript:alert(1)", "https://user:senha@exemplo.com"):
        with pytest.raises(acoes.AcoesError):
            acoes.abrir_url(ruim, confirmado=False)


def test_toda_acao_confirmada_sem_trava_diz_o_nome_da_variavel(tmp_path: Path) -> None:
    arquivo = tmp_path / "files" / "nota.md"
    arquivo.parent.mkdir(parents=True)
    arquivo.write_text("# oi", encoding="utf-8")
    tentativas = [
        lambda: acoes.converter(origem="nota.md", formato="html", raiz=tmp_path / "files", confirmado=True),
        lambda: acoes.mermaid_svg("flowchart TD\n  A[Um] --> B[Dois]", confirmado=True, raiz=tmp_path / "files"),
        lambda: acoes.rodar_testes(pasta=".", raiz=tmp_path / "files", confirmado=True),
        lambda: acoes.publicar_pr(
            repositorio="dono/projeto", branch="b", base="main", titulo="t", corpo="", arquivos={"a.txt": "x"}, confirmado=True
        ),
        lambda: acoes.estudio_tokens("--bg: #fff\n--fg: #000", confirmado=True, raiz=tmp_path / "files"),
        lambda: acoes.descompilar(arquivo="apk.apk", raiz=tmp_path / "files", confirmado=True),
    ]
    for tentar in tentativas:
        with pytest.raises(acoes.AcoesError) as erro:
            tentar()
        mensagem = str(erro.value)
        # Ou a trava, ou a falta declarada (ferramenta/arquivo/token) — nunca sucesso.
        minuscula = mensagem.lower()
        assert any(pista in minuscula for pista in ("jarvis_acoes", "falta", "não", "instale")), mensagem


# ---------------------------------------------------------------------------
# Segredos nunca voltam
# ---------------------------------------------------------------------------

def test_erro_de_smtp_nao_ecoa_a_senha(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JARVIS_ACOES", "1")
    monkeypatch.setenv("JARVIS_SMTP_HOST", "127.0.0.1")
    monkeypatch.setenv("JARVIS_SMTP_PORTA", "9")  # porta fechada: falha rápido
    monkeypatch.setenv("JARVIS_SMTP_USUARIO", "eu@exemplo.com")
    monkeypatch.setenv("JARVIS_SMTP_SENHA", "senha-secreta-123")
    monkeypatch.setenv("JARVIS_SMTP_REMETENTE", "eu@exemplo.com")
    with pytest.raises(acoes.AcoesError) as erro:
        acoes.enviar_email(para="alguem@exemplo.com", assunto="oi", corpo="teste", confirmado=True)
    assert "senha-secreta-123" not in str(erro.value)
    # E o estado também não vaza a senha.
    assert "senha-secreta-123" not in json.dumps(acoes.estado(), ensure_ascii=False)


def test_email_limita_destinatarios_e_valida_endereco() -> None:
    with pytest.raises(acoes.AcoesError):
        acoes.enviar_email(para=[f"pessoa{i}@exemplo.com" for i in range(11)], assunto="oi", corpo="")
    with pytest.raises(acoes.AcoesError):
        acoes.enviar_email(para="não é e-mail", assunto="oi", corpo="")


# ---------------------------------------------------------------------------
# Conversão: tabela fechada
# ---------------------------------------------------------------------------

def test_conversao_fora_da_tabela_e_recusada_com_a_lista() -> None:
    with pytest.raises(acoes.AcoesError) as erro:
        acoes.converter(origem="x.zip", formato="rar", raiz=Path("/tmp"))
    assert "pdf" in str(erro.value) or "mp3" in str(erro.value)


def test_conversoes_possiveis_marca_o_que_a_maquina_tem() -> None:
    lista = acoes.conversoes_possiveis()
    assert lista and all({"de", "para", "ferramenta", "disponivel"} <= set(item) for item in lista)
    assert all(item["de"] and item["para"] for item in lista)


# ---------------------------------------------------------------------------
# Diagramas de verdade
# ---------------------------------------------------------------------------

def test_mermaid_desenha_svg_com_os_nos(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("JARVIS_ACOES", "1")
    raiz = tmp_path / "files"
    raiz.mkdir()
    resultado = acoes.mermaid_svg(
        "flowchart TD\n  A[Cliente] --> B[Pedido]\n  B --> C[Pago]",
        confirmado=True, raiz=raiz, nome="fluxo.svg",
    )
    assert resultado["executado"] is True
    svg = (raiz / "fluxo.svg").read_text(encoding="utf-8")
    assert svg.startswith("<svg") or "<svg" in svg
    for rotulo in ("Cliente", "Pedido", "Pago"):
        assert rotulo in svg
    assert resultado["arestas"] == 2


def test_mermaid_recusa_o_que_nao_desenha() -> None:
    with pytest.raises(acoes.AcoesError) as erro:
        acoes.mermaid_svg("sequenceDiagram\n  A->>B: oi")
    assert "flowchart" in str(erro.value)


# ---------------------------------------------------------------------------
# Estúdio: compila de verdade, sem inventar valor
# ---------------------------------------------------------------------------

def test_estudio_compila_tokens_e_declara_o_que_falta(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("JARVIS_ACOES", "1")
    raiz = tmp_path / "files"
    raiz.mkdir()
    resultado = acoes.estudio_tokens(
        "--bg: #0b0b0c\n--fg: #f5f5f5\n--accent: #e4572e", confirmado=True, raiz=raiz,
    )
    assert resultado["executado"] is True
    css = (raiz / "tokens.css").read_text(encoding="utf-8")
    assert "--bg: #0b0b0c;" in css and "--accent: #e4572e;" in css
    assert resultado["slots"] == 56
    assert resultado["faltando_total"] > 0, "o compilador não pode dizer que preencheu os 56"
    # Nada de valor inventado para o que não foi declarado.
    assert "--space-8" not in css


def test_estudio_recusa_tabela_sem_tema() -> None:
    with pytest.raises(acoes.AcoesError):
        acoes.estudio_tokens("--accent: #fff")


def test_estudio_previa_e_um_html_unico_sem_rede() -> None:
    pagina = acoes.estudio_previa(tokens="--bg: #0b0b0c\n--fg: #f5f5f5")
    assert pagina["executado"] is False
    assert "<!doctype html>" in pagina["html"].lower()
    assert "http://" not in pagina["html"].replace("http://www.w3.org", "")
    assert "não há PNG" in pagina["nota"]


# ---------------------------------------------------------------------------
# Carreira: carta reprovada não vira candidatura
# ---------------------------------------------------------------------------

def test_candidatura_recusa_carta_sem_pesquisa(tmp_path: Path) -> None:
    vaga = "Buscamos pessoa analista de dados para time de varejo, com SQL e Python, modelo híbrido em São Paulo."
    curriculo = "Ana Souza\nanalista de dados\nPython, SQL\n2020-2024 Acme\n"
    with pytest.raises(acoes.AcoesError) as erro:
        acoes.carreira_candidatar(
            vaga=vaga, curriculo=curriculo, destino="rh@exemplo.com",
            confirmado=False, raiz=tmp_path,
        )
    assert "carta" in str(erro.value).lower()


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------

def test_rota_de_estado_responde_sem_trava(tmp_path: Path) -> None:
    cliente = TestClient(create_app(registry=build_registry(tmp_path / "files")))
    resposta = cliente.get("/api/acoes/estado")
    assert resposta.status_code == 200
    dados = resposta.json()["result"]
    assert dados["ligado"] is False
    assert isinstance(dados["conversoes"], list)


def test_rota_de_email_sem_confirmacao_devolve_plano(tmp_path: Path) -> None:
    cliente = TestClient(create_app(registry=build_registry(tmp_path / "files")))
    resposta = cliente.post("/api/acoes/email", json={"para": "a@b.com", "assunto": "oi", "corpo": "teste"})
    assert resposta.status_code == 200
    assert resposta.json()["result"]["executado"] is False
