"""Estúdio de design estático inspirado em nexu-io/open-design (Apache-2.0).

Implementação própria e determinística. Nenhum daemon, CLI, plugin, MCP,
runtime de agente, Docker ou provedor do upstream é instalado ou executado.
As skills leem contratos de design declarados pelo usuário (manifesto,
`DESIGN.md`, `tokens.css`, pares de contraste, notas de crítica e um artefato
HTML) e devolvem candidatos com evidência, veredito e limites explícitos.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .review import common, finalize, finding

MAX_TOKENS_CHARS = 120_000
MAX_DESIGN_CHARS = 120_000
MAX_MANIFEST_CHARS = 20_000
MAX_ARTIFACT_CHARS = 200_000
MAX_ROWS = 120
MAX_FIELD_CHARS = 400
CANONICAL_SCHEMA = "od-design-system-project/v1"
MIN_H2 = 7

# Camadas: A1 sem fallback, A2 com fallback declarado, B slot de consistência.
TOKEN_GROUPS: tuple[tuple[str, str, tuple[tuple[str, str, str], ...]], ...] = (
    ("surface", "Superfícies", (
        ("--bg", "A1", "fundo da página, define a tela da marca"),
        ("--surface", "A1", "fundo de cartão ou contêiner elevado"),
        ("--surface-warm", "B", "terceiro nível de superfície; pode apontar para var(--surface)"),
    )),
    ("text", "Texto", (
        ("--fg", "A1", "cor primária de texto"),
        ("--fg-2", "B", "segundo nível de texto; pode apontar para var(--fg)"),
        ("--muted", "A1", "legendas e texto secundário"),
        ("--meta", "B", "metadados; pode apontar para var(--muted)"),
    )),
    ("border", "Bordas", (
        ("--border", "A1", "borda padrão de cartão"),
        ("--border-soft", "B", "separador interno discreto; pode apontar para var(--border)"),
    )),
    ("accent", "Acento", (
        ("--accent", "A1", "cor de marca, no máximo dois usos visíveis por tela"),
        ("--accent-on", "A2", "cor de texto quando o acento é o fundo"),
        ("--accent-hover", "A2", "estado de hover sobre o acento"),
        ("--accent-active", "A2", "estado pressionado sobre o acento"),
    )),
    ("semantic", "Estados semânticos", (
        ("--success", "A2", "sucesso"),
        ("--warn", "A2", "atenção"),
        ("--danger", "A2", "erro"),
    )),
    ("fonts", "Famílias tipográficas", (
        ("--font-display", "A1", "fonte de títulos e display"),
        ("--font-body", "A1", "fonte de corpo"),
        ("--font-mono", "A2", "fonte monoespaçada para código e métricas"),
    )),
    ("scale", "Escala tipográfica", (
        ("--text-xs", "A1", "degrau extra pequeno, cerca de 11–12px"),
        ("--text-sm", "A1", "degrau pequeno, cerca de 12–14px"),
        ("--text-base", "A1", "corpo base"),
        ("--text-lg", "A1", "subtítulo ou corpo destacado"),
        ("--text-xl", "A1", "título de nível 2"),
        ("--text-2xl", "A1", "título de seção"),
        ("--text-3xl", "A1", "título principal"),
        ("--text-4xl", "A1", "display ou herói"),
    )),
    ("rhythm", "Entrelinha e kerning", (
        ("--leading-body", "A1", "entrelinha de leitura"),
        ("--leading-tight", "A1", "entrelinha de títulos"),
        ("--tracking-display", "A1", "espaçamento entre letras em display"),
    )),
    ("space", "Espaçamento", (
        ("--space-1", "A2", "4px"),
        ("--space-2", "A2", "8px"),
        ("--space-3", "A2", "12px"),
        ("--space-4", "A2", "16px"),
        ("--space-5", "A2", "20px"),
        ("--space-6", "A2", "24px"),
        ("--space-8", "A2", "32px"),
        ("--space-12", "A2", "48px"),
    )),
    ("section", "Ritmo de seção", (
        ("--section-y-desktop", "A1", "respiro vertical entre seções no desktop"),
        ("--section-y-tablet", "A1", "respiro vertical entre seções no tablet"),
        ("--section-y-phone", "A1", "respiro vertical entre seções no celular"),
    )),
    ("radius", "Raios", (
        ("--radius-sm", "A2", "botões, campos e chips"),
        ("--radius-md", "A2", "cartões e modais"),
        ("--radius-lg", "A2", "contêineres em destaque"),
        ("--radius-pill", "A2", "avatares e selos"),
    )),
    ("elevation", "Elevação e foco", (
        ("--elev-flat", "A2", "sem elevação"),
        ("--elev-ring", "A2", "anel de 1px"),
        ("--elev-raised", "A2", "superfície elevada"),
        ("--focus-ring", "A2", "indicador de foco por teclado"),
    )),
    ("motion", "Movimento", (
        ("--motion-fast", "A2", "micro-estado e hover"),
        ("--motion-base", "A2", "mudança de estado geral"),
        ("--ease-standard", "A2", "curva padrão, ease-out forte"),
    )),
    ("layout", "Layout", (
        ("--container-max", "A1", "largura máxima do conteúdo"),
        ("--container-gutter-desktop", "A1", "goteira lateral no desktop"),
        ("--container-gutter-tablet", "A1", "goteira lateral no tablet"),
        ("--container-gutter-phone", "A1", "goteira lateral no celular"),
    )),
)

SCHEMA_TOKENS: tuple[str, ...] = tuple(
    name for _key, _label, tokens in TOKEN_GROUPS for name, _layer, _description in tokens
)
SCHEMA_SET = set(SCHEMA_TOKENS)
REQUIRED_BY_GROUP = {
    key: tuple(name for name, _layer, _description in tokens) for key, _label, tokens in TOKEN_GROUPS
}
THEME_MUST = ("--bg", "--fg")

DIMENSIONS: tuple[tuple[str, str, str, str], ...] = (
    ("filosofia", "Filosofia", "Uma direção clara sustenta cada micro-decisão?", "Três estilos brigando = 0–4; deriva em páginas de borda = 7–8."),
    ("hierarquia", "Hierarquia", "Um estranho sabe o que ler primeiro, sem legenda?", "Tudo grita = 0–4; camadas claras com colisão ocasional = 7–8."),
    ("detalhe", "Detalhe", "Alinhamento, entrelinha, enquadramento e polimento de borda.", "Fita e barbante à vista = 0–4; dois ou três deslizes com olho treinado = 7–8."),
    ("funcao", "Função", "O artefato cumpre o trabalho para o qual existe?", "Bonito e inútil = 0–4; robusto no uso normal = 7–8."),
    ("inovacao", "Inovação", "Existe um momento que faz alguém se inclinar?", "Mediano de IA = 0–4; um momento memorável = 7–8."),
)
DIMENSION_ALIASES = {
    "filosofia": "filosofia", "philosophy": "filosofia", "direcao": "filosofia", "direção": "filosofia",
    "hierarquia": "hierarquia", "hierarchy": "hierarquia",
    "detalhe": "detalhe", "detail": "detalhe", "execucao": "detalhe", "execução": "detalhe",
    "funcao": "funcao", "função": "funcao", "function": "funcao", "functionality": "funcao",
    "inovacao": "inovacao", "inovação": "inovacao", "innovation": "inovacao",
}
BANDS = ((0, 4, "Quebrado"), (5, 6, "Funcional"), (7, 8, "Forte"), (9, 10, "Excepcional"))

_CITATION = re.compile(
    r"(?:#[\w-]+|\.[A-Za-z][\w-]*|linha\s*\d+|p[áa]gina\s*\d+|page\s*\d+|[\w-]+\.(?:html|css|md|tsx?|jsx?)\b|\d+px|var\(--|<h[1-6]|class=)",
    re.I,
)
_HEX3 = re.compile(r"^#[0-9a-fA-F]{3}$")
_HEX6 = re.compile(r"^#[0-9a-fA-F]{6}$")


class StudioError(ValueError):
    """Erro esperado do estúdio de design, seguro para o usuário."""


def _norm(value: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return text.strip().lower()


def _lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _cells(text: str, expected: int, label: str, limit: int = MAX_ROWS) -> list[tuple[int, list[str]]]:
    if not text.strip():
        raise StudioError(f"Informe ao menos {label}.")
    rows: list[tuple[int, list[str]]] = []
    for number, raw in enumerate(_lines(text), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        cells = [cell.strip() for cell in stripped.split("|")]
        if len(cells) > expected:
            raise StudioError(f"Linha {number}: use no máximo {expected} campos separados por |.")
        if any(len(cell) > MAX_FIELD_CHARS for cell in cells):
            raise StudioError(f"Linha {number}: cada campo deve ter até {MAX_FIELD_CHARS} caracteres.")
        cells += [""] * (expected - len(cells))
        rows.append((number, cells))
    if not rows:
        raise StudioError(f"Informe ao menos {label}.")
    if len(rows) > limit:
        raise StudioError(f"A entrada tem {len(rows)} linhas; o limite é {limit}.")
    return rows


def _mode(mode: str) -> None:
    if mode not in {"lite", "full", "ultra"}:
        raise StudioError("Nível inválido: use lite, full ou ultra.")


# ---------------------------------------------------------------- contrato


def _parse_css(css: str) -> tuple[dict[str, str], dict[str, dict[str, str]], list[tuple[str, str]]]:
    """Devolve `(:root, temas, blocos de componente)` do CSS declarado."""
    stripped = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    root: dict[str, str] = {}
    themes: dict[str, dict[str, str]] = {}
    components: list[tuple[str, str]] = []
    stack: list[tuple[str, list[str]]] = []
    buffer: list[str] = []
    for char in stripped:
        if char == "{":
            selector = "".join(buffer).strip()
            normalized = " ".join(selector.split())[-160:]
            stack.append((normalized, []))
            buffer = []
        elif char == "}":
            if not stack:
                buffer = []
                continue
            selector, body = stack.pop()
            body_text = "".join(body)
            declarations = {
                name.lower(): value.strip()
                for name, value in re.findall(r"(--[A-Za-z0-9_-]+)\s*:\s*([^;{}]*)", body_text)
            }
            lowered = selector.lower()
            if "data-theme" in lowered or lowered in {".dark", ":root.dark"}:
                key = "dark" if "dark" in lowered else selector
                themes.setdefault(key, {}).update(declarations)
            elif ":root" in lowered:
                root.update(declarations)
            elif not selector.startswith("@"):
                components.append((selector, body_text))
            buffer = []
        elif stack:
            stack[-1][1].append(char)
        else:
            buffer.append(char)
    return root, themes, components


def _h2_sections(markdown: str) -> list[tuple[str, int]]:
    sections: list[list[Any]] = []
    for line in _lines(markdown):
        if re.match(r"^##\s+\S", line):
            sections.append([line[2:].strip(), 0])
        elif sections and line.strip() and not line.startswith("#"):
            sections[-1][1] += len(line.strip())
    return [(str(title), int(content)) for title, content in sections]


def audit_contract(
    *,
    manifest: str = "",
    design: str = "",
    tokens: str = "",
    mode: str = "full",
) -> dict[str, Any]:
    _mode(mode)
    if not tokens.strip() and not design.strip() and not manifest.strip():
        raise StudioError("Informe ao menos um dos três arquivos: manifest.json, DESIGN.md ou tokens.css.")
    if len(tokens) > MAX_TOKENS_CHARS:
        raise StudioError(f"tokens.css excede {MAX_TOKENS_CHARS:,} caracteres.".replace(",", "."))
    if len(design) > MAX_DESIGN_CHARS:
        raise StudioError(f"DESIGN.md excede {MAX_DESIGN_CHARS:,} caracteres.".replace(",", "."))
    if len(manifest) > MAX_MANIFEST_CHARS:
        raise StudioError(f"manifest.json excede {MAX_MANIFEST_CHARS:,} caracteres.".replace(",", "."))

    findings: list[dict[str, Any]] = []
    raw_colors: list[tuple[int, str]] = []

    def add(*args: str) -> None:
        findings.append(finding(*args))

    # ---- manifesto
    payload: dict[str, Any] = {}
    if manifest.strip():
        try:
            parsed = json.loads(manifest)
        except json.JSONDecodeError as exc:
            add("must", "manifest-json", "Manifesto não é JSON válido", f"linha {exc.lineno}",
                f"A leitura parou em: {exc.msg}.",
                "Sem manifesto legível, o pacote não é descoberto pelo catálogo.",
                "Corrija a vírgula ou aspas na linha indicada e valide de novo.",
                "O pacote some do catálogo, mesmo com DESIGN.md e tokens.css corretos.")
            parsed = {}
        if isinstance(parsed, dict):
            payload = parsed
        elif manifest.strip():
            add("must", "manifest-object", "Manifesto não é um objeto", "manifest.json",
                "O JSON raiz não é um objeto de chaves e valores.",
                "O contrato espera um objeto com schemaVersion, id, files e source.",
                "Envolva os campos em { }.", "Nenhum campo do manifesto pode ser lido.")
        if payload:
            schema_version = str(payload.get("schemaVersion", ""))
            if schema_version != CANONICAL_SCHEMA:
                add("must", "manifest-schema", "schemaVersion fora do contrato", "manifest.json",
                    f"Valor declarado: `{schema_version or '(vazio)'}`.",
                    f"O contrato atual espera `{CANONICAL_SCHEMA}`.",
                    f"Troque por `{CANONICAL_SCHEMA}`.", "A validação do pacote rejeita o manifesto.")
            package_id = str(payload.get("id", ""))
            if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", package_id):
                add("must", "manifest-id", "id do pacote não é slug ASCII", "manifest.json",
                    f"Valor declarado: `{package_id or '(vazio)'}`.",
                    "O id precisa ser igual ao nome da pasta e usar apenas minúsculas, números e hífens.",
                    "Use um slug normalizado, como `acme-studio`.", "O pacote e a pasta divergem no catálogo.")
            files = payload.get("files") if isinstance(payload.get("files"), dict) else {}
            if not files:
                add("must", "manifest-files", "Manifesto sem files declarados", "manifest.json",
                    "O objeto `files` não foi declarado.",
                    "O catálogo só encontra DESIGN.md e tokens.css pelos caminhos declarados.",
                    'Declare `"files": {"design": "DESIGN.md", "tokens": "tokens.css"}`.',
                    "A descoberta cai no modo legado e perde a paridade.")
            else:
                if str(files.get("design", "")) != "DESIGN.md":
                    add("must", "manifest-design-path", "Caminho de DESIGN.md fora do padrão", "manifest.json",
                        f"`files.design` = `{files.get('design', '(vazio)')}`.",
                        "O nome canônico é DESIGN.md; qualquer outro exige uma exceção documentada.",
                        "Aponte `files.design` para `DESIGN.md`.", "Ferramentas que leem o caminho canônico não acham a prosa.")
                if str(files.get("tokens", "")) != "tokens.css":
                    add("must", "manifest-tokens-path", "Caminho de tokens.css fora do padrão", "manifest.json",
                        f"`files.tokens` = `{files.get('tokens', '(vazio)')}`.",
                        "O nome canônico é tokens.css.", "Aponte `files.tokens` para `tokens.css`.",
                        "O CSS compilado pode ser ignorado.")
                for key, value in files.items():
                    path = str(value)
                    if path.startswith(("/", "\\")) or ".." in path.replace("\\", "/").split("/") or "\\" in path:
                        add("must", "manifest-unsafe-path", f"Caminho inseguro em files.{key}", "manifest.json",
                            f"`{path}` sai da pasta do pacote.",
                            "Caminhos declarados precisam ser relativos e seguros.",
                            "Use um nome de arquivo simples dentro da pasta.", "A leitura pode escapar do pacote.")
            source = payload.get("source")
            if not isinstance(source, dict) or not str(source.get("type", "")):
                add("nice", "manifest-source", "Proveniência não declarada", "manifest.json",
                    "`source` está ausente ou sem `type`.",
                    "Sem proveniência não se sabe se o pacote é bundled, local, GitHub ou shadcn.",
                    'Declare `"source": {"type": "bundled", "origin": "..." }`.',
                    "A revisão de licença fica sem rastro.")
            for field_name, group in (("name", "nice"), ("category", "nice"), ("description", "nice")):
                if not str(payload.get(field_name, "")).strip():
                    add(group, f"manifest-{field_name}", f"Metadado ausente: {field_name}", "manifest.json",
                        f"O campo `{field_name}` está vazio.",
                        "Os três campos formam a cópia do catálogo e evitam títulos inferidos por Markdown.",
                        f"Preencha `{field_name}` com texto curto e específico.",
                        "O catálogo mostra um rótulo genérico.")

    # ---- DESIGN.md
    headings = _h2_sections(design)
    if design.strip():
        if len(headings) < MIN_H2:
            add("must", "design-sections", "Poucas seções substantivas em DESIGN.md", "DESIGN.md",
                f"Encontrei {len(headings)} título(s) H2; o contrato pede pelo menos {MIN_H2}.",
                "Um contrato curto demais deixa decisões para o acaso do agente.",
                "Cubra tema, cor, tipografia, espaçamento, componentes, movimento, acessibilidade e antíteses.",
                "O agente improvisa o que a prosa não decidiu.")
        for title, content in headings:
            if content < 40:
                add("should", "design-empty-section", f"Seção sem substância: {title}", "DESIGN.md",
                    f"`## {title}` tem {content} caractere(s) de conteúdo.",
                    "Título vazio cumpre contagem sem informar decisão.",
                    "Escreva a decisão, o porquê e o que evitar, ou remova a seção.",
                    "A contagem de seções sobe, a qualidade do contrato não.")
                if len([item for item in findings if item["kind"] == "design-empty-section"]) >= 3:
                    break
        lowered_design = design.lower()
        for word in ("lorem ipsum", "dolor sit amet", "todo:", "tbd", "preencher depois"):
            if word in lowered_design:
                add("must", "design-placeholder", f"Texto de preenchimento: {word}", "DESIGN.md",
                    f"O contrato contém `{word}`.",
                    "Placeholder no contrato vira placeholder no artefato.",
                    "Substitua pela decisão real antes de publicar o pacote.",
                    "O agente reproduz o vazio como se fosse escolha.")
                break
        if not re.search(r"^#\s+\S", design, re.M):
            add("nice", "design-h1", "DESIGN.md sem título H1", "DESIGN.md",
                "Não há um título de nível 1 no documento.",
                "O H1 é o nome legível do sistema quando o manifesto não é lido.",
                "Adicione `# Nome do sistema` na primeira linha.",
                "O catálogo depende do manifesto para exibir o nome.")
    elif tokens.strip() or manifest.strip():
        add("should", "design-missing", "DESIGN.md não foi declarado", "pacote",
            "Só o manifesto ou o CSS foi enviado.",
            "O manifesto e os tokens são máquina; a prosa é o que o agente lê para decidir.",
            "Cole o DESIGN.md do pacote.", "As decisões de intenção ficam sem registro.")

    # ---- tokens.css
    root, themes, components = _parse_css(tokens)
    declared = dict(root)
    for theme_tokens in themes.values():
        for name, value in theme_tokens.items():
            declared.setdefault(name, value)

    if tokens.strip():
        group_rows: list[dict[str, Any]] = []
        for key, label, items in TOKEN_GROUPS:
            missing = [name for name, _layer, _desc in items if name not in root]
            group_rows.append({"group": key, "label": label, "declared": len(items) - len(missing), "total": len(items)})
            if not missing:
                continue
            detail = ", ".join(f"`{name}`" for name in missing[:6])
            suffix = f" e mais {len(missing) - 6}" if len(missing) > 6 else ""
            add("must", "missing-tokens", f"Tokens ausentes: {label}", ", ".join(missing[:3]),
                f"Faltam {len(missing)} token(s) em `:root`: {detail}{suffix}.",
                "Artefato gerado cola este bloco em um `<style>` só; `var()` sem alvo derruba a regra inteira.",
                "Declare os slots A1/A2 ou aponte os slots B para o irmão nomeado (`var(--surface)`).",
                "A regra que usa o token é descartada silenciosamente no artefato.")
        empty = [name for name, value in root.items() if not value.strip()]
        if empty:
            add("must", "empty-token", "Token declarado sem valor", ", ".join(empty[:5]),
                f"{len(empty)} declaração(ões) termina(m) sem valor: {', '.join(empty[:5])}.",
                "Um token vazio resolve para nada e quebra o `var()`.",
                "Remova a declaração ou preencha o valor.", "A propriedade cai no valor inicial do navegador.")

        referenced = {match.lower() for match in re.findall(r"var\(\s*(--[A-Za-z0-9_-]+)", tokens)}
        undefined = sorted(referenced - set(declared))
        if undefined:
            add("must", "undefined-token", "Referência a token inexistente", ", ".join(undefined[:5]),
                f"`var()` aponta para {len(undefined)} token(s) não declarado(s): {', '.join(undefined[:6])}.",
                "É o mesmo defeito do slot ausente, mas invertido: o componente pede o que não existe.",
                "Declare o token ou troque a referência por um slot do contrato.",
                "A declaração inteira é descartada no artefato.")

        if themes:
            for theme_name, theme_tokens in themes.items():
                missing_theme = [name for name in THEME_MUST if name not in theme_tokens]
                if missing_theme:
                    add("should", "theme-parity", "Tema sem paridade mínima", f"tema {theme_name}",
                        f"O tema `{theme_name}` não redefine: {', '.join(missing_theme)}.",
                        "Um tema que não reescreve fundo e texto herda a dupla do tema claro e perde contraste.",
                        "Redefina `--bg` e `--fg` no seletor do tema.", "O modo escuro fica ilegível ou inconsistente.")
                elif len([name for name in ("--bg", "--fg", "--surface", "--border", "--muted") if name in theme_tokens]) < 4:
                    add("nice", "theme-shallow", "Tema redefine poucos tokens", f"tema {theme_name}",
                        f"O tema `{theme_name}` redefine {len(theme_tokens)} token(s).",
                        "Tema raso gera mistura de superfícies entre os modos.",
                        "Redefina superfície, texto, borda e acento juntos.", "A mistura aparece só em algumas telas.")

        for selector, body in components:
            for match in re.finditer(r"#[0-9a-fA-F]{3,8}\b|(?:rgba?|hsla?)\(", body):
                raw_colors.append((match.start(), selector))
        if raw_colors:
            samples = sorted({selector for _offset, selector in raw_colors})
            add("should", "raw-color", "Cor bruta fora dos tokens", ", ".join(samples[:3]),
                f"{len(raw_colors)} cor(es) literal(is) em regras de componente ({', '.join(samples[:4])}).",
                "Cor repetida fora do token impossibilita trocar de marca e quebra o tema escuro.",
                "Troque por `var(--...)`; valores literais ficam só em `:root`.",
                "Uma troca de acento exige caçar cada ocorrência.")

        if re.search(r"\btransition\s*:|\banimation\s*:|@keyframes", tokens) and "prefers-reduced-motion" not in tokens:
            add("must", "reduced-motion", "Movimento sem alternativa reduzida", "tokens.css",
                "Há transição ou animação e nenhuma consulta `prefers-reduced-motion`.",
                "Quem pede menos movimento no sistema continua recebendo animação.",
                "Adicione um bloco `@media (prefers-reduced-motion: reduce)` que zere as durações.",
                "A interface ignora a preferência de acessibilidade do usuário.")

        if re.search(r"\bscale\(\s*0(?:\.0+)?\s*\)", tokens):
            add("should", "scale-zero", "Animação a partir de scale(0)", "tokens.css",
                "Uma regra anima de `scale(0)`.",
                "Surgir do nada parece colagem; a convenção é começar em `scale(0.9)` com opacidade.",
                "Troque por `scale(0.9)` mais opacidade.", "O movimento parece barato e desorienta.")

        if re.search(r"\bease-in\b(?!-out)", tokens):
            add("should", "ease-in", "Curva ease-in em interface", "tokens.css",
                "Uma transição usa `ease-in`.",
                "Entrada lenta e saída rápida parece travada em interface responsiva.",
                "Use um ease-out forte, como `cubic-bezier(0.23, 1, 0.32, 1)`.",
                "O toque parece atrasar antes de responder.")

        ease_value = root.get("--ease-standard", "")
        if ease_value and not re.search(r"cubic-bezier|ease-out|var\(", ease_value):
            add("should", "ease-standard-weak", "Curva padrão fraca", "--ease-standard",
                f"Valor declarado: `{ease_value}`.",
                "A convenção do produto pede ease-out forte, não `ease` nem `linear`.",
                "Use `cubic-bezier(0.23, 1, 0.32, 1)` ou documente a exceção de marca.",
                "Todo o movimento do sistema fica sem identidade.")

        documented = design.lower()
        unknown = sorted(name for name in root if name not in SCHEMA_SET and name.lower() not in documented)
        if unknown:
            add("nice", "unknown-token", "Token fora do esquema e sem documentação", ", ".join(unknown[:4]),
                f"{len(unknown)} token(s) fora do esquema: {', '.join(unknown[:6])}.",
                "Extensão não declarada não é promovível nem verificável por outra marca.",
                "Documente o token no DESIGN.md ou promova-o ao esquema compartilhado.",
                "O nome vira dívida invisível na próxima marca.")

        used_in_rules = set()
        for _selector, body in components:
            used_in_rules.update(match.lower() for match in re.findall(r"var\(\s*(--[A-Za-z0-9_-]+)", body))
        unused = sorted(
            name for name in root
            if name not in SCHEMA_SET and name not in used_in_rules and name.lower() not in documented
        )
        if unused:
            add("nice", "unused-token", "Token declarado e nunca usado", ", ".join(unused[:4]),
                f"{len(unused)} token(s) só aparecem na declaração: {', '.join(unused[:6])}.",
                "Slot sem consumidor nem citação é peso morto no contrato.",
                "Use o token em um componente ou remova a declaração.",
                "O contrato promete decisões que ninguém aplica.")

        total = len(SCHEMA_TOKENS)
        found = sum(1 for name in SCHEMA_TOKENS if name in root)
    else:
        group_rows = [{"group": key, "label": label, "declared": 0, "total": len(items)} for key, label, items in TOKEN_GROUPS]
        total = len(SCHEMA_TOKENS)
        found = 0
        if design.strip() or manifest.strip():
            add("must", "tokens-missing", "tokens.css não foi declarado", "pacote",
                "Só a prosa ou o manifesto foi enviado.",
                "Sem CSS compilado, cada artefato inventa valores e a marca deriva.",
                "Cole o tokens.css do pacote.", "A revisão de cor, tipografia e movimento não existe.")

    questions = [
        "Cada decisão do DESIGN.md aparece como token ou é só intenção?",
        "Quem revisa a promoção de um token de marca para o esquema compartilhado?",
        "O pacote foi validado por guard e typecheck antes de entrar no catálogo?",
    ]
    limitations = [
        "A revisão compara com o esquema compartilhado embutido, não com o guard do upstream.",
        "O parser de CSS cobre blocos simples; aninhamento profundo e valores calculados não são avaliados.",
        "Nada é compilado, renderizado ou publicado: os achados são candidatos.",
    ]
    summary = [
        f"**Pacote:** {found}/{total} slots do contrato · {len(headings)} seção(ões) H2 · {len(themes)} tema(s).",
        f"**Manifesto:** {'lido' if payload else 'não enviado'} · {'slots completos' if found == total else f'{total - found} slot(s) ausente(s)'}.",
    ]
    findings, counts, verdict_text, questions = finalize(findings, mode, questions)
    extra = ["", "## Slots por grupo", "", "| Grupo | Declarados | Total |", "|---|---|---|"]
    extra += [f"| {row['label']} | {row['declared']} | {row['total']} |" for row in group_rows]
    return common(
        analysis="contract", mode=mode, title="Revisão do contrato de design", summary=summary,
        findings=findings, counts=counts, verdict=verdict_text, questions=questions, rows=group_rows,
        metrics={
            "tokensDeclared": len(root), "requiredFound": found, "requiredTotal": total,
            "headings": len(headings), "themes": len(themes), "rawColors": len(raw_colors),
            "manifest": bool(payload),
        },
        limitations=limitations, extra_sections=extra,
    )


# ---------------------------------------------------------------- contraste


def _channel(value: float) -> float:
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    value = hex_color.lstrip("#")
    if len(value) == 3:
        value = "".join(char * 2 for char in value)
    red, green, blue = (int(value[index:index + 2], 16) / 255 for index in (0, 2, 4))
    return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)


def contrast_ratio(foreground: str, background: str) -> float:
    first, second = luminance(foreground), luminance(background)
    lighter, darker = (first, second) if first >= second else (second, first)
    return round((lighter + 0.05) / (darker + 0.05), 2)


def _color(raw: str, label: str, line: int) -> str:
    value = raw.strip()
    if not (_HEX3.match(value) or _HEX6.match(value)):
        raise StudioError(
            f"Linha {line}: cor inválida em {label}. Use hexadecimal de 3 ou 6 dígitos, como #111 ou #18181b."
        )
    return value.lower()


def audit_contrast(*, pairs: str, mode: str = "full") -> dict[str, Any]:
    _mode(mode)
    source = _cells(pairs, 4, "par de contraste")
    findings: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    aaa_gaps: list[tuple[str, str, str, float, float, float]] = []
    failures = 0

    for number, cells in source:
        label, foreground_raw, background_raw, size_raw = cells
        label = label or f"par {number}"
        size = "large" if _norm(size_raw) in {"grande", "large", "titulo", "título", "display"} else "body"
        if not foreground_raw or not background_raw:
            findings.append(finding(
                "must", "missing-color", f"Par incompleto: {label}", f"linha {number}",
                "Faltou a cor de frente ou de fundo.",
                "Contraste só existe contra um fundo real; par incompleto é alegação sem medida.",
                "Informe frente e fundo em hexadecimal.", "A dupla não pode ser verificada.",
            ))
            continue
        try:
            foreground = _color(foreground_raw, "frente", number)
            background = _color(background_raw, "fundo", number)
        except StudioError as exc:
            findings.append(finding(
                "must", "invalid-color", f"Cor inválida: {label}", f"linha {number}", str(exc),
                "Sem hexadecimal não há luminância relativa nem razão de contraste.",
                "Use 3 ou 6 dígitos hexadecimais.", "O par fica fora da verificação de acessibilidade.",
            ))
            continue
        ratio = contrast_ratio(foreground, background)
        aa = 3.0 if size == "large" else 4.5
        aaa = 4.5 if size == "large" else 7.0
        if ratio >= aaa:
            level = "AAA"
        elif ratio >= aa:
            level = "AA"
        else:
            level = "reprovado"
            failures += 1
        if ratio < aa:
            findings.append(finding(
                "must", "contrast-fail", f"Contraste abaixo de AA: {label}", f"linha {number}",
                f"Razão {ratio:.2f}:1 entre `{foreground}` e `{background}` (mínimo {aa}:1 para texto {'grande' if size == 'large' else 'normal'}).",
                "Texto com contraste insuficiente é barreira de leitura, não preferência estética.",
                "Escureça o fundo ou clareie o texto até passar de AA; confira também o estado de hover.",
                "Parte do público não consegue ler o conteúdo, inclusive em tela ao sol.",
            ))
        elif ratio < aaa:
            aaa_gaps.append((label, foreground, background, ratio, aa, aaa))
        rows.append({
            "label": label, "foreground": foreground, "background": background, "size": size,
            "ratio": ratio, "aa": aa, "aaa": aaa, "level": level, "line": number,
        })

    if aaa_gaps:
        label, foreground, background, ratio, aa, aaa = min(aaa_gaps, key=lambda item: item[3])
        findings.append(finding(
            "nice", "contrast-aaa", f"AA sem AAA: {label}", f"`{foreground}` sobre `{background}`",
            f"Razão {ratio:.2f}:1; AA exige {aa:g}:1 e AAA exige {aaa:g}:1.",
            "AA é piso, não meta; o par mais próximo de AAA ganha leitura longa ao subir.",
            f"Aproxime esta dupla até {aaa:g}:1 antes de mexer nas outras.",
            "Leitura longa cansa mais cedo, principalmente em tela pequena.",
        ))
    body_rows = [row for row in rows if row["size"] == "body"]
    weakest = min(rows, key=lambda row: row["ratio"]) if rows else None
    questions = [
        "Cada par de frente e fundo realmente aparece junto no artefato?",
        "Os estados de hover, foco e desabilitado foram medidos com a mesma régua?",
        "Texto grande foi classificado pelo tamanho real, e não para passar no limite menor?",
    ]
    limitations = [
        "Só hexadecimal é medido; `rgb()`, `hsl()`, `color-mix()` e transparências ficam fora da conta.",
        "A razão usa luminância relativa WCAG 2.x; não mede tamanho de fonte, peso real nem daltonismo.",
        "Opacidade herdada e fundo composto por imagem não são simulados.",
    ]
    summary = [
        f"**Pares:** {len(rows)} · {failures} reprovado(s) em AA · menor razão {weakest['ratio'] if weakest else 0:.2f}:1"
        + (f" em `{weakest['label']}`." if weakest else "."),
        f"**Texto de corpo:** {len(body_rows)} par(es) com limite 4,5:1 · {sum(1 for row in body_rows if row['level'] != 'reprovado')} aprovado(s).",
    ]
    findings, counts, verdict_text, questions = finalize(findings, mode, questions)
    extra = ["", "## Pares medidos", "", "| Par | Frente | Fundo | Razão | Nível |", "|---|---|---|---|---|"]
    extra += [f"| {row['label']} | `{row['foreground']}` | `{row['background']}` | {row['ratio']:.2f}:1 | {row['level']} |" for row in rows]
    return common(
        analysis="contrast", mode=mode, title="Contraste de acessibilidade", summary=summary,
        findings=findings, counts=counts, verdict=verdict_text, questions=questions, rows=rows,
        metrics={
            "pairs": len(rows), "failAA": failures,
            "passAAA": sum(1 for row in rows if row["level"] == "AAA"),
            "minRatio": weakest["ratio"] if weakest else 0,
            "worst": weakest["label"] if weakest else "",
        },
        limitations=limitations, extra_sections=extra,
    )


# ---------------------------------------------------------------- crítica


def _band(score: int) -> str:
    for low, high, label in BANDS:
        if low <= score <= high:
            return label
    return "Fora da escala"


def _minutes(text: str) -> int | None:
    match = re.search(r"(\d{1,3})\s*(?:min|minuto)", text, re.I)
    return int(match.group(1)) if match else None


def critique(*, entries: str, keep: str = "", fix: str = "", quick_wins: str = "", mode: str = "full") -> dict[str, Any]:
    _mode(mode)
    source = _cells(entries, 3, "dimensão")
    findings: list[dict[str, Any]] = []
    scores: dict[str, dict[str, Any]] = {}

    for number, cells in source:
        raw_dimension, raw_score, evidence = cells
        key = DIMENSION_ALIASES.get(_norm(raw_dimension))
        if key is None:
            findings.append(finding(
                "must", "unknown-dimension", f"Dimensão desconhecida: {raw_dimension or '(vazio)'}", f"linha {number}",
                "A dimensão não faz parte das cinco do contrato.",
                "Relatório parcial ou inventado esconde justamente o eixo mais fraco.",
                "Use filosofia, hierarquia, detalhe, função ou inovação.", "A nota não entra no relatório.",
            ))
            continue
        if key in scores:
            findings.append(finding(
                "must", "duplicate-dimension", f"Dimensão repetida: {raw_dimension}", f"linha {number}",
                "A mesma dimensão aparece mais de uma vez.",
                "Duas notas para o mesmo eixo tornam o relatório ambíguo.",
                "Mantenha uma linha por dimensão.", "A nota final depende da ordem de leitura.",
            ))
            continue
        try:
            score = int(raw_score.strip())
        except ValueError:
            score = -1
        if score < 0 or score > 10:
            findings.append(finding(
                "must", "invalid-score", f"Nota fora de 0–10: {raw_dimension}", f"linha {number}",
                f"Valor declarado: `{raw_score or '(vazio)'}`.",
                "A escala do contrato é inteira de 0 a 10 com quatro bandas nomeadas.",
                "Informe um inteiro entre 0 e 10.", "A banda e a média não podem ser calculadas.",
            ))
            continue
        clean_evidence = " ".join(evidence.split())
        if len(clean_evidence) < 40:
            findings.append(finding(
                "must", "thin-evidence", f"Evidência curta: {raw_dimension}", f"linha {number}",
                f"{len(clean_evidence)} caractere(s) de evidência.",
                "Nota sem evidência é opinião; o contrato rejeita 'parece inconsistente'.",
                "Cite o elemento, a classe, a página ou a linha que sustenta a nota.",
                "A nota não é defensável na revisão.",
            ))
        elif not _CITATION.search(clean_evidence):
            findings.append(finding(
                "should", "no-citation", f"Evidência sem referência: {raw_dimension}", f"linha {number}",
                f"Trecho declarado: `{clean_evidence[:120]}`.",
                "Sem classe, seletor, arquivo, linha ou medida, a evidência é impressão.",
                "Acrescente `#seletor`, `.classe`, `linha 42`, `página 3` ou uma medida em px.",
                "A revisão vira gosto pessoal disfarçado de auditoria.",
            ))
        scores[key] = {"key": key, "score": score, "evidence": clean_evidence, "line": number, "band": _band(score)}

    missing = [key for key, _label, _question, _band in DIMENSIONS if key not in scores]
    if missing:
        labels = ", ".join(label for key, label, _question, _band in DIMENSIONS if key in missing)
        findings.append(finding(
            "must", "missing-dimension", "Relatório incompleto", labels,
            f"Faltam {len(missing)} dimensão(ões): {labels}.",
            "O contrato exige as cinco notas sempre; relatório parcial não é revisão.",
            "Dê uma nota com evidência para cada dimensão que falta.",
            "O eixo omitido normalmente é o mais fraco — e o mais útil."
        ))

    values = [item["score"] for item in scores.values()]
    mean = round(sum(values) / len(values), 2) if values else 0.0
    weakest = min(scores.values(), key=lambda item: item["score"]) if scores else None

    if values and mean > 8:
        findings.append(finding(
            "should", "grade-inflation", "Média alta demais para uma revisão", f"média {mean}",
            f"As cinco notas somam média {mean}, acima de 8.",
            "Nota 7 já significa forte; média acima de 8 costuma indicar inflação.",
            "Reveja a dimensão mais fraca: se ela é 8, cite o defeito que ficou de fora.",
            "O relatório elogia o artefato e não melhora nada.",
            ))
    if values and min(values) >= 7:
        findings.append(finding(
            "nice", "no-weak-axis", "Nenhum eixo fraco declarado", f"mínimo {min(values)}",
            "Todas as dimensões ficaram em 7 ou mais.",
            "Um artefato sem nenhum eixo abaixo de 7 é raro; confirme se a revisão foi crítica.",
            "Procure um eixo real abaixo da banda Forte ou registre por que todos são fortes.",
            "A revisão perde o poder de orientar a próxima iteração.",
            ))

    def bullets(raw: str, label: str, minimum: int) -> list[str]:
        items = [line.strip(" -*\t") for line in _lines(raw) if line.strip(" -*\t")]
        if len(items) < minimum:
            findings.append(finding(
                "should", f"{label}-short", f"Poucos itens em {label}", label,
                f"{len(items)} item(ns) declarado(s); o contrato pede pelo menos {minimum}.",
                f"{label} sem massa não orienta a próxima iteração.",
                f"Acrescente itens concretos, citando classe, página ou elemento.",
                "A ação vira genérica e some no próximo ciclo.",
            ))
        return items

    keep_items = bullets(keep, "manter", 3)
    fix_items = bullets(fix, "corrigir", 3)
    win_items = bullets(quick_wins, "ganhos rápidos", 3)
    for item in win_items:
        minutes = _minutes(item)
        if minutes is None:
            findings.append(finding(
                "nice", "win-without-time", "Ganho sem estimativa de tempo", f"ganhos rápidos: {item[:60]}",
                "O item não declara minutos.",
                "Ganho rápido sem tempo declarado vira tarefa normal.",
                "Feche a linha com o tempo, como `(10 min)`.", "A lista perde a promessa de esforço baixo.",
            ))
        elif minutes < 5 or minutes > 15:
            findings.append(finding(
                "should", "win-out-of-range", "Ganho fora de 5–15 minutos", f"ganhos rápidos: {item[:60]}",
                f"Tempo declarado: {minutes} min.",
                "A faixa do contrato é 5 a 15 minutos; abaixo disso é trivial, acima é tarefa.",
                "Reclassifique como correção ou reduza o escopo do ganho.",
                "A lista mistura tarefas grandes com ajustes pequenos.",
            ))

    score_rows = [
        {
            "key": item["key"], "label": next(label for key, label, _q, _b in DIMENSIONS if key == item["key"]),
            "score": item["score"], "band": item["band"], "evidence": item["evidence"],
        }
        for key, item in sorted(scores.items(), key=lambda pair: [d[0] for d in DIMENSIONS].index(pair[0]))
    ]
    if missing:
        verdict_text = f"Faltam {len(missing)} nota(s): não existe revisão parcial."
    elif weakest is None:
        verdict_text = "Nenhuma nota válida."
    else:
        weakest_label = next(label for key, label, _q, _b in DIMENSIONS if key == weakest["key"])
        verdict_text = (
            f"Eixo mais fraco: {weakest_label} com {weakest['score']}/10 ({weakest['band']}). "
            f"Média {mean}, mas a leitura usa a banda mais fraca, não a média."
        )

    questions = [
        "A nota da dimensão mais fraca continua igual se você olhar de novo só para ela?",
        "Algum item de 'corrigir' depende de decisão de produto, e não de design?",
        "O artefato foi visto executado, ou a nota saiu do frontmatter?",
    ]
    limitations = [
        "A skill não lê o artefato: ela valida disciplina de notas, evidência e listas.",
        "Banda mais fraca e média são aritmética declarada; nenhuma inspeção visual foi feita.",
        "Revisar o próprio artefato na mesma rodada em que ele foi gerado continua sendo um viés registrado.",
    ]
    summary = [
        f"**Notas:** {len(scores)}/5 dimensões · média {mean} · banda geral {weakest['band'] if weakest else '—'}."
        + (f" Eixo fraco: {next(label for key, label, _q, _b in DIMENSIONS if weakest and key == weakest['key'])}." if weakest else ""),
        f"**Ações:** {len(keep_items)} para manter · {len(fix_items)} para corrigir · {len(win_items)} ganhos rápidos.",
    ]
    findings, counts, blocking_verdict, questions = finalize(findings, mode, questions)
    if counts["must"]:
        verdict_text = f"{verdict_text} {blocking_verdict}"
    radar = [{"axis": row["key"], "label": row["label"], "score": row["score"], "band": row["band"]} for row in score_rows]
    extra = ["", "## Dimensões", "", "| Dimensão | Nota | Banda | Evidência |", "|---|---|---|---|"]
    extra += [
        f"| {row['label']} | {row['score']}/10 | {row['band']} | {row['evidence'][:160].replace('|', '/')} |" for row in score_rows
    ]
    for title, items in (("Manter", keep_items), ("Corrigir", fix_items), ("Ganhos rápidos", win_items)):
        if not items:
            continue
        extra += ["", f"## {title}", ""]
        extra += [f"- [ ] {item}" for item in items]
    return {
        **common(
            analysis="critique", mode=mode, title="Crítica de design em cinco dimensões", summary=summary,
            findings=findings, counts=counts, verdict=verdict_text, questions=questions, rows=score_rows,
            metrics={
                "dimensions": len(scores), "mean": mean,
                "weakest": weakest["key"] if weakest else "", "weakestScore": weakest["score"] if weakest else 0,
                "keep": len(keep_items), "fix": len(fix_items), "quickWins": len(win_items),
            },
            limitations=limitations, extra_sections=extra,
        ),
        "radar": radar,
        "bands": [{"low": low, "high": high, "label": label} for low, high, label in BANDS],
        "keep": keep_items,
        "fix": fix_items,
        "quickWins": win_items,
    }


# ---------------------------------------------------------------- artefato


_PURPLE = ("#8b5cf6", "#7c3aed", "#a855f7", "#6d28d9", "#9333ea", "#581c87")
_INDIGO = ("#6366f1", "#4f46e5", "#4338ca", "#818cf8", "#a5b4fc")
_BLUE = ("#3b82f6", "#2563eb", "#1d4ed8", "#1e40af", "#60a5fa", "#0ea5e9")
_CYAN = ("#06b6d4", "#0891b2", "#0e7490", "#22d3ee", "#155e75")
_SLOP_EMOJI = ("✨", "🚀", "🎯", "⚡", "🔥", "💡", "📈", "🎨", "🛡", "🌟", "💪", "🎉", "👋", "🙌", "✅", "⭐", "🏆")
_METRIC = re.compile(
    r"\b(?:10|100|3)\s*[x×]\s*(?:mais\s+)?(?:r[áa]pido|melhor|produtivo|eficiente|faster|better|productive)\b"
    r"|\b99[.,]\d+%\s*(?:de\s+)?uptime\b|\bzero[- ]downtime\b|\b(?:uptime|disponibilidade)\s+de\s+99[.,]\d+%\b",
    re.I,
)
_FILLER = re.compile(
    r"\blorem\s+ipsum\b|\bdolor\s+sit\s+amet\b|\bfeature\s+(?:one|two|three|1|2|3)\b"
    r"|\b(?:texto|conte[úu]do)\s+de\s+exemplo\b|\bplaceholder\s+(?:text|copy)\b|\bsample\s+content\b",
    re.I,
)
_SANS_DISPLAY = re.compile(
    r"(?:h1|h2|h3|\.(?:hero|display|headline)[\w-]*)\b[^{}]{0,80}\{[^{}]*font-family\s*:\s*[\"']?"
    r"(?:Inter|Roboto|Arial|-apple-system|system-ui|SF\s*Pro|Helvetica)",
    re.I,
)
_HEX_ANY = re.compile(r"#[0-9a-fA-F]{3,8}\b")


def _strip_comments(html: str) -> str:
    return re.sub(r"<!--.*?-->", "", html, flags=re.S)


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _snippet(text: str, offset: int, length: int = 120) -> str:
    start = max(0, offset - 30)
    return " ".join(text[start:offset + length].split())[:160]


def _style_and_body(html: str) -> tuple[str, str]:
    styles = "\n".join(match.group(1) for match in re.finditer(r"<style[^>]*>(.*?)</style>", html, re.S | re.I))
    body = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.S | re.I)
    return styles, body


def _without_root(styles: str) -> tuple[str, str]:
    """Separa o bloco :root do restante das regras."""
    root_matches = list(re.finditer(r":root\s*\{[^{}]*\}", styles))
    root_text = "\n".join(match.group(0) for match in root_matches)
    rest = styles
    for match in reversed(root_matches):
        rest = rest[:match.start()] + " " + rest[match.end():]
    return root_text, rest


def audit_artifact(*, artifact: str, mode: str = "full") -> dict[str, Any]:
    _mode(mode)
    if not artifact.strip():
        raise StudioError("Cole o HTML do artefato antes de revisar.")
    if len(artifact) > MAX_ARTIFACT_CHARS:
        raise StudioError(f"O artefato excede {MAX_ARTIFACT_CHARS:,} caracteres.".replace(",", "."))
    html = _strip_comments(artifact)
    lowered = html.lower()
    styles, body = _style_and_body(html)
    styles_start = html.find(styles) if styles else 0
    _root_text, component_styles = _without_root(styles)
    findings: list[dict[str, Any]] = []
    hits: list[str] = []

    def add(group: str, kind: str, title: str, location: str, what: str, problem: str, fix: str, if_skipped: str) -> None:
        findings.append(finding(group, kind, title, location, what, problem, fix, if_skipped))
        hits.append(kind)

    # 1. Gradiente roxo ou violeta.
    gradient = re.compile(r"(?:linear|radial|conic)-gradient\([^)]*?(?:%s|purple|violet)[^)]*\)" % "|".join(_PURPLE), re.I)
    match = gradient.search(html)
    if match:
        add("must", "purple-gradient", "Gradiente roxo ou violeta", f"linha {_line_of(html, match.start())}",
            f"Trecho: `{_snippet(html, match.start())}`.",
            "É a assinatura visual mais reconhecível de artefato gerado por IA.",
            "Troque por superfície plana ou um acento único, sem gradiente.",
            "O artefato parece template genérico, não marca.")

    # 2. Gradiente azul para ciano.
    if "gradient" in lowered:
        for item in re.finditer(r"(?:linear|radial|conic)-gradient\([^)]*\)", html, re.I):
            piece = item.group(0).lower()
            if any(color in piece for color in _BLUE) and any(color in piece for color in _CYAN):
                add("must", "trust-gradient", "Gradiente azul para ciano", f"linha {_line_of(html, item.start())}",
                    f"Trecho: `{_snippet(html, item.start())}`.",
                    "O degradê azul→ciano virou sinônimo de landing page de IA.",
                    "Use cor sólida do token de acento, em uma única intensidade.",
                    "A peça perde credibilidade antes do primeiro parágrafo.")
                break
        if "gradient" in lowered and not any("trust-gradient" in hit for hit in hits):
            keyword = re.search(r"(?:linear|radial|conic)-gradient\([^)]*\b(?:blue|cyan)\b[^)]*\)", html, re.I)
            if keyword:
                add("must", "trust-gradient", "Gradiente azul para ciano", f"linha {_line_of(html, keyword.start())}",
                    f"Trecho: `{_snippet(html, keyword.start())}`.",
                    "Degradê de confiança azul→ciano é o clichê de 2024–2026.",
                    "Troque por acento sólido documentado no DESIGN.md.",
                    "O visual parece cópia de qualquer concorrente.")

    # 3. Índigo padrão como acento.
    indigo_hit = next((color for color in _INDIGO if color in component_styles.lower()), None)
    if indigo_hit:
        offset = html.lower().find(indigo_hit)
        add("must", "indigo-accent", "Índigo padrão como acento", f"linha {_line_of(html, max(offset, 0))}",
            f"`{indigo_hit}` aparece fora de `:root`.",
            "É a cor padrão de todo LLM; acento precisa vir do contrato da marca.",
            "Use `var(--accent)` declarado no tokens.css.", "O artefato não tem identidade própria.")

    # 4. Emoji como ícone.
    visible = re.sub(r"<(?:code|pre)[^>]*>.*?</(?:code|pre)>", " ", body, flags=re.S | re.I)
    emojis = [emoji for emoji in _SLOP_EMOJI if emoji in visible]
    if emojis:
        offset = html.find(emojis[0])
        add("must", "emoji-icon", "Emoji usado como ícone", f"linha {_line_of(html, max(offset, 0))}",
            f"Emojis encontrados: {' '.join(emojis[:8])}.",
            "Emoji como ícone de recurso é atalho de conteúdo, não decisão de design.",
            "Use ícone vetorial do sistema ou none; emoji só quando for a voz do produto.",
            "A peça parece rascunho de apresentação.")

    # 5. Métrica inventada.
    match = _METRIC.search(visible)
    if match:
        add("must", "invented-metric", "Métrica inventada", f"linha {_line_of(html, max(html.find(match.group(0)), 0))}",
            f"Trecho: `{match.group(0)}`.",
            "Número sem fonte é alegação falsa dentro de uma peça de design.",
            "Remova ou troque por dado real com fonte e data.",
            "Comunicação e jurídico precisam retirar a peça depois.")

    # 6. Copy de preenchimento.
    match = _FILLER.search(visible)
    if match:
        add("must", "filler-copy", "Texto de preenchimento", f"linha {_line_of(html, max(html.find(match.group(0)), 0))}",
            f"Trecho: `{match.group(0)}`.",
            "Placeholder entregue como conteúdo final é entrega incompleta.",
            "Escreva o texto real ou marque explicitamente como conteúdo de exemplo.",
            "O usuário recebe uma peça que não pode publicar.")

    # 7. Display em sans genérica.
    match = _SANS_DISPLAY.search(styles)
    if match:
        add("must", "sans-display", "Display em sans genérica", f"linha {_line_of(html, styles_start + styles.find(match.group(0)))}",
            f"Regra: `{_snippet(match.group(0), 0, 140)}`.",
            "Título em Inter/Roboto/system-ui sem contraste com o corpo achata a hierarquia.",
            "Use a fonte de display do contrato ou uma serif/documentação explícita.",
            "A página parece painel de admin, mesmo quando não é.")

    # 8. CSS externo.
    match = re.search(r"<link[^>]+rel=[\"']?stylesheet", html, re.I)
    if match:
        add("must", "external-css", "CSS externo", f"linha {_line_of(html, match.start())}",
            f"Trecho: `{_snippet(html, match.start())}`.",
            "Artefato de arquivo único não pode depender de folha externa: o preview quebra offline.",
            "Incorpore o CSS em `<style>`.", "O artefato aparece sem estilo em outro ambiente.")
    match = re.search(r"@import\s+(?:url\()?[\"']?https?://", html, re.I)
    if match:
        add("must", "external-import", "Import de CSS remoto", f"linha {_line_of(html, match.start())}",
            f"Trecho: `{_snippet(html, match.start())}`.",
            "Import remoto adiciona rede, privacidade e falha silenciosa.",
            "Baixe e incorpore a fonte ou o estilo.", "A tipografia cai para o fallback sem aviso.")

    # 9. JS externo.
    match = re.search(r"<script[^>]+src=", html, re.I)
    if match:
        add("must", "external-js", "JavaScript externo", f"linha {_line_of(html, match.start())}",
            f"Trecho: `{_snippet(html, match.start())}`.",
            "Artefato de arquivo único precisa ser autossuficiente.",
            "Incorpore o script ou remova a dependência.", "O artefato fica morto quando o CDN falha.")

    # 10. Imagem sem alt.
    for match in re.finditer(r"<img\b[^>]*>", html, re.I):
        tag = match.group(0)
        if not re.search(r"\balt\s*=", tag, re.I):
            add("must", "missing-alt", "Imagem sem texto alternativo", f"linha {_line_of(html, match.start())}",
                f"Trecho: `{_snippet(tag, 0, 100)}`.",
                "Sem `alt`, leitor de tela não descreve a imagem e o fallback some.",
                'Adicione `alt="descrição objetiva"` ou `alt=""` se for decorativa.',
                "A peça reprova na revisão de acessibilidade.")
            break

    # 11. Movimento sem alternativa.
    has_motion = bool(re.search(r"@keyframes|\btransition\s*:|\banimation\s*:", styles))
    if has_motion and "prefers-reduced-motion" not in html:
        add("must", "no-reduced-motion", "Movimento sem alternativa reduzida", "estilos",
            "Há animação ou transição e nenhuma consulta `prefers-reduced-motion`.",
            "Quem reduziu movimento no sistema continua recebendo a animação.",
            "Adicione `@media (prefers-reduced-motion: reduce)` zerando durações.",
            "A interface ignora uma preferência de acessibilidade.")

    # 12. Estrutura mínima.
    if not re.search(r"<!doctype\s+html", html, re.I):
        add("should", "no-doctype", "Sem doctype", "início do arquivo",
            "O documento não declara `<!doctype html>`.",
            "Sem doctype o navegador entra em modo quase padrão e muda o box model.",
            "Comece com `<!doctype html>`.", "O layout pode variar entre navegadores.")
    match = re.search(r"<html\b([^>]*)>", html, re.I)
    if match and not re.search(r"\blang\s*=", match.group(1), re.I):
        add("should", "no-lang", "Sem atributo lang", f"linha {_line_of(html, match.start())}",
            f"Trecho: `{_snippet(match.group(0), 0, 80)}`.",
            "Sem `lang`, leitores de tela escolhem a pronúncia errada.",
            'Use `lang="pt-BR"` no elemento raiz.', "A leitura em voz alta fica incorreta.")
    if not re.search(r"<title[^>]*>\s*\S", html, re.I):
        add("should", "no-title", "Sem título", "cabeçalho",
            "O documento não tem `<title>` preenchido.",
            "Título é o nome do artefato na aba, no histórico e na exportação.",
            "Adicione um título curto e específico.", "A peça aparece como 'documento sem título'.")
    if not re.search(r"<meta[^>]+name=[\"']?viewport", html, re.I):
        add("should", "no-viewport", "Sem meta viewport", "cabeçalho",
            "Falta a meta de viewport.",
            "Sem ela, o celular renderiza a página em 980px e encolhe tudo.",
            'Adicione `<meta name="viewport" content="width=device-width, initial-scale=1">`.',
            "O artefato fica ilegível no celular.")

    # 13. Cor bruta fora dos tokens.
    raw = _HEX_ANY.findall(component_styles)
    if raw:
        add("should", "raw-color", "Cor bruta fora de :root", "estilos",
            f"{len(raw)} cor(es) literal(is) em regras de componente: {', '.join(sorted(set(raw))[:5])}.",
            "Hex solto ignora o contrato e quebra o tema escuro.",
            "Troque por `var(--...)`; o literal fica só em `:root`.",
            "Trocar a marca exige editar cada regra.")

    # 14. target=_blank sem rel.
    for match in re.finditer(r"<a\b[^>]*target=[\"']_blank[\"'][^>]*>", html, re.I):
        if not re.search(r"\brel\s*=", match.group(0), re.I):
            add("should", "blank-noopener", "Link externo sem rel", f"linha {_line_of(html, match.start())}",
                f"Trecho: `{_snippet(match.group(0), 0, 100)}`.",
                "Sem `rel=noopener`, a página aberta ganha acesso ao contexto de origem.",
                'Acrescente `rel="noopener noreferrer"`.', "Existe risco de sequestro de aba.")
            break

    # 15. Caixa alta sem tracking.
    for match in re.finditer(r"[^{}]{0,120}\{[^{}]*text-transform\s*:\s*uppercase[^{}]*\}", styles, re.I):
        rule = match.group(0)
        if "letter-spacing" not in rule:
            rule_offset = styles_start + styles.find(rule) + (len(rule) - len(rule.lstrip()))
            add("should", "caps-no-tracking", "Caixa alta sem espaçamento", f"linha {_line_of(html, rule_offset)}",
                f"Regra: `{_snippet(rule, 0, 140)}`.",
                "Maiúsculas sem ajuste de kerning ficam apertadas e difíceis de ler.",
                "Acrescente `letter-spacing: 0.06em` ou use a classe de rótulo do contrato.",
                "Rótulos parecem apertados e amadores.")
            break

    # 16. Imagem remota.
    match = re.search(r"(?:<img[^>]+src=[\"']https?://|background(?:-image)?\s*:\s*url\(\s*[\"']?https?://)", html, re.I)
    if match:
        add("should", "external-image", "Imagem remota", f"linha {_line_of(html, match.start())}",
            f"Trecho: `{_snippet(html, match.start())}`.",
            "Imagem remota quebra offline, vaza referrer e pode sumir sem aviso.",
            "Incorpore o arquivo como data URI ou asset do pacote.",
            "O artefato fica com espaços vazios em outra máquina.")

    # 17. scale(0).
    match = re.search(r"scale\(\s*0(?:\.0+)?\s*\)", styles)
    if match:
        add("should", "scale-zero", "Animação a partir de scale(0)", f"linha {_line_of(html, styles_start + styles.find(match.group(0)))}",
            f"Trecho: `{_snippet(match.group(0), 0, 60)}`.",
            "Surgir do nada desorienta; a convenção é 0.9 com opacidade.",
            "Use `scale(0.9)` e anime a opacidade.", "O movimento parece colagem.")

    # 18. Card com barra de acento à esquerda.
    match = re.search(r"border-left\s*:\s*\d+px\s+solid\s+(?:var\(--accent\)|#[0-9a-f]{3,8})", component_styles, re.I)
    if match:
        add("should", "left-accent", "Barra de acento à esquerda", f"linha {_line_of(html, styles_start + styles.find(match.group(0)))}",
            f"Trecho: `{_snippet(match.group(0), 0, 80)}`.",
            "É o cartão de recurso padrão de qualquer template de IA.",
            "Diferencie o cartão por tipografia, espaçamento ou superfície.",
            "O bloco de recursos parece copiado.")

    # 19. Handler inline.
    match = re.search(r"\son(?:click|change|input|submit|load)\s*=", html, re.I)
    if match:
        add("nice", "inline-handler", "Handler inline no HTML", f"linha {_line_of(html, match.start())}",
            f"Trecho: `{_snippet(html, match.start())}`.",
            "Handler inline mistura conteúdo e comportamento e bloqueia CSP.",
            "Mova para um `<script>` no fim do arquivo com `addEventListener`.",
            "A política de segurança não pode ser endurecida.")

    # 20. Acento em excesso.
    accent_uses = len(re.findall(r"var\(\s*--accent\s*\)", html))
    if accent_uses > 8:
        add("nice", "accent-overuse", "Acento em excesso", "estilos",
            f"`var(--accent)` aparece {accent_uses} vezes.",
            "Acento perde força quando aparece em tudo; a convenção é até dois usos visíveis por tela.",
            "Reserve o acento para a ação primária e o foco.",
            "Nada se destaca porque tudo se destaca.")

    # 21. Aspas curvas em código.
    match = re.search(r"<(?:pre|code)[^>]*>[^<]*[\u2018\u2019\u201c\u201d]", body, re.I)
    if match:
        add("should", "smart-quotes", "Aspas curvas em bloco de código", f"linha {_line_of(html, match.start())}",
            "Um bloco de código contém aspas tipográficas.",
            "Código copiado com aspas curvas não executa.",
            "Use aspas retas dentro de `<code>` e `<pre>`.", "O leitor copia um comando quebrado.")

    # 22. iframe sem sandbox.
    for match in re.finditer(r"<iframe\b[^>]*>", html, re.I):
        if not re.search(r"\bsandbox\b", match.group(0), re.I):
            add("should", "iframe-sandbox", "Iframe sem sandbox", f"linha {_line_of(html, match.start())}",
                f"Trecho: `{_snippet(match.group(0), 0, 100)}`.",
                "Iframe sem `sandbox` herda poder de navegação e pode disparar downloads.",
                'Use `sandbox="allow-scripts"` e só as permissões necessárias.',
                "Conteúdo embutido ganha mais poder do que precisa.")
            break

    images = len(re.findall(r"<img\b", html, re.I))
    sections = len(re.findall(r"<section\b", html, re.I))
    scripts = len(re.findall(r"<script\b", html, re.I))
    style_count = len(re.findall(r"<style\b", html, re.I))
    questions = [
        "O artefato foi aberto em viewport de celular além do desktop?",
        "Cada número na peça tem fonte, data e dono?",
        "O movimento ainda funciona com `prefers-reduced-motion: reduce` ligado?",
    ]
    limitations = [
        "O linter é lexical: não interpreta HTML nem CSS e tolera falso positivo, mas cada achado traz trecho.",
        "Contraste real depende de fundo composto, opacidade e imagens; use a revisão de contraste para pares declarados.",
        "Nada é renderizado, capturado ou executado; o julgamento visual continua humano.",
    ]
    summary = [
        f"**Artefato:** {len(artifact):,} caracteres · {len(_lines(artifact))} linhas · {style_count} `<style>` · {scripts} `<script>` · {images} imagem(ns) · {sections} seção(ões).".replace(",", "."),
        f"**Regras acionadas:** {len(findings)} · {len(hits)} tipo(s) distinto(s).",
    ]
    findings, counts, verdict_text, questions = finalize(findings, mode, questions)
    return common(
        analysis="artifact", mode=mode, title="Revisão anti-clichê do artefato", summary=summary,
        findings=findings, counts=counts, verdict=verdict_text, questions=questions,
        rows=[{"rule": hit} for hit in hits],
        metrics={
            "characters": len(artifact), "lines": len(_lines(artifact)), "styles": style_count,
            "scripts": scripts, "images": images, "sections": sections, "rules": len(set(hits)),
        },
        limitations=limitations,
    )


def design_reference() -> dict[str, Any]:
    """Referência estática do esquema: tokens, bandas, movimento e limites."""
    groups = [
        {
            "key": key,
            "label": label,
            "slots": len(tokens),
            "tokens": [
                {"name": name, "layer": layer, "description": description}
                for name, layer, description in tokens
            ],
        }
        for key, label, tokens in TOKEN_GROUPS
    ]
    bands = [
        {"min": low, "max": high, "label": label, "meaning": meaning}
        for (low, high, label), meaning in zip(
            BANDS,
            (
                "Não passa: reescreva a direção antes de polir.",
                "Utilizável: resolve o trabalho, sem assinatura.",
                "Forte: direção clara e detalhe sob controle.",
                "Excepcional: há um momento próprio e defensável.",
            ),
        )
    ]
    return {
        "analysis": "reference",
        "mode": "reference",
        "schemaVersion": CANONICAL_SCHEMA,
        "groups": groups,
        "dimensions": [
            {"key": key, "label": label, "question": question, "band": anchor}
            for key, label, question, anchor in DIMENSIONS
        ],
        "bands": bands,
        "motion": {
            "enter": "200ms com cubic-bezier(0.23, 1, 0.32, 1)",
            "exit": "140ms",
            "rules": [
                "Nunca anime de `scale(0)`; parta de 0.96 ou de opacidade.",
                "`ease-in` atrasa justamente o trecho que o olho acompanha.",
                "Sempre ofereça alternativa em `prefers-reduced-motion: reduce`.",
            ],
        },
        "metrics": {
            "slots": len(SCHEMA_TOKENS),
            "groups": len(TOKEN_GROUPS),
            "dimensions": len(DIMENSIONS),
            "bands": len(BANDS),
        },
        "limits": {
            "tokensCharacters": MAX_TOKENS_CHARS,
            "designCharacters": MAX_DESIGN_CHARS,
            "manifestCharacters": MAX_MANIFEST_CHARS,
            "artifactCharacters": MAX_ARTIFACT_CHARS,
            "rows": MAX_ROWS,
            "fieldCharacters": MAX_FIELD_CHARS,
        },
        "executed": False,
        "readOnly": True,
        "limitations": [
            "É o esquema lido pelas quatro análises, não uma biblioteca de componentes.",
            "A referência não compila CSS, não baixa fontes e não valida identidade visual.",
            "Nenhum daemon, plugin, CLI ou runtime do upstream é instalado.",
        ],
    }
