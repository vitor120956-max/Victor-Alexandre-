"""Navegador assistido — leitura de snapshots, alvos e planos.

Inspirado em citrolabs/ego-lite (MIT, 2026). Implementação própria e
determinística. Nada do upstream é instalado ou executado: não há app, binário,
SDK, skill de marketplace nem navegador. As skills leem o snapshot que você cola
(árvore de acessibilidade no estilo ego-browser/Playwright), o roteiro em
JavaScript e o log de recibos, e devolvem índice, resolução de alvo, roteiro de
rodadas, checagem de actionability, recibos e limites de consentimento.

O recorte é o que sobrevive sem navegador: o parser da árvore, a resolução de
locators, a regra de escopo (documento principal antes dos frames), a checagem
estática de padrões e o vocabulário de segurança. Nenhuma skill abre aba, clica,
preenche ou envia coisa alguma.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from .review import common, finalize, finding

MAX_SNAPSHOT = 200_000
MAX_PLANO = 40_000
MAX_LOG = 40_000
MAX_ACOES = 40_000
MAX_OBJETIVO = 2_000
MAX_NOS = 2_000
MAX_LINHAS = 120


class NavegadorError(ValueError):
    """Erro esperado do navegador assistido, seguro para o usuário."""


# --------------------------------------------------------------- vocabulário

PAPEIS_ACIONAVEIS = {
    "button", "link", "anchor", "checkbox", "radio", "textbox", "searchbox",
    "combobox", "listbox", "option", "menuitem", "menuitemcheckbox",
    "menuitemradio", "tab", "switch", "slider", "spinbutton", "treeitem",
    "textarea", "input", "upload", "file",
}
PAPEIS_ESTRUTURA = {
    "root", "container", "generic", "group", "region", "main", "navigation",
    "form", "list", "listitem", "table", "row", "cell", "text", "heading",
    "paragraph", "image", "svg_root", "canvas", "iframe", "dialog", "alert",
    "status", "banner", "contentinfo", "complementary", "article", "section",
    "separator", "progressbar", "meter", "tooltip", "figure", "caption",
    "blockquote", "code", "definition", "term", "note", "time",
}
PAPEIS = sorted(PAPEIS_ACIONAVEIS | PAPEIS_ESTRUTURA)

ACOES: dict[str, dict[str, Any]] = {
    "clicar": {"api": "click", "rotulo": True, "acionavel": True, "valor": False, "efeito": True},
    "click": {"api": "click", "rotulo": True, "acionavel": True, "valor": False, "efeito": True},
    "clicar-duplo": {"api": "dblclick", "rotulo": True, "acionavel": True, "valor": False, "efeito": True},
    "dblclick": {"api": "dblclick", "rotulo": True, "acionavel": True, "valor": False, "efeito": True},
    "pairar": {"api": "hover", "rotulo": True, "acionavel": True, "valor": False, "efeito": True},
    "hover": {"api": "hover", "rotulo": True, "acionavel": True, "valor": False, "efeito": True},
    "arrastar": {"api": "dragAndDrop", "rotulo": True, "acionavel": True, "valor": False, "efeito": True},
    "preencher": {"api": "fill", "rotulo": False, "acionavel": True, "valor": True, "efeito": True},
    "fill": {"api": "fill", "rotulo": False, "acionavel": True, "valor": True, "efeito": True},
    "selecionar": {"api": "selectOption", "rotulo": False, "acionavel": True, "valor": True, "efeito": True},
    "select": {"api": "selectOption", "rotulo": False, "acionavel": True, "valor": True, "efeito": True},
    "focar": {"api": "focus", "rotulo": False, "acionavel": True, "valor": False, "efeito": False},
    "teclar": {"api": "press", "rotulo": False, "acionavel": True, "valor": True, "efeito": True},
    "press": {"api": "press", "rotulo": False, "acionavel": True, "valor": True, "efeito": True},
    "enviar-arquivo": {"api": "setInputFiles", "rotulo": False, "acionavel": True, "valor": True, "efeito": True},
    "upload": {"api": "setInputFiles", "rotulo": False, "acionavel": True, "valor": True, "efeito": True},
    "esperar": {"api": "waitForSelector", "rotulo": False, "acionavel": False, "valor": False, "efeito": False},
    "wait": {"api": "waitForSelector", "rotulo": False, "acionavel": False, "valor": False, "efeito": False},
}

TIPOS_ALVO = {
    "ref": "referência do snapshot (@N / ref=N)",
    "texto": "texto visível (text=)",
    "papel": "papel + nome acessível (loc=role:)",
    "css": "seletor CSS (loc=css: / css=)",
    "href": "URL do link (loc=href:)",
    "xpath": "XPath",
}

ESTADOS = {
    "oculto": ("hidden", "must", "O nó está no snapshot mas não está visível.",
               "A ação falha antes de chegar ao elemento.",
               "Espere a condição observável: `await page.waitForSelector(seletor, { state: \"visible\" })`.",
               "O agente insiste no mesmo passo e queima rodadas."),
    "desabilitado": ("disabled", "must", "O controle está desabilitado.",
                     "Clique ou digitação não despacham nada.",
                     "Espere habilitar com `waitForFunction` ou escolha outro caminho na tela.",
                     "O roteiro trava sem explicar por quê."),
    "somente-leitura": ("readonly", "must", "O campo é somente leitura.",
                        "O valor preenchido não é aceito.",
                        "Encontre o campo editável equivalente ou a ação de edição.",
                        "O dado parece salvo e não foi."),
    "coberto": ("obscured", "must", "Outro elemento cobre o alvo.",
                "O clique cai no overlay.",
                "Espere o overlay sumir; `force` é último recurso e esconde o problema.",
                "O agente clica no botão errado."),
    "fora-da-viewport": ("outside viewport", "nice", "O alvo está fora da viewport.",
                          "O clique rola sozinho; pré-rolar só gasta um passo.",
                          "Não pré-role: `click`/`fill` trazem o alvo à vista.",
                          "Uma rodada inteira gasta sem necessidade."),
    "animando": ("animating", "should", "O alvo ainda está animando.",
                  "A caixa muda entre a medição e o clique.",
                  "Espere a condição de estabilidade com `waitForFunction`.",
                  "O clique erra por poucos pixels."),
    "destacado": ("detached", "must", "O nó foi substituído depois do snapshot.",
                  "A referência aponta para um nó que não existe mais.",
                  "Tire um novo snapshot e re-resolva o alvo.",
                  "A ação falha com timeout opaco."),
    "ambiguo": ("ambiguous", "must", "Mais de um nó acionável casa com o alvo.",
                "O ego-browser recusa alvo ambíguo no mesmo documento ou frame.",
                "Refine com `loc=role:button[name=\"...\"]` ou `>> nth=N`.",
                "O clique pode acertar o elemento errado."),
    "sem-ref": ("no ref", "should", "O nó não traz `ref=` no snapshot.",
                 "Não dá para agir por `@N`.",
                 "Monte o seletor por papel e nome: `loc=role:...`.",
                 "O plano precisa de um seletor que ninguém escreveu."),
    "sem-nome": ("no name", "should", "O nó acionável não tem nome acessível.",
                  "Não dá para resolver por texto ou `role[name=]`.",
                  "Use o `loc=css:` que o snapshot trouxe ou `page.evaluate()`.",
                  "O alvo fica impossível de descrever."),
}

ACAO_LABEL = {
    "click", "dblclick", "hover", "dragAndDrop",
    "mouse.click", "mouse.move", "mouse.wheel",
}


# ------------------------------------------------------------------- helpers

def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip().lower()


def _clean(value: Any, limit: int) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(char for char in text if char == "\n" or char == "\t" or char >= " ")
    return text[:limit]


def _cap(nome: str, value: Any, limit: int) -> str:
    text = _clean(value, limit + 1)
    if len(text) > limit:
        raise NavegadorError(
            "O campo {0} tem {1} caracteres; o limite desta skill é {2}. "
            "Recorte o texto e tente de novo.".format(nome, len(text), limit)
        )
    return text


def _mode(value: Any) -> str:
    modo = _norm(value)
    if modo not in {"lite", "full", "ultra"}:
        raise NavegadorError("modo deve ser lite, full ou ultra.")
    return modo


def _as_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _acao(value: Any) -> tuple[str, dict[str, Any]]:
    chave = _norm(value) or "clicar"
    if chave not in ACOES:
        raise NavegadorError(
            "acao desconhecida: {0}. Use uma de: {1}.".format(
                chave, ", ".join(sorted(ACOES))
            )
        )
    return chave, ACOES[chave]


def _to_finding(item: dict[str, str]) -> dict[str, Any]:
    dados = dict(item)
    if "ifSkipped" in dados:
        dados["if_skipped"] = dados.pop("ifSkipped")
    return finding(**dados)


def _rateio(percentual: float) -> str:
    return "{0:.0f}%".format(percentual)


# ------------------------------------------------------------------ snapshot

@dataclass
class No:
    indice: int
    linha: int
    profundidade: int
    papel: str
    nome: str
    ref: str = ""
    loc: str = ""
    url: str = ""
    attrs: dict[str, str] = field(default_factory=dict)
    quadro: list[str] = field(default_factory=list)
    pai: int | None = None

    @property
    def acionavel(self) -> bool:
        return self.papel in PAPEIS_ACIONAVEIS

    def linha_tabela(self) -> dict[str, Any]:
        return {
            "linha": self.linha,
            "papel": self.papel,
            "nome": self.nome,
            "ref": self.ref,
            "loc": self.loc,
            "url": self.url,
            "profundidade": self.profundidade,
            "quadro": " / ".join("@{}".format(item) for item in self.quadro),
            "acionavel": self.acionavel,
        }


@dataclass
class Arvore:
    nos: list[No]
    linhas: list[str]
    raiz: bool
    indentacao_estavel: bool
    texto: str

    @property
    def acionaveis(self) -> list[No]:
        return [no for no in self.nos if no.acionavel]

    @property
    def frames(self) -> list[No]:
        return [no for no in self.nos if no.papel == "iframe"]

    @property
    def refs(self) -> list[str]:
        return [no.ref for no in self.nos if no.ref]

    def por_papel(self) -> dict[str, int]:
        contagem: dict[str, int] = {}
        for no in self.nos:
            contagem[no.papel] = contagem.get(no.papel, 0) + 1
        return dict(sorted(contagem.items(), key=lambda item: (-item[1], item[0])))

    def por_ref(self, ref: str) -> No | None:
        for no in self.nos:
            if no.ref and no.ref == ref:
                return no
        return None


_LINHA = re.compile(r"^(?P<indent>[ \t]*)(?P<corpo>.+?)\s*$")
_PAPEL = re.compile(r"^(?P<papel>[A-Za-z_][\w-]*)(?P<resto>.*)$")
_NOME = re.compile(r'^\s*"((?:[^"\\]|\\.)*)"')
_CHAVE = re.compile(
    r"\b(?:ref|loc|url|level|checked|disabled|expanded|pressed|selected|"
    r"valuetext|placeholder|href|value|description)="
)


def _atributos(bloco: str) -> dict[str, str]:
    itens: list[str] = []
    buffer: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(bloco):
        char = bloco[index]
        if quote:
            if char == "\\" and index + 1 < len(bloco):
                buffer.append(char)
                index += 1
                buffer.append(bloco[index])
            elif char == quote:
                quote = None
                buffer.append(char)
            else:
                buffer.append(char)
        elif char in "\"'":
            quote = char
            buffer.append(char)
        elif char == ",":
            itens.append("".join(buffer))
            buffer = []
        else:
            buffer.append(char)
        index += 1
    itens.append("".join(buffer))
    attrs: dict[str, str] = {}
    for item in itens:
        if "=" not in item:
            continue
        chave, valor = item.split("=", 1)
        chave = chave.strip().lower()
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
            valor = valor[1:-1]
        if chave:
            attrs[chave] = valor
    return attrs


def _desescapar(valor: str) -> str:
    return valor.replace('\\"', '"').replace("\\\\", "\\")


def _bloco_meta(resto: str) -> tuple[str, str] | None:
    """Acha o bloco `[...]` que fecha a linha, respeitando colchetes aninhados."""
    texto = resto.rstrip()
    if not texto.endswith("]"):
        return None
    profundidade = 0
    for posicao in range(len(texto) - 1, -1, -1):
        char = texto[posicao]
        if char == "]":
            profundidade += 1
        elif char == "[":
            profundidade -= 1
            if profundidade == 0:
                return texto[posicao + 1 : -1], texto[:posicao]
    return None


def _quebrar(linha: str) -> tuple[str, str, dict[str, str]] | None:
    """Separa papel, nome e metadados de uma linha do snapshot.

    O nome vem antes dos metadados: um `[ref=9]` dentro das aspas do nome é
    texto do nó, não opção — a mesma distinção que o upstream faz.
    """
    corpo = linha.strip()
    if corpo.startswith("- ") or corpo.startswith("* ") or corpo.startswith("+ "):
        corpo = corpo[2:].strip()
    if not corpo:
        return None
    casamento = _PAPEL.match(corpo)
    if not casamento:
        return None
    papel = casamento.group("papel").lower()
    resto = casamento.group("resto")

    nome = ""
    casamento_nome = _NOME.match(resto)
    if casamento_nome:
        nome = _desescapar(casamento_nome.group(1))
        resto = resto[casamento_nome.end() :]
    else:
        resto = resto.lstrip()

    attrs: dict[str, str] = {}
    bloco = _bloco_meta(resto)
    if bloco is not None:
        conteudo, antes = bloco
        if _CHAVE.search(conteudo):
            attrs = _atributos(conteudo)
            resto = antes

    resto = resto.strip()
    if not nome and resto:
        nome = resto
    return papel, nome, attrs


def parse_snapshot(texto: str) -> Arvore:
    linhas = [linha for linha in texto.split("\n")]
    uteis = [linha for linha in linhas if linha.strip()]
    if not uteis:
        raise NavegadorError("O snapshot está vazio. Cole a árvore devolvida por page.snapshot().")
    if len(uteis) > MAX_NOS:
        raise NavegadorError(
            "O snapshot tem {0} linhas; o limite é {1}. Use scope: \"subtree\" no bloco "
            "que importa ou cole só a parte relevante.".format(len(uteis), MAX_NOS)
        )

    raiz = False
    estavel = True
    nos: list[No] = []
    pilha: list[tuple[int, int]] = []
    frames: list[tuple[int, str]] = []
    for numero, linha in enumerate(linhas, start=1):
        if not linha.strip():
            continue
        indent = linha[: len(linha) - len(linha.lstrip())]
        if len(indent) % 2 != 0:
            estavel = False
        profundidade = len(indent) // 2
        quebrado = _quebrar(linha)
        if quebrado is None:
            continue
        papel, nome, attrs = quebrado
        if papel == "root":
            raiz = True
        elif papel not in PAPEIS_ACIONAVEIS and papel not in PAPEIS_ESTRUTURA:
            # Papel desconhecido continua na árvore, mas não é tratado como alvo.
            pass
        while pilha and pilha[-1][0] >= profundidade:
            pilha.pop()
        pai = pilha[-1][1] if pilha else None
        while frames and frames[-1][0] >= profundidade:
            frames.pop()
        quadro = [ref for _, ref in frames]
        no = No(
            indice=len(nos),
            linha=numero,
            profundidade=profundidade,
            papel=papel,
            nome=nome,
            ref=(attrs.get("ref") or "").lstrip("@"),
            loc=attrs.get("loc") or "",
            url=attrs.get("url") or attrs.get("href") or "",
            attrs=attrs,
            quadro=quadro,
            pai=pai,
        )
        nos.append(no)
        pilha.append((profundidade, no.indice))
        if papel == "iframe" and no.ref:
            frames.append((profundidade, no.ref))
    if not nos:
        raise NavegadorError("Nenhuma linha do snapshot pôde ser lida. O formato esperado é `papel \"nome\" [ref=N, loc=...]`.")
    return Arvore(nos=nos, linhas=linhas, raiz=raiz, indentacao_estavel=estavel, texto=texto)


def _achados_snapshot(arvore: Arvore) -> list[dict[str, Any]]:
    achados: list[dict[str, Any]] = []
    vistos: dict[str, No] = {}
    repetidos: list[str] = []
    sem_ref: list[No] = []
    nome_vazio: list[No] = []
    instaveis: list[No] = []
    frames_sem_ref: list[No] = []
    for no in arvore.nos:
        if no.ref:
            if no.ref in vistos:
                repetidos.append(no.ref)
            else:
                vistos[no.ref] = no
        if no.acionavel and not no.ref:
            sem_ref.append(no)
        if no.acionavel and not no.nome:
            nome_vazio.append(no)
        if no.loc in {"unstable", "ambiguous"} or "loc=unstable" in no.loc or "loc=ambiguous" in no.loc:
            instaveis.append(no)
        if no.papel == "iframe" and not no.ref:
            frames_sem_ref.append(no)

    if repetidos:
        achados.append(_to_finding({
            "group": "must", "kind": "ref-duplicado", "title": "Referência repetida no snapshot",
            "location": "refs @" + ", @".join(sorted(set(repetidos))[:6]),
            "what": "Duas ou mais linhas anunciam a mesma referência.",
            "problem": "A ação por @N atinge só um dos nós; o outro fica inalcançável e o resultado é imprevisível.",
            "fix": "Tire um novo snapshot; se repetir, resolva esses nós por `loc=role:` com nome exato.",
            "ifSkipped": "Você age no elemento errado sem perceber.",
        }))
    if not arvore.acionaveis:
        achados.append(_to_finding({
            "group": "must", "kind": "sem-acionaveis", "title": "Nenhum alvo acionável",
            "location": "snapshot",
            "what": "A árvore só tem texto, títulos e contêineres.",
            "problem": "Não existe botão, campo ou link para uma ação semântica; o roteiro não sai do lugar.",
            "fix": "Use `page.screenshot()` com mouse/teclado, `page.evaluate()` para extrair, ou navegue até a tela que tem controles.",
            "ifSkipped": "O agente tenta clicar em texto e falha em todas as rodadas.",
        }))
    if not arvore.raiz:
        achados.append(_to_finding({
            "group": "should", "kind": "sem-raiz", "title": "Snapshot sem a linha root",
            "location": "primeira linha",
            "what": "A árvore começa direto em um nó, sem `root`.",
            "problem": "O recorte pode ser um subtree colado pela metade, e a hierarquia de frames fica implícita.",
            "fix": "Cole o snapshot inteiro, incluindo `root`, ou declare no objetivo que o recorte é um subtree.",
            "ifSkipped": "A profundidade e o frame dos nós podem estar errados.",
        }))
    if not arvore.indentacao_estavel:
        achados.append(_to_finding({
            "group": "should", "kind": "indentacao", "title": "Indentação fora do padrão",
            "location": "snapshot",
            "what": "Alguma linha tem recuo ímpar.",
            "problem": "O ego-browser usa dois espaços por nível; recuo ímpar quebra a leitura da árvore e do frame atual.",
            "fix": "Copie o snapshot cru, sem reindentar à mão.",
            "ifSkipped": "O pai e o frame de cada nó podem ser atribuídos errado.",
        }))
    if sem_ref:
        amostra = ", ".join("@{}".format(no.ref) if no.ref else no.papel + " \"" + no.nome[:24] + "\"" for no in sem_ref[:4])
        achados.append(_to_finding({
            "group": "should", "kind": "acionavel-sem-ref", "title": "Alvo acionável sem referência",
            "location": "{} nó(s): {}".format(len(sem_ref), amostra),
            "what": "Há controles na árvore sem `ref=`.",
            "problem": "Não dá para usar `@N`; sobra montar seletor por papel e nome.",
            "fix": "Monte `loc=role:<papel>[name=\"<nome>\"]` ou use o `loc=css:` que vier junto.",
            "ifSkipped": "A ação precisa adivinhar um seletor e pode acertar outro nó.",
        }))
    if instaveis:
        achados.append(_to_finding({
            "group": "should", "kind": "loc-instavel", "title": "Locator instável ou ambíguo",
            "location": "{} nó(s)".format(len(instaveis)),
            "what": "O snapshot traz `loc=unstable` ou `loc=ambiguous`.",
            "problem": "O próprio upstream remove esse locator do resultado porque ele não identifica o nó de forma única.",
            "fix": "Não reuse esse `loc=`; resolva por `@ref` enquanto o snapshot for atual ou por papel + nome.",
            "ifSkipped": "O seletor casa com outro nó depois da próxima mudança de tela.",
        }))
    if frames_sem_ref:
        achados.append(_to_finding({
            "group": "should", "kind": "iframe-sem-ref", "title": "Iframe sem referência",
            "location": "{} iframe(s)".format(len(frames_sem_ref)),
            "what": "O iframe aparece na árvore, mas sem `ref=`.",
            "problem": "Sem a referência não há `snapshot({ scope: \"subtree\", root: \"@N\" })` para focar o conteúdo do frame.",
            "fix": "Tire um snapshot de página inteira ou use `loc=` do iframe; se o conteúdo não aparecer, o frame ainda não carregou.",
            "ifSkipped": "O conteúdo do frame fica visível e inalcançável.",
        }))
    if nome_vazio:
        achados.append(_to_finding({
            "group": "nice", "kind": "sem-nome", "title": "Controle sem nome acessível",
            "location": "{} nó(s)".format(len(nome_vazio)),
            "what": "O nó é acionável, mas o nome acessível está vazio.",
            "problem": "Resolver por texto é impossível; sobra CSS, que muda com o layout.",
            "fix": "Use o `loc=css:` do snapshot ou `page.evaluate()` para localizar por atributo estável.",
            "ifSkipped": "O seletor quebra na próxima alteração de estilo.",
        }))
    if len(arvore.nos) > 300:
        achados.append(_to_finding({
            "group": "nice", "kind": "denso", "title": "Snapshot denso",
            "location": "{} nós".format(len(arvore.nos)),
            "what": "A árvore passa de 300 nós.",
            "problem": "Cada rodada carrega texto que não muda a decisão, e o custo sobe sem ganho.",
            "fix": "Peça `snapshot({ scope: \"subtree\", root: \"@N\" })` do bloco que importa, ou recorte a região relevante.",
            "ifSkipped": "O agente gasta contexto e ainda precisa de outra rodada.",
        }))
    return achados


# ----------------------------------------------------------------- snapshot skill

def read_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    modo = _mode(payload.get("modo"))
    texto = _cap("snapshot", payload.get("snapshot"), MAX_SNAPSHOT)
    if not texto.strip():
        raise NavegadorError("Cole o snapshot devolvido por `page.snapshot()`.")
    arvore = parse_snapshot(texto)
    achados = _achados_snapshot(arvore)
    com_ref = sum(1 for no in arvore.nos if no.ref)
    sem_ref = sum(1 for no in arvore.acionaveis if not no.ref)
    profundidade = max((no.profundidade for no in arvore.nos), default=0)
    papeis = arvore.por_papel()

    achados, counts, veredito, perguntas = finalize(achados, modo, [])
    extra = ["", "## Papéis", "", "| Papel | Nós |", "| --- | --- |"]
    extra += ["| {} | {} |".format(chave, valor) for chave, valor in list(papeis.items())[:16]]
    acionaveis = arvore.acionaveis[:25]
    if acionaveis:
        extra += ["", "## Alvos acionáveis", "", "| Linha | Papel | Nome | Ref | Locator |", "| --- | --- | --- | --- | --- |"]
        extra += [
            "| {0} | {1} | {2} | {3} | {4} |".format(
                no.linha, no.papel, (no.nome or "—")[:48],
                "@" + no.ref if no.ref else "—", no.loc or "—",
            )
            for no in acionaveis
        ]
    resultado = common(
        analysis="leitura de snapshot",
        mode=modo,
        title="Snapshot: {} nós, {} acionáveis".format(len(arvore.nos), len(arvore.acionaveis)),
        summary=[
            "{} nó(s), {} referência(s), {} frame(s) e profundidade {}.".format(
                len(arvore.nos), com_ref, len(arvore.frames), profundidade
            ),
            "{} acionável(is) sem `ref=`: esses só se resolvem por papel + nome ou CSS.".format(sem_ref),
            "A leitura é estática: o JARVIS não abre a página nem executa o snapshot.",
        ],
        findings=achados,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=[no.linha_tabela() for no in arvore.nos[:MAX_LINHAS]],
        metrics={
            "total": len(arvore.nos),
            "acionaveis": len(arvore.acionaveis),
            "comRef": com_ref,
            "semRef": sem_ref,
            "frames": len(arvore.frames),
            "profundidade": profundidade,
            "papelDominante": next(iter(papeis), ""),
        },
        limitations=[
            "O snapshot é uma foto do instante em que foi tirado; a página pode ter mudado.",
            "Papéis desconhecidos continuam na árvore, mas não viram alvo de ação.",
            "Nada é aberto, clicado ou preenchido por esta skill.",
        ],
        extra_sections=extra,
    )
    resultado["nos"] = resultado["rows"]
    resultado["porPapel"] = papeis
    return resultado


# --------------------------------------------------------------------- alvo

def _alvo_tipo(bruto: str) -> tuple[str, str]:
    texto = bruto.strip()
    if re.fullmatch(r"@\d+", texto):
        return "ref", texto[1:]
    casamento = re.fullmatch(r"ref=(\d+)", texto, re.I)
    if casamento:
        return "ref", casamento.group(1)
    if texto.lower().startswith("text="):
        return "texto", texto[5:]
    if texto.lower().startswith("loc=role:"):
        return "papel", texto[len("loc=role:") :]
    if texto.lower().startswith("loc=css:"):
        return "css", texto[len("loc=css:") :]
    if texto.lower().startswith("loc=href:"):
        return "href", texto[len("loc=href:") :]
    if texto.lower().startswith("css="):
        return "css", texto[4:]
    if texto.lower().startswith("xpath=") or texto.lower().startswith("//"):
        return "xpath", texto
    if texto.startswith("#") or texto.startswith(".") or texto.startswith("["):
        return "css", texto
    if texto.lower().startswith("loc="):
        raise NavegadorError(
            "locator não suportado: {0}. Use loc=css:, loc=role: ou loc=href:.".format(texto)
        )
    return "texto", texto


def _sem_nth(texto: str) -> tuple[str, int | None]:
    casamento = re.search(r">>\s*nth=(-?\d+)\s*$", texto)
    if not casamento:
        return texto, None
    return texto[: casamento.start()].rstrip(), int(casamento.group(1))


def _filtro_papel(resto: str) -> tuple[str, str, str]:
    """Devolve (papel, modo, valor) de `button[name='X']`."""
    casamento = re.match(r"^(?P<papel>[A-Za-z_][\w-]*)(?:\[(?P<filtro>.*)\])?$", resto)
    if not casamento:
        raise NavegadorError(
            "loc=role inválido: {0}. Use `loc=role:button` ou `loc=role:button[name=\"Entrar\"]`.".format(resto)
        )
    papel = casamento.group("papel").lower()
    filtro = casamento.group("filtro")
    if filtro is None:
        return papel, "", ""
    nome = re.match(r"""^name(?P<estrela>\*?)=\s*(?P<quote>['"])(?P<valor>.*)(?P=quote)$""", filtro.strip())
    if not nome:
        raise NavegadorError(
            "filtro suportado em loc=role: apenas `[name=\"...\"]` e `[name*=\"...\"]`."
        )
    return papel, "*" if nome.group("estrela") else "=", nome.group("valor")


def _texto_alvo(valor: str) -> tuple[str, bool]:
    valor = valor.strip()
    if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
        return valor[1:-1], True
    return valor, False


def _candidatos(arvore: Arvore, tipo: str, valor: str) -> list[No]:
    if tipo == "ref":
        no = arvore.por_ref(valor)
        return [no] if no else []
    if tipo == "texto":
        alvo, exato = _texto_alvo(valor)
        if not alvo:
            raise NavegadorError("Alvo de texto vazio. Escreva `text=\"Salvar\"` ou o texto desejado.")
        if exato:
            return [no for no in arvore.nos if no.nome == alvo]
        alvo_norm = _norm(alvo)
        return [no for no in arvore.nos if alvo_norm in _norm(no.nome)]
    if tipo == "papel":
        papel, modo, nome = _filtro_papel(valor)
        if papel not in PAPEIS:
            raise NavegadorError(
                "papel desconhecido: {0}. Papéis comuns: button, link, textbox, checkbox.".format(papel)
            )
        if modo == "=":
            return [no for no in arvore.nos if no.papel == papel and no.nome == nome]
        if modo == "*":
            nome_norm = _norm(nome)
            return [no for no in arvore.nos if no.papel == papel and nome_norm in _norm(no.nome)]
        return [no for no in arvore.nos if no.papel == papel]
    if tipo == "css":
        seletor = valor.strip()
        seletor = seletor[4:] if seletor.lower().startswith("css=") else seletor
        if not seletor:
            raise NavegadorError("Seletor CSS vazio.")
        exatos = [no for no in arvore.nos if no.loc and no.loc == seletor]
        if exatos:
            return exatos
        sem_prefixo = [no for no in arvore.nos if no.loc and no.loc == "css:" + seletor]
        return sem_prefixo
    if tipo == "href":
        alvo = valor.strip()
        return [no for no in arvore.nos if no.url and alvo in no.url]
    if tipo == "xpath":
        raise NavegadorError(
            "XPath não é avaliável a partir do snapshot de texto. Use `@ref` enquanto o snapshot "
            "for atual ou `loc=role:`/`loc=css:`; `page.evaluate()` é a saída documentada."
        )
    return []


def _sugestoes(arvore: Arvore, termo: str, limite: int = 3) -> list[dict[str, str]]:
    alvo = _norm(termo)
    fichas = [palavra for palavra in re.split(r"[^a-z0-9]+", alvo) if len(palavra) > 3]
    pontuados: list[tuple[int, No]] = []
    for no in arvore.acionaveis:
        nome = _norm(no.nome)
        if not nome:
            continue
        pontos = sum(1 for palavra in fichas if palavra in nome)
        if pontos:
            pontuados.append((pontos, no))
    pontuados.sort(key=lambda item: (-item[0], item[1].indice))
    sugestoes: list[dict[str, str]] = []
    for _, no in pontuados[:limite]:
        seletor = "loc=role:{}[name={}]".format(no.papel, json.dumps(no.nome))
        sugestoes.append({"ref": no.ref, "papel": no.papel, "nome": no.nome, "seletor": seletor})
    return sugestoes


def _comando(api: str, seletor: str, valor: str, rotulo: str, acao: dict[str, Any]) -> str:
    alvo = json.dumps(seletor, ensure_ascii=False)
    if api == "waitForSelector":
        return "await page.waitForSelector({0}, {{ state: \"visible\" }});".format(alvo)
    if api in {"fill", "press", "selectOption", "setInputFiles"}:
        conteudo = json.dumps(valor, ensure_ascii=False) if valor else "\"<valor>\""
        return "await page.{0}({1}, {2});".format(api, alvo, conteudo)
    if api in {"click", "dblclick", "hover"}:
        extras = ""
        if rotulo and acao.get("rotulo"):
            extras = ", {{ label: {0} }}".format(json.dumps(rotulo, ensure_ascii=False))
        return "await page.{0}({1}{2});".format(api, alvo, extras)
    if api == "dragAndDrop":
        return "await page.dragAndDrop({0}, \"<destino>\");".format(alvo)
    return "await page.{0}({1});".format(api, alvo)


def resolver_alvo(payload: dict[str, Any]) -> dict[str, Any]:
    modo = _mode(payload.get("modo"))
    texto = _cap("snapshot", payload.get("snapshot"), MAX_SNAPSHOT)
    bruto = _cap("alvo", payload.get("alvo"), 400).strip()
    if not bruto:
        raise NavegadorError("Informe o alvo: `@21`, `text=\"Salvar\"`, `loc=role:button[name=\"Entrar\"]` ou `loc=css:#email`.")
    chave, acao = _acao(payload.get("acao"))
    valor = _cap("valor", payload.get("valor"), 400)
    rotulo = _cap("rotulo", payload.get("rotulo"), 120).strip()
    arvore = parse_snapshot(texto)
    achados = _achados_snapshot(arvore)

    bruto, nth = _sem_nth(bruto)
    tipo, valor_alvo = _alvo_tipo(bruto)
    todos = _candidatos(arvore, tipo, valor_alvo)

    encontrados = todos
    escopo = "documento principal"
    ignorados: list[No] = []
    if acao["acionavel"] and tipo != "ref":
        acionaveis = [no for no in todos if no.acionavel]
        if acionaveis:
            no_topo = [no for no in acionaveis if not no.quadro]
            no_frame = [no for no in acionaveis if no.quadro]
            if no_topo:
                encontrados = no_topo
                ignorados = no_frame
            else:
                encontrados = no_frame
                escopo = "frame"
    if nth is not None and encontrados:
        if nth == -1:
            encontrados = encontrados[-1:]
        elif 0 <= nth < len(encontrados):
            encontrados = encontrados[nth : nth + 1]
        else:
            encontrados = []
            achados.append(_to_finding({
                "group": "must", "kind": "nth-fora", "title": "Índice fora do intervalo",
                "location": bruto,
                "what": "O `>> nth=N` aponta para uma posição que não existe entre os nós encontrados.",
                "problem": "O comando não tem alvo.",
                "fix": "Reveja os candidatos e escolha um índice válido.",
                "ifSkipped": "A ação falha antes de despachar.",
            }))

    ambiguo = len(encontrados) > 1
    escolhido = encontrados[0] if len(encontrados) == 1 else None
    bloqueado = escolhido if (escolhido is not None and acao["acionavel"] and not escolhido.acionavel) else None
    if bloqueado is not None:
        escolhido = None
    if escolhido is not None:
        escopo = "frame @" + escolhido.quadro[-1] if escolhido.quadro else "documento principal"
    acionavel = bool(escolhido and escolhido.acionavel)
    if bloqueado is not None:
        achados.append(_to_finding({
            "group": "must", "kind": "nao-acionavel", "title": "Alvo não é acionável",
            "location": "{} \"{}\"".format(bloqueado.papel, bloqueado.nome[:40]),
            "what": "O nó existe, mas o papel `{}` não recebe clique nem digitação.".format(bloqueado.papel),
            "problem": "A ação não despacha e o agente interpreta como falha de tempo.",
            "fix": "Resolva o controle filho (button, link, textbox) ou use `page.evaluate()` para o texto.",
            "ifSkipped": "O roteiro insiste numa linha que nunca funciona.",
        }))
    if ambiguo:
        refs = ", ".join("@" + no.ref if no.ref else no.papel for no in encontrados[:6])
        achados.append(_to_finding({
            "group": "must", "kind": "ambiguo", "title": "Mais de um alvo casa",
            "location": bruto,
            "what": "{} nós atendem ao mesmo locator ({}).".format(len(encontrados), refs),
            "problem": "O ego-browser recusa alvo ambíguo no mesmo documento ou frame; a ação não escolhe por conta própria.",
            "fix": "Use `@ref`, inclua o nome exato em `loc=role:` ou selecione com `>> nth=N`.",
            "ifSkipped": "O clique pode cair no nó errado.",
        }))
    if not encontrados:
        achados.append(_to_finding({
            "group": "must", "kind": "nao-encontrado", "title": "Alvo não encontrado",
            "location": bruto,
            "what": "Nenhum nó do snapshot casa com o locator.",
            "problem": "A referência pode estar velha ou o texto pode ter mudado.",
            "fix": "Tire um novo snapshot, confira o nome acessível e tente `loc=role:` com o nome exato.",
            "ifSkipped": "A ação falha sem dizer se o elemento sumiu ou se o seletor está errado.",
        }))
        if tipo == "ref":
            achados.append(_to_finding({
                "group": "should", "kind": "ref-velha", "title": "Referência de um snapshot anterior",
                "location": bruto,
                "what": "A ref não existe nesta árvore.",
                "problem": "O ego-browser invalida refs quando a página muda; cada snapshot renumera os nós.",
                "fix": "Use o snapshot mais recente e resolva por `loc=role:` quando a ação precisa sobreviver a mudanças.",
                "ifSkipped": "O agente repete o mesmo @N para sempre.",
            }))
        sugestoes = _sugestoes(arvore, valor_alvo)
    else:
        sugestoes = []

    if rotulo and not acao["rotulo"]:
        achados.append(_to_finding({
            "group": "must", "kind": "rotulo-proibido", "title": "Ação sem rótulo de cursor",
            "location": chave,
            "what": "Você passou `rotulo`, mas `{}` não aceita `label`.".format(acao["api"]),
            "problem": "O upstream documenta `label` só para click, dblclick, hover, dragAndDrop, mouse.click, mouse.move e mouse.wheel.",
            "fix": "Remova o rótulo ou use uma ação de ponteiro que o aceite.",
            "ifSkipped": "O script quebra na validação de opções.",
        }))
    elif rotulo:
        palavras = len(re.findall(r"[\wÀ-ÿ]+", rotulo))
        if palavras > 6:
            achados.append(_to_finding({
                "group": "nice", "kind": "rotulo-longo", "title": "Rótulo acima de seis palavras",
                "location": chave,
                "what": "O rótulo tem {} palavras.".format(palavras),
                "problem": "O texto aparece ao lado do cursor; acima de seis palavras ele cobre a tela e some do contexto.",
                "fix": "Resuma em 3 a 6 palavras no infinitivo (\"abrir detalhes\", \"enviar formulário\").",
                "ifSkipped": "A legenda do cursor deixa de ajudar quem está assistindo.",
            }))

    seletor = ""
    if escolhido:
        seletor = "@" + escolhido.ref if escolhido.ref else bruto
    comando = _comando(acao["api"], seletor, valor, rotulo, acao) if seletor else ""

    achados, counts, veredito, perguntas = finalize(achados, modo, [])
    linhas = [
        {"passo": "tipo", "valor": TIPOS_ALVO.get(tipo, tipo)},
        {"passo": "escopo", "valor": escopo},
        {"passo": "encontrados", "valor": len(encontrados)},
        {"passo": "escolhido", "valor": ("{} \"{}\"".format(escolhido.papel, escolhido.nome[:48]) if escolhido else "—")},
        {"passo": "ref", "valor": escolhido.ref if escolhido else "—"},
        {"passo": "loc", "valor": escolhido.loc if escolhido and escolhido.loc else "—"},
    ]
    extra = [
        "",
        "## Resolução",
        "",
        "- **Tipo:** {}".format(TIPOS_ALVO.get(tipo, tipo)),
        "- **Escopo:** {}".format(escopo),
        "- **Candidatos acionáveis:** {}".format(len(encontrados)),
    ]
    if escolhido:
        extra += [
            "- **Escolhido:** {} \"{}\"".format(escolhido.papel, escolhido.nome),
            "- **Referência:** {}".format("@" + escolhido.ref if escolhido.ref else "sem ref"),
            "- **Comando:** `{}`".format(comando),
        ]
    if ignorados:
        extra += ["- **Frames ignorados:** {} (o documento principal tinha correspondência)".format(len(ignorados))]
    if sugestoes:
        extra += ["", "## Candidatos próximos", ""]
        extra += ["- {} \"{}\" → `{}`".format(item["papel"], item["nome"], item["seletor"]) for item in sugestoes]
    resultado = common(
        analysis="resolução de alvo",
        mode=modo,
        title="Alvo: {}".format(bruto),
        summary=[
            "{} nó(s) casam com o locator no {}.".format(len(encontrados), escopo)
            if encontrados
            else "Nenhum nó do snapshot casa com `{}`.".format(bruto),
            "A resolução é estática: o JARVIS lê o snapshot colado e não abre a página.",
        ],
        findings=achados,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=linhas,
        metrics={
            "tipo": tipo,
            "escopo": escopo,
            "candidatos": len(encontrados),
            "ambiguo": ambiguo,
            "resolvido": bool(escolhido),
            "acionavel": acionavel,
            "ref": escolhido.ref if escolhido else "",
            "comando": comando,
        },
        limitations=[
            "O snapshot é uma foto: se a página mudou depois dele, o alvo pode não existir mais.",
            "Não há avaliação de CSS, XPath ou shadow DOM aqui: só o que o snapshot declarou.",
            "Quem executa o comando é o seu agente, no ego-browser; esta skill não abre navegador.",
        ],
        extra_sections=extra,
    )
    resultado["candidatos"] = [no.linha_tabela() for no in encontrados[:MAX_LINHAS]]
    resultado["sugestoes"] = sugestoes
    resultado["comando"] = comando
    return resultado


# ------------------------------------------------------------------ roteiro

INTENCOES = (
    ("abrir", r"\b(abrir|abre|acessar|acesse|ir para|navegar|visitar|entrar no site|consultar)\b"),
    ("buscar", r"\b(buscar|busque|pesquisar|pesquise|procurar|filtrar|encontrar)\b"),
    ("preencher", r"\b(preencher|preencha|digitar|digite|escrever|inserir|informar|enviar formul)\b"),
    ("clicar", r"\b(clicar|clique|apertar|selecionar|escolher|marcar|assinar)\b"),
    ("extrair", r"\b(extrair|coletar|listar|copiar|raspar|obter|comparar|preços?)\b"),
    ("baixar", r"\b(baixar|download|salvar arquivo|exportar)\b"),
    ("enviar-arquivo", r"\b(enviar arquivo|upload|anexar|subir arquivo)\b"),
    ("concluir", r"\b(agendar|reservar|marcar horário|finalizar|concluir|comprar|pagar)\b"),
)

RISCO_ALTO = re.compile(
    r"\b(pague|pagar|compre|comprar|checkout|pix|transferir|transferência|sacar|"
    r"boleto|cartão|assinatura|assinar|excluir|apagar|deletar|remover conta|"
    r"publicar|publicar|postar|comentar|enviar mensagem|curtir|seguir|"
    r"cancelar|contratar|apostar|investir)\b",
    re.I,
)


def _intencoes(objetivo: str) -> list[str]:
    alvo = _norm(objetivo)
    achadas = [nome for nome, padrao in INTENCOES if re.search(padrao, alvo)]
    return achadas or ["abrir"]


def _slug(texto: str, limite: int = 40) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", _norm(texto)).strip("-")
    if len(base) > limite:
        corte = base[:limite].rsplit("-", 1)[0]
        base = corte or base[:limite]
    return base.strip("-") or "tarefa"


def _js(valor: str) -> str:
    return json.dumps(valor, ensure_ascii=False)


def _url_valida(valor: str) -> bool:
    if not valor:
        return True
    parsed = urlparse(valor)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def montar_roteiro(payload: dict[str, Any]) -> dict[str, Any]:
    modo = _mode(payload.get("modo"))
    objetivo = _cap("objetivo", payload.get("objetivo"), MAX_OBJETIVO).strip()
    if len(objetivo) < 4:
        raise NavegadorError("Descreva o objetivo em uma frase: o que deve estar verdadeiro no fim?")
    url = _cap("url", payload.get("url"), 2_000).strip()
    if url and not _url_valida(url):
        raise NavegadorError("url deve começar com http:// ou https:// e ter um domínio.")
    orcamento = _as_int(payload.get("orcamento"), 4, 2, 8)
    texto_snapshot = _cap("snapshot", payload.get("snapshot"), MAX_SNAPSHOT)
    arvore = parse_snapshot(texto_snapshot) if texto_snapshot.strip() else None
    achados = _achados_snapshot(arvore) if arvore else []
    intencoes = _intencoes(objetivo)
    space = _slug(objetivo)
    dia = _cap("dia", payload.get("dia"), 20).strip() or "20261023"
    nome_space = "{}-{}".format(space, dia)[:60]
    risco = bool(RISCO_ALTO.search(objetivo))

    if not arvore:
        achados.append(_to_finding({
            "group": "should", "kind": "sem-snapshot", "title": "Roteiro sem snapshot",
            "location": "rodada 2",
            "what": "Você pediu o roteiro sem colar a árvore da página.",
            "problem": "Sem os nós, a rodada de ação não tem alvo: só resta um passo de localização.",
            "fix": "Rode a rodada 1, cole o snapshot e peça o roteiro de novo para receber os alvos resolvidos.",
            "ifSkipped": "O agente precisa de uma rodada extra só para descobrir o que clicar.",
        }))
    if not url:
        achados.append(_to_finding({
            "group": "should", "kind": "sem-url", "title": "Roteiro sem URL",
            "location": "rodada 1",
            "what": "A tarefa não declara a página de partida.",
            "problem": "Uma space nova começa em branco; `p1` precisa de um `goto` com endereço real.",
            "fix": "Informe a URL de partida; se a tarefa continua uma página já aberta, use a space existente.",
            "ifSkipped": "A primeira rodada abre uma aba vazia e gasta o orçamento.",
        }))

    rodadas: list[dict[str, Any]] = []
    abertura = [
        "// Rodada 1 — abrir e observar",
        "const task = await taskSpace({});".format(_js(nome_space)),
        "const page = task.page(\"p1\");",
    ]
    if url:
        abertura.append("await page.goto({0});".format(_js(url)))
    else:
        abertura.append("await page.goto(\"<url da tarefa>\");")
    abertura += [
        "console.log({ spaceId: task.spaceId, page: page.label });",
        "console.log(await page.snapshot()); // último: vira a vista da próxima rodada",
    ]
    rodadas.append({
        "numero": 1,
        "titulo": "Abrir e observar",
        "objetivo": "Criar a space do objetivo, abrir a página e terminar com o snapshot.",
        "codigo": "\n".join(abertura),
        "acoes": [
            {"passo": 1, "acao": "taskSpace", "alvo": nome_space, "espera": "", "risco": "livre"},
            {"passo": 2, "acao": "goto", "alvo": url or "<url>", "espera": "", "risco": "livre"},
            {"passo": 3, "acao": "snapshot", "alvo": "página", "espera": "", "risco": "livre"},
        ],
        "observacao": "Uma space por objetivo. O nome é único: reabrir com o mesmo nome retoma a space em vez de criar outra.",
    })

    # Rodada 2 — agir.
    passos: list[dict[str, Any]] = []
    codigo_acao = [
        "// Rodada 2 — agir sobre o snapshot da rodada 1",
        "const SPACE_ID = 7; // troque pelo spaceId impresso na rodada 1",
        "const task = await taskSpace(SPACE_ID);",
        "const page = task.page(\"p1\");",
    ]
    if arvore:
        campos = [no for no in arvore.acionaveis if no.papel in {"textbox", "searchbox", "combobox"}]
        botoes = [no for no in arvore.acionaveis if no.papel in {"button", "link", "anchor", "menuitem", "tab"}]
        alvo_norm = _norm(objetivo)
        if "preencher" in intencoes or "buscar" in intencoes:
            campo = campos[0] if campos else None
            if campo:
                seletor = "@" + campo.ref if campo.ref else "loc=role:{0}[name={1}]".format(campo.papel, _js(campo.nome))
                codigo_acao.append(
                    "await page.fill({0}, \"<valor real>\", {{ clearFirst: true }}); // {1}".format(
                        _js(seletor), campo.nome[:48] or campo.papel
                    )
                )
                passos.append({"passo": 1, "acao": "fill", "alvo": seletor, "espera": "", "risco": "livre"})
            else:
                codigo_acao.append("// Nenhum campo de texto no snapshot: localize o campo na tela ou use evaluate().")
        candidato = None
        melhor = 0
        for no in botoes:
            nome = _norm(no.nome)
            if not nome:
                continue
            pontos = sum(1 for palavra in re.split(r"[^a-z0-9]+", alvo_norm) if len(palavra) > 3 and palavra in nome)
            if pontos > melhor:
                melhor, candidato = pontos, no
        if candidato is not None:
            seletor = "@" + candidato.ref if candidato.ref else "loc=role:{0}[name={1}]".format(candidato.papel, _js(candidato.nome))
            codigo_acao.append(
                "await page.click({0}, {{ label: {1} }});".format(_js(seletor), _js(_rotulo_curto(candidato.nome or "avançar")))
            )
            passos.append({"passo": len(passos) + 1, "acao": "click", "alvo": seletor, "espera": "", "risco": "livre"})
        elif "extrair" in intencoes:
            codigo_acao += [
                "const dados = await page.evaluate(({ selector, limit }) =>",
                "  [...document.querySelectorAll(selector)].slice(0, limit).map((node) => node.textContent?.trim()),",
                "  { selector: \"<seletor do bloco>\", limit: 20 },",
                ");",
                "console.log(dados);",
            ]
            passos.append({"passo": len(passos) + 1, "acao": "evaluate", "alvo": "<seletor do bloco>", "espera": "", "risco": "livre"})
        elif "baixar" in intencoes:
            codigo_acao += [
                "const espera = page.waitForEvent(\"download\", { timeout: 30000 }); // arme antes do clique",
                "await page.click(\"<botão de download>\");",
                "const download = await espera;",
                "await download.saveAs(\"/caminho/absoluto/relatorio.pdf\");",
            ]
            passos.append({"passo": len(passos) + 1, "acao": "download", "alvo": "<botão de download>", "espera": "waitForEvent", "risco": "livre"})
    if not passos:
        codigo_acao += [
            "// Localize o alvo no snapshot e troque o seletor abaixo.",
            "await page.click(\"loc=role:button[name=\\\"<nome do botão>\\\"]\", { label: \"avancar a tarefa\" });",
        ]
        passos.append({"passo": 1, "acao": "localizar", "alvo": "snapshot", "espera": "", "risco": "livre"})
    if risco:
        passos.append({"passo": len(passos) + 1, "acao": "confirmar", "alvo": "usuário", "espera": "", "risco": "alto"})
        codigo_acao += [
            "// Esta tarefa envolve pagamento, exclusão, publicação ou envio: pare aqui.",
            "// await task.handOff(); // devolve o controle e explique o que falta",
        ]
    codigo_acao += [
        "await page.waitForLoadState(\"load\");",
        "console.log(await page.snapshot()); // observação da rodada, não prova de resultado",
    ]
    rodadas.append({
        "numero": 2,
        "titulo": "Agir",
        "objetivo": "Executar os passos na mesma space e terminar com uma observação.",
        "codigo": "\n".join(codigo_acao),
        "acoes": passos,
        "observacao": "Cada rodada é um processo novo: as variáveis somem, a space e os rótulos de página ficam.",
    })

    # Rodada 3 — verificar e fechar.
    codigo_fim = [
        "// Rodada 3 — verificar e fechar",
        "const SPACE_ID = 7; // o mesmo da rodada 1",
        "const task = await taskSpace(SPACE_ID);",
        "const page = task.page(\"p1\");",
        "await page.waitForSelector(\"<seletor do estado final>\", { state: \"visible\" });",
        "console.log(await page.title());",
        "await task.finish({ keep: [] }); // uma vez, por último",
    ]
    rodadas.append({
        "numero": 3,
        "titulo": "Verificar e fechar",
        "objetivo": "Conferir o estado final por uma condição observável e encerrar a space.",
        "codigo": "\n".join(codigo_fim),
        "acoes": [
            {"passo": 1, "acao": "waitForSelector", "alvo": "<estado final>", "espera": "visible", "risco": "livre"},
            {"passo": 2, "acao": "finish", "alvo": "keep=[]", "espera": "", "risco": "livre"},
        ],
        "observacao": "`finish` encerra a space e todos os rótulos, inclusive os mantidos. Chame uma vez só.",
    })

    estimativa = len(rodadas)
    if estimativa > orcamento:
        achados.append(_to_finding({
            "group": "must", "kind": "orcamento", "title": "Orçamento de rodadas insuficiente",
            "location": "planejamento",
            "what": "O roteiro precisa de {} rodadas; o orçamento é {}.".format(estimativa, orcamento),
            "problem": "Vai faltar rodada para verificar ou fechar, e a tarefa termina com a space aberta.",
            "fix": "Aumente o orçamento para {} ou junte ações na mesma rodada.".format(estimativa),
            "ifSkipped": "O agente corta a verificação e reporta um resultado que não conferiu.",
        }))

    achados, counts, veredito, perguntas = finalize(achados, modo, [])
    extra = ["", "## Rodadas", ""]
    for rodada in rodadas:
        extra += [
            "### Rodada {} — {}".format(rodada["numero"], rodada["titulo"]),
            "",
            "```js",
            rodada["codigo"],
            "```",
            "",
        ]
    if risco:
        extra += [
            "## Confirmação humana",
            "",
            "A tarefa contém verbo de risco (pagamento, exclusão, publicação ou envio). "
            "O roteiro para no ponto de confirmação e devolve o controle com `task.handOff()`.",
            "",
        ]
    resultado = common(
        analysis="roteiro de rodadas",
        mode=modo,
        title="Roteiro: {}".format(objetivo[:70]),
        summary=[
            "Objetivo: **{}**. Intenções lidas: {}.".format(objetivo, ", ".join(intencoes)),
            "{} rodada(s) para um orçamento de {}. Uma space, uma página e uma observação por rodada.".format(
                estimativa, orcamento
            ),
            "O JARVIS não executa: o script é para o seu agente no ego-browser.",
        ],
        findings=achados,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=[
            {"rodada": rodada["numero"], "titulo": rodada["titulo"], "passos": len(rodada["acoes"]), "objetivo": rodada["objetivo"]}
            for rodada in rodadas
        ],
        metrics={
            "rodadas": estimativa,
            "orcamento": orcamento,
            "space": nome_space,
            "intencoes": intencoes,
            "risco": "alto" if risco else "baixo",
            "passos": sum(len(rodada["acoes"]) for rodada in rodadas),
        },
        limitations=[
            "O roteiro é uma proposta: o agente precisa preencher `<...>` com dados reais e conferir o snapshot.",
            "Sem snapshot, a rodada de ação fica sem alvos resolvidos.",
            "Nenhum comando foi executado e nenhuma página foi aberta por esta skill.",
        ],
        extra_sections=extra,
    )
    resultado["rodadas"] = rodadas
    resultado["exigeConfirmacao"] = risco
    return resultado


def _rotulo_curto(texto: str) -> str:
    palavras = re.findall(r"[\wÀ-ÿ]+", texto)
    escolhidas = palavras[:3] or ["avançar"]
    return " ".join(escolhida.lower() for escolhida in escolhidas)


# ----------------------------------------------------------------- checagem

PADROES: tuple[dict[str, Any], ...] = (
    {
        "id": "espera-fixa", "grupo": "should",
        "padrao": r"waitForTimeout\s*\(",
        "titulo": "Espera fixa no lugar de condição",
        "o_que": "O plano usa `waitForTimeout` para esperar a página.",
        "problema": "Tempo fixo não garante que o estado chegou: ou espera demais, ou clica cedo.",
        "correcao": "Use `waitForURL`, `waitForSelector` ou `waitForFunction` com a condição real.",
        "se_ignorar": "A rodada falha de forma intermitente e o agente repete o passo.",
    },
    {
        "id": "duas-superficies", "grupo": "nice",
        "padrao": r"screenshot\s*\(",
        "companheiro": r"snapshot\s*\(",
        "janela": 15,
        "titulo": "Snapshot e screenshot na mesma rodada",
        "o_que": "O plano pede as duas superfícies de observação.",
        "problema": "Cada observação custa contexto; na maioria das telas basta o snapshot.",
        "correcao": "Escolha a mais barata que responde à pergunta: semântica para alvo, imagem para visual.",
        "se_ignorar": "A rodada fica lenta e cara sem decidir melhor.",
    },
    {
        "id": "space-nova", "grupo": "must",
        "padrao": r"taskSpace\s*\(\s*[\"']",
        "contar": 2,
        "titulo": "Mais de uma space no mesmo roteiro",
        "o_que": "O plano cria uma segunda space.",
        "problema": "Recuperar de página travada criando space nova perde o contexto e contraria a regra de uma space por objetivo.",
        "correcao": "Retome a mesma space pelo `spaceId` e recarregue ou feche a página dentro dela.",
        "se_ignorar": "O trabalho fica espalhado em spaces diferentes e ninguém sabe qual é a boa.",
    },
    {
        "id": "pagina-por-url", "grupo": "should",
        "padrao": r"newPage\s*\(",
        "contar": 2,
        "companheiro": r"goto\s*\(",
        "titulo": "Página nova para cada URL",
        "o_que": "O plano cria páginas além da `p1`.",
        "problema": "Cada página consome o orçamento e o rótulo; a mesma `p1` navega com `goto`.",
        "correcao": "Reuse `p1` com `goto` e abra outra página só quando duas telas precisam ficar abertas.",
        "se_ignorar": "O orçamento de páginas estoura no meio da tarefa.",
    },
    {
        "id": "finish-duplo", "grupo": "must",
        "padrao": r"finish\s*\(",
        "contar": 2,
        "titulo": "Fechamento repetido",
        "o_que": "O plano chama `finish()` mais de uma vez.",
        "problema": "A segunda chamada opera uma space já encerrada e falha.",
        "correcao": "Chame uma vez, por último, e não toque em página depois.",
        "se_ignorar": "O erro aparece no fim e esconde o resultado da tarefa.",
    },
    {
        "id": "finish-cedo", "grupo": "must",
        "padrao": r"finish\s*\(",
        "depois": r"page\.[a-zA-Z]+\s*\(",
        "titulo": "Ação depois do fechamento",
        "o_que": "Há chamada de página depois do `finish()`.",
        "problema": "A space e os rótulos já foram encerrados.",
        "correcao": "Mova o `finish()` para a última linha da última rodada.",
        "se_ignorar": "A última ação falha e o resultado se perde.",
    },
    {
        "id": "rotulo-proibido", "grupo": "must",
        "padrao": r"\.(fill|press|focus|selectOption|setInputFiles|waitForSelector)\s*\([^;\n]*label\s*:",
        "titulo": "`label` em ação que não aceita",
        "o_que": "Uma ação sem ponteiro recebeu a opção `label`.",
        "problema": "Só click, dblclick, hover, dragAndDrop e mouse.* aceitam `label`.",
        "correcao": "Remova a opção; o rótulo é do cursor, não do campo.",
        "se_ignorar": "A validação de opções rejeita a chamada.",
    },
    {
        "id": "rotulo-longo", "grupo": "nice",
        "padrao": r"label\s*:\s*[\"']([^\"']{46,})[\"']",
        "titulo": "Rótulo de cursor longo",
        "o_que": "O texto do `label` passa de seis palavras.",
        "problema": "A legenda cobre a tela e perde a função de orientar quem assiste.",
        "correcao": "Resuma em 3 a 6 palavras.",
        "se_ignorar": "O rótulo atrapalha mais do que explica.",
    },
    {
        "id": "playwright", "grupo": "must",
        "padrao": r"(?:from\s+[\"']playwright|require\(\s*[\"']playwright|chromium\.launch)",
        "titulo": "Playwright no roteiro",
        "o_que": "O plano importa ou lança Playwright.",
        "problema": "O ego-browser expõe uma API própria; não é Playwright e não abre navegador paralelo.",
        "correcao": "Use só TaskSpace, Page, FileChooser, mouse e keyboard documentados.",
        "se_ignorar": "O script não roda ou abre um navegador concorrente.",
    },
    {
        "id": "env", "grupo": "should",
        "padrao": r"process\.env",
        "titulo": "Dependência de ambiente do shell",
        "o_que": "O roteiro lê `process.env`.",
        "problema": "O processo do ego-browser não herda as variáveis exportadas no seu shell.",
        "correcao": "Escreva o valor no próprio script ou leia de um arquivo com caminho absoluto.",
        "se_ignorar": "O valor chega vazio e a ação usa placeholder.",
    },
    {
        "id": "caminho-relativo", "grupo": "must",
        "padrao": r"path\s*:\s*[\"'](?!\/|[A-Za-z]:\/)([^\"']+)[\"']",
        "titulo": "Caminho relativo em arquivo",
        "o_que": "Um caminho de screenshot ou download não é absoluto.",
        "problema": "O script não roda no diretório do shell e o caminho relativo aponta para outro lugar.",
        "correcao": "Use caminho absoluto, com barras normais (`/`).",
        "se_ignorar": "O arquivo é gravado onde ninguém procura ou a chamada falha.",
    },
    {
        "id": "coordenada-primeiro", "grupo": "should",
        "padrao": r"mouse\.click\s*\(",
        "companheiro": r"snapshot\s*\(",
        "inverter_companheiro": True,
        "titulo": "Coordenada sem observar a página",
        "o_que": "O plano clica por coordenada sem snapshot.",
        "problema": "Coordenada é o último recurso; sem árvore, o clique é um chute.",
        "correcao": "Tire o snapshot antes e use o alvo semântico; coordenada só para canvas.",
        "se_ignorar": "O clique cai no lugar errado e ninguém sabe por quê.",
    },
    {
        "id": "retry-cego", "grupo": "should",
        "padrao": r"(?:for|while)\s*\([^)]*\)\s*\{[\s\S]{0,400}?\.click\s*\(",
        "titulo": "Laço de repetição cego",
        "o_que": "O plano repete um clique em laço.",
        "problema": "Repetir sem observar repete o mesmo erro e pode duplicar efeitos.",
        "correcao": "Observe o estado e decida; se falhou, tire novo snapshot antes de tentar de novo.",
        "se_ignorar": "A ação é despachada duas vezes.",
    },
    {
        "id": "close-apos-finish", "grupo": "must",
        "padrao": r"finish\s*\([^)]*\)[\s\S]{0,200}?\.close\s*\(",
        "titulo": "Página fechada depois do fechamento",
        "o_que": "Há `page.close()` depois de `finish()`.",
        "problema": "A space já foi encerrada; a página não existe mais.",
        "correcao": "Feche páginas durante a tarefa; no fim, liste o que manter em `keep`.",
        "se_ignorar": "A chamada falha e aparece como erro da tarefa.",
    },
    {
        "id": "claim-sem-pedido", "grupo": "should",
        "padrao": r"claimTaskSpace\s*\(",
        "titulo": "Assumir space do usuário",
        "o_que": "O plano chama `claimTaskSpace`.",
        "problema": "Assumir a space de outra pessoa só é permitido com pedido explícito.",
        "correcao": "Peça autorização e registre a escolha antes de assumir.",
        "se_ignorar": "Você toma o navegador de quem estava trabalhando.",
    },
)


def _linhas_codigo(texto: str) -> list[str]:
    return texto.split("\n")


def _checar_padroes(plano: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    achados: list[dict[str, Any]] = []
    padroes: list[dict[str, Any]] = []
    linhas = _linhas_codigo(plano)
    for regra in PADROES:
        ocorrencias = [i + 1 for i, linha in enumerate(linhas) if re.search(regra["padrao"], linha)]
        if not ocorrencias:
            casamento = re.search(regra["padrao"], plano)
            if casamento:
                ocorrencias = [plano[: casamento.start()].count("\n") + 1]
        if not ocorrencias:
            continue
        if regra.get("contar") and len(ocorrencias) < regra["contar"]:
            continue
        if regra.get("depois"):
            ultimo = ocorrencias[-1]
            if not any(re.search(regra["depois"], linha) for linha in linhas[ultimo:]):
                continue
        companheiro = regra.get("companheiro")
        if companheiro:
            if regra.get("janela"):
                inicio = max(0, ocorrencias[0] - regra["janela"])
                fim = min(len(linhas), ocorrencias[-1] + regra["janela"])
                if not any(re.search(companheiro, linha) for linha in linhas[inicio:fim]):
                    continue
            elif regra.get("inverter_companheiro"):
                if re.search(companheiro, plano):
                    continue
            elif not re.search(companheiro, plano):
                continue
        local = "linha {}".format(ocorrencias[0]) if len(ocorrencias) == 1 else "linhas {}–{}".format(ocorrencias[0], ocorrencias[-1])
        padroes.append({"regra": regra["id"], "linhas": ocorrencias, "grupo": regra["grupo"], "titulo": regra["titulo"]})
        achados.append(_to_finding({
            "group": regra["grupo"], "kind": regra["id"], "title": regra["titulo"],
            "location": local,
            "what": regra["o_que"], "problem": regra["problema"],
            "fix": regra["correcao"], "ifSkipped": regra["se_ignorar"],
        }))
    if "taskSpace(" in plano and not re.search(r"finish\s*\(", plano):
        achados.append(_to_finding({
            "group": "should", "kind": "finish-ausente", "title": "Roteiro sem fechamento",
            "location": "fim do plano",
            "what": "O plano abre espaço, mas não chama `finish()`.",
            "problem": "A space fica aberta e as páginas do agente continuam vivas.",
            "fix": "Feche com `await task.finish({ keep: [] })` na última rodada.",
            "ifSkipped": "Sobra aba e space para o usuário limpar.",
        }))
    return achados, padroes


def checar_plano(payload: dict[str, Any]) -> dict[str, Any]:
    modo = _mode(payload.get("modo"))
    plano = _cap("plano", payload.get("plano"), MAX_PLANO).strip()
    passos_texto = _cap("passos", payload.get("passos"), MAX_LOG).strip()
    if payload.get("passos") and not passos_texto:
        raise NavegadorError("A lista de passos está vazia. Use `ação | alvo | estado` por linha.")
    if not plano and not passos_texto:
        raise NavegadorError("Cole o plano em JavaScript ou a lista de passos para checar.")
    achados: list[dict[str, Any]] = []
    padroes: list[dict[str, Any]] = []
    if plano:
        achados_padrao, padroes = _checar_padroes(plano)
        achados += achados_padrao

    passos: list[dict[str, Any]] = []
    if passos_texto:
        for numero, linha in enumerate(passos_texto.split("\n"), start=1):
            if not linha.strip():
                continue
            partes = [parte.strip() for parte in re.split(r"\s*[|;]\s*", linha)]
            acao = partes[0] if partes else ""
            alvo = partes[1] if len(partes) > 1 else ""
            estado = partes[2] if len(partes) > 2 else ""
            estado_norm = _norm(estado).replace(" ", "-")
            veredito = "ok"
            causa = ""
            correcao = ""
            if estado_norm:
                if estado_norm not in ESTADOS:
                    veredito = "revisar"
                    causa = "estado não reconhecido: {}".format(estado)
                    correcao = "Use um dos estados: {}.".format(", ".join(sorted(ESTADOS)))
                else:
                    _, grupo, o_que, problema, fix, se_ignorar = ESTADOS[estado_norm]
                    veredito = "bloqueado" if grupo == "must" else "atencao"
                    causa = o_que + " " + problema
                    correcao = fix
                    if grupo == "must":
                        achados.append(_to_finding({
                            "group": "must", "kind": "estado-" + estado_norm,
                            "title": "Passo {}: {}".format(numero, o_que),
                            "location": "passo {} ({})".format(numero, alvo or acao),
                            "what": o_que, "problem": problema, "fix": fix, "ifSkipped": se_ignorar,
                        }))
            passos.append({
                "passo": numero, "acao": acao, "alvo": alvo, "estado": estado,
                "veredito": veredito, "causa": causa, "correcao": correcao,
            })
        if not passos:
            achados.append(_to_finding({
                "group": "must", "kind": "passos-vazios", "title": "Lista de passos vazia",
                "location": "passos",
                "what": "Nenhuma linha pôde ser lida.",
                "problem": "O formato esperado é `ação | alvo | estado`.",
                "fix": "Escreva uma linha por passo, por exemplo `clicar | @21 | coberto`.",
                "ifSkipped": "A checagem não tem o que avaliar.",
            }))
    if not passos:
        achados.append(_to_finding({
            "group": "should", "kind": "sem-passos", "title": "Checagem sem passos declarados",
            "location": "passos",
            "what": "Só o código foi colado.",
            "problem": "Actionability depende do estado do alvo: oculto, desabilitado, coberto, ambíguo.",
            "fix": "Liste `ação | alvo | estado` para cada passo que importa.",
            "ifSkipped": "O código passa, mas o clique pode falhar na execução.",
        }))

    achados, counts, veredito, perguntas = finalize(achados, modo, [])
    bloqueados = sum(1 for item in passos if item["veredito"] == "bloqueado")
    atencao = sum(1 for item in passos if item["veredito"] == "atencao")
    extra = ["", "## Passos", ""]
    if passos:
        extra += ["| # | Ação | Alvo | Estado | Veredito |", "| --- | --- | --- | --- | --- |"]
        extra += [
            "| {0} | {1} | {2} | {3} | {4} |".format(
                item["passo"], item["acao"], item["alvo"] or "—", item["estado"] or "—", item["veredito"]
            )
            for item in passos
        ]
    if padroes:
        extra += ["", "## Padrões encontrados", ""]
        extra += ["- `{}` — {} (linhas {})".format(item["regra"], item["titulo"], ", ".join(map(str, item["linhas"]))) for item in padroes]
    resultado = common(
        analysis="checagem de actionability",
        mode=modo,
        title="Checagem do plano",
        summary=[
            "{} passo(s) lidos: {} bloqueado(s) e {} em atenção.".format(len(passos), bloqueados, atencao),
            "{} padrão(ões) de código encontrados no plano.".format(len(padroes)),
            "A checagem é estática: nada foi clicado, preenchido ou aberto.",
        ],
        findings=achados,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=passos[:MAX_LINHAS],
        metrics={
            "passos": len(passos),
            "bloqueados": bloqueados,
            "atencao": atencao,
            "padroes": len(padroes),
            "linhasPlano": len(_linhas_codigo(plano)) if plano else 0,
        },
        limitations=[
            "A checagem não vê a página: estados declarados por você são a única fonte.",
            "Regras de código são léxicas; um padrão pode ser intencional e ainda assim aparecer.",
            "Quem executa o plano é o seu agente, no ego-browser.",
        ],
        extra_sections=extra,
    )
    resultado["passos"] = passos
    resultado["padroes"] = padroes
    return resultado


# ------------------------------------------------------------------ recibos

def _tem(linha: str, *termos: str) -> bool:
    normal = _norm(linha)
    return any(termo in normal for termo in termos)


def _recibo(linha: str, numero: int) -> dict[str, Any]:
    normal = _norm(linha)
    if _tem(linha, "snapshot"):
        acao = "snapshot"
    elif _tem(linha, "screenshot", "captura"):
        acao = "screenshot"
    elif _tem(linha, "goto", "abri", "naveguei"):
        acao = "goto"
    elif _tem(linha, "preenchi", "fill", "digitei"):
        acao = "fill"
    elif _tem(linha, "clique", "click"):
        acao = "click"
    elif _tem(linha, "esperei", "wait", "aguardei"):
        acao = "wait"
    elif _tem(linha, "baixei", "download"):
        acao = "download"
    elif _tem(linha, "enviei arquivo", "upload", "anexei"):
        acao = "upload"
    elif _tem(linha, "dialogo", "dialog", "alerta"):
        acao = "dialog"
    elif _tem(linha, "finish", "fechei", "encerrei"):
        acao = "finish"
    elif _tem(linha, "handoff", "devolvi"):
        acao = "handoff"
    else:
        acao = "observacao" if _tem(linha, "conferi", "verifiquei", "observei") else "outro"
    resultado = "ok"
    if _tem(linha, "falhou", "falha", "erro", "timeout", "recus"):
        resultado = "falhou"
    elif _tem(linha, "parcial", "parado", "pendente"):
        resultado = "parcial"
    popup = ""
    dialogo = ""
    baixado = ""
    salvo = ""
    for chave, destino in (("popup=", "popup"), ("dialogo=", "dialogo"), ("baixei=", "baixado"), ("salvei=", "salvo")):
        casamento = re.search(re.escape(chave) + r"([^\s,;]+)", normal)
        if casamento:
            valor = casamento.group(1)
            if valor not in {"nenhum", "none", "-", "nao", "na"}:
                if destino == "popup":
                    popup = valor
                elif destino == "dialogo":
                    dialogo = valor
                elif destino == "baixado":
                    baixado = valor
                else:
                    salvo = valor
    alvo = ""
    casamento_alvo = re.search(r"(@\d+|loc=[^\s,;]+|#[a-z0-9_-]+|text=[^\s,;]+)", linha, re.I)
    if casamento_alvo:
        alvo = casamento_alvo.group(1)
    tempo = ""
    casamento_tempo = re.search(r"(\d+)\s*ms", linha)
    if casamento_tempo:
        tempo = casamento_tempo.group(1) + "ms"
    return {
        "passo": numero, "acao": acao, "alvo": alvo, "resultado": resultado,
        "efeito": popup or dialogo or baixado or salvo,
        "popup": popup, "dialogo": dialogo, "baixado": baixado, "salvo": salvo,
        "tempo": tempo, "linha": linha.strip(),
    }


def ler_recibos(payload: dict[str, Any]) -> dict[str, Any]:
    modo = _mode(payload.get("modo"))
    log = _cap("log", payload.get("log"), MAX_LOG).strip()
    if not log:
        raise NavegadorError("Cole o log da execução: uma linha por passo, com ação e resultado.")
    recibos = [_recibo(linha, numero) for numero, linha in enumerate(log.split("\n"), start=1) if linha.strip()]
    if not recibos:
        raise NavegadorError("Nenhuma linha do log pôde ser lida.")
    achados: list[dict[str, Any]] = []
    mutantes = [item for item in recibos if item["acao"] in {"click", "fill", "upload", "download", "dialog", "goto"}]
    observacoes = [item for item in recibos if item["acao"] in {"snapshot", "screenshot", "observacao", "wait"}]
    fechamentos = [item for item in recibos if item["acao"] == "finish"]
    keep = re.findall(r"keep\s*=\s*\[([^\]]*)\]", log)
    if not fechamentos:
        achados.append(_to_finding({
            "group": "must", "kind": "sem-finish", "title": "Tarefa sem fechamento",
            "location": "log",
            "what": "Não há `finish` no log.",
            "problem": "A space continua aberta e as páginas do agente seguem vivas para o usuário.",
            "fix": "Encerre com `await task.finish({ keep: [] })` depois da verificação.",
            "ifSkipped": "Sobra aba e space na máquina do usuário.",
        }))
    if len(fechamentos) > 1:
        achados.append(_to_finding({
            "group": "must", "kind": "finish-repetido", "title": "Fechamento repetido",
            "location": "passos {}".format(", ".join(str(item["passo"]) for item in fechamentos)),
            "what": "O log registra mais de um `finish`.",
            "problem": "A segunda chamada age numa space encerrada.",
            "fix": "Mantenha apenas o último fechamento.",
            "ifSkipped": "O erro no fim esconde o resultado.",
        }))
    if fechamentos and mutantes:
        ultimo_fechamento = fechamentos[-1]["passo"]
        depois = [item for item in recibos if item["passo"] > ultimo_fechamento and item["acao"] in {"click", "fill", "goto", "snapshot", "download"}]
        if depois:
            achados.append(_to_finding({
                "group": "must", "kind": "acao-pos-finish", "title": "Ação depois do fechamento",
                "location": "passos {}".format(", ".join(str(item["passo"]) for item in depois)),
                "what": "Há ação de página depois do `finish`.",
                "problem": "A space e os rótulos já estavam encerrados.",
                "fix": "Mova o fechamento para o fim absoluto da tarefa.",
                "ifSkipped": "O último passo falha e o resultado se perde.",
            }))
    popups = [item for item in recibos if item["popup"]]
    if popups:
        texto = _norm(log)
        for item in popups:
            alvo_popup = _norm(item["popup"])
            tratado = bool(re.search(r"(?:page|pagina)\s*\(?\s*[\"']?" + re.escape(alvo_popup), texto))
            if not tratado:
                achados.append(_to_finding({
                    "group": "must", "kind": "popup", "title": "Popup aberto sem tratamento",
                    "location": "passo {}".format(item["passo"]),
                    "what": "A ação abriu a página `{}` e o log não mostra uso dela.".format(item["popup"]),
                    "problem": "O popup é uma página nova com o resultado; sem `task.page(receipt.popups[0].label)` a tarefa continua na página errada.",
                    "fix": "Resolva a página do popup e espere a URL quando o destino importar.",
                    "ifSkipped": "O objetivo fica aberto numa aba que ninguém lê.",
                }))
    dialogos = [item for item in recibos if item["dialogo"]]
    if dialogos and not re.search(r"aceit|dispens|dismiss|accept", _norm(log)):
        achados.append(_to_finding({
            "group": "must", "kind": "dialogo", "title": "Diálogo pendente",
            "location": "passo {}".format(dialogos[0]["passo"]),
            "what": "Um diálogo síncrono apareceu e não foi aceito nem dispensado.",
            "problem": "O diálogo bloqueia a página: as ações seguintes não despacham.",
            "fix": "Chame `page.acceptDialog()` ou `page.dismissDialog()` antes de seguir.",
            "ifSkipped": "A tarefa trava sem mensagem clara.",
        }))
    downloads = [item for item in recibos if item["acao"] == "download"]
    if downloads and not re.search(r"saveas|salvei=", _norm(log)):
        achados.append(_to_finding({
            "group": "must", "kind": "download", "title": "Download sem salvar",
            "location": "passo {}".format(downloads[0]["passo"]),
            "what": "Houve download, mas nenhum `saveAs` para caminho absoluto.",
            "problem": "O arquivo temporário é removido quando a rodada termina.",
            "fix": "Chame `await download.saveAs(\"/caminho/absoluto/arquivo\")` antes do fim do script.",
            "ifSkipped": "O arquivo baixado desaparece.",
        }))
    if "keep" in log:
        for bruto in keep:
            paginas = [item.strip() for item in bruto.split(",") if item.strip()]
            if len(paginas) > 1:
                achados.append(_to_finding({
                    "group": "should", "kind": "keep-demais", "title": "Páginas demais mantidas",
                    "location": "keep=[{}]".format(bruto),
                    "what": "O fechamento mantém {} páginas.".format(len(paginas)),
                    "problem": "Manter páginas é exceção: só quando o usuário pede ou precisa continuar o trabalho.",
                    "fix": "Mantenha só a página do resultado, ou nenhuma.",
                    "ifSkipped": "O usuário herda abas que não pediu.",
                }))
    if mutantes and not observacoes:
        achados.append(_to_finding({
            "group": "should", "kind": "sem-observacao", "title": "Ações sem observação",
            "location": "log",
            "what": "Houve ações e nenhum snapshot, screenshot ou espera registrada.",
            "problem": "Sem observar depois de agir, o agente não sabe se o efeito aconteceu.",
            "fix": "Feche cada rodada com uma observação barata (`snapshot` ou `waitForSelector`).",
            "ifSkipped": "O agente reporta sucesso sem prova.",
        }))
    if mutantes and not any(_tem(item["linha"], "conferi", "verifiquei", "waitfor", "esperei", "title") for item in recibos):
        achados.append(_to_finding({
            "group": "should", "kind": "recibo-nao-e-prova", "title": "Recibo não é verificação",
            "location": "log",
            "what": "O log registra despacho, mas não o estado final.",
            "problem": "O recibo descreve a ação e efeitos imediatos; ele não prova que a aplicação mudou.",
            "fix": "Registre a condição final: URL, seletor visível, título ou snapshot.",
            "ifSkipped": "Você confunde “clique despachado” com “tarefa concluída”.",
        }))
    if any(item["resultado"] == "falhou" for item in recibos):
        falhas = [item for item in recibos if item["resultado"] == "falhou"]
        achados.append(_to_finding({
            "group": "must", "kind": "falha", "title": "Passo com falha registrada",
            "location": "passo {}".format(falhas[0]["passo"]),
            "what": "O log declara falha em {} passo(s).".format(len(falhas)),
            "problem": "Seguir adiante sem tratar a falha deixa o resultado incompleto.",
            "fix": "Observe a página, corrija o alvo e repita com base no novo snapshot.",
            "ifSkipped": "O relatório final promete algo que não aconteceu.",
        }))

    achados, counts, veredito, perguntas = finalize(achados, modo, [])
    extra = ["", "## Recibos", ""]
    extra += ["| # | Ação | Alvo | Resultado | Efeito |", "| --- | --- | --- | --- | --- |"]
    extra += [
        "| {0} | {1} | {2} | {3} | {4} |".format(
            item["passo"], item["acao"], item["alvo"] or "—", item["resultado"],
            item["popup"] or item["dialogo"] or item["baixado"] or item["salvo"] or "—",
        )
        for item in recibos
    ]
    resultado = common(
        analysis="recibos de execução",
        mode=modo,
        title="Recibos: {} passo(s)".format(len(recibos)),
        summary=[
            "{} ação(ões), {} observação(ões) e {} fechamento(s).".format(len(mutantes), len(observacoes), len(fechamentos)),
            "O recibo é despacho, não prova: a verificação é uma linha separada.",
        ],
        findings=achados,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=recibos[:MAX_LINHAS],
        metrics={
            "passos": len(recibos),
            "acoes": len(mutantes),
            "observacoes": len(observacoes),
            "fechamentos": len(fechamentos),
            "popups": len(popups),
            "dialogos": len(dialogos),
            "downloads": len(downloads),
        },
        limitations=[
            "O log é declaração sua; a skill não tem acesso à sessão do navegador.",
            "Formatos fora de `ação alvo resultado popup=/dialogo=` não são reconhecidos.",
            "Nada é executado, salvo ou reenviado por esta skill.",
        ],
        extra_sections=extra,
    )
    resultado["recibos"] = recibos
    return resultado


# ------------------------------------------------------------------ limites

REGRAS_LIMITE: tuple[dict[str, Any], ...] = (
    {
        "id": "credencial", "nivel": "bloqueado",
        "gatilho": r"\b(senha|password|2fa|segundo fator|c[óo]digo de verifica|token|cvv|pin|chave de acesso)\b",
        "titulo": "Credencial nunca passa pelo agente",
        "porque": "Quem digita senha, código de verificação ou cartão é a pessoa; o agente não deve ver nem reter isso.",
        "fazer": "Peça ao usuário para entrar e use `task.handOff()`; retome depois com `takeOverTaskSpace`.",
    },
    {
        "id": "pagamento", "nivel": "bloqueado",
        "gatilho": r"\b(pague|pagar|compre|comprar|checkout|pix|transferir|sacar|boleto|cart[ãa]o|finalizar compra)\b",
        "titulo": "Pagamento é decisão humana",
        "porque": "Compra, transferência e assinatura movem dinheiro e não têm desfazer.",
        "fazer": "Leve até a revisão do pedido e devolva o controle para o usuário concluir.",
    },
    {
        "id": "captcha", "nivel": "bloqueado",
        "gatilho": r"\b(captcha|n[ãa]o sou (um )?rob[ôo]|verifica[çc][ãa]o humana|prove que [ée] humano)\b",
        "titulo": "Desafio anti-robô não se resolve",
        "porque": "Resolver CAPTCHA automaticamente contraria o dono do site e a intenção do desafio.",
        "fazer": "Pare e peça ao usuário para resolver; depois retome a mesma space.",
    },
    {
        "id": "exclusao", "nivel": "confirmar",
        "gatilho": r"\b(excluir|apagar|deletar|remover|encerrar conta|cancelar assinatura|desativar conta)\b",
        "titulo": "Exclusão e cancelamento",
        "porque": "Apagar ou cancelar costuma ser irreversível e pode atingir dados de terceiros.",
        "fazer": "Confirme o alvo e o escopo com o usuário; mostre o que será removido antes de agir.",
    },
    {
        "id": "publicacao", "nivel": "confirmar",
        "gatilho": r"\b(publicar|postar|comentar|enviar mensagem|responder|curtir|seguir|avaliar|recomendar)\b",
        "titulo": "Publicação em nome da pessoa",
        "porque": "O conteúdo sai com a identidade do usuário e fica público.",
        "fazer": "Mostre o rascunho final e espere o aval explícito antes de despachar.",
    },
    {
        "id": "termos", "nivel": "confirmar",
        "gatilho": r"\b(aceitar (os )?termos|aceitar (o )?contrato|assinar|concordar com|cookie[s]?)\b",
        "titulo": "Aceite de termos e cookies",
        "porque": "Aceitar cria obrigação jurídica em nome de outra pessoa.",
        "fazer": "Liste o que está sendo aceito e deixe a decisão com o usuário.",
    },
    {
        "id": "configuracao", "nivel": "confirmar",
        "gatilho": r"\b(alterar|mudar|trocar|configurar)\b.*\b(conta|privacidade|e-?mail|telefone|endere[çc]o|senha|perfil)\b",
        "titulo": "Alteração de conta",
        "porque": "Mudar dados de conta pode quebrar acesso e notificações.",
        "fazer": "Confirme campo e valor com o usuário e mostre o antes/depois.",
    },
    {
        "id": "upload", "nivel": "confirmar",
        "gatilho": r"\b(enviar arquivo|upload|anexar|subir arquivo)\b",
        "titulo": "Envio de arquivo",
        "porque": "O arquivo pode conter dado pessoal e passa a existir no serviço de terceiros.",
        "fazer": "Confirme o caminho absoluto e o conteúdo antes de `setInputFiles`.",
    },
    {
        "id": "dados-pessoais", "nivel": "confirmar",
        "gatilho": r"\b(cpf|cnpj|telefone de|endere[çc]o de|lista de (clientes|contatos)|dados (pessoais|de terceiros)|e-?mail de (cliente|contato|terceiro))\b",
        "titulo": "Dados pessoais de terceiros",
        "porque": "Coletar ou colar dados de outras pessoas muda a base legal e o risco.",
        "fazer": "Limite ao mínimo necessário e confirme a origem e a finalidade.",
    },
    {
        "id": "conta-corporativa", "nivel": "confirmar",
        "gatilho": r"\b(corporativ[ao]|empresa|work|admin|painel administrativo)\b",
        "titulo": "Conta ou painel corporativo",
        "porque": "A política da organização pode proibir automação nesse sistema.",
        "fazer": "Confirme a autorização antes de qualquer ação que mude estado.",
    },
    {
        "id": "takeover", "nivel": "bloqueado",
        "gatilho": r"\b(ignorar|contornar|burlar|desativar)\b.*\b(controle|aviso|prote[çc][ãa]o|bloqueio|takeover)\b",
        "titulo": "Contornar o controle do usuário",
        "porque": "O usuário pode retomar o navegador a qualquer momento; ignorar isso é falha grave.",
        "fazer": "Pare na hora. Não repita a ação nem crie outra space para escapar do bloqueio.",
    },
)

BENIGNOS = re.compile(
    r"\b(abrir|abre|navegar|acessar|ler|consultar|observar|snapshot|screenshot|"
    r"rolar|esperar|aguardar|buscar|pesquisar|preencher|digitar|selecionar|filtrar|"
    r"copiar|extrair|listar|baixar (o )?(relat[óo]rio|arquivo pr[óo]prio)|"
    r"clicar em (pr[óo]xim|continuar|avan[çc]ar|ver mais|detalhes))\b"
)

NIVEIS = {
    "bloqueado": ("bloqueado", "O agente não faz; quem faz é você."),
    "confirmar": ("confirmar", "O agente só faz depois do seu aval explícito."),
    "liberado": ("liberado", "Leitura e navegação comuns, sem efeito externo."),
}


def checar_limites(payload: dict[str, Any]) -> dict[str, Any]:
    modo = _mode(payload.get("modo"))
    texto = _cap("acoes", payload.get("acoes"), MAX_ACOES).strip()
    if not texto:
        raise NavegadorError("Liste as ações pretendidas, uma por linha.")
    linhas = [linha.strip(" -•\t") for linha in texto.split("\n") if linha.strip()]
    if len(linhas) > 60:
        raise NavegadorError("O limite é 60 ações por análise.")
    achados: list[dict[str, Any]] = []
    veredictos: list[dict[str, Any]] = []
    for numero, linha in enumerate(linhas, start=1):
        normal = _norm(linha)
        regra = next((item for item in REGRAS_LIMITE if re.search(item["gatilho"], normal)), None)
        if regra:
            nivel = regra["nivel"]
            motivo = regra["porque"]
            fazer = regra["fazer"]
            titulo = regra["titulo"]
            chave = regra["id"]
        elif BENIGNOS.search(normal):
            nivel, motivo, fazer, titulo, chave = "liberado", "Navegação ou leitura sem efeito externo.", "Siga com a observação no fim da rodada.", "Ação comum", "comum"
        else:
            nivel, motivo, fazer, titulo, chave = "confirmar", "A skill não reconhece a ação como leitura nem como bloqueada.", "Descreva o efeito esperado e confirme com o usuário.", "Ação não classificada", "indefinida"
        veredictos.append({
            "passo": numero, "acao": linha, "nivel": nivel, "regra": chave,
            "titulo": titulo, "porque": motivo, "fazer": fazer, "quem": "usuário" if nivel != "liberado" else "agente",
        })
        if nivel == "bloqueado":
            achados.append(_to_finding({
                "group": "must", "kind": "limite-" + chave, "title": "Bloqueado: {}".format(titulo),
                "location": "ação {} ({})".format(numero, linha[:60]),
                "what": "A ação casa com uma regra de bloqueio.",
                "problem": motivo, "fix": fazer,
                "ifSkipped": "O agente faz em nome da pessoa o que ela não autorizou.",
            }))
        elif nivel == "confirmar":
            achados.append(_to_finding({
                "group": "should", "kind": "limite-" + chave, "title": "Confirme: {}".format(titulo),
                "location": "ação {} ({})".format(numero, linha[:60]),
                "what": "A ação tem efeito externo e precisa de aval.",
                "problem": motivo, "fix": fazer,
                "ifSkipped": "A ação é despachada sem revisão humana.",
            }))
    bloqueadas = [item for item in veredictos if item["nivel"] == "bloqueado"]
    confirmar = [item for item in veredictos if item["nivel"] == "confirmar"]
    achados, counts, veredito, perguntas = finalize(achados, modo, [])
    handoff = ""
    if bloqueadas or confirmar:
        handoff = (
            "Pare antes das ações marcadas, explique o que falta e devolva o controle com "
            "`await task.handOff()`. Depois do aval, retome a mesma space com `takeOverTaskSpace`."
        )
    extra = ["", "## Veredito por ação", ""]
    extra += ["| # | Ação | Nível | Regra |", "| --- | --- | --- | --- |"]
    extra += [
        "| {0} | {1} | {2} | {3} |".format(item["passo"], item["acao"][:70], item["nivel"], item["titulo"])
        for item in veredictos
    ]
    if handoff:
        extra += ["", "## Handoff", "", handoff]
    resultado = common(
        analysis="limites e consentimento",
        mode=modo,
        title="Limites: {} ação(ões)".format(len(veredictos)),
        summary=[
            "{} bloqueada(s), {} para confirmar e {} liberada(s).".format(
                len(bloqueadas), len(confirmar), len(veredictos) - len(bloqueadas) - len(confirmar)
            ),
            "A classificação é léxica e conservadora: na dúvida, confirma com você.",
        ],
        findings=achados,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=veredictos[:MAX_LINHAS],
        metrics={
            "acoes": len(veredictos),
            "bloqueadas": len(bloqueadas),
            "confirmar": len(confirmar),
            "liberadas": len(veredictos) - len(bloqueadas) - len(confirmar),
            "handoff": bool(handoff),
        },
        limitations=[
            "A classificação lê palavras, não intenção: uma ação pode ser mal descrita.",
            "Ela não substitui política da empresa, termos do site nem julgamento humano.",
            "Nada é executado; o texto de handoff é instrução para o seu agente.",
        ],
        extra_sections=extra,
    )
    resultado["veredictos"] = veredictos
    resultado["handoff"] = handoff
    return resultado


# ------------------------------------------------------------------ catálogo

def navegador_catalog() -> dict[str, Any]:
    return {
        "fonte": "citrolabs/ego-lite (MIT)",
        "versao": "0.60.3",
        "principio": "Uma space por objetivo; o documento principal antes dos frames; recibo não é prova.",
        "papeis": [
            {"papel": "button", "rotulo": "Botão", "acionavel": True},
            {"papel": "link / anchor", "rotulo": "Link", "acionavel": True},
            {"papel": "textbox", "rotulo": "Campo de texto", "acionavel": True},
            {"papel": "searchbox", "rotulo": "Campo de busca", "acionavel": True},
            {"papel": "combobox", "rotulo": "Lista suspensa", "acionavel": True},
            {"papel": "checkbox / radio", "rotulo": "Marcação", "acionavel": True},
            {"papel": "menuitem / tab", "rotulo": "Item de menu ou aba", "acionavel": True},
            {"papel": "iframe", "rotulo": "Frame (alvo de subtree)", "acionavel": False},
            {"papel": "heading / text", "rotulo": "Leitura, não ação", "acionavel": False},
        ],
        "alvos": [{"tipo": chave, "formato": valor} for chave, valor in TIPOS_ALVO.items()],
        "acoes": [
            {"acao": chave, "api": valor["api"], "rotulo": valor["rotulo"], "valor": valor["valor"]}
            for chave, valor in sorted(ACOES.items())
        ],
        "estados": [
            {"estado": chave, "grupo": valor[1], "titulo": valor[2], "correcao": valor[4]}
            for chave, valor in ESTADOS.items()
        ],
        "limites": [
            {"id": item["id"], "nivel": item["nivel"], "titulo": item["titulo"], "porque": item["porque"], "fazer": item["fazer"]}
            for item in REGRAS_LIMITE
        ],
        "padroes": [
            {"id": item["id"], "grupo": item["grupo"], "titulo": item["titulo"], "correcao": item["correcao"]}
            for item in PADROES
        ],
        "recibos": [
            {"campo": "passo", "leitura": "ordem da linha no log"},
            {"campo": "acao", "leitura": "click, fill, goto, wait, snapshot, download, finish…"},
            {"campo": "alvo", "leitura": "ref, locator ou descrição"},
            {"campo": "resultado", "leitura": "ok, parcial ou falhou"},
            {"campo": "popup", "leitura": "rótulo da página aberta"},
            {"campo": "dialogo", "leitura": "texto do diálogo pendente"},
            {"campo": "tempo", "leitura": "duração em ms"},
        ],
        "orcamento": [
            {"regra": "uma space por objetivo", "limite": "reabrir pelo nome ou spaceId"},
            {"regra": "uma observação por rodada", "limite": "snapshot ou screenshot, não os dois"},
            {"regra": "páginas", "limite": "p1 por padrão; newPage só com duas telas abertas"},
            {"regra": "fechamento", "limite": "finish uma vez, por último"},
            {"regra": "rodadas", "limite": "entre 2 e 8 no roteiro"},
        ],
    }


__all__ = [
    "NavegadorError",
    "parse_snapshot",
    "read_snapshot",
    "resolver_alvo",
    "montar_roteiro",
    "checar_plano",
    "ler_recibos",
    "checar_limites",
    "navegador_catalog",
]
