"""Continuidade de plano em arquivo: fases, portão, retomada, injeção e livro.

A 0.6.0 já adaptou o `planning-with-files` para criar, listar, retomar e
atualizar planos com escrita real em disco. O que ficou de fora é o outro lado
do padrão, o que o upstream resolveu depois: o plano precisa continuar valendo
quando a sessão é limpa, quando o contexto é compactado e quando o agente
insiste em parar no meio. Aqui isso vira leitura determinística, sem escrever
nada:

- **fases** — lê `### Phase` do `task_plan.md` nos dois formatos de status e
  mede consistência, ordem e critério;
- **portão** — aplica a tabela de decisão do bloqueio de parada (opt-in, fase
  em andamento, teto de bloqueios, progresso no livro);
- **retomada** — cruza plano, progresso e achados para reconstruir o estado
  depois de um `/clear`, com as cinco perguntas de reboot;
- **injeção** — monta o bloco re-injetado por turno com orçamento em bytes,
  truncamento declarado e relógio normalizado;
- **livro** — valida o `ledger-<agente>.jsonl` append-only: evento, tick,
  ordem, lacuna e resumo;
- **médico** — diagnostica o diretório de planos: arquivo faltando, plano
  duplicado, plano órfão e ambiguidade de plano ativo;
- **regras** — publica formatos, limites e a tabela de decisão.

Nada é escrito, nenhum hook roda e nenhum arquivo do host é lido.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from .review import common, finalize, finding

VERSAO = "0.37.6"

MAX_TEXTO = 1_800_000
MAX_LINHAS = 20_000
MAX_ROWS = 200
MAX_FASES = 40
MAX_PLANOS = 200
MODOS = ("lite", "full", "ultra")

# Orçamentos do upstream (inject-plan)
ORCAMENTO_PLANO = 65_536
ORCAMENTO_PROGRESSO = 32_768
TAIL_PROGRESSO = 20
HEAD_PLANO = 120
CABECALHO_ATTEST = 128

# Portão de conclusão (check-complete.sh --gate)
GATE_CAP = 20
GATE_ATIVO = "gate"

# Livro-razão (ledger-append.sh)
EVENTOS = ("progress", "phase_complete", "error", "gate_block", "attest", "note")
RESUMO_MAX = 200
TICK_MAX = 1_000_000
AGENTE_RE = re.compile(r"[^A-Za-z0-9_-]")

# Fases
STATUS = ("pending", "in_progress", "complete")
STATUS_INVALIDO = "?"

SECOES_PLANO = ("Goal", "Next Step", "Current Phase", "Phases", "Key Questions", "Decisions Made", "Errors Encountered", "Notes")
SECOES_PROGRESSO = ("Session", "Test Results", "Error Log", "5-Question Reboot Check")
ARQUIVOS_PLANO = ("task_plan.md", "progress.md", "findings.md")
RE_FASE = re.compile(r"^###\s+Phase\s*(\d+)?\s*[:\-–]?\s*(.*)$", re.I)
RE_STATUS_MD = re.compile(r"\*\*Status:\*\*\s*\[?(pending|in_progress|complete)\]?", re.I)
RE_STATUS_INLINE = re.compile(r"\[(pending|in_progress|complete)\]", re.I)
RE_CAIXA = re.compile(r"^\s*[-*]\s*\[([ xX])\]\s*(.+)$")
RE_ITEM = re.compile(r"^\s*[-*]\s+(.+)$")
RE_CABECALHO = re.compile(r"^(#{1,6})\s+(.+)$")
RE_DATA = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
RE_TS = re.compile(r"T\d{2}:\d{2}:\d{2}(?:\.\d+)?(Z|[+-]\d{2}:\d{2})")
RE_CHECKBOX_MARCA = re.compile(r"\[(pending|in_progress|complete)\]", re.I)


class ContinuidadeError(ValueError):
    """Entrada recusada antes do cálculo."""


def _modo(valor: str) -> str:
    if valor not in MODOS:
        raise ContinuidadeError(f"Modo inválido: {valor}. Use {', '.join(MODOS)}.")
    return valor


def _resumo(texto: str, limite: int) -> str:
    limpo = re.sub(r"\s+", " ", (texto or "").strip())
    return limpo if len(limpo) <= limite else limpo[: limite - 1].rstrip() + "…"


def _questoes() -> list[str]:
    return [
        "Quem escreve `task_plan.md` — o orquestrador ou cada trabalhador?",
        "O portão existe para impedir parada ou para lembrar o humano?",
    ]


def _linhas(texto: str) -> list[str]:
    if len(texto) > MAX_TEXTO:
        raise ContinuidadeError(f"O texto passa de {MAX_TEXTO:,} caracteres.")
    linhas = texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if len(linhas) > MAX_LINHAS:
        raise ContinuidadeError(f"O texto passa de {MAX_LINHAS:,} linhas: divida o plano.")
    return linhas


# --------------------------------------------------------------- markdown

@dataclass
class Secao:
    titulo: str
    nivel: int
    linha: int
    corpo: list[str] = field(default_factory=list)

    @property
    def texto(self) -> str:
        return "\n".join(self.corpo).strip()


def ler_secoes(texto: str) -> list[Secao]:
    """Divide o Markdown em seções de nível 2 (`##`), preservando a ordem."""
    secoes: list[Secao] = []
    atual: Secao | None = None
    for numero, linha in enumerate(_linhas(texto), start=1):
        casamento = RE_CABECALHO.match(linha)
        if casamento and len(casamento.group(1)) == 2:
            nivel = len(casamento.group(1))
            atual = Secao(titulo=casamento.group(2).strip(), nivel=nivel, linha=numero)
            secoes.append(atual)
            continue
        if atual is not None:
            atual.corpo.append(linha)
    return secoes


def _secao(secoes: list[Secao], nome: str) -> Secao | None:
    alvo = nome.lower()
    for secao in secoes:
        if secao.titulo.lower().startswith(alvo):
            return secao
    return None


def _valor_da_secao(secoes: list[Secao], nome: str) -> str:
    secao = _secao(secoes, nome)
    if secao is None:
        return ""
    for linha in secao.corpo:
        limpa = linha.strip()
        if limpa and not limpa.startswith("[") and not limpa.startswith("#"):
            return limpa
    return ""


# ------------------------------------------------------------------ fases

@dataclass
class Fase:
    numero: int
    titulo: str
    linha: int
    status: str
    marcas: int
    formato: str
    criterios: list[tuple[str, bool]]
    itens: int

    @property
    def feitos(self) -> int:
        return sum(1 for _, feito in self.criterios if feito)

    @property
    def total(self) -> int:
        return len(self.criterios)

    @property
    def rotulo(self) -> str:
        return f"Phase {self.numero}: {self.titulo}" if self.titulo else f"Phase {self.numero}"


def _status_da_linha(linha: str) -> list[tuple[str, str]]:
    """Devolve [(status, formato)] das marcas de status presentes na linha."""
    marcas = [(item.group(1).lower(), "primario") for item in RE_STATUS_MD.finditer(linha)]
    marcas += [(item.group(1).lower(), "inline") for item in RE_STATUS_INLINE.finditer(linha)]
    return marcas


def ler_fases(texto: str) -> tuple[list[Fase], list[Secao]]:
    """Lê `### Phase` do `task_plan.md` nos dois formatos de status."""
    secoes = ler_secoes(texto)
    linhas = _linhas(texto)
    fases: list[Fase] = []
    atual: dict[str, Any] | None = None

    def fechar() -> None:
        nonlocal atual
        if atual is None:
            return
        marcas: list[tuple[str, str]] = atual["marcas"]
        status = marcas[0][0] if len({item[0] for item in marcas}) == 1 else STATUS_INVALIDO
        vistos = {item[1] for item in marcas}
        formato = "+".join(nome for nome in ("primario", "inline") if nome in vistos) or "ausente"
        fases.append(
            Fase(
                numero=atual["numero"],
                titulo=atual["titulo"],
                linha=atual["linha"],
                status=status,
                marcas=len(marcas),
                formato=formato,
                criterios=atual["criterios"],
                itens=atual["itens"],
            )
        )
        atual = None

    for numero_linha, linha in enumerate(linhas, start=1):
        casamento = RE_FASE.match(linha)
        if casamento:
            fechar()
            atual = {
                "numero": int(casamento.group(1) or len(fases) + 1),
                "titulo": casamento.group(2).strip(),
                "linha": numero_linha,
                "marcas": [],
                "criterios": [],
                "itens": 0,
            }
            continue
        if atual is None:
            continue
        if RE_CABECALHO.match(linha) and not linha.startswith("####"):
            fechar()
            continue
        atual["marcas"].extend(_status_da_linha(linha))
        caixa = RE_CAIXA.match(linha)
        if caixa:
            atual["criterios"].append((caixa.group(2).strip(), caixa.group(1).lower() == "x"))
        elif RE_ITEM.match(linha):
            atual["itens"] += 1
    fechar()
    return fases, secoes


def _contagem_por_formato(linhas: list[str]) -> dict[str, dict[str, int]]:
    """Repete a regra do upstream: conta cada formato e usa o maior por campo."""
    primario = {status: 0 for status in STATUS}
    inline = {status: 0 for status in STATUS}
    for linha in linhas:
        for casamento in RE_STATUS_MD.finditer(linha):
            primario[casamento.group(1).lower()] += 1
        for casamento in RE_STATUS_INLINE.finditer(linha):
            inline[casamento.group(1).lower()] += 1
    efetivo = {status: max(primario[status], inline[status]) for status in STATUS}
    return {"primario": primario, "inline": inline, "efetivo": efetivo}


# ------------------------------------------------------------------ fases
# (skill 1: continuidade.fases)

def fases(*, plano: str, modo: str = "full") -> dict[str, Any]:
    """Lista as fases do `task_plan.md` com status, critério e consistência."""
    modo = _modo(modo)
    if not (plano or "").strip():
        raise ContinuidadeError("Informe o `task_plan.md`: as fases saem dele, não do nome do arquivo.")
    lista, secoes = ler_fases(plano)
    if not lista:
        raise ContinuidadeError(
            "Nenhum cabeçalho `### Phase` encontrado: sem fase o plano não é verificável e o portão nunca bloqueia."
        )
    if len(lista) > MAX_FASES:
        raise ContinuidadeError(f"O plano passa de {MAX_FASES} fases: divida em planos separados.")

    findings: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for indice, fase in enumerate(lista):
        if fase.marcas > 1:
            findings.append(
                finding(
                    "must", "status", "Fase com mais de uma marca de status",
                    f"Phase {fase.numero} (linha {fase.linha})",
                    f"A fase tem {fase.marcas} marcas de status ({fase.formato}).",
                    "O contador do portão soma marcas, não fases: uma fase com duas marcas adianta a conclusão do plano inteiro.",
                    "Deixe exatamente uma marca por fase, no formato `**Status:** pending|in_progress|complete`.",
                    "O plano parece mais adiantado do que está e o portão libera a parada.",
                )
            )
        if fase.marcas == 0:
            findings.append(
                finding(
                    "must", "status", "Fase sem status",
                    f"Phase {fase.numero} (linha {fase.linha})",
                    "O cabeçalho existe e nenhuma linha da fase declara status.",
                    "Fase sem status não entra em nenhuma contagem: nem pendente, nem em andamento, nem concluída.",
                    "Acrescente `- **Status:** pending` (ou `in_progress` / `complete`) ao fim da fase.",
                    "A fase desaparece do portão e a conclusão do plano é superestimada.",
                )
            )
        if fase.status in STATUS and fase.total == 0:
            findings.append(
                finding(
                    "should", "criterio", "Fase sem critério verificável",
                    f"Phase {fase.numero} (linha {fase.linha})",
                    f"A fase tem {fase.itens} item(ns) e nenhum checkbox.",
                    "Conclusão sem critério é opinião: nada distingue fase feita de fase achada pronta.",
                    "Escreva cada critério como `- [ ] ...` e marque `- [x]` só com evidência.",
                    "A fase vira `complete` sem prova e o plano perde a função de trilha.",
                )
            )
        elif fase.status == "complete" and fase.total and fase.feitos < fase.total:
            findings.append(
                finding(
                    "should", "criterio", "Fase concluída com critério aberto",
                    f"Phase {fase.numero} (linha {fase.linha})",
                    f"{fase.total - fase.feitos} de {fase.total} critério(s) continuam sem marca.",
                    "O status diz `complete` e a lista diz o contrário; quem retomar não sabe em qual acreditar.",
                    "Marque os critérios com evidência ou volte o status para `in_progress`.",
                    "A próxima sessão assume entregue o que não foi.",
                )
            )
        if fase.status == "in_progress" and fase.feitos == fase.total and fase.total:
            findings.append(
                finding(
                    "nice", "status", "Fase em andamento com todos os critérios marcados",
                    f"Phase {fase.numero} (linha {fase.linha})",
                    "Todos os critérios estão marcados e o status não é `complete`.",
                    "O trabalho terminou e o plano não registrou: o portão continua bloqueando a parada.",
                    "Atualize o status para `complete` e registre a evidência em `progress.md`.",
                    "O agente fica preso em uma fase que já acabou.",
                )
            )
        if indice and fase.numero <= lista[indice - 1].numero:
            findings.append(
                finding(
                    "should", "ordem", "Fase fora de ordem",
                    f"Phase {fase.numero} (linha {fase.linha})",
                    f"O número {fase.numero} vem depois de {lista[indice - 1].numero}.",
                    "A fase ativa é lida de cima para baixo; número repetido ou fora de ordem escolhe a fase errada.",
                    "Numere as fases em ordem crescente, sem repetir.",
                    "A retomada aponta para uma fase que não é a que está sendo trabalhada.",
                )
            )
        if indice and lista[indice - 1].status != "complete" and fase.status == "complete":
            findings.append(
                finding(
                    "should", "ordem", "Fase concluída antes da anterior",
                    f"Phase {fase.numero} (linha {fase.linha})",
                    f"A fase anterior está `{lista[indice - 1].status}`.",
                    "Concluir fora de ordem costuma ser fase marcada por engano, não trabalho adiantado.",
                    "Ou a anterior terminou (e o status está atrasado), ou esta não terminou.",
                    "O plano conta uma história que não aconteceu.",
                )
            )
        rows.append(
            {
                "numero": fase.numero,
                "titulo": fase.titulo or "—",
                "status": fase.status,
                "marcas": fase.marcas,
                "formato": fase.formato,
                "criterios": fase.total,
                "feitos": fase.feitos,
                "linha": fase.linha,
            }
        )

    completas = sum(1 for fase in lista if fase.status == "complete")
    andamento = [fase for fase in lista if fase.status == "in_progress"]
    invalidas = sum(1 for fase in lista if fase.status == STATUS_INVALIDO)
    if not andamento and completas < len(lista):
        findings.append(
            finding(
                "should", "status", "Nenhuma fase em andamento",
                "task_plan.md",
                f"{len(lista) - completas} fase(s) pendente(s) e nenhuma em `in_progress`.",
                "Sem fase ativa o agente não sabe onde está, e o portão do upstream só bloqueia quando existe uma.",
                "Marque `in_progress` a fase que está sendo trabalhada.",
                "A retomada volta para o início em vez de continuar de onde parou.",
            )
        )
    objetivo = _valor_da_secao(secoes, "Goal")
    proximo = _valor_da_secao(secoes, "Next Step")
    for nome, valor, grupo in (("Goal", objetivo, "must"), ("Next Step", proximo, "should")):
        if not valor:
            findings.append(
                finding(
                    grupo, "secao", f"`## {nome}` ausente ou vazio",
                    "task_plan.md",
                    f"A seção `## {nome}` não traz conteúdo utilizável.",
                    "A injeção por turno depende dessas duas seções para reconstruir o rumo sem reler o plano inteiro.",
                    f"Preencha `## {nome}` com uma frase.",
                    "O bloco reinjetado chega sem rumo e o agente relê o arquivo inteiro.",
                )
            )

    achados, counts, veredito, perguntas = finalize(
        findings, modo, ["Quem move o status de uma fase — o trabalhador ou o orquestrador?"]
    )
    formatos = _contagem_por_formato(_linhas(plano))
    metrics = {
        "fases": len(lista),
        "completas": completas,
        "emAndamento": len(andamento),
        "pendentes": sum(1 for fase in lista if fase.status == "pending"),
        "invalidas": invalidas,
        "criterios": sum(fase.total for fase in lista),
        "feitos": sum(fase.feitos for fase in lista),
        "ativa": andamento[0].rotulo if andamento else "",
        "porFormato": formatos["efetivo"],
    }
    summary = [
        f"{len(lista)} fase(s): {completas} concluída(s), {len(andamento)} em andamento, "
        f"{metrics['pendentes']} pendente(s) e {invalidas} sem status legível.",
        f"{metrics['feitos']} de {metrics['criterios']} critério(s) marcados.",
        "A leitura aceita `**Status:**` e `[status]`; a contagem do portão usa o maior valor por campo, como no upstream.",
    ]
    extra = [
        "",
        "## Fases",
        "",
        "| # | Título | Status | Marcas | Critérios | Feitos | Linha |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    extra += [
        f"| {row['numero']} | {row['titulo']} | {row['status']} | {row['marcas']} | {row['criterios']} | {row['feitos']} | {row['linha']} |"
        for row in rows
    ]
    resultado = common(
        analysis="fases",
        mode=modo,
        title="Fases do plano",
        summary=summary,
        findings=achados,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows[:MAX_ROWS],
        metrics=metrics,
        limitations=[
            "Não edita o plano: aponta a inconsistência e o texto que a resolve.",
            "Não interpreta prosa: só cabeçalho `### Phase`, marca de status e checkbox.",
            "Não sabe se o critério foi realmente cumprido — só se está marcado.",
            "Não lê o histórico do Git nem a data de modificação do arquivo.",
        ],
        extra_sections=extra,
    )
    resultado["fases"] = rows[:MAX_ROWS]
    return resultado


# ------------------------------------------------------------------ portão

def _guardas(*, ligado: bool, em_andamento: int, stop_ativo: bool, bloqueios: int, cap: int, linhas: int, anterior: int) -> list[dict[str, Any]]:
    """Tabela de decisão do upstream, na ordem em que os guardas são avaliados."""
    guardas = [
        {
            "ordem": 1,
            "guarda": "modo `gate` declarado",
            "passou": ligado,
            "detalhe": "o plano optou por bloquear" if ligado else "sem `.mode` com `gate`: o portão é consultivo",
        },
        {
            "ordem": 2,
            "guarda": "existe fase em andamento",
            "passou": em_andamento > 0,
            "detalhe": f"{em_andamento} fase(s) em `in_progress`" if em_andamento else "nenhuma fase em andamento: nada a bloquear",
        },
        {
            "ordem": 3,
            "guarda": "parada forçada desligada",
            "passou": not stop_ativo,
            "detalhe": "`stop_hook_active` verdadeiro permite a parada" if stop_ativo else "a parada não veio de bloqueio anterior",
        },
        {
            "ordem": 4,
            "guarda": "abaixo do teto de bloqueios",
            "passou": bloqueios < cap,
            "detalhe": f"{bloqueios} de {cap} bloqueio(s)",
        },
        {
            "ordem": 5,
            "guarda": "o livro avançou desde o último bloqueio",
            "passou": not (bloqueios > 0 and linhas == anterior),
            "detalhe": (
                f"{linhas} linha(s) no livro, {anterior} no último bloqueio"
                if bloqueios > 0
                else "sem bloqueio anterior: a regra de estagnação não se aplica"
            ),
        },
    ]
    return guardas


def portao(
    *,
    plano: str,
    ligado: bool = False,
    bloqueios: int = 0,
    cap: int = GATE_CAP,
    ledger: str = "",
    linhas_anteriores: int = 0,
    stop_ativo: bool = False,
    modo: str = "full",
) -> dict[str, Any]:
    """Aplica a tabela de decisão do portão de conclusão sobre o plano e o livro."""
    modo = _modo(modo)
    if not (plano or "").strip():
        raise ContinuidadeError("Informe o `task_plan.md`: o portão decide sobre fases declaradas.")
    if cap < 1 or cap > 1_000:
        raise ContinuidadeError("O teto de bloqueios precisa ficar entre 1 e 1.000.")
    if bloqueios < 0:
        raise ContinuidadeError("O contador de bloqueios não pode ser negativo.")
    if linhas_anteriores < 0:
        raise ContinuidadeError("A contagem anterior do livro não pode ser negativa.")

    lista, _ = ler_fases(plano)
    if not lista:
        raise ContinuidadeError(
            "Sem cabeçalho `### Phase` o plano não tem estado de conclusão: nada é bloqueado e o parecer diz isso."
        )
    linhas_ledger = len([linha for linha in _linhas(ledger) if linha.strip()]) if ledger.strip() else 0
    andamento = [fase for fase in lista if fase.status == "in_progress"]
    completas = sum(1 for fase in lista if fase.status == "complete")
    guardas = _guardas(
        ligado=ligado,
        em_andamento=len(andamento),
        stop_ativo=stop_ativo,
        bloqueios=bloqueios,
        cap=cap,
        linhas=linhas_ledger,
        anterior=linhas_anteriores,
    )
    deve_bloquear = all(guarda["passou"] for guarda in guardas)
    ordem_que_parou = next((guarda["ordem"] for guarda in guardas if not guarda["passou"]), 0)
    motivo_decisao = "" if deve_bloquear else {
        1: "portão desligado: o plano não declarou `.mode` com `gate`",
        2: "nenhuma fase em `in_progress`: plano sem trabalho ativo não bloqueia parada",
        3: "a parada veio de um bloqueio anterior (`stop_hook_active`)",
        4: f"teto de bloqueios atingido ({bloqueios}/{cap})",
        5: "sem progresso no livro desde o último bloqueio: bloquear de novo só repetiria a mensagem",
    }.get(ordem_que_parou, "")
    if deve_bloquear:
        motivo_decisao = "fase ativa, portão armado e livro avançando: a parada seria bloqueada"

    findings: list[dict[str, Any]] = []
    if deve_bloquear:
        fase = andamento[0]
        findings.append(
            finding(
                "must", "portao", "Plano bloqueado no meio de uma fase",
                fase.rotulo,
                f"O portão decidiu `block` com {completas} de {len(lista)} fase(s) concluída(s).",
                "A parada aconteceria com a fase ativa pela metade e a próxima ação já escrita: o trabalho é retomável, mas não terminado.",
                "Termine a fase, atualize o status e registre a evidência em `progress.md`; ou acrescente fase nova ao plano.",
                "O agente para no meio e a próxima sessão encontra o plano dizendo que está tudo bem.",
            )
        )
    else:
        if not ligado:
            findings.append(
                finding(
                    "should", "portao", "Portão desligado em plano incompleto",
                    "task_plan.md",
                    f"{len(lista) - completas} fase(s) aberta(s) e o bloqueio não está armado.",
                    "O modo consultivo informa a incompletude e deixa parar — a decisão é da pessoa, não do hook.",
                    "Se a parada precisa ser impedida, declare `.mode` com `gate` e aceite o teto de bloqueios.",
                    "O agente para no meio do plano sem que ninguém seja avisado.",
                )
            )
        if ordem_que_parou == 4:
            findings.append(
                finding(
                    "should", "portao", "Teto de bloqueios atingido",
                    f"{bloqueios}/{cap}",
                    "O limite existe para o agente não ficar preso em um plano que não avança.",
                    "Um plano que chega ao teto está bloqueado por algo que o próprio plano não resolve.",
                    "Reveja a fase: divida em passos menores, marque o que já foi entregue ou encerre com registro.",
                    "O laço continua sem que o plano mude.",
                )
            )
        if ordem_que_parou == 5:
            findings.append(
                finding(
                    "nice", "portao", "Estagnação detectada",
                    "livro",
                    f"O livro tem {linhas_ledger} linha(s), a mesma contagem do último bloqueio.",
                    "Bloquear de novo sem entrada nova só repete a mensagem; o upstream libera a parada nesse caso.",
                    "Registre o que foi tentado, mesmo que seja um beco sem saída.",
                    "O portão vira ruído e o agente aprende a ignorá-lo.",
                )
            )
        if stop_ativo:
            findings.append(
                finding(
                    "nice", "portao", "Bloqueio desligado pela própria parada",
                    "stop_hook_active",
                    "A parada já veio de um bloqueio anterior; a guarda permite sair para não gerar recursão.",
                    "Sem essa guarda, um bloqueio que gera parada que gera bloqueio pode entrar em laço.",
                    "Corrija a causa antes de rearmar o portão.",
                    "O agente fica preso em um ciclo de bloqueio e parada.",
                )
            )

    achados, counts, veredito, perguntas = finalize(
        findings,
        modo,
        ["Quem rearma o portão depois de um bloqueio — o humano ou a próxima sessão?"],
    )
    rows = [
        {
            "ordem": guarda["ordem"],
            "guarda": guarda["guarda"],
            "resultado": "passa" if guarda["passou"] else "para",
            "detalhe": guarda["detalhe"],
        }
        for guarda in guardas
    ]
    metrics = {
        "decisao": "block" if deve_bloquear else "allow",
        "bloqueios": bloqueios,
        "cap": cap,
        "restantes": max(cap - bloqueios, 0),
        "fases": len(lista),
        "completas": completas,
        "emAndamento": len(andamento),
        "faseAtiva": andamento[0].rotulo if andamento else "",
        "linhasLedger": linhas_ledger,
        "guardaQueParou": ordem_que_parou,
    }
    summary = [
        f"Decisão: `{'block' if deve_bloquear else 'allow'}` ({motivo_decisao}).",
        f"{completas} de {len(lista)} fase(s) concluída(s); fase ativa: {metrics['faseAtiva'] or 'nenhuma'}.",
        f"Bloqueios {bloqueios} de {cap}; livro com {linhas_ledger} linha(s) e {linhas_anteriores} no último bloqueio.",
    ]
    extra = [
        "",
        "## Guardas",
        "",
        "| Ordem | Guarda | Resultado | Detalhe |",
        "| --- | --- | --- | --- |",
    ]
    extra += [f"| {row['ordem']} | {row['guarda']} | {row['resultado']} | {row['detalhe']} |" for row in rows]
    resultado = common(
        analysis="portao",
        mode=modo,
        title="Portão de conclusão",
        summary=summary,
        findings=achados,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows,
        metrics=metrics,
        limitations=[
            "Não para nenhum agente: devolve a decisão que o hook tomaria, sem instalar hook nem bloquear sessão.",
            "Não escreve o contador de bloqueios nem o marcador do livro: as duas contagens vêm na chamada.",
            "Não distingue plano autônomo de plano manual além do que o próprio arquivo declara.",
            "Não avalia se a fase concluída foi realmente entregue.",
        ],
        extra_sections=extra,
    )
    resultado["decisao"] = "block" if deve_bloquear else "allow"
    resultado["motivo"] = motivo_decisao
    return resultado


# ---------------------------------------------------------------- retomada

PERGUNTAS_REBOOT = (
    ("Onde estou?", ("fase", "ativa")),
    ("Para onde vou?", ("fases", "pendentes")),
    ("Qual é o objetivo?", ("goal",)),
    ("O que aprendi?", ("achados",)),
    ("O que já fiz?", ("completas",)),
)


def _datas(texto: str) -> list[str]:
    return [casamento.group(0) for casamento in RE_DATA.finditer(texto)]


def _arquivos_citados(texto: str) -> list[str]:
    return sorted(set(re.findall(r"`([\w./-]+\.[A-Za-z0-9]{1,8})`", texto)))


def retomada(
    *,
    plano: str,
    progresso: str,
    achados: str = "",
    modo: str = "full",
) -> dict[str, Any]:
    """Reconstrói o estado depois de `/clear` cruzando plano, progresso e achados."""
    modo = _modo(modo)
    if not (plano or "").strip():
        raise ContinuidadeError("Informe o `task_plan.md`: a retomada começa pelo rumo declarado.")
    if not (progresso or "").strip():
        raise ContinuidadeError("Informe o `progress.md`: sem registro não há o que retomar, só o que recomeçar.")

    fases_plano, secoes_plano = ler_fases(plano)
    if not fases_plano:
        raise ContinuidadeError("O plano não tem `### Phase`: não há fase para retomar nem status para comparar.")
    fases_progresso, secoes_progresso = ler_fases(progresso)

    findings: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    por_numero = {fase.numero: fase for fase in fases_progresso}
    divergentes = 0
    for fase in fases_plano:
        registrada = por_numero.get(fase.numero)
        status_progresso = registrada.status if registrada else "ausente"
        diverge = bool(registrada) and registrada.status in STATUS and fase.status in STATUS and registrada.status != fase.status
        if diverge:
            divergentes += 1
            findings.append(
                finding(
                    "must", "divergencia", "Status do plano diverge do progresso",
                    f"Phase {fase.numero}",
                    f"`task_plan.md` diz `{fase.status}` e `progress.md` diz `{registrada.status}`.",
                    "São duas fontes de verdade para o mesmo fato; quem retoma escolhe uma e erra na metade das vezes.",
                    "Alinhe os dois arquivos: o plano manda, o progresso registra.",
                    "A próxima sessão recomeça fase concluída ou pula fase pendente.",
                )
            )
        if not registrada:
            findings.append(
                finding(
                    "should", "progresso", "Fase do plano sem registro no progresso",
                    f"Phase {fase.numero}",
                    "A fase existe no plano e não aparece no `progress.md`.",
                    "Sem registro não há o que foi feito, nem quando, nem em que arquivo — só a intenção.",
                    "Registre a fase no progresso com status, data e o que mudou.",
                    "A retomada sabe o que falta e não sabe o que já foi tentado.",
                )
            )
        rows.append(
            {
                "fase": fase.numero,
                "titulo": fase.titulo or "—",
                "plano": fase.status,
                "progresso": status_progresso,
                "situacao": "diverge" if diverge else ("registrada" if registrada else "sem registro"),
            }
        )

    for fase in fases_progresso:
        if fase.numero not in {item.numero for item in fases_plano}:
            findings.append(
                finding(
                    "should", "progresso", "Progresso cita fase que o plano não tem",
                    f"Phase {fase.numero}",
                    "O registro descreve trabalho de uma fase que o plano não declara.",
                    "Plano e progresso contam histórias diferentes do mesmo trabalho.",
                    "Acrescente a fase ao plano ou corrija o número no progresso.",
                    "A conclusão do plano fica abaixo do trabalho realmente feito.",
                )
            )

    datas = _datas(progresso)
    if not datas:
        findings.append(
            finding(
                "must", "data", "Progresso sem data",
                "progress.md",
                "Nenhuma data `AAAA-MM-DD` no registro.",
                "Sem data não se sabe se o registro é desta sessão ou de três semanas atrás.",
                "Comece o progresso com `## Session: AAAA-MM-DD`.",
                "A retomada mistura trabalho antigo com trabalho atual.",
            )
        )
    if "[DATE]" in progresso or "[timestamp]" in progresso.lower():
        findings.append(
            finding(
                "should", "data", "Placeholder de data não substituído",
                "progress.md",
                "O modelo trouxe `[DATE]` ou `[timestamp]` e ninguém trocou pelo valor real.",
                "Placeholder é a assinatura de um registro preenchido pela metade.",
                "Substitua pelo dia e pela hora em que o trabalho aconteceu.",
                "O arquivo parece completo e não dá para ordenar as sessões.",
            )
        )

    for secao in secoes_progresso:
        if secao.titulo.lower().startswith("test results"):
            linhas_tabela = [linha for linha in secao.corpo if linha.strip().startswith("|")]
            vazias = [linha for linha in linhas_tabela if re.fullmatch(r"\|[\s|:-]*\|", linha.strip())]
            if len(linhas_tabela) <= 2 or len(linhas_tabela) == len(vazias):
                findings.append(
                    finding(
                        "nice", "teste", "Tabela de teste sem resultado",
                        "progress.md › Test Results",
                        "A seção existe e a tabela está vazia.",
                        "Seção vazia passa a impressão de verificação feita.",
                        "Registre comando, esperado, obtido e status — ou remova a seção.",
                        "Quem retoma assume que houve teste onde não houve.",
                    )
                )

    secoes_achados = ler_secoes(achados) if achados.strip() else []
    if achados.strip() and not _secao(secoes_achados, "Requirements"):
        findings.append(
            finding(
                "should", "achados", "`findings.md` sem requisitos",
                "findings.md",
                "O arquivo de achados não tem a seção `## Requirements`.",
                "Requisito é o que a entrega precisa cumprir; sem ele a retomada não sabe o que conta como pronto.",
                "Registre o pedido como requisito verificável durante a descoberta.",
                "A fase de entrega julga sem régua.",
            )
        )

    objetivo = _valor_da_secao(secoes_plano, "Goal")
    proximo = _valor_da_secao(secoes_plano, "Next Step")
    ativa = next((fase for fase in fases_plano if fase.status == "in_progress"), None)
    completas = sum(1 for fase in fases_plano if fase.status == "complete")
    respostas = {
        "Onde estou?": ativa.rotulo if ativa else "sem fase em andamento",
        "Para onde vou?": ", ".join(f"Phase {f.numero}" for f in fases_plano if f.status == "pending") or "nenhuma fase pendente",
        "Qual é o objetivo?": objetivo or "sem `## Goal`",
        "O que aprendi?": _resumo(_secao(secoes_achados, "Research Findings").texto, 120) if _secao(secoes_achados, "Research Findings") else "sem `findings.md`",
        "O que já fiz?": f"{completas} de {len(fases_plano)} fase(s) concluída(s)",
    }
    faltando = [pergunta for pergunta, resposta in respostas.items() if resposta.startswith("sem ")]
    if faltando:
        findings.append(
            finding(
                "should", "reboot", "Pergunta de reboot sem resposta",
                ", ".join(faltando),
                f"{len(faltando)} das cinco perguntas não têm resposta nos arquivos.",
                "As cinco perguntas existem para reconstruir o rumo sem o histórico da conversa; sem resposta, a retomada adivinha.",
                "Preencha a seção que falta — objetivo, achado ou fase ativa.",
                "A nova sessão começa com menos contexto do que a anterior tinha.",
            )
        )

    achados_finais, counts, veredito, perguntas = finalize(
        findings, modo, ["Quem corrige a divergência: o orquestrador antes de parar ou quem retoma?"]
    )
    metrics = {
        "fases": len(fases_plano),
        "registradas": len(fases_progresso),
        "divergentes": divergentes,
        "completas": completas,
        "ativa": ativa.rotulo if ativa else "",
        "ultimaData": max(datas) if datas else "",
        "datas": len(datas),
        "perguntas": len(PERGUNTAS_REBOOT) - len(faltando),
        "arquivos": len(_arquivos_citados(progresso)),
    }
    summary = [
        f"{len(fases_plano)} fase(s) no plano e {len(fases_progresso)} no progresso; {divergentes} divergência(s) de status.",
        f"Última data registrada: {metrics['ultimaData'] or 'nenhuma'}; {metrics['perguntas']} de 5 pergunta(s) de reboot respondida(s).",
        f"Fase ativa: {metrics['ativa'] or 'nenhuma'}. Próximo passo: {_resumo(proximo, 120) or 'não declarado'}.",
    ]
    extra = [
        "",
        "## Plano × progresso",
        "",
        "| Fase | Título | Plano | Progresso | Situação |",
        "| --- | --- | --- | --- | --- |",
    ]
    extra += [
        f"| {row['fase']} | {row['titulo']} | {row['plano']} | {row['progresso']} | {row['situacao']} |"
        for row in rows
    ]
    extra += ["", "## Cinco perguntas de reboot", "", "| Pergunta | Resposta |", "| --- | --- |"]
    extra += [f"| {pergunta} | {_resumo(resposta, 140)} |" for pergunta, resposta in respostas.items()]
    resultado = common(
        analysis="retomada",
        mode=modo,
        title="Retomada depois de limpar a sessão",
        summary=summary,
        findings=achados_finais,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows[:MAX_ROWS],
        metrics=metrics,
        limitations=[
            "Não lê histórico de conversa nem transcrição de sessão: o estado vem só dos três arquivos colados.",
            "Não escreve `progress.md` nem corrige divergência.",
            "Não sabe se o trabalho registrado foi realmente feito: lê o que o arquivo afirma.",
            "A data é lida como texto: fuso e ordem de fuso não são interpretados.",
        ],
        extra_sections=extra,
    )
    resultado["respostas"] = respostas
    return resultado


# ----------------------------------------------------------------- injeção

def _normalizar_relogio(texto: str) -> tuple[str, int]:
    """Zera a hora de todo timestamp, preservando o fuso — o bloco fica estável."""
    trocas = 0

    def zerar(casamento: re.Match[str]) -> str:
        nonlocal trocas
        trocas += 1
        return "T00:00:00" + casamento.group(1)

    return RE_TS.sub(zerar, texto), trocas


def _truncar_em_linha(texto: str, limite: int) -> tuple[str, bool]:
    """Corta em bytes abaixo do limite, na última linha inteira que couber."""
    dados = texto.encode("utf-8")
    if len(dados) <= limite:
        return texto, False
    corte = dados[:limite].decode("utf-8", errors="ignore")
    ultimo = corte.rfind("\n")
    if ultimo > limite // 2:
        corte = corte[:ultimo]
    return corte.rstrip("\n"), True


def _bloco_ledger(texto: str, fases: list[Fase]) -> str:
    """Resumo de forma fixa: sem hora, sem texto livre de disco."""
    entradas = [linha for linha in texto.split("\n") if linha.strip()]
    completas = sum(1 for fase in fases if fase.status == "complete")
    ativa = next((fase for fase in fases if fase.status == "in_progress"), None)
    por_agente: dict[str, str] = {}
    for linha in entradas:
        try:
            dado = json.loads(linha)
        except json.JSONDecodeError:
            continue
        agente = str(dado.get("agent") or "main")
        por_agente[agente] = str(dado.get("event") or "?")
    linhas = [
        "=== RUN LEDGER ===",
        f"entries: {len(entradas)}",
        f"phases: {completas}/{len(fases)} complete",
        f"in_progress: {ativa.rotulo if ativa else 'none'}",
    ]
    linhas += [f"agent {agente}: {evento}" for agente, evento in sorted(por_agente.items())]
    linhas.append("==================")
    return "\n".join(linhas)


def injecao(
    *,
    plano: str,
    progresso: str = "",
    ledger: str = "",
    orcamento: int = ORCAMENTO_PLANO,
    linhas: int = HEAD_PLANO,
    modo: str = "full",
) -> dict[str, Any]:
    """Monta o bloco que o hook reinjetaria no contexto, com orçamento e corte declarados."""
    modo = _modo(modo)
    if not (plano or "").strip():
        raise ContinuidadeError("Informe o `task_plan.md`: é ele que a injeção carrega.")
    if orcamento < 512 or orcamento > MAX_TEXTO:
        raise ContinuidadeError(f"O orçamento precisa ficar entre 512 e {MAX_TEXTO:,} caracteres.")
    if linhas < 5 or linhas > 2_000:
        raise ContinuidadeError("A visão por cabeçalho precisa ficar entre 5 e 2.000 linhas.")

    fases, secoes = ler_fases(plano)
    objetivo = _valor_da_secao(secoes, "Goal")
    proximo = _valor_da_secao(secoes, "Next Step")
    corrente = _valor_da_secao(secoes, "Current Phase")
    ativa = next((fase for fase in fases if fase.status == "in_progress"), None)
    decisoes = _secao(secoes, "Decisions Made")

    partes: list[str] = []
    if objetivo:
        partes += ["## Goal", "", objetivo, ""]
    if proximo:
        partes += ["## Next Step", "", proximo, ""]
    if corrente:
        partes += ["## Current Phase", "", corrente, ""]
    if ativa:
        partes += [f"### Phase {ativa.numero}: {ativa.titulo}", ""]
        partes += [f"- {'[x]' if feito else '[ ]'} {criterio}" for criterio, feito in ativa.criterios]
        partes += ["", f"- **Status:** {ativa.status}", ""]
    if decisoes is not None and decisoes.texto:
        partes += ["## Decisions Made", "", decisoes.texto, ""]

    inteligente = bool(partes)
    if inteligente:
        visao = "\n".join(partes).rstrip() + "\n"
        fonte = "secoes"
    else:
        todas = _linhas(plano)
        visao = "\n".join(todas[:linhas]).rstrip() + "\n"
        fonte = "cabecalho"

    visao, relogio = _normalizar_relogio(visao)
    visao, truncada = _truncar_em_linha(visao, orcamento)
    bytes_visao = len(visao.encode("utf-8"))

    if ledger.strip():
        bloco_progresso = _bloco_ledger(ledger, fases)
        fonte_progresso = "livro"
    elif progresso.strip():
        cauda = [linha for linha in _linhas(progresso) if linha is not None][-TAIL_PROGRESSO:]
        bloco_progresso, _ = _normalizar_relogio("\n".join(cauda))
        bloco_progresso, _ = _truncar_em_linha(bloco_progresso, ORCAMENTO_PROGRESSO)
        fonte_progresso = "cauda"
    else:
        bloco_progresso = ""
        fonte_progresso = "nenhuma"

    hash_plano = hashlib.sha256(plano.encode("utf-8")).hexdigest()[:16]
    findings: list[dict[str, Any]] = []
    if not proximo:
        findings.append(
            finding(
                "must", "secao", "Bloco injetado sem próximo passo",
                "task_plan.md › Next Step",
                "A seção `## Next Step` está ausente ou vazia.",
                "A injeção existe para dizer uma coisa por turno: qual é a próxima ação. Sem ela o bloco chega sem instrução.",
                "Escreva `## Next Step` com uma única ação e atualize quando a fase mudar.",
                "O agente relê o plano inteiro a cada turno e o custo sobe sem ganho.",
            )
        )
    if not objetivo:
        findings.append(
            finding(
                "must", "secao", "Bloco injetado sem objetivo",
                "task_plan.md › Goal",
                "A seção `## Goal` está ausente ou vazia.",
                "Sem objetivo o agente otimiza o passo e perde o destino.",
                "Acrescente `## Goal` com uma frase.",
                "Decisões locais passam a contrariar o resultado combinado.",
            )
        )
    if truncada:
        findings.append(
            finding(
                "should", "orcamento", "Visão do plano truncada no orçamento",
                f"{orcamento:,} caracteres",
                f"A visão tinha mais que o orçamento e foi cortada em {bytes_visao:,} bytes.",
                "O corte tira justamente a cauda: decisão e critério das últimas fases.",
                "Encurte `## Goal` e `## Next Step`, ou aumente o orçamento sabendo o custo por turno.",
                "O turno seguinte decide sem a parte cortada.",
            )
        )
    if len(objetivo) > 500:
        findings.append(
            finding(
                "should", "tamanho", "Objetivo longo demais para reinjetar",
                "task_plan.md › Goal",
                f"O objetivo tem {len(objetivo)} caracteres.",
                "O objetivo é reinjetado em todo turno: cada linha dele é paga a cada mensagem.",
                "Deixe uma frase no `## Goal` e mova o detalhe para `findings.md`.",
                "O custo por turno sobe sem melhorar a decisão.",
            )
        )
    if relogio:
        findings.append(
            finding(
                "nice", "relogio", "Relógio normalizado para manter o bloco estável",
                "task_plan.md",
                f"{relogio} timestamp(s) tiveram a hora zerada.",
                "Hora que muda a cada turno invalida o cache do prefixo e encarece a conversa.",
                "Deixe a hora exata no arquivo e injete a data sem hora.",
                "Cada turno paga o prefixo inteiro de novo.",
            )
        )
    if fonte_progresso == "cauda":
        findings.append(
            finding(
                "nice", "progresso", "Progresso injetado pela cauda do arquivo",
                "progress.md",
                f"As últimas {TAIL_PROGRESSO} linha(s) entram no bloco.",
                "Texto livre do progresso varia a cada edição; o resumo do livro é de forma fixa.",
                "Mantenha o `ledger-<agente>.jsonl` e injete o resumo dele.",
                "O bloco muda sem que o estado do plano mude.",
            )
        )
    if not fases:
        findings.append(
            finding(
                "must", "fase", "Plano sem `### Phase`",
                "task_plan.md",
                "Nenhum cabeçalho de fase foi encontrado.",
                "Sem fase não há contagem de conclusão e o portão nunca bloqueia.",
                "Estruture o plano em fases numeradas com um status por fase.",
                "O plano vira prosa e deixa de ser verificável.",
            )
        )

    achados, counts, veredito, perguntas = finalize(
        findings, modo, ["Quanto contexto por turno vale manter o plano à mão?"]
    )
    bloco = visao + ("\n" + bloco_progresso if bloco_progresso else "")
    rows = [
        {"fonte": "task_plan.md", "modo": fonte, "bytes": bytes_visao, "teto": orcamento},
        {"fonte": "progress.md" if fonte_progresso == "cauda" else "ledger", "modo": fonte_progresso, "bytes": len(bloco_progresso.encode()), "teto": ORCAMENTO_PROGRESSO},
    ]
    metrics = {
        "bytesPlano": len(plano.encode("utf-8")),
        "bytesVisao": bytes_visao,
        "bytesProgresso": len(bloco_progresso.encode()),
        "bytesBloco": len(bloco.encode("utf-8")),
        "orcamento": orcamento,
        "truncada": truncada,
        "fonte": fonte,
        "fonteProgresso": fonte_progresso,
        "fases": len(fases),
        "hash": hash_plano,
        "economia": round(100 * (1 - bytes_visao / max(len(plano.encode("utf-8")), 1))),
    }
    summary = [
        f"Bloco de {len(bloco.encode()):,} bytes a partir de {len(plano.encode()):,} bytes de plano; "
        f"a visão é {abs(metrics['economia'])}% {'menor' if metrics['economia'] >= 0 else 'maior'} que o arquivo, "
        f"por {fonte}, com progresso por {fonte_progresso}.",
        f"Orçamento {orcamento:,}; truncado: {'sim' if truncada else 'não'}; hash do plano `{hash_plano}`.",
        f"{relogio} timestamp(s) normalizado(s) para manter o prefixo estável.",
    ]
    extra = [
        "",
        "## Fontes do bloco",
        "",
        "| Fonte | Modo | Bytes | Teto |",
        "| --- | --- | --- | --- |",
    ]
    extra += [f"| {row['fonte']} | {row['modo']} | {row['bytes']:,} | {row['teto']:,} |" for row in rows]
    extra += ["", "## Bloco proposto", "", "```markdown", bloco.strip() or "(vazio)", "```"]
    resultado = common(
        analysis="injecao",
        mode=modo,
        title="Injeção por turno",
        summary=summary,
        findings=achados,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows,
        metrics=metrics,
        limitations=[
            "Não instala hook nem escreve no contexto de nenhum agente: o bloco é texto na resposta.",
            "Não lê o cache do host: a estabilidade do prefixo é argumento, não medição.",
            "Não resume o progresso por modelo: a cauda é literal e o resumo do livro é contagem.",
            "O hash do plano não é atestação assinada — é impressão digital do texto colado.",
        ],
        extra_sections=extra,
    )
    resultado["bloco"] = bloco
    resultado["hash"] = hash_plano
    return resultado


# ------------------------------------------------------------------- livro

RE_TS_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")
CAMPOS_OBRIGATORIOS = ("tick", "ts", "agent", "event")


def _agrupar_achados(
    problemas: list[tuple[str, str, str]], grupo: str, tipo: str, titulo: str, what: str, problem: str, fix: str, se_ignorar: str
) -> dict[str, Any] | None:
    """Um achado por tipo, com os primeiros locais — evita 500 achados iguais."""
    itens = [(local, mensagem) for local, chave, mensagem in problemas if chave == tipo]
    if not itens:
        return None
    locais = ", ".join(f"`{local}`" for local, _ in itens[:5])
    if len(itens) > 5:
        locais += f" e mais {len(itens) - 5}"
    detalhe = "; ".join(mensagem for _, mensagem in itens[:3])
    return finding(grupo, tipo, titulo, locais, f"{len(itens)} ocorrência(s). {what} Exemplo: {detalhe}.", problem, fix, se_ignorar)


def livro(*, ledger: str, agente: str = "", modo: str = "full") -> dict[str, Any]:
    """Valida o `ledger-<agente>.jsonl` append-only do plano."""
    modo = _modo(modo)
    if not (ledger or "").strip():
        raise ContinuidadeError("Informe as linhas do livro: uma entrada JSON por linha, como o `ledger-append.sh` grava.")
    linhas = [linha for linha in _linhas(ledger) if linha.strip()]
    if len(linhas) > MAX_LINHAS:
        raise ContinuidadeError(f"O livro passa de {MAX_LINHAS:,} linhas: leia por período.")
    filtro = AGENTE_RE.sub("", agente.strip())
    if agente.strip() and not filtro:
        raise ContinuidadeError("O nome do agente precisa ter ao menos uma letra, dígito, `_` ou `-`.")

    problemas: list[tuple[str, str, str]] = []
    rows: list[dict[str, Any]] = []
    eventos: dict[str, int] = {evento: 0 for evento in EVENTOS}
    por_agente: dict[str, dict[str, Any]] = {}
    ticks: list[int] = []
    invalidas = 0

    for numero, linha in enumerate(linhas, start=1):
        local = f"linha {numero}"
        try:
            dado = json.loads(linha)
        except json.JSONDecodeError as exc:
            invalidas += 1
            problemas.append((local, "json", f"JSON inválido: {exc.msg}"))
            rows.append({"linha": numero, "tick": "—", "agente": "—", "evento": "—", "fase": "—", "resumo": linha[:40], "situacao": "json inválido"})
            continue
        if not isinstance(dado, dict):
            invalidas += 1
            problemas.append((local, "json", "a linha não é um objeto JSON"))
            rows.append({"linha": numero, "tick": "—", "agente": "—", "evento": "—", "fase": "—", "resumo": str(dado)[:40], "situacao": "não é objeto"})
            continue

        faltando = [campo for campo in CAMPOS_OBRIGATORIOS if campo not in dado]
        if faltando:
            invalidas += 1
            problemas.append((local, "campos", f"falta {', '.join(faltando)}"))
        tick = dado.get("tick")
        if not isinstance(tick, int) or isinstance(tick, bool):
            problemas.append((local, "tick", "`tick` não é inteiro"))
        elif tick < 1 or tick > TICK_MAX:
            problemas.append((local, "tick", f"`tick` fora de 1..{TICK_MAX}: {tick}"))
        else:
            ticks.append(tick)
        evento = str(dado.get("event") or "")
        if evento not in EVENTOS:
            problemas.append((local, "evento", f"evento `{evento or '(vazio)'}` fora dos seis previstos"))
        else:
            eventos[evento] += 1
        nome = str(dado.get("agent") or "")
        if not nome:
            problemas.append((local, "agente", "agente vazio: o upstream cai para `main`"))
            nome = "main"
        elif AGENTE_RE.search(nome):
            problemas.append((local, "agente", f"agente `{nome}` tem caractere fora de [A-Za-z0-9_-]"))
        ts = str(dado.get("ts") or "")
        if not RE_TS_ISO.fullmatch(ts):
            problemas.append((local, "ts", f"`ts` fora do formato ISO-8601 UTC: `{ts or '(vazio)'}`"))
        resumo = str(dado.get("summary") or "")
        if len(resumo) > RESUMO_MAX:
            problemas.append((local, "resumo", f"resumo com {len(resumo)} caracteres passa de {RESUMO_MAX}"))
        if "\n" in resumo:
            problemas.append((local, "resumo", "resumo com quebra de linha"))
        arquivos = dado.get("files", [])
        if arquivos and not (isinstance(arquivos, list) and all(isinstance(item, str) for item in arquivos)):
            problemas.append((local, "files", "`files` não é lista de texto"))
        if filtro and nome != filtro:
            continue
        registro = por_agente.setdefault(nome, {"agente": nome, "entradas": 0, "ultimo": "", "fase": ""})
        registro["entradas"] += 1
        registro["ultimo"] = evento or "?"
        registro["fase"] = str(dado.get("phase") or registro["fase"] or "")
        rows.append(
            {
                "linha": numero,
                "tick": tick if isinstance(tick, int) else "—",
                "agente": nome,
                "evento": evento or "—",
                "fase": str(dado.get("phase") or "—"),
                "resumo": _resumo(resumo, 48) or "—",
                "situacao": "ok" if evento in EVENTOS and isinstance(tick, int) else "revisar",
            }
        )

    if ticks:
        repetidos = len(ticks) - len(set(ticks))
        if repetidos:
            problemas.append(("livro", "tick", f"{repetidos} tick(s) repetido(s)"))
        fora_de_ordem = sum(1 for anterior, atual in zip(ticks, ticks[1:]) if atual < anterior)
        if fora_de_ordem:
            problemas.append(("livro", "ordem", f"{fora_de_ordem} salto(s) para trás na ordem do arquivo"))
        lacunas = sum(1 for anterior, atual in zip(ticks, ticks[1:]) if atual - anterior > 5)
        if lacunas:
            problemas.append(("livro", "lacuna", f"{lacunas} lacuna(s) de mais de 5 ticks"))
    if not ticks and linhas:
        problemas.append(("livro", "tick", "nenhuma linha trouxe `tick` inteiro"))

    findings: list[dict[str, Any]] = []
    for item in (
        _agrupar_achados(
            problemas, "must", "json", "Linha do livro fora do formato JSON",
            "A linha não é objeto JSON legível, então o resumo do livro descarta a entrada.",
            "O livro é a camada de máquina: linha quebrada some da contagem e a estagnação é detectada errado.",
            "Grave uma entrada por linha, via `ledger-append`, sem edição manual.",
            "O portão acha que o agente parou de progredir e libera a parada.",
        ),
        _agrupar_achados(
            problemas, "must", "evento", "Evento fora dos seis previstos",
            "O `event` não é `progress`, `phase_complete`, `error`, `gate_block`, `attest` nem `note`.",
            "Evento livre não é agregado pelo resumo e some da leitura do orquestrador.",
            "Use um dos seis valores declarados.",
            "A entrada existe no arquivo e não conta em lugar nenhum.",
        ),
        _agrupar_achados(
            problemas, "must", "tick", "Tick inválido ou repetido",
            "O `tick` precisa ser inteiro positivo e estritamente crescente entre todos os agentes.",
            "Tick repetido quebra a ordem total que o detector de estagnação usa para comparar avanço.",
            "Deixe o `ledger-append` calcular `1 + maior tick` em vez de digitar o número.",
            "Dois agentes gravam o mesmo tick e o resumo perde a ordem dos fatos.",
        ),
        _agrupar_achados(
            problemas, "should", "campos", "Entrada sem campo obrigatório",
            "Faltam `tick`, `ts`, `agent` ou `event`.",
            "Campo obrigatório ausente faz a linha ser lida como evento desconhecido.",
            "Grave a entrada completa: tick, ts ISO-8601, agent, phase, event, summary e files.",
            "A entrada vira ruído no meio do livro.",
        ),
        _agrupar_achados(
            problemas, "should", "ts", "Data fora do formato ISO-8601",
            "O `ts` não termina em `Z` nem traz offset, ou não tem hora.",
            "Sem hora comparável o resumo deixa de ser estável e o bloco injetado muda a cada leitura.",
            "Use `AAAA-MM-DDTHH:MM:SSZ`.",
            "O bloco reinjetado muda sem que o estado mude.",
        ),
        _agrupar_achados(
            problemas, "should", "resumo", "Resumo acima do teto ou com quebra de linha",
            f"O resumo é truncado em {RESUMO_MAX} caracteres e não pode ter newline.",
            "Resumo longo quebra a linha do JSONL em duas e o arquivo deixa de ser linha a linha.",
            "Resuma em uma frase curta.",
            "O livro deixa de ser parseável por ferramenta de texto.",
        ),
        _agrupar_achados(
            problemas, "should", "agente", "Nome de agente fora do padrão",
            "O nome do agente é sanitizado para [A-Za-z0-9_-] e vazio cai para `main`.",
            "Nome com espaço ou acento vira outro arquivo de livro: o histórico se parte em dois.",
            "Use nome curto sem acento nem espaço.",
            "O resumo mostra dois agentes onde há um.",
        ),
        _agrupar_achados(
            problemas, "nice", "ordem", "Ticks fora de ordem no arquivo",
            "A ordem do arquivo não acompanha o tick.",
            "A leitura por linha deixa de bater com a ordem dos fatos.",
            "Acrescente no fim, nunca no meio.",
            "A linha do tempo do trabalho sai trocada.",
        ),
        _agrupar_achados(
            problemas, "nice", "lacuna", "Lacuna no contador de ticks",
            "O tick salta mais de cinco posições.",
            "Salto grande costuma ser livro trocado de plano, não progresso de verdade.",
            "Confira se as entradas foram para o diretório do plano certo.",
            "A contagem de avanço compara planos diferentes.",
        ),
        _agrupar_achados(
            problemas, "nice", "files", "`files` fora do formato de lista",
            "O campo `files` deveria ser uma lista de caminhos em texto.",
            "Lista malformada impede contar quais arquivos a entrada tocou.",
            "Grave `--files a.py,b.py` e deixe o script montar a lista.",
            "A rastreabilidade por arquivo se perde.",
        ),
    ):
        if item is not None:
            findings.append(item)

    achados, counts, veredito, perguntas = finalize(
        findings, modo, ["Quem é o dono do livro quando dois agentes gravam no mesmo plano?"]
    )
    metrics = {
        "entradas": len(linhas),
        "filtradas": len(rows),
        "validas": len(linhas) - invalidas,
        "invalidas": invalidas,
        "agentes": len(por_agente),
        "primeiroTick": min(ticks) if ticks else 0,
        "ultimoTick": max(ticks) if ticks else 0,
        "lacunas": len([item for item in problemas if item[1] == "lacuna"]),
        "problemas": len(problemas),
    }
    metrics.update({f"evento_{evento}": total for evento, total in eventos.items()})
    summary = [
        f"{len(linhas)} entrada(s) no livro: {metrics['validas']} válida(s) e {invalidas} inválida(s).",
        f"{len(por_agente)} agente(s); ticks de {metrics['primeiroTick']} a {metrics['ultimoTick']}.",
        "Eventos: " + ", ".join(f"{evento} {total}" for evento, total in eventos.items() if total) or "nenhum evento reconhecido.",
    ]
    extra = [
        "",
        "## Agentes",
        "",
        "| Agente | Entradas | Último evento | Fase |",
        "| --- | --- | --- | --- |",
    ]
    extra += [
        f"| `{registro['agente']}` | {registro['entradas']} | {registro['ultimo'] or '—'} | {registro['fase'] or '—'} |"
        for registro in sorted(por_agente.values(), key=lambda item: item["agente"])
    ]
    extra += ["", "## Entradas", "", "| Linha | Tick | Agente | Evento | Fase | Resumo | Situação |", "| --- | --- | --- | --- | --- | --- | --- |"]
    extra += [
        f"| {row['linha']} | {row['tick']} | {row['agente']} | {row['evento']} | {row['fase']} | {row['resumo']} | {row['situacao']} |"
        for row in rows[:MAX_ROWS]
    ]
    resultado = common(
        analysis="livro",
        mode=modo,
        title="Livro de execução",
        summary=summary,
        findings=achados,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows[:MAX_ROWS],
        metrics=metrics,
        limitations=[
            "Não escreve nem acrescenta entrada: valida o que foi colado.",
            "Não abre o diretório do plano: o nome do arquivo `ledger-<agente>.jsonl` não é inferido.",
            "Não junta livros de agentes diferentes — para isso, cole as linhas em ordem de tick.",
            "Não valida conteúdo do resumo além de tamanho e quebra de linha.",
        ],
        extra_sections=extra,
    )
    resultado["agentes"] = sorted(por_agente.values(), key=lambda item: item["agente"])
    return resultado


# ------------------------------------------------------------------ médico

RE_ATTEST = re.compile(r"(^|/)\.?attest", re.I)
RE_LEDGER = re.compile(r"(^|/)ledger-[A-Za-z0-9_-]+\.jsonl$", re.I)
RE_TITULO_PLANO = re.compile(r"^#\s*Task\s+Plan\s*:\s*(.+)$", re.I | re.M)


def _bundle(texto: str) -> dict[str, dict[str, str]]:
    """Agrupa o bundle por diretório de plano: `>>> <plano>/<arquivo>`."""
    if len(texto) > MAX_TEXTO:
        raise ContinuidadeError(f"O texto passa de {MAX_TEXTO:,} caracteres.")
    grupos: dict[str, dict[str, str]] = {}
    atual: tuple[str, str] | None = None
    corpo: list[str] = []
    linhas = texto.replace("\r\n", "\n").split("\n")

    def fechar() -> None:
        nonlocal atual, corpo
        if atual is None:
            return
        plano, arquivo = atual
        grupos.setdefault(plano, {})[arquivo] = "\n".join(corpo).rstrip("\n")
        atual = None
        corpo = []

    for linha in linhas:
        if linha.lstrip().startswith(">>>"):
            fechar()
            caminho = linha.lstrip()[3:].strip().lstrip("./")
            if "/" in caminho:
                plano, arquivo = caminho.split("/", 1)
            else:
                plano, arquivo = ".", caminho
            atual = (plano, arquivo)
            continue
        if atual is not None:
            corpo.append(linha)
    fechar()
    return grupos


def medico(*, planos: str, ativo: str = "", modo: str = "full") -> dict[str, Any]:
    """Diagnostica o diretório de planos: arquivos, livro, atestação e plano ativo."""
    modo = _modo(modo)
    grupos = _bundle(planos)
    if not grupos:
        raise ContinuidadeError("Informe o diretório de planos: `>>> <plano>/task_plan.md` seguido do conteúdo.")
    if len(grupos) > MAX_PLANOS:
        raise ContinuidadeError(f"O diagnóstico passa de {MAX_PLANOS} planos: divida por projeto.")

    findings: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    com_fase_ativa: list[str] = []
    titulos: dict[str, list[str]] = {}

    for nome, arquivos in sorted(grupos.items()):
        plano = arquivos.get("task_plan.md", "")
        progresso = arquivos.get("progress.md", "")
        achados = arquivos.get("findings.md", "")
        ledger = [chave for chave in arquivos if RE_LEDGER.search(chave)]
        attest = [chave for chave in arquivos if RE_ATTEST.search(chave) and not RE_LEDGER.search(chave)]
        fases, secoes = ler_fases(plano) if plano else ([], [])
        ativa = next((fase for fase in fases if fase.status == "in_progress"), None)
        completas = sum(1 for fase in fases if fase.status == "complete")

        if not plano:
            findings.append(
                finding(
                    "must", "arquivo", "Plano sem `task_plan.md`",
                    nome,
                    "O diretório existe e não tem o arquivo que declara rumo e fase.",
                    "Sem `task_plan.md` nada resolve: nem retomada, nem portão, nem injeção.",
                    "Acrescente `task_plan.md` com `## Goal`, `## Next Step` e as fases.",
                    "O diretório é invisível para todo o resto da camada.",
                )
            )
            rows.append(
                {
                    "plano": nome,
                    "arquivos": len(arquivos),
                    "fases": 0,
                    "completas": 0,
                    "ativa": "—",
                    "livro": "não",
                    "attest": "não",
                    "situacao": "sem plano",
                    "ultima": "—",
                }
            )
            continue

        if not progresso:
            findings.append(
                finding(
                    "should", "arquivo", "Plano sem `progress.md`",
                    nome,
                    "O registro cronológico não está no diretório.",
                    "Plano diz o que falta; progresso diz o que já foi tentado. Sem o segundo, a próxima sessão repete erro.",
                    "Registre fase, data, ação e arquivo tocado a cada avanço.",
                    "A retomada recomeça a fase do zero.",
                )
            )
        if not achados:
            findings.append(
                finding(
                    "should", "arquivo", "Plano sem `findings.md`",
                    nome,
                    "O arquivo de conhecimento durável não está no diretório.",
                    "Requisito, decisão e fonte ficam só na conversa e morrem no `/clear`.",
                    "Registre requisito, achado e decisão no `findings.md`.",
                    "A fase de entrega julga sem o que foi aprendido.",
                )
            )
        if not ledger:
            findings.append(
                finding(
                    "should", "livro", "Plano sem livro de execução",
                    nome,
                    "Nenhum `ledger-<agente>.jsonl` no diretório.",
                    "Sem livro o portão não tem como distinguir avanço de estagnação e injeta texto livre de `progress.md`.",
                    "Comece o livro com uma entrada por evento relevante.",
                    "O portão libera a parada por falta de sinal, não por conclusão.",
                )
            )
        if not attest:
            findings.append(
                finding(
                    "nice", "atestacao", "Plano sem atestação",
                    nome,
                    "Nenhum arquivo de atestação ao lado do plano.",
                    "A atestação prova que o plano lido é o plano que o orquestrador escreveu; sem ela a injeção confia no arquivo.",
                    "Gere a atestação no fim de cada fase e reconfira ao retomar.",
                    "Edição manual do plano não é detectada.",
                )
            )
        if not fases:
            findings.append(
                finding(
                    "must", "fase", "Plano sem `### Phase`",
                    nome,
                    "O `task_plan.md` não tem fase numerada.",
                    "Sem fase o plano é prosa: não conta conclusão e não bloqueia parada.",
                    "Estruture em três a sete fases, cada uma com status e critério.",
                    "O portão nunca dispara e o plano vira diário.",
                )
            )
        objetivo = _valor_da_secao(secoes, "Goal") if secoes else ""
        if not objetivo:
            findings.append(
                finding(
                    "should", "secao", "Plano sem objetivo declarado",
                    nome,
                    "`## Goal` ausente ou vazio.",
                    "Objetivo é o que permite decidir entre dois caminhos sem perguntar de novo.",
                    "Acrescente `## Goal` com uma frase.",
                    "Cada sessão decide por conta própria e o rumo varia.",
                )
            )
        if ativa:
            com_fase_ativa.append(nome)
        titulo = RE_TITULO_PLANO.search(plano)
        if titulo:
            titulos.setdefault(titulo.group(1).strip().lower(), []).append(nome)
        datas = _datas(progresso)
        rows.append(
            {
                "plano": nome,
                "arquivos": len(arquivos),
                "fases": len(fases),
                "completas": completas,
                "ativa": ativa.rotulo if ativa else "—",
                "livro": "sim" if ledger else "não",
                "attest": "sim" if attest else "não",
                "situacao": "ok" if plano and fases and progresso and achados else "incompleto",
                "ultima": max(datas) if datas else "—",
            }
        )

    alvo = ativo.strip()
    if alvo and alvo not in grupos:
        findings.append(
            finding(
                "must", "ativo", "Plano ativo não existe no diretório",
                alvo,
                f"O plano declarado como ativo é `{alvo}` e o diretório não tem essa pasta.",
                "No upstream o seletor explícito é vínculo, não dica: se ele não resolve, nenhum outro plano é substituído — a execução para.",
                "Corrija o nome do plano ativo ou recrie o diretório.",
                "A automação lê o estado de outro plano, ou não lê nenhum.",
            )
        )
    elif not alvo and len(com_fase_ativa) > 1:
        findings.append(
            finding(
                "must", "ativo", "Ambiguidade de plano ativo",
                ", ".join(f"`{nome}`" for nome in com_fase_ativa),
                f"{len(com_fase_ativa)} planos têm fase em andamento e nenhum está declarado como ativo.",
                "Sem vínculo explícito o resolvedor escolhe pelo mais recente: a escolha fica invisível e pode ser a errada.",
                "Declare o plano ativo (`.active_plan`) antes de retomar.",
                "O agente trabalha em um plano enquanto a pessoa olha outro.",
            )
        )
    elif not alvo and not com_fase_ativa:
        findings.append(
            finding(
                "nice", "ativo", "Nenhum plano com fase em andamento",
                "diretório",
                "Há planos e nenhum tem fase ativa.",
                "Sem fase ativa o portão não bloqueia e a retomada não sabe por onde voltar.",
                "Marque `in_progress` na fase que está sendo trabalhada, ou encerre o plano.",
                "O diretório acumula plano parado.",
            )
        )

    for titulo, nomes in sorted(titulos.items()):
        if len(nomes) > 1:
            findings.append(
                finding(
                    "should", "duplicata", "Dois planos com o mesmo título",
                    ", ".join(f"`{nome}`" for nome in nomes),
                    f"O título `{titulo}` aparece em {len(nomes)} planos.",
                    "Título repetido é plano duplicado por acidente: um continua e o outro apodrece.",
                    "Una os dois ou renomeie o que foi criado por engano.",
                    "Metade do trabalho fica em um plano que ninguém abre.",
                )
            )

    achados, counts, veredito, perguntas = finalize(
        findings, modo, ["Qual plano é o ativo quando o diretório tem mais de um com fase aberta?"]
    )
    metrics = {
        "planos": len(grupos),
        "completos": sum(1 for row in rows if row["situacao"] == "ok"),
        "semLivro": sum(1 for row in rows if row["livro"] == "não"),
        "semAttest": sum(1 for row in rows if row["attest"] == "não"),
        "comAtiva": len(com_fase_ativa),
        "ativo": alvo or "não declarado",
        "duplicados": sum(1 for nomes in titulos.values() if len(nomes) > 1),
    }
    summary = [
        f"{len(grupos)} plano(s) no diretório; {metrics['completos']} com os três arquivos e fase declarada.",
        f"{metrics['semLivro']} sem livro, {metrics['semAttest']} sem atestação e {metrics['comAtiva']} com fase em andamento.",
        f"Plano ativo: {metrics['ativo']}.",
    ]
    extra = [
        "",
        "## Planos",
        "",
        "| Plano | Arquivos | Fases | Completas | Ativa | Livro | Attest | Última data | Situação |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    extra += [
        f"| `{row['plano']}` | {row['arquivos']} | {row['fases']} | {row['completas']} | {row['ativa']} | {row['livro']} | {row['attest']} | {row['ultima']} | {row['situacao']} |"
        for row in rows[:MAX_ROWS]
    ]
    resultado = common(
        analysis="medico",
        mode=modo,
        title="Diagnóstico do diretório de planos",
        summary=summary,
        findings=achados,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows[:MAX_ROWS],
        metrics=metrics,
        limitations=[
            "Não varre o disco: o diretório vem no bundle `>>> <plano>/<arquivo>`.",
            "Não altera `.active_plan`, não move arquivo e não cria plano.",
            "Não valida o conteúdo da atestação, só a presença do arquivo.",
            "A data mais recente é texto do `progress.md`, não mtime do sistema de arquivos.",
        ],
        extra_sections=extra,
    )
    return resultado


# ----------------------------------------------------------------- regras

def catalogo() -> dict[str, Any]:
    """Publica formatos, limites, guardas e a semântica de cada operação."""
    return {
        "executed": False,
        "readOnly": True,
        "versao": VERSAO,
        "origem": {
            "projeto": "OthmanAdi/planning-with-files",
            "licenca": "MIT",
            "estrelas": 27_629,
            "forks": 2_297,
            "commit_da_0_6": "de837a95cc845b6341a6cbfd902a89a8190c568e",
            "scripts": [
                "inject-plan.py",
                "session-catchup.py",
                "check-complete.sh",
                "plan-doctor.sh",
                "phase-status.sh",
                "ledger-append.sh",
                "ledger-summary.sh",
            ],
        },
        "principio": (
            "Plano em arquivo só continua valendo se a próxima sessão conseguir retomá-lo: "
            "fase com um status só, portão que sabe quando não bloquear e um bloco reinjetado "
            "que cabe no orçamento sem mudar a cada turno."
        ),
        "arquivos": {
            "plano": "task_plan.md — Goal, Next Step, Current Phase, Phases com `### Phase N`, Key Questions, Decisions Made, Errors Encountered",
            "progresso": "progress.md — Session com data, fases com status, Test Results, Error Log, 5-Question Reboot Check",
            "achados": "findings.md — Requirements, Research Findings, Technical Decisions, Issues Encountered, Resources",
            "livro": "ledger-<agente>.jsonl — uma entrada JSON por linha, append-only",
            "modo": ".mode — contém `gate` para armar o portão de conclusão",
            "atestacao": "arquivo de atestação do hash do plano, reescrito a cada fase",
        },
        "status": list(STATUS),
        "formatos_de_status": ["**Status:** <status>", "[<status>]"],
        "eventos": list(EVENTOS),
        "guardas_do_portao": [
            {"ordem": 1, "guarda": "modo `gate` declarado", "permite_parada": "sempre que ausente"},
            {"ordem": 2, "guarda": "existe fase em andamento", "permite_parada": "quando não há fase ativa"},
            {"ordem": 3, "guarda": "parada forçada desligada", "permite_parada": "quando `stop_hook_active` é verdadeiro"},
            {"ordem": 4, "guarda": "abaixo do teto de bloqueios", "permite_parada": f"ao atingir {GATE_CAP}"},
            {"ordem": 5, "guarda": "o livro avançou", "permite_parada": "quando nada foi registrado desde o último bloqueio"},
        ],
        "injeção": {
            "secoes_prioritarias": ["Goal", "Next Step", "Current Phase", "fase ativa", "Decisions Made"],
            "orcamento_plano": ORCAMENTO_PLANO,
            "orcamento_progresso": ORCAMENTO_PROGRESSO,
            "cauda_do_progresso": TAIL_PROGRESSO,
            "cabecalho_do_plano": HEAD_PLANO,
            "normalizacao": "hora zerada em todo timestamp, fuso preservado",
        },
        "regras": [
            "Uma marca de status por fase; duas marcas contam duas vezes e adiantam a conclusão.",
            "A contagem do portão usa o maior valor entre o formato `**Status:**` e o formato `[status]`.",
            "Fase sem status não entra em nenhuma contagem: nem pendente, nem ativa, nem concluída.",
            "O portão só bloqueia com opt-in declarado, fase ativa, parada não forçada, abaixo do teto e livro avançando.",
            "Sem fase em andamento, a incompletude não bloqueia parada — é estado normal, não laço.",
            "Estagnação libera a parada: bloquear de novo sem entrada nova só repete a mensagem.",
            "`tick` é 1 + o maior tick de todos os livros do diretório, e nunca se repete.",
            "Resumo de evento cabe em 200 caracteres e não tem quebra de linha.",
            "O bloco reinjetado normaliza a hora: timestamp que muda invalida o prefixo e encarece o turno.",
            "Seletor de plano explícito é vínculo: quando não resolve, nenhum outro plano é substituído.",
            "Plano e progresso são duas fontes do mesmo fato; divergência de status é bloqueio, não observação.",
            "O plano é do orquestrador; o livro é de cada agente. Quem trabalha registra, quem coordena decide.",
        ],
        "limites": {
            "texto": MAX_TEXTO,
            "linhas": MAX_LINHAS,
            "fases": MAX_FASES,
            "planos": MAX_PLANOS,
            "bloqueios": GATE_CAP,
            "resumo": RESUMO_MAX,
            "tick": TICK_MAX,
            "orcamento": ORCAMENTO_PLANO,
            "attest": CABECALHO_ATTEST,
            "linhas_tabela": MAX_ROWS,
        },
        "operacoes": [
            {"id": "fases", "entrada": "task_plan.md", "saida": "fases com status, critério e inconsistência"},
            {"id": "portao", "entrada": "plano + bloqueios + livro", "saida": "block ou allow com o guarda que decidiu"},
            {"id": "retomada", "entrada": "plano + progresso + achados", "saida": "estado e as cinco perguntas"},
            {"id": "injecao", "entrada": "plano + progresso + livro", "saida": "bloco com orçamento e corte declarados"},
            {"id": "livro", "entrada": "linhas JSONL", "saida": "entradas válidas, ordem, lacuna e resumo por agente"},
            {"id": "medico", "entrada": "bundle de diretório", "saida": "arquivo faltando, livro, atestação e ambiguidade"},
        ],
        "nao_faz": [
            "Não escreve plano, progresso, livro, `.mode` ou atestação.",
            "Não instala hook, não bloqueia sessão e não para agente nenhum.",
            "Não lê o disco: o diretório chega no bundle `>>> <plano>/<arquivo>`.",
            "Não chama modelo para resumir: o bloco é corte, contagem e normalização de relógio.",
        ],
    }
