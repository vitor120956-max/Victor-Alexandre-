"""Habilidades de fora: puxar um `SKILL.md`, guardar e usar como guia.

O pedido que originou esta camada: o usuário viu uma lista de habilidades
publicadas por terceiros (skills.sh, clawhub.ai, repositórios do GitHub) e
queria que o JARVIS **buscasse aquilo, guardasse e usasse** quando ele pedisse.

O que dá para fazer sem chave nenhuma — e é o que esta camada faz:

1. **puxar** o texto da habilidade (o `SKILL.md`, que é markdown puro) de um
   link do GitHub, de uma página de catálogo ou de um `raw` qualquer;
2. **guardar** o texto em `storage/habilidades.json`, com nome, descrição,
   endereço de origem e data — nada é executado, nada é instalado;
3. **usar** como guia: quando você pede, o JARVIS devolve a habilidade inteira
   (ou o trecho que interessa) junto com a sua pergunta, já com a fonte.

O que esta camada **não** faz, e não finge fazer: não roda o código de uma
habilidade, não instala pacote e não transforma texto em raciocínio. Sem modelo
configurado, a habilidade é um **roteiro** que você segue — o JARVIS não "pensa"
com ela. Habilidades que dependem de um modelo (gerar imagem, escrever código
com IA, usar o Copilot) precisam de provedor pago; o texto delas é guardado,
mas o efeito não acontece sozinho.

Nada aqui pede token: baixar um `.md` de texto é leitura. A trava é
`JARVIS_HOST_REDE=1`, a mesma da busca na web.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlparse

from . import busca_web, dados

ARQUIVO = "habilidades.json"
MAX_TEXTO = 60_000
LIMITE_GUIA = 9_000
MAX_TENTATIVAS = 4
AGENTE = "jarvis-habilidades/1.0 (+local)"

# Caminhos onde um repositório costuma guardar a habilidade, em ordem de chance.
CAMINHOS_SKILL = (
    "SKILL.md",
    "skills/{nome}/SKILL.md",
    ".claude/skills/{nome}/SKILL.md",
    "skill/SKILL.md",
    "README.md",
)

Baixar = Callable[[str], str]


class HabilidadeError(ValueError):
    """A habilidade não veio, veio vazia ou o endereço não serve."""


# ------------------------------------------------------------------ endereços

def _skills_do_repositorio(url: str) -> list[str]:
    """Repositório sem `SKILL.md` na raiz: descobre onde estão os arquivos.

    Um repositório como `vercel-labs/agent-skills` guarda dezenas de habilidades
    em pastas. Em vez de adivinhar caminho, a árvore da API diz onde cada
    `SKILL.md` está — e o import pega os primeiros.
    """
    from . import github  # import local: evita ciclo na carga do pacote

    host = (urlparse(url).hostname or "").lower()
    if host not in {"github.com", "www.github.com"}:
        return []
    _, dono, repo, ref, _ = _pedacos(url)
    if not dono or not repo:
        return []
    try:
        caminhos = github.arvore(f"{dono}/{repo}", ref=ref or "", sufixo="SKILL.md", limite=200)
    except github.GithubError:
        return []
    base = f"https://raw.githubusercontent.com/{dono}/{repo}/{ref or 'HEAD'}"
    return [f"{base}/{caminho}" for caminho in caminhos[:MAX_TENTATIVAS]]


def _via_api(url: str) -> str | None:
    """`raw.githubusercontent.com` bloqueado? A API do GitHub entrega o mesmo texto.

    Isso importa na prática: muita rede de escritório e de operadora bloqueia
    `raw.*`, e a API (`api.github.com`) passa. O conteúdo é idêntico — só não é
    servido como arquivo estático.
    """
    from . import github  # import local: evita ciclo na carga do pacote

    partes = [p for p in urlparse(url).path.split("/") if p]
    if not urlparse(url).hostname or not urlparse(url).hostname.lower().endswith("raw.githubusercontent.com"):
        return None
    if len(partes) < 4:
        return None
    dono, repo, ref = partes[0], partes[1], partes[2]
    caminho = "/".join(partes[3:])
    try:
        return github.arquivo(f"{dono}/{repo}", caminho, ref=ref, limite=MAX_TEXTO)["texto"]
    except github.GithubError:
        return None


def _baixar(url: str) -> str:
    """Mesmo cliente da busca: UA de navegador, teto de página, sem token."""
    try:
        return busca_web._baixar(url)  # noqa: SLF001 — mesma camada de leitura
    except busca_web.BuscaError as exc:
        alternativa = _via_api(url)
        if alternativa:
            return alternativa
        raise HabilidadeError(f"Não consegui baixar {url}: {exc}") from exc


def _publica(url: str) -> str:
    limpo = busca_web._url_publica(url)  # noqa: SLF001
    if not limpo:
        raise HabilidadeError(f"Endereço recusado (só http/https público): {url}")
    return limpo


def _pedacos(url: str) -> tuple[str, str, str, str, str]:
    """`(host, dono, repositório, ref, caminho)` de um link do GitHub."""
    partes = [p for p in urlparse(url).path.split("/") if p]
    dono = partes[0] if partes else ""
    repo = partes[1] if len(partes) > 1 else ""
    modo = partes[2] if len(partes) > 2 else ""
    ref = partes[3] if len(partes) > 3 else ""
    caminho = "/".join(partes[4:]) if len(partes) > 4 else ""
    return (urlparse(url).hostname or "", dono, repo, ref if modo in {"blob", "tree"} else "", caminho)


def enderecos_candidatos(url: str, *, nome: str = "") -> list[str]:
    """Transforma o que o usuário colou em links que devolvem **texto puro**.

    - `github.com/o/r/blob/main/x/SKILL.md` → `raw.githubusercontent.com/...`;
    - `github.com/o/r/tree/main/skills/x` → `raw.../main/skills/x/SKILL.md`;
    - `github.com/o/r` → tenta `SKILL.md` e os caminhos conhecidos;
    - link `raw` já pronto passa direto.
    """
    limpo = _publica(url)
    host = (urlparse(limpo).hostname or "").lower()
    if host.endswith("raw.githubusercontent.com") or host.endswith("raw.github.com"):
        return [limpo]
    if host not in {"github.com", "www.github.com"}:
        return [limpo]  # catálogo ou página qualquer: tenta o texto da página

    _, dono, repo, ref, caminho = _pedacos(limpo)
    if not dono or not repo:
        raise HabilidadeError("Link do GitHub sem dono/repositório.")
    if not ref:
        ref = "HEAD"
    candidatos: list[str] = []
    base = f"https://raw.githubusercontent.com/{dono}/{repo}/{ref}"
    eh_pasta = "/tree/" in limpo
    if caminho:
        if eh_pasta:
            candidatos.append(f"{base}/{caminho.rstrip('/')}/SKILL.md")
        candidatos.append(f"{base}/{caminho}")
        if not eh_pasta and not caminho.lower().endswith((".md", ".markdown", ".txt")):
            candidatos.append(f"{base}/{caminho.rstrip('/')}/SKILL.md")
    else:
        apelido = _slug(nome or repo)
        for modelo in CAMINHOS_SKILL:
            candidatos.append(f"{base}/{modelo.format(nome=apelido)}")
    return candidatos[:MAX_TENTATIVAS]


_RE_GITHUB = re.compile(
    r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
    r"(?:/(?:blob|tree)/[^\"'\s<>]+)?",
)


def _links_do_catalogo(html: str) -> list[str]:
    """De uma página de catálogo (skills.sh, clawhub), tira os links do GitHub."""
    vistos: list[str] = []
    for achado in _RE_GITHUB.findall(html or ""):
        if achado not in vistos:
            vistos.append(achado)
    # O link do próprio arquivo vale mais do que o do repositório.
    com_arquivo = [link for link in vistos if link.lower().endswith((".md", ".markdown"))]
    return (com_arquivo + [link for link in vistos if link not in com_arquivo])[:MAX_TENTATIVAS]


# ------------------------------------------------------------------- markdown

def _sem_acento(texto: str) -> str:
    return "".join(
        letra for letra in unicodedata.normalize("NFD", texto or "") if unicodedata.category(letra) != "Mn"
    )


def _slug(texto: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", _sem_acento(texto or "").lower()).strip("-")
    return base[:48] or "habilidade"


def separar_front_matter(texto: str) -> tuple[dict[str, str], str]:
    """Lê o cabeçalho `--- chave: valor ---` do SKILL.md; o resto é o corpo."""
    bruto = (texto or "").replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    if not bruto.startswith("---"):
        return {}, bruto.strip()
    fim = bruto.find("\n---", 3)
    if fim == -1:
        return {}, bruto.strip()
    cabecalho = bruto[3:fim]
    corpo = bruto[fim + 4 :]
    dados: dict[str, str] = {}
    for linha in cabecalho.splitlines():
        if ":" not in linha or linha.startswith((" ", "\t")):
            continue
        chave, valor = linha.split(":", 1)
        dados[chave.strip().lower()] = valor.strip().strip("\"'")
    return dados, corpo.strip()


def _titulo(corpo: str) -> str:
    for linha in corpo.splitlines():
        if linha.startswith("# "):
            return linha[2:].strip()[:80]
    return ""


def _resumo(corpo: str) -> str:
    """Primeiro parágrafo que não é título, lista nem cerca de código."""
    for bloco in re.split(r"\n\s*\n", corpo):
        limpo = " ".join(bloco.split())
        if not limpo or limpo.startswith(("#", "-", "*", ">", "|", "```")):
            continue
        return limpo[:280]
    return ""


def interpretar(texto: str, *, padrao: str = "habilidade") -> dict[str, Any]:
    """Front matter + corpo → ficha da habilidade. Não inventa nome nem descrição."""
    cabecalho, corpo = separar_front_matter(texto)
    if not corpo:
        raise HabilidadeError("O arquivo veio vazio — não é um SKILL.md.")
    nome = (cabecalho.get("name") or _titulo(corpo) or padrao).strip()[:80]
    descricao = (cabecalho.get("description") or _resumo(corpo)).strip()[:300]
    return {
        "nome": nome,
        "slug": _slug(nome),
        "descricao": descricao,
        "texto": corpo[:MAX_TEXTO],
        "tamanho": len(corpo),
        "ferramentas": (cabecalho.get("allowed-tools") or cabecalho.get("allowed_tools") or "")[:200],
        "versao": (cabecalho.get("version") or "")[:40],
    }


# -------------------------------------------------------------------- arquivo

def _arquivo(raiz: Path | None = None) -> Path:
    return (Path(raiz) if raiz else dados.raiz()) / ARQUIVO


def carregar(raiz: Path | None = None) -> list[dict[str, Any]]:
    try:
        bruto = json.loads(_arquivo(raiz).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    itens = bruto.get("habilidades") if isinstance(bruto, dict) else bruto
    return [item for item in (itens or []) if isinstance(item, dict) and item.get("slug") and item.get("texto")]


def _salvar(raiz: Path | None, itens: list[dict[str, Any]]) -> None:
    arquivo = _arquivo(raiz)
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(
        json.dumps({"habilidades": itens}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def listar(raiz: Path | None = None) -> list[dict[str, Any]]:
    """Ficha curta de cada habilidade guardada — sem o texto inteiro."""
    return [
        {
            "slug": item["slug"],
            "nome": item.get("nome") or item["slug"],
            "descricao": item.get("descricao") or "",
            "url": item.get("url") or "",
            "tamanho": int(item.get("tamanho") or len(item.get("texto") or "")),
            "importado_em": item.get("importado_em") or "",
        }
        for item in carregar(raiz)
    ]


def _achar(ref: str, itens: list[dict[str, Any]]) -> dict[str, Any] | None:
    chave = _slug(ref)
    if not chave or chave == "habilidade":
        return None
    for item in itens:
        if item["slug"] == chave:
            return item
    for item in itens:
        if chave in _slug(item.get("nome") or item["slug"]) or chave in item["slug"]:
            return item
    return None


def remover(ref: str, raiz: Path | None = None) -> bool:
    itens = carregar(raiz)
    achado = _achar(ref, itens)
    if achado is None:
        return False
    _salvar(raiz, [item for item in itens if item is not achado])
    return True


# ------------------------------------------------------------------ importar

def _texto_de_habilidade(url: str, baixar: Baixar) -> tuple[str, str, list[str], list[str], list[str]]:
    """Acha o markdown da habilidade a partir do que foi colado.

    Devolve `(texto, endereço_que_funcionou, tentativas, erros, descobertos)`. Link de
    catálogo (skills.sh, clawhub) é seguido até o GitHub — a página é vitrine,
    o `SKILL.md` é o conteúdo.
    """
    tentativas: list[str] = []
    erros: list[str] = []

    def tentar(alvo: str) -> str | None:
        tentativas.append(alvo)
        try:
            texto = baixar(alvo)
        except HabilidadeError as exc:
            erros.append(str(exc))
            return None
        except busca_web.BuscaError as exc:
            erros.append(str(exc))
            return None
        limpo = (texto or "").lstrip()
        if not limpo:
            erros.append(f"{alvo}: veio vazio")
            return None
        return texto

    for candidato in enderecos_candidatos(url):
        texto = tentar(candidato)
        if texto is None:
            continue
        limpo = texto.lstrip()
        if limpo.startswith(("#", "---")):
            return texto, candidato, tentativas, erros, []
        if "<html" in limpo.lower():
            # Vitrine: procura o link do arquivo dentro dela.
            for link in _links_do_catalogo(texto):
                for alvo in enderecos_candidatos(link):
                    achado = tentar(alvo)
                    if achado is not None and achado.lstrip().startswith(("#", "---")):
                        return achado, alvo, tentativas, erros, []
            erros.append(f"{candidato}: é uma página de catálogo, sem link direto para o SKILL.md")
            continue
        return texto, candidato, tentativas, erros, []

    # Último recurso: é um repositório com as habilidades dentro de pastas?
    descobertos = _skills_do_repositorio(url)
    for alvo in descobertos:
        if alvo in tentativas:
            continue
        achado = tentar(alvo)
        if achado is not None and achado.lstrip().startswith(("#", "---")):
            return achado, alvo, tentativas, erros, descobertos

    raise HabilidadeError(
        "Não achei um SKILL.md em nenhum endereço tentado ("
        + "; ".join(erros[-3:] or tentativas[-3:])
        + "). Cole o link do arquivo — no GitHub, o do botão “Raw”."
    )


def importar(
    url: str,
    *,
    raiz: Path | None = None,
    baixar: Baixar | None = None,
    nome: str = "",
    evitar: Iterable[str] = (),
) -> dict[str, Any]:
    """Puxa a habilidade do link, interpreta e guarda. Devolve a ficha curta.

    `evitar` são slugs já usados nesta rodada (importação em lote): em vez de o
    segundo `SKILL.md` sobrescrever o primeiro, ele ganha sufixo `-2`, `-3`…
    """
    baixar = baixar or _baixar
    texto, achado, tentativas, erros, descobertos = _texto_de_habilidade(url, baixar)
    padrao = _slug(Path(urlparse(achado).path).stem) or _slug(nome) or "habilidade"
    ficha = interpretar(texto, padrao=padrao)
    base = ficha["slug"]
    usados = set(evitar)
    contador = 1
    while ficha["slug"] in usados:
        contador += 1
        ficha["slug"] = f"{base}-{contador}"
    itens = carregar(raiz)
    anterior = _achar(ficha["slug"], itens)
    agora = datetime.now(timezone.utc).isoformat()
    registro = {
        "slug": ficha["slug"],
        "nome": ficha["nome"],
        "descricao": ficha["descricao"],
        "url": achado,
        "origem": url,
        "texto": ficha["texto"],
        "tamanho": ficha["tamanho"],
        "ferramentas": ficha["ferramentas"],
        "versao": ficha["versao"],
        "importado_em": (anterior or {}).get("importado_em") or agora,
        "atualizado_em": agora,
    }
    _salvar(raiz, [item for item in itens if item.get("slug") != registro["slug"]] + [registro])
    return {
        "slug": registro["slug"],
        "nome": registro["nome"],
        "descricao": registro["descricao"],
        "url": registro["url"],
        "tamanho": registro["tamanho"],
        "novo": anterior is None,
        "tentativas": tentativas,
        "outros": [item for item in descobertos if item != achado][:8],
    }


_RE_LINK = re.compile(r"https?://[^\s,;]+")


def links_no_texto(texto: str) -> list[str]:
    """Todos os links colados, sem repetir e sem pontuação grudada no fim."""
    vistos: list[str] = []
    for bruto in _RE_LINK.findall(texto or ""):
        limpo = bruto.rstrip(").,;]>}")
        if limpo not in vistos:
            vistos.append(limpo)
    return vistos


def importar_varias(
    texto: str,
    *,
    raiz: Path | None = None,
    baixar: Baixar | None = None,
    limite: int = 10,
) -> dict[str, Any]:
    """Importa vários links de uma vez — uma lista de 100 skills vem assim.

    Falha em um link não derruba os outros: cada erro volta em `falhas`, com o
    motivo, para você corrigir o link e repetir só ele.
    """
    links = links_no_texto(texto)
    if not links:
        raise HabilidadeError("Não achei link nenhum no texto colado — mande um por linha.")
    quantos = max(1, min(int(limite), 20))
    alvos = links[:quantos]
    importadas: list[dict[str, Any]] = []
    falhas: list[dict[str, str]] = []
    usados: set[str] = set()
    for link in alvos:
        try:
            ficha = importar(link, raiz=raiz, baixar=baixar, evitar=usados)
        except HabilidadeError as exc:
            falhas.append({"url": link, "erro": str(exc)[:200]})
            continue
        # Dois arquivos chamados `SKILL.md` gerariam o mesmo slug: o segundo já
        # vem com sufixo, sem sobrescrever o primeiro.
        usados.add(ficha["slug"])
        importadas.append(ficha)
    return {
        "tentadas": len(alvos),
        "importadas": importadas,
        "falhas": falhas,
        "restantes": max(0, len(links) - len(alvos)),
        "links": links,
    }


# --------------------------------------------------------------------- usar

def guia(ref: str, *, raiz: Path | None = None, limite: int = LIMITE_GUIA) -> dict[str, Any]:
    """Devolve a habilidade para ser usada como roteiro, com a fonte."""
    achado = _achar(ref, carregar(raiz))
    if achado is None:
        raise HabilidadeError(f"Não tenho a habilidade “{ref}”. Importe com `importa a habilidade <link>`.")
    texto = achado.get("texto") or ""
    return {
        "slug": achado["slug"],
        "nome": achado.get("nome") or achado["slug"],
        "descricao": achado.get("descricao") or "",
        "url": achado.get("url") or achado.get("origem") or "",
        "texto": texto[:limite],
        "cortado": len(texto) > limite,
    }
