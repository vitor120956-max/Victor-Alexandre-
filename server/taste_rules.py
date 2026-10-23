"""Regras estáticas de gosto: copy deck, linter de fantasia e registro de tells.

Implementação própria inspirada em Leonxlnx/taste-skill (MIT, 2026). Tudo é
lexical e determinístico: nada é renderizado, compilado ou enviado à rede, e
nenhum script Node do upstream é executado. As três skills desta módulo leem o
texto ou a fonte que você declara e devolvem achados em quatro partes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Pattern

from .review import common, finalize, finding
from .taste import MAX_HTML_CHARS, TasteError, _mode, _norm, _rows

# ------------------------------------------------------------------------ copy

COPY_ROLES: dict[str, tuple[str, tuple[str, ...]]] = {
    "manchete": ("Título", ("headline", "titulo", "título", "h1", "manchete")),
    "apoio": ("Linha de apoio", ("support", "subheadline", "subtitulo", "subtítulo", "dek", "resumo")),
    "corpo": ("Corpo", ("body", "paragrafo", "parágrafo", "texto")),
    "acao": ("Ação", ("action", "cta", "botao", "botão", "button")),
    "nav": ("Navegação", ("nav", "menu", "navegacao", "navegação")),
    "legenda": ("Legenda", ("caption", "legenda", "credito", "crédito")),
    "statement": ("Declaração", ("statement", "manifesto", "declaracao", "declaração")),
    "eyebrow": ("Sobrancelha", ("eyebrow", "kicker", "overline", "sobrancelha")),
    "rotulo": ("Rótulo", ("label", "rotulo", "rótulo", "tag")),
}
COPY_ALIASES = {alias: key for key, (_label, aliases) in COPY_ROLES.items() for alias in aliases}
COPY_ALIASES.update({key: key for key in COPY_ROLES})

_ACTION_STOCK = (
    "saiba mais", "saber mais", "comece agora", "começar agora", "clique aqui", "leia mais",
    "descubra", "descubra mais", "explore", "explore agora", "get started", "learn more",
    "read more", "start now", "discover", "enviar", "submit",
)
_STOCK_WORDS = (
    "desbloqueie", "desbloquear", "eleve", "elevar", "transforme", "revolucione", "potencialize",
    "superalimente", "sem esforço", "sem fricção", "à prova de futuro", "prova de futuro",
    "próximo nível", "solução completa", "tudo em um", "líder de mercado", "corte de ponta",
    "estado da arte", "world-class", "cutting-edge", "all-in-one", "next-generation",
    "seamless", "effortless", "unlock", "supercharge", "elevate", "empower", "streamline",
    "revolutionize", "game-changer", "blazing fast", "reimagine", "leverage", "synergy",
)
_PLACEHOLDERS = (
    "lorem ipsum", "dolor sit amet", "título aqui", "titulo aqui", "seu texto", "sua empresa",
    "nome da empresa", "texto de exemplo", "placeholder", "insira o texto", "your text here",
    "company name", "your headline",
)
_REIMAGINED = re.compile(r"reimaginad[oa]?|redefinid[oa]?|reinventad[oa]?|reimagined|redefined|reinvented", re.I)
_MADLIB = re.compile(
    r"\b(?:plataforma|ferramenta|solu[çc][ãa]o|sistema|app|software)\s+(?:para|pra)\s+"
    r"(?:times|empresas|pessoas|neg[óo]cios|criadores|marcas|startups)\b"
    r"|\b(?:o|a)\s+(?:futuro|jeito)\s+(?:do|de|da)\s+\w+",
    re.I,
)
_CORRECTION = re.compile(
    r"n[ãa]o\s+[ée]\s+(?:s[óo]|apenas|somente)\b[^.]{1,60}[,;—–-]\s*(?:[ée]|mas)\b"
    r"|n[ãa]o\s+[ée]\s+um[a]?\s+\w+[,;—–-]\s*[ée]\s+um[a]?"
    r"|more than just\b|mais que um[a]?\b",
    re.I,
)
_EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF]")
_LOREM = re.compile(r"lorem ipsum|dolor sit amet", re.I)


def _copy_label(role: str) -> str:
    return COPY_ROLES[role][0]


def _words(text: str) -> list[str]:
    return re.findall(r"[^\W\d_]+(?:['’-][^\W\d_]+)*|\d+(?:[.,]\d+)?", text, re.UNICODE)


def _squash(text: str) -> str:
    return " ".join(text.split())


def audit_copy(*, deck: str, mode: str = "full") -> dict[str, Any]:
    """Audita um deck de copy declarado: papéis, limites e formas proibidas."""
    _mode(mode)
    rows = _rows(deck, 2, "peça de copy")
    findings: list[dict[str, Any]] = []

    def add(*args: str) -> None:
        findings.append(finding(*args))

    entries: list[dict[str, Any]] = []
    by_role: dict[str, list[str]] = {}
    for number, cells in rows:
        raw_role, value = cells
        role = COPY_ALIASES.get(_norm(raw_role))
        label = _copy_label(role) if role else (raw_role or f"peça {number}")
        text = _squash(value)
        if role is None:
            add("must", "unknown-role", "Peça de copy desconhecida", f"linha {number}",
                f"`{raw_role}` não é um papel do deck.",
                "Sem papel, a regra não sabe qual limite aplicar.",
                "Use: " + ", ".join(COPY_ROLES) + ".",
                "A peça entra no deck sem ser medida.")
            entries.append({"line": number, "role": "", "label": label, "text": text, "status": "desconhecida"})
            continue
        if not text:
            add("must", "empty-copy", "Peça vazia", f"{label} · linha {number}",
                "A peça foi declarada sem texto.",
                "Peça vazia costuma virar placeholder no layout.",
                "Escreva o texto ou apague a peça.", "O espaço fica reservado e vazio.")
            entries.append({"line": number, "role": role, "label": label, "text": "", "status": "vazia"})
            continue
        by_role.setdefault(role, []).append(text)
        entries.append({"line": number, "role": role, "label": label, "text": text, "status": "lida"})

    headline = by_role.get("manchete", [""])[0]
    support = by_role.get("apoio", [""])[0]
    action = by_role.get("acao", [""])[0]
    bodies = by_role.get("corpo", [])
    nav = by_role.get("nav", [])
    statements = by_role.get("statement", [])
    labels = by_role.get("rotulo", [])
    eyebrows = by_role.get("eyebrow", [])
    actions = by_role.get("acao", [])

    if not headline:
        add("must", "no-headline", "Sem título", "deck",
            "O deck não declara a peça `manchete`.",
            "O título é a única peça que responde 'o que é isto' em cinco segundos.",
            "Declare `manchete | ...` com quatro a seis palavras.", "A primeira tela fica sem argumento.")
    else:
        chars = len(headline)
        words = len(headline.split())
        if chars > 42:
            add("must", "headline-over", "Título acima do orçamento", f"{chars} caracteres",
                f"`{headline[:100]}`.",
                "Acima de 42 caracteres o título deixa de caber em duas linhas no celular.",
                "Corte até 32 caracteres e leve o resto para a linha de apoio.",
                "O título encolhe no celular e perde a hierarquia.")
        elif chars > 32:
            add("should", "headline-tight", "Título no limite", f"{chars} caracteres",
                f"`{headline[:100]}`.",
                "Entre 33 e 42 caracteres o título só cabe em duas linhas com corpo menor.",
                "Encurte ou aceite um corpo de 34 px no celular.", "O título quebra em três linhas.")
        if words > 7:
            add("nice", "headline-words", "Muitas palavras no título", f"{words} palavras",
                "A mediana dos heróis estudados é de cinco palavras.",
                "Título é olhado de relance; frase é lida.",
                "Deixe quatro a seis palavras.", "O título é lido como parágrafo.")
        if _CORRECTION.search(headline):
            add("should", "correction-copy", "Título de correção", headline[:80],
                "A fórmula 'não é X, é Y' está no título.",
                "Ela explica por oposição em vez de dizer o que a coisa é.",
                "Troque pela afirmação direta.", "O título soa a anúncio de IA.")
        if _REIMAGINED.search(headline):
            add("should", "reimagined-copy", "Título de reinvenção", headline[:80],
                "O título diz que algo foi reimaginado, redefinido ou reinventado.",
                "Ninguém sabe o que era antes nem o que mudou.",
                "Diga o que a coisa faz agora, com substantivo concreto.",
                "A promessa não tem conteúdo verificável.")
        if _MADLIB.search(headline):
            add("should", "madlib-copy", "Título de molde", headline[:80],
                "A estrutura é 'plataforma X para times modernos'.",
                "É o molde que qualquer concorrente preenche sem mudar nada.",
                "Troque a categoria pelo fato que só este sujeito tem.", "A página poderia ser de outro cliente.")
        if re.search(r"\bbem-vindo\b|\bwelcome\b", headline, re.I):
            add("should", "welcome-copy", "Boas-vindas no título", headline[:80],
                "O título abre com boas-vindas.",
                "Ninguém procura boas-vindas; procura o que a página faz.",
                "Abra com a afirmação.", "A primeira linha desperdiça a atenção.")
        if headline.endswith("?") and len(headline.split()) <= 12:
            add("nice", "question-copy", "Título em pergunta", headline[:90],
                "O título é uma pergunta curta.",
                "Pergunta de título costuma ser retórica e não é respondida na página.",
                "Afirme a resposta em vez de perguntar.", "O leitor procura a resposta e não encontra.")
        tri = re.fullmatch(r"([^.!?]{1,25})\.\s*([^.!?]{1,25})\.\s*([^.!?]{1,25})\.?", headline)
        if tri and all(len(part.split()) <= 4 for part in tri.groups()):
            add("should", "tricolon-copy", "Título em trio", headline[:90],
                "Três frases curtas separadas por ponto.",
                "O trio 'Rápido. Simples. Seguro.' é uma das formas mais geradas.",
                "Escolha a frase mais forte e corte as outras duas.", "O título vira slogan vazio.")
        if re.search(r"^[^:]{1,18}:\s", headline):
            add("nice", "colon-copy", "Título com dois-pontos", headline[:90],
                "O título começa com um rótulo curto e dois-pontos.",
                "Costuma ser 'Marca: descrição', repetindo o que já está na navegação.",
                "Comece pela descrição.", "O título gasta metade do orçamento na marca.")
        if headline.endswith("."):
            add("nice", "headline-period", "Ponto final no título", headline[-30:],
                "O título termina em ponto final.",
                "A convenção é frase sem ponto final, salvo uma voz que pontua tudo.",
                "Remova o ponto ou pontue a página inteira.", "O título parece uma legenda.")

    if support:
        support_words = len(support.split())
        if support_words > 22:
            add("should", "support-long", "Linha de apoio longa", f"{support_words} palavras",
                f"`{support[:110]}`.",
                "Acima de 22 palavras a linha de apoio vira parágrafo.",
                "Corte para uma frase com o detalhe concreto.", "A linha some da primeira tela.")
        if headline:
            overlap = set(_norm(support).split()) & set(_norm(headline).split())
            if len(overlap) >= max(3, len(set(_norm(headline).split())) // 2):
                add("should", "support-repeats", "Apoio repete o título", ", ".join(sorted(overlap))[:80],
                    "A linha de apoio repete palavras do título.",
                    "Ela existe para acrescentar o que o título cortou.",
                    "Diga o que é, para quem e o que custa.", "A primeira tela diz duas vezes a mesma coisa.")
    elif headline and len(headline.split()) <= 3:
        add("should", "support-missing", "Sem linha de apoio", "deck",
            f"O título tem {len(headline.split())} palavra(s) e não há apoio.",
            "Nome curto sem apoio não diz o que é nem para quem.",
            "Acrescente uma frase de até 22 palavras com o detalhe concreto.",
            "O visitante entende o tom, não o produto.")

    if not actions:
        add("must", "no-action", "Sem ação", "deck",
            "O deck não nomeia nenhuma ação.",
            "Página sem ação é leitura, não convite.",
            "Declare `acao | ...` com um a três verbos no imperativo.",
            "O visitante não sabe o próximo passo.")
    else:
        if len(actions) > 1:
            add("should", "multiple-primary", "Mais de uma ação principal", f"{len(actions)} ações",
                "Foram declaradas " + ", ".join(f"`{item}`" for item in actions[:4]) + ".",
                "Cada tela tem um botão primário; os outros são secundários e precisam de rótulo próprio.",
                "Marque uma como primária e reduza as demais a links ou ações secundárias.",
                "Os botões competem e nenhum parece principal.")
        for item in actions:
            if _norm(item) in {_norm(term) for term in _ACTION_STOCK}:
                add("should", "stock-action", "Ação de prateleira", item[:60],
                    f"`{item}` não diz o que acontece ao clicar.",
                    "Rótulo genérico é o tell mais comum de uma tela gerada.",
                    "Nomeie pelo resultado: 'Reservar mesa', 'Baixar para Mac'.",
                    "O botão some no meio dos outros.")
            elif len(item.split()) > 3:
                add("nice", "action-long", "Ação longa", item[:60],
                    "A ação tem mais de três palavras.",
                    "Botão é lido de relance e clicado no celular.",
                    "Reduza a uma a três palavras.", "O botão quebra em duas linhas.")
        arrows = sum(item.count("→") + item.count("->") + item.count("↗") for item in actions)
        if arrows > 1:
            add("nice", "action-arrows", "Setas em excesso", f"{arrows} setas",
                "Mais de uma ação leva seta.",
                "A seta é um acento: repetida, deixa de significar avanço.",
                "Deixe a seta só na ação primária.", "O padrão visual se repete e cansa.")

    if len(nav) > 5:
        add("should", "nav-long", "Navegação longa", f"{len(nav)} links",
            "A navegação tem mais de cinco links.",
            "Cada link a mais dilui a decisão de onde clicar.",
            "Mantenha no máximo cinco substantivos e uma ação.",
            "O menu vira um índice e some no celular.")
    duplicates = {item for item in nav if nav.count(item) > 1}
    if duplicates:
        add("nice", "nav-duplicate", "Link repetido na navegação", ", ".join(sorted(duplicates))[:80],
            "O mesmo link aparece mais de uma vez.",
            "Repetição na navegação costuma ser sobra de montagem.",
            "Deixe uma ocorrência.", "O menu parece copiado de um template.")

    for item in statements:
        if len(item.split()) > 25:
            add("should", "statement-paragraph", "Declaração virou parágrafo", f"{len(item.split())} palavras",
                f"`{item[:110]}`.",
                "Declaração é frase de efeito com corpo grande; acima de 25 palavras ela é parágrafo.",
                "Corte para até 25 palavras ou rebaixe para corpo.",
                "A frase ocupa a tela inteira e não é lida.")

    for item in labels:
        caps = [word for word in item.split() if word.isupper() and len(word) > 2]
        if len(caps) > 3:
            add("should", "micro-caps", "Rótulo em caixa alta", f"{len(caps)} palavras",
                f"`{item[:70]}`.",
                "Caixa alta com mais de três palavras é micro-rótulo de 2024.",
                "Use frase normal ou só a primeira palavra em caixa alta.",
                "O texto grita sem hierarquia.")

    for item in eyebrows:
        add("must", "eyebrow-banned", "Sobrancelha acima do título", item[:70],
            "O deck declara uma sobrancelha sobre o título.",
            "Eyebrow/kicker é a fantasia editorial mais reconhecível da década.",
            "Apague a sobrancelha e deixe o título fazer o trabalho.",
            "A primeira tela começa com uma etiqueta que ninguém pediu.")

    full_text = " ".join(entry["text"] for entry in entries)
    lowered = _norm(full_text)
    hits = [word for word in _STOCK_WORDS if _norm(word) in lowered]
    if hits:
        add("should", "stock-words", "Vocabulário de catálogo", ", ".join(hits[:6]),
            f"{len(hits)} expressão(ões) de prateleira no deck.",
            "São as palavras que qualquer concorrente poderia imprimir sem mudar nada.",
            "Troque o adjetivo pelo fato: número, material, prazo, lugar.",
            "O texto fala como um anúncio genérico.")
    placeholder = [term for term in _PLACEHOLDERS if _norm(term) in lowered]
    if placeholder:
        add("must", "placeholder-copy", "Texto de exemplo no deck", ", ".join(placeholder[:4]),
            "O deck ainda contém texto de exemplo.",
            "Placeholder publicado é o defeito mais caro e mais comum.",
            "Substitua por conteúdo real antes de construir.",
            "A página vai ao ar dizendo 'seu texto aqui'.")
    if _LOREM.search(full_text):
        add("must", "lorem-copy", "Lorem ipsum", "deck",
            "O texto latino de exemplo continua no deck.",
            "Lorem é o oposto de direção de arte: não há conteúdo para compor.",
            "Escreva o texto real, mesmo provisório.", "O layout é desenhado para um texto que não existe.")
    if _EMOJI.search(full_text):
        add("should", "emoji-copy", "Emoji no texto", "deck",
            "O deck usa emoji como parte da copy.",
            "Emoji como ícone ou acento é um tell de página gerada.",
            "Troque por palavra ou por ícone desenhado.", "O texto envelhece junto com o conjunto de emoji.")

    dumps = [entry["text"] for entry in entries]
    straight = sum(item.count('"') + item.count("'") for item in dumps)
    if straight:
        add("nice", "straight-quotes", "Aspas retas", f"{straight} aspas",
            "O texto usa aspas retas.",
            "Aspas curvas fazem parte da micro-tipografia de uma página cuidada.",
            "Troque por aspas curvas “ ” e ’.", "O texto parece digitado no terminal.")
    if any("..." in item for item in dumps):
        add("nice", "three-dots", "Reticências em três pontos", "deck",
            "O texto usa `...` em vez do caractere de reticências.",
            "São três pontos digitados como atalho, não tipografia.",
            "Use o caractere …", "A pontuação denuncia o texto de máquina.")
    if any("--" in item or " - " in item for item in dumps):
        add("nice", "hyphen-dash", "Hífen no lugar de travessão", "deck",
            "O texto usa dois hífens ou hífen cercado de espaço como travessão.",
            "Travessão tem seu próprio caractere e espaçamento.",
            "Use — ou reescreva com ponto final.", "A pontuação parece digitada às pressas.")
    dashes = full_text.count("—")
    if dashes > 3:
        add("should", "em-dash-copy", "Travessão em excesso", f"{dashes} travessões",
            "O texto usa travessão como pontuação padrão.",
            "Um ou dois leem como escrita; dez leem como modelo.",
            "Troque por ponto final ou vírgula.", "O texto entrega que foi gerado.")
    for item in dumps:
        run = re.findall(r"\b[A-ZÀ-Ú]{3,}\b", item)
        if len(run) > 3:
            add("should", "caps-run", "Caixa alta em sequência", f"{len(run)} palavras",
                " ".join(run[:6]),
                "Caixa alta em sequência é micro-rótulo disfarçado de ênfase.",
                "Use peso ou tamanho em vez de caixa alta.",
                "A página grita em vez de hierarquizar.")
            break

    metrics = {
        "pieces": len(entries), "roles": len({entry["role"] for entry in entries if entry["role"]}),
        "characters": len(full_text), "words": len(_words(full_text)),
        "headlineChars": len(headline), "headlineWords": len(headline.split()),
        "supportWords": len(support.split()), "actions": len(actions), "navLinks": len(nav),
        "stockWords": len(hits), "placeholders": len(placeholder),
    }
    questions = [
        "Cada peça deste deck poderia ser dita por um concorrente sem mudar uma palavra?",
        "O título cabe em duas linhas a 390 px com o corpo que você escolheu?",
        "A ação primária descreve o resultado, e não o gesto de clicar?",
    ]
    limitations = [
        "A medição de linhas do título é estimada por caracteres; a quebra real depende da fonte e da largura.",
        "A detecção de forma proibida é lexical: ironia, contexto e voz de marca não são avaliados.",
        "Nenhum texto é reescrito automaticamente e nada é enviado a um provedor externo.",
    ]
    summary = [
        f"**Peças:** {len(entries)} · {len(_words(full_text))} palavras · título {len(headline)} caracteres · apoio {len(support.split())} palavras.",
        f"**Ações:** {len(actions)} · links de navegação: {len(nav)} · vocabulário de catálogo: {len(hits)}.",
    ]
    findings, counts, verdict_text, questions = finalize(findings, mode, questions)
    extra = ["", "## Deck auditado", "", "| Peça | Texto | Palavras | Estado |", "|---|---|---|---|"]
    extra += [
        f"| {entry['label']} | {entry['text'][:90] or '—'} | {len(_words(entry['text']))} | {entry['status']} |"
        for entry in entries
    ]
    return common(
        analysis="copy", mode=mode, title="Deck de copy", summary=summary,
        findings=findings, counts=counts, verdict=verdict_text, questions=questions, rows=entries,
        metrics=metrics, limitations=limitations, extra_sections=extra,
    )


# ------------------------------------------------------------------------ lint


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    severity: str
    pattern: Pattern[str]
    what: str
    problem: str
    fix: str
    if_skipped: str
    app: str = "same"  # same | warn | off
    threshold: int = 0
    counter: bool = False


def _rule(*args: Any, **kwargs: Any) -> Rule:
    return Rule(*args, **kwargs)


RULES: tuple[Rule, ...] = (
    _rule(
        "gradient-text", "Texto com gradiente", "must",
        re.compile(r"background-clip\s*:\s*text|-webkit-background-clip\s*:\s*text", re.I),
        "O texto recebe um gradiente por recorte de fundo.",
        "Texto com gradiente é o efeito mais reconhecível de página gerada.",
        "Use uma cor sólida; se precisar de acento, use-o em uma palavra e sem gradiente.",
        "A manchete parece um anúncio de 2021.",
    ),
    _rule(
        "gradient", "Gradiente decorativo", "should",
        re.compile(r"(?:linear|radial|conic)-gradient\(", re.I),
        "Há um gradiente em fundo, borda ou sobreposição.",
        "O estudo mede gradiente em 22% dos sites premiados e 52% dos fracos.",
        "Troque por cor chapada ou por uma imagem real; gradiente só como scrim de legibilidade.",
        "A superfície compete com o conteúdo.",
    ),
    _rule(
        "mono", "Fonte mono fora de código", "should",
        re.compile(r"font-family\s*:[^;}]*\b(?:monospace|mono|Courier|Consolas|JetBrains|Fira Code)\b", re.I),
        "Uma família monoespaçada é usada fora de código.",
        "Mono como decoração é fantasia de portfólio: 44% dos premiados usam, mas 38% dos fracos também.",
        "Reserve mono para números tabulares e blocos de código.",
        "O texto parece um terminal sem motivo.", app="off",
    ),
    _rule(
        "numbering", "Numeração decorativa", "should",
        re.compile(r">\s*0[1-9]\s*[./·—–-]|<span[^>]*>\s*0[1-9]\s*</span>", re.I),
        "Seções ou itens são numerados com zero à esquerda.",
        "01 / 02 / 03 é o enfeite de template mais copiado da década.",
        "Remova a numeração; se a ordem importa, use um passo a passo real.",
        "A página finge ter um sistema que não existe.", app="off",
    ),
    _rule(
        "eyebrow", "Sobrancelha sobre o título", "should",
        re.compile(r"class=[\"'][^\"']*(?:eyebrow|kicker|overline|pretitle)", re.I),
        "Existe uma etiqueta pequena acima do título.",
        "Eyebrow é a fantasia editorial mais reconhecível: acrescenta um rótulo que ninguém lê.",
        "Apague a etiqueta e deixe o título começar a página.",
        "A hierarquia começa com um sussurro antes da frase.", app="off",
    ),
    _rule(
        "micro-label", "Micro-rótulo em caixa alta", "should",
        re.compile(r"\{[^}]{0,240}text-transform\s*:\s*uppercase[^}]{0,240}\}", re.I),
        "Um bloco de estilo aplica caixa alta a um texto curto.",
        "Micro-caps com tracking é um tell datado: 16% nos premiados e 57% nos fracos.",
        "Use frase normal com peso e tamanho; caixa alta só em siglas reais.",
        "O rótulo grita e some.",
    ),
    _rule(
        "purple", "Violeta ou índigo", "must",
        re.compile(r"#(?:6366f1|8b5cf6|7c3aed|a855f7|4f46e5|6d28d9)\b|\b(?:violet|indigo|purple)\b", re.I),
        "A paleta usa violeta, índigo ou a família do gradiente roxo.",
        "Um site em 246 do estudo usava botão violeta; é a cor padrão de ferramenta de IA.",
        "Troque pelo acento da marca, com contraste medido.",
        "A página parece um produto de IA de 2023.",
    ),
    _rule(
        "claude-palette", "Creme e terracota", "nice",
        re.compile(r"#(?:d97757|c2634a|e07a5f|cc7a5c)\b", re.I),
        "A paleta usa o terracota associado a creme e serifa alta.",
        "Creme mais terracota virou uniforme de landing page em 2026.",
        "Só mantenha se for a cor real da marca; troque o creme por branco ou cinza neutro.",
        "A página parece gerada pelo mesmo modelo que todas as outras.",
    ),
    _rule(
        "emoji", "Emoji como ícone", "should",
        re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF]"),
        "Há emoji no documento.",
        "Emoji como ícone é substituível, desenha diferente em cada sistema e envelhece.",
        "Desenhe o ícone ou use texto.",
        "A interface parece um post de rede social.",
    ),
    _rule(
        "lorem", "Lorem ipsum", "must",
        re.compile(r"lorem ipsum|dolor sit amet", re.I),
        "O documento contém texto latino de exemplo.",
        "Lorem significa que ninguém escreveu o conteúdo ainda.",
        "Escreva o texto real antes de desenhar.",
        "O layout foi composto para um texto que não existe.",
    ),
    _rule(
        "hairline", "Fio de 1 px", "should",
        re.compile(r"border(?:-[a-z]+)?\s*:\s*1px\s+(?:solid|dashed|dotted)", re.I),
        "Há bordas de 1 px separando blocos.",
        "Fios de 1 px são o recurso mais comum de quem não tem hierarquia.",
        "Separe por espaço, cor de fundo ou tipografia.",
        "A página vira uma grade de caixas.", app="off",
    ),
    _rule(
        "pill", "Botão ou navegação em pílula", "should",
        re.compile(r"border-radius\s*:\s*(?:999|9999|999px|9999px|50rem|100vmax)", re.I),
        "Um elemento usa raio máximo de pílula.",
        "A pílula apareceu em 14% dos premiados e 34% dos fracos no estudo.",
        "Use um raio pequeno e consistente com o resto da página.",
        "Botões e etiquetas ficam com a mesma forma.",
    ),
    _rule(
        "shadow", "Sombra em repouso", "should",
        re.compile(r"box-shadow\s*:\s*(?!none\b)[^;}]", re.I),
        "Um elemento tem sombra fora de estado de foco.",
        "Sombra em repouso é um tell: 24% nos premiados e 48% nos fracos.",
        "Prefira borda de baixo contraste ou mudança de superfície; guarde a sombra para o estado elevado.",
        "A página ganha profundidade falsa.",
    ),
    _rule(
        "text-shadow", "Sombra em texto", "should",
        re.compile(r"text-shadow\s*:[^;}]", re.I),
        "O texto tem sombra.",
        "Sombra em texto reduz a legibilidade e é rara em trabalho premiado.",
        "Remova a sombra e garanta contraste no fundo.",
        "O texto parece um título de slide.",
    ),
    _rule(
        "glass", "Vidro fosco", "should",
        re.compile(r"backdrop-filter\s*:", re.I),
        "Há desfoque de fundo atrás de um elemento.",
        "Glassmorphism é o efeito de 2021 que nunca voltou.",
        "Use uma superfície opaca com contraste medido.",
        "O texto perde legibilidade sobre o que passa atrás.",
    ),
    _rule(
        "stock-copy", "Vocabulário de catálogo", "should",
        re.compile(
            r"\b(?:unlock|supercharge|elevate|empower|seamless|effortless|streamline|revolutionize|"
            r"desbloqueie|potencialize|eleve|transforme|revolucione)\b", re.I,
        ),
        "O texto usa verbos e adjetivos de catálogo.",
        "São as palavras que qualquer concorrente poderia imprimir sem mudar nada.",
        "Troque o adjetivo pelo fato: número, material, prazo, lugar.",
        "A página fala como um anúncio genérico.",
    ),
    _rule(
        "cta-copy", "Ação genérica", "nice",
        re.compile(r">\s*(?:saiba mais|clique aqui|comece agora|get started|learn more|leia mais)\s*<", re.I),
        "Um botão ou link usa rótulo genérico.",
        "O rótulo não diz o que acontece ao clicar.",
        "Nomeie a ação pelo resultado.",
        "O botão some no meio dos outros.",
    ),
    _rule(
        "default-font", "Fonte padrão de ferramenta", "nice",
        re.compile(r"font-family\s*:[^;}]*\b(?:Inter|Poppins|Space Grotesk|Instrument Serif|Manrope|Satoshi|Plus Jakarta|DM Sans)\b", re.I),
        "A tipografia usa uma família padrão de gerador.",
        "Essas famílias são ótimas, mas viraram uniforme: aparecem em qualquer página gerada.",
        "Se a marca já usa, mantenha; senão escolha uma família com motivo.",
        "A página parece feita com o mesmo preset de todo mundo.", app="off",
    ),
    _rule(
        "transition-all", "Transição em tudo", "should",
        re.compile(r"transition\s*:\s*all\b", re.I),
        "Uma transição anima todas as propriedades.",
        "Animar tudo faz o layout tremer e custa caro no celular.",
        "Liste as propriedades animadas e use uma curva com saída.",
        "O hover fica pesado e imprevisível.",
    ),
    _rule(
        "ease-in", "Entrada com ease-in", "nice",
        re.compile(r"ease-in\b(?!-out)", re.I),
        "Uma animação usa ease-in.",
        "Ease-in atrasa o movimento no início, quando o olho está acompanhando.",
        "Use ease-out ou uma curva com saída forte.",
        "A interface parece lenta no primeiro instante.",
    ),
    _rule(
        "scale-zero", "Entrada a partir de escala zero", "should",
        re.compile(r"scale(?:3d)?\(\s*0(?:[.,]0+)?\s*[,)]", re.I),
        "Um elemento aparece a partir de escala zero.",
        "Escala zero não tem de onde vir: o objeto deveria existir antes de aparecer.",
        "Comece em 0,96 ou em opacidade, não em zero.",
        "A entrada parece um efeito de slide.",
    ),
    _rule(
        "h-screen", "Altura de viewport", "nice",
        re.compile(r"height\s*:\s*100(?:d|s|l)?vh", re.I),
        "Uma seção usa 100vh como altura.",
        "No celular, 100vh inclui a barra do navegador e corta o conteúdo.",
        "Use min-height: 100svh ou deixe a altura vir do conteúdo.",
        "O herói passa por baixo da barra e esconde a ação.",
    ),
    _rule(
        "bounce", "Curva com ultrapassagem", "should",
        re.compile(r"\bbounce\b|cubic-bezier\([^)]*(?:1\.[1-9]|-[0-9])", re.I),
        "Uma animação usa curva elástica.",
        "Overshoot em interface é ruído, não personalidade.",
        "Use uma curva com saída, entre 150 e 240 ms.",
        "A interface parece um brinquedo.",
    ),
    _rule(
        "outline-none", "Foco removido", "should",
        re.compile(r"outline\s*:\s*(?:none|0)", re.I),
        "O contorno de foco foi removido.",
        "Quem navega por teclado perde a posição na página.",
        "Mantenha o foco visível com :focus-visible e um anel de 2 a 3 px.",
        "A página é impossível de navegar sem mouse.",
    ),
    _rule(
        "important", "!important", "nice",
        re.compile(r"!important", re.I),
        "Uma declaração força prioridade.",
        "!important costuma esconder um conflito de especificidade não resolvido.",
        "Corrija o seletor ou a ordem das camadas.",
        "O CSS fica impossível de manter.",
    ),
    _rule(
        "zindex", "z-index alto", "nice",
        re.compile(r"z-index\s*:\s*(?:[1-9]\d{3,})", re.I),
        "Um elemento usa z-index de quatro dígitos.",
        "Números altos indicam uma guerra de camadas que já foi perdida.",
        "Reorganize o contexto de empilhamento.",
        "Um elemento cobre o outro sem ninguém saber por quê.",
    ),
    _rule(
        "placeholder-data", "Dado de exemplo", "should",
        re.compile(r"\b(?:João Silva|Maria Silva|Fulano|Lorem|placeholder|dados de exemplo|example@example)\b", re.I),
        "A tela usa dado de exemplo como conteúdo.",
        "Dado de exemplo publicado é o defeito mais visível de um app.",
        "Use dado real ou um estado vazio desenhado.",
        "O produto parece um protótipo.", app="same",
    ),
    _rule(
        "framework-blue", "Azul de framework", "should",
        re.compile(r"#(?:0ea5e9|3b82f6|2563eb|1d4ed8|60a5fa)\b", re.I),
        "A tela usa o azul padrão de framework de interface.",
        "O azul de framework é a cor que aparece quando ninguém escolheu uma.",
        "Defina o acento do produto e meça o contraste.",
        "A tela parece um painel de demonstração.", app="same",
    ),
    _rule(
        "em-dash", "Travessão em excesso", "nice",
        re.compile(r"—"),
        "O documento usa travessão como pontuação padrão.",
        "Um ou dois leem como escrita; dez leem como modelo.",
        "Troque por ponto final ou vírgula.",
        "O texto entrega que foi gerado.", threshold=4, counter=True,
    ),
)

RULE_INDEX = {rule.id: rule for rule in RULES}
MAX_RULE_HITS = 3


def _blank_block(match: re.Match[str]) -> str:
    return "\n" * match.group(0).count("\n")


def _strip_exempt(source: str) -> tuple[str, int]:
    """Remove blocos isentos preservando as linhas; devolve o número de isenções."""
    escaped = 0
    lines = []
    for line in source.split("\n"):
        if "taste-skill-ignore" in line:
            escaped += 1
            lines.append("")
        else:
            lines.append(line)
    cleaned = "\n".join(lines)
    for pattern in (
        re.compile(r"<pre\b[^>]*>.*?</pre>", re.I | re.S),
        re.compile(r"<code\b[^>]*>.*?</code>", re.I | re.S),
        re.compile(r"<table\b[^>]*>.*?</table>", re.I | re.S),
        re.compile(r"<form\b[^>]*>.*?</form>", re.I | re.S),
        re.compile(r"<[a-z][^>]*\bdata-ui\b[^>]*>.*?</[a-z]+>", re.I | re.S),
        re.compile(r"<!--.*?-->", re.S),
        re.compile(r"/\*.*?\*/", re.S),
    ):
        cleaned, count = pattern.subn(_blank_block, cleaned)
        escaped += count
    return cleaned, escaped


def lint_page(*, source: str, surface: str = "page", mode: str = "full") -> dict[str, Any]:
    """Varre HTML/CSS/JS declarado contra as regras caseiras de gosto."""
    _mode(mode)
    if not source.strip():
        raise TasteError("Cole o HTML ou o CSS da página para a varredura.")
    if len(source) > MAX_HTML_CHARS:
        raise TasteError(f"A fonte excede {MAX_HTML_CHARS:,} caracteres.".replace(",", "."))
    if surface not in {"page", "app"}:
        raise TasteError("Superfície inválida: use page ou app.")
    findings: list[dict[str, Any]] = []
    cleaned, escaped = _strip_exempt(source)
    lines = cleaned.split("\n")

    def add(*args: str) -> None:
        findings.append(finding(*args))

    hits: list[dict[str, Any]] = []
    skipped_by_app: list[str] = []
    for rule in RULES:
        if surface == "app" and rule.app == "off":
            skipped_by_app.append(rule.id)
            continue
        severity = rule.severity
        if surface == "app" and rule.app == "warn" and severity == "must":
            severity = "should"
        matches = list(rule.pattern.finditer(cleaned))
        if rule.counter:
            if len(matches) <= rule.threshold:
                continue
        elif not matches:
            continue
        locations: list[int] = []
        samples: list[str] = []
        for match in matches[:MAX_RULE_HITS]:
            line_number = cleaned.count("\n", 0, match.start()) + 1
            locations.append(line_number)
            excerpt = lines[line_number - 1].strip() if 0 <= line_number - 1 < len(lines) else ""
            samples.append(excerpt[:120] or match.group(0)[:120])
        count = len(matches)
        where = "linha " + ", ".join(str(number) for number in locations)
        if count > len(locations):
            where += f" · {count} ocorrências"
        add(severity, rule.id, rule.title, where, rule.what,
            rule.problem, rule.fix, rule.if_skipped)
        hits.append({
            "rule": rule.id, "title": rule.title, "severity": severity, "count": count,
            "lines": locations, "samples": samples,
        })

    h1 = len(re.findall(r"<h1\b", cleaned, re.I))
    images = len(re.findall(r"<img\b", cleaned, re.I))
    if re.search(r"<html\b|<body\b", source, re.I):
        if h1 == 0:
            add("must", "no-h1", "Sem título principal", "documento",
                "O documento não tem nenhum `<h1>`.",
                "Sem título, a página não responde o que é isto — nem para o leitor, nem para o leitor de tela.",
                "Escreva um `<h1>` com o argumento da primeira tela.", "A página começa sem hierarquia.")
            hits.append({"rule": "no-h1", "title": "Sem título principal", "severity": "must", "count": 1, "lines": [], "samples": ["<h1> ausente"]})
        if images < 4:
            add("should", "few-images", "Menos de quatro imagens", f"{images} imagens",
                "O documento tem menos de quatro imagens.",
                "O estudo pede piso de quatro imagens reais; a mediana é de seis a doze.",
                "Acrescente imagens do assunto, não ilustrações genéricas.",
                "A página é feita só de texto e cor.")
            hits.append({"rule": "few-images", "title": "Menos de quatro imagens", "severity": "should", "count": max(1, 4 - images), "lines": [], "samples": [f"{images} imagens"]})
    if surface == "app" and len(cleaned) > 2000:
        add("nice", "app-surface", "Superfície de aplicativo", "modo app",
            "As regras de fio, mono, numeração e fonte padrão foram desligadas.",
            "Tela de app usa densidade e mono por função; o que sobra é hierarquia e cor.",
            "Rode também na versão de página quando houver uma.",
            "A comparação com landing page fica injusta.")

    metrics = {
        "lines": len(lines), "rules": len(RULES) - len(skipped_by_app), "hits": len(hits),
        "rulesHit": len({item["rule"] for item in hits}),
        "must": sum(1 for item in hits if item["severity"] == "must"),
        "should": sum(1 for item in hits if item["severity"] == "should"),
        "nice": sum(1 for item in hits if item["severity"] == "nice"),
        "escapes": escaped, "images": images, "h1": h1,
        "skipped": len(skipped_by_app),
    }
    questions = [
        "Cada acento visual desta página tem um motivo que não seja 'fica bonito'?",
        "As imagens mostram o assunto real ou são ilustrações que serviriam a qualquer marca?",
        "O que nesta página só poderia existir para este cliente?",
    ]
    limitations = [
        "A varredura é lexical: blocos isentos (`<pre>`, `<code>`, tabelas, formulários, `data-ui`, comentários e `taste-skill-ignore`) são removidos antes.",
        "Nada é renderizado: layout, quebra de linha, contraste real e movimento não são medidos.",
        "Regras por padrão de texto têm falso positivo (por exemplo, a palavra 'índigo' em uma redação).",
        "Nenhum arquivo é escrito, compilado ou publicado, e nenhum script do upstream é executado.",
    ]
    summary = [
        f"**Superfície:** {surface} · {len(RULES) - len(skipped_by_app)} regras · {len(hits)} regra(s) acionada(s) · {escaped} isenção(ões).",
        f"**Documento:** {len(lines)} linhas · {h1} `<h1>` · {images} imagens · modo `{mode}`.",
    ]
    findings, counts, verdict_text, questions = finalize(findings, mode, questions)
    extra = ["", "## Regras acionadas", "", "| Regra | Grupo | Ocorrências | Linhas | Amostra |", "|---|---|---|---|---|"]
    extra += [
        f"| {item['title']} (`{item['rule']}`) | {item['severity']} | {item['count']} | "
        f"{', '.join(str(number) for number in item['lines']) or '—'} | {item['samples'][0][:80] if item['samples'] else '—'} |"
        for item in hits
    ]
    clean = [rule.id for rule in RULES if rule.id not in {item["rule"] for item in hits} and rule.id not in skipped_by_app]
    extra += ["", "## Regras sem ocorrência", "", ", ".join(f"`{item}`" for item in clean) if clean else "Todas as regras acionadas."]
    if skipped_by_app:
        extra += ["", "## Desligadas no modo app", "", ", ".join(f"`{item}`" for item in skipped_by_app)]
    return common(
        analysis="lint", mode=mode, title="Regras caseiras", summary=summary,
        findings=findings, counts=counts, verdict=verdict_text, questions=questions, rows=hits,
        metrics=metrics, limitations=limitations, extra_sections=extra,
    )


# ----------------------------------------------------------------------- tells

WAVES: dict[int, tuple[str, str]] = {
    1: ("Onda 1 · 2023", "vidro, gradiente roxo e ícone genérico"),
    2: ("Onda 2 · 2024–2025", "micro-rótulo, numeração, fio de 1 px e mobília editorial"),
    3: ("Onda 3 · 2026", "creme e terracota, serifa apertada e manchete-parágrafo"),
}


@dataclass(frozen=True)
class Tell:
    id: str
    wave: int
    kind: str
    name: str
    pattern: Pattern[str]
    what: str
    problem: str
    fix: str
    if_skipped: str
    severity: str = "should"
    validate: Any = None


_TRICOLON = re.compile(
    r"(?m)(?:^|[.!?]\s+)([A-ZÀ-Ú][^.!?<>{}\n]{2,30})\.\s+([A-ZÀ-Ú][^.!?<>{}\n]{2,30})\.\s+([A-ZÀ-Ú][^.!?<>{}\n]{2,30})\."
)


def _short_trio(match: re.Match[str]) -> bool:
    return all(len(part.split()) <= 4 for part in match.groups())


TELLS: tuple[Tell, ...] = (
    Tell(
        "glass", 1, "visual", "Vidro fosco",
        re.compile(r"backdrop-filter\s*:", re.I),
        "Um painel usa desfoque de fundo.",
        "O vidro fosco de 2021 virou sinônimo de template de agência.",
        "Troque por superfície opaca e contraste medido.",
        "O texto perde legibilidade sobre o que passa atrás.",
    ),
    Tell(
        "purple-gradient", 1, "visual", "Gradiente roxo",
        re.compile(r"(?:linear|radial|conic)-gradient\([^)]*(?:#6366f1|#8b5cf6|#a855f7|#7c3aed|#4f46e5)", re.I),
        "O gradiente usa a família violeta do produto de IA.",
        "Nenhum site premiado no estudo usava botão violeta; é a cor padrão de ferramenta.",
        "Troque pelo acento da marca.",
        "A página parece um painel de IA de 2023.", severity="should",
    ),
    Tell(
        "icon-cards", 1, "codigo", "Grade de cards com ícone",
        re.compile(r"class=[\"'][^\"']*(?:feature-card|icon-card|card-icon|feature-grid|benefit-card)", re.I),
        "Os recursos são apresentados em cards com ícone.",
        "Cards de ícone em três colunas aparecem em 28% dos sites fracos e 1% dos premiados.",
        "Apresente cada recurso como argumento e prova, sem moldura.",
        "A seção vira uma grade que qualquer template produz.",
    ),
    Tell(
        "mockup-hero", 1, "codigo", "Mockup no herói",
        re.compile(r"(?:hero|mockup)[^>]{0,80}>(?:\s*<[^>]+>){0,3}\s*<img[^>]+(?:mockup|screenshot|dashboard)", re.I),
        "O herói é dominado por um mockup de produto.",
        "O mockup mostra uma tela que não é a sua e esconde o que a página faz.",
        "Mostre a interface real ou uma cena do assunto.",
        "O visitante vê uma promessa, não o produto.",
    ),
    Tell(
        "emoji-title", 1, "codigo", "Emoji no título",
        re.compile(r"<h[12][^>]*>[^<]{0,120}[\U0001F300-\U0001FAFF\u2600-\u27BF]", re.I),
        "Um título inclui emoji.",
        "Emoji no título é o atalho de personalidade mais datado.",
        "Troque por palavra ou por ícone desenhado.",
        "O título envelhece a cada atualização do sistema.",
    ),
    Tell(
        "unlock", 1, "texto", "Verbo de desbloqueio",
        re.compile(r"\b(?:unlock|supercharge|elevate|empower|effortless|seamless|desbloqueie|potencialize|eleve)\b", re.I),
        "O texto usa verbos de desbloqueio e superalimentação.",
        "São as palavras que todo gerador escolhe quando não tem fato.",
        "Troque pelo resultado concreto: quanto tempo, quanto custa, o que muda.",
        "A promessa não pode ser verificada.",
    ),
    Tell(
        "eyebrow", 2, "codigo", "Sobrancelha editorial",
        re.compile(r"class=[\"'][^\"']*(?:eyebrow|kicker|overline|pretitle|field-notes)", re.I),
        "Uma etiqueta pequena precede o título.",
        "O kicker é a mobília editorial que o estudo encontra em página gerada.",
        "Apague a etiqueta; o título já é o começo.",
        "A página abre com um sussurro.",
    ),
    Tell(
        "numbering", 2, "codigo", "Numeração 01/02/03",
        re.compile(r">\s*0[1-9]\s*[./·—–-]|<span[^>]*>\s*0[1-9]\s*</span>", re.I),
        "Itens ou seções usam zero à esquerda.",
        "Numeração decorativa finge um sistema que não existe.",
        "Remova o zero; se a ordem importa, use passos reais.",
        "O conteúdo parece um índice de revista.",
    ),
    Tell(
        "hairline", 2, "codigo", "Fio de 1 px",
        re.compile(r"border(?:-[a-z]+)?\s*:\s*1px\s+solid", re.I),
        "Blocos são separados por fios de 1 px.",
        "Fios são o recurso de quem não tem hierarquia nem contraste de superfície.",
        "Separe por espaço, fundo ou tipografia.",
        "A página vira uma grade de caixas.",
    ),
    Tell(
        "mono-label", 2, "codigo", "Mono decorativa",
        re.compile(r"\.(?:label|caption|meta|tag|eyebrow)[^{]{0,40}\{[^}]{0,200}font-family\s*:[^;}]*mono", re.I | re.S),
        "Um rótulo usa fonte monoespaçada como estilo.",
        "Mono fora de código é fantasia de portfólio.",
        "Reserve mono para números tabulares e código.",
        "O rótulo parece um terminal.",
    ),
    Tell(
        "shadow-rest", 2, "visual", "Sombra em repouso",
        re.compile(r"box-shadow\s*:\s*0\s+[1-9]\d*px", re.I),
        "Um cartão tem sombra mesmo sem elevação.",
        "Sombra em repouso aparece em 48% dos fracos e 24% dos premiados.",
        "Troque por borda baixa ou superfície levemente diferente.",
        "A página ganha profundidade falsa.",
    ),
    Tell(
        "status-dot", 2, "codigo", "Ponto de status",
        re.compile(r"class=[\"'][^\"']*(?:status-dot|pulse-dot|live-dot|online-dot)|width\s*:\s*6px\s*;\s*height\s*:\s*6px\s*;\s*border-radius\s*:\s*50%", re.I),
        "Um ponto colorido indica status ou disponibilidade.",
        "O ponto verde de 'disponível' é mobília de página gerada e raramente é real.",
        "Mostre o estado por texto ou remova.",
        "A página promete um serviço que talvez não exista.",
    ),
    Tell(
        "est-year", 2, "texto", "Ano de fundação na mobília",
        re.compile(r"\bEst\.?\s*20\d{2}\b|\b©\s*20\d{2}\b|\bdesde\s+20\d{2}\b", re.I),
        "O texto usa 'Est. 20xx', '© 20xx' ou 'desde 20xx' como personalidade.",
        "É a mobília que tenta dar idade a uma página nova.",
        "Se a idade for real, ela vira prova; se não, apague.",
        "O ano contradiz a própria página.",
    ),
    Tell(
        "coordinates", 2, "texto", "Coordenadas geográficas",
        re.compile(r"\d{1,3}\.\d{1,}°\s*[NS]|\b-?\d{1,3}\.\d{4,}\s*[,;]\s*-?\d{1,3}\.\d{4,}"),
        "O texto exibe coordenadas para localizar o negócio.",
        "Coordenada é enfeite de portfólio: ninguém navega por grau decimal.",
        "Diga o bairro e a rua; coordenada só em link de mapa.",
        "O endereço fica mais difícil de usar.",
    ),
    Tell(
        "tricolon", 2, "texto", "Tudo em trio",
        _TRICOLON,
        "O texto encadeia três frases curtas e paralelas.",
        "O trio é a cadência que os modelos escolhem quando não têm argumento.",
        "Corte duas frases e desenvolva a mais forte.",
        "O texto soa como slogan.", validate=_short_trio,
    ),
    Tell(
        "not-x-but-y", 2, "texto", "Não é X, é Y",
        re.compile(r"n[ãa]o\s+[ée]\s+(?:s[óo]|apenas|somente)[^.]{1,50}[,;—–-]\s*[ée]\b|more than just\b|mais que um[a]?\b", re.I),
        "O texto nega uma categoria para se definir.",
        "A correção é o título mais gerado da década.",
        "Afirme o que a coisa é.",
        "O leitor precisa entender o que você nega antes de entender você.",
    ),
    Tell(
        "micro-caps", 2, "codigo", "Micro-rótulo em caixa alta",
        re.compile(r"\{[^}]{0,240}text-transform\s*:\s*uppercase[^}]{0,240}\}", re.I),
        "Um bloco aplica caixa alta com tracking a um texto curto.",
        "Micro-caps aparece em 57% dos fracos e 16% dos premiados.",
        "Use frase normal com peso.",
        "O rótulo grita e some.",
    ),
    Tell(
        "cream-terracotta", 3, "visual", "Creme e terracota",
        re.compile(r"(?=[\s\S]{0,4000}#(?:d97757|c2634a|e07a5f|cc7a5c)\b)(?=[\s\S]{0,4000}#(?:f0eee6|faf9f5|f5f1ea|f7f3ec)\b)", re.I),
        "A paleta combina terracota com creme.",
        "É o uniforme de 2026: aparece em toda landing page feita pelo mesmo modelo.",
        "Mantenha só se for a cor real da marca; troque o creme por branco ou cinza.",
        "A página se confunde com as outras.",
    ),
    Tell(
        "serif-tight", 3, "codigo", "Serifa apertada",
        re.compile(r"font-family\s*:[^;}]*serif[^}]{0,160}letter-spacing\s*:\s*-0\.0[3-6]em", re.I | re.S),
        "Uma serifa de display é comprimida com tracking negativo.",
        "A combinação serifa alta e tracking apertado é a assinatura de 2026.",
        "Só use se a marca tiver essa voz; caso contrário, mexa no peso e no corpo.",
        "O título parece renderizado por um preset.",
    ),
    Tell(
        "headline-paragraph", 3, "codigo", "Manchete-parágrafo",
        re.compile(r"<h1[^>]*>\s*([^<]{44,})</h1>", re.I),
        "O `<h1>` tem mais de 42 caracteres.",
        "Acima de duas linhas o título vira parágrafo e perde a função.",
        "Corte para quatro a seis palavras.",
        "No celular o título ocupa meia tela.",
    ),
    Tell(
        "colon-brand", 3, "codigo", "Marca antes dos dois-pontos",
        re.compile(r"<h1[^>]*>\s*[A-Z][\wÀ-ú\s]{1,18}:\s", re.I),
        "O título começa com o nome da marca e dois-pontos.",
        "O nome já está na navegação; o título gasta metade do orçamento repetindo.",
        "Comece pela descrição.",
        "O título não diz nada novo.",
    ),
    Tell(
        "styled-word", 3, "codigo", "Palavra estilizada",
        re.compile(r"<h[12][^>]*>[^<]{0,80}<(?:em|i|span)[^>]*class=[\"'][^\"']*(?:accent|italic|serif|highlight)", re.I),
        "Uma palavra do título recebe estilo próprio.",
        "Destacar uma palavra do título é o truque de 2026 para parecer autoral.",
        "Mude a frase em vez de pintar uma palavra.",
        "O título tem dois registros e nenhum motivo.",
    ),
    Tell(
        "gradient-drift", 3, "codigo", "Gradiente em movimento",
        re.compile(r"@keyframes[^{]{0,60}\{[^}]{0,200}background-position", re.I | re.S),
        "Um gradiente se move em loop.",
        "Movimento de gradiente é decoração que consome bateria e atenção.",
        "Remova o loop; se houver movimento, ele deve significar algo.",
        "A página pulsa sem comunicar.",
    ),
    Tell(
        "reveal", 3, "codigo", "Revelação no scroll",
        re.compile(r"class=[\"'][^\"']*(?:reveal|fade-in|scroll-in)|IntersectionObserver", re.I),
        "Elementos aparecem conforme o scroll.",
        "Revelar tudo no scroll é o gesto padrão de 2026 e atrasa a leitura.",
        "Deixe o conteúdo visível; anime só o que precisa de explicação.",
        "O visitante rola por uma página vazia.",
    ),
    Tell(
        "editorial-furniture", 3, "texto", "Mobília editorial",
        re.compile(r"\b(?:Vol\.|Volume)\s*\d{1,2}\b|\bEdi[çc][ãa]o\s*\d{1,3}\b|\bArquivo\s*\d{1,2}\b|\bIndex\s*\d{1,2}\b"),
        "A página usa volume, edição ou arquivo numerado.",
        "A mobília editorial dá ares de revista a uma página sem periodicidade.",
        "Use a mobília só se existir uma série real.",
        "O número não significa nada.",
    ),
)

TELL_INDEX = {tell.id: tell for tell in TELLS}
TELL_KINDS = {"todos": None, "texto": "texto", "visual": "visual", "codigo": "codigo", "código": "codigo"}


def audit_tells(*, text: str, kind: str = "todos", mode: str = "full") -> dict[str, Any]:
    """Reconhece motivos datados no material declarado e devolve o registro."""
    _mode(mode)
    if not text.strip():
        raise TasteError("Cole o texto ou a fonte a ser confrontada com o registro de tells.")
    if len(text) > MAX_HTML_CHARS:
        raise TasteError(f"O material excede {MAX_HTML_CHARS:,} caracteres.".replace(",", "."))
    kind_key = TELL_KINDS.get(_norm(kind), "invalid")
    if kind_key == "invalid":
        raise TasteError("Tipo inválido: use todos, texto, visual ou codigo.")

    findings: list[dict[str, Any]] = []
    lines = text.split("\n")

    def add(*args: str) -> None:
        findings.append(finding(*args))

    hits: list[dict[str, Any]] = []
    for tell in TELLS:
        if kind_key and tell.kind != kind_key:
            continue
        matches = [match for match in tell.pattern.finditer(text) if tell.validate is None or tell.validate(match)]
        if not matches:
            continue
        locations: list[int] = []
        samples: list[str] = []
        for match in matches[:3]:
            line_number = text.count("\n", 0, match.start()) + 1
            locations.append(line_number)
            excerpt = lines[line_number - 1].strip() if line_number - 1 < len(lines) else ""
            samples.append(excerpt[:130] or match.group(0)[:130])
        wave_label, wave_hint = WAVES[tell.wave]
        add(
            tell.severity, tell.id, tell.name, f"{wave_label} · linha {', '.join(str(item) for item in locations)}",
            f"{tell.what} Amostra: `{samples[0][:100]}`.",
            f"{tell.problem} É um tell da {wave_label.lower()} ({wave_hint}).",
            tell.fix, tell.if_skipped,
        )
        hits.append({
            "id": tell.id, "name": tell.name, "wave": tell.wave, "waveLabel": wave_label,
            "kind": tell.kind, "count": len(matches), "lines": locations, "samples": samples,
        })

    words = max(1, len(re.findall(r"\S+", text)))
    per_k = round(len(hits) * 1000 / words, 1)
    wave_counts = {wave: sum(1 for hit in hits if hit["wave"] == wave) for wave in WAVES}
    dominant = max(wave_counts, key=lambda wave: wave_counts[wave]) if hits else 0
    if not hits:
        verdict_text = "Nenhum tell do registro aparece no material declarado."
    else:
        verdict_text = (
            f"{len(hits)} tell(s) do registro: {wave_counts[3]} da onda 3, {wave_counts[2]} da onda 2, "
            f"{wave_counts[1]} da onda 1. O material fala a língua de {WAVES[dominant][0].split(' · ')[1]}."
        )
    serialized = {item["id"] for item in hits}
    report = [f"# Registro de tells", "", f"**Material:** {words} palavras · {len(hits)} tell(s) · tipo `{kind_key or 'todos'}`.", "", f"**Veredito:** {verdict_text}"]
    if hits:
        report += ["", "## Motivos reconhecidos", "", "| Tell | Onda | Tipo | Ocorrências | Amostra |", "|---|---|---|---|---|"]
        report += [
            f"| {hit['name']} (`{hit['id']}`) | {hit['waveLabel']} | {hit['kind']} | {hit['count']} | {hit['samples'][0][:80]} |"
            for hit in hits
        ]
    report += ["", "## Registro completo", "", "| Tell | Onda | Tipo | Contramedida |", "|---|---|---|---|"]
    report += [
        f"| {tell.name} (`{tell.id}`) | {WAVES[tell.wave][0]} | {tell.kind} | {tell.fix} |"
        for tell in TELLS
        if not kind_key or tell.kind == kind_key
    ]
    report += ["", "## Não verificado", "",
               "- A varredura é lexical: motivos puramente de composição, como margem desigual, não são vistos.",
               "- O registro é datado por onda, não por site: um motivo pode ser legítimo quando é a voz real da marca.",
               "- Nada é renderizado ou comparado com o estudo original de 247 sites."]
    metrics = {
        "catalog": len(TELLS), "hits": len(hits), "wave1": wave_counts[1], "wave2": wave_counts[2],
        "wave3": wave_counts[3], "dominant": WAVES[dominant][0] if dominant else "—",
        "perK": per_k, "words": words, "unused": len(TELLS) - len(serialized),
    }
    rows = hits
    return {
        "analysis": "tells", "mode": mode, "metrics": metrics, "rows": rows,
        "findings": findings, "counts": {"must": 0, "should": sum(1 for item in findings if item["group"] == "should"), "nice": sum(1 for item in findings if item["group"] == "nice"), "total": len(findings)},
        "verdict": verdict_text, "questions": [], "executed": False, "readOnly": True,
        "markdown": "\n".join(report), "limitations": [],
        "catalog": [
            {"id": tell.id, "name": tell.name, "wave": tell.wave, "waveLabel": WAVES[tell.wave][0],
             "kind": tell.kind, "fix": tell.fix, "found": tell.id in serialized}
            for tell in TELLS
        ],
        "waves": [{"wave": wave, "label": WAVES[wave][0], "hint": WAVES[wave][1], "count": wave_counts[wave],
                   "tells": [tell.name for tell in TELLS if tell.wave == wave]} for wave in WAVES],
    }
