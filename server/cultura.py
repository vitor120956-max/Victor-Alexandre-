"""Cultura — livros completos e gratuitos, e o que fazer com eles.

O pedido: dar **cultura** ao JARVIS, com livros que ele possa ler de verdade.
Ler sem pagar e sem pirataria só tem um caminho honesto: **domínio público** (e
livros acadêmicos em acesso aberto). As fontes que prestam estão na tabela
`FONTES` — a maior é o Project Gutenberg, com o catálogo inteiro em texto puro,
sem cadastro e sem chave.

O que este módulo faz:

- **fontes** — onde baixar, o que cada site tem e qual o limite de cada um;
- **buscar** — procura o livro por título/autor (Gutendex para o Gutenberg,
  Open Library para metadados) e devolve o endereço do texto;
- **baixar** — puxa o `.txt`, tira o cabeçalho do Gutenberg e guarda na
  **biblioteca** (`storage/biblioteca`), de onde `biblioteca.buscar`,
  `biblioteca.resumir` e as demais skills já leem;
- **persona** — mede o estilo de um livro importado (tamanho de frase,
  pontuação, diálogo, vocabulário) e monta um cartão de escrita.

O limite, dito de frente: isso é **estilo**, não o autor. O cartão não inventa
citações, não escreve “como Machado” por mágica e não copia trechos longos — para
citação literal existe `biblioteca.buscar`, que aponta a seção de onde saiu.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from . import biblioteca, busca_web, dados
from .texto import todas_as_palavras

TIMEOUT = 25
MAX_LIVRO = 6 * 1024 * 1024
MAX_TEXTO_PERSONA = 600_000
ARQUIVO_PERSONAS = "personas.json"
Baixar = Callable[[str], str]


class CulturaError(ValueError):
    """Fonte desconhecida, livro sem texto livre ou download recusado."""


# ------------------------------------------------------------------- fontes

FONTES: tuple[dict[str, str], ...] = (
    {
        "id": "gutenberg",
        "nome": "Project Gutenberg",
        "url": "https://www.gutenberg.org",
        "o_que_tem": "cerca de 79 mil e-books completos, em texto puro, EPUB e HTML",
        "idiomas": "inglês, português, francês, espanhol, alemão e outros",
        "licenca": "domínio público (regra dos EUA: publicado antes de 1929)",
        "precisa": "nada — sem cadastro, sem chave, sem pagamento",
        "baixar": "sim: https://www.gutenberg.org/ebooks/<id>.txt.utf-8",
        "nota": "a maior e mais estável. Tem catálogo por API aberta (Gutendex), sem chave.",
    },
    {
        "id": "standardebooks",
        "nome": "Standard Ebooks",
        "url": "https://standardebooks.org",
        "o_que_tem": "edições revisadas de clássicos (EPUB), com tipografia e notas",
        "idiomas": "inglês (principal)",
        "licenca": "domínio público nos EUA; o trabalho editorial é CC0",
        "precisa": "nada",
        "baixar": "sim, EPUB por obra (o JARVIS lê EPUB na biblioteca)",
        "nota": "poucos títulos, mas a qualidade do texto é melhor que a média.",
    },
    {
        "id": "openlibrary",
        "nome": "Open Library / Internet Archive",
        "url": "https://openlibrary.org",
        "o_que_tem": "milhões de registros e scans de livros antigos",
        "idiomas": "todos",
        "licenca": "domínio público nos scans antigos; o resto é empréstimo",
        "precisa": "conta para emprestar livro protegido",
        "baixar": "só para obra em domínio público (o resto é leitura emprestada)",
        "nota": "melhor lugar para achar metadados e descobrir o ano da obra.",
    },
    {
        "id": "wikisource",
        "nome": "Wikisource",
        "url": "https://pt.wikisource.org",
        "o_que_tem": "textos transcritos e revisados pela comunidade, capítulo por capítulo",
        "idiomas": "português, inglês e mais dezenas",
        "licenca": "domínio público ou CC BY-SA",
        "precisa": "nada",
        "baixar": "sim (texto na página; dá para copiar ou pedir o EPUB)",
        "nota": "bom para texto em português com notas e ligações entre capítulos.",
    },
    {
        "id": "dominiopublico",
        "nome": "Domínio Público (MEC)",
        "url": "http://www.dominiopublico.gov.br",
        "o_que_tem": "obras em português: literatura, filosofia, ciências",
        "idiomas": "português",
        "licenca": "domínio público",
        "precisa": "nada",
        "baixar": "sim, PDF por obra",
        "nota": "site antigo e sem API; a busca é manual, mas o acervo em português é grande.",
    },
    {
        "id": "librivox",
        "nome": "LibriVox",
        "url": "https://librivox.org",
        "o_que_tem": "audiolivros de domínio público, lidos por voluntários",
        "idiomas": "vários",
        "licenca": "domínio público",
        "precisa": "nada",
        "baixar": "áudio, não texto",
        "nota": "serve para ouvir; para o JARVIS ler, use o texto do Gutenberg.",
    },
    {
        "id": "doab",
        "nome": "DOAB — Directory of Open Access Books",
        "url": "https://www.doabooks.org",
        "o_que_tem": "livros acadêmicos completos em acesso aberto",
        "idiomas": "inglês (principal)",
        "licenca": "Creative Commons, conforme a obra",
        "precisa": "nada",
        "baixar": "sim, PDF/EPUB no site da editora",
        "nota": "é o caminho para livro técnico e científico de graça e legal.",
    },
)

FONTES_POR_ID = {fonte["id"]: fonte for fonte in FONTES}


def fontes() -> dict[str, Any]:
    """Tabela de onde achar livro completo e gratuito — sem rede."""
    return {
        "total": len(FONTES),
        "fontes": list(FONTES),
        "recomendacao": (
            "Para texto que o JARVIS consegue ler e citar: **Project Gutenberg** "
            "(texto puro, API aberta). Em português, complemente com **Wikisource** e "
            "**Domínio Público**. Livro ainda protegido por direito autoral não entra: "
            "não existe site legal que dê o texto completo de graça."
        ),
    }


# ------------------------------------------------------------------- busca

def _json(url: str, baixar: Baixar) -> dict[str, Any]:
    texto = baixar(url)
    try:
        dados_ = json.loads(texto)
    except ValueError as exc:
        raise CulturaError("A fonte devolveu algo que não é JSON.") from exc
    if not isinstance(dados_, dict):
        raise CulturaError("A fonte devolveu um formato inesperado.")
    return dados_


def _formato_texto(formatos: dict[str, Any]) -> str:
    """Endereço do `.txt` dentro do mapa `formats` do Gutendex."""
    for chave in ("text/plain; charset=utf-8", "text/plain; charset=us-ascii", "text/plain"):
        achado = (formatos or {}).get(chave)
        if achado:
            return str(achado)
    return ""


def buscar(
    consulta: str,
    *,
    fonte: str = "gutenberg",
    idioma: str = "",
    limite: int = 5,
    baixar: Baixar | None = None,
) -> dict[str, Any]:
    """Procura livro livre por título ou autor. Sem chave em nenhuma das fontes."""
    termo = " ".join((consulta or "").split())
    if len(termo) < 2:
        raise CulturaError("Escreva o título ou o autor (pelo menos 2 letras).")
    qual = (fonte or "gutenberg").strip().lower()
    if qual not in {"gutenberg", "openlibrary"}:
        raise CulturaError(
            "Busca automática só em `gutenberg` e `openlibrary`. Veja as outras em `cultura.fontes`."
        )
    buscar_texto = baixar or busca_web.baixar_texto
    quantos = max(1, min(int(limite), 10))

    if qual == "gutenberg":
        endereco = f"https://gutendex.com/books?search={quote(termo)}"
        if idioma:
            endereco += f"&languages={quote(idioma)}"
        bruto = _json(endereco, buscar_texto)
        livros: list[dict[str, Any]] = []
        for item in (bruto.get("results") or [])[:quantos]:
            if not isinstance(item, dict):
                continue
            formatos = item.get("formats") if isinstance(item.get("formats"), dict) else {}
            livros.append(
                {
                    "id": item.get("id"),
                    "titulo": str(item.get("title") or "")[:200],
                    "autores": [str(a.get("name")) for a in (item.get("authors") or []) if isinstance(a, dict)][:3],
                    "idiomas": item.get("languages") or [],
                    "downloads": item.get("download_count") or 0,
                    "texto": _formato_texto(formatos),
                    "url": f"https://www.gutenberg.org/ebooks/{item.get('id')}" if item.get("id") else "",
                }
            )
        return {
            "fonte": "gutenberg",
            "consulta": termo,
            "total": bruto.get("count") or len(livros),
            "livros": livros,
            "dica": "Baixe com `cultura.baixar` usando o `id` (ex.: 59863) — vem o texto completo.",
        }

    endereco = f"https://openlibrary.org/search.json?q={quote(termo)}&limit={quantos}"
    if idioma:
        endereco += f"&language={quote(idioma)}"
    bruto = _json(endereco, buscar_texto)
    livros = []
    for item in (bruto.get("docs") or [])[:quantos]:
        if not isinstance(item, dict):
            continue
        livros.append(
            {
                "id": str(item.get("key") or "").rsplit("/", 1)[-1],
                "titulo": str(item.get("title") or "")[:200],
                "autores": [str(a) for a in (item.get("author_name") or [])][:3],
                "ano": item.get("first_publish_year") or "",
                "dominio_publico": bool(item.get("public_scan_b")),
                "url": f"https://openlibrary.org{item.get('key')}" if item.get("key") else "",
            }
        )
    return {
        "fonte": "openlibrary",
        "consulta": termo,
        "total": bruto.get("numFound") or len(livros),
        "livros": livros,
        "dica": "Metadados e ano. Para o texto completo de graça, procure o mesmo título no Gutenberg.",
    }


# ---------------------------------------------------------------- download

_RE_INICIO_GUTENBERG = re.compile(r"\*\*\*\s*START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*", re.I | re.S)
_RE_FIM_GUTENBERG = re.compile(r"\*\*\*\s*END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*", re.I | re.S)


def limpar_gutenberg(texto: str) -> str:
    """Tira o cabeçalho/rodapé legal do Gutenberg e deixa só a obra."""
    bruto = (texto or "").replace("\r\n", "\n")
    inicio = _RE_INICIO_GUTENBERG.search(bruto)
    if inicio:
        bruto = bruto[inicio.end():]
    fim = _RE_FIM_GUTENBERG.search(bruto)
    if fim:
        bruto = bruto[: fim.start()]
    return bruto.strip()


def _id_do_livro(livro: str) -> str:
    bruto = (livro or "").strip()
    achado = re.search(r"gutenberg\.org/(?:ebooks|files|cache/epub)/(\d+)", bruto) or re.search(r"^(\d{1,7})$", bruto)
    if not achado:
        raise CulturaError("Passe o número do livro (ex.: 59863) ou o endereço do Gutenberg.")
    return achado.group(1)


def baixar(
    livro: str,
    *,
    titulo: str = "",
    raiz: Path | None = None,
    baixar: Baixar | None = None,
    guardar: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Baixa o texto do Gutenberg e guarda na biblioteca — sem mover nem apagar nada."""
    numero = _id_do_livro(livro)
    fetch = baixar or busca_web.baixar_texto
    endereco = f"https://www.gutenberg.org/ebooks/{numero}.txt.utf-8"
    try:
        cru = fetch(endereco)
    except Exception as exc:
        raise CulturaError(f"O Gutenberg não respondeu para o livro {numero}: {exc}"[:200]) from exc
    if len(cru) > MAX_LIVRO:
        raise CulturaError("O arquivo passa de 6 MB — grande demais para importar de uma vez.")
    texto = limpar_gutenberg(cru)
    if len(texto) < 500:
        raise CulturaError("O download veio sem texto (ou é só o cabeçalho do Gutenberg).")
    if len(texto) > biblioteca.MAX_CARACTERES:
        texto = texto[: biblioteca.MAX_CARACTERES]
    nome = titulo.strip() or f"Gutenberg {numero}"
    registrar = guardar or biblioteca.importar_texto
    fonte = registrar(nome, texto, tipo="livro", origem=endereco)
    return {
        "livro": numero,
        "titulo": fonte.get("titulo") or nome,
        "slug": fonte.get("slug"),
        "caracteres": len(texto),
        "secoes": fonte.get("secoes") or 0,
        "arquivo": endereco,
        "resposta": (
            f"Guardei “{fonte.get('titulo') or nome}” na biblioteca "
            f"({format(len(texto), ',').replace(',', '.')} caracteres, {fonte.get('secoes') or '?'} seções)."
            "\n\nAgora dá para: `biblioteca.buscar` por um assunto, `biblioteca.resumir` e "
            "`cultura.persona` para medir o estilo."
        ),
    }


# ------------------------------------------------------------------ persona

def _frases_de_estilo(texto: str) -> list[str]:
    pedacos = re.split(r"(?<=[.!?…])\s+|\n{2,}", texto or "")
    return [p.strip() for p in pedacos if len(p.strip()) >= 15]


def analisar_estilo(texto: str, nome: str = "") -> dict[str, Any]:
    """Cartão de estilo medido no texto — números, não opinião."""
    limpo = (texto or "")[:MAX_TEXTO_PERSONA]
    frases = _frases_de_estilo(limpo)
    if len(frases) < 20:
        raise CulturaError("Texto curto demais para medir estilo (menos de 20 frases).")
    palavras = todas_as_palavras(limpo)
    if not palavras:
        raise CulturaError("Não achei palavra aproveitável no texto.")
    contagem: dict[str, int] = {}
    for palavra in palavras:
        contagem[palavra] = contagem.get(palavra, 0) + 1
    vocabulario = [palavra for palavra, _ in sorted(contagem.items(), key=lambda par: -par[1])[:15]]

    tamanhos = [len(p.split()) for p in frases]
    media = sum(tamanhos) / len(tamanhos)
    curtas = sum(1 for t in tamanhos if t <= 8) / len(tamanhos)
    longas = sum(1 for t in tamanhos if t >= 30) / len(tamanhos)
    por_mil = lambda marca: round(limpo.count(marca) * 1000 / max(1, len(limpo)), 1)  # noqa: E731
    falas = sum(1 for linha in limpo.split("\n") if linha.strip().startswith(("—", "–", '"', "“")))
    paragrafos = max(1, len([b for b in limpo.split("\n\n") if b.strip()]))
    eu = len(re.findall(r"\b(?:eu|meu|minha|mim)\b", limpo, re.I)) * 1000 / max(1, len(palavras))
    voce = len(re.findall(r"\b(?:você|voce|tu|teu|sua)\b", limpo, re.I)) * 1000 / max(1, len(palavras))

    if media <= 14 and curtas >= 0.25:
        tom = "direto: frase curta, ritmo rápido"
    elif media >= 26 or longas >= 0.2:
        tom = "reflexivo: período longo, subordinadas encaixadas"
    else:
        tom = "equilibrado: alterna frase curta e período médio"
    if falas / paragrafos >= 0.15:
        tom += ", com bastante diálogo"

    regras = [
        f"Frase média de {media:.0f} palavras (o livro fica entre {min(tamanhos)} e {max(tamanhos)}).",
        f"{curtas:.0%} das frases são curtas (até 8 palavras) e {longas:.0%} passam de 30 — mantenha essa proporção.",
        "Vocabulário recorrente: " + ", ".join(vocabulario[:10]) + ".",
        f"Diálogo ocupa cerca de {falas / paragrafos:.0%} dos parágrafos; use travessão para fala.",
        f"Pontuação por mil caracteres: {por_mil('?')} interrogação, {por_mil('!')} exclamação, "
        f"{por_mil(';')} ponto e vírgula, {por_mil('—')} travessão.",
        f"Primeira pessoa aparece {eu:.1f}× por mil palavras; segunda pessoa, {voce:.1f}×.",
    ]
    return {
        "nome": nome or "persona",
        "palavras": len(palavras),
        "frases": len(frases),
        "media_palavras": round(media, 1),
        "frases_curtas": round(curtas, 3),
        "frases_longas": round(longas, 3),
        "dialogo": round(falas / paragrafos, 3),
        "tom": tom,
        "vocabulario": vocabulario,
        "regras": regras,
        "limites": [
            "Isto descreve **estilo medido**, não o autor: não imita personalidade nem opinião.",
            "Não inventa citação. Para trecho literal, use `biblioteca.buscar`, que aponta a seção.",
            "Não copia trechos longos: a persona orienta como escrever, não o que reproduzir.",
        ],
    }


def _arquivo_personas(raiz: Path | None = None) -> Path:
    return (Path(raiz) if raiz else dados.raiz()) / ARQUIVO_PERSONAS


def personas(raiz: Path | None = None) -> list[dict[str, Any]]:
    try:
        bruto = json.loads(_arquivo_personas(raiz).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    itens = bruto.get("personas") if isinstance(bruto, dict) else bruto
    return [item for item in (itens or []) if isinstance(item, dict) and item.get("nome")]


def persona(
    livro: str,
    *,
    nome: str = "",
    raiz: Path | None = None,
    salvar: bool = True,
    texto: str | None = None,
) -> dict[str, Any]:
    """Mede o estilo de um livro da biblioteca (ou de um texto) e guarda o cartão."""
    if texto is None:
        fonte = biblioteca.achar(livro)
        if fonte is None:
            raise CulturaError(
                f"Não achei o livro “{livro}” na biblioteca. Importe antes com `cultura.baixar`."
            )
        texto = biblioteca.texto_completo(str(fonte.get("slug")))
        nome = nome or str(fonte.get("titulo") or "")
    cartao = analisar_estilo(texto, nome=nome or livro)
    cartao["atualizado_em"] = datetime.now(timezone.utc).isoformat()
    if salvar:
        existentes = [p for p in personas(raiz) if p.get("nome") != cartao["nome"]]
        destino = _arquivo_personas(raiz)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(
            json.dumps({"personas": [*existentes, cartao]}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        cartao["arquivo"] = str(destino)
    return cartao
