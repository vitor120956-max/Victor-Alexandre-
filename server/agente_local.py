"""Agente local: acha a skill certa e executa sem provedor de IA.

O caminho é sempre o mesmo, e nenhum passo chama modelo:

1. **procura** o pedido nas 227 skills do registro, por palavra (nome, categoria,
   descrição, campos do formulário);
2. achando, **preenche os parâmetros** a partir da própria frase — número,
   endereço, caminho, enum, texto colado — e **executa**;
3. não achando, tenta uma das **receitas** prontas (contar palavras, somar,
   converter unidades…), **cria a skill local** e executa na mesma hora;
4. não achando nem receita, **procura na web** com a skill `sistema.rede` e
   devolve as fontes e o trecho lido, sem resumo.

O que este módulo **não** faz: escrever código Python novo. Skill criada aqui é
uma receita declarativa de um catálogo fechado, executada por funções puras —
sem `eval`, sem `exec`, sem `subprocess`. Se o pedido não couber nas receitas, o
agente diz isso e devolve o que encontrou na web, em vez de fingir que criou.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Literal

from . import biblioteca
from .pesquisa import responder as pesquisa_responder
from .sistema import SistemaError

# Faixas de confiança da busca lexical. Abaixo do piso, o agente não executa
# nada: prefere dizer que não sabe a rodar a skill errada.
LIMIAR_EXECUTAR = 0.50
LIMIAR_SUGERIR = 0.25
LIMITE_CANDIDATOS = 5
LIMITE_RESPOSTA = 4_000
LIMITE_TRECHO_WEB = 1_200
ARQUIVO_LOCAIS = Path("agente-local") / "skills.json"


class AgenteError(ValueError):
    """Pedido que o agente local não consegue nem começar a tratar."""


# --------------------------------------------------------------- normalização

_PARADAS = {
    "a", "o", "e", "de", "do", "da", "dos", "das", "um", "uma", "uns", "umas",
    "para", "com", "em", "no", "na", "nos", "nas", "que", "se", "por", "como",
    "mais", "menos", "seu", "sua", "seus", "suas", "ao", "aos", "as", "os",
    "voce", "vc", "eu", "me", "minha", "meu", "isso", "este", "esta", "esse",
    "essa", "tem", "ter", "foi", "ser", "sao", "ja", "nao", "sim", "muito",
    "pode", "quero", "queria", "gostaria", "favor", "por", "entao", "aqui",
}


def normalizar(texto: str) -> str:
    """Minúsculas, sem acento e com espaço simples — a forma de comparar."""
    decomposto = unicodedata.normalize("NFKD", texto or "")
    sem_acento = "".join(caractere for caractere in decomposto if not unicodedata.combining(caractere))
    return re.sub(r"\s+", " ", sem_acento.lower()).strip()


def palavras(texto: str) -> list[str]:
    """Palavras úteis (3+ letras, fora as palavras vazias), sem repetição."""
    vistas: list[str] = []
    for palavra in re.findall(r"[a-z0-9]+", normalizar(texto)):
        if len(palavra) >= 3 and palavra not in _PARADAS and palavra not in vistas:
            vistas.append(palavra)
    return vistas


# Sinônimos que aproximam a fala do usuário do vocabulário das skills. Só entram
# na busca; nunca mudam o que a skill recebe.
_SINONIMOS: dict[str, tuple[str, ...]] = {
    "planilha": ("xlsx", "excel", "tabela"),
    "site": ("web", "http", "url"),
    "link": ("url", "web"),
    "pasta": ("diretorio", "arquivos"),
    "conta": ("somar", "calculadora", "calculo"),
    "soma": ("somar", "calculadora"),
    "senha": ("segredo", "credencial"),
    "emprego": ("carreira", "vaga"),
    "curriculo": ("carreira",),
    "desenho": ("diagrama", "figura"),
    "fluxo": ("diagrama", "processo"),
    "resumo": ("resumir", "resumo"),
    "traduzir": ("traduzir", "texto"),
    "revisar": ("revisao", "revisar"),
    "seguranca": ("risco", "confianca"),
}


def _termos_de_busca(consulta: str) -> list[str]:
    termos = palavras(consulta)
    extras: list[str] = []
    for termo in termos:
        for sinonimo in _SINONIMOS.get(termo, ()):
            if sinonimo not in termos and sinonimo not in extras:
                extras.append(sinonimo)
    return termos + extras


# --------------------------------------------------------------------- índice

@dataclass(frozen=True)
class Entrada:
    """Uma skill pronta para ser comparada com o pedido."""

    skill_id: str
    nome: str
    categoria: str
    descricao: str
    schema: dict[str, Any]
    fortes: frozenset[str]
    fracos: frozenset[str]
    receita: str | None = None
    local: bool = False
    # Skill que baixa, grava ou executa não roda sem o "sim" na conversa.
    confirma: bool = False

    def resumo(self) -> dict[str, Any]:
        return {
            "id": self.skill_id,
            "nome": self.nome,
            "categoria": self.categoria,
            "descricao": self.descricao,
            "local": self.local,
        }


def _campos_do_schema(schema: dict[str, Any]) -> set[str]:
    """Palavras que o formulário da skill usa: nomes, títulos e opções."""
    campos: set[str] = set()
    for nome, spec in (schema.get("properties") or {}).items():
        campos.update(palavras(nome.replace("_", " ")))
        if isinstance(spec, dict):
            campos.update(palavras(str(spec.get("title") or "")))
            campos.update(palavras(str(spec.get("description") or "")))
            for opcao in spec.get("enum") or []:
                campos.update(palavras(str(opcao).replace("-", " ").replace("_", " ")))
            for rotulo in spec.get("enumLabels") or []:
                campos.update(palavras(str(rotulo)))
    return campos


def entrada_de_skill(skill: dict[str, Any]) -> Entrada:
    schema = skill.get("inputSchema") or {}
    fortes = set(palavras(str(skill.get("id") or "").replace(".", " ")))
    fortes.update(palavras(str(skill.get("name") or "")))
    fortes.update(palavras(str(skill.get("category") or "")))
    fracos = set(palavras(str(skill.get("description") or "")))
    fracos |= _campos_do_schema(schema)
    return Entrada(
        skill_id=str(skill.get("id") or ""),
        nome=str(skill.get("name") or ""),
        categoria=str(skill.get("category") or ""),
        descricao=str(skill.get("description") or ""),
        schema=schema,
        fortes=frozenset(fortes),
        fracos=frozenset(fracos),
        confirma=bool(skill.get("requiresConfirmation") or skill.get("requires_confirmation")),
    )


def indexar(skills: Iterable[dict[str, Any]]) -> list[Entrada]:
    return [entrada_de_skill(skill) for skill in skills if skill.get("id")]


def _eh_verbo(palavra: str) -> bool:
    return len(palavra) >= 4 and palavra.endswith(("ar", "er", "ir"))


def _casa(termo: str, vocabulario: frozenset[str]) -> bool:
    """Casa palavra igual, plural e conjugação — nada além disso.

    "palavra" casa com "palavras" (uma letra a mais), "analise" casa com
    "analisar" (mesma raiz, uma é verbo), mas "caseiro" **não** casa com
    "caseiras" e "assis" não casa com "assistido".
    """
    if termo in vocabulario:
        return True
    if len(termo) < 4:
        return False
    for item in vocabulario:
        if len(item) < 4:
            continue
        if item.startswith(termo) and len(item) - len(termo) <= 1:
            return True
        if termo.startswith(item) and len(termo) - len(item) <= 1:
            return True
        if len(termo) >= 5 and len(item) >= 5 and _eh_verbo(item) != _eh_verbo(termo):
            corte = min(6, len(termo), len(item))
            if item[:corte] == termo[:corte]:
                return True
    return False


def pontuar(consulta: str, entrada: Entrada) -> tuple[float, list[str], int]:
    """Nota de 0 a 1, as palavras que a justificaram e quantas são fortes.

    Termo forte é o que aparece no id, no nome ou na categoria da skill; termo
    fraco só na descrição ou no formulário. A contagem de fortes é o que separa
    "essa skill é sobre isso" de "essa skill menciona a palavra em algum lugar".
    """
    # Endereço e caminho não são assunto: `virgiliojr94/book-to-skill` não pode
    # diluir a nota de uma skill que é justamente sobre baixar repositório.
    assunto = _RE_ENDERECO.sub(" ", consulta or "")
    termos = _termos_de_busca(assunto)
    if not termos:
        return 0.0, [], 0
    # O denominador conta só as palavras que o usuário escreveu: sinônimo que a
    # gente acrescenta pode ajudar, nunca penalizar.
    base = max(1, len(palavras(assunto)))
    peso = 0.0
    achados: list[str] = []
    fortes = 0
    for termo in termos:
        if _casa(termo, entrada.fortes):
            peso += 3.0
            achados.append(termo)
            fortes += 1
        elif _casa(termo, entrada.fracos):
            peso += 1.0
            achados.append(termo)
    nota = peso / (3.0 * base)
    nome = normalizar(entrada.nome)
    if nome and nome in normalizar(assunto):
        nota = min(1.0, nota + 0.25)
    return round(min(1.0, nota), 3), achados, fortes


def pesquisar(consulta: str, entradas: Iterable[Entrada], limite: int = LIMITE_CANDIDATOS) -> list[dict[str, Any]]:
    """Ranking de skills para o pedido, da mais parecida para a menos."""
    if not (consulta or "").strip():
        return []
    ranking: list[dict[str, Any]] = []
    for entrada in entradas:
        nota, achados, fortes = pontuar(consulta, entrada)
        if nota <= 0:
            continue
        ranking.append({"entrada": entrada, "score": nota, "termos": achados, "fortes": fortes})
    ranking.sort(key=lambda item: (-item["score"], item["entrada"].skill_id))
    return ranking[:limite]


# ------------------------------------------------------- extração de parâmetros

_CAMPOS_TEXTO = {
    "text", "texto", "content", "conteudo", "diff", "transcript", "transcricao",
    "notes", "notas", "code", "codigo", "body", "corpo", "mensagem", "message",
    "material", "prompt", "descricao", "resumo", "transcription", "entrada",
}
_CAMPOS_URL = {"url", "link", "href", "endereco", "address", "site"}
_CAMPOS_CAMINHO = {"path", "caminho", "arquivo", "file", "filename", "pasta", "dir", "diretorio", "caminhoarquivo"}
_CAMPOS_ID = {"planId", "planid", "id", "chamada", "chamadaid", "artifactid", "runid"}

_RE_URL = re.compile(r"https?://[^\s<>\"']+")
_RE_ENDERECO = re.compile(r"https?://\S+|\b[\w.-]*[A-Za-z][\w.-]*(?:/[\w.-]+)+")
# Endereço curto de repositório ("dono/repo") só vale em campo de URL.
_RE_REPO = re.compile(r"\b([A-Za-z0-9][\w.-]{1,60}/[A-Za-z0-9][\w.-]{1,60})\b")
_RE_CAMINHO = re.compile(
    r"(?:[A-Za-z]:\\[^\s\"']+|(?:[\w.\-]+/)+[\w.\-]+\.[A-Za-z0-9]{1,6}|[\w.\-]+\.(?:pdf|docx?|xlsx?|pptx?|txt|md|csv|json|png|jpe?g|svg|py|ts|tsx|js|zip|exe))",
    re.IGNORECASE,
)
_RE_ARTIGO = re.compile(r"artigo\s+([0-9][0-9.\-]*[a-zA-Z]?)", re.IGNORECASE)
_RE_COMANDO = re.compile(r"(?:rodar|rode|executar|execute|run)\s+(.+)$", re.IGNORECASE)
_RE_SLUG = re.compile(r"\b([a-z0-9][\w.-]{1,60}--[\w.-]{1,60})\b")

# Comando com repositório nomeado: o verbo vem antes, o alvo depois ("rodar
# `python -m pacote --help` no repositório dono--repo"). O extrator genérico não
# dá conta porque os dois campos são texto livre.
_RE_REPO_EXEC = re.compile(
    r"(?:rodar|rode|roda|executar|execute)\s+(?P<cmd>.+?)\s+no\s+reposit[oó]rio\s+(?P<repo>[\w.-]+)",
    re.IGNORECASE,
)
_RE_REPO_LER = re.compile(
    r"ler\s+(?:o\s+)?(?:arquivo\s+)?(?P<arq>[\w./-]+\.\w{1,6})\s+d[oa]\s+reposit[oó]rio\s+(?P<repo>[\w.-]+)",
    re.IGNORECASE,
)


_RE_DRIVE_ACAO = re.compile(
    r"\b(?:configur\w*|apont\w*|usar|usa|lev\w+|pass\w+|mand\w+|mov\w+|coloc\w+|"
    r"jog\w+|salv\w+|guard\w+|sincroniz\w+|ativ\w+|volt\w+)\b"
)
_RE_DRIVE_DESFAZER = re.compile(r"\b(?:desfaz\w*|tir\w+|remov\w*)\b|\bvolt\w+\b")
# Pergunta disfarçada de ordem: sem isso, "o drive ta configurado?" copiaria pastas.
_RE_DRIVE_PERGUNTA = re.compile(
    r"^(?:como|qual|quais|quanto|onde|status|ja)\b|\b(?:status|configurado|funcionando)\b"
)
_RE_DRIVE_PARA_DENTRO = re.compile(r"(?:para|pra|pro)\s+(?:o\s+)?(?:google\s+)?drive\b")
# "limita a banda do drive", "deixa o drive lento", "o drive ta comendo a internet"
_RE_DRIVE_BANDA = re.compile(
    r"\b(?:banda|velocidade|internet|upload|download|trafego|mbps|kbps|mb|kb)\b"
)
_RE_DRIVE_BANDA_ACAO = re.compile(
    r"\b(?:limit\w*|reduz\w*|baix\w+|diminu\w*|control\w+|capar|travar)\b"
)
# "deixa o drive em 500": o número depois de "em" já diz que é limite (KB/s).
_RE_DRIVE_BANDA_NUMERO = re.compile(
    r"\b(?:poe|p[oõ]e|deixa|deixe|coloca|limita|limite|reduz\w*|baix\w*|diminu\w*)\b"
    r".*\b(?:em|pra|para|a)\s+\d"
)
_RE_DRIVE_FECHAR = re.compile(
    r"\b(?:fecha|fechar|fech\w+|desliga\w*|para|parar|pausa\w*)\b"
)
_RE_DRIVE_ABRIR = re.compile(
    r"\b(?:abre|abrir|liga|ligar|relig\w+|retoma\w*|volta a sincronizar)\b"
)
# "devolve a banda toda", "sem limite", "tira o limite do drive"
_RE_DRIVE_SEM_LIMITE = re.compile(
    r"\b(?:sem limite|ilimitad\w+|devolv\w+|(?:tira|remove|tirar|remover) o limite)\b"
)


def _schema_da_skill(registry: Any, skill_id: str) -> dict[str, Any]:
    """Formulário publicado pela skill, ou vazio quando o registro não tem."""
    try:
        for item in registry.list():
            if isinstance(item, dict) and item.get("id") == skill_id:
                schema = item.get("inputSchema") or {}
                return schema if isinstance(schema, dict) else {}
    except Exception:  # registro de teste pode não listar
        pass
    return {}


def _banda_do_pedido(texto: str) -> dict[str, int]:
    """Tira do pedido o limite em KB/s. "500" = 500 KB/s; "2 MB" = 2000 KB/s."""
    achados = re.findall(r"(\d+(?:[.,]\d+)?)\s*(mb|mega|kb|kilo)?", texto)
    valores: list[int] = []
    for numero, unidade in achados:
        try:
            valor = float(numero.replace(",", "."))
        except ValueError:
            continue
        if not valor:
            continue
        if unidade in ("mb", "mega"):
            valor *= 1000
        if 1 <= valor <= 100_000_000:
            valores.append(int(valor))
    if len(valores) == 1:
        return {"download_kbps": valores[0]}
    if len(valores) >= 2:
        return {"download_kbps": valores[0], "upload_kbps": valores[1]}
    return {}


# ---------------------------------------------------------------- mesa (mouse)

_RE_CLICAR = re.compile(r"\b(?:clica|clicar|clique)\b", re.I)
_RE_COORD = re.compile(r"\(?\s*(\d{1,4})\s*[,x ]\s*(\d{1,4})\s*\)?")
_RE_MOVER = re.compile(
    r"\b(?:move|mover|leva|levar|arrasta|arrastar)\b.*?(?P<x>\d{1,4})\s*[,x ]\s*(?P<y>\d{1,4})", re.I
)
_RE_DIGITAR = re.compile(
    r"\b(?:digita|digitar|escreve|escrever|digite)\s+(?:(?:o|a)\s+)?(?:(?:texto|mensagem|seguinte)\s*:?\s*)?(?P<texto>.+)$",
    re.I,
)
_RE_TECLAR = re.compile(
    r"\b(?:aperta|apertar|tecla|pressiona|pressionar)\s+(?:a\s+tecla\s+)?(?P<tecla>[\w+ ]{2,20})$", re.I
)
_RE_FOCAR = re.compile(
    r"\b(?:foca|focar|traz|trazer)\b(?:\s+(?:a|o|na|no))?\s+(?:janela\s+)?(?:d[oa]\s+)?(?P<janela>[\w .-]{2,60})$",
    re.I,
)
_RE_MESA_STATUS = re.compile(r"\b(?:onde (?:esta|está|ta) o (?:mouse|cursor)|status da mesa|mesa status)\b", re.I)


def _pedido_direto_de_mesa(termo: str) -> dict[str, Any] | None:
    """Mouse e teclado: regra explícita, com coordenada obrigatória para clicar."""
    texto = (termo or "").strip()
    if _RE_MESA_STATUS.search(texto):
        return {"skill_id": "mesa.status", "nome": "Onde está o mouse", "parametros": {}, "confirma": False}

    achado = _RE_DIGITAR.search(texto)
    if achado and re.search(r"\b(?:e-?mail|correio|mensagem)\b", texto, re.I):
        # “escreve um e-mail para a Ana” é correio, não teclado.
        achado = None
    if achado:
        conteudo = achado.group("texto").strip().strip("\"'")
        if len(conteudo) >= 1:
            return {
                "skill_id": "mesa.digitar",
                "nome": "Digitar",
                "parametros": {"texto": conteudo[:2000]},
                "confirma": True,
            }

    if _RE_CLICAR.search(texto) and not re.search(r"\bdrive\b", texto, re.I):
        parametros: dict[str, Any] = {}
        coordenada = _RE_COORD.search(texto)
        if coordenada:
            parametros["x"] = int(coordenada.group(1))
            parametros["y"] = int(coordenada.group(2))
        botao = re.search(r"\bbot[aã]o\s+(?:d[oa]\s+)?(esquerd\w+|direit\w+|meio)\b", texto, re.I)
        if botao:
            escolhido = botao.group(1).lower()
            parametros["botao"] = "direito" if escolhido.startswith("direit") else (
                "meio" if escolhido == "meio" else "esquerdo"
            )
        elif re.search(r"\b(?:com o |no )?bot[aã]o direito\b|\bdireito\b", texto, re.I):
            parametros["botao"] = "direito"
        if "duplo" in texto.lower():
            parametros["vezes"] = 2
        return {"skill_id": "mesa.clicar", "nome": "Clicar", "parametros": parametros, "confirma": True}

    achado = _RE_MOVER.search(texto)
    if achado:
        return {
            "skill_id": "mesa.mover",
            "nome": "Mover o mouse",
            "parametros": {"x": int(achado.group("x")), "y": int(achado.group("y"))},
            "confirma": True,
        }

    achado = _RE_TECLAR.search(texto)
    if achado:
        tecla = achado.group("tecla").strip().lower()
        # "ctrl v" e "ctrl mais v" viram "ctrl+v"; "page down" vira "page_down".
        tecla = re.sub(r"\s*(?:mais|\+)\s*", "+", tecla)
        tecla = re.sub(r"^(ctrl|alt|shift)\s+", r"\1+", tecla)
        tecla = re.sub(r"\s+", "_", tecla).replace("control", "ctrl")
        if tecla:
            return {"skill_id": "mesa.teclar", "nome": "Apertar tecla", "parametros": {"tecla": tecla}, "confirma": True}

    achado = _RE_FOCAR.search(texto)
    if achado:
        janela = achado.group("janela").strip()
        if janela.lower() not in {"janela", "tela"}:
            return {
                "skill_id": "mesa.focar",
                "nome": "Focar janela",
                "parametros": {"janela": janela},
                "confirma": True,
            }
    return None


AVISO_FECHAR_DRIVE = (
    "Fechar o app para a sincronização, mas também derruba a unidade `G:` — e a "
    "biblioteca do JARVIS mora nela. Enquanto estiver fechado, não acho livro nenhum. "
    "Para só parar de transferir e continuar lendo, use o menu do app "
    "(Pausar sincronização), que mantém a unidade."
)


def _pedido_direto_de_drive(termo: str) -> dict[str, Any] | None:
    """Pedidos de Google Drive: regra explícita, porque "drive" aparece em tudo.

    Só casa quando a frase fala de **drive** (ou de sincronização) e tem verbo
    de configuração ou palavra de diagnóstico. "Como abro o drive" continua indo
    para a busca normal.
    """
    texto = normalizar(termo)
    tem_drive = "drive" in palavras(texto)
    # "pausa a sincronização" sem dizer "drive" também é claro no contexto do JARVIS.
    tem_sync = "sincroniza" in texto
    if not (tem_drive or tem_sync):
        return None

    estado_ = {
        "skill_id": "armazenamento.drive",
        "nome": "Drive como espaço de fora",
        "parametros": {},
        "confirma": False,
    }
    copiar = {
        "skill_id": "armazenamento.drive-copiar",
        "nome": "Configurar o Drive",
        "parametros": {"modo": "usar"},
        "confirma": True,
    }

    # "?" ou palavra de diagnóstico: o usuário quer saber, não quer que mexa.
    if "?" in (termo or "") or _RE_DRIVE_PERGUNTA.search(texto) or "passo a passo" in texto:
        return estado_
    # Sem a palavra "drive", só abrir/fechar a sincronização faz sentido —
    # "sincroniza meus contatos" não pode virar cópia da biblioteca.
    if not tem_drive:
        if _RE_DRIVE_FECHAR.search(texto):
            return {
                "skill_id": "armazenamento.drive-app",
                "nome": "Abrir ou fechar o Drive",
                "parametros": {"acao": "fechar"},
                "confirma": True,
                "aviso": AVISO_FECHAR_DRIVE,
            }
        if _RE_DRIVE_ABRIR.search(texto):
            return {
                "skill_id": "armazenamento.drive-app",
                "nome": "Abrir ou fechar o Drive",
                "parametros": {"acao": "abrir"},
                "confirma": False,
            }
        return None
    # "fecha o drive" / "pausa a sincronização": parar a sincronização de verdade.
    if _RE_DRIVE_FECHAR.search(texto) and not _RE_DRIVE_SEM_LIMITE.search(texto):
        return {
            "skill_id": "armazenamento.drive-app",
            "nome": "Abrir ou fechar o Drive",
            "parametros": {"acao": "fechar"},
            "confirma": True,
            "aviso": AVISO_FECHAR_DRIVE,
        }
    if _RE_DRIVE_ABRIR.search(texto):
        return {
            "skill_id": "armazenamento.drive-app",
            "nome": "Abrir ou fechar o Drive",
            "parametros": {"acao": "abrir"},
            "confirma": False,
        }

    # "limita a banda do drive": só com verbo, senão "o drive ta lento" vira confusão.
    sem_limite = bool(_RE_DRIVE_SEM_LIMITE.search(texto))
    if (
        sem_limite
        or (_RE_DRIVE_BANDA.search(texto) and _RE_DRIVE_BANDA_ACAO.search(texto))
        or _RE_DRIVE_BANDA_NUMERO.search(texto)
    ):
        parametros = {"download_kbps": 0, "upload_kbps": 0} if sem_limite else _banda_do_pedido(texto)
        return {
            "skill_id": "armazenamento.drive-banda",
            "nome": "Limitar a banda do Drive",
            "parametros": parametros,
            "confirma": True,
        }
    # "volta a biblioteca pro drive" é ida; "tira do drive" é volta.
    if _RE_DRIVE_DESFAZER.search(texto) and not _RE_DRIVE_PARA_DENTRO.search(texto):
        return {**copiar, "parametros": {"modo": "desfazer"}}
    if _RE_DRIVE_ACAO.search(texto):
        return copiar
    return None


def _pedido_direto_de_repositorio(termo: str) -> dict[str, Any] | None:
    """Pedidos de repositório que só funcionam com regra, não com nota."""
    achado = _RE_REPO_EXEC.search(termo)
    if achado:
        return {
            "skill_id": "repos.executar",
            "nome": "Executar no repositório",
            "parametros": {"repo": achado.group("repo"), "comando": achado.group("cmd").strip(" `'\"")},
            "confirma": True,
        }
    achado = _RE_REPO_LER.search(termo)
    if achado:
        return {
            "skill_id": "repos.ler",
            "nome": "Ler arquivo do repositório",
            "parametros": {"repo": achado.group("repo"), "caminho": achado.group("arq")},
            "confirma": False,
        }
    return None
_RE_MINUTOS = re.compile(r"(\d+)\s*(?:min|minuto)", re.IGNORECASE)
_RE_NUMEROS = re.compile(r"-?\d+(?:[.,]\d+)?")


def _numeros(texto: str) -> list[float]:
    valores: list[float] = []
    for bruto in _RE_NUMEROS.findall(texto or ""):
        try:
            valores.append(float(bruto.replace(".", "").replace(",", ".")) if bruto.count(",") else float(bruto))
        except ValueError:
            continue
    return valores


def texto_livre(consulta: str) -> str:
    """Tira o comando e devolve só o conteúdo que o usuário colou."""
    texto = (consulta or "").strip().strip('"').strip("'")
    texto = re.sub(r"^(?:ei|oi|ola)[,\s]+", "", texto, flags=re.IGNORECASE)
    texto = re.sub(r"^(?:jarvis[,\s]+)+", "", texto, flags=re.IGNORECASE)
    texto = re.sub(r"^(?:por favor[,\s]+|pode[,\s]+|poderia[,\s]+|quero que (?:voce|vc|tu)[,\s]+)", "", texto, flags=re.IGNORECASE)
    texto = re.sub(
        r"^(?:usar?|use|rode|rodar|executar?|aplique|aplicar)\s+(?:a\s+)?(?:skill|ferramenta)\s+[\w.\-]+[,\s]*(?:com|para|em)?[:\s]*",
        "",
        texto,
        flags=re.IGNORECASE,
    )
    texto = re.sub(
        r"^(?:analisar|analise|analisa|contar|conte|calcular|calcule|transformar|transforme|processar|processe|resumir|resuma|traduzir|traduza)\s+(?:o\s+|a\s+|os\s+|as\s+)?",
        "",
        texto,
        flags=re.IGNORECASE,
    )
    texto = re.sub(r"^(?:o\s+)?(?:texto|conteudo)\s*[:\-]\s*", "", texto, flags=re.IGNORECASE)
    texto = re.sub(r"^(?:de|do|da|que diz|seguinte)\s*[:\-]\s*", "", texto, flags=re.IGNORECASE)
    # "contar as palavras de: <conteúdo>" — o que vale é o que vem depois dos
    # dois-pontos, desde que não seja um endereço (http://).
    corte = texto.find(":")
    if 0 <= corte <= 60 and not texto[corte:].startswith("://"):
        texto = texto[corte + 1:].strip()
    texto = re.sub(r"[,\s]+por favor\.?$", "", texto, flags=re.IGNORECASE)
    return texto.strip(" \"'")


def _lista_do_pedido(consulta: str) -> str | None:
    """Pega os itens depois de "entre" — ou depois dos dois-pontos."""
    texto = (consulta or "").strip()
    achado = re.search(r"\bentre\s+(.+)$", texto, flags=re.IGNORECASE)
    if achado:
        return achado.group(1).strip() or None
    corte = texto.find(":")
    if 0 <= corte <= 60:
        return texto[corte + 1:].strip() or None
    return None


def _booleano(consulta: str) -> bool | None:
    normalizado = normalizar(consulta)
    if re.search(r"\b(sim|verdadeiro|ativa|ative|ligado|ligar)\b", normalizado):
        return True
    if re.search(r"\b(nao|falso|desativa|desative|desligado)\b", normalizado):
        return False
    return None


def _escolher_enum(consulta: str, opcoes: list[Any], rotulos: list[Any] | None = None) -> str | None:
    normalizado = f" {normalizar(consulta)} "
    for opcao in opcoes:
        alvo = normalizar(str(opcao).replace("-", " ").replace("_", " "))
        if f" {alvo} " in normalizado or f" {alvo}s " in normalizado:
            return str(opcao)
    for indice, rotulo in enumerate(rotulos or []):
        alvo = normalizar(str(rotulo))
        if alvo and f" {alvo} " in normalizado:
            return str(opcoes[indice]) if indice < len(opcoes) else None
    return None


def _valor_do_campo(
    nome: str,
    spec: dict[str, Any],
    consulta: str,
    *,
    unico_texto: bool,
) -> Any | None:
    tipo = spec.get("type")
    opcoes = spec.get("enum")
    if opcoes:
        return _escolher_enum(consulta, list(opcoes), list(spec.get("enumLabels") or []))

    if tipo == "boolean":
        return _booleano(consulta)

    chave = nome.replace("_", "").lower()

    if tipo in ("integer", "number"):
        if "minuto" in chave:
            achado = _RE_MINUTOS.search(consulta)
            return int(achado.group(1)) if achado else None
        valores = _numeros(consulta)
        if not valores:
            return None
        minimo, maximo = spec.get("minimum"), spec.get("maximum")
        for valor in valores:
            numero = int(valor) if tipo == "integer" and float(valor).is_integer() else valor
            if minimo is not None and numero < minimo:
                continue
            if maximo is not None and numero > maximo:
                continue
            return numero
        return None

    if tipo == "array":
        itens = [item.strip() for item in re.split(r"[,;]| e ", consulta) if item.strip()]
        return itens or None

    if tipo != "string":
        return None

    if chave in {c.lower() for c in _CAMPOS_URL}:
        achado = _RE_URL.search(consulta)
        if achado:
            return achado.group(0).rstrip(".,)")
        curto = _RE_REPO.search(consulta)
        return curto.group(1) if curto else None
    if chave in {c.lower() for c in _CAMPOS_CAMINHO}:
        achado = _RE_CAMINHO.search(consulta)
        return achado.group(0) if achado else None
    if chave in {"repo", "repositorio", "repository", "slug"}:
        achado = _RE_REPO.search(consulta) or _RE_SLUG.search(normalizar(consulta))
        return achado.group(1) if achado else None
    if chave in {"comando", "command", "argv"}:
        achado = _RE_COMANDO.search(consulta)
        if not achado:
            return None
        valor = re.split(r"\s+no\s+reposit[oó]rio\b", achado.group(1), maxsplit=1, flags=re.IGNORECASE)[0]
        return valor.strip(" .") or None
    if chave in {c.lower() for c in _CAMPOS_ID}:
        achado = re.search(r"\b([a-z]{2,}[_-][a-z0-9_-]{3,})\b", normalizar(consulta))
        return achado.group(1) if achado else None
    if "artigo" in chave or chave.startswith("article"):
        achado = _RE_ARTIGO.search(consulta)
        return achado.group(1) if achado else None
    if chave in {"entries", "participantes", "itens", "nomes", "lista"}:
        return _lista_do_pedido(consulta)

    tem_padrao = "default" in spec
    if unico_texto or chave in _CAMPOS_TEXTO or (spec.get("format") == "textarea" and not tem_padrao):
        texto = texto_livre(consulta)
        return texto or None

    # Campo de texto comum: só aceita o que veio entre aspas, para não repetir a
    # frase inteira em vários campos.
    achado = re.search(r"[\"“']([^\"”']{2,})[\"”']", consulta)
    return achado.group(1).strip() if achado else None


def extrair_parametros(consulta: str, schema: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    propriedades = schema.get("properties") or {}
    textos = [nome for nome, spec in propriedades.items() if isinstance(spec, dict) and spec.get("type") == "string" and not spec.get("enum")]
    unico_texto = len(textos) == 1
    valores: dict[str, Any] = {}
    for nome, spec in propriedades.items():
        if not isinstance(spec, dict):
            continue
        valor = _valor_do_campo(nome, spec, consulta, unico_texto=unico_texto)
        if valor is not None:
            valores[nome] = valor
    obrigatorios = [campo for campo in (schema.get("required") or []) if campo in propriedades]
    faltando = [campo for campo in obrigatorios if campo not in valores]
    return valores, faltando


# "campo=valor" separado por vírgula ou ponto e vírgula. A vírgula só separa
# quando o que vem depois é outro campo — assim "taxa=3,5" continua um número.
_RE_PAR = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$", re.DOTALL)
_RE_SEPARADOR = re.compile(r"[,;]\s*(?=[A-Za-z_][A-Za-z0-9_]*\s*=)")


def _converter_explicito(bruto: str, spec: dict[str, Any]) -> Any:
    texto = bruto.strip().strip('"').strip("'")
    if texto.startswith(("{", "[")):
        try:
            return json.loads(texto)
        except ValueError:
            pass
    tipo = spec.get("type")
    if tipo == "integer":
        try:
            return int(float(texto.replace(",", ".")))
        except ValueError:
            return texto
    if tipo == "number":
        try:
            return float(texto.replace(",", "."))
        except ValueError:
            return texto
    if tipo == "boolean":
        return normalizar(texto) in {"sim", "true", "1", "verdadeiro", "ativo", "ligado"}
    return texto


def parametros_explicitos(consulta: str, schema: dict[str, Any]) -> dict[str, Any]:
    """Lê `campo=valor` do pedido. É a rede de segurança: cobre qualquer skill.

    Com isso o usuário sempre consegue preencher o que o agente não adivinhou,
    sem formulário e sem IA — inclusive campo de tipo composto, escrito em JSON.
    """
    propriedades = schema.get("properties") or {}
    valores: dict[str, Any] = {}
    for parte in _RE_SEPARADOR.split(consulta or ""):
        achado = _RE_PAR.search(parte.strip())
        if not achado:
            continue
        chave, bruto = achado.group(1), achado.group(2).strip()
        if chave not in propriedades:
            continue
        valores[chave] = _converter_explicito(bruto, propriedades[chave] or {})
    return valores


def _titulo_do_campo(nome: str, schema: dict[str, Any]) -> str:
    spec = (schema.get("properties") or {}).get(nome) or {}
    return str(spec.get("title") or nome)


# ------------------------------------------------------------------- receitas

TipoReceita = Literal["texto", "numeros"]


@dataclass(frozen=True)
class Receita:
    """Uma operação pronta que pode virar skill local, sem escrever código."""

    id: str
    nome: str
    descricao: str
    fortes: tuple[str, ...]
    campo: str
    exemplo: str
    tipo: TipoReceita = "texto"
    minimo: int = 2

    def publica(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "nome": self.nome,
            "descricao": self.descricao,
            "exemplo": self.exemplo,
            "campo": self.campo,
        }


RECEITAS: tuple[Receita, ...] = (
    Receita("contar-palavras", "Contar palavras", "Conta as palavras de um texto colado.", ("contar", "conte", "palavras", "palavra", "quantas"), "texto", "contar as palavras de: <texto>"),
    Receita("contar-caracteres", "Contar caracteres", "Conta letras, com e sem espaço, e o tamanho do texto.", ("caracteres", "caractere", "letras", "letra", "contar"), "texto", "contar os caracteres de: <texto>", minimo=1),
    Receita("contar-linhas", "Contar linhas", "Conta quantas linhas têm conteúdo num bloco de texto.", ("linhas", "linha", "contar"), "texto", "contar as linhas de: <texto>"),
    Receita("extrair-links", "Extrair links", "Lista os endereços http que aparecem no texto.", ("links", "link", "urls", "extrair", "enderecos"), "texto", "extrair os links de: <texto>"),
    Receita("extrair-emails", "Extrair e-mails", "Lista os e-mails que aparecem no texto.", ("emails", "email", "extrair", "contatos"), "texto", "extrair os emails de: <texto>"),
    Receita("extrair-numeros", "Extrair números", "Lista os números encontrados no texto.", ("numeros", "numero", "extrair", "valores"), "texto", "extrair os números de: <texto>"),
    Receita("somar", "Somar números", "Soma todos os números que aparecem no pedido.", ("somar", "soma", "somatorio", "total"), "numeros", "somar 12 30 8", tipo="numeros", minimo=1),
    Receita("media", "Calcular média", "Calcula a média dos números informados.", ("media", "medias", "calcular"), "numeros", "média de 10 20 30", tipo="numeros", minimo=1),
    Receita("maior-menor", "Maior e menor", "Diz o maior e o menor número da lista.", ("maior", "menor", "maximo", "minimo"), "numeros", "maior e menor de 4 9 2", tipo="numeros", minimo=2),
    Receita("porcentagem", "Calcular porcentagem", "Calcula quanto é uma porcentagem de um valor.", ("porcentagem", "porcento", "%"), "texto", "quanto é 20% de 350", minimo=1),
    Receita("ordenar", "Ordenar lista", "Coloca os itens em ordem alfabética.", ("ordenar", "ordene", "ordem", "alfabetica", "classificar"), "texto", "ordenar: Ana, Bruno, Carla", minimo=1),
    Receita("unicos", "Remover repetidos", "Remove itens repetidos mantendo a ordem.", ("unicos", "unicas", "repetidos", "duplicados", "remover"), "texto", "remover repetidos de: Ana, Ana, Bruno"),
    Receita("frequencia", "Contar repetições", "Mostra quantas vezes cada item aparece.", ("frequencia", "repetem", "repetido", "repeticoes", "repeticao", "vezes", "contar"), "texto", "contar repetições em: Ana, Bruno, Ana"),
    Receita("maiusculas", "Deixar em maiúsculas", "Converte o texto para maiúsculas.", ("maiusculas", "maiusculo", "gritar", "caixa-alta"), "texto", "deixar em maiúsculas: <texto>", minimo=1),
    Receita("minusculas", "Deixar em minúsculas", "Converte o texto para minúsculas.", ("minusculas", "minusculo", "caixa-baixa"), "texto", "deixar em minúsculas: <texto>", minimo=1),
    Receita("slug", "Criar slug", "Transforma o texto em endereço amigável, com hífens.", ("slug", "amigavel", "endereco"), "texto", "criar slug de: <texto>", minimo=1),
    Receita("inverter", "Inverter texto", "Escreve o texto de trás para frente.", ("inverter", "invertida", "tras", "reverter"), "texto", "inverter o texto: <texto>", minimo=1),
    Receita("converter-unidades", "Converter unidades", "Converte km/milhas, kg/libras, litros/galões, °C/°F, metros/pés.", ("converter", "conversao", "unidades", "km", "milhas", "kg", "libras", "celsius", "fahrenheit", "litros", "galoes"), "texto", "converter 10 km em milhas"),
    Receita("diferenca-datas", "Diferença entre datas", "Conta os dias entre duas datas.", ("dias", "datas", "entre", "diferenca", "idade"), "texto", "quantos dias entre 01/01/2026 e 25/10/2026"),
    Receita("hash-sha256", "Hash SHA-256", "Calcula o SHA-256 de um texto.", ("hash", "sha256", "resumo", "criptografico"), "texto", "hash sha256 de: <texto>", minimo=1),
    Receita("validar-cpf", "Validar CPF", "Confere os dois dígitos verificadores do CPF, sem consultar nenhum sistema.", ("cpf", "validar", "valide", "digito", "verificador"), "texto", "validar cpf 123.456.789-09", minimo=1),
    Receita("imc", "Calcular IMC", "Calcula o índice de massa corporal e diz a faixa.", ("imc", "massa", "corporal", "indice"), "texto", "IMC de 80 kg e 1,75 m", minimo=1),
    Receita("regra-de-tres", "Regra de três", "Resolve proporção direta: se A vale B, quanto vale C.", ("regra", "tres", "proporcao", "proporcional"), "texto", "se 3 custa 15, quanto custa 7", minimo=2),
    Receita("juros-simples", "Juros simples", "Calcula juros simples sobre um capital, com taxa ao mês.", ("juros", "simples", "taxa", "meses", "mes"), "texto", "juros de 1000 a 2% ao mês por 6 meses", minimo=2),
    Receita("extrair-telefones", "Extrair telefones", "Lista os telefones brasileiros que aparecem no texto.", ("telefone", "telefones", "celular", "whatsapp", "fone"), "texto", "extrair os telefones de: <texto>", minimo=1),
    Receita("extrair-datas", "Extrair datas", "Lista as datas dd/mm/aaaa que aparecem no texto.", ("datas", "data", "extrair", "encontradas"), "texto", "extrair as datas de: <texto>", minimo=2),
    Receita("somar-dias", "Somar dias a uma data", "Diz que dia cai X dias depois (ou antes) de uma data.", ("dias", "depois", "antes", "somar", "cai"), "texto", "30 dias depois de 01/01/2026", minimo=2),
)

_RECEITAS_POR_ID = {receita.id: receita for receita in RECEITAS}


# Formas que não aparecem como palavra (o "%" some na tokenização) mas são
# inequívocas: antes de contar gatilhos, olha estes padrões.
_PADROES_DIRETOS: tuple[tuple[str, str], ...] = (
    (r"\d+(?:[.,]\d+)?\s*%\s*(?:de|do|da)\s*\d", "porcentagem"),
    (r"\b\d+\s*(?:km|milhas?|kg|libras?|litros?|galoes?|celsius|fahrenheit)\b.*\b(?:em|para|pra)\b", "converter-unidades"),
    (r"\bse\s+\d+(?:[.,]\d+)?\b.*\bquanto\b", "regra-de-tres"),
)


def achar_receita(pedido: str) -> Receita | None:
    """Escolhe a receita cujas palavras de gatilho mais aparecem no pedido."""
    for padrao, receita_id in _PADROES_DIRETOS:
        if re.search(padrao, pedido or "", flags=re.IGNORECASE):
            return _RECEITAS_POR_ID[receita_id]
    termos = set(palavras(pedido))
    melhor: tuple[int, Receita] | None = None
    for receita in RECEITAS:
        acertos = sum(1 for gatilho in receita.fortes if normalizar(gatilho) in termos)
        if acertos < max(1, receita.minimo):
            continue
        # Receita que precisa de duas palavras perde para a que acerta mais.
        if melhor is None or acertos > melhor[0]:
            melhor = (acertos, receita)
    return melhor[1] if melhor else None


def _itens(texto: str) -> list[str]:
    itens: list[str] = []
    for linha in texto.splitlines():
        for parte in re.split(r"[,;]", linha):
            limpo = parte.strip().strip('"').strip("'")
            if limpo:
                itens.append(limpo)
    return itens


def _formatar_numero(valor: float) -> str:
    if float(valor).is_integer():
        return str(int(valor))
    return f"{valor:.4f}".rstrip("0").rstrip(".").replace(".", ",")


def _contar_palavras(texto: str) -> dict[str, Any]:
    achados = re.findall(r"[^\W\d_]+(?:['’-][^\W\d_]+)*|\d+(?:[.,]\d+)?", texto, re.UNICODE)
    return {"resultado": f"{len(achados)} palavras.", "palavras": len(achados)}


def _contar_caracteres(texto: str) -> dict[str, Any]:
    sem_espaco = len(re.sub(r"\s", "", texto))
    return {"resultado": f"{len(texto)} caracteres no total, {sem_espaco} sem contar espaços.", "caracteres": len(texto), "semEspacos": sem_espaco}


def _contar_linhas(texto: str) -> dict[str, Any]:
    linhas = [linha for linha in texto.splitlines() if linha.strip()]
    return {"resultado": f"{len(linhas)} linhas com conteúdo.", "linhas": len(linhas)}


def _extrair_links(texto: str) -> dict[str, Any]:
    links = sorted(set(_RE_URL.findall(texto)))
    if not links:
        return {"resultado": "Nenhum link encontrado no texto.", "links": []}
    return {"resultado": "Links encontrados:\n" + "\n".join(f"- {link}" for link in links), "links": links}


def _extrair_emails(texto: str) -> dict[str, Any]:
    emails = sorted(set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", texto)))
    if not emails:
        return {"resultado": "Nenhum e-mail encontrado no texto.", "emails": []}
    return {"resultado": "E-mails encontrados:\n" + "\n".join(f"- {email}" for email in emails), "emails": emails}


def _extrair_numeros(texto: str) -> dict[str, Any]:
    valores = _numeros(texto)
    if not valores:
        return {"resultado": "Nenhum número encontrado no texto.", "numeros": []}
    return {"resultado": "Números: " + ", ".join(_formatar_numero(valor) for valor in valores), "numeros": valores}


def _somar(texto: str) -> dict[str, Any]:
    valores = _numeros(texto)
    if not valores:
        return {"resultado": "Não achei número nenhum para somar.", "numeros": [], "total": 0}
    total = sum(valores)
    return {"resultado": f"{' + '.join(_formatar_numero(v) for v in valores)} = {_formatar_numero(total)}", "numeros": valores, "total": total}


def _media(texto: str) -> dict[str, Any]:
    valores = _numeros(texto)
    if not valores:
        return {"resultado": "Não achei número nenhum para calcular a média.", "numeros": []}
    media = sum(valores) / len(valores)
    return {"resultado": f"Média de {len(valores)} números = {_formatar_numero(media)}", "media": media, "numeros": valores}


def _maior_menor(texto: str) -> dict[str, Any]:
    valores = _numeros(texto)
    if not valores:
        return {"resultado": "Não achei número nenhum na lista.", "numeros": []}
    return {
        "resultado": f"Maior: {_formatar_numero(max(valores))} · menor: {_formatar_numero(min(valores))}",
        "maior": max(valores),
        "menor": min(valores),
    }


def _porcentagem(texto: str) -> dict[str, Any]:
    achado = re.search(r"(\d+(?:[.,]\d+)?)\s*%\s*(?:de|do|da)\s*(\d+(?:[.,]\d+)?)", texto)
    if not achado:
        return {"resultado": "Diga assim: quanto é 20% de 350."}
    parte = float(achado.group(1).replace(",", "."))
    total = float(achado.group(2).replace(",", "."))
    return {"resultado": f"{_formatar_numero(parte)}% de {_formatar_numero(total)} = {_formatar_numero(parte * total / 100)}", "valor": parte * total / 100}


def _ordenar(texto: str) -> dict[str, Any]:
    itens = sorted(_itens(texto), key=str.casefold)
    return {"resultado": "\n".join(itens), "itens": itens}


def _unicos(texto: str) -> dict[str, Any]:
    vistos: list[str] = []
    removidos = 0
    for item in _itens(texto):
        if item.casefold() in {visto.casefold() for visto in vistos}:
            removidos += 1
            continue
        vistos.append(item)
    marca = f"{removidos} repetido removido" if removidos == 1 else f"{removidos} repetidos removidos"
    return {"resultado": f"{len(vistos)} itens, {marca}:\n" + "\n".join(vistos), "itens": vistos, "removidos": removidos}


def _frequencia(texto: str) -> dict[str, Any]:
    contagem = Counter(item.casefold() for item in _itens(texto))
    if not contagem:
        return {"resultado": "Nenhum item para contar."}
    linhas = [f"- {item}: {quantas}×" for item, quantas in contagem.most_common(10)]
    return {"resultado": "Repetições:\n" + "\n".join(linhas), "contagem": dict(contagem)}


def _maiusculas(texto: str) -> dict[str, Any]:
    return {"resultado": texto.upper()}


def _minusculas(texto: str) -> dict[str, Any]:
    return {"resultado": texto.lower()}


def _slug(texto: str) -> dict[str, Any]:
    base = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")
    return {"resultado": slug, "slug": slug}


def _inverter(texto: str) -> dict[str, Any]:
    return {"resultado": texto[::-1]}


_UNIDADES: dict[str, tuple[str, float]] = {
    "km": ("comprimento", 1000.0), "quilometro": ("comprimento", 1000.0), "quilometros": ("comprimento", 1000.0),
    "m": ("comprimento", 1.0), "metro": ("comprimento", 1.0), "metros": ("comprimento", 1.0),
    "cm": ("comprimento", 0.01), "centimetro": ("comprimento", 0.01), "centimetros": ("comprimento", 0.01),
    "milha": ("comprimento", 1609.344), "milhas": ("comprimento", 1609.344),
    "pe": ("comprimento", 0.3048), "pes": ("comprimento", 0.3048),
    "polegada": ("comprimento", 0.0254), "polegadas": ("comprimento", 0.0254),
    "kg": ("massa", 1.0), "quilo": ("massa", 1.0), "quilos": ("massa", 1.0), "quilograma": ("massa", 1.0), "quilogramas": ("massa", 1.0),
    "g": ("massa", 0.001), "grama": ("massa", 0.001), "gramas": ("massa", 0.001),
    "libra": ("massa", 0.45359237), "libras": ("massa", 0.45359237),
    "l": ("volume", 1.0), "litro": ("volume", 1.0), "litros": ("volume", 1.0),
    "ml": ("volume", 0.001), "mililitro": ("volume", 0.001), "mililitros": ("volume", 0.001),
    "galao": ("volume", 3.785411784), "galoes": ("volume", 3.785411784),
}


def _converter_unidades(texto: str) -> dict[str, Any]:
    achado = re.search(r"(-?\d+(?:[.,]\d+)?)\s*([a-zA-Zçãéê]+)\s*(?:em|para|pra)\s*([a-zA-Zçãéê]+)", texto)
    if not achado:
        return {"resultado": "Diga assim: converter 10 km em milhas."}
    valor = float(achado.group(1).replace(",", "."))
    origem = normalizar(achado.group(2))
    destino = normalizar(achado.group(3))

    if origem in {"c", "celsius", "graus"} and destino in {"f", "fahrenheit"}:
        return {"resultado": f"{_formatar_numero(valor)} °C = {_formatar_numero(valor * 9 / 5 + 32)} °F", "valor": valor * 9 / 5 + 32}
    if origem in {"f", "fahrenheit"} and destino in {"c", "celsius", "graus"}:
        return {"resultado": f"{_formatar_numero(valor)} °F = {_formatar_numero((valor - 32) * 5 / 9)} °C", "valor": (valor - 32) * 5 / 9}

    if origem not in _UNIDADES or destino not in _UNIDADES:
        return {"resultado": "Não conheço essa unidade. Tento km, m, cm, milhas, pés, polegadas, kg, g, libras, litros, ml, galões, °C e °F."}
    grandeza_origem, fator_origem = _UNIDADES[origem]
    grandeza_destino, fator_destino = _UNIDADES[destino]
    if grandeza_origem != grandeza_destino:
        return {"resultado": "Essas duas unidades medem coisas diferentes; não dá para converter."}
    convertido = valor * fator_origem / fator_destino
    return {"resultado": f"{_formatar_numero(valor)} {origem} = {_formatar_numero(convertido)} {destino}", "valor": convertido}


def _diferenca_datas(texto: str) -> dict[str, Any]:
    padroes = [r"(\d{1,2})/(\d{1,2})/(\d{4})", r"(\d{4})-(\d{2})-(\d{2})"]
    datas: list[date] = []
    for padrao in padroes:
        for achado in re.finditer(padrao, texto):
            grupos = achado.groups()
            try:
                if len(grupos[0]) == 4:
                    datas.append(date(int(grupos[0]), int(grupos[1]), int(grupos[2])))
                else:
                    datas.append(date(int(grupos[2]), int(grupos[1]), int(grupos[0])))
            except ValueError:
                continue
    if len(datas) < 2:
        return {"resultado": "Preciso de duas datas, por exemplo: quantos dias entre 01/01/2026 e 25/10/2026."}
    dias = abs((datas[1] - datas[0]).days)
    return {"resultado": f"{dias} dias entre {datas[0].strftime('%d/%m/%Y')} e {datas[1].strftime('%d/%m/%Y')}.", "dias": dias}


def _hash_sha256(texto: str) -> dict[str, Any]:
    import hashlib

    resumo = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    return {"resultado": resumo, "sha256": resumo}


def _br(valor: float, casas: int = 2) -> str:
    """Número no jeito brasileiro: vírgula decimal, ponto de milhar."""
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def _validar_cpf(texto: str) -> dict[str, Any]:
    """Confere os dois dígitos verificadores do CPF — sem consultar nada."""
    digitos = re.sub(r"\D", "", texto)
    if len(digitos) != 11:
        return {"resultado": "Diga o CPF com 11 dígitos, como 123.456.789-09.", "valido": False}
    if len(set(digitos)) == 1:
        return {"resultado": f"CPF {digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]} inválido: todos os dígitos são iguais.", "valido": False}

    def digito(parcial: str) -> int:
        peso = len(parcial) + 1
        soma = sum(int(numero) * (peso - indice) for indice, numero in enumerate(parcial))
        resto = (soma * 10) % 11
        return 0 if resto == 10 else resto

    calculado = f"{digito(digitos[:9])}{digito(digitos[:10])}"
    valido = digitos[-2:] == calculado
    bonito = f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"
    if valido:
        return {"resultado": f"CPF {bonito} é válido (dígitos verificadores {calculado}).", "valido": True}
    return {
        "resultado": f"CPF {bonito} é inválido: o correto seria terminar em {calculado}.",
        "valido": False,
        "esperado": calculado,
    }


def _imc(texto: str) -> dict[str, Any]:
    """Índice de massa corporal a partir de peso (kg) e altura (m)."""
    valores = _numeros(texto)
    altura = next((valor for valor in valores if 0.5 <= valor < 3), None)
    peso = next((valor for valor in valores if valor >= 20), None)
    if altura is None or peso is None:
        return {"resultado": "Diga assim: IMC de 80 kg e 1,75 m."}
    indice = peso / (altura ** 2)
    if indice < 18.5:
        faixa = "abaixo do peso"
    elif indice < 25:
        faixa = "peso normal"
    elif indice < 30:
        faixa = "sobrepeso"
    else:
        faixa = "obesidade"
    return {
        "resultado": f"IMC {_br(indice, 1)} — {faixa} (peso {_br(peso, 1)} kg, altura {_br(altura, 2)} m).",
        "imc": round(indice, 1),
        "faixa": faixa,
    }


def _regra_de_tres(texto: str) -> dict[str, Any]:
    """Se A vale B, quanto vale C — proporção direta."""
    valores = _numeros(texto)
    if len(valores) < 3:
        return {"resultado": "Diga assim: se 3 custa 15, quanto custa 7."}
    a, b, c = valores[:3]
    if a == 0:
        return {"resultado": "O primeiro valor não pode ser zero."}
    resultado = b * c / a
    return {
        "resultado": f"Se {_br(a, 0)} vale {_br(b, 0)}, então {_br(c, 0)} vale {_br(resultado)}.",
        "resultado_numerico": round(resultado, 4),
    }


def _juros_simples(texto: str) -> dict[str, Any]:
    """Juros simples: capital, taxa ao mês em % e número de meses."""
    valores = _numeros(texto)
    if len(valores) < 3:
        return {"resultado": "Diga assim: juros de 1000 a 2% ao mês por 6 meses."}
    capital, taxa, meses = valores[0], valores[1], valores[2]
    juros = capital * (taxa / 100) * meses
    return {
        "resultado": (
            f"Juros de {_br(juros)} e total de {_br(capital + juros)} "
            f"(capital {_br(capital)}, {_br(taxa, 0)}% ao mês por {_br(meses, 0)} meses)."
        ),
        "juros": round(juros, 2),
        "total": round(capital + juros, 2),
    }


def _extrair_telefones(texto: str) -> dict[str, Any]:
    achados = re.findall(r"(?:\+55\s*)?\(?\d{2}\)?\s*9?\d{4}[-.\s]?\d{4}\b", texto or "")
    telefones: list[str] = []
    for bruto in achados:
        digitos = re.sub(r"\D", "", bruto)
        if 10 <= len(digitos) <= 13:
            limpo = bruto.strip()
            if limpo not in telefones:
                telefones.append(limpo)
    if not telefones:
        return {"resultado": "Não achei telefone no texto.", "telefones": []}
    return {"resultado": "\n".join(telefones), "telefones": telefones}


def _extrair_datas(texto: str) -> dict[str, Any]:
    achados = re.findall(r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b", texto or "")
    datas: list[str] = []
    for bruto in achados:
        if bruto not in datas:
            datas.append(bruto)
    if not datas:
        return {"resultado": "Não achei data no texto.", "datas": []}
    return {"resultado": "\n".join(datas), "datas": datas}


def _somar_dias(texto: str) -> dict[str, Any]:
    """Que dia cai X dias depois (ou antes) de uma data."""
    achado_data = re.search(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b", texto or "")
    achado_dias = re.search(r"(\d+)\s*dias?", texto or "")
    if not achado_data or not achado_dias:
        return {"resultado": "Diga assim: 30 dias depois de 01/01/2026."}
    dia, mes, ano = int(achado_data.group(1)), int(achado_data.group(2)), int(achado_data.group(3))
    if ano < 100:
        ano += 2000
    quantidade = int(achado_dias.group(1))
    antes = bool(re.search(r"\bantes\b", texto or "", flags=re.IGNORECASE))
    try:
        base = date(ano, mes, dia)
    except ValueError:
        return {"resultado": "Essa data não existe no calendário."}
    alvo = base - timedelta(days=quantidade) if antes else base + timedelta(days=quantidade)
    sentido = "antes" if antes else "depois"
    return {
        "resultado": f"{quantidade} dias {sentido} de {base.strftime('%d/%m/%Y')} cai em {alvo.strftime('%d/%m/%Y')}.",
        "data": alvo.isoformat(),
    }


_OPERACOES: dict[str, Callable[[str], dict[str, Any]]] = {
    "contar-palavras": _contar_palavras,
    "contar-caracteres": _contar_caracteres,
    "contar-linhas": _contar_linhas,
    "extrair-links": _extrair_links,
    "extrair-emails": _extrair_emails,
    "extrair-numeros": _extrair_numeros,
    "somar": _somar,
    "media": _media,
    "maior-menor": _maior_menor,
    "porcentagem": _porcentagem,
    "ordenar": _ordenar,
    "unicos": _unicos,
    "frequencia": _frequencia,
    "maiusculas": _maiusculas,
    "minusculas": _minusculas,
    "slug": _slug,
    "inverter": _inverter,
    "converter-unidades": _converter_unidades,
    "diferenca-datas": _diferenca_datas,
    "hash-sha256": _hash_sha256,
    "validar-cpf": _validar_cpf,
    "imc": _imc,
    "regra-de-tres": _regra_de_tres,
    "juros-simples": _juros_simples,
    "extrair-telefones": _extrair_telefones,
    "extrair-datas": _extrair_datas,
    "somar-dias": _somar_dias,
}


def executar_receita(receita: Receita, entrada: str) -> dict[str, Any]:
    operacao = _OPERACOES.get(receita.id)
    if operacao is None:
        raise AgenteError(f"A receita {receita.id} não tem operação registrada.")
    resultado = operacao(entrada)
    resultado.setdefault("resultado", "")
    return resultado


# ------------------------------------------------------------- skills locais

@dataclass(frozen=True)
class SkillLocal:
    """Skill criada pelo agente: uma receita do catálogo, com nome e exemplo."""

    id: str
    nome: str
    descricao: str
    receita: str
    campo: str
    criado_em: str
    passos: tuple[str, ...] = ()
    fonte: str = ""

    def publica(self) -> dict[str, Any]:
        dados = asdict(self)
        dados["passos"] = list(self.passos)
        return dados


def _pasta_locais(raiz: Path) -> Path:
    return Path(raiz) / ARQUIVO_LOCAIS


def carregar_locais(raiz: Path) -> list[SkillLocal]:
    arquivo = _pasta_locais(raiz)
    if not arquivo.exists():
        return []
    try:
        bruto = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    itens = bruto.get("skills") if isinstance(bruto, dict) else bruto
    locais: list[SkillLocal] = []
    for item in itens or []:
        if not isinstance(item, dict) or not item.get("id") or not item.get("receita"):
            continue
        receita = str(item["receita"])
        if receita not in _RECEITAS_POR_ID and receita != "procedimento":
            continue
        locais.append(
            SkillLocal(
                id=str(item["id"]),
                nome=str(item.get("nome") or item["receita"]),
                descricao=str(item.get("descricao") or ""),
                receita=receita,
                campo=str(item.get("campo") or "texto"),
                criado_em=str(item.get("criado_em") or ""),
                passos=tuple(str(passo) for passo in (item.get("passos") or []) if str(passo).strip()),
                fonte=str(item.get("fonte") or ""),
            )
        )
    return locais


def salvar_locais(raiz: Path, locais: list[SkillLocal]) -> None:
    arquivo = _pasta_locais(raiz)
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    conteudo = {"skills": [asdict(local) for local in locais]}
    arquivo.write_text(json.dumps(conteudo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def criar_skill(receita: Receita, raiz: Path) -> tuple[SkillLocal, bool]:
    """Cria (ou reaproveita) a skill local que executa esta receita."""
    locais = carregar_locais(raiz)
    for local in locais:
        if local.receita == receita.id:
            return local, False
    skill = SkillLocal(
        id=f"local.{receita.id}",
        nome=receita.nome,
        descricao=receita.descricao,
        receita=receita.id,
        campo=receita.campo,
        criado_em=datetime.now(timezone.utc).isoformat(),
    )
    salvar_locais(raiz, [*locais, skill])
    return skill, True


def remover_local(skill_id: str, raiz: Path) -> bool:
    locais = carregar_locais(raiz)
    restantes = [local for local in locais if local.id != skill_id]
    if len(restantes) == len(locais):
        return False
    salvar_locais(raiz, restantes)
    return True


def entrada_de_local(local: SkillLocal) -> Entrada:
    receita = _RECEITAS_POR_ID.get(local.receita)
    if local.receita == "procedimento":
        fortes = set(palavras(local.nome)) | set(palavras(local.id.replace(".", " ").replace("-", " ")))
        fracos = set(palavras(local.descricao)) | set(palavras(" ".join(local.passos)))
        return Entrada(
            skill_id=local.id,
            nome=local.nome,
            categoria="Skill local",
            descricao=local.descricao,
            schema={"properties": {}, "required": []},
            fortes=frozenset(fortes),
            fracos=frozenset(fracos),
            local=True,
        )
    fortes = set(palavras(local.nome)) | set(palavras(local.id.replace(".", " ").replace("-", " ")))
    fracos = set(palavras(local.descricao)) | (set(palavras(receita.exemplo)) if receita else set())
    return Entrada(
        skill_id=local.id,
        nome=local.nome,
        categoria="Skill local",
        descricao=local.descricao,
        schema={"properties": {local.campo: {"type": "string", "title": local.campo}}, "required": [local.campo]},
        fortes=frozenset(fortes),
        fracos=frozenset(fracos),
        receita=local.receita,
        local=True,
    )


# --------------------------------------------------------------- formatação

def _tabela(itens: list[Any], limite: int = 12) -> str:
    linhas: list[str] = []
    for item in itens[:limite]:
        if isinstance(item, dict):
            partes = [f"{chave}: {valor}" for chave, valor in list(item.items())[:4] if not isinstance(valor, (dict, list))]
            linhas.append("- " + " · ".join(partes))
        else:
            linhas.append(f"- {item}")
    if len(itens) > limite:
        linhas.append(f"- … e mais {len(itens) - limite}")
    return "\n".join(linhas)


# Rótulos em português para as chaves que mais aparecem nos resultados. Chave
# fora da lista aparece como veio; nada é omitido.
_ROTULOS = {
    "words": "palavras",
    "characters": "caracteres",
    "charactersWithoutSpaces": "caracteres sem espaço",
    "sentences": "frases",
    "estimatedReadingMinutes": "minutos de leitura",
    "count": "total",
    "files": "arquivos",
    "root": "raiz",
    "limit": "limite",
    "path": "caminho",
    "status": "estado",
    "version": "versão",
    "article": "artigo",
    "articleNumber": "número do artigo",
    "documentTitle": "documento",
    "documentShortTitle": "documento",
    "text": "texto",
    "source": "fonte",
    "total": "total",
    "dryRun": "simulação",
}

_TEXTO_LONGO = ("text", "texto", "conteudo", "content", "resposta", "answer", "resultado", "mensagem", "message")


def _rotulo(chave: str) -> str:
    return _ROTULOS.get(chave, chave)


def _valor_legivel(valor: Any) -> str:
    if isinstance(valor, bool):
        return "sim" if valor else "não"
    if isinstance(valor, float):
        return _formatar_numero(valor)
    return str(valor)


_RE_IMPORTAR_HABILIDADE = re.compile(
    r"\b(?:importa|importar|importe|puxa|puxar|puxe|adiciona|adicionar|adicione|traz|trazer|"
    r"aprende|aprender|baixa|baixar)\b.*?\bhabilidades?\b.*?(?P<url>https?://\S+)",
    re.I,
)
_RE_LISTAR_HABILIDADES = re.compile(
    r"\b(?:quais|qual|lista|listar|liste|mostra|mostrar|mostre|minhas)\b.*?\bhabilidades?\b"
    r"|\bhabilidades? (?:importadas?|de fora|que (?:você )?(?:importou|guardou))\b",
    re.I,
)
_RE_APLICAR_HABILIDADE = re.compile(
    r"\b(?:usa|usar|use|aplica|aplicar|aplique|segue|seguir|siga)\b.*?\bhabilidade\s+"
    r"(?P<nome>[\w.-]{2,60}(?:\s[\w.-]{1,40}){0,4}?)(?:\s+para\s+(?P<tarefa>.+))?$",
    re.I,
)


_RE_TRIAGEM_CORREIO = re.compile(
    r"\b(?:triagem|triar|tria|filtra\w*|filtrar|prioriza\w*|separa\w*|quais)\b[^.]*"
    r"\b(?:e-?mails?|correio|caixa de entrada|gmail)\b"
    r"|\b(?:e-?mails?|correio|gmail|caixa de entrada)\b[^.]*\b(?:filtra\w*|triagem|prioriza\w*|importantes?|urgentes?)\b"
    r"|\b(?:e-?mails?|correio)\s+(?:importantes?|urgentes?)\b",
    re.I,
)
_RE_PADROES_CORREIO = re.compile(
    r"\b(?:padr(?:[õo]es|ã?o)|estilo|jeito|como eu escrevo|analisa\w*|analisar)\b[^.]*"
    r"\b(?:e-?mails?|correio|mensagens|gmail|caixa)\b",
    re.I,
)
_RE_ESCREVER_EMAIL = re.compile(
    r"\b(?:rascunh\w+|escrev\w+|escreva|redig\w+|monta\w*|prepara\w*|faz|faça)\b[^.]*?"
    r"\b(?:e-?mail|mensagem|correio)\b(?P<resto>.*)$",
    re.I,
)


def _limpar_destino(bruto: str) -> tuple[str, str, str]:
    """“para a Ana sobre o relatório: ponto 1; ponto 2” → (Ana, relatório, pontos)."""
    resto = (bruto or "").strip(" :,.!")
    pontos = ""
    if ":" in resto:
        resto, pontos = resto.split(":", 1)
        pontos = pontos.strip()
    assunto = ""
    achado = re.search(r"\b(?:sobre|falando de|a respeito de|com (?:o )?assunto|assunto)\s+(.+)$", resto, re.I)
    if achado:
        resto = resto[: achado.start()].strip()
        assunto = achado.group(1).strip(" .,!")
    destino = re.sub(r"^(?:o|a|os|as|sr\.?|sra\.?|dr\.?|dra\.?)\s+", "", resto.strip(), flags=re.I).strip(" .,!")
    assunto = re.sub(r"^(?:o|a|os|as)\s+", "", assunto.strip(), flags=re.I)
    return destino, assunto, pontos


_RE_GMAIL_BUSCA = re.compile(
    r"\b(?:gmail|caixa de entrada|correio)\b[^.]*\b(?:faturas?|boletos?|intima\w*|processos?|cita\w*|governo|receita|"
    r"detran|seguran\w*|senhas?|c[óo]digos?|n[ãa]o lidos?|importantes?)\b"
    r"|\b(?:fatura|boleto|intima\w*|processo|governo|receita|detran|senha)\b[^.]*\b(?:no|do|pelo) gmail\b",
    re.I,
)
_RE_CATALOGO_CARREGAR = re.compile(
    r"\b(?:carrega|carregar|carregue|ler|l[êe]|leia|abre|abrir)\b[^.]*\bcat[áa]logo\b",
    re.I,
)
_RE_CATALOGO_LISTAR = re.compile(
    r"\b(?:lista|listar|liste|quais|mostra|mostrar|mostre|tem no)\b[^.]*\bcat[áa]logo\b"
    r"|\bcat[áa]logo\b[^.]*\b(?:tem|lista|mostra)\b",
    re.I,
)


def _ficha_real(registry: Any, skill_id: str, direto: dict[str, Any]) -> tuple[str, str, str]:
    """Nome, categoria e descrição do registro — o cartão do chat não fica vazio."""
    try:
        definicao = registry.get(skill_id)
    except Exception:  # skill fora do registro: vale o que a regra declarou
        return direto["nome"], direto.get("categoria", "Repositórios"), ""
    return definicao.name, definicao.category, definicao.description


def _pedido_direto_de_catalogo(termo: str) -> dict[str, Any] | None:
    """Catálogo de terceiros: carregar a planilha, filtrar e importar por linha."""
    texto = (termo or "").strip()
    if "http" in texto:
        return None

    if re.search(r"\bgithub\b", texto, re.I) and re.search(
        r"\b(?:t[óo]pico|topic|agent-skills|skills?|habilidades)\b", texto, re.I
    ):
        quantos = re.search(r"\b(\d{1,2})\b", texto)
        tema = re.search(r"\b(?:t[óo]pico|topic)\s+([\w-]{2,40})", texto, re.I)
        return {
            "skill_id": "catalogo.topico",
            "nome": "Catálogo de um tópico do GitHub",
            "parametros": {
                "topico": (tema.group(1) if tema else "agent-skills")[:60],
                "repos": min(15, max(1, int(quantos.group(1)) if quantos else 12)),
            },
            "confirma": True,
        }

    achado_importar = re.search(r"\b(?:importa|importar|importe|traz|trazer|puxa|puxar)\b", texto, re.I)
    filtros = _filtros_do_texto(texto)
    if _RE_CATALOGO_CARREGAR.search(texto) and achado_importar is None:
        return {
            "skill_id": "catalogo.carregar",
            "nome": "Carregar catálogo de skills",
            "parametros": {"caminho": "catalogo-skills.csv"},
            "confirma": True,
        }

    if achado_importar and re.search(r"\bcat[áa]logo\b", texto, re.I):
        quantos = re.search(r"\b(\d{1,2})\b", texto)
        parametros = dict(filtros)
        parametros["quantos"] = min(10, max(1, int(quantos.group(1)) if quantos else 5))
        return {"skill_id": "catalogo.importar", "nome": "Importar do catálogo", "parametros": parametros, "confirma": True}

    if _RE_CATALOGO_LISTAR.search(texto):
        return {"skill_id": "catalogo.listar", "nome": "Listar catálogo", "parametros": filtros, "confirma": False}
    return None


CATEGORIAS_CATALOGO = ("design", "dev", "ai-agent", "office", "knowledge", "content", "life", "business", "it-ops")
FORNECEDORES_CATALOGO = ("anthropics", "vercel-labs", "mattpocock", "prisma", "supabase", "cloudflare", "remotion", "neondatabase", "heygen", "steipete", "open.feishu")


def _filtros_do_texto(texto: str) -> dict[str, Any]:
    """“as de design da vercel” → categoria/vendor; o resto vira texto livre."""
    filtros: dict[str, Any] = {}
    baixo = (texto or "").lower()
    for categoria in CATEGORIAS_CATALOGO:
        if categoria in baixo:
            filtros["categoria"] = categoria
            break
    for fornecedor in FORNECEDORES_CATALOGO:
        # “da vercel” e “do mattpocock” são como se fala; o índice usa o nome completo.
        procurado = fornecedor.split(".")[0].replace("-labs", "")
        if fornecedor in baixo or re.search(rf"\b{re.escape(procurado)}\b", baixo):
            filtros["fornecedor"] = fornecedor
            break
    return filtros


def _pedido_direto_de_correio(termo: str) -> dict[str, Any] | None:
    """E-mail exportado: triagem por importância, padrão de escrita e rascunho."""
    texto = (termo or "").strip()

    achado = _RE_ESCREVER_EMAIL.search(texto)
    if achado and re.search(r"\b(?:para|pra|ao|à)\b", achado.group("resto") or "", re.I):
        resto = achado.group("resto")
        resto = re.sub(r"^\s*(?:para|pra|ao|à)\b", "para", resto, flags=re.I)
        destino, assunto, pontos = _limpar_destino(resto.replace("para", "", 1) if resto.lower().startswith("para") else resto)
        if destino and assunto:
            parametros: dict[str, Any] = {"para": destino[:200], "assunto": assunto[:160]}
            if pontos:
                parametros["pontos"] = pontos[:4000]
            return {"skill_id": "correio.rascunho", "nome": "Rascunhar e-mail no seu estilo", "parametros": parametros, "confirma": False}

    if _RE_GMAIL_BUSCA.search(texto):
        tipo = "importantes"
        baixo = texto.lower()
        if re.search(r"fatura|boleto", baixo):
            tipo = "faturas"
        elif re.search(r"intima|processo|cita", baixo):
            tipo = "intimacoes"
        elif re.search(r"governo|receita|detran", baixo):
            tipo = "governo"
        elif re.search(r"seguran|senha|c[óo]digo", baixo):
            tipo = "seguranca"
        return {"skill_id": "correio.gmail-busca", "nome": "Busca pronta no Gmail", "parametros": {"tipo": tipo}, "confirma": False}

    if _RE_TRIAGEM_CORREIO.search(texto):
        return {"skill_id": "correio.triar", "nome": "Triar e-mail por importância", "parametros": {}, "confirma": False}

    if _RE_PADROES_CORREIO.search(texto):
        return {"skill_id": "correio.padroes", "nome": "Meu jeito de escrever", "parametros": {}, "confirma": False}
    return None


def _formatar_catalogo(resultado: dict[str, Any]) -> str | None:
    """Texto do chat para o catálogo de terceiros."""
    if (
        resultado.get("por_categoria")
        and resultado.get("total")
        and resultado.get("arquivo")
        and not resultado.get("repos_lidos")
    ):
        linhas = [f"Catálogo carregado: {resultado['total']} habilidade(s).", f"Arquivo: {resultado['arquivo']}", ""]
        if resultado.get("por_categoria"):
            linhas.append("Por categoria: " + ", ".join(f"{k} ({v})" for k, v in resultado["por_categoria"].items()))
        if resultado.get("por_fornecedor"):
            linhas.append("Por fornecedor: " + ", ".join(f"{k} ({v})" for k, v in resultado["por_fornecedor"].items()))
        linhas += ["", "Agora: `importa as 5 primeiras do catálogo` ou `importa as de design do catálogo`."]
        return "\n".join(linhas)

    if "repos_lidos" in resultado and resultado.get("adicionadas"):
        linhas = [
            f"Li {resultado['repos_lidos']} repositório(s) do tópico “{resultado['topico']}” "
            f"({resultado['origem']}):",
            f"{resultado['adicionadas']} skill(s) somada(s) ao catálogo — total agora: {resultado['total']}.",
        ]
        if resultado.get("por_categoria"):
            linhas.append("Por categoria: " + ", ".join(f"{k} ({v})" for k, v in resultado["por_categoria"].items()))
        if resultado.get("sem_skill"):
            linhas.append(f"Sem `SKILL.md` (é lista/plugin, não skill): {', '.join(resultado['sem_skill'][:5])}.")
        if resultado.get("falhas"):
            linhas.append(f"Falharam {len(resultado['falhas'])} repositório(s): {resultado['falhas'][0]['erro'][:120]}")
        if resultado.get("aviso"):
            linhas.append("")
            linhas.append(resultado["aviso"])
        linhas += ["", "Agora: `importa as 5 primeiras do catálogo` (até 10 por chamada)."]
        return "\n".join(linhas)

    if "mostrando" in resultado and isinstance(resultado.get("itens"), list):
        itens = resultado["itens"]
        if not itens:
            return "Nenhuma linha do catálogo bate com esse filtro."
        linhas = [f"{resultado['total']} linha(s) no filtro — mostrando {len(itens)}:", ""]
        for item in itens:
            linhas.append(f"[{item.get('rank')}] {item['skill']} — {item.get('vendor') or '?'} · {item.get('category') or 'sem categoria'}")
            if item.get("repo_url"):
                linhas.append(f"    {item['repo_url']}")
        linhas += ["", "Importe com: `importa as 5 primeiras do catálogo`."]
        return "\n".join(linhas)

    if "limite_por_chamada" in resultado and "importadas" in resultado:
        linhas = [f"Importei {len(resultado['importadas'])} de {resultado.get('tentadas')} linha(s) do catálogo."]
        for item in resultado["importadas"][:10]:
            linhas.append(f"• [{item.get('rank')}] {item.get('nome')} (`{item.get('slug')}`)")
        if resultado.get("falhas"):
            linhas.append("")
            linhas.append("Não deu para importar:")
            for falha in resultado["falhas"][:5]:
                if falha.get("install"):
                    linhas.append(f"• {falha['skill']} — {falha['erro']}; só pela plataforma: `{falha['install']}`")
                else:
                    linhas.append(f"• {falha['skill']} — {falha['erro']}")
        if resultado.get("restantes"):
            linhas.append("")
            linhas.append(
                f"Ainda há {resultado['restantes']} linha(s) no filtro (as sem `repo_url` voltam sempre como falha). "
                f"Mande outra leva de até {resultado['limite_por_chamada']}."
            )
        return "\n".join(linhas)

    if resultado.get("consulta") and resultado.get("url") and resultado.get("dica"):
        linhas = [
            f"Busca pronta no Gmail — {resultado.get('rotulo')}:",
            "",
            resultado["url"],
            "",
            f"Filtro: {resultado['consulta']}",
            str(resultado["dica"]),
        ]
        return "\n".join(linhas)
    return None


def _formatar_correio(resultado: dict[str, Any]) -> str | None:
    """Texto do chat para a camada de correio."""
    if "mensagens" in resultado and "por_categoria" in resultado:
        total = int(resultado.get("total") or 0)
        urgentes = int(resultado.get("urgentes") or 0)
        linhas = [f"Triagem de {total} mensagem(ns): {urgentes} urgente(s).", ""]
        for item in resultado.get("mensagens") or []:
            vence = f" — vence {item['vencimento']}" if item.get("vencimento") else ""
            dias = item.get("dias_para_vencer")
            if isinstance(dias, int) and dias >= 0:
                vence += f" (em {dias} dia(s))"
            linhas.append(f"[{item.get('prioridade')}] {item.get('rotulo')} — {item.get('assunto') or '(sem assunto)'}")
            linhas.append(f"    de {item.get('de') or '?'}{vence}")
        if resultado.get("por_categoria"):
            resumo = ", ".join(f"{chave}: {valor}" for chave, valor in resultado["por_categoria"].items())
            linhas += ["", f"Por categoria — {resumo}."]
        linhas += ["", "Nada foi aberto no Gmail: isto é o que você exportou em storage/correio."]
        return "\n".join(linhas)

    if "total_enviadas" in resultado:
        linhas = [
            f"Seu jeito de escrever (medido em {resultado['total_enviadas']} e-mail(s) enviado(s)):",
            "",
            f"• Saudação mais comum: {resultado.get('saudacao') or 'nenhuma detectada'}",
            f"• Fecho mais comum: {resultado.get('fecho') or 'nenhum detectado'}",
            f"• Assinatura: {resultado.get('assinatura') or 'sem assinatura curta no fim'}",
            f"• Tamanho: média de {resultado.get('palavras_media')} palavras (mediana {resultado.get('palavras_mediana')})",
            f"• Usa lista com marcadores: {resultado.get('usa_lista')}% das mensagens",
        ]
        if resultado.get("assuntos"):
            linhas.append("• Assuntos recentes: " + " · ".join(resultado["assuntos"][:3]))
        linhas += ["", "Para escrever no seu estilo: `escreve um e-mail para fulano sobre o assunto: ponto 1; ponto 2`."]
        return "\n".join(linhas)

    if resultado.get("para") and resultado.get("corpo") and "avisos" in resultado:
        linhas = [f"Para: {resultado['para']}", f"Assunto: {resultado['assunto']}", "", resultado["corpo"].rstrip()]
        if resultado.get("avisos"):
            linhas += ["", "— " + " ".join(resultado["avisos"][:2])]
        return "\n".join(linhas)

    if "arquivos" in resultado and isinstance(resultado.get("arquivos"), list):
        itens = resultado["arquivos"]
        if not itens:
            return f"Nenhum arquivo de correio em {resultado.get('pasta')}. Exporte do Gmail e ponha ali."
        linhas = [f"Correio exportado em {resultado.get('pasta')} ({len(itens)} arquivo(s)):"]
        linhas += [f"• {item['nome']} — {item['formato']}, {item['bytes']} byte(s)" for item in itens[:30]]
        return "\n".join(linhas)
    return None


_RE_ADAPTAR_HABILIDADE = re.compile(
    r"\b(?:adapta|adaptar|adapte|transforma|transformar|transforme|converte|converter|converta)\b"
    r"[^.]*\bhabilidades?\b\s*(?:de fora\s+)?(?P<nome>[\w.-]{2,60}(?:\s[\w.-]{1,40}){0,3})",
    re.I,
)
_RE_FONTES_DE_LIVROS = re.compile(
    r"\b(?:onde|quais|que)\b[^.]*\b(?:livros?|fontes?|sites?)\b[^.]*"
    r"\b(?:gr[áa]tis|gratuit[oa]s?|livres?|dom[íi]nio p[úu]blico|de gra[çc]a|completos?)\b"
    r"|\bfontes de livros\b|\blivros? (?:de gra[çc]a|gratuitos?|livres?|completos?)\b",
    re.I,
)
_RE_PERSONA = re.compile(
    r"\bpersona\b[^.]*?\b(?:d[oa]s?|de|sobre)\s+(?P<livro>[\wÀ-ÿ'’ .-]{3,80})",
    re.I,
)
_RE_BUSCAR_LIVRO = re.compile(
    r"\b(?:procura|procurar|procure|ache|achar|busca|buscar|busque|tem|existe)\b[^.]*\blivro\b\s+"
    r"(?P<consulta>[\wÀ-ÿ'’ .:-]{2,90})",
    re.I,
)
_RE_BAIXAR_LIVRO = re.compile(
    r"\b(?:baixa|baixar|baixe|puxa|puxar|puxe|importa|importar|importe|traz|trazer)\b[^.]*\blivro\b\s+"
    r"(?P<livro>[\wÀ-ÿ'’ .:/-]{2,300})",
    re.I,
)


def _pedido_direto_de_cultura(termo: str) -> dict[str, Any] | None:
    """Livros livres: fontes, busca, download e persona de escrita."""
    texto = (termo or "").strip()

    achado = _RE_ADAPTAR_HABILIDADE.search(texto)
    if achado:
        nome = re.split(r"\s+para\b", achado.group("nome"), maxsplit=1)[0].strip(" .")
        if nome and nome.lower() not in {"de fora", "importada", "essa", "a minha"}:
            return {
                "skill_id": "habilidades.adaptar",
                "nome": "Adaptar habilidade para uso próprio",
                "parametros": {"habilidade": nome[:80]},
                "confirma": True,
            }

    achado = _RE_PERSONA.search(texto)
    if achado:
        livro = re.split(r"\s+para\b", achado.group("livro"), maxsplit=1)[0].strip(" .")
        livro = re.sub(r"^(?:[oa]s?\s+)?livros?\s+", "", livro, flags=re.I).strip(" .")
        if len(livro) >= 3:
            return {
                "skill_id": "cultura.persona",
                "nome": "Persona de escrita a partir de um livro",
                "parametros": {"livro": livro[:80]},
                "confirma": True,
            }

    if _RE_FONTES_DE_LIVROS.search(texto):
        return {"skill_id": "cultura.fontes", "nome": "Fontes de livros livres", "parametros": {}, "confirma": False}

    achado = _RE_BAIXAR_LIVRO.search(texto)
    if achado:
        livro = achado.group("livro").strip(" .")
        if re.search(r"\d", livro) or "gutenberg" in livro.lower():
            return {
                "skill_id": "cultura.baixar",
                "nome": "Baixar livro do Gutenberg",
                "parametros": {"livro": livro[:300]},
                "confirma": True,
            }
        # Sem número não dá para baixar: procura primeiro e devolve as opções.
        return {
            "skill_id": "cultura.buscar",
            "nome": "Buscar livro livre",
            "parametros": {"consulta": livro[:160]},
            "confirma": False,
        }

    achado = _RE_BUSCAR_LIVRO.search(texto)
    if achado:
        consulta = re.split(r"\s+(?:no|na|em|pelo|pela)\b", achado.group("consulta"), maxsplit=1)[0].strip(" .")
        if len(consulta) >= 2:
            return {
                "skill_id": "cultura.buscar",
                "nome": "Buscar livro livre",
                "parametros": {"consulta": consulta[:160]},
                "confirma": False,
            }
    return None


def _pedido_direto_de_habilidade(termo: str) -> dict[str, Any] | None:
    """Habilidades de fora: importar de um link, listar e usar como roteiro."""
    texto = (termo or "").strip()

    links = re.findall(r"https?://[^\s,;]+", texto)
    if len(links) >= 2 and re.search(r"\bhabilidades?\b", texto, re.I):
        limpos = [link.rstrip(").,;]}") for link in links]
        return {
            "skill_id": "habilidades.importar-varias",
            "nome": "Importar várias habilidades",
            "parametros": {"links": "\n".join(limpos[:20]), "limite": min(20, len(limpos))},
            "confirma": True,
        }

    achado = _RE_IMPORTAR_HABILIDADE.search(texto)
    if achado:
        url = achado.group("url").rstrip(").,;")
        if url.startswith("http"):
            return {
                "skill_id": "habilidades.importar",
                "nome": "Importar habilidade de fora",
                "parametros": {"url": url},
                "confirma": True,
            }

    achado = _RE_APLICAR_HABILIDADE.search(texto)
    if achado:
        nome = achado.group("nome").strip(" .")
        if nome and nome.lower() not in {"de fora", "importada", "nova", "essa"}:
            parametros = {"habilidade": nome[:80]}
            tarefa = (achado.group("tarefa") or "").strip(" ?.!")
            if tarefa:
                parametros["tarefa"] = tarefa[:400]
            return {"skill_id": "habilidades.aplicar", "nome": "Usar habilidade importada", "parametros": parametros, "confirma": False}

    if _RE_LISTAR_HABILIDADES.search(texto) and "http" not in texto:
        return {"skill_id": "habilidades.listar", "nome": "Habilidades importadas", "parametros": {}, "confirma": False}
    return None


def _formatar_cultura(resultado: dict[str, Any]) -> str | None:
    """Texto do chat para fontes de livro, busca, download e persona."""
    if resultado.get("skill_local") and resultado.get("resposta"):
        return str(resultado["resposta"])

    if isinstance(resultado.get("fontes"), list) and resultado.get("total"):
        linhas = ["Onde achar livro completo e de graça (e legal):", ""]
        for fonte in resultado["fontes"]:
            linhas.append(f"• {fonte.get('nome')} — {fonte.get('url')}")
            linhas.append(f"    {fonte.get('o_que_tem')}")
            linhas.append(f"    licença: {fonte.get('licenca')} · precisa: {fonte.get('precisa')}")
        if resultado.get("recomendacao"):
            linhas += ["", str(resultado["recomendacao"])]
        return "\n".join(linhas)

    if isinstance(resultado.get("livros"), list) and "consulta" in resultado:
        livros = resultado["livros"]
        if not livros:
            return f"Nenhum livro livre encontrado para “{resultado['consulta']}” em {resultado['fonte']}."
        linhas = [f"{resultado.get('total')} resultado(s) em {resultado['fonte']} — mostrando {len(livros)}:", ""]
        for livro in livros:
            autores = ", ".join(livro.get("autores") or []) or "autor não informado"
            linhas.append(f"[{livro.get('id')}] {livro.get('titulo')} — {autores}")
            if livro.get("texto"):
                linhas.append(f"    texto: {livro['texto']}")
            elif livro.get("url"):
                linhas.append(f"    {livro['url']}")
        linhas += ["", f"Dica: {resultado.get('dica')}"]
        return "\n".join(linhas)

    if isinstance(resultado.get("regras"), list) and resultado.get("tom"):
        linhas = [
            f"Persona “{resultado.get('nome')}” — estilo medido em {resultado.get('palavras')} palavras:",
            f"Tom: {resultado['tom']}.",
            "",
        ]
        linhas += [f"• {regra}" for regra in resultado["regras"]]
        linhas += ["", "Limites:", *[f"• {limite}" for limite in resultado.get("limites") or []]]
        if resultado.get("arquivo"):
            linhas += ["", f"Guardei em {resultado['arquivo']}."]
        return "\n".join(linhas)

    if resultado.get("resposta") and resultado.get("livro") and resultado.get("slug"):
        return str(resultado["resposta"])
    return None


def _formatar_habilidade(resultado: dict[str, Any]) -> str | None:
    """Texto do chat para as habilidades importadas."""
    if "habilidades" in resultado and isinstance(resultado.get("habilidades"), list):
        itens = resultado["habilidades"]
        if not itens:
            return (
                "Nenhuma habilidade de fora guardada ainda. Mande o link assim: "
                "`importa a habilidade https://github.com/dono/repo/blob/main/SKILL.md`."
            )
        linhas = [f"Habilidades guardadas ({len(itens)}):", ""]
        for item in itens[:30]:
            linhas.append(f"• {item.get('nome')} (`{item.get('slug')}`) — {item.get('descricao') or 'sem descrição'}")
            if item.get("url"):
                linhas.append(f"  {item['url']}")
        linhas.append("")
        linhas.append("Use com: `usa a habilidade <nome> para <seu pedido>`.")
        return "\n".join(linhas)

    if resultado.get("texto") and resultado.get("slug") and resultado.get("lembrete"):
        cabeca = [f"Habilidade “{resultado.get('nome')}” (`{resultado['slug']}`)"]
        if resultado.get("url"):
            cabeca.append(f"Fonte: {resultado['url']}")
        if resultado.get("tarefa"):
            cabeca.append(f"Para: {resultado['tarefa']}")
        if resultado.get("cortado"):
            cabeca.append("(texto cortado no limite — peça com `limite` maior para ver tudo)")
        corpo = [cabeca[0], *cabeca[1:], "", str(resultado["texto"]).strip(), "", str(resultado["lembrete"])]
        return "\n".join(corpo)

    if isinstance(resultado.get("importadas"), list) and "falhas" in resultado:
        linhas = [f"Importei {len(resultado['importadas'])} de {resultado.get('tentadas')} habilidade(s)."]
        for item in resultado["importadas"][:20]:
            linhas.append(f"• {item.get('nome')} (`{item.get('slug')}`) — {item.get('tamanho')} caractere(s)")
        if resultado.get("falhas"):
            linhas.append("")
            linhas.append("Não deu para importar:")
            linhas += [f"• {falha['url']} — {falha['erro']}" for falha in resultado["falhas"][:5]]
        if resultado.get("restantes"):
            linhas.append("")
            linhas.append(f"Sobraram {resultado['restantes']} link(s); mande o resto em outra leva (até 20 por vez).")
        return "\n".join(linhas)

    if resultado.get("slug") and resultado.get("novo") is not None and "tentativas" in resultado:
        estado = "importada" if resultado["novo"] else "atualizada"
        linhas = [
            f"Habilidade {estado}: “{resultado.get('nome')}” (`{resultado['slug']}`).",
            f"Fonte: {resultado.get('url')}",
        ]
        if resultado.get("descricao"):
            linhas.append(f"Resumo: {resultado['descricao']}")
        linhas.append(f"Tamanho: {resultado.get('tamanho')} caractere(s). Ficou guardada em storage/habilidades.json.")
        outros = resultado.get("outros") or []
        if outros:
            linhas.append(
                f"Esse endereço tem mais {len(outros)} habilidade(s). Importei esta; para outra, "
                f"cole o link da pasta — por exemplo {outros[0]}"
            )
        linhas.append("Use com: " f"`usa a habilidade {resultado['slug']} para <seu pedido>`.")
        return "\n".join(linhas)

    if resultado.get("removida") and resultado.get("habilidade"):
        return f"Habilidade “{resultado['habilidade']}” removida do arquivo local."

    return None


def _formatar_mesa(resultado: dict[str, Any]) -> str | None:
    """Texto do chat para mouse, teclado e janelas."""
    acao = str(resultado.get("acao") or "")
    if acao not in {"mover", "clicar", "digitar", "teclar", "focar"} and "janelas" not in resultado:
        return None

    if "janelas" in resultado and acao not in {"mover", "clicar", "digitar", "teclar", "focar"}:
        if not resultado.get("suportado"):
            return str(resultado.get("motivo") or "Mouse e teclado só existem no Windows.")
        linhas = [
            f"Cursor em ({resultado.get('x')}, {resultado.get('y')}) — tela {resultado.get('largura')}x{resultado.get('altura')}.",
            "Janelas abertas:",
        ]
        linhas += [f"  • {titulo}" for titulo in (resultado.get("janelas") or [])[:15]]
        return "\n".join(linhas)

    if acao == "mover":
        if resultado.get("interrompido"):
            return (
                "Parei: você mexeu o mouse no meio do caminho, então não continuei "
                f"(fiquei em {tuple(resultado.get('parou_em') or [])})."
            )
        destino = resultado.get("para") or []
        return f"Cursor em ({destino[0]}, {destino[1]})." if destino else "Cursor movido."

    if acao == "clicar":
        if not resultado.get("clicou"):
            return "Não cliquei: o movimento foi interrompido."
        em = resultado.get("em") or []
        vezes = int(resultado.get("vezes") or 1)
        rotulo = {"esquerdo": "esquerdo", "direito": "direito", "meio": "do meio"}.get(
            str(resultado.get("botao")), str(resultado.get("botao"))
        )
        return f"Clique {rotulo} {'duplo' if vezes == 2 else ''} em ({em[0]}, {em[1]}).".replace("  ", " ")

    if acao == "digitar":
        return f'Digitei {resultado.get("caracteres")} caractere(s): “{resultado.get("amostra")}”.'

    if acao == "teclar":
        return f"Apertei {resultado.get('tecla')}."

    if acao == "focar":
        return f"Trouxe para a frente: {resultado.get('janela')}."

    return None


def _formatar_app_do_drive(resultado: dict[str, Any]) -> str | None:
    """Texto do chat para fechar/abrir o app do Drive."""
    if resultado.get("app") != "drive":
        return None
    acao = str(resultado.get("acao") or "")
    linhas: list[str] = []

    if acao == "estado":
        aberto = resultado.get("aberto")
        if aberto is None:
            return "Não consigo ver os processos nesta máquina."
        linhas.append("O app do Google Drive está aberto." if aberto else "O app do Google Drive está fechado.")
        if resultado.get("executavel"):
            linhas.append(f"Executável: {resultado['executavel']}")
        elif not aberto:
            linhas.append("Não achei o executável para abrir sozinho — abra pelo menu Iniciar.")
        return "\n".join(linhas)

    if resultado.get("ja_estava"):
        linhas.append(str(resultado.get("mensagem") or "Já estava assim."))
    elif acao == "fechar":
        if resultado.get("vai_fechar"):
            linhas.append("Vou fechar o app do Google Drive.")
        else:
            linhas.append(str(resultado.get("mensagem") or "Fechei o app do Google Drive."))
    else:
        linhas.append(str(resultado.get("mensagem") or "Abrindo o app do Google Drive."))

    aviso = resultado.get("aviso")
    if aviso:
        linhas.append(f"⚠ {aviso}")
    if acao == "fechar" and (resultado.get("vai_fechar") or not resultado.get("fechado")):
        linhas.append('Responda "sim, pode" para eu fechar.')
    return "\n".join(linhas)


def _formatar_banda(resultado: dict[str, Any]) -> str | None:
    """Texto do chat para o limite de banda (antes/depois, em linguagem simples)."""
    if not resultado.get("banda"):
        return None
    antes = resultado.get("antes") or {}
    depois = resultado.get("depois") or {}
    suportado = resultado.get("suportado", True)

    def _linha(nome: str, valores: dict[str, Any]) -> str:
        valor = int(valores.get("download_kbps") or 0) if nome == "download" else int(valores.get("upload_kbps") or 0)
        return f"{nome}: {'sem limite' if not valor else _br(valor / 1000, 1) + ' MB/s (' + str(valor) + ' KB/s)'}"

    if resultado.get("planejado"):
        if not suportado:
            return str(resultado.get("motivo") or "Não dá para ajustar a banda nesta máquina.")
        return "\n".join(
            [
                "Vou gravar no registro do Windows:",
                f"  • antes  — {_linha('download', antes)} · {_linha('upload', antes)}",
                f"  • depois — {_linha('download', depois)} · {_linha('upload', depois)}",
                "Responda “sim, pode” para eu aplicar.",
            ]
        )
    if not suportado:
        return str(resultado.get("motivo") or "Não dá para ajustar a banda nesta máquina.")
    linhas = [
        "Limite aplicado:",
        f"  • antes  — {_linha('download', antes)} · {_linha('upload', antes)}",
        f"  • depois — {_linha('download', depois)} · {_linha('upload', depois)}",
    ]
    if resultado.get("mensagem"):
        linhas.append(str(resultado["mensagem"]))
    return "\n".join(linhas)


def _formatar_drive(resultado: dict[str, Any]) -> str | None:
    """Texto do chat para as skills de Drive (estado, planejar, aplicar, desfazer)."""
    if "areas" not in resultado and "vai_acontecer" not in resultado:
        if str(resultado.get("modo") or "") == "desfazer" and "mensagem" in resultado:
            texto = [str(resultado["mensagem"])]
            if resultado.get("aviso"):
                texto.append(str(resultado["aviso"]))
            return "\n".join(texto)
        return None
    if "passos" in resultado and "areas" not in resultado:
        return None

    linhas: list[str] = []
    modo = str(resultado.get("modo") or "")
    if modo == "usar" and "mensagem" in resultado:
        copiados = int(resultado.get("copiados") or 0)
        if copiados:
            linhas.append(
                f"Pronto: {copiados} arquivo(s), {_br(float(resultado.get('mb_copiados') or 0), 1)} MB "
                f"para {resultado.get('destino', '')}."
            )
        else:
            # Pasta vazia não é erro: o JARVIS só ainda não tinha livro nenhum.
            linhas.append(f"Configurado: o JARVIS agora usa {resultado.get('destino', '')}.")
            linhas.append(
                "As pastas estavam vazias, então nada foi copiado — os próximos livros e "
                "repositórios vão direto para o Drive."
            )
        for item in resultado.get("areas") or []:
            if not isinstance(item, dict):
                continue
            linhas.append(
                f"  • {item.get('nome')}: {item.get('situacao', 'ok')}"
                + (f" — {item['conferido']}" if item.get("conferido") else "")
            )
        if resultado.get("env"):
            linhas.append(f".env atualizado: {resultado['env']}")
        if resultado.get("aviso"):
            linhas.append(str(resultado["aviso"]))
        linhas.append("Nada foi apagado do PC.")
        return "\n".join(linhas)

    if modo == "desfazer":
        linhas.append(str(resultado.get("mensagem") or "Desfiz a configuração do Drive."))
        if resultado.get("aviso"):
            linhas.append(str(resultado["aviso"]))
        return "\n".join(linhas)

    if "vai_acontecer" in resultado:
        linhas.append("Para desfazer:")
        linhas.extend(f"  • {item}" for item in resultado["vai_acontecer"])
        if resultado.get("precisa_reiniciar"):
            linhas.append("Reinicie o JARVIS depois.")
        return "\n".join(linhas)

    # estado
    if resultado.get("detectado"):
        linhas.append(f"Drive: {resultado.get('drive', '')}")
        linhas.append(f"Destino: {resultado.get('destino', '')}")
        livre = resultado.get("espaco_livre_gb")
        if isinstance(livre, (int, float)) and livre:
            linhas.append(f"Livre no Drive: {_br(float(livre), 1)} GB")
    else:
        linhas.append("Não achei a pasta do Google Drive nesta máquina.")
    for item in resultado.get("areas") or []:
        if not isinstance(item, dict):
            continue
        if item.get("configurada"):
            situacao = "já está no Drive"
        elif item.get("ja_no_drive"):
            situacao = f"no Drive ({item['ja_no_drive']} arquivos), mas o .env não aponta para lá"
        else:
            situacao = "no PC"
        linhas.append(
            f"  • {item.get('nome')}: {situacao} — {item.get('arquivos', 0)} arquivo(s), "
            f"{_br(float(item.get('mb') or 0), 1)} MB"
        )
    for aviso in resultado.get("avisos") or []:
        linhas.append(f"⚠ {aviso}")
    env = resultado.get("env") or {}
    if isinstance(env, dict):
        aponta = bool(env.get("biblioteca") or env.get("repos"))
        linhas.append(f".env: {'aponta para o Drive' if aponta else 'não aponta para o Drive'}")
    if resultado.get("configurado"):
        if not resultado.get("total_arquivos"):
            linhas.append(
                "Está configurado, mas ainda não há livro nenhum: importe um "
                "(ex.: `importar C:\\Users\\Você\\Downloads\\livro.pdf`) e confira aqui."
            )
        linhas.append('Para voltar ao PC, diga "tira a biblioteca do drive".')
    else:
        linhas.append('Para levar de verdade, diga "configura o Google Drive pra mim".')
    return "\n".join(linhas)


def _formatar_repositorio(resultado: dict[str, Any]) -> str | None:
    """Resumo curto para as skills de repositório; o resto é ruído no chat."""
    if {"slug", "arquivos", "sugestao"} <= set(resultado):
        linhas = [
            f"Baixei “{resultado.get('nome')}” — {resultado['arquivos']} arquivos, "
            f"{round(int(resultado.get('bytes') or 0) / 1e6, 2)} MB, em storage/repos/{resultado['slug']}."
        ]
        linguagens = resultado.get("linguagens") or []
        if linguagens:
            linhas.append(
                "Linguagens: " + ", ".join(f"{item['nome']} ({item['arquivos']})" for item in linguagens[:4])
            )
        entradas = [item["comando"] for item in (resultado.get("entradas") or [])]
        if entradas:
            linhas.append("Entradas prováveis: " + ", ".join(entradas[:4]))
        linhas.append(str(resultado["sugestao"]))
        return "\n\n".join(linhas)[:LIMITE_RESPOSTA]

    if {"comando", "codigo"} <= set(resultado):
        partes = [f"`{resultado['comando']}` terminou com código {resultado['codigo']}."]
        if resultado.get("saida"):
            partes.append(str(resultado["saida"])[:2_000])
        if resultado.get("erro"):
            # Programa que sai com 0 e escreve no stderr (uso do argparse, aviso
            # de licença) não é erro; o rótulo tem que acompanhar o código.
            rotulo = "Erro:" if resultado.get("codigo") else "Avisos do programa:"
            partes.append(rotulo + "\n" + str(resultado["erro"])[:1_000])
        return "\n\n".join(partes)[:LIMITE_RESPOSTA]

    if "repos" in resultado and isinstance(resultado.get("repos"), list):
        repos = resultado["repos"]
        if not repos:
            return "Nenhum repositório baixado ainda."
        linhas = [f"{len(repos)} repositório(s) em storage/repos:"]
        for item in repos[:10]:
            linguagens = ", ".join(item.get("linguagens") or []) or "sem linguagem medida"
            linhas.append(f"- {item.get('slug')} — {item.get('arquivos')} arquivos — {linguagens}")
        return "\n".join(linhas)

    return None


def _formatar_fonte_da_biblioteca(resultado: dict[str, Any]) -> str | None:
    """Resultado de `biblioteca.importar`: uma linha em vez de sete campos."""
    if "slug" not in resultado or "secoes" not in resultado or "achados" in resultado:
        return None
    titulo = str(resultado.get("titulo") or resultado["slug"])
    secoes = int(resultado.get("secoes") or 0)
    detalhe = f"{secoes} " + ("seção" if secoes == 1 else "seções")
    palavras = resultado.get("total_palavras")
    if isinstance(palavras, int):
        detalhe += f", {palavras} palavras"
    idioma = resultado.get("idioma")
    if isinstance(idioma, str) and idioma:
        detalhe += f", idioma {idioma}"
    origem = resultado.get("origem")
    sufixo = f" Origem: {origem}." if isinstance(origem, str) and origem else ""
    return f'Fonte “{titulo}” na biblioteca: {detalhe}. Slug: `{resultado["slug"]}`.{sufixo}'


def formatar_resultado(resultado: Any) -> str:
    """Transforma o retorno de uma skill em texto legível no chat."""
    if not isinstance(resultado, dict):
        return str(resultado)[:LIMITE_RESPOSTA]

    especial = _formatar_catalogo(resultado)
    if especial is not None:
        return especial

    especial = _formatar_cultura(resultado)
    if especial is not None:
        return especial

    especial = _formatar_correio(resultado)
    if especial is not None:
        return especial

    especial = _formatar_habilidade(resultado)
    if especial is not None:
        return especial

    especial = _formatar_mesa(resultado)
    if especial is not None:
        return especial

    especial = _formatar_app_do_drive(resultado)
    if especial is not None:
        return especial

    especial = _formatar_banda(resultado)
    if especial is not None:
        return especial

    especial = _formatar_drive(resultado)
    if especial is not None:
        return especial

    especial = _formatar_repositorio(resultado)
    if especial is not None:
        return especial

    fonte = _formatar_fonte_da_biblioteca(resultado)
    if fonte is not None:
        return fonte

    partes: list[str] = []
    usados: set[str] = set()

    resumo = resultado.get("summary")
    if isinstance(resumo, str) and resumo.strip():
        partes.append(resumo.strip())
        usados.add("summary")

    corpo = ""
    for chave in _TEXTO_LONGO:
        valor = resultado.get(chave)
        if isinstance(valor, str) and len(valor.strip()) >= 40:
            corpo = valor.strip()
            usados.add(chave)
            break
    if corpo:
        partes.append(corpo)

    for chave in ("rows", "items", "resultados", "lista", "registros", "files", "topTerms"):
        itens = resultado.get(chave)
        if isinstance(itens, list) and itens:
            partes.append(_tabela(itens))
            usados.add(chave)
            break

    escalares: list[str] = []
    for chave, valor in resultado.items():
        if chave in usados or not isinstance(valor, (str, int, float, bool)):
            continue
        if isinstance(valor, str) and len(valor) > 160:
            continue
        escalares.append(f"{_rotulo(chave)}: {_valor_legivel(valor)}")
    if escalares:
        partes.append("\n".join(f"- {linha}" for linha in escalares[:10]))

    if not partes:
        partes.append(json.dumps(resultado, ensure_ascii=False, indent=2))
    texto = "\n\n".join(partes)
    return texto[:LIMITE_RESPOSTA] + ("…" if len(texto) > LIMITE_RESPOSTA else "")


# ------------------------------------------------------------------- web

_RE_FONTE_PEDIDO = re.compile(
    r"\b(?:no|na|pelo|pela|do|da|em)\s+"
    r"(youtube|wikipedia|wiki|duckduckgo|ddg|google|web|internet|sites?)\b",
    re.I,
)
_FONTE_APELIDOS = {
    "wiki": "wikipedia",
    "google": "auto",  # sem chave não dá para ler o Google: responde com todas
    "web": "auto",
    "internet": "auto",
    "site": "auto",
    "sites": "auto",
    "ddg": "duckduckgo",
}
_RE_VERBO_PESQUISA = re.compile(
    r"^\s*(?:jarvis[,\s]+)?(?:pesquisa|pesquisar|pesquise|procura|procurar|procure|"
    r"busca|buscar|busque|consulta|consultar)\b",
    re.I,
)


def _limpar_consulta(texto: str) -> str:
    """Tira o verbo, a fonte e o "sobre" — sobra o assunto."""
    limpo = _RE_VERBO_PESQUISA.sub("", texto)
    limpo = re.sub(
        r"\b(?:no|na|pelo|pela|do|da|em)\s+"
        r"(?:youtube|wikipedia|wiki|duckduckgo|ddg|google|web|internet|sites?)\b",
        " ",
        limpo,
        flags=re.I,
    )
    limpo = re.sub(r"^\s*(?:o|a|os|as)?\s*(?:sobre|por|de)\s+", " ", limpo, flags=re.I)
    limpo = re.sub(r"\s+(?:na web|na internet|no google|no youtube|na wikipedia)$", " ", limpo, flags=re.I)
    return re.sub(r"\s+", " ", limpo).strip(" ?!.,")


def _pedido_direto_de_pesquisa(termo: str) -> dict[str, Any] | None:
    """"pesquisa no youtube sobre X": vai direto para a web, sem passar pelo ranking.

    Sem regra, o pedido casava com `biblioteca.video` (que é legenda de vídeo) e
    o usuário recebia uma sugestão em vez da busca.
    """
    texto = (termo or "").strip()
    if not _RE_VERBO_PESQUISA.search(texto):
        return None
    achado = _RE_FONTE_PEDIDO.search(texto)
    if not achado:
        return None
    consulta = _limpar_consulta(texto)
    if len(consulta) < 2:
        return None
    nome = achado.group(1).lower()
    return {"consulta": consulta, "fonte": _FONTE_APELIDOS.get(nome, nome)}


_NOME_DA_FONTE = {
    "auto": "todas as fontes (DuckDuckGo, Wikipédia e YouTube)",
    "duckduckgo": "DuckDuckGo",
    "wikipedia": "Wikipédia",
    "youtube": "YouTube",
}


def fonte_do_pedido(pedido: str) -> str:
    """"pesquisa no youtube sobre X" → youtube; "no google" → auto (as três).

    O Google não tem página de resultado parseável sem chave; "no google" é o
    pedido genérico, então responde com todas as fontes em vez de fingir.
    """
    achado = _RE_FONTE_PEDIDO.search(pedido or "")
    if not achado:
        return "auto"
    nome = achado.group(1).lower()
    return _FONTE_APELIDOS.get(nome, nome)


async def procurar_na_web(
    pergunta: str,
    *,
    autorizacao: str,
    buscar: Callable[..., dict[str, Any]] | None = None,
    ler: Callable[..., dict[str, Any]] | None = None,
    limite: int = 6,
    paginas: int = 1,
    fonte: str | None = None,
) -> dict[str, Any]:
    """Busca e lê sem modelo: devolve fontes e trecho, nunca um resumo inventado."""
    try:
        resultado = await pesquisa_responder(
            pergunta,
            autorizacao=autorizacao,
            provedor=None,
            buscar=buscar,
            ler=ler,
            limite=limite,
            paginas=paginas,
            fonte=fonte or fonte_do_pedido(pergunta),
        )
    except SistemaError as exc:
        return {
            "acao": "nada",
            "resposta": f"Não achei skill nem receita para isso, e a busca na web falhou: {exc}",
            "fontes": [],
            "avisos": [str(exc)],
        }

    fontes = resultado.get("fontes") or []
    trecho = (resultado.get("trecho") or "").strip()
    passos = extrair_passos(trecho)
    linhas = ["Não tenho skill nem receita para isso. Procurei na web e isto é o que existe:"]
    for indice, fonte in enumerate(fontes, start=1):
        marca = " (lida)" if fonte.get("lida") else ""
        origem = f"[{fonte['fonte']}] " if fonte.get("fonte") else ""
        linhas.append(f"{indice}. {origem}{fonte.get('titulo') or 'sem título'} — {fonte.get('url')}{marca}")
    if trecho:
        linhas.append("")
        linhas.append(f"Trecho de {fontes[0]['url'] if fontes else 'uma das páginas'}:")
        linhas.append(trecho[:LIMITE_TRECHO_WEB])
    if not fontes:
        linhas.append("A busca não devolveu nenhum link.")
    if len(passos) >= 2:
        linhas.append("")
        linhas.append("A página traz um passo a passo:")
        linhas += [f"{indice}. {passo}" for indice, passo in enumerate(passos, start=1)]
        linhas.append("")
        linhas.append("Se quiser que eu guarde isso como skill, diga: criar skill com esses passos")
    return {
        "acao": "web",
        "resposta": "\n".join(linhas),
        "fontes": fontes,
        "passos": passos,
        "avisos": list(resultado.get("avisos") or []),
    }



_RE_PASSO = re.compile(
    r"(?:^|(?<=[.;:\n]))[ \t]*(?:passo\s*)?(\d{1,2})\s*[.)\-–:]\s*(?=[A-Za-zÀ-ÿ])",
    re.IGNORECASE | re.MULTILINE,
)
_RE_CRIAR_PASSOS = re.compile(
    r"\b(?:criar|salvar|guardar|transformar|aprove|aprovar|vira)\b.*\b(?:skill|passos?|procedimento)\b",
    re.IGNORECASE,
)


def extrair_passos(texto: str, limite: int = 8) -> list[str]:
    """Lista numerada que aparece no texto lido da web — sem inventar nada.

    Só aceita o que está escrito: ``1. ... 2. ...`` ou ``Passo 1: ...``.
    Número solto no meio da frase (data, preço) não vira passo.
    """
    bruto = (texto or "").replace("\r", "\n")
    marcas = list(_RE_PASSO.finditer(bruto))
    passos: list[str] = []
    for indice, marca in enumerate(marcas):
        inicio = marca.end()
        fim = marcas[indice + 1].start() if indice + 1 < len(marcas) else len(bruto)
        trecho = " ".join(bruto[inicio:fim].split()).strip(" .;,-")
        if 15 <= len(trecho) <= 300:
            passos.append(trecho)
    return passos[:limite]


def _titulo_de(termo: str) -> str:
    limpo = re.sub(r"^(?:como\s+(?:eu\s+)?(?:faço|faco|fazer)|como|o que é|o que e)\s+", "", (termo or "").strip(), flags=re.IGNORECASE)
    limpo = " ".join(limpo.split())[:60].strip(" ?.!")
    return limpo[:1].upper() + limpo[1:] if limpo else "Procedimento"


def criar_skill_de_passos(
    raiz: Path,
    nome: str,
    passos: list[str] | tuple[str, ...],
    *,
    descricao: str = "",
    fonte: str = "",
) -> tuple[SkillLocal, bool]:
    """Guarda o passo a passo lido da web como skill local de procedimento."""
    limpos = [str(passo).strip() for passo in passos if str(passo).strip()][:12]
    if len(limpos) < 2:
        raise AgenteError("Preciso de pelo menos dois passos para criar a skill.")
    locais = carregar_locais(raiz)
    base = re.sub(r"[^a-z0-9]+", "-", normalizar(nome)).strip("-")[:40] or "procedimento"
    skill_id = f"local.proc-{base}"
    for local in locais:
        if local.id == skill_id:
            return local, False
    skill = SkillLocal(
        id=skill_id,
        nome=nome.strip()[:80] or "Procedimento",
        descricao=(descricao or f"Passo a passo lido de {fonte or 'uma página'}.")[:300],
        receita="procedimento",
        campo="",
        criado_em=datetime.now(timezone.utc).isoformat(),
        passos=tuple(limpos),
        fonte=fonte,
    )
    salvar_locais(raiz, [*locais, skill])
    return skill, True


def guardar_pendente(raiz: Path, dados: dict[str, Any]) -> None:
    arquivo = Path(raiz) / ARQUIVO_PENDENTE
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ler_pendente(raiz: Path) -> dict[str, Any] | None:
    try:
        bruto = json.loads((Path(raiz) / ARQUIVO_PENDENTE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return bruto if isinstance(bruto, dict) and bruto.get("passos") else None


def limpar_pendente(raiz: Path) -> None:
    (Path(raiz) / ARQUIVO_PENDENTE).unlink(missing_ok=True)


def _resposta_de_local(entrada: Entrada, locais: list[SkillLocal]) -> str | None:
    """Skill de procedimento: devolve o passo a passo gravado, com a fonte."""
    if not entrada.local:
        return None
    local = next((item for item in locais if item.id == entrada.skill_id), None)
    if local is None or local.receita != "procedimento" or not local.passos:
        return None
    linhas = [f"Passo a passo — skill local “{local.nome}” ({local.id}):", ""]
    linhas += [f"{indice}. {passo}" for indice, passo in enumerate(local.passos, start=1)]
    if local.fonte:
        linhas += ["", f"Fonte: {local.fonte}"]
    linhas += ["", "Passos copiados da página; confira a fonte antes de seguir."]
    return "\n".join(linhas)


async def _rodar_entrada(
    entrada: Entrada,
    termo: str,
    *,
    registry: Any,
    locais: list[SkillLocal],
    confirmar: bool = False,
    autorizacao: str = "",
) -> dict[str, Any]:
    """Executa a entrada: procedimento local responde direto; o resto vai à skill."""
    texto = _resposta_de_local(entrada, locais)
    if texto is not None:
        return {"parametros": {}, "faltando": [], "resposta": texto}
    return await _executar_skill(entrada, termo, registry=registry, confirmar=confirmar, autorizacao=autorizacao)


# ------------------------------------------------ memória do agente (arquivos)

ARQUIVO_APELIDOS = Path("agente-local") / "apelidos.json"
ARQUIVO_FILA = Path("agente-local") / "fila.json"
ARQUIVO_RESPOSTAS = Path("agente-local") / "respostas.json"
ARQUIVO_HISTORICO = Path("agente-local") / "historico.json"
ARQUIVO_PENDENTE = Path("agente-local") / "pendente.json"
LIMITE_HISTORICO = 200
LIMITE_FILA = 200


def _ler_lista(arquivo: Path) -> list[dict[str, Any]]:
    try:
        bruto = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    itens = bruto.get("itens") if isinstance(bruto, dict) else bruto
    return [item for item in itens or [] if isinstance(item, dict)]


def _gravar_lista(arquivo: Path, itens: list[dict[str, Any]]) -> None:
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(json.dumps({"itens": itens}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def chave_do_pedido(pedido: str) -> str:
    """Forma comparável do pedido: sem acento, sem pontuação, espaço único."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", normalizar(pedido))).strip()


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- apelidos: "quando eu pedir assim, use esta skill" -----------------------

def ensinar(pedido: str, skill_id: str, raiz: Path, origem: str = "correcao") -> dict[str, Any]:
    """Guarda a correlação pedido → skill. Ensina de novo substitui a antiga."""
    chave = chave_do_pedido(pedido)
    if not chave or not skill_id:
        raise AgenteError("Para ensinar, mande o pedido e a skill.")
    arquivo = Path(raiz) / ARQUIVO_APELIDOS
    itens = [item for item in _ler_lista(arquivo) if chave_do_pedido(str(item.get("pedido", ""))) != chave]
    registro = {"pedido": pedido.strip(), "chave": chave, "skill_id": skill_id, "origem": origem, "criado_em": _agora()}
    itens.append(registro)
    _gravar_lista(arquivo, itens[-LIMITE_HISTORICO:])
    return registro


def apelido_de(pedido: str, raiz: Path) -> dict[str, Any] | None:
    """Procura o apelido exato; se não houver, o mais longo que abre o pedido.

    Isso permite ensinar "meu relatorio do mes" e depois pedir
    "meu relatorio do mes com path=documentos/x.pdf".
    """
    chave = chave_do_pedido(pedido)
    if not chave:
        return None
    itens = _ler_lista(Path(raiz) / ARQUIVO_APELIDOS)
    for item in itens:
        if item.get("chave") == chave:
            return item
    candidatos = [
        item
        for item in itens
        if item.get("chave") and chave.startswith(str(item["chave"]) + " ")
    ]
    if not candidatos:
        return None
    return max(candidatos, key=lambda item: len(str(item["chave"])))


def listar_apelidos(raiz: Path) -> list[dict[str, Any]]:
    return _ler_lista(Path(raiz) / ARQUIVO_APELIDOS)


def esquecer(pedido: str, raiz: Path) -> int:
    """Remove o apelido e a resposta guardada daquele pedido. Devolve quantos."""
    chave = chave_do_pedido(pedido)
    removidos = 0
    for arquivo, campo in ((ARQUIVO_APELIDOS, "chave"), (ARQUIVO_RESPOSTAS, "chave")):
        caminho = Path(raiz) / arquivo
        itens = _ler_lista(caminho)
        restantes = [item for item in itens if item.get(campo) != chave]
        removidos += len(itens) - len(restantes)
        if len(restantes) != len(itens):
            _gravar_lista(caminho, restantes)
    return removidos


# --- respostas guardadas da web ---------------------------------------------

def guardar_resposta(pedido: str, texto: str, fontes: list[dict[str, Any]], raiz: Path) -> dict[str, Any]:
    chave = chave_do_pedido(pedido)
    arquivo = Path(raiz) / ARQUIVO_RESPOSTAS
    itens = [item for item in _ler_lista(arquivo) if item.get("chave") != chave]
    registro = {"pedido": pedido.strip(), "chave": chave, "texto": texto, "fontes": fontes, "criado_em": _agora()}
    itens.append(registro)
    _gravar_lista(arquivo, itens[-LIMITE_HISTORICO:])
    return registro


def resposta_guardada(pedido: str, raiz: Path) -> dict[str, Any] | None:
    chave = chave_do_pedido(pedido)
    if not chave:
        return None
    for item in _ler_lista(Path(raiz) / ARQUIVO_RESPOSTAS):
        if item.get("chave") == chave:
            return item
    return None


# --- fila do que ele não soube fazer ----------------------------------------

def registrar_falha(pedido: str, motivo: str, raiz: Path) -> dict[str, Any]:
    """Todo pedido sem solução fica aqui, com data — nada some."""
    chave = chave_do_pedido(pedido)
    arquivo = Path(raiz) / ARQUIVO_FILA
    itens = _ler_lista(arquivo)
    for item in itens:
        if item.get("chave") == chave:
            item["tentativas"] = int(item.get("tentativas", 1)) + 1
            item["motivo"] = motivo
            item["visto_em"] = _agora()
            _gravar_lista(arquivo, itens[-LIMITE_FILA:])
            return item
    registro = {
        "id": f"falha-{len(itens) + 1:04d}",
        "pedido": pedido.strip(),
        "chave": chave,
        "motivo": motivo,
        "tentativas": 1,
        "criado_em": _agora(),
        "visto_em": _agora(),
    }
    itens.append(registro)
    _gravar_lista(arquivo, itens[-LIMITE_FILA:])
    return registro


def listar_fila(raiz: Path) -> list[dict[str, Any]]:
    itens = _ler_lista(Path(raiz) / ARQUIVO_FILA)
    return sorted(itens, key=lambda item: str(item.get("visto_em", "")), reverse=True)


def remover_falha(falha_id: str, raiz: Path) -> bool:
    arquivo = Path(raiz) / ARQUIVO_FILA
    itens = _ler_lista(arquivo)
    restantes = [item for item in itens if item.get("id") != falha_id]
    if len(restantes) == len(itens):
        return False
    _gravar_lista(arquivo, restantes)
    return True


# --- histórico do que ele fez ------------------------------------------------

def registrar_execucao(
    pedido: str,
    *,
    acao: str,
    skill: str | None,
    confianca: float,
    resposta: str,
    raiz: Path,
) -> dict[str, Any]:
    arquivo = Path(raiz) / ARQUIVO_HISTORICO
    itens = _ler_lista(arquivo)
    registro = {
        "quando": _agora(),
        "pedido": pedido.strip()[:200],
        "acao": acao,
        "skill": skill,
        "confianca": confianca,
        "resumo": (resposta or "")[:240],
    }
    itens.append(registro)
    _gravar_lista(arquivo, itens[-LIMITE_HISTORICO:])
    return registro


def listar_historico(raiz: Path, limite: int = 50) -> list[dict[str, Any]]:
    itens = _ler_lista(Path(raiz) / ARQUIVO_HISTORICO)
    return list(reversed(itens))[:limite]


def painel(raiz: Path) -> dict[str, Any]:
    """Tudo que a página do agente mostra, numa chamada só."""
    return {
        "locais": [local.publica() for local in carregar_locais(raiz)],
        "receitas": [receita.publica() for receita in RECEITAS],
        "apelidos": list(reversed(listar_apelidos(raiz))),
        "fila": listar_fila(raiz),
        "historico": listar_historico(raiz),
        "respostas": [
            {"pedido": item.get("pedido"), "criado_em": item.get("criado_em"), "fontes": item.get("fontes", [])}
            for item in reversed(_ler_lista(Path(raiz) / ARQUIVO_RESPOSTAS))
        ],
    }


# ----------------------------------------------------------- orquestração

def _resultado_base(pedido: str) -> dict[str, Any]:
    return {
        "ok": True,
        "pedido": pedido,
        "acao": "nada",
        "via": "nada",
        "skill": None,
        "confianca": 0.0,
        "parametros": {},
        "faltando": [],
        "resposta": "",
        "alternativas": [],
        "fontes": [],
        "avisos": [],
        "limites": [
            "A busca nas skills é por palavra, não por significado: sinônimo fora da lista não encontra.",
            "Skill criada aqui vem de um catálogo fechado de receitas; o agente não escreve código novo.",
            "Nenhum passo chama provedor de IA — com a rede desligada, só a etapa da web deixa de funcionar.",
        ],
    }


async def _executar_skill(
    entrada: Entrada,
    consulta: str,
    *,
    registry: Any,
    confirmar: bool = False,
    autorizacao: str = "",
) -> dict[str, Any]:
    explicitos = parametros_explicitos(consulta, entrada.schema)
    if entrada.receita:
        receita = _RECEITAS_POR_ID.get(entrada.receita)
        if receita is None:
            return {"parametros": {}, "faltando": [], "resposta": None, "erro": "receita desconhecida"}
        texto = str(explicitos.get(receita.campo) or texto_livre(consulta))
        if receita.tipo == "numeros" and not _numeros(texto):
            texto = ""
        if not texto:
            return {"parametros": {}, "faltando": [receita.campo], "resposta": None}
        resultado = executar_receita(receita, texto)
        return {"parametros": {receita.campo: texto}, "faltando": [], "resposta": str(resultado.get("resultado") or "")}
    parametros, faltando = extrair_parametros(consulta, entrada.schema)
    parametros.update(explicitos)
    # O "sim, pode" que liberou a execução também vale como autorização da skill.
    propriedades = entrada.schema.get("properties") or {}
    if autorizacao and "autorizacao" in propriedades and not parametros.get("autorizacao"):
        parametros["autorizacao"] = autorizacao
    faltando = [campo for campo in (entrada.schema.get("required") or []) if campo not in parametros]
    if faltando:
        return {"parametros": parametros, "faltando": faltando, "resposta": None}
    if entrada.confirma and not confirmar:
        # Não executa nada: devolve os parâmetros e pede o "sim".
        return {"parametros": parametros, "faltando": [], "resposta": None, "confirmar": True}
    try:
        resultado = await registry.execute(entrada.skill_id, parametros, False)
    except Exception as exc:  # a skill pode recusar parâmetro; o chat não pode cair
        return {"parametros": parametros, "faltando": [], "resposta": None, "erro": str(exc)}
    return {"parametros": parametros, "faltando": [], "resposta": formatar_resultado(resultado)}


def _pedir_confirmacao(
    base: dict[str, Any],
    entrada: Entrada,
    tentativa: dict[str, Any],
    aviso: str = "",
) -> dict[str, Any]:
    """Para antes do efeito colateral e mostra exatamente o que vai rodar."""
    parametros = {
        chave: valor for chave, valor in (tentativa.get("parametros") or {}).items()
        if valor not in (None, "", [], {})
    }
    detalhe = ", ".join(f"{chave}={valor}" for chave, valor in parametros.items()) or "sem parâmetros"
    base["acao"] = "confirmar"
    base["parametros"] = parametros
    base["resposta"] = (
        f"A skill “{entrada.nome}” ({entrada.skill_id}) baixa, grava ou executa algo. "
        f"Vou usar: {detalhe}. Responda “sim, pode” para eu seguir."
    )
    if aviso:
        base["resposta"] += f"\n\n⚠ {aviso}"
    return base


def _detalhe_que_falta(campos: list[str], entrada: Entrada) -> str:
    """Junta os campos que faltam numa frase que continua depois de uma vírgula."""
    partes = [_pedido_do_campo(campo, entrada, "veja o formulário da skill") for campo in campos]
    texto = " e ".join(partes)
    return (texto[0].lower() + texto[1:]) if texto else texto


def _pedido_do_campo(campo: str, entrada: Entrada, exemplo: str) -> str:
    titulo = _titulo_do_campo(campo, entrada.schema)
    return f"Falta o campo “{titulo}”. Exemplo: {exemplo}"


async def _resolver(
    pedido: str,
    *,
    registry: Any,
    raiz: Path,
    autorizacao: str = "",
    criar: bool = True,
    consultar_web: bool = True,
    confirmar: bool = False,
    buscar: Callable[..., dict[str, Any]] | None = None,
    ler: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve o pedido sem IA: apelido → guardada → skill → receita → web."""
    termo = (pedido or "").strip()
    if len(termo) < 3:
        raise AgenteError("Escreva o pedido com pelo menos 3 caracteres.")

    base = _resultado_base(termo)
    locais = carregar_locais(raiz)

    # 0a. Resposta que já foi buscada na web e guardada numa correção.
    guardada = resposta_guardada(termo, raiz)
    if guardada is not None:
        base["acao"] = "guardado"
        base["via"] = "guardado"
        base["resposta"] = (
            f"{guardada.get('texto', '')}\n\n"
            f"(resposta guardada em {str(guardada.get('criado_em', ''))[:10]} — diga “esqueça {termo}” para buscar de novo)"
        )
        base["fontes"] = [fonte for fonte in guardada.get("fontes") or [] if isinstance(fonte, dict)]
        return base

    # 0a. Passo a passo lido da web virando skill local.
    if _RE_CRIAR_PASSOS.search(termo):
        pendente = ler_pendente(raiz)
        if pendente is not None:
            try:
                skill, criada = criar_skill_de_passos(
                    raiz,
                    str(pendente.get("titulo") or _titulo_de(termo)),
                    pendente["passos"],
                    descricao=str(pendente.get("descricao") or ""),
                    fonte=str(pendente.get("fonte") or ""),
                )
            except AgenteError as exc:
                base["acao"] = "faltando"
                base["resposta"] = str(exc)
                return base
            limpar_pendente(raiz)
            base["acao"] = "criado"
            base["via"] = "procedimento"
            base["skill"] = {
                "id": skill.id,
                "nome": skill.nome,
                "categoria": "Skill local",
                "descricao": skill.descricao,
                "local": True,
            }
            base["confianca"] = 1.0
            base["parametros"] = {"passos": len(skill.passos)}
            base["resposta"] = (
                f"{'Criei' if criada else 'Já existia'} a skill local “{skill.nome}” ({skill.id}) "
                f"com {len(skill.passos)} passos lidos da página.\n"
                f"Da próxima vez, peça por “{skill.nome}” que eu devolvo o passo a passo."
            )
            return base

    # 0b. Apelido ensinado: "quando eu pedir assim, use esta skill".
    ensinado = apelido_de(termo, raiz)
    if ensinado is not None:
        alvo = str(ensinado.get("skill_id") or "")
        disponiveis = indexar(registry.list()) + [entrada_de_local(local) for local in locais]
        escolhida = next((item for item in disponiveis if item.skill_id == alvo), None)
        if escolhida is not None:
            tentativa = await _rodar_entrada(
                escolhida,
                termo,
                registry=registry,
                locais=locais,
                confirmar=confirmar,
                autorizacao=autorizacao,
            )
            base["skill"] = escolhida.resumo()
            base["parametros"] = tentativa.get("parametros", {})
            base["via"] = "apelido"
            base["confianca"] = 1.0
            if tentativa.get("confirmar"):
                return _pedir_confirmacao(base, escolhida, tentativa)
            if tentativa.get("resposta"):
                base["acao"] = "executado"
                base["resposta"] = str(tentativa["resposta"])
                return base
            if tentativa.get("faltando"):
                base["acao"] = "faltando"
                base["faltando"] = tentativa["faltando"]
                base["resposta"] = "Você me ensinou a usar “{}”, mas {}.".format(
                    escolhida.nome,
                    " e ".join(_pedido_do_campo(campo, escolhida, "veja o formulário da skill") for campo in tentativa["faltando"]),
                )
                return base

    # 0b1. "pesquisa no youtube sobre X": a fonte está dita, não há o que adivinhar.
    pesquisa = _pedido_direto_de_pesquisa(termo)
    if pesquisa is not None:
        base["via"] = "web"
        base["confianca"] = 1.0
        achado = await procurar_na_web(
            pesquisa["consulta"],
            autorizacao=autorizacao,
            buscar=buscar,
            ler=ler,
            fonte=pesquisa["fonte"],
        )
        base["acao"] = achado["acao"]
        base["resposta"] = achado["resposta"]
        base["fontes"] = achado["fontes"]
        base["avisos"].extend(achado["avisos"])
        base["parametros"] = {"consulta": pesquisa["consulta"], "fonte": pesquisa["fonte"]}
        if achado["acao"] == "nada":
            # O aviso antigo ("não achei skill nem receita") não faz sentido num
            # pedido que já dizia onde buscar. E, principalmente: não é o token.
            motivo = "; ".join(achado["avisos"] or ["nenhuma fonte respondeu"])
            onde = _NOME_DA_FONTE.get(pesquisa["fonte"], pesquisa["fonte"])
            linhas = [f"Tentei buscar “{pesquisa['consulta']}” em {onde} e não deu: {motivo}"]
            if "rede" not in motivo.lower():
                linhas.append(
                    "A busca não usa token: confira a internet do PC. Se uma fonte cair, as "
                    "outras continuam — tente de novo sem dizer a fonte para eu usar as três."
                )
            base["resposta"] = "\n".join(linhas)
        return base

    # 0b2. Google Drive: regra antes do ranking (a palavra "drive" dilui tudo).
    direto = _pedido_direto_de_drive(termo)

    # 0b3. Mouse e teclado: coordenada e verbo são sinal forte.
    if direto is None:
        direto = _pedido_direto_de_mesa(termo)

    # 0b4. Habilidades de fora: link colado, lista ou uso como roteiro.
    if direto is None:
        direto = _pedido_direto_de_habilidade(termo)

    # 0b5. Correio exportado: triagem, padrão de escrita e rascunho.
    if direto is None:
        direto = _pedido_direto_de_correio(termo)

    # 0b6. Catálogo de terceiros: carregar a planilha, filtrar e importar.
    if direto is None:
        direto = _pedido_direto_de_catalogo(termo)

    # 0b7. Livros livres e adaptação de habilidade importada.
    if direto is None:
        direto = _pedido_direto_de_cultura(termo)

    # 0c. Repositório citado com comando ou arquivo: regra, não adivinhação.
    if direto is None:
        direto = _pedido_direto_de_repositorio(termo)
    if direto is not None:
        # O formulário real da skill importa: só injeta `autorizacao` em quem
        # declara esse campo. Sem isso, a confirmação do chat quebrava skills
        # com `extra="forbid"` (a do Drive é uma delas).
        schema_direto = _schema_da_skill(registry, direto["skill_id"])
        nome_real, categoria_real, descricao_real = _ficha_real(
            registry, direto["skill_id"], direto
        )
        entrada_direta = Entrada(
            skill_id=direto["skill_id"],
            nome=nome_real,
            categoria=categoria_real,
            descricao=descricao_real,
            schema=schema_direto,
            fortes=frozenset(),
            fracos=frozenset(),
            confirma=bool(direto["confirma"]),
        )
        base["skill"] = entrada_direta.resumo()
        base["parametros"] = dict(direto["parametros"])
        base["confianca"] = 1.0
        if direto["confirma"] and not confirmar:
            return _pedir_confirmacao(
                base,
                entrada_direta,
                {"parametros": direto["parametros"]},
                aviso=str(direto.get("aviso") or ""),
            )
        parametros = dict(direto["parametros"])
        if direto["confirma"] and autorizacao and "autorizacao" in (schema_direto.get("properties") or {}):
            parametros["autorizacao"] = autorizacao
        try:
            resultado = await registry.execute(direto["skill_id"], parametros, False)
        except Exception as exc:  # recusa da própria skill, não queda do chat
            base["acao"] = "nada"
            base["resposta"] = f"A skill “{entrada_direta.nome}” recusou o pedido: {exc}"
            return base
        base["acao"] = "executado"
        base["via"] = "skill"
        base["resposta"] = formatar_resultado(resultado)
        return base

    receita = achar_receita(termo) if criar else None

    # 0. Receita que já virou skill local: executa direto, sem passar pelo
    #    ranking — o gatilho da receita é sinal forte e determinístico.
    if receita is not None:
        existente = next((local for local in locais if local.receita == receita.id), None)
        if existente is not None:
            tentativa = await _rodar_entrada(
                entrada_de_local(existente), termo, registry=registry, locais=locais
            )
            if tentativa.get("resposta"):
                base["acao"] = "executado"
                base["confianca"] = 1.0
                base["skill"] = {"id": existente.id, "nome": existente.nome, "categoria": "Skill local", "descricao": existente.descricao, "local": True}
                base["parametros"] = tentativa["parametros"]
                base["resposta"] = f"Usei a skill local “{existente.nome}” ({existente.id}).\n\n{tentativa['resposta']}"
                return base

    entradas = indexar(registry.list()) + [entrada_de_local(local) for local in locais]
    ranking = pesquisar(termo, entradas, LIMITE_CANDIDATOS)

    if ranking:
        base["alternativas"] = [
            {"id": item["entrada"].skill_id, "nome": item["entrada"].nome, "confianca": item["score"]}
            for item in ranking[1:4]
        ]

    # 1. Skill existente com confiança alta e ao menos um termo forte: executa.
    if ranking and ranking[0]["score"] >= LIMIAR_EXECUTAR and ranking[0]["fortes"] > 0:
        principal = ranking[0]
        base["confianca"] = principal["score"]
        tentativa = await _rodar_entrada(
            principal["entrada"],
            termo,
            registry=registry,
            locais=locais,
            confirmar=confirmar,
            autorizacao=autorizacao,
        )
        base["parametros"] = tentativa["parametros"]
        base["skill"] = principal["entrada"].resumo()
        if tentativa.get("confirmar"):
            return _pedir_confirmacao(base, principal["entrada"], tentativa)
        if tentativa.get("erro"):
            base["acao"] = "nada"
            base["resposta"] = (
                f"A skill “{principal['entrada'].nome}” recusou o pedido: {tentativa['erro']}"
            )
            return base
        if tentativa.get("resposta"):
            base["acao"] = "executado"
            base["via"] = "skill"
            prefixo = f"Usei a skill local “{principal['entrada'].nome}” ({principal['entrada'].skill_id}).\n\n" if principal["entrada"].local else ""
            base["resposta"] = prefixo + tentativa["resposta"]
            return base
        if tentativa.get("faltando"):
            base["acao"] = "faltando"
            base["faltando"] = tentativa["faltando"]
            base["resposta"] = "Encontrei a skill “{}”, mas {}.".format(
                principal["entrada"].nome,
                _detalhe_que_falta(tentativa["faltando"], principal["entrada"]),
            )
            return base
        base["avisos"].append(f"A skill {principal['entrada'].skill_id} recusou o pedido: {tentativa.get('erro') or 'sem detalhe'}")

    # 2. Biblioteca: livro, vídeo ou pesquisa importados nesta máquina. Vem
    #    antes da faixa média porque cobertura de 50% das palavras é evidência
    #    mais forte que um casamento lexical fraco com o nome de uma skill.
    try:
        achado_biblioteca = biblioteca.responder(termo)
    except Exception:
        achado_biblioteca = None
    if achado_biblioteca is not None:
        base["acao"] = "biblioteca"
        base["via"] = "biblioteca"
        base["confianca"] = float(achado_biblioteca.get("cobertura") or 0.0)
        base["resposta"] = str(achado_biblioteca["resposta"])
        return base

    # 3. Confiança média: não executa nada. Pede o campo que falta quando a
    #    skill é a única parecida; caso contrário, mostra as mais próximas.
    if ranking and ranking[0]["score"] >= LIMIAR_SUGERIR and ranking[0]["fortes"] > 0:
        principal = ranking[0]
        base["confianca"] = principal["score"]
        _, faltando = extrair_parametros(termo, principal["entrada"].schema)
        segundo = ranking[1]["score"] if len(ranking) > 1 else 0.0
        if faltando and principal["score"] - segundo >= 0.15:
            base["acao"] = "faltando"
            base["skill"] = principal["entrada"].resumo()
            base["faltando"] = faltando
            base["resposta"] = "Encontrei a skill “{}”, mas {}.".format(
                principal["entrada"].nome,
                _detalhe_que_falta(faltando, principal["entrada"]),
            )
            return base
        base["acao"] = "sugerir"
        base["skill"] = None
        nomes = "\n".join(f"- {item['entrada'].nome} ({item['entrada'].skill_id})" for item in ranking[:3])
        base["resposta"] = (
            "Não tenho certeza de qual skill resolve isso. As mais próximas são:\n"
            f"{nomes}\n\nDiga o nome ou o id da skill, ou reformule o pedido."
        )
        return base

    # 4. Nenhuma skill: cria a skill local a partir de uma receita e executa.
    if receita is not None:
        skill, criada = criar_skill(receita, raiz)
        entrada_texto = texto_livre(termo)
        if receita.tipo == "numeros" and not _numeros(entrada_texto):
            entrada_texto = ""
        base["skill"] = {"id": skill.id, "nome": skill.nome, "categoria": "Skill local", "descricao": skill.descricao, "local": True}
        if not entrada_texto:
            base["acao"] = "faltando"
            base["faltando"] = [receita.campo]
            base["resposta"] = (
                f"{'Criei' if criada else 'Já existe'} a skill local “{skill.nome}” ({skill.id}).\n"
                f"Para rodar, mande: {receita.exemplo}"
            )
            return base
        resultado = executar_receita(receita, entrada_texto)
        base["acao"] = "criado"
        base["via"] = "receita"
        base["parametros"] = {receita.campo: entrada_texto}
        base["confianca"] = 1.0
        base["resposta"] = f"{'Criei' if criada else 'Usei'} a skill local “{skill.nome}” ({skill.id}).\n\n{resultado.get('resultado', '')}"
        return base

    # 5. Web, sem modelo: fontes e trecho.
    if consultar_web:
        busca_web = await procurar_na_web(termo, autorizacao=autorizacao, buscar=buscar, ler=ler)
        base["acao"] = busca_web["acao"]
        base["via"] = "web" if busca_web["acao"] == "web" else "nada"
        base["resposta"] = busca_web["resposta"]
        base["fontes"] = busca_web["fontes"]
        base["avisos"].extend(busca_web["avisos"])
        passos = busca_web.get("passos") or []
        if busca_web["acao"] == "web" and len(passos) >= 2:
            guardar_pendente(
                raiz,
                {
                    "titulo": _titulo_de(termo),
                    "descricao": f"Passo a passo lido de {busca_web['fontes'][0]['url'] if busca_web['fontes'] else 'uma página'}.",
                    "passos": passos,
                    "fonte": busca_web["fontes"][0]["url"] if busca_web["fontes"] else "",
                    "criado_em": datetime.now(timezone.utc).isoformat(),
                },
            )
        if busca_web["acao"] == "web":
            base["avisos"].append(
                "Não criei skill para isso: escrever código novo exigiria um modelo. "
                "Se quiser, peça uma das receitas prontas ou copie os passos da página."
            )
        return base

    base["resposta"] = (
        "Não achei skill, receita nem web para este pedido. "
        "Diga “ajuda” para ver os comandos que funcionam sem modelo."
    )
    return base


async def pesquisar_e_guardar(
    pedido: str,
    *,
    raiz: Path,
    autorizacao: str,
    buscar: Callable[..., dict[str, Any]] | None = None,
    ler: Callable[..., dict[str, Any]] | None = None,
    limite: int = 6,
) -> dict[str, Any]:
    """Busca na web sem modelo e guarda a resposta para o mesmo pedido."""
    resultado = await procurar_na_web(pedido, autorizacao=autorizacao, buscar=buscar, ler=ler, limite=limite)
    if resultado["acao"] == "web":
        guardar_resposta(pedido, resultado["resposta"], resultado["fontes"], raiz)
    return resultado


async def atender(
    pedido: str,
    *,
    registry: Any,
    raiz: Path,
    autorizacao: str = "",
    criar: bool = True,
    consultar_web: bool = True,
    confirmar: bool = False,
    buscar: Callable[..., dict[str, Any]] | None = None,
    ler: Callable[..., dict[str, Any]] | None = None,
    forcar_web: bool = False,
) -> dict[str, Any]:
    """Resolve o pedido sem IA e **registra** o que fez.

    A resolução fica em `_resolver`; aqui ficam as três coisas que o usuário
    não pode perder de vista: nada some (fila), tudo fica no histórico e a
    correção pela web vale para as próximas vezes.
    """
    termo = (pedido or "").strip()
    if len(termo) < 3:
        raise AgenteError("Escreva o pedido com pelo menos 3 caracteres.")

    if forcar_web:
        base = _resultado_base(termo)
        base["via"] = "web"
        resultado = await pesquisar_e_guardar(termo, raiz=raiz, autorizacao=autorizacao, buscar=buscar, ler=ler)
        base["acao"] = resultado["acao"]
        base["resposta"] = resultado["resposta"]
        base["fontes"] = resultado["fontes"]
        base["avisos"] = list(resultado["avisos"])
        if resultado["acao"] == "web":
            registrar_execucao(termo, acao="web", skill=None, confianca=0.0, resposta=resultado["resposta"], raiz=raiz)
        else:
            registrar_falha(termo, resultado["resposta"][:200], raiz)
        return base

    resultado = await _resolver(
        termo,
        registry=registry,
        raiz=raiz,
        autorizacao=autorizacao,
        criar=criar,
        consultar_web=consultar_web,
        confirmar=confirmar,
        buscar=buscar,
        ler=ler,
    )
    if resultado["acao"] == "confirmar":
        return resultado
    if resultado["acao"] in {"nada", "sugerir"}:
        registrar_falha(termo, (resultado.get("resposta") or "")[:200], raiz)
    else:
        registrar_execucao(
            termo,
            acao=resultado["acao"],
            skill=(resultado.get("skill") or {}).get("id"),
            confianca=float(resultado.get("confianca") or 0.0),
            resposta=resultado.get("resposta") or "",
            raiz=raiz,
        )
    return resultado


def ensinar_por_nome(pedido: str, alvo: str, raiz: Path, registry: Any, origem: str = "correcao") -> dict[str, Any]:
    """Aceita id, nome exato ou pedaço do nome e grava o apelido."""
    alvo = (alvo or "").strip()
    if not alvo:
        raise AgenteError("Diga qual skill deve responder por esse pedido.")
    disponiveis = indexar(registry.list()) + [entrada_de_local(local) for local in carregar_locais(raiz)]
    por_id = next((item for item in disponiveis if item.skill_id.lower() == alvo.lower()), None)
    if por_id is None:
        alvo_normal = normalizar(alvo)
        por_nome = next((item for item in disponiveis if normalizar(item.nome) == alvo_normal), None)
        if por_nome is None:
            candidatos = [item for item in disponiveis if alvo_normal in normalizar(item.nome) or alvo_normal in item.skill_id.lower()]
            if len(candidatos) != 1:
                nomes = ", ".join(item.skill_id for item in candidatos[:5]) or "nenhuma"
                raise AgenteError(f"Não achei uma skill única com “{alvo}”. Candidatas: {nomes}.")
            por_nome = candidatos[0]
        por_id = por_nome
    return ensinar(pedido, por_id.skill_id, raiz, origem)
