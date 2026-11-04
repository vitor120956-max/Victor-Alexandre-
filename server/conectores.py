"""Conectores: como o JARVIS chega ao Gmail, ao WhatsApp e ao resto.

## A pergunta que abriu este módulo

*“Mas quero que o modelo tenha acesso à minha caixa, ou o JARVIS acesso ao
Gmail, WhatsApp e conectores igual a você.”*

Dá para separar em três níveis, e a diferença entre eles é o que decide se o
recurso funciona ou vira promessa:

| nível | o que é | precisa de quê | o que o JARVIS consegue |
|---|---|---|---|
| **1. sessão do navegador** | você já está logado; o JARVIS monta o link certo e abre | nada | abrir a busca pronta, abrir a conversa do WhatsApp, preencher o texto |
| **2. IMAP** | o JARVIS lê a caixa pelo protocolo, só leitura | senha de app (uma vez) | **ler assunto, remetente e data de verdade** e triar por regra |
| **3. OAuth** | o JARVIS recebe um token em seu nome | projeto no Google Cloud + consentimento | ler, marcar como lido, enviar, agenda |

Os conectores que eu uso aqui (Gmail, Agenda, Drive, Notion…) funcionam no nível
3, **e o token fica no servidor de quem hospeda o agente** — não no seu PC. Para
o JARVIS local, o nível 3 existe, mas exige que **você** crie o projeto no Google
Cloud; é burocracia sua, não minha. Por isso o padrão daqui é o nível 2: IMAP com
senha de app, que é grátis, não pede cartão, não pede projeto e lê de verdade.

## O que este módulo faz

- **IMAP somente leitura** (`EXAMINE`): nada é marcado como lido, nada é apagado,
  nada é enviado. Abre, lê os cabeçalhos, fecha.
- **Triagem ao vivo**: as mesmas regras determinísticas do `correio` (intimação
  100, fatura 85, governo 75, segurança 70…) aplicadas ao que está na caixa
  agora, sem exportar nada.
- **WhatsApp**: link direto para a conversa (`web.whatsapp.com/send?phone=`), que
  abre no navegador onde você já pareou o celular — e leitura dos arquivos
  **exportados** de conversa (`.txt`), que é o único jeito honesto de o JARVIS
  ler mensagens sem violar os termos do WhatsApp.
- **Estado de cada conector**, com o que falta para ele funcionar — em vez de um
  botão que promete e falha depois.
"""
from __future__ import annotations

import email
import imaplib
import re
import ssl
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable

from . import chaves as chaves_mod
from . import correio
from . import dados as dados_locais

# ---------------------------------------------------------------------------
# Onde as coisas ficam
# ---------------------------------------------------------------------------
IMAP_PADRAO = "imap.gmail.com"

VARS = {
    "servidor": "JARVIS_EMAIL_IMAP",
    "usuario": "JARVIS_EMAIL_USUARIO",
    "senha": "JARVIS_EMAIL_SENHA",
    "pasta": "JARVIS_EMAIL_PASTA",
}

LIMITE_MAX = 60
DIAS_PADRAO = 7

_CABECALHOS = "(BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE)])"


class ConectorError(ValueError):
    """Configuração faltando ou provedor recusando — com frase para a tela."""


# ---------------------------------------------------------------------------
# Ler o `.env` (mesmo arquivo e mesmo cuidado do resto do projeto)
# ---------------------------------------------------------------------------

def _valor(nome: str) -> str:
    return (chaves_mod.ler_valor(nome) or "").strip()


def _gravar(valores: dict[str, str]) -> None:
    texto = chaves_mod._texto_atual()  # noqa: SLF001 - o `.env` é o mesmo
    for nome, valor in valores.items():
        texto = chaves_mod.definir(texto, nome, valor)
    chaves_mod.gravar(texto)
    # `aplicar_no_ambiente` cuida das chaves de IA; as da caixa de e-mail têm
    # lista própria e são aplicadas aqui, para valerem sem reiniciar a API.
    import os  # noqa: PLC0415 (import local: só este caminho precisa)

    for nome in VARS.values():
        os.environ[nome] = chaves_mod.ler_valor(nome)


def _mascarar_usuario(usuario: str) -> str:
    if "@" not in usuario:
        return usuario[:2] + "…" if usuario else ""
    nome, dominio = usuario.split("@", 1)
    return f"{nome[:2]}…@{dominio}"


# ---------------------------------------------------------------------------
# Estado
# ---------------------------------------------------------------------------

def _estado_email() -> dict[str, Any]:
    usuario = _valor(VARS["usuario"])
    senha = _valor(VARS["senha"])
    servidor = _valor(VARS["servidor"]) or IMAP_PADRAO
    pasta = _valor(VARS["pasta"]) or "INBOX"
    pronto = bool(usuario and senha)
    return {
        "id": "email",
        "nome": "Sua caixa de e-mail",
        "nivel": "IMAP somente leitura",
        "pronto": pronto,
        "usuario": _mascarar_usuario(usuario),
        "servidor": servidor,
        "pasta": pasta,
        "gratis": "sim",
        "precisa": (
            "nada — já está lendo a caixa"
            if pronto
            else "uma senha de app do seu e-mail (não é a senha normal; é gerada em 1 minuto)"
        ),
        "como": (
            "O JARVIS entra por IMAP em modo **somente leitura**: `EXAMINE`, cabeçalhos "
            "com `BODY.PEEK`. Nada é marcado como lido, apagado ou enviado."
        ),
        "onde": (
            "myaccount.google.com/apppasswords"
            if servidor.endswith("gmail.com")
            else "o painel do seu provedor de e-mail"
        ),
    }


def _estado_whatsapp() -> dict[str, Any]:
    exportados = _conversas_exportadas()
    return {
        "id": "whatsapp",
        "nome": "WhatsApp",
        "nivel": "navegador + conversas exportadas",
        "pronto": True,
        "conversas_exportadas": len(exportados),
        "gratis": "sim",
        "precisa": (
            "nada para abrir conversas; exportar o `.txt` para o JARVIS ler o conteúdo"
            if exportados
            else "para ler o conteúdo, exporte a conversa como .txt e ponha em storage/whatsapp"
        ),
        "como": (
            "Não existe API grátis do WhatsApp para uso pessoal. O JARVIS faz o que é "
            "possível sem violar os termos: **abre a conversa** em `web.whatsapp.com` "
            "(você já pareou o celular) e monta o link com o texto pronto; para **ler** "
            "mensagens, usa o `.txt` que o próprio WhatsApp exporta."
        ),
        "onde": "web.whatsapp.com",
    }


def _estado_navegador() -> dict[str, Any]:
    return {
        "id": "navegador",
        "nome": "Gmail e sites pela sessão do navegador",
        "nivel": "sessão do navegador",
        "pronto": True,
        "gratis": "sim",
        "precisa": "nada — usa o navegador onde você já está logado",
        "como": (
            "Monta a busca pronta do Gmail (`correio.gmail-busca`) e abre. Nada é lido "
            "pelo JARVIS: o filtro roda no seu navegador, na sua sessão."
        ),
        "onde": "mail.google.com",
    }


def estado() -> dict[str, Any]:
    """O que a tela mostra: cada conector, o nível e o que falta."""
    email = _estado_email()
    conectores = [email, _estado_navegador(), _estado_whatsapp()]
    prontos = sum(1 for item in conectores if item["pronto"])
    return {
        "conectores": conectores,
        "prontos": prontos,
        "total": len(conectores),
        "email_configurado": email["pronto"],
        "resumo": (
            ("A caixa de e-mail está ligada no JARVIS." if email["pronto"] else "A caixa de e-mail ainda não está ligada.")
            + f" {prontos} de {len(conectores)} conectores prontos."
        ),
        "nota": (
            "O nível mais alto (OAuth: enviar, marcar como lido, agenda) funciona, mas exige "
            "que você crie um projeto no Google Cloud. É burocracia sua, não minha — por isso "
            "o padrão é IMAP somente leitura, que resolve ler e triar sem conta de desenvolvedor."
        ),
    }


# ---------------------------------------------------------------------------
# Configurar a caixa
# ---------------------------------------------------------------------------

def _servidor_do_email(usuario: str) -> str:
    dominio = usuario.split("@")[-1].lower() if "@" in usuario else ""
    mapa = {
        "gmail.com": "imap.gmail.com",
        "googlemail.com": "imap.gmail.com",
        "outlook.com": "outlook.office365.com",
        "hotmail.com": "outlook.office365.com",
        "live.com": "outlook.office365.com",
        "yahoo.com": "imap.mail.yahoo.com",
        "bol.com.br": "imap.bol.com.br",
        "uol.com.br": "imap.uol.com.br",
        "terra.com.br": "imap.terra.com.br",
    }
    return mapa.get(dominio, "")


def configurar_email(usuario: str, senha: str, servidor: str = "", pasta: str = "") -> dict[str, Any]:
    """Grava usuário, senha de app e servidor no `.env`. A senha nunca volta."""
    limpo_usuario = (usuario or "").strip()
    limpa_senha = (senha or "").strip().replace(" ", "")  # o Google mostra com espaços
    if "@" not in limpo_usuario:
        raise ConectorError("diga o e-mail inteiro (nome@dominio.com)")
    if len(limpa_senha) < 8:
        raise ConectorError(
            "a senha de app tem 16 letras. A senha normal da conta não funciona por IMAP — "
            "gere a de app no painel do provedor."
        )
    alvo_servidor = (servidor or "").strip() or _servidor_do_email(limpo_usuario)
    if not alvo_servidor:
        raise ConectorError(
            "não conheço o servidor IMAP desse domínio. Diga o endereço (ex.: imap.gmail.com)."
        )
    _gravar(
        {
            VARS["usuario"]: limpo_usuario,
            VARS["senha"]: limpa_senha,
            VARS["servidor"]: alvo_servidor,
            VARS["pasta"]: (pasta or "").strip() or "INBOX",
        }
    )
    return {**estado(), "salvo": True}


def esquecer_email() -> dict[str, Any]:
    """Apaga usuário e senha do `.env`. O resto do arquivo fica igual."""
    _gravar({VARS["usuario"]: "", VARS["senha"]: ""})
    return {**estado(), "apagado": True}


# ---------------------------------------------------------------------------
# IMAP
# ---------------------------------------------------------------------------

def _conectar(abrir: Callable[[str], Any] | None = None) -> Any:
    usuario = _valor(VARS["usuario"])
    senha = _valor(VARS["senha"])
    if not usuario or not senha:
        raise ConectorError(
            "a caixa de e-mail ainda não está configurada: cole o e-mail e a senha de app "
            "no cartão Conectores."
        )
    servidor = _valor(VARS["servidor"]) or IMAP_PADRAO
    fabrica = abrir or (lambda host: imaplib.IMAP4_SSL(host, ssl_context=ssl.create_default_context()))
    try:
        conexao = fabrica(servidor)
    except (OSError, imaplib.IMAP4.error) as exc:
        raise ConectorError(
            f"não consegui abrir {servidor} ({type(exc).__name__}) — internet ou servidor fora do ar"
        ) from exc
    try:
        conexao.login(usuario, senha)
    except imaplib.IMAP4.error as exc:
        # Nunca repete o texto do servidor: ele pode ecoar o usuário.
        raise ConectorError(
            "o provedor recusou o login. Quase sempre é senha normal no lugar da senha de app: "
            "gere a de app (16 letras) no painel e cole de novo."
        ) from exc
    return conexao


def _decodificar(bruto: bytes | str | None) -> str:
    if not bruto:
        return ""
    if isinstance(bruto, bytes):
        bruto = bruto.decode("utf-8", errors="replace")
    try:
        return " ".join(str(make_header(decode_header(bruto))).split())
    except (UnicodeDecodeError, LookupError):
        return " ".join(str(bruto).split())


def _data_iso(bruto: str) -> str:
    try:
        achada = parsedate_to_datetime(bruto)
    except (TypeError, ValueError):
        return ""
    if achada is None:
        return ""
    if achada.tzinfo is None:
        achada = achada.replace(tzinfo=timezone.utc)
    return achada.astimezone(timezone.utc).isoformat()


def _mensagem_do_cabecalho(bruto: bytes, uid: str) -> dict[str, Any]:
    """Transforma os cabeçalhos em algo que `correio.classificar` entende."""
    texto = bruto.decode("utf-8", errors="replace")
    cabecalho = email.message_from_string(texto)
    nome, endereco = parseaddr(_decodificar(cabecalho.get("From", "")))
    return {
        "de": endereco or _decodificar(cabecalho.get("From", "")),
        "de_nome": nome,
        "para": parseaddr(_decodificar(cabecalho.get("To", "")))[1],
        "assunto": _decodificar(cabecalho.get("Subject", ""))[:200],
        # Sem corpo: IMAP traz só cabeçalho, de propósito. O assunto basta para
        # triar (as regras do correio olham assunto + corpo + remetente), e não
        # baixar o corpo é o que mantém a leitura rápida e discreta.
        "corpo": "",
        "data": _data_iso(_decodificar(cabecalho.get("Date", ""))),
        "rotulos": "",
        "arquivo": f"imap:{uid}",
    }


def ler_caixa(
    limite: int = 20,
    dias: int = DIAS_PADRAO,
    *,
    abrir: Callable[[str], Any] | None = None,
    agora: datetime | None = None,
) -> dict[str, Any]:
    """Lê os cabeçalhos dos e-mails recentes. Somente leitura, sem marcar nada."""
    quantos = max(1, min(int(limite or 20), LIMITE_MAX))
    janela = max(1, min(int(dias or DIAS_PADRAO), 365))
    hoje = (agora or datetime.now(timezone.utc))
    desde = (hoje - timedelta(days=janela)).strftime("%d-%b-%Y")
    pasta = _valor(VARS["pasta"]) or "INBOX"

    conexao = _conectar(abrir)
    try:
        # `readonly=True` = EXAMINE: o servidor **não** marca como lido.
        tipico, total = conexao.select(pasta, readonly=True)
        if tipico != "OK":
            raise ConectorError(f"não consegui abrir a pasta “{pasta}” da caixa.")
        _, achados = conexao.search(None, f'(SINCE "{desde}")')
        ids = (achados[0] or b"").split() if achados else []
        ids = ids[-quantos:]  # os mais recentes
        mensagens: list[dict[str, Any]] = []
        for uid in ids:
            _, partes = conexao.fetch(uid, _CABECALHOS)
            for parte in partes or []:
                if isinstance(parte, tuple) and len(parte) > 1:
                    mensagens.append(_mensagem_do_cabecalho(parte[1], uid.decode() if isinstance(uid, bytes) else str(uid)))
                elif isinstance(parte, bytes):
                    mensagens.append(_mensagem_do_cabecalho(parte, str(uid)))
    finally:
        try:
            conexao.close()
        except (imaplib.IMAP4.error, OSError):
            pass
        try:
            conexao.logout()
        except (imaplib.IMAP4.error, OSError):
            pass

    mensagens.sort(key=lambda item: item.get("data") or "", reverse=True)
    return {
        "fonte": "imap",
        "pasta": pasta,
        "janela_dias": janela,
        "total": len(mensagens),
        "mensagens": mensagens,
        "resumo": (
            f"{len(mensagens)} e-mail(s) nos últimos {janela} dia(s) em {pasta}."
            if mensagens
            else f"Nenhum e-mail nos últimos {janela} dia(s) em {pasta}."
        ),
    }


def testar_email(abrir: Callable[[str], Any] | None = None) -> dict[str, Any]:
    """Login de verdade + contagem da caixa. É o botão Testar do cartão."""
    leitura = ler_caixa(limite=5, dias=DIAS_PADRAO, abrir=abrir)
    return {
        "ok": True,
        "resumo": "A caixa respondeu: " + leitura["resumo"],
        "mensagens": leitura["mensagens"],
    }


def triar_ao_vivo(
    limite: int = 25,
    dias: int = DIAS_PADRAO,
    *,
    abrir: Callable[[str], Any] | None = None,
    agora: datetime | None = None,
) -> dict[str, Any]:
    """Triagem pela regra do `correio`, aplicada ao que está na caixa agora.

    O modelo (ou você) recebe a lista ordenada por importância; o texto do corpo
    não é baixado, então o que sai daqui é assunto, remetente, data e motivo.
    """
    leitura = ler_caixa(limite=limite, dias=dias, abrir=abrir, agora=agora)
    itens: list[dict[str, Any]] = []
    for mensagem in leitura["mensagens"]:
        ficha = correio.classificar(mensagem, agora)
        itens.append(
            {
                "prioridade": ficha["prioridade"],
                "categoria": ficha["categoria"],
                "rotulo": ficha["rotulo"],
                "motivos": ficha["motivos"],
                "vencimento": ficha["vencimento"],
                "dias_para_vencer": ficha["dias_para_vencer"],
                "assunto": mensagem["assunto"],
                "de": mensagem["de"],
                "data": mensagem["data"],
                "arquivo": mensagem["arquivo"],
            }
        )
    ordenadas = sorted(itens, key=lambda item: (-item["prioridade"], item.get("data") or ""))
    contagem: dict[str, int] = {}
    for item in itens:
        contagem[item["rotulo"]] = contagem.get(item["rotulo"], 0) + 1
    urgentes = [item for item in ordenadas if item["prioridade"] >= 85]
    return {
        "fonte": "imap",
        "pasta": leitura["pasta"],
        "total": len(itens),
        "por_categoria": contagem,
        "urgentes": len(urgentes),
        "mensagens": ordenadas[: max(1, min(int(limite or 25), LIMITE_MAX))],
        "resumo": (
            f"{len(itens)} e-mail(s) lido(s) da caixa; {len(urgentes)} urgente(s)."
            if itens
            else leitura["resumo"]
        ),
    }


def texto_da_triagem(triagem: dict[str, Any], limite: int = 12) -> str:
    """Versão em linhas para o chat — o que o modelo (ou você) lê."""
    if not triagem.get("mensagens"):
        return triagem.get("resumo") or "A caixa está vazia nesta janela."
    linhas = [triagem.get("resumo", "")]
    for item in triagem["mensagens"][:limite]:
        quando = (item.get("data") or "")[:10]
        motivo = ", ".join(item.get("motivos") or []) or "sem marcador"
        linhas.append(
            f"- [{item['prioridade']}] {item.get('assunto') or '(sem assunto)'} — {item.get('de') or '?'} "
            f"({quando}) · {item['rotulo']} · {motivo}"
        )
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# WhatsApp
# ---------------------------------------------------------------------------

def whatsapp_link(numero: str, texto: str = "") -> dict[str, Any]:
    """Link que abre a conversa no WhatsApp Web com o texto pronto.

    Não envia nada: quem aperta Enter é você. Montar o link é tudo o que dá para
    fazer sem API paga e sem violar os termos.
    """
    digitos = re.sub(r"\D", "", numero or "")
    if len(digitos) < 10:
        raise ConectorError("diga o número com DDD (ex.: 48 99999-1234) ou com o país (55 48 …).")
    if len(digitos) <= 11 and not digitos.startswith("55"):
        digitos = "55" + digitos  # Brasil por padrão: quem digita 48… quer DDD daqui
    if len(digitos) < 12 or len(digitos) > 15:
        raise ConectorError("número com tamanho estranho: use DDD + número, com o 55 na frente se for Brasil.")
    from urllib.parse import quote

    url = f"https://web.whatsapp.com/send?phone={digitos}"
    if texto.strip():
        url += "&text=" + quote(texto.strip()[:1500])
    return {
        "numero": digitos,
        "url": url,
        "texto": texto.strip()[:1500],
        "enviado": False,
        "aviso": (
            "Abre a conversa no navegador onde o WhatsApp Web já está pareado. "
            "O texto vai no campo de mensagem; quem envia é você (aperte Enter)."
        ),
    }


def pasta_whatsapp() -> Path:
    return dados_locais.raiz() / "whatsapp"


# O export do WhatsApp tem dois formatos conhecidos:
#   12/03/2024 14:05 - Ana: mensagem
#   [12/03/2024, 14:05:32] Ana: mensagem
_RE_LINHA_WHATSAPP = re.compile(
    r"^\[?(?P<data>\d{1,2}/\d{1,2}/\d{2,4})[, ]+(?P<hora>\d{1,2}:\d{2}(?::\d{2})?)\]?\s*[-–]?\s*(?P<quem>[^:]{1,60}):\s?(?P<texto>.*)$"
)


def _arquivos_whatsapp(pasta: Path | str | None = None) -> list[Path]:
    alvo = Path(pasta).expanduser() if pasta else pasta_whatsapp()
    if not alvo.exists():
        return []
    if alvo.is_file():
        return [alvo]
    return sorted(item for item in alvo.iterdir() if item.is_file() and item.suffix.lower() in {".txt"})


def ler_conversa(caminho: Path | str, limite: int = 200) -> dict[str, Any]:
    """Lê um `.txt` exportado do WhatsApp: quem falou, quando e o quê."""
    arquivo = Path(caminho).expanduser()
    if not arquivo.is_file():
        raise ConectorError(f"não achei o arquivo {arquivo.name}.")
    texto = arquivo.read_text(encoding="utf-8", errors="replace")
    mensagens: list[dict[str, Any]] = []
    participantes: dict[str, int] = {}
    for linha in texto.splitlines():
        achado = _RE_LINHA_WHATSAPP.match(linha.strip())
        if not achado:
            continue
        quem = achado.group("quem").strip()
        participantes[quem] = participantes.get(quem, 0) + 1
        mensagens.append(
            {
                "data": achado.group("data"),
                "hora": achado.group("hora"),
                "quem": quem,
                "texto": " ".join(achado.group("texto").split())[:500],
            }
        )
    if not mensagens:
        raise ConectorError(
            "o arquivo não parece um export do WhatsApp. Exporte pelo próprio app "
            "(Conversa → ⋮ → Mais → Exportar conversa → sem mídia)."
        )
    return {
        "arquivo": arquivo.name,
        "total": len(mensagens),
        "participantes": participantes,
        "mensagens": mensagens[-max(1, limite):],
    }


def _conversas_exportadas() -> list[Path]:
    return _arquivos_whatsapp()


def estado_whatsapp(pasta: Path | str | None = None) -> dict[str, Any]:
    """Quantas conversas exportadas existem e quais são."""
    arquivos = _arquivos_whatsapp(pasta)
    return {
        "pasta": str(Path(pasta).expanduser() if pasta else pasta_whatsapp()),
        "arquivos": [item.name for item in arquivos],
        "total": len(arquivos),
        "resumo": (
            f"{len(arquivos)} conversa(s) exportada(s) prontas para ler."
            if arquivos
            else "Nenhuma conversa exportada. Abrir conversa funciona; ler o conteúdo exige o .txt."
        ),
    }
