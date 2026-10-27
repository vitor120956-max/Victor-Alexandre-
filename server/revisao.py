"""Revisão da revisão: escopo do diff, lotes, posição, duplicata, cobertura e regras.

O upstream é o `alibaba/open-code-review` (Apache-2.0, 48 mil estrelas), que
chama de "architetura híbrida" o casamento entre engenharia determinística e
agente. Ele nomeia três falhas que a parte determinística existe para evitar:
cobertura incompleta (o agente revisa só parte dos arquivos), deriva de posição
(o comentário aponta para a linha errada) e qualidade instável.

Esta camada mede exatamente essas três coisas sobre um diff unificado e um
conjunto de achados: o que precisa ser revisado, como agrupar, onde cada
comentário cai de fato, o que é duplicata entre regra e agente, quanto do diff
foi coberto e quais regras por caminho se aplicam. Nada é baixado, executado ou
enviado: o diff e os achados são o texto que você cola.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from .review import common, finalize, finding

VERSAO = "0.59.0"

MODOS = ("lite", "full", "ultra")

MAX_TEXTO = 1_800_000
MAX_ARQUIVOS = 2_000
MAX_ACHADOS = 5_000

LIMIAR_DIFF_GRANDE = 400
LIMIAR_ARQUIVO_GRANDE = 200
LIMIAR_LOTE_ARQUIVOS = 12
LIMIAR_LOTE_TOKENS = 20_000
LIMIAR_PRECISAO = 80
LIMIAR_COBERTURA = 60
TOLERANCIA_LINHA = 2
SIMILARIDADE_DUPLICATA = 0.5

SEVERIDADES = ("blocker", "major", "minor", "nit")
SEVERIDADE_ORDEM = {nome: indice for indice, nome in enumerate(SEVERIDADES)}
SINONIMOS_SEVERIDADE = {
    "critical": "blocker",
    "critico": "blocker",
    "crítico": "blocker",
    "bloqueio": "blocker",
    "high": "major",
    "alto": "major",
    "error": "major",
    "erro": "major",
    "warning": "minor",
    "warn": "minor",
    "medio": "minor",
    "médio": "minor",
    "medium": "minor",
    "info": "nit",
    "suggestion": "nit",
    "sugestao": "nit",
    "style": "nit",
    "estilo": "nit",
}
FONTES = ("regra", "agente")

CLASSES: dict[str, dict[str, Any]] = {
    "codigo": {"rotulo": "Código", "peso": 3, "revisar": True},
    "teste": {"rotulo": "Teste", "peso": 2, "revisar": True},
    "migracao": {"rotulo": "Migração", "peso": 4, "revisar": True},
    "infra": {"rotulo": "Infraestrutura", "peso": 4, "revisar": True},
    "segredo": {"rotulo": "Segredo", "peso": 5, "revisar": True},
    "config": {"rotulo": "Configuração", "peso": 2, "revisar": True},
    "doc": {"rotulo": "Documentação", "peso": 1, "revisar": False},
    "lockfile": {"rotulo": "Lockfile", "peso": 1, "revisar": False},
    "gerado": {"rotulo": "Gerado", "peso": 0, "revisar": False},
    "vendor": {"rotulo": "Dependência embarcada", "peso": 0, "revisar": False},
    "binario": {"rotulo": "Binário", "peso": 1, "revisar": False},
    "outro": {"rotulo": "Outro", "peso": 2, "revisar": True},
}

REGRAS_CLASSE: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("lockfile", re.compile(r"(^|/)(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|go\.sum|Cargo\.lock|poetry\.lock|composer\.lock|Gemfile\.lock)$", re.I)),
    ("segredo", re.compile(r"(^|/)(\.env(\..+)?|[^/]+\.(pem|key|p12|pfx)|id_rsa|credentials|secrets?\.(json|ya?ml))$", re.I)),
    ("gerado", re.compile(r"(^|/)(dist|build|out|coverage|\.next|target)/|\.min\.(js|css)$|(_generated|\.gen|\.pb)\.(go|ts|py|java)$|\.lock$", re.I)),
    ("vendor", re.compile(r"(^|/)(vendor|node_modules|third_party|external)/", re.I)),
    ("migracao", re.compile(r"(^|/)(migrations?|migrate|db/migrate)/|\.sql$|schema\.prisma$", re.I)),
    ("infra", re.compile(r"(^|/)(Dockerfile|docker-compose\.ya?ml|Makefile|\.github/workflows/|[^/]+\.tf|k8s/|helm/|charts/)", re.I)),
    ("doc", re.compile(r"\.(md|mdx|rst|adoc)$|(^|/)(docs?|documentation)/|(^|/)README", re.I)),
    ("teste", re.compile(r"(^|/)(tests?|__tests__|spec)/|_test\.go$|test_[^/]+\.py$|[^/]+_test\.py$|\.(test|spec)\.[jt]sx?$", re.I)),
    ("config", re.compile(r"\.(json|ya?ml|toml|ini|cfg|conf|properties|env)$|(^|/)(Makefile|\.editorconfig|tsconfig[^/]*\.json)$", re.I)),
    ("codigo", re.compile(r"\.(go|py|ts|tsx|js|jsx|java|kt|rs|rb|php|cs|swift|c|h|cpp|hpp|scala|sh|bash|lua|dart|ex|exs)$", re.I)),
)

RE_DIFF_GIT = re.compile(r"^diff --git a/(.+?) b/(.+)$")
RE_ANTIGO = re.compile(r"^--- (?:a/)?(.+?)(?:\t.*)?$")
RE_NOVO = re.compile(r"^\+\+\+ (?:b/)?(.+?)(?:\t.*)?$")
RE_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@ ?(.*)$")
RE_BINARIO = re.compile(r"^(Binary files .* differ|GIT binary patch)$")
RE_RENOMEADO = re.compile(r"^rename (from|to) (.+)$")

RE_SEGREDO_LINHA = re.compile(
    r"(?i)(api[_-]?key|secret|token|senha|password|passwd|private[_-]?key|access[_-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9/+_\-]{16,}"
)
RE_SEGREDO_CONHECIDO = re.compile(
    r"(AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|xox[baprs]-[A-Za-z0-9-]{10,})"
)
RE_ROLLBACK = re.compile(r"(?i)\b(down|rollback|revert|undo|desfazer)\b")


class RevisaoError(ValueError):
    """Entrada recusada antes do cálculo."""


def _modo(valor: str) -> str:
    if valor not in MODOS:
        raise RevisaoError(f"Modo inválido: {valor}. Use {', '.join(MODOS)}.")
    return valor


def _normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", texto.strip().lower())


def _palavras(texto: str) -> set[str]:
    return {item for item in re.findall(r"[a-zà-ú0-9_]{3,}", _normalizar(texto))}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _percentual(parte: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(100.0 * parte / total, 1)


def _fmt_pct(valor: float) -> str:
    """50.0 -> '50%'; 66.7 -> '66.7%'."""
    texto = f"{valor:g}"
    return f"{texto}%"


def _severidade(valor: str) -> str:
    limpo = _normalizar(valor).replace("-", "")
    if not limpo:
        return ""
    if limpo in SEVERIDADE_ORDEM:
        return limpo
    for chave, destino in SINONIMOS_SEVERIDADE.items():
        if limpo == _normalizar(chave).replace("-", ""):
            return destino
    return ""


def _fonte(valor: str) -> str:
    limpo = _normalizar(valor)
    if limpo in FONTES:
        return limpo
    if limpo in {"rule", "regras", "deterministico", "determinístico", "lint"}:
        return "regra"
    if limpo in {"agent", "llm", "modelo", "ia"}:
        return "agente"
    return ""


# --- diff -------------------------------------------------------------------


@dataclass
class Linha:
    tipo: str
    texto: str
    antiga: int | None
    nova: int | None


@dataclass
class Hunk:
    antiga_ini: int
    antiga_qtd: int
    nova_ini: int
    nova_qtd: int
    contexto: str = ""
    linhas: list[Linha] = field(default_factory=list)

    @property
    def adicionadas(self) -> list[int]:
        return [linha.nova for linha in self.linhas if linha.tipo == "adicionada" and linha.nova is not None]

    @property
    def novas(self) -> list[int]:
        return [linha.nova for linha in self.linhas if linha.tipo in {"adicionada", "contexto"} and linha.nova is not None]


@dataclass
class Arquivo:
    caminho: str
    antigo: str = ""
    status: str = "modificado"
    binario: bool = False
    hunks: list[Hunk] = field(default_factory=list)
    adicionadas: int = 0
    removidas: int = 0
    contexto: int = 0
    classe: str = "outro"
    risco: int = 2
    revisar: bool = True
    linhas_adicionadas: list[tuple[int, str]] = field(default_factory=list)
    linhas_removidas: list[tuple[int, str]] = field(default_factory=list)


def _classificar(caminho: str, binario: bool) -> str:
    if binario:
        return "binario"
    for classe, padrao in REGRAS_CLASSE:
        if padrao.search(caminho):
            return classe
    return "outro"


def ler_diff(diff: str) -> list[Arquivo]:
    """Lê um diff unificado e devolve os arquivos com hunks, churn e classe."""
    if len(diff) > MAX_TEXTO:
        raise RevisaoError(f"O diff passa de {MAX_TEXTO:,} caracteres.")
    texto = diff.replace("\r\n", "\n").replace("\r", "\n")
    if not texto.strip():
        raise RevisaoError("Informe um diff unificado (`git diff`, `git show` ou `gh pr diff`).")
    linhas = texto.split("\n")
    arquivos: list[Arquivo] = []
    atual: Arquivo | None = None
    hunk: Hunk | None = None
    antiga = nova = 0

    def fechar_hunk() -> None:
        nonlocal hunk
        if atual is not None and hunk is not None:
            atual.hunks.append(hunk)
        hunk = None

    def fechar_arquivo() -> None:
        nonlocal atual
        fechar_hunk()
        if atual is not None:
            if atual.binario:
                atual.classe = "binario"
            else:
                atual.classe = _classificar(atual.caminho, False)
            info = CLASSES.get(atual.classe, CLASSES["outro"])
            atual.risco = info["peso"]
            atual.revisar = bool(info["revisar"]) and (atual.adicionadas + atual.removidas > 0)
            arquivos.append(atual)
        atual = None

    for linha in linhas:
        casado = RE_DIFF_GIT.match(linha)
        if casado:
            fechar_arquivo()
            atual = Arquivo(caminho=casado.group(2), antigo=casado.group(1))
            continue
        if linha.startswith("diff --git"):
            fechar_arquivo()
            atual = Arquivo(caminho="(sem caminho)")
            continue
        if atual is None:
            if linha.startswith("--- ") or linha.startswith("+++ "):
                if atual is None and linha.startswith("+++ "):
                    caminho = RE_NOVO.match(linha)
                    if caminho:
                        atual = Arquivo(caminho=caminho.group(1))
                continue
            continue
        if RE_BINARIO.match(linha):
            atual.binario = True
            continue
        if linha.startswith("new file mode"):
            atual.status = "adicionado"
            continue
        if linha.startswith("deleted file mode"):
            atual.status = "removido"
            continue
        renomeado = RE_RENOMEADO.match(linha)
        if renomeado:
            atual.status = "renomeado"
            continue
        if linha.startswith("--- "):
            cabecalho_antigo = RE_ANTIGO.match(linha)
            if cabecalho_antigo:
                atual.antigo = "" if cabecalho_antigo.group(1) == "/dev/null" else cabecalho_antigo.group(1)
            continue
        if linha.startswith("+++ "):
            novo = RE_NOVO.match(linha)
            if novo and novo.group(1) != "/dev/null":
                atual.caminho = novo.group(1)
            continue
        cabecalho = RE_HUNK.match(linha)
        if cabecalho:
            fechar_hunk()
            antiga = int(cabecalho.group(1))
            nova = int(cabecalho.group(3))
            hunk = Hunk(
                antiga_ini=antiga,
                antiga_qtd=int(cabecalho.group(2) or 1),
                nova_ini=nova,
                nova_qtd=int(cabecalho.group(4) or 1),
                contexto=(cabecalho.group(5) or "").strip(),
            )
            continue
        if hunk is None:
            continue
        if linha.startswith("\\"):
            continue
        if linha.startswith("+"):
            hunk.linhas.append(Linha("adicionada", linha[1:], None, nova))
            atual.linhas_adicionadas.append((nova, linha[1:]))
            atual.adicionadas += 1
            nova += 1
            continue
        if linha.startswith("-"):
            hunk.linhas.append(Linha("removida", linha[1:], antiga, None))
            atual.linhas_removidas.append((antiga, linha[1:]))
            atual.removidas += 1
            antiga += 1
            continue
        conteudo = linha[1:] if linha.startswith(" ") else linha
        hunk.linhas.append(Linha("contexto", conteudo, antiga, nova))
        atual.contexto += 1
        antiga += 1
        nova += 1

    fechar_arquivo()
    if not arquivos:
        raise RevisaoError("Nenhum arquivo encontrado: o texto não parece um diff unificado.")
    if len(arquivos) > MAX_ARQUIVOS:
        raise RevisaoError(f"O diff tem mais de {MAX_ARQUIVOS:,} arquivos.")
    return arquivos


def _rotulo_classe(classe: str) -> str:
    return CLASSES.get(classe, CLASSES["outro"])["rotulo"]


def _churn(arquivo: Arquivo) -> int:
    return arquivo.adicionadas + arquivo.removidas


# --- 1. escopo --------------------------------------------------------------


def _segredos(arquivo: Arquivo) -> list[tuple[int, str]]:
    achados = []
    for numero, texto in arquivo.linhas_adicionadas:
        if RE_SEGREDO_CONHECIDO.search(texto) or RE_SEGREDO_LINHA.search(texto):
            achados.append((numero, texto.strip()[:90]))
    return achados


def analisar_escopo(*, diff: str, modo: str = "full") -> dict[str, Any]:
    """Decide o que precisa ser revisado, o que é mecânico e o que falta no diff."""
    modo = _modo(modo)
    arquivos = ler_diff(diff)

    revisar = [arquivo for arquivo in arquivos if arquivo.revisar]
    filtrar = [arquivo for arquivo in arquivos if not arquivo.revisar]
    adicionadas = sum(arquivo.adicionadas for arquivo in arquivos)
    removidas = sum(arquivo.removidas for arquivo in arquivos)
    churn = adicionadas + removidas
    testes = [arquivo for arquivo in arquivos if arquivo.classe == "teste"]
    docs = [arquivo for arquivo in arquivos if arquivo.classe == "doc"]
    migracoes = [arquivo for arquivo in arquivos if arquivo.classe == "migracao"]
    binarios = [arquivo for arquivo in arquivos if arquivo.binario]
    segredos: list[tuple[str, int, str]] = []
    for arquivo in arquivos:
        for numero, trecho in _segredos(arquivo):
            segredos.append((arquivo.caminho, numero, trecho))
        if arquivo.classe == "segredo" and arquivo.adicionadas:
            segredos.append((arquivo.caminho, 0, "arquivo de segredo alterado"))

    rows = [
        {
            "arquivo": arquivo.caminho,
            "classe": _rotulo_classe(arquivo.classe),
            "status": arquivo.status,
            "adicionadas": arquivo.adicionadas,
            "removidas": arquivo.removidas,
            "risco": arquivo.risco,
            "decisao": "revisar" if arquivo.revisar else "filtrar",
        }
        for arquivo in sorted(arquivos, key=lambda item: (-item.risco, -_churn(item), item.caminho))
    ]

    achados: list[dict[str, Any]] = []
    if not churn:
        achados.append(
            finding(
                "must",
                "diff-sem-linhas",
                "Diff sem linha alterada",
                f"{len(arquivos)} arquivo(s)",
                "Só há metadados: nenhuma linha adicionada ou removida.",
                "Sem linha alterada não há o que revisar linha a linha.",
                "Confira se o diff foi copiado inteiro, com os hunks `@@`.",
                "O parecer sai vazio e parece aprovação.",
            )
        )
    if segredos:
        amostra = ", ".join(f"{caminho}:{numero or '—'}" for caminho, numero, _ in segredos[:4])
        achados.append(
            finding(
                "must",
                "segredo-no-diff",
                f"{len(segredos)} possível(is) segredo(s) no diff",
                amostra,
                "Linha adicionada com chave, token ou arquivo de segredo versionado.",
                "Segredo commitado vaza para o histórico e para o CI antes de a revisão terminar.",
                "Revogue a credencial, remova do commit e use variável de ambiente.",
                "O valor fica no repositório para sempre, mesmo que a linha seja apagada depois.",
            )
        )
    if binarios:
        achados.append(
            finding(
                "should",
                "binario-sem-revisao",
                f"{len(binarios)} binário(s) no diff",
                ", ".join(arquivo.caminho for arquivo in binarios[:4]),
                "Arquivo binário não tem linha para comentar.",
                "Revisão linha a linha não cobre binário: ele passa sem escrutínio.",
                "Revise o binário à parte, por hash e origem.",
                "O arquivo entra sem revisão e ninguém percebe.",
            )
        )
    if revisar and not testes:
        achados.append(
            finding(
                "should",
                "sem-teste",
                "Código mudou sem teste no diff",
                f"{len(revisar)} arquivo(s) a revisar, 0 de teste",
                "Nenhum arquivo de teste aparece no mesmo diff.",
                "Sem teste no diff, a mudança de comportamento entra sem prova.",
                "Acrescente o teste que falha antes e passa depois, ou explique onde ele já existe.",
                "A revisão fica na leitura: nada prova que a mudança funciona.",
            )
        )
    for arquivo in migracoes:
        trecho = " ".join(texto for _, texto in arquivo.linhas_adicionadas)
        if arquivo.adicionadas and not RE_ROLLBACK.search(trecho):
            achados.append(
                finding(
                    "must",
                    "migracao-sem-rollback",
                    "Migração sem caminho de volta",
                    arquivo.caminho,
                    "A migração adiciona passo para frente e nada de `down`, `rollback` ou `revert`.",
                    "Migração sem volta transforma erro de deploy em incidente de dado.",
                    "Acrescente o `down` equivalente ou declare que a migração é irreversível e por quê.",
                    "O rollback vira restauração de backup.",
                )
            )
    if churn > LIMIAR_DIFF_GRANDE:
        achados.append(
            finding(
                "should",
                "diff-grande",
                f"Diff com {churn} linhas alteradas",
                f"{len(arquivos)} arquivo(s)",
                f"Acima de {LIMIAR_DIFF_GRANDE} linhas o revisor lê por amostragem.",
                "Diff grande é onde a cobertura incompleta aparece: ninguém lê tudo.",
                "Divida o PR por assunto ou declare o que ficou de fora da revisão.",
                "A parte não lida passa como aprovada.",
            )
        )
    grandes = [arquivo for arquivo in arquivos if _churn(arquivo) > LIMIAR_ARQUIVO_GRANDE]
    if grandes:
        achados.append(
            finding(
                "should",
                "arquivo-gigante",
                f"{len(grandes)} arquivo(s) acima de {LIMIAR_ARQUIVO_GRANDE} linhas alteradas",
                ", ".join(arquivo.caminho for arquivo in grandes[:4]),
                "Um arquivo concentra a maior parte do diff.",
                "Arquivo gigante costuma misturar refatoração com mudança de comportamento.",
                "Separe move/renomeação de lógica para o diff mostrar só o que importa.",
                "A revisão compara arquivos inteiros em vez de mudanças.",
            )
        )
    gerados = [arquivo for arquivo in arquivos if arquivo.classe == "gerado"]
    if gerados:
        achados.append(
            finding(
                "should",
                "gerado-no-diff",
                f"{len(gerados)} arquivo(s) gerado(s) versionado(s)",
                ", ".join(arquivo.caminho for arquivo in gerados[:4]),
                "Artefato de build, lockfile ou código gerado aparece no diff.",
                "Gerado no diff infla o churn e esconde a mudança real.",
                "Gere em CI e mantenha fora do commit.",
                "O diff cresce sem que ninguém tenha escrito aquilo.",
            )
        )
    if docs and not revisar:
        achados.append(
            finding(
                "nice",
                "diff-so-de-documentacao",
                "Diff só de documentação",
                f"{len(docs)} arquivo(s)",
                "Nenhum arquivo de código entre os revisáveis.",
                "PR de documentação não precisa do mesmo rito de código.",
                "Aprove com revisão de texto, sem exigir teste.",
                "O rito vira cerimônia e atrasa o que é só texto.",
            )
        )

    findings, counts, veredito, perguntas = finalize(
        achados,
        modo,
        [
            "O que ficou de fora deste diff — outro PR, outro repositório, outro time?",
            "Quem revisa a migração e como ela volta atrás?",
            "O teste que cobre esta mudança existe em outro lugar?",
        ],
    )
    risco_total = sum(arquivo.risco for arquivo in revisar)
    metrics = {
        "arquivos": len(arquivos),
        "revisar": len(revisar),
        "filtrar": len(filtrar),
        "adicionadas": adicionadas,
        "removidas": removidas,
        "linhas": churn,
        "testes": len(testes),
        "docs": len(docs),
        "risco": risco_total,
        "segredos": len(segredos),
    }
    summary = [
        f"{len(arquivos)} arquivo(s): {len(revisar)} para revisar e {len(filtrar)} filtrado(s); "
        f"+{adicionadas} −{removidas} linhas.",
        f"Risco somado dos revisáveis: {risco_total} ponto(s); {len(segredos)} sinal(is) de segredo.",
    ]
    limitations = [
        "A classe vem do caminho e da extensão: um `.py` de migração fora de pasta de migração não é reconhecido.",
        "Binário não é lido: a decisão de revisar é sobre o caminho, não sobre o conteúdo.",
        "O regex de segredo acha padrão conhecido, não toda credencial — e pode acusar exemplo de documento.",
        "Renomeação só é vista quando o diff traz `rename from`/`rename to`; fora isso, aparece como remoção mais adição.",
        "Nada é executado: o diff não é aplicado e o repositório não é lido.",
    ]
    return common(
        analysis="revisao.escopo",
        mode=modo,
        title="Escopo da revisão",
        summary=summary,
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows,
        metrics=metrics,
        limitations=limitations,
    )


# --- 2. lotes ---------------------------------------------------------------

LOCALES = {
    "en", "pt", "pt-br", "pt_br", "es", "fr", "de", "it", "ja", "ko", "ru", "zh", "zh-cn", "zh_cn",
    "zh-tw", "nl", "pl", "tr", "ar", "hi", "id", "vi", "th", "sv", "da", "fi", "cs", "uk",
}
RE_LOCALE = re.compile(r"^(?P<base>.+?)[._-](?P<locale>[A-Za-z]{2}(?:[-_][A-Za-z]{2})?)$")


def _separar_locale(nome: str) -> tuple[str, str] | None:
    """`messages_en` -> ('messages', 'en'); `README.zh-CN` -> ('README', 'zh-CN')."""
    casado = RE_LOCALE.match(nome)
    if not casado:
        return None
    locale = casado.group("locale").lower()
    if locale not in LOCALES:
        return None
    return casado.group("base"), casado.group("locale")


def _fonte_do_teste(caminho: str) -> str:
    partes = caminho.split("/")
    nome = partes[-1]
    pasta = partes[:-1]
    candidato = ""
    if nome.endswith("_test.go"):
        candidato = nome[: -len("_test.go")] + ".go"
    elif nome.startswith("test_") and nome.endswith(".py"):
        candidato = nome[len("test_"):]
    elif nome.endswith("_test.py"):
        candidato = nome[: -len("_test.py")] + ".py"
    elif re.search(r"\.(test|spec)\.[jt]sx?$", nome):
        candidato = re.sub(r"\.(test|spec)\.", ".", nome)
    if not candidato:
        return ""
    if pasta and pasta[-1] in {"tests", "test", "__tests__", "spec", "testdata"}:
        pasta = pasta[:-1]
    return "/".join([*pasta, candidato])


def _grupos(arquivos: list[Arquivo], max_arquivos: int) -> list[list[Arquivo]]:
    pais: dict[str, int] = {arquivo.caminho: indice for indice, arquivo in enumerate(arquivos)}

    def raiz(chave: str) -> str:
        while pais.get(chave, chave) != chave:
            chave = pais[chave]
        return chave

    def unir(a: str, b: str) -> None:
        if a not in pais or b not in pais:
            return
        raiz_a, raiz_b = raiz(a), raiz(b)
        if raiz_a != raiz_b:
            pais[raiz_b] = raiz_a

    for arquivo in arquivos:
        if arquivo.classe == "teste":
            origem = _fonte_do_teste(arquivo.caminho)
            if origem and origem in pais:
                unir(origem, arquivo.caminho)
    familias: dict[tuple[str, str, str], list[str]] = {}
    for arquivo in arquivos:
        pasta = "/".join(arquivo.caminho.split("/")[:-1])
        nome = arquivo.caminho.split("/")[-1]
        extensao = "." + nome.rsplit(".", 1)[1] if "." in nome else ""
        sem_extensao = nome[: -len(extensao)] if extensao else nome
        separado = _separar_locale(sem_extensao)
        if separado:
            base, _locale = separado
            familias.setdefault((pasta, base, extensao), []).append(arquivo.caminho)
    for chave, membros in familias.items():
        if len(membros) > 1:
            for outro in membros[1:]:
                unir(membros[0], outro)
    por_pasta: dict[tuple[str, str], list[str]] = {}
    for arquivo in arquivos:
        if arquivo.classe not in {"codigo", "config"}:
            continue
        pasta = "/".join(arquivo.caminho.split("/")[:-1])
        extensao = "." + arquivo.caminho.rsplit(".", 1)[1] if "." in arquivo.caminho else ""
        por_pasta.setdefault((pasta, extensao), []).append(arquivo.caminho)
    for membros in por_pasta.values():
        if 1 < len(membros) <= max_arquivos:
            for outro in membros[1:]:
                unir(membros[0], outro)

    grupos: dict[str, list[Arquivo]] = {}
    for arquivo in arquivos:
        grupos.setdefault(raiz(arquivo.caminho), []).append(arquivo)
    return sorted(grupos.values(), key=lambda grupo: (-sum(_churn(item) for item in grupo), grupo[0].caminho))


def _tokens_do_grupo(grupo: list[Arquivo]) -> int:
    caracteres = 0
    for arquivo in grupo:
        for hunk in arquivo.hunks:
            caracteres += sum(len(linha.texto) + 1 for linha in hunk.linhas)
    return (caracteres + 3) // 4


def montar_lotes(*, diff: str, modo: str = "full", max_arquivos: int = LIMIAR_LOTE_ARQUIVOS) -> dict[str, Any]:
    """Agrupa arquivos relacionados em unidades de revisão e mede o peso de cada uma."""
    modo = _modo(modo)
    if max_arquivos < 2 or max_arquivos > 50:
        raise RevisaoError("O teto de arquivos por lote precisa estar entre 2 e 50.")
    arquivos = [arquivo for arquivo in ler_diff(diff) if arquivo.revisar or arquivo.classe == "teste"]
    if not arquivos:
        raise RevisaoError("Nenhum arquivo revisável no diff: só há gerado, lockfile ou documentação.")

    grupos = _grupos(arquivos, max_arquivos)
    tokens = [_tokens_do_grupo(grupo) for grupo in grupos]
    rows = []
    for indice, (grupo, estimativa) in enumerate(zip(grupos, tokens), start=1):
        principal = grupo[0]
        rows.append(
            {
                "lote": indice,
                "arquivos": len(grupo),
                "principal": principal.caminho,
                "outros": ", ".join(item.caminho for item in grupo[1:6]) or "—",
                "classe": _rotulo_classe(principal.classe),
                "linhas": sum(_churn(item) for item in grupo),
                "tokens": estimativa,
            }
        )

    achados: list[dict[str, Any]] = []
    grandes = [row for row in rows if row["arquivos"] > max_arquivos or row["tokens"] > LIMIAR_LOTE_TOKENS]
    if grandes:
        achados.append(
            finding(
                "should",
                "lote-grande",
                f"{len(grandes)} lote(s) acima do teto",
                ", ".join(f"lote {row['lote']} ({row['arquivos']} arquivos, {row['tokens']} tokens)" for row in grandes[:3]),
                f"O teto é {max_arquivos} arquivos ou {LIMIAR_LOTE_TOKENS} tokens por unidade de revisão.",
                "Lote grande demais volta a ser o problema que o agrupamento devia resolver.",
                "Divida pelo assunto, não pela pasta.",
                "O revisor de novo lê por amostragem.",
            )
        )
    separados = []
    for arquivo in arquivos:
        if arquivo.classe != "teste":
            continue
        origem = _fonte_do_teste(arquivo.caminho)
        if not origem:
            continue
        lote_teste = next(row["lote"] for row in rows if arquivo.caminho in [row["principal"], *row["outros"].split(", ")])
        lote_origem = next((row["lote"] for row in rows if origem in [row["principal"], *row["outros"].split(", ")]), None)
        if lote_origem is not None and lote_origem != lote_teste:
            separados.append(f"{origem} e {arquivo.caminho}")
    if separados:
        achados.append(
            finding(
                "should",
                "teste-separado",
                f"{len(separados)} teste(s) fora do lote do código",
                "; ".join(separados[:3]),
                "O teste e o código que ele cobre caíram em unidades diferentes.",
                "Revisar os dois juntos é o que permite comparar intenção e prova.",
                "Agrupe o teste com o arquivo de origem.",
                "O revisor aprova o código sem ver o teste que deveria justificá-lo.",
            )
        )
    sem_original = []
    vistos = {arquivo.caminho for arquivo in arquivos}
    for arquivo in arquivos:
        pasta = "/".join(arquivo.caminho.split("/")[:-1])
        nome = arquivo.caminho.split("/")[-1]
        extensao = "." + nome.rsplit(".", 1)[1] if "." in nome else ""
        sem_extensao = nome[: -len(extensao)] if extensao else nome
        separado = _separar_locale(sem_extensao)
        if not separado:
            continue
        base, locale = separado
        original = "/".join([*([pasta] if pasta else []), base + extensao])
        if original not in vistos:
            sem_original.append(f"{arquivo.caminho} ({locale})")
    if sem_original:
        achados.append(
            finding(
                "should",
                "i18n-sem-original",
                f"{len(sem_original)} arquivo(s) de tradução sem o original",
                ", ".join(sem_original[:4]),
                "Arquivo localizado mudou e o texto de origem não está no diff.",
                "Tradução sem o original revisado costuma divergir em silêncio.",
                "Inclua o original no PR ou confirme que ele já está publicado.",
                "Duas versões do mesmo texto seguem caminhos diferentes.",
            )
        )
    if len(rows) == 1 and len(arquivos) > 4:
        achados.append(
            finding(
                "nice",
                "lote-unico",
                "Tudo caiu em um lote só",
                f"{len(arquivos)} arquivo(s)",
                "O agrupamento não separou nada: os arquivos compartilham pasta ou extensão.",
                "Lote único perde o isolamento de contexto que o agrupamento existe para dar.",
                "Separe por assunto quando o diff tiver mais de um.",
                "O agente lê tudo junto e mistura os temas.",
            )
        )
    if len(tokens) > 1 and max(tokens) > 3 * (sum(tokens) / len(tokens)):
        achados.append(
            finding(
                "nice",
                "lote-desbalanceado",
                "Um lote concentra o diff",
                f"maior {max(tokens)} tokens contra média {round(sum(tokens) / len(tokens))}",
                "A distribuição de trabalho entre as unidades é desigual.",
                "Lote muito maior que os outros domina o custo e o tempo.",
                "Mova parte dos arquivos para um lote vizinho ou divida o PR.",
                "A revisão demora o tempo do maior lote.",
            )
        )

    findings, counts, veredito, perguntas = finalize(
        achados,
        modo,
        [
            "Os arquivos deste lote são revisados pela mesma pessoa ou pelo mesmo agente?",
            "O teste e o código precisam ser lidos na mesma passada?",
            "Qual lote pode esperar o próximo PR?",
        ],
    )
    metrics = {
        "lotes": len(grupos),
        "arquivos": len(arquivos),
        "maior_lote": max((len(grupo) for grupo in grupos), default=0),
        "tokens": sum(tokens),
        "maior_tokens": max(tokens, default=0),
        "media_arquivos": round(len(arquivos) / len(grupos), 1) if grupos else 0.0,
    }
    summary = [
        f"{len(arquivos)} arquivo(s) em {len(grupos)} lote(s); maior lote com {metrics['maior_lote']} arquivo(s) e {metrics['maior_tokens']} token(s) estimados.",
        f"Estimativa total: {metrics['tokens']} tokens (1 token a cada 4 caracteres de diff).",
    ]
    limitations = [
        "O agrupamento usa caminho, nome e extensão: relação semântica entre arquivos não é detectada.",
        "A estimativa de token é lexical e aproximada; o tokenizador real do provedor não é usado.",
        "Arquivo filtrado (gerado, lockfile, documentação) não entra em lote — inclusive quando é o único do PR.",
        "O teto de arquivos por lote é escolha desta camada, não do upstream.",
    ]
    return common(
        analysis="revisao.lotes",
        mode=modo,
        title="Lotes de revisão",
        summary=summary,
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows,
        metrics=metrics,
        limitations=limitations,
    )


# --- achados -----------------------------------------------------------------

CAMPOS_ARQUIVO = ("file", "arquivo", "path", "caminho")
CAMPOS_LINHA = ("line", "linha", "line_number", "linenumber")
CAMPOS_SEVERIDADE = ("severity", "severidade", "level", "nivel")
CAMPOS_MENSAGEM = ("message", "mensagem", "body", "text", "comentario")
CAMPOS_REGRA = ("rule", "regra", "check", "rule_id")
CAMPOS_FONTE = ("source", "fonte", "origin", "origem")


def _primeiro(item: dict[str, Any], chaves: tuple[str, ...]) -> Any:
    for chave in chaves:
        if chave in item and item[chave] not in (None, ""):
            return item[chave]
    return None


def _caminho_limpo(caminho: str) -> str:
    limpo = caminho.strip().strip('"').strip("'").replace("\\", "/")
    while limpo.startswith("./"):
        limpo = limpo[2:]
    if limpo.startswith("a/") or limpo.startswith("b/"):
        limpo = limpo[2:]
    return limpo


def ler_achados(texto: str) -> list[dict[str, Any]]:
    """Lê achados em JSON (lista ou objeto com `findings`) ou em linhas `arquivo:linha | severidade | ...`."""
    if len(texto) > MAX_TEXTO:
        raise RevisaoError(f"Os achados passam de {MAX_TEXTO:,} caracteres.")
    bruto = texto.strip()
    if not bruto:
        raise RevisaoError("Informe os achados em JSON ou em linhas `arquivo:linha | severidade | fonte | regra | mensagem`.")
    itens: list[dict[str, Any]] = []
    if bruto[0] in "[{":
        try:
            dados = json.loads(bruto)
        except json.JSONDecodeError as exc:
            raise RevisaoError(f"Achados JSON inválidos na linha {exc.lineno}: {exc.msg}.") from exc
        lista = dados if isinstance(dados, list) else (dados.get("findings") or dados.get("achados") or dados.get("comments") or [])
        if not isinstance(lista, list):
            raise RevisaoError("O JSON precisa ser uma lista de achados ou um objeto com a chave `findings`.")
        for item in lista:
            if not isinstance(item, dict):
                continue
            arquivo = _primeiro(item, CAMPOS_ARQUIVO)
            if not arquivo:
                continue
            linha = _primeiro(item, CAMPOS_LINHA)
            try:
                numero = int(linha) if linha is not None else None
            except (TypeError, ValueError):
                numero = None
            itens.append(
                {
                    "arquivo": _caminho_limpo(str(arquivo)),
                    "linha": numero,
                    "severidade": str(_primeiro(item, CAMPOS_SEVERIDADE) or "").strip(),
                    "mensagem": str(_primeiro(item, CAMPOS_MENSAGEM) or "").strip(),
                    "regra": str(_primeiro(item, CAMPOS_REGRA) or "").strip(),
                    "fonte": str(_primeiro(item, CAMPOS_FONTE) or "").strip(),
                }
            )
    else:
        for numero_linha, linha in enumerate(bruto.splitlines(), start=1):
            limpa = linha.strip()
            if not limpa or limpa.startswith("#"):
                continue
            partes = [parte.strip() for parte in limpa.split("|")]
            if len(partes) < 2:
                continue
            local = partes[0]
            arquivo, _, posicao = local.rpartition(":")
            if not arquivo:
                arquivo, posicao = local, ""
            try:
                numero = int(posicao) if posicao else None
            except ValueError:
                arquivo, numero = local, None
            severidade = partes[1] if len(partes) > 1 else ""
            if len(partes) >= 5:
                fonte, regra, mensagem = partes[2], partes[3], " | ".join(partes[4:])
            elif len(partes) == 4:
                fonte, regra, mensagem = partes[2], "", partes[3]
            else:
                fonte, regra, mensagem = "", "", partes[2] if len(partes) > 2 else ""
            itens.append(
                {
                    "arquivo": _caminho_limpo(arquivo),
                    "linha": numero,
                    "severidade": severidade,
                    "mensagem": mensagem,
                    "regra": regra,
                    "fonte": fonte,
                }
            )
    if not itens:
        raise RevisaoError("Nenhum achado reconhecido: confira o caminho do arquivo em cada item.")
    if len(itens) > MAX_ACHADOS:
        raise RevisaoError(f"Mais de {MAX_ACHADOS:,} achados: revise em partes.")
    return itens


# --- 3. posição --------------------------------------------------------------


@dataclass
class MapaArquivo:
    caminho: str
    adicionadas: set[int] = field(default_factory=set)
    contexto: set[int] = field(default_factory=set)
    removidas: set[int] = field(default_factory=set)
    intervalo: tuple[int, int] = (0, 0)

    @property
    def maior_linha(self) -> int:
        candidatos = self.adicionadas | self.contexto
        return max(candidatos) if candidatos else 0

    def mais_proxima(self, linha: int) -> int | None:
        if not self.adicionadas:
            return None
        return min(self.adicionadas, key=lambda item: (abs(item - linha), item))


def _mapas(arquivos: list[Arquivo]) -> dict[str, MapaArquivo]:
    mapas: dict[str, MapaArquivo] = {}
    for arquivo in arquivos:
        mapa = MapaArquivo(caminho=arquivo.caminho)
        for hunk in arquivo.hunks:
            for linha in hunk.linhas:
                if linha.tipo == "adicionada" and linha.nova is not None:
                    mapa.adicionadas.add(linha.nova)
                elif linha.tipo == "contexto" and linha.nova is not None:
                    mapa.contexto.add(linha.nova)
                elif linha.tipo == "removida" and linha.antiga is not None:
                    mapa.removidas.add(linha.antiga)
            if hunk.nova_qtd:
                inicio, fim = hunk.nova_ini, hunk.nova_ini + hunk.nova_qtd - 1
                mapa.intervalo = (min(mapa.intervalo[0], inicio) if mapa.intervalo[0] else inicio, max(mapa.intervalo[1], fim))
        mapas[arquivo.caminho] = mapa
    return mapas


def _situar(achado: dict[str, Any], mapas: dict[str, MapaArquivo], tolerancia: int = TOLERANCIA_LINHA) -> tuple[str, str]:
    """Devolve (situação, sugestão) para um achado: exato, contexto, próximo, deslocado ou inválido."""
    mapa = mapas.get(achado["arquivo"])
    if mapa is None:
        return "arquivo-fora-do-diff", ""
    linha = achado["linha"]
    if linha is None:
        return "arquivo", ""
    if linha in mapa.adicionadas:
        return "exato", ""
    if linha in mapa.contexto:
        return "contexto", ""
    if linha in mapa.removidas:
        proxima = mapa.mais_proxima(linha)
        return "linha-removida", f"linha {proxima}" if proxima else ""
    proxima = mapa.mais_proxima(linha)
    if tolerancia and proxima is not None and abs(proxima - linha) <= tolerancia:
        return "proximo", f"linha {proxima}"
    inicio, fim = mapa.intervalo
    if inicio and inicio <= linha <= fim:
        proxima = mapa.mais_proxima(linha)
        return "deslocado", f"linha {proxima}" if proxima else ""
    if 1 <= linha <= mapa.maior_linha and mapa.adicionadas:
        proxima = mapa.mais_proxima(linha)
        return "deslocado", f"linha {proxima}" if proxima else ""
    return "linha-inexistente", ""


def verificar_posicao(*, diff: str, achados: str, tolerancia: int = TOLERANCIA_LINHA, modo: str = "full") -> dict[str, Any]:
    """Confere se cada comentário cai em linha que existe no diff — a deriva de posição."""
    modo = _modo(modo)
    if tolerancia < 0 or tolerancia > 50:
        raise RevisaoError("A tolerância precisa estar entre 0 e 50 linhas.")
    mapas = _mapas(ler_diff(diff))
    itens = ler_achados(achados)

    rows = []
    contagem = {
        "exato": 0, "contexto": 0, "proximo": 0, "arquivo": 0,
        "deslocado": 0, "linha-removida": 0, "linha-inexistente": 0, "arquivo-fora-do-diff": 0,
    }
    for achado in itens:
        situacao, sugestao = _situar(achado, mapas, tolerancia)
        contagem[situacao] = contagem.get(situacao, 0) + 1
        rows.append(
            {
                "arquivo": achado["arquivo"],
                "linha": achado["linha"] if achado["linha"] is not None else "—",
                "situacao": situacao,
                "sugestao": sugestao or "—",
            }
        )

    fora = [row for row in rows if row["situacao"] == "arquivo-fora-do-diff"]
    removidas = [row for row in rows if row["situacao"] == "linha-removida"]
    inexistentes = [row for row in rows if row["situacao"] == "linha-inexistente"]
    deslocadas = [row for row in rows if row["situacao"] == "deslocado"]
    validos = contagem["exato"] + contagem["contexto"] + contagem["proximo"] + contagem["arquivo"]
    precisao = _percentual(validos, len(itens))

    achados_lista: list[dict[str, Any]] = []
    if fora:
        achados_lista.append(
            finding(
                "must",
                "arquivo-fora-do-diff",
                f"{len(fora)} comentário(s) em arquivo que não está no diff",
                ", ".join(sorted({str(row["arquivo"]) for row in fora})[:4]),
                "O caminho do achado não aparece no diff colado.",
                "Comentário em arquivo ausente não é ancorável: o host recusa ou cola no arquivo errado.",
                "Alinhe o caminho com o do diff ou descarte o achado.",
                "A revisão aponta para fora e o autor não encontra o trecho.",
            )
        )
    if removidas:
        achados_lista.append(
            finding(
                "must",
                "linha-removida",
                f"{len(removidas)} comentário(s) em linha removida",
                ", ".join(f"{row['arquivo']}:{row['linha']}" for row in removidas[:4]),
                "A linha existe só na versão antiga do arquivo.",
                "A linha não existe mais no arquivo final: o comentário não pode ser postado ali.",
                "Mova o comentário para a linha nova equivalente, se ela existir.",
                "O comentário some na publicação ou aparece na linha errada.",
            )
        )
    if inexistentes:
        achados_lista.append(
            finding(
                "must",
                "linha-inexistente",
                f"{len(inexistentes)} comentário(s) em linha inexistente",
                ", ".join(f"{row['arquivo']}:{row['linha']}" for row in inexistentes[:4]),
                "O número da linha passa do maior número do arquivo no diff.",
                "Linha inventada é a forma mais direta de deriva de posição.",
                "Recalcule a âncora a partir do hunk correspondente.",
                "O comentário é recusado pela API do host.",
            )
        )
    if deslocadas:
        achados_lista.append(
            finding(
                "should",
                "posicao-deslocada",
                f"{len(deslocadas)} comentário(s) fora de hunk",
                ", ".join(f"{row['arquivo']}:{row['linha']}→{row['sugestao']}" for row in deslocadas[:4]),
                "A linha existe no arquivo, mas está fora das linhas que o diff mostra.",
                "Comentário fora do hunk não tem contexto para o autor avaliar.",
                "Ancore no `adição` mais próximo, indicado na sugestão.",
                "O autor vê o comentário solto e não entende o que mudou.",
            )
        )
    if itens and precisao < LIMIAR_PRECISAO:
        achados_lista.append(
            finding(
                "should",
                "precisao-baixa",
                f"Precisão de ancoragem em {_fmt_pct(precisao)}",
                f"{validos} de {len(itens)} ancorados",
                f"Abaixo de {LIMIAR_PRECISAO}% dos comentários caem em linha do diff.",
                "Revisão com âncora errada custa mais tempo do que revisão nenhuma.",
                "Reancore os deslocados antes de publicar.",
                "O autor perde tempo procurando o trecho certo.",
            )
        )
    if not itens:
        achados_lista.append(
            finding(
                "nice",
                "sem-achados",
                "Nenhum achado para posicionar",
                "lista vazia",
                "Não há comentário para conferir.",
                "Cobertura zero também pode significar revisão que não aconteceu.",
                "Confirme se a revisão rodou e se o resultado foi colado inteiro.",
                "O silêncio parece aprovação.",
            )
        )

    findings, counts, veredito, perguntas = finalize(
        achados_lista,
        modo,
        [
            "O host aceita comentário em linha de contexto ou só em linha adicionada?",
            "A âncora deve ser recalculada no arquivo final ou no diff?",
            "Quem confere a posição antes de publicar o comentário?",
        ],
    )
    metrics = {
        "achados": len(itens),
        "exatos": contagem["exato"],
        "contexto": contagem["contexto"],
        "proximos": contagem["proximo"],
        "deslocados": contagem["deslocado"],
        "invalidos": len(removidas) + len(inexistentes) + len(fora),
        "precisao": precisao,
    }
    summary = [
        f"{len(itens)} comentário(s): {contagem['exato']} em linha adicionada, {contagem['contexto']} em contexto, "
        f"{contagem['proximo']} a até {tolerancia} linha(s) da adição, {contagem['deslocado']} deslocado(s) "
        f"e {metrics['invalidos']} inválido(s).",
        f"Precisão de ancoragem: {_fmt_pct(precisao)}.",
    ]
    limitations = [
        "A âncora é conferida contra o diff colado: se o diff veio truncado, linha válida parece inexistente.",
        "Linha de contexto é aceita como posição válida, mas nem todo host permite comentar nela.",
        "Renomeação e mudança de arquivo não são reconstruídas: vale o caminho que está no diff.",
        "O deslocamento considera a linha adicionada mais próxima, não a intenção do comentário.",
        f"Linha a até {tolerancia} posição(ões) de uma adição conta como ancoragem aceitável, não como erro.",
        "Nada é publicado: a verificação é local e não chama a API do host.",
    ]
    return common(
        analysis="revisao.posicao",
        mode=modo,
        title="Posição dos comentários",
        summary=summary,
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows,
        metrics=metrics,
        limitations=limitations,
    )


# --- 4. achados --------------------------------------------------------------

RE_PROSA = re.compile(r"\b(fix|corrija|sugest|recomend|considere|should|must|nice|please)\b", re.I)


def _limpar_mensagem(texto: str) -> str:
    limpo = re.sub(r"^[\s>\-*#]+", "", texto or "")
    return re.sub(r"\s+", " ", limpo).strip()


def _resumo(texto: str, limite: int = 110) -> str:
    limpo = re.sub(r"\s+", " ", texto).strip()
    if len(limpo) <= limite:
        return limpo or "—"
    corte = limpo[:limite].rsplit(" ", 1)[0]
    return f"{corte}…"


def _fonte_padrao(item: dict[str, Any]) -> str:
    """Sem fonte declarada: id de regra sugere pipeline determinístico; prosa solta sugere agente."""
    if item.get("regra"):
        return "regra"
    return "agente"


def _chave_exata(item: dict[str, Any]) -> tuple[Any, ...]:
    return (item["arquivo"], item["linha"], item["severidade"], _normalizar(item["mensagem"]))


def _ordenar_chave(item: dict[str, Any]) -> tuple[Any, ...]:
    linha = item["linha"] if item["linha"] is not None else 0
    return (SEVERIDADE_ORDEM.get(item["severidade"], 9), item["arquivo"], linha, item["regra"])


def normalizar_achados(
    *,
    achados: str,
    limite: int = 50,
    severidade_minima: str = "nit",
    modo: str = "full",
) -> dict[str, Any]:
    """Padroniza severidade e fonte, junta repetidos e ordena o que o autor vê primeiro."""
    modo = _modo(modo)
    if limite < 1 or limite > 500:
        raise RevisaoError("O limite de achados por página precisa estar entre 1 e 500.")
    minimo = _severidade(severidade_minima)
    if not minimo:
        raise RevisaoError(f"Severidade mínima inválida: {severidade_minima}. Use {'|'.join(SEVERIDADES)}.")
    itens = ler_achados(achados)

    padronizados: list[dict[str, Any]] = []
    desconhecidas = 0
    sem_mensagem = 0
    sem_regra = 0
    sem_fonte = 0
    for item in itens:
        severidade = _severidade(item["severidade"])
        if not severidade:
            desconhecidas += 1
            severidade = "minor"
        fonte = _fonte(item["fonte"])
        if not fonte:
            sem_fonte += 1
            fonte = _fonte_padrao(item)
        mensagem = _limpar_mensagem(item["mensagem"])
        if not mensagem:
            sem_mensagem += 1
        if not item["regra"]:
            sem_regra += 1
        padronizados.append({**item, "severidade": severidade, "fonte": fonte, "mensagem": mensagem})

    for item, original in zip(padronizados, itens):
        item["_bruta"] = original["severidade"]
        item["_bruta_fonte"] = original["fonte"]

    mantidos: list[dict[str, Any]] = []
    vistos: dict[tuple[Any, ...], dict[str, Any]] = {}
    duplicados = 0
    for item in padronizados:
        chave = _chave_exata(item)
        anterior = vistos.get(chave)
        if anterior is not None:
            anterior["_ocorrencias"] += 1
            duplicados += 1
            continue
        vistos[chave] = item
        item["_ocorrencias"] = 1
        mantidos.append(item)

    mantidos.sort(key=_ordenar_chave)
    filtrados = [item for item in mantidos if SEVERIDADE_ORDEM[item["severidade"]] <= SEVERIDADE_ORDEM[minimo]]
    mostrados = filtrados[:limite]

    rows = []
    for posicao, item in enumerate(mostrados, start=1):
        rows.append(
            {
                "ordem": posicao,
                "arquivo": item["arquivo"],
                "linha": item["linha"] if item["linha"] is not None else "—",
                "severidade": item["severidade"],
                "fonte": item["fonte"],
                "regra": item["regra"] or "—",
                "ocorrencias": item["_ocorrencias"],
                "resumo": _resumo(item["mensagem"]),
            }
        )

    por_severidade = {nome: sum(1 for item in filtrados if item["severidade"] == nome) for nome in SEVERIDADES}
    por_fonte = {nome: sum(1 for item in filtrados if item["fonte"] == nome) for nome in FONTES}
    arquivos = sorted({item["arquivo"] for item in filtrados})
    sem_linha = sum(1 for item in filtrados if item["linha"] is None)
    total = len(filtrados)
    inflados = _percentual(por_severidade["blocker"], total) if total else 0.0

    achados_lista: list[dict[str, Any]] = []
    if duplicados:
        achados_lista.append(
            finding(
                "should",
                "achados-duplicados",
                f"{duplicados} achado(s) repetido(s)",
                f"{len(itens)} brutos, {len(mantidos)} depois de juntar iguais",
                "Mesmo arquivo, linha, severidade e texto normalizado apareceram mais de uma vez.",
                "Repetição polui a leitura e faz a revisão parecer maior do que é.",
                "Mantenha uma ocorrência e cite a contagem.",
                "O autor relê o mesmo problema três vezes e para de confiar na contagem.",
            )
        )
    if sem_mensagem:
        achados_lista.append(
            finding(
                "must",
                "sem-mensagem",
                f"{sem_mensagem} achado(s) sem texto",
                "mensagem vazia depois da normalização",
                "O item tem arquivo e severidade, mas não diz o que está errado.",
                "Achado mudo não é acionável e costuma vir de serialização incompleta.",
                "Preencha a mensagem ou descarte o item antes de publicar.",
                "O autor recebe um marcador sem explicação.",
            )
        )
    if desconhecidas:
        achados_lista.append(
            finding(
                "should",
                "severidade-desconhecida",
                f"{desconhecidas} achado(s) com severidade fora do padrão",
                "normalizados para minor",
                f"Os valores caem em {', '.join(SEVERIDADES)} mais os sinônimos conhecidos.",
                "Severidade livre impede ordenar e impede contar bloqueios.",
                "Mapeie o vocabulário do produtor para a escala de quatro níveis.",
                "Todo achado vira ruído de mesma prioridade.",
            )
        )
    if total and inflados > 40 and por_severidade["blocker"] >= 3:
        achados_lista.append(
            finding(
                "should",
                "severidade-inflada",
                f"{_fmt_pct(inflados)} dos achados são blocker",
                f"{por_severidade['blocker']} de {total}",
                "Bloqueio perde significado quando a maioria bloqueia.",
                "Escala inflada faz o autor parar de distinguir o que trava o merge.",
                "Reserve blocker para o que quebra produção ou perde dado.",
                "O bloqueio real se perde no meio dos falsos.",
            )
        )
    if len(arquivos) == 1 and total >= 5:
        achados_lista.append(
            finding(
                "nice",
                "achados-concentrados",
                "Todos os achados estão em um arquivo",
                arquivos[0],
                "A revisão inteira recaiu sobre um único arquivo.",
                "Concentração pode ser correta, mas também esconde arquivo que ninguém abriu.",
                "Confirme que os outros arquivos do diff foram lidos.",
                "O resto do PR passa sem comentário por omissão.",
            )
        )
    if sem_linha:
        achados_lista.append(
            finding(
                "nice",
                "sem-linha",
                f"{sem_linha} achado(s) sem linha",
                "comentário de arquivo, não de trecho",
                "O item aponta o arquivo sem apontar a linha.",
                "Sem linha, o comentário não ancora no diff e perde o contexto do trecho.",
                "Acrescente a linha quando o problema for local.",
                "O autor precisa procurar o trecho no arquivo inteiro.",
            )
        )
    if sem_regra and sem_regra == total:
        achados_lista.append(
            finding(
                "nice",
                "sem-regra",
                "Nenhum achado traz identificador de regra",
                "campo `rule` vazio em todos",
                "Não é possível saber qual verificador gerou cada comentário.",
                "Sem origem rastreável não se mede falso positivo por regra.",
                "Inclua o id da regra no achado.",
                "A mesma regra ruidosa volta no próximo PR sem ninguém notar.",
            )
        )
    if not itens:
        achados_lista.append(
            finding(
                "nice",
                "sem-achados",
                "Nenhum achado informado",
                "lista vazia",
                "Não há comentário para normalizar.",
                "Lista vazia pode ser revisão limpa ou revisão que não rodou.",
                "Confirme que o produtor rodou e que a saída foi colada inteira.",
                "A ausência de comentário parece aprovação.",
            )
        )

    findings, counts, veredito, perguntas = finalize(
        achados_lista,
        modo,
        [
            "Quem mapeia o vocabulário de severidade do produtor para blocker, major, minor e nit?",
            "Qual achado deste lote o autor deve ler primeiro?",
            "O limite por página é escolha da revisão ou do host?",
        ],
    )
    metrics = {
        "brutos": len(itens),
        "normalizados": total,
        "duplicados": duplicados,
        "blockers": por_severidade["blocker"],
        "majors": por_severidade["major"],
        "minors": por_severidade["minor"],
        "nits": por_severidade["nit"],
        "regra": por_fonte["regra"],
        "agente": por_fonte["agente"],
        "arquivos": len(arquivos),
        "sem_linha": sem_linha,
        "inflados": inflados,
        "mostrados": len(mostrados),
    }
    summary = [
        f"{len(itens)} achado(s) brutos viraram {total} único(s): "
        f"{por_severidade['blocker']} blocker, {por_severidade['major']} major, "
        f"{por_severidade['minor']} minor e {por_severidade['nit']} nit.",
        f"Origem: {por_fonte['regra']} de regra e {por_fonte['agente']} de agente; {len(arquivos)} arquivo(s) citado(s).",
        f"Mostrando {len(mostrados)} de {total}, do mais grave para o mais leve.",
    ]
    limitations = [
        "Dois textos que dizem a mesma coisa com palavras diferentes não são juntados aqui; isso é papel de `revisao.duplicatas`.",
        "Severidade ausente ou desconhecida vira minor, o que pode esconder um bloqueio real.",
        "Fonte ausente é inferida: id de regra presente indica regra, caso contrário agente.",
        "O limite por página corta pela gravidade; não há paginação.",
        "Nada é publicado: a lista normalizada não é enviada ao host.",
    ]
    return common(
        analysis="revisao.achados",
        mode=modo,
        title="Achados normalizados",
        summary=summary,
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows,
        metrics=metrics,
        limitations=limitations,
    )


# --- 5. duplicatas -----------------------------------------------------------

PARADAS = {
    "que", "para", "com", "uma", "dos", "das", "por", "como", "mas", "nao", "este", "esta", "isso",
    "aqui", "essa", "esse", "sao", "foi", "ser", "tem", "deve", "pode", "quando", "onde", "tambem",
    "mais", "muito", "pelo", "pela", "nos", "nas", "aos", "seu", "sua", "ele", "ela", "voce", "the",
    "and", "for", "with", "this", "that", "from", "are", "was", "has", "have", "you", "not", "but",
    "should", "must", "please", "fix", "corrija", "considere", "sugestao",
}


def _sem_acento(texto: str) -> str:
    return "".join(caractere for caractere in unicodedata.normalize("NFD", texto) if unicodedata.category(caractere) != "Mn")


def _assinatura(texto: str) -> set[str]:
    """Palavras comparáveis: sem acento, minúsculas, sem palavras vazias."""
    palavras = re.findall(r"[a-z0-9_]{3,}", _sem_acento(_normalizar(texto)))
    return {palavra for palavra in palavras if palavra not in PARADAS}


def _proximos(a: dict[str, Any], b: dict[str, Any], tolerancia: int) -> bool:
    if a["arquivo"] != b["arquivo"]:
        return False
    if a["linha"] is None or b["linha"] is None:
        return a["linha"] is None and b["linha"] is None
    return abs(a["linha"] - b["linha"]) <= tolerancia


def comparar_duplicatas(
    *,
    achados: str,
    tolerancia: int = TOLERANCIA_LINHA,
    similaridade: float = SIMILARIDADE_DUPLICATA,
    modo: str = "full",
) -> dict[str, Any]:
    """Encontra o mesmo problema reportado duas vezes — sobretudo por regra e por agente."""
    modo = _modo(modo)
    if not 0.1 <= similaridade <= 1.0:
        raise RevisaoError("A similaridade precisa estar entre 0,1 e 1,0.")
    if tolerancia < 0 or tolerancia > 50:
        raise RevisaoError("A tolerância precisa estar entre 0 e 50 linhas.")
    itens = ler_achados(achados)
    for item in itens:
        item["severidade"] = _severidade(item["severidade"]) or "minor"
        item["fonte"] = _fonte(item["fonte"]) or _fonte_padrao(item)
        item["assinatura"] = _assinatura(item["mensagem"])

    por_arquivo: dict[str, list[int]] = {}
    for indice, item in enumerate(itens):
        por_arquivo.setdefault(item["arquivo"], []).append(indice)
    for indices in por_arquivo.values():
        indices.sort(key=lambda posicao: (itens[posicao]["linha"] is None, itens[posicao]["linha"] or 0))

    pais = list(range(len(itens)))

    def raiz(posicao: int) -> int:
        while pais[posicao] != posicao:
            pais[posicao] = pais[pais[posicao]]
            posicao = pais[posicao]
        return posicao

    def unir(a: int, b: int) -> None:
        raiz_a, raiz_b = raiz(a), raiz(b)
        if raiz_a != raiz_b:
            pais[max(raiz_a, raiz_b)] = min(raiz_a, raiz_b)

    cruzados = 0
    duplicatas = 0
    internas = 0
    conflitos = 0
    pares: list[dict[str, Any]] = []
    for indices in por_arquivo.values():
        for posicao, primeiro in enumerate(indices):
            for segundo in indices[posicao + 1:]:
                a, b = itens[primeiro], itens[segundo]
                if a["linha"] is not None and b["linha"] is not None and b["linha"] - a["linha"] > tolerancia:
                    break
                if not _proximos(a, b, tolerancia):
                    continue
                parecido = _jaccard(a["assinatura"], b["assinatura"])
                mesma_fonte = a["fonte"] == b["fonte"]
                if not mesma_fonte:
                    cruzados += 1
                    if parecido < similaridade:
                        continue
                    duplicatas += 1
                    unir(primeiro, segundo)
                    diferente = SEVERIDADE_ORDEM[a["severidade"]] != SEVERIDADE_ORDEM[b["severidade"]]
                    if diferente:
                        conflitos += 1
                else:
                    if parecido < max(similaridade, 0.75):
                        continue
                    internas += 1
                    unir(primeiro, segundo)
                pares.append(
                    {
                        "arquivo": a["arquivo"],
                        "linha": a["linha"] if a["linha"] is not None else "—",
                        "fontes": f"{a['fonte']}×{b['fonte']}",
                        "similaridade": round(parecido * 100, 1),
                        "severidades": f"{a['severidade']}/{b['severidade']}",
                        "tipo": "entre fontes" if not mesma_fonte else "mesma fonte",
                    }
                )

    grupos: dict[int, list[int]] = {}
    for indice in range(len(itens)):
        grupos.setdefault(raiz(indice), []).append(indice)
    clusters = [membros for membros in grupos.values() if len(membros) > 1]
    clusters.sort(key=lambda membros: (itens[membros[0]]["arquivo"], itens[membros[0]]["linha"] or 0))

    rows = []
    for numero, membros in enumerate(clusters, start=1):
        escolhidos = [itens[posicao] for posicao in membros]
        fontes = sorted({item["fonte"] for item in escolhidos})
        pior = min(escolhidos, key=lambda item: SEVERIDADE_ORDEM[item["severidade"]])
        linhas = sorted({item["linha"] for item in escolhidos if item["linha"] is not None})
        rows.append(
            {
                "grupo": numero,
                "arquivo": escolhidos[0]["arquivo"],
                "linhas": ", ".join(str(linha) for linha in linhas) or "—",
                "achados": len(escolhidos),
                "fontes": " + ".join(fontes),
                "severidades": ", ".join(sorted({item["severidade"] for item in escolhidos}, key=SEVERIDADE_ORDEM.get)),
                "acao": f"manter um comentário em {pior['severidade']}",
                "resumo": _resumo(escolhidos[0]["mensagem"]),
            }
        )

    por_fonte = {nome: sum(1 for item in itens if item["fonte"] == nome) for nome in FONTES}
    taxa = _percentual(duplicatas, cruzados) if cruzados else 0.0
    total = len(itens)

    achados_lista: list[dict[str, Any]] = []
    if duplicatas:
        achados_lista.append(
            finding(
                "should",
                "duplicata-entre-fontes",
                f"{duplicatas} comentário(s) repetido(s) entre regra e agente",
                f"{len(clusters)} grupo(s) em {total} achado(s)",
                f"Pares no mesmo arquivo e a até {tolerancia} linha(s) com similaridade de palavras acima de {round(similaridade * 100)}%.",
                "Duplicata entre camadas é o efeito colateral esperado de revisão híbrida sem junção.",
                "Publique uma vez: guarde a âncora da regra e a explicação do agente.",
                "O autor recebe o mesmo pedido duas vezes e desconta a revisão inteira.",
            )
        )
    if conflitos:
        achados_lista.append(
            finding(
                "must",
                "conflito-severidade",
                f"{conflitos} duplicata(s) com severidade divergente",
                ", ".join(f"{row['arquivo']}:{row['linhas']} ({row['severidades']})" for row in rows[:3]) or "ver grupos",
                "O mesmo trecho recebeu gravidades diferentes das duas fontes.",
                "Divergência de gravidade no mesmo ponto é sinal de regra mal calibrada ou de agente exagerando.",
                "Defina qual fonte manda em conflito — normalmente a determinística — e registre a decisão.",
                "O autor não sabe se aquilo bloqueia ou é sugestão.",
            )
        )
    if internas:
        achados_lista.append(
            finding(
                "nice",
                "duplicata-interna",
                f"{internas} par(es) quase idêntico(s) na mesma fonte",
                "similaridade acima de 75%",
                "A mesma fonte repetiu o comentário no mesmo arquivo.",
                "Repetição interna costuma vir de varredura por arquivo sem deduplicação.",
                "Deduplique a saída do produtor antes de publicar.",
                "O volume de comentários cresce sem informação nova.",
            )
        )
    if (por_fonte["regra"] and not por_fonte["agente"]) or (por_fonte["agente"] and not por_fonte["regra"]):
        unica = "regra" if por_fonte["regra"] else "agente"
        achados_lista.append(
            finding(
                "should",
                "fonte-unica",
                f"Só uma fonte revisou: {unica}",
                f"{total} achado(s), todos de {unica}",
                "Não há comentário da outra camada para comparar.",
                "Revisão híbrida depende das duas: a determinística não cobre o que exige leitura, o agente não garante cobertura.",
                "Rode a outra camada antes de concluir que não há duplicata.",
                "O relatório de duplicata mede zero porque metade da revisão não aconteceu.",
            )
        )
    if not itens:
        achados_lista.append(
            finding(
                "nice",
                "sem-achados",
                "Nenhum achado para comparar",
                "lista vazia",
                "Não há comentário para procurar repetição.",
                "Sem comentário não se mede duplicata.",
                "Confirme que as duas camadas rodaram e que a saída foi colada inteira.",
                "Zero duplicata parece revisão enxuta.",
            )
        )

    findings, counts, veredito, perguntas = finalize(
        achados_lista,
        modo,
        [
            "Quem publica o comentário final quando regra e agente apontam o mesmo trecho?",
            "Em conflito de gravidade, qual camada vence?",
            f"Similaridade de {round(similaridade * 100)}% por palavras é suficiente para este projeto?",
        ],
    )
    metrics = {
        "achados": total,
        "pares": len(pares),
        "pares_entre_fontes": cruzados,
        "duplicatas": duplicatas,
        "grupos": len(clusters),
        "internas": internas,
        "conflitos": conflitos,
        "taxa": taxa,
        "regra": por_fonte["regra"],
        "agente": por_fonte["agente"],
    }
    summary = [
        f"{total} achado(s) em {len(clusters)} grupo(s) de repetição; {duplicatas} par(es) entre fontes e {internas} na mesma fonte.",
        f"{cruzados} par(es) comparável(is) entre regra e agente, duplicidade de {_fmt_pct(taxa)}.",
        f"Conflito de severidade em {conflitos} par(es).",
    ]
    limitations = [
        "A comparação é lexical (Jaccard de palavras sem acento): sinônimo e frase reescrita não são reconhecidos.",
        "Só compara itens do mesmo arquivo e a até a tolerância de linhas escolhida.",
        "Achado sem linha só é comparado com outro sem linha.",
        "O agrupamento é transitivo: A parecido com B e B com C põe os três no mesmo grupo.",
        "Nada é publicado ou mesclado: a decisão de qual comentário manter fica com quem revisa.",
    ]
    return common(
        analysis="revisao.duplicatas",
        mode=modo,
        title="Duplicatas entre camadas",
        summary=summary,
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows,
        metrics=metrics,
        limitations=limitations,
    )


# --- 6. cobertura ------------------------------------------------------------


def _lista_caminhos(texto: str) -> list[str]:
    if len(texto) > MAX_TEXTO:
        raise RevisaoError(f"A lista de revisados passa de {MAX_TEXTO:,} caracteres.")
    caminhos: list[str] = []
    for pedaco in re.split(r"[\n,;]+", texto or ""):
        limpo = _caminho_limpo(pedaco.split(" -> ")[0].split("=>")[0])
        if limpo and not limpo.startswith("#"):
            caminhos.append(limpo)
    return caminhos


def medir_cobertura(*, diff: str, revisados: str, modo: str = "full") -> dict[str, Any]:
    """Compara o que o diff pedia para revisar com o que a revisão realmente abriu."""
    modo = _modo(modo)
    arquivos = ler_diff(diff)
    esperados = [arquivo for arquivo in arquivos if arquivo.revisar]
    filtrados = [arquivo for arquivo in arquivos if not arquivo.revisar]
    declarados = _lista_caminhos(revisados)
    conjunto = set(declarados)
    nomes = {arquivo.caminho for arquivo in arquivos}
    conhecidos = [caminho for caminho in declarados if caminho in nomes]
    desconhecidos = sorted({caminho for caminho in declarados if caminho not in nomes})
    lidos = {arquivo.caminho for arquivo in esperados if arquivo.caminho in conjunto}
    faltando = [arquivo for arquivo in esperados if arquivo.caminho not in conjunto]
    cobertura = _percentual(len(lidos), len(esperados))

    rows = []
    for arquivo in sorted(esperados, key=lambda item: (-item.risco, -_churn(item), item.caminho)):
        rows.append(
            {
                "arquivo": arquivo.caminho,
                "classe": _rotulo_classe(arquivo.classe),
                "risco": arquivo.risco,
                "linhas": _churn(arquivo),
                "status": "revisado" if arquivo.caminho in lidos else "não revisado",
            }
        )
    for arquivo in filtrados:
        rows.append(
            {
                "arquivo": arquivo.caminho,
                "classe": _rotulo_classe(arquivo.classe),
                "risco": arquivo.risco,
                "linhas": _churn(arquivo),
                "status": "filtrado",
            }
        )

    achados_lista: list[dict[str, Any]] = []
    risco_alto = [arquivo for arquivo in faltando if arquivo.risco >= 3]
    if risco_alto:
        achados_lista.append(
            finding(
                "must",
                "risco-alto-sem-revisao",
                f"{len(risco_alto)} arquivo(s) de risco alto fora da revisão",
                ", ".join(arquivo.caminho for arquivo in risco_alto[:4]),
                "Arquivo de risco alto no diff sem sinal de revisão.",
                "É exatamente nesses arquivos que a revisão incompleta custa mais caro.",
                "Abra cada um antes de fechar o PR ou registre por que ficou de fora.",
                "O trecho que mais importa passa sem leitura.",
            )
        )
    if esperados and cobertura < LIMIAR_COBERTURA:
        achados_lista.append(
            finding(
                "must",
                "cobertura-baixa",
                f"Cobertura em {_fmt_pct(cobertura)}",
                f"{len(lidos)} de {len(esperados)} arquivo(s) revisáveis",
                f"Abaixo do piso de {LIMIAR_COBERTURA}% de cobertura.",
                "Cobertura parcial é a falha número um de revisão feita por agente: ele corta caminho sem avisar.",
                "Revise o restante ou diga explicitamente o que ficou de fora e por quê.",
                "A aprovação cobre um PR que ninguém leu inteiro.",
            )
        )
    elif faltando:
        achados_lista.append(
            finding(
                "should",
                "cobertura-parcial",
                f"{len(faltando)} arquivo(s) revisável(is) sem revisão",
                ", ".join(arquivo.caminho for arquivo in faltando[:5]),
                f"Cobertura de {_fmt_pct(cobertura)}, acima do piso de {LIMIAR_COBERTURA}% mas incompleta.",
                "Ficar acima do piso não quer dizer que o que sobrou seja irrelevante.",
                "Feche os arquivos que faltam, do maior risco para o menor.",
                "O arquivo esquecido costuma ser o que quebra.",
            )
        )
    if desconhecidos:
        achados_lista.append(
            finding(
                "should",
                "caminho-desconhecido",
                f"{len(desconhecidos)} caminho(s) revisado(s) fora do diff",
                ", ".join(desconhecidos[:4]),
                "A lista de revisados cita arquivo que não aparece no diff.",
                "Caminho divergente costuma ser renomeação não acompanhada ou lista copiada de outro PR.",
                "Alinhe os caminhos com os do diff.",
                "A cobertura é contada a menos e parece pior do que é.",
            )
        )
    if not esperados:
        achados_lista.append(
            finding(
                "nice",
                "nada-a-revisar",
                "Nenhum arquivo revisável no diff",
                f"{len(filtrados)} arquivo(s) filtrado(s)",
                "Só há gerado, lockfile, documentação, vendor ou binário.",
                "Nada a revisar não é o mesmo que revisão completa.",
                "Confirme que a classificação de filtro está correta para este projeto.",
                "Arquivo de código marcado como gerado passa sem revisão.",
            )
        )
    if declarados and not lidos and esperados:
        achados_lista.append(
            finding(
                "must",
                "revisao-vazia",
                "Nenhum arquivo revisável foi aberto",
                f"{len(declarados)} caminho(s) declarado(s)",
                "A revisão citou arquivos, mas nenhum dos que o diff exige.",
                "Revisão que não toca o diff aprovou por omissão.",
                "Recomece a leitura pelos arquivos desta lista.",
                "O PR é aprovado sem uma única leitura do que mudou.",
            )
        )

    findings, counts, veredito, perguntas = finalize(
        achados_lista,
        modo,
        [
            "Quem declara os arquivos revisados — o agente, a pessoa ou o host?",
            "Qual arquivo de risco alto pode ficar de fora com justificativa registrada?",
            f"{LIMIAR_COBERTURA}% é piso suficiente para este repositório?",
        ],
    )
    metrics = {
        "arquivos": len(arquivos),
        "revisaveis": len(esperados),
        "filtrados": len(filtrados),
        "revisados": len(lidos),
        "faltando": len(faltando),
        "cobertura": cobertura,
        "risco_alto": len(risco_alto),
        "declarados": len(declarados),
        "desconhecidos": len(desconhecidos),
        "conhecidos": len(conhecidos),
    }
    summary = [
        f"{len(lidos)} de {len(esperados)} arquivo(s) revisável(is) conferido(s): cobertura de {_fmt_pct(cobertura)}.",
        f"{len(filtrados)} arquivo(s) fora da revisão por classe (gerado, lockfile, documentação, vendor, binário).",
        f"{len(desconhecidos)} caminho(s) declarado(s) não existem no diff.",
    ]
    limitations = [
        "A cobertura mede arquivos citados, não linhas lidas: abrir o arquivo não garante leitura.",
        "A lista de revisados é declarada por quem revisa; não há verificação de leitura real.",
        "Arquivo filtrado por classe conta como fora da revisão mesmo que alguém o tenha lido.",
        "Renomeação só casa se o nome novo estiver na lista.",
        f"O piso de {LIMIAR_COBERTURA}% é escolha desta camada, não do upstream.",
    ]
    return common(
        analysis="revisao.cobertura",
        mode=modo,
        title="Cobertura da revisão",
        summary=summary,
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows,
        metrics=metrics,
        limitations=limitations,
    )


# --- 7. regras ---------------------------------------------------------------

GUIA_CLASSE = {
    "codigo": [
        "Preserve o estilo do arquivo: nomes, tratamento de erro e estrutura de módulo como estão.",
        "Trate caminho de erro e valor ausente antes de tratar o caminho feliz.",
        "Não introduza dependência nova sem justificar no PR.",
    ],
    "teste": [
        "Cubra o caso de borda que o código novo cria, não só o caminho feliz.",
        "Teste determinístico: sem rede real, sem relógio real, sem ordem implícita.",
        "Ao mudar comportamento, atualize o teste que o protege no mesmo commit.",
    ],
    "config": [
        "Toda chave nova precisa de valor padrão e de entrada no exemplo de configuração.",
        "Segredo não entra em arquivo versionado: use variável de ambiente.",
        "Mudança de configuração precisa de nota de migração para quem já instalou.",
    ],
    "migracao": [
        "Migration precisa de rollback escrito e testado.",
        "Alteração de coluna existente exige janela de compatibilidade com a versão anterior da aplicação.",
        "Dado de produção não é pré-requisito para o teste da migration.",
    ],
    "infra": [
        "Mudança de infraestrutura precisa de plano de reversão e de custo estimado.",
        "Explique o efeito em produção no corpo do PR.",
    ],
    "doc": [
        "Documentação acompanha o código no mesmo PR.",
        "Exemplo de uso precisa ser executável como está escrito.",
    ],
    "segredo": [
        "Nenhum segredo entra no repositório: remova do commit e rotacione a credencial.",
        "Use variável de ambiente e registre a rotação no PR.",
    ],
    "outro": [
        "Explique no PR por que este arquivo muda.",
        "Mantenha a mudança restrita ao assunto do PR.",
    ],
}


def _guia(arquivo: Arquivo) -> list[str]:
    return GUIA_CLASSE.get(arquivo.classe, GUIA_CLASSE["outro"])


def _caracteristica(arquivo: Arquivo) -> str:
    marcas = [_rotulo_classe(arquivo.classe)]
    if arquivo.status != "modificado":
        marcas.append(arquivo.status)
    if arquivo.binario:
        marcas.append("binário")
    if arquivo.adicionadas and not arquivo.removidas:
        marcas.append("só adiciona")
    elif arquivo.removidas and not arquivo.adicionadas:
        marcas.append("só remove")
    if _churn(arquivo) > LIMIAR_ARQUIVO_GRANDE:
        marcas.append("mudança grande")
    if _segredos(arquivo):
        marcas.append("possível segredo")
    return ", ".join(marcas)


def _texto_regra(arquivo: Arquivo, convencoes: str) -> str:
    linhas = [
        f"# {arquivo.caminho}",
        "",
        f"Arquivo de {_rotulo_classe(arquivo.classe).lower()} com {_churn(arquivo)} linha(s) alterada(s) "
        f"({arquivo.adicionadas} adicionada(s), {arquivo.removidas} removida(s)).",
        "",
        "## Estilo",
        "",
        *[f"- {item}" for item in _guia(arquivo)],
    ]
    detalhes = []
    if arquivo.classe == "teste":
        origem = _fonte_do_teste(arquivo.caminho)
        if origem:
            detalhes.append(f"Este teste cobre `{origem}`; leia os dois juntos.")
    if _separar_locale(arquivo.caminho.split("/")[-1].rsplit(".", 1)[0]):
        detalhes.append("Bundle de tradução: confira se a chave existe em todas as locales.")
    if arquivo.classe == "migracao":
        detalhes.append("Migration: o rollback precisa existir e ser reversível sem perda de dado.")
    if _segredos(arquivo):
        detalhes.append("A linha nova parece conter segredo: bloqueie o merge até rotacionar.")
    if detalhes:
        linhas += ["", "## Pontos deste arquivo", "", *[f"- {item}" for item in detalhes]]
    if convencoes.strip():
        linhas += ["", "## Convenções do projeto", "", convencoes.strip()]
    return "\n".join(linhas)


def propor_regras(
    *,
    diff: str,
    convencoes: str = "",
    max_regras: int = 20,
    modo: str = "full",
) -> dict[str, Any]:
    """Monta `rule.json` — regra por caminho, no formato do open-code-review."""
    modo = _modo(modo)
    if max_regras < 1 or max_regras > 200:
        raise RevisaoError("O número de regras precisa estar entre 1 e 200.")
    if len(convencoes) > 20_000:
        raise RevisaoError("As convenções passam de 20.000 caracteres: resuma o que é regra.")
    arquivos = ler_diff(diff)
    candidatos = [arquivo for arquivo in arquivos if arquivo.revisar and arquivo.classe != "binario"]
    candidatos.sort(key=lambda item: (-item.risco, -_churn(item), item.caminho))
    escolhidos = candidatos[:max_regras]
    omitidos = candidatos[max_regras:]

    regras = [
        {
            "path": arquivo.caminho,
            "rule": _texto_regra(arquivo, convencoes),
            "merge_system_rule": True,
        }
        for arquivo in escolhidos
    ]
    documento = json.dumps({"rules": regras}, ensure_ascii=False, indent=2)
    tokens = sum((len(regra["rule"]) + 3) // 4 for regra in regras)

    rows = [
        {
            "caminho": regra["path"],
            "classe": _rotulo_classe(next(arquivo.classe for arquivo in escolhidos if arquivo.caminho == regra["path"])),
            "caracteristica": _caracteristica(next(arquivo for arquivo in escolhidos if arquivo.caminho == regra["path"])),
            "linhas": len(regra["rule"].splitlines()),
            "tokens": (len(regra["rule"]) + 3) // 4,
            "merge": "sim" if regra["merge_system_rule"] else "não",
        }
        for regra in regras
    ]

    longas = [regra for regra in regras if len(regra["rule"]) > 2_000]
    por_guia: dict[str, list[str]] = {}
    for arquivo in escolhidos:
        por_guia.setdefault(_rotulo_classe(arquivo.classe), []).append(arquivo.caminho)
    repetidas = sum(len(caminhos) - 1 for caminhos in por_guia.values() if len(caminhos) >= 3)
    classe_maior = max(por_guia.items(), key=lambda par: len(par[1])) if por_guia else ("", [])

    achados_lista: list[dict[str, Any]] = []
    if not regras:
        achados_lista.append(
            finding(
                "must",
                "sem-regras",
                "Nenhuma regra proposta",
                f"{len(arquivos)} arquivo(s), nenhum revisável",
                "O diff só tem arquivo filtrado, então não há caminho para regra.",
                "`rule.json` sem regra não muda o comportamento do revisor.",
                "Gere as regras a partir de um diff com código.",
                "O revisor segue só com o prompt genérico.",
            )
        )
    if omitidos:
        achados_lista.append(
            finding(
                "should",
                "regras-omitidas",
                f"{len(omitidos)} arquivo(s) ficaram sem regra",
                ", ".join(arquivo.caminho for arquivo in omitidos[:5]),
                f"O teto de {max_regras} regra(s) foi atingido e o resto ficou de fora.",
                "Cada regra entra no prompt; regra demais encarece e dilui a atenção.",
                "Escolha os arquivos de maior risco ou agrupe por pasta.",
                "Arquivo sem regra volta a depender só do prompt genérico.",
            )
        )
    if longas:
        achados_lista.append(
            finding(
                "should",
                "regra-longa",
                f"{len(longas)} regra(s) acima de 2.000 caracteres",
                ", ".join(regra["path"] for regra in longas[:3]),
                "Texto de regra longo entra inteiro no prompt de sistema.",
                "Regra longa consome contexto e costuma repetir o que o prompt já diz.",
                "Corte o que for redundante e mantenha só o que é específico do caminho.",
                "O revisor gasta contexto em prosa e sobra menos para o diff.",
            )
        )
    if repetidas:
        achados_lista.append(
            finding(
                "should",
                "regras-repetidas",
                f"{repetidas} regra(s) repetem o mesmo guia",
                f"{len(classe_maior[1])} caminho(s) de {classe_maior[0].lower()} com o mesmo texto-base",
                "Vários caminhos receberam a mesma orientação, mudando só o cabeçalho.",
                "Cópia por arquivo transforma uma convenção de projeto em N textos para manter.",
                "Escreva a orientação comum em `convencoes` e deixe na regra do caminho só o que é daquele arquivo.",
                "A próxima mudança de convenção exige editar todas as cópias.",
            )
        )
    if not convencoes.strip():
        achados_lista.append(
            finding(
                "should",
                "sem-convencoes",
                "Regras geradas sem as convenções do projeto",
                "campo `convencoes` vazio",
                "O texto sai do que dá para inferir do caminho e da classe do arquivo.",
                "Sem convenção declarada, a regra repete o prompt genérico e não ensina nada específico.",
                "Escreva o que este projeto exige e que não está no código — erro, log, teste, revisão.",
                "O revisor continua opinando em geral em vez de no seu padrão.",
            )
        )
    if tokens > LIMIAR_LOTE_TOKENS:
        achados_lista.append(
            finding(
                "nice",
                "regras-caras",
                f"Regras somam {tokens} token(s) estimados",
                f"acima de {LIMIAR_LOTE_TOKENS}",
                "O conjunto de regras entra no prompt a cada arquivo revisado.",
                "Custo por revisão cresce com regra que poderia ser convenção compartilhada.",
                "Reduza o número de regras ou o tamanho de cada uma.",
                "A conta do provedor sobe sem ganho de precisão.",
            )
        )

    findings, counts, veredito, perguntas = finalize(
        achados_lista,
        modo,
        [
            "Estas regras entram em `.opencodereview/rule.json` ou ficam só como diretriz de PR?",
            "Quem revisa o `rule.json` quando o arquivo correspondente muda?",
            "As convenções do projeto devem virar convenção comum em vez de cópia por caminho?",
        ],
    )
    metrics = {
        "arquivos": len(arquivos),
        "candidatos": len(candidatos),
        "regras": len(regras),
        "omitidos": len(omitidos),
        "linhas": sum(len(regra["rule"].splitlines()) for regra in regras),
        "tokens": tokens,
        "longas": len(longas),
        "repetidas": repetidas,
        "com_convencoes": 1 if convencoes.strip() else 0,
    }
    summary = [
        f"{len(regras)} regra(s) para {len(candidatos)} arquivo(s) revisável(is), {tokens} token(s) estimados no total.",
        f"Cada regra é mesclada ao prompt de sistema (`merge_system_rule: true`) e vale só para o caminho indicado.",
    ]
    limitations = [
        "O texto da regra é gerado a partir do caminho, da classe e do tamanho do diff — não do conteúdo do arquivo.",
        "Uma regra por caminho exato: não há herança por pasta nem por padrão de nome.",
        "O custo em token é estimado por caracteres, não pelo tokenizador do provedor.",
        "O arquivo `.opencodereview/rule.json` não é escrito nem validado contra o schema do host.",
        "Convenção declarada é copiada como está: nada é reescrito nem revisado por outra pessoa.",
    ]
    return common(
        analysis="revisao.regras",
        mode=modo,
        title="Regras por caminho",
        summary=summary,
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows,
        metrics=metrics,
        limitations=limitations,
        extra_sections=["", "## rule.json proposto", "", "```json", documento, "```"],
    )
