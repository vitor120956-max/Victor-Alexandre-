"""Correio exportado: triar por importância e copiar o seu jeito de escrever.

O pedido que originou esta camada foi direto: *“se eu pedir para ele entrar no meu
Gmail e filtrar por importância — faturas a pagar, intimações, e-mails do governo —
ou ver os padrões do que eu mando e escrever igual”*.

Entrar na conta exige OAuth do Google: é credencial, e o JARVIS é sem chave. Então
esta camada faz o que dá para fazer **sem credencial nenhuma**, com o que você
exporta da sua própria caixa:

- **triagem** — lê `.eml` e `.mbox` (Google Takeout ou “salvar como .eml”), classifica
  cada mensagem por regra determinística (fatura, intimação, governo, segurança,
  pessoal, newsletter), extrai vencimento e ordena por prioridade;
- **padrões** — olha só as mensagens **enviadas** (rótulo `Sent`/`Enviados` ou nome do
  arquivo) e mede o seu jeito: saudação, fecho, assinatura, tamanho médio, uso de lista;
- **rascunho** — escreve um e-mail novo copiando esse jeito, com os pontos que você
  ditar. É texto para você revisar: esta camada **não envia** nada.

O que ela não faz: não conecta no Gmail, não lê a caixa em tempo real, não marca como
lido, não envia. Para isso existe a camada `escritorio.*` (comandos do `gws`), que
também só monta o comando — quem autentica e executa é você.
"""
from __future__ import annotations

import email
import email.policy
import mailbox
import re
from collections import Counter
from datetime import datetime, timezone
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable

from . import dados

MAX_MENSAGENS = 800
MAX_CORPO = 6_000
EXTENSOES = (".eml", ".mbox", ".mbx", ".txt")

CATEGORIAS: dict[str, dict[str, Any]] = {
    "intimacao": {
        "rotulo": "Intimação / processo",
        "prioridade": 100,
        "termos": (
            "intimação", "intimacao", "citação", "citacao", "intimado", "intimada",
            "prazo de", "audiência", "audiencia", "processo nº", "processo n.", "autos",
            "tribunal", "vara ", "juízo", "juizo", "dje", "pje", "mandado", "oficial de justiça",
        ),
    },
    "fatura": {
        "rotulo": "Fatura / boleto",
        "prioridade": 85,
        "termos": (
            "fatura", "boleto", "vencimento", "vence em", "cobrança", "cobranca",
            "débito automático", "debito automatico", "mensalidade", "a pagar", "pagamento",
            "pix", "invoice", "payment due", "recibo", "comprovante",
        ),
    },
    "governo": {
        "rotulo": "Governo",
        "prioridade": 75,
        "termos": (
            "gov.br", "receita federal", "sefaz", "prefeitura", "detran", "inss", "ipva",
            "licenciamento", "imposto de renda", "declaração", "declaracao", "e-cac", "ecac",
            "dnit", "ministério", "ministerio", "secretaria", "caixa econômica", "fgts",
        ),
    },
    "seguranca": {
        "rotulo": "Segurança / acesso",
        "prioridade": 70,
        "termos": (
            "código de verificação", "codigo de verificacao", "código de segurança",
            "senha", "acesso suspeito", "novo login", "2fa", "autenticação", "autenticacao",
            "dispositivo desconhecido", "verifique sua conta",
        ),
    },
    "newsletter": {
        "rotulo": "Newsletter / promoção",
        "prioridade": 5,
        "termos": (
            "descadastrar", "unsubscribe", "newsletter", "promoção", "promocao", "oferta",
            "webinar", "não responda", "nao responda", "black friday", "cupom",
        ),
    },
}
PRIORIDADE_PESSOAL = 45
PRIORIDADE_OUTRO = 20
REMETENTES_AUTOMATICOS = ("noreply", "no-reply", "nao-responda", "naoresponda", "donotreply", "no_reply")

_RE_DATA = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?\b")
_RE_ROTULO_ENVIADO = re.compile(r"\b(sent|enviad[oa]s?|outbox)\b", re.I)


class CorreioError(ValueError):
    """Pasta vazia, arquivo ilegível ou exportação sem o que analisar."""


# ------------------------------------------------------------------ leitura

def pasta_padrao() -> Path:
    return dados.raiz() / "correio"


def _pasta(pasta: Path | str | None) -> Path:
    alvo = Path(pasta).expanduser() if pasta else pasta_padrao()
    if not alvo.exists():
        raise CorreioError(
            f"A pasta “{alvo}” não existe. Exporte seus e-mails (Google Takeout ou “salvar como .eml”) "
            f"e coloque os arquivos em {pasta_padrao()}."
        )
    if alvo.is_file():
        return alvo
    return alvo


def arquivos(pasta: Path | str | None = None) -> list[dict[str, Any]]:
    """O que tem para ler: `.eml`, `.mbox` e `.txt` (um e-mail por arquivo ou caixa inteira)."""
    alvo = _pasta(pasta)
    if alvo.is_file():
        candidatos = [alvo]
    else:
        candidatos = sorted(
            item for item in alvo.iterdir() if item.is_file() and item.suffix.lower() in EXTENSOES
        )
    return [
        {
            "nome": item.name,
            "formato": "mbox" if item.suffix.lower() in {".mbox", ".mbx"} else "eml",
            "bytes": item.stat().st_size,
        }
        for item in candidatos
    ]


def _texto_da_parte(parte: email.message.Message) -> str:
    """Texto da parte, aceitando tanto a API nova (`get_content`) quanto a do mbox."""
    if hasattr(parte, "get_content"):
        try:
            conteudo = parte.get_content()
        except (KeyError, LookupError, ValueError):
            conteudo = None
        if isinstance(conteudo, str):
            return conteudo
    bruto = parte.get_payload(decode=True) or b""
    if isinstance(bruto, str):
        return bruto
    charset = parte.get_content_charset() or "utf-8"
    try:
        return bruto.decode(charset, errors="replace")
    except (LookupError, UnicodeDecodeError):
        return bruto.decode("utf-8", errors="replace")


def _corpo(mensagem: email.message.Message) -> str:
    if mensagem.is_multipart():
        for parte in mensagem.walk():
            anexo = str(parte.get("Content-Disposition", "") or "").lower().startswith("attachment")
            if parte.get_content_type() == "text/plain" and not anexo:
                texto = _texto_da_parte(parte)
                if texto.strip():
                    return texto.strip()[:MAX_CORPO]
        for parte in mensagem.walk():
            if parte.get_content_type() == "text/html":
                texto = re.sub(r"(?s)<[^>]+>", " ", _texto_da_parte(parte))
                if texto.strip():
                    return re.sub(r"\s+", " ", texto).strip()[:MAX_CORPO]
        return ""
    if mensagem.get_content_type() == "text/html":
        return re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", _texto_da_parte(mensagem))).strip()[:MAX_CORPO]
    return _texto_da_parte(mensagem).strip()[:MAX_CORPO]


def _endereco(bruto: str) -> str:
    nome, email_limpo = parseaddr(bruto or "")
    return email_limpo or (bruto or "").strip()


def _data(bruto: str) -> datetime | None:
    try:
        achada = parsedate_to_datetime(bruto)
    except (TypeError, ValueError):
        return None
    if achada is None:
        return None
    return achada if achada.tzinfo else achada.replace(tzinfo=timezone.utc)


def _mensagem(bruto: email.message.Message, arquivo: str) -> dict[str, Any]:
    data = _data(bruto.get("Date", ""))
    rotulos = str(bruto.get("X-Gmail-Labels", "") or "")
    return {
        "de": _endereco(bruto.get("From", "")),
        "de_nome": parseaddr(bruto.get("From", ""))[0] or "",
        "para": _endereco(bruto.get("To", "")),
        "assunto": " ".join(str(bruto.get("Subject", "") or "").split())[:200],
        "data": data.isoformat() if data else "",
        "rotulos": rotulos,
        "corpo": _corpo(bruto),
        "arquivo": arquivo,
    }


def _ler_arquivo(caminho: Path) -> list[dict[str, Any]]:
    if caminho.suffix.lower() in {".mbox", ".mbx"}:
        caixa = mailbox.mbox(str(caminho), create=False)
        mensagens = []
        for bruto in caixa:
            mensagens.append(_mensagem(bruto, caminho.name))
            if len(mensagens) >= MAX_MENSAGENS:
                break
        return mensagens
    bruto = email.message_from_binary_file(caminho.open("rb"), policy=email.policy.default)
    return [_mensagem(bruto, caminho.name)]


def ler(pasta: Path | str | None = None) -> list[dict[str, Any]]:
    """Lê tudo da pasta, tolerando arquivo quebrado (avisa em `erros`, não derruba)."""
    alvo = _pasta(pasta)
    lista = arquivos(alvo)
    if not lista:
        raise CorreioError(
            f"Não achei `.eml` nem `.mbox` em {alvo}. Exporte do Gmail (Takeout) ou salve a mensagem como `.eml`."
        )
    mensagens: list[dict[str, Any]] = []
    erros: list[str] = []
    for item in lista:
        caminho = alvo if alvo.is_file() else alvo / item["nome"]
        try:
            mensagens.extend(_ler_arquivo(caminho))
        except (OSError, ValueError, mailbox.Error) as exc:
            erros.append(f"{item['nome']}: {type(exc).__name__}")
        if len(mensagens) >= MAX_MENSAGENS:
            break
    if not mensagens:
        raise CorreioError("Li os arquivos, mas nenhuma mensagem saiu: " + (", ".join(erros) or "formato não reconhecido") + ".")
    for mensagem in mensagens:
        mensagem["erros"] = list(erros)
    return mensagens


# --------------------------------------------------------------- triagem

def _dias_ate(vencimento: datetime | None, agora: datetime | None = None) -> int | None:
    if vencimento is None:
        return None
    hoje = (agora or datetime.now(timezone.utc)).date()
    return (vencimento.date() - hoje).days


def achar_vencimento(texto: str, agora: datetime | None = None) -> datetime | None:
    """Data que aparece perto de “vencimento”, “vence”, “prazo” ou “até”.

    Sem palavra de prazo por perto, não vira vencimento — nota fiscal com data
    no meio do texto não é boleto.
    """
    baixo = (texto or "").lower()
    marcas = re.finditer(r"(venciment\w*|vence\w*|prazo|at[ée] o dia|pagar at[ée])", baixo)
    achados: list[datetime] = []
    for marca in marcas:
        janela = baixo[marca.start() : marca.start() + 80]
        for numero in _RE_DATA.finditer(janela):
            dia, mes, ano = numero.group(1), numero.group(2), numero.group(3)
            ano_num = int(ano) if ano else (agora or datetime.now(timezone.utc)).year
            if ano and len(ano) == 2:
                ano_num += 2000
            try:
                achados.append(datetime(int(ano_num), int(mes), int(dia), tzinfo=timezone.utc))
            except ValueError:
                continue
    validos = [data for data in achados if _dias_ate(data, agora) is None or _dias_ate(data, agora) >= -1]
    return min(validos, key=lambda item: item.date()) if validos else (achados[0] if achados else None)


def classificar(mensagem: dict[str, Any], agora: datetime | None = None) -> dict[str, Any]:
    """Categoria, prioridade e motivo — só com o que está escrito na mensagem."""
    texto = f"{mensagem.get('assunto', '')}\n{mensagem.get('corpo', '')}".lower()
    achados: list[tuple[str, list[str]]] = []
    for chave, regra in CATEGORIAS.items():
        termos = [termo for termo in regra["termos"] if termo in texto]
        if termos:
            achados.append((chave, termos))

    remetente = str(mensagem.get("de", "")).lower()
    automatico = any(marca in remetente for marca in REMETENTES_AUTOMATICOS)
    if not achados:
        chave = "pessoal" if (remetente and not automatico) else ("newsletter" if automatico else "outro")
        prioridade = PRIORIDADE_PESSOAL if chave == "pessoal" else PRIORIDADE_OUTRO
        categoria = {"pessoal": "Pessoal", "newsletter": "Newsletter / promoção", "outro": "Outro"}[chave]
        motivos: list[str] = [] if chave == "pessoal" else ["remetente automático"]
    else:
        chave, motivos = max(achados, key=lambda par: CATEGORIAS[par[0]]["prioridade"])
        categoria = CATEGORIAS[chave]["rotulo"]
        prioridade = CATEGORIAS[chave]["prioridade"]

    vencimento = achar_vencimento(f"{mensagem.get('assunto', '')}\n{mensagem.get('corpo', '')}", agora)
    dias = _dias_ate(vencimento, agora)
    if dias is not None and -1 <= dias <= 7:
        prioridade = min(100, prioridade + 10)
        motivos = [*motivos, f"vence em {dias} dia(s)" if dias >= 0 else "venceu ontem"]

    return {
        "categoria": chave,
        "rotulo": categoria,
        "prioridade": prioridade,
        "motivos": motivos[:6],
        "vencimento": vencimento.date().isoformat() if vencimento else "",
        "dias_para_vencer": dias,
    }


def triar(
    pasta: Path | str | None = None,
    *,
    limite: int = 25,
    agora: datetime | None = None,
) -> dict[str, Any]:
    """Ordena por importância real: intimação, fatura vencendo, governo, segurança."""
    mensagens = ler(pasta)
    itens = []
    for mensagem in mensagens:
        ficha = classificar(mensagem, agora)
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
    ordenadas = sorted(itens, key=lambda item: (-item["prioridade"], item["vencimento"] or "9999"))
    contagem = Counter(item["rotulo"] for item in itens)
    urgentes = [item for item in ordenadas if item["prioridade"] >= 85]
    return {
        "total": len(itens),
        "por_categoria": dict(contagem),
        "urgentes": len(urgentes),
        "mensagens": ordenadas[: max(1, limite)],
    }


# ---------------------------------------------------------------- padrões

def _enviada(mensagem: dict[str, Any]) -> bool:
    return bool(_RE_ROTULO_ENVIADO.search(mensagem.get("rotulos", ""))) or bool(
        _RE_ROTULO_ENVIADO.search(mensagem.get("arquivo", ""))
    )


SAUDACOES = (
    "prezados", "prezado", "prezada", "olá", "ola", "oi", "bom dia", "boa tarde", "boa noite",
    "caros", "caro", "cara", "excelentíssimo", "excelentissimo",
)
FECHOS = (
    "atenciosamente", "att", "abraços", "abracos", "abs", "obrigado", "obrigada",
    "cordialmente", "à disposição", "a disposição", "grande abraço", "saudações", "saudacoes",
    "atenção", "respeitosamente",
)


def _linhas(texto: str) -> list[str]:
    return [linha.strip() for linha in (texto or "").splitlines() if linha.strip()]


def _saudacao(texto: str) -> str:
    primeira = (_linhas(texto) or [""])[0].lower()
    for candidata in SAUDACOES:
        if primeira.startswith(candidata):
            return candidata
    return ""


def _fecho(texto: str) -> str:
    for linha in reversed(_linhas(texto)[-4:]):
        baixa = linha.lower()
        if baixa in {fecho for fecho in FECHOS} or any(baixa.startswith(fecho) for fecho in FECHOS):
            return baixa.strip(" ,.")
    return ""


def _assinatura(texto: str) -> str:
    linhas = _linhas(texto)
    if not linhas:
        return ""
    ultima = linhas[-1]
    return ultima if len(ultima) <= 40 and not ultima.endswith((".", "?", "!")) else ""


def padroes(pasta: Path | str | None = None) -> dict[str, Any]:
    """O seu jeito de escrever, medido só nas mensagens enviadas."""
    mensagens = ler(pasta)
    enviadas = [mensagem for mensagem in mensagens if _enviada(mensagem)]
    if not enviadas:
        raise CorreioError(
            "Não achei mensagem enviada. No Takeout, exporte o rótulo “Enviados” (ou inclua os rótulos); "
            "no Gmail, salve uma mensagem enviada como `.eml` e ponha em storage/correio."
        )
    tamanhos = sorted(len(mensagem["corpo"].split()) for mensagem in enviadas)
    mediana = tamanhos[len(tamanhos) // 2]
    saudacoes = Counter(_saudacao(mensagem["corpo"]) for mensagem in enviadas if _saudacao(mensagem["corpo"]))
    fechos = Counter(_fecho(mensagem["corpo"]) for mensagem in enviadas if _fecho(mensagem["corpo"]))
    assinaturas = Counter(_assinatura(mensagem["corpo"]) for mensagem in enviadas if _assinatura(mensagem["corpo"]))
    com_lista = sum(1 for mensagem in enviadas if re.search(r"(?m)^\s*[-•*]\s+", mensagem["corpo"]))
    com_pergunta = sum(1 for mensagem in enviadas if "?" in mensagem["corpo"])
    return {
        "total_enviadas": len(enviadas),
        "palavras_media": round(sum(tamanhos) / len(tamanhos), 1),
        "palavras_mediana": mediana,
        "saudacao": saudacoes.most_common(1)[0][0] if saudacoes else "",
        "saudacoes": dict(saudacoes.most_common(5)),
        "fecho": fechos.most_common(1)[0][0] if fechos else "",
        "fechos": dict(fechos.most_common(5)),
        "assinatura": assinaturas.most_common(1)[0][0] if assinaturas else "",
        "com_lista": com_lista,
        "usa_lista": round(100 * com_lista / len(enviadas)),
        "com_pergunta": com_pergunta,
        "assuntos": [mensagem["assunto"] for mensagem in enviadas[:5]],
    }


# --------------------------------------------------------------- rascunho

def rascunho(
    para: str,
    assunto: str,
    pontos: Iterable[str] | str = (),
    *,
    pasta: Path | str | None = None,
    saudacao: str = "",
    fecho: str = "",
    assinatura: str = "",
) -> dict[str, Any]:
    """Escreve o e-mail no seu padrão. Texto para revisar — nada é enviado."""
    destino = (para or "").strip()
    if not destino:
        raise CorreioError("Diga para quem é o e-mail.")
    titulo = " ".join((assunto or "").split())[:120]
    if not titulo:
        raise CorreioError("Diga o assunto do e-mail.")

    lista = pontos.splitlines() if isinstance(pontos, str) else list(pontos or ())
    lista = [re.sub(r"^[\s\-•*0-9.)]+", "", str(item)).strip() for item in lista]
    lista = [item for item in lista if item]

    try:
        estilo = padroes(pasta)
    except CorreioError:
        estilo = {}

    abertura = (saudacao or estilo.get("saudacao") or "olá").strip()
    despedida = (fecho or estilo.get("fecho") or "atenciosamente").strip()
    assina = (assinatura or estilo.get("assinatura") or "").strip()

    linhas = [f"{abertura.capitalize()}," if abertura else "Olá,", ""]
    if len(lista) <= 1:
        linhas.append(f"Escrevo sobre {titulo[0].lower() + titulo[1:] if titulo else 'o assunto'}.")
        if lista:
            linhas.append(lista[0] + ("." if not lista[0].endswith((".", "!", "?")) else ""))
    else:
        linhas.append(f"Sobre {titulo[0].lower() + titulo[1:]}:")
        linhas.append("")
        for item in lista:
            linhas.append(f"- {item}")
    linhas += ["", despedida.capitalize() + ("," if despedida else ""), *([assina] if assina else [])]
    corpo = "\n".join(linhas).strip() + "\n"

    avisos = [
        "Rascunho montado a partir do seu padrão — revise antes de enviar.",
        "Nada foi enviado: esta camada não fala com o Gmail. Para enviar, use o próprio Gmail ou o `gws` (camada escritório).",
    ]
    if not estilo:
        avisos.append("Não havia e-mails enviados para medir o padrão; usei saudação e fecho genéricos.")
    return {
        "para": destino,
        "assunto": titulo,
        "corpo": corpo,
        "palavras": len(corpo.split()),
        "baseado_em": estilo.get("total_enviadas", 0),
        "saudacao": abertura,
        "fecho": despedida,
        "avisos": avisos,
    }
