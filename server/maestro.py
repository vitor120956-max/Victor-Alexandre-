"""Maestro — orquestração determinística de skills (0.91.0).

O problema que este módulo resolve: até a 0.90.0 o JARVIS sabia fazer **uma**
coisa por pedido. “Pesquisa isso e guarda num arquivo” tem duas, e a pessoa
tinha de pedir duas vezes, na ordem certa, passando o resultado de uma para a
outra na mão.

O maestro é o que encadeia. E ele foi escrito com quatro regras que existem
para não repetir os erros desta semana:

1. **Nada de modelo.** A decomposição é uma **receita declarada** (procedimento)
   com passos em ordem. Pedido igual → plano igual, sempre. Quem inventa passo
   é o modelo, e modelo inventa passo errado com confiança.
2. **Só skill do catálogo.** Cada passo nomeia uma skill que existe no registro;
   se não existir, o plano é recusado antes de qualquer execução.
3. **Efeito colateral pausa a fila.** Passo que abre, grava, baixa ou digita só
   roda com autorização explícita. Sem ela, o maestro **para ali** e diz o que
   faria — não “continua com o que dá”.
4. **Erro para a fila.** Se um passo falha, os seguintes não rodam. Continuar
   depois de um erro é construir em cima de resultado que não veio.

O que este módulo **não** faz: abrir shell, avaliar expressão vinda de texto
livre, ou deixar o modelo escolher qual skill roda. A referência entre passos é
uma linguagem mínima (`$pedido`, `$1.resposta`, `{{2.slug}}`) resolvida por
código, não por interpretador.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


class MaestroError(ValueError):
    """Procedimento desconhecido, passo inválido, referência que não resolve."""


# ---------------------------------------------------------------------------
# Peças
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Passo:
    """Um passo de um procedimento: uma skill e os campos dela.

    `campos` aceita três formas de valor:

    - literal: `{"programa": "bloco de notas"}`;
    - referência pura: `"$pedido"` (o pedido inteiro) ou `"$1.slug"` (campo
      `slug` da saída do passo 1);
    - modelo: `"resumo de {{1.resposta}}"` — interpolação dentro de texto.
    """

    skill: str
    campos: dict[str, Any] = field(default_factory=dict)
    porque: str = ""
    # Campo da saída que precisa vir verdadeiro para o passo valer. Um passo
    # que "rodou" e devolveu `lido: false` não leu nada — seguir para o
    # seguinte é construir em cima de vazio. Fica declarado, não adivinhado.
    exigir: str = ""
    # O que dizer à pessoa quando **este** passo barra a fila. Declarado junto
    # do passo porque só ele sabe qual é a saída.
    dica: str = ""
    # Se o passo produz um documento (dossiê, relatório), o terminal mostra o
    # texto inteiro. Cortar em 160 caracteres o produto do passo é entregar
    # nada com aparência de entrega.
    mostrar_texto: bool = False


@dataclass(frozen=True)
class Procedimento:
    id: str
    nome: str
    exemplo: str
    # Palavras que precisam aparecer no pedido para este procedimento servir.
    # `precisa`: todas aparecem. `grupos`: de cada grupo, pelo menos uma.
    # É por grupo que “salva” e “guarda” viram a mesma intenção sem lista de
    # sinônimo solta: o procedimento exige *um* verbo de pesquisa **e** *um* de
    # gravação, não qualquer um dos dois.
    passos: tuple[Passo, ...]
    precisa: tuple[str, ...] = ()
    grupos: tuple[tuple[str, ...], ...] = ()
    limites: str = ""


# ---------------------------------------------------------------------------
# Procedimentos — poucos, declarados e testáveis
# ---------------------------------------------------------------------------

PROCEDIMENTOS: tuple[Procedimento, ...] = (
    Procedimento(
        id="pesquisar-guardar",
        nome="Pesquisar na web e guardar num arquivo",
        exemplo="pesquisa o clima de Palhoça e guarda em clima.txt",
        grupos=(
            ("pesquis", "procura", "busca", "consulta"),
            ("guard", "salv", "anot", "escrev"),
        ),
        passos=(
            Passo(
                skill="sistema.rede",
                campos={"acao": "buscar", "consulta": "$pedido_limpo", "fonte": "auto", "limite": 6},
                porque="buscar e ler as fontes antes de escrever qualquer coisa",
            ),
            Passo(
                skill="files.write",
                campos={
                    "path": "$arquivo",
                    "content": "# {{pedido}}\n\n{{1.resumo}}\n\n## Resultados\n{{1.linhas}}\n",
                    "overwrite": True,
                },
                porque="gravar o que foi encontrado, com as fontes junto",
            ),
        ),
        limites=(
            "Se a busca não achar nada, o segundo passo não roda: gravar um arquivo "
            "vazio com o nome de uma pesquisa seria pior que não gravar."
        ),
    ),
    Procedimento(
        id="baixar-repositorio",
        nome="Baixar um repositório do GitHub e analisar",
        exemplo="baixa o repositório https://github.com/vitor120956-max/Victor-Alexandre- e analisa",
        precisa=("repositor",),
        grupos=(("baixa", "clona", "puxa"), ("analis", "explica", "ve como", "mostra")),
        passos=(
            Passo(
                skill="repos.baixar",
                campos={"url": "$url"},
                porque="baixar o zip do repositório e conferir o que veio",
            ),
            Passo(
                skill="repos.analisar",
                campos={"repo": "$1.slug"},
                porque="ler o que foi baixado: arquivos, tamanho e tipos",
            ),
        ),
        limites=(
            "Baixar é efeito colateral: sem autorização, o maestro para no passo 1 "
            "e mostra o que faria."
        ),
    ),
    Procedimento(
        id="consertar-erro",
        nome="Diagnosticar um erro e montar o dossiê",
        exemplo="conserta o erro que apareceu no meu programa",
        precisa=("erro",),
        grupos=(("conserta", "consertar", "arruma", "arrumar", "diagnostic", "corrig", "resolve"),),
        passos=(
            Passo(
                skill="conserto.diagnosticar",
                campos={"erro": "$erro"},
                porque="dizer onde quebrou e por quê, antes de propor conserto",
                exigir="lido",
                dica=(
                    "o diário de erros não tinha nada e o pedido não trouxe erro. "
                    "Cole o traceback junto com o pedido, ou deixe o JARVIS registrar a falha antes."
                ),
            ),
            Passo(
                skill="conserto.dossie",
                campos={"erro": "$erro"},
                porque="juntar o que é preciso para corrigir de primeira",
                exigir="lido",
                mostrar_texto=True,
            ),
            Passo(
                skill="conserto.propor",
                campos={"erro": "$erro"},
                porque="propor o patch — este passo tem efeito, então pede autorização",
                exigir="proposto",
            ),
        ),
        limites=(
            "O maestro não aplica o patch: ele mostra. Aplicar é outra decisão, com "
            "outro comando."
        ),
    ),
    Procedimento(
        id="escrever-no-programa",
        nome="Abrir um programa e escrever",
        exemplo='escreve "oi, mundo" no bloco de notas',
        precisa=("escrev",),
        grupos=(("bloco de notas", "notepad", "paint", "calculadora", "programa"),),
        passos=(
            Passo(
                skill="mesa.ditar",
                campos={"programa": "$programa", "texto": "$texto", "executar": True},
                porque="abrir se preciso, achar o campo, escrever e conferir lendo de volta",
            ),
        ),
        limites=(
            "Só a lista fechada de programas, e só no Windows. É o passo que já foi "
            "medido no PC do usuário em 0.90.0."
        ),
    ),
)


# ---------------------------------------------------------------------------
# Extração do pedido
# ---------------------------------------------------------------------------

_RE_URL = re.compile(r"https?://[^\s\"']+")
_RE_ASPAS = re.compile(r"[\"“”']([^\"“”']{1,300})[\"“”']")
_RE_ARQUIVO = re.compile(r"em\s+([\w./\\-]+\.(?:txt|md|json|csv))\b", re.IGNORECASE)
_RE_PROGRAMA = re.compile(
    r"\b(bloco de notas|notepad|paint|mspaint|calculadora|calc|wordpad|cmd|powershell)\b",
    re.IGNORECASE,
)


def limpar_pedido(pedido: str) -> str:
    """O pedido sem endereço e sem o verbo de guardar — é o que se pesquisa."""
    texto = _RE_URL.sub(" ", pedido or "")
    texto = re.sub(r"\s+e\s+(guarda|salva|anota)\b.*$", "", texto, flags=re.IGNORECASE)
    texto = re.sub(r"\b(guarda|salva|anota)\b.*$", "", texto, flags=re.IGNORECASE)
    texto = re.sub(
        r"^(pesquisa|pesquisar|procura|procurar|busca|buscar)\s+(por\s+|sobre\s+)?",
        "",
        texto.strip(),
        flags=re.IGNORECASE,
    )
    texto = re.sub(r"^(o|a|os|as|um|uma)\s+", "", texto.strip(), flags=re.IGNORECASE)
    return " ".join(texto.split()).strip(" .,")


def _programa_do_pedido(pedido: str) -> str:
    achado = _RE_PROGRAMA.search(pedido or "")
    if not achado:
        return ""
    return achado.group(1).lower()


def _texto_do_pedido(pedido: str) -> str:
    """O que está entre aspas; sem aspas, o que vem depois de “escreve”."""
    achado = _RE_ASPAS.search(pedido or "")
    if achado:
        return achado.group(1).strip()
    resto = re.sub(r"^.*?\b(escreve|escrever|escreva|digita|digitar)\b\s*", "", pedido or "", flags=re.IGNORECASE)
    resto = re.sub(r"\s+(no|na|em)\s+.*$", "", resto, flags=re.IGNORECASE)
    return resto.strip(" .,")


_RE_TRACEBACK = re.compile(r"Traceback \(most recent call last\)", re.IGNORECASE)
# Um erro de uma linha: `KeyError: 'a'`, `ValueError: ...`, `Exception in ...`.
_RE_ERRO_UMA_LINHA = re.compile(
    r"\b(?:[A-Z][A-Za-z]*(?:Error|Exception)|Exception|Error)\b\s*[:\-]?",
)
# Como o pedido costuma começar quando o erro vem depois dele.
_RE_COMANDO = re.compile(
    r"^\s*(?:por favor\s+)?(?:conserta|consertar|arruma|arrumar|corrige|corrigir|"
    r"resolve|resolver|diagnostica|diagnosticar|ve|ver|olha|ver\s+esse)\s+"
    r"(?:o\s+|a\s+|esse\s+|este\s+|isso\s+)*(?:erro\s+)?",
    re.IGNORECASE,
)


def erro_do_pedido(pedido: str) -> str:
    """O erro em si — **vazio** quando o pedido não traz erro nenhum.

    Duas coisas erradas antes da 0.91.3, as duas medidas no PC do usuário:

    1. “conserta o erro do meu programa” chegava ao diagnóstico como se fosse
       um traceback colado. A skill respondia `lido: true, fonte: colado`, o
       maestro aceitava, e o dossiê saía com `exceção: :` — vazio.
    2. “conserta esse erro: <traceback>” mandava a frase junto.

    Devolver vazio é o certo: a skill cai no diário de erros, que é onde os
    erros de verdade estão. Se o diário também estiver vazio, ela responde
    `lido: false` e o maestro para no passo 1 em vez de inventar dossiê.
    """
    texto = (pedido or "").strip()
    achado = _RE_TRACEBACK.search(texto)
    if achado:
        return texto[achado.start():].strip()
    sem_comando = _RE_COMANDO.sub("", texto).strip()
    if _RE_ERRO_UMA_LINHA.search(sem_comando):
        return sem_comando
    return ""


def slots_do_pedido(pedido: str) -> dict[str, str]:
    """O que dá para tirar do texto sem inventar: url, arquivo, programa, texto."""
    texto = pedido or ""
    url = (_RE_URL.search(texto).group(0).rstrip(").,") if _RE_URL.search(texto) else "")
    arquivo = (_RE_ARQUIVO.search(texto).group(1) if _RE_ARQUIVO.search(texto) else "pesquisa.txt")
    slots = {
        "pedido_limpo": limpar_pedido(texto),
        "url": url,
        "arquivo": arquivo,
        "programa": _programa_do_pedido(texto),
        "texto": _texto_do_pedido(texto),
        "erro": erro_do_pedido(texto),
    }
    return slots


def _normalizar(texto: str) -> str:
    """Minúsculas, sem acento, espaço simples — igual a `agente_local.normalizar`.

    Copiado em vez de importado de propósito: `agente_local` importa este
    módulo, e a importação inversa fecharia o ciclo. Um teste garante que as
    duas versões dão o mesmo resultado.
    """
    decomposto = unicodedata.normalize("NFKD", texto or "")
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem_acento.lower()).strip()


def escolher_procedimento(pedido: str) -> Procedimento | None:
    """O procedimento que casa com o pedido — ou `None`.

    Casa por **palavras declaradas**, na ordem em que os procedimentos foram
    escritos. Não é “o mais parecido”: é “o primeiro que satisfaz as condições”.
    Pedido igual devolve sempre o mesmo procedimento.
    """
    alvo = _normalizar(pedido)
    if not alvo:
        return None
    for procedimento in PROCEDIMENTOS:
        if not all(_normalizar(p) in alvo for p in procedimento.precisa):
            continue
        if any(
            not any(_normalizar(termo) in alvo for termo in grupo)
            for grupo in procedimento.grupos
        ):
            continue
        return procedimento
    return None


# ---------------------------------------------------------------------------
# Plano
# ---------------------------------------------------------------------------

def _schema_de(registry: Any, skill: str) -> dict[str, Any]:
    for item in registry.list():
        if item["id"] == skill:
            return item.get("inputSchema") or {}
    raise MaestroError(f"o procedimento usa a skill “{skill}”, que não existe no catálogo.")


def _efeito(registry: Any, skill: str) -> bool:
    for item in registry.list():
        if item["id"] == skill:
            return bool(item.get("sideEffects"))
    return False


def planejar(pedido: str, *, registry: Any, procedimento: Procedimento | None = None) -> dict[str, Any]:
    """Monta o plano — e não executa nada.

    Cada passo já vem com os campos resolvidos que **não dependem de saída
    anterior**; o que depende fica como referência e é resolvido na hora de
    rodar (o valor ainda não existe).
    """
    escolhido = procedimento or escolher_procedimento(pedido)
    if escolhido is None:
        nomes = ", ".join(p.id for p in PROCEDIMENTOS)
        raise MaestroError(
            "não tenho procedimento para esse pedido. Os que existem: "
            f"{nomes}. Um pedido precisa casar com as palavras declaradas de um deles."
        )

    slots = slots_do_pedido(pedido)
    passos: list[dict[str, Any]] = []
    for numero, passo in enumerate(escolhido.passos, start=1):
        schema = _schema_de(registry, passo.skill)
        obrigatorios = list(schema.get("required") or [])
        campos = dict(passo.campos)

        # O que já dá para conferir no plano: campo sem referência a passo
        # anterior. Campo que vem de outro passo só é conferível na hora.
        vindos: list[str] = []
        faltando: list[str] = []
        contexto = _contexto(pedido, slots, [])
        for nome in obrigatorios:
            if nome not in campos:
                faltando.append(nome)
                continue
            bruto = campos[nome]
            if _depende_de_passo_anterior(bruto):
                vindos.append(f"{nome} (do passo {_passo_de_origem(bruto)})")
                continue
            if not str(resolver_valor(bruto, contexto=contexto) or "").strip():
                faltando.append(nome)

        passos.append(
            {
                "n": numero,
                "skill": passo.skill,
                "porque": passo.porque,
                "campos": campos,
                "efeito": _efeito(registry, passo.skill),
                "exigir": passo.exigir,
                "dica": passo.dica,
                "mostrar_texto": passo.mostrar_texto,
                "obrigatorios": obrigatorios,
                "faltando": sorted(set(faltando)),
                "vem_do_passo": vindos,
            }
        )

    return {
        "procedimento": escolhido.id,
        "nome": escolhido.nome,
        "exemplo": escolhido.exemplo,
        "pedido": pedido,
        "slots": slots,
        "passos": passos,
        "limites": escolhido.limites,
        "precisa_autorizacao": any(item["efeito"] for item in passos),
        "resumo": _resumo(passos, escolhido),
    }


def _depende_de_passo_anterior(valor: Any) -> bool:
    """True se o valor cita a saída de um passo (`$1.x` ou `{{1.x}}`)."""
    if not isinstance(valor, str):
        return False
    return bool(re.search(r"\$\d+\.", valor) or re.search(r"\{\{\d+\.", valor))


def _passo_de_origem(valor: Any) -> str:
    achado = re.search(r"(?:\$|\{\{)(\d+)\.", str(valor))
    return achado.group(1) if achado else "?"


def _resumo(passos: list[dict[str, Any]], procedimento: Procedimento) -> str:
    partes = [f"{item['n']}. {item['skill']}" + (" (tem efeito)" if item["efeito"] else "") for item in passos]
    return f"{procedimento.nome}: " + " → ".join(partes)


# ---------------------------------------------------------------------------
# Referências entre passos
# ---------------------------------------------------------------------------

_RE_REF = re.compile(r"\$(\d+)\.([\w.]+)")
_RE_CHAVE = re.compile(r"\{\{([\w.]+)\}\}")


def _buscar_caminho(origem: Any, caminho: str) -> Any:
    atual = origem
    for parte in caminho.split("."):
        if isinstance(atual, dict) and parte in atual:
            atual = atual[parte]
        elif isinstance(atual, list) and parte.isdigit() and int(parte) < len(atual):
            atual = atual[int(parte)]
        else:
            return ""
    return atual


def _contexto(pedido: str, slots: dict[str, str], saidas: list[dict[str, Any]]) -> dict[str, Any]:
    return {"pedido": pedido, "slots": slots, "saidas": saidas}


def resolver_valor(valor: Any, *, contexto: dict[str, Any]) -> Any:
    """Resolve `$pedido`, `$slot`, `$1.slug` e `{{2.slug}}` — e nada além disso.

    Não existe `eval`, não existe acesso a atributo, não existe chamada. O que
    não resolve vira string vazia, e `campos_do_passo` barra o passo antes de
    rodar se o campo era obrigatório. Ir com campo vazio seria pior.
    """
    if not isinstance(valor, str):
        return valor

    pedido = contexto["pedido"]
    slots = contexto["slots"]
    saidas = contexto["saidas"]

    # Referência pura: o valor É a referência (pode devolver número, lista...).
    if valor.startswith("$") and " " not in valor and "{{" not in valor:
        return _referencia_pura(valor, pedido=pedido, slots=slots, saidas=saidas)

    # Modelo: interpolação dentro de texto, sempre vira string.
    if "{{" in valor:
        return _RE_CHAVE.sub(
            lambda m: _formatar(_chave(m.group(1), pedido=pedido, slots=slots, saidas=saidas)),
            valor,
        )
    return valor


def _referencia_pura(valor: str, *, pedido: str, slots: dict[str, str], saidas: list[dict[str, Any]]) -> Any:
    if valor == "$pedido":
        return pedido
    if valor == "$pedido_limpo":
        return slots.get("pedido_limpo", "")
    nome = valor[1:]
    if nome in slots:
        return slots[nome]
    achado = _RE_REF.fullmatch(valor)
    if achado:
        return _chave(f"{achado.group(1)}.{achado.group(2)}", pedido=pedido, slots=slots, saidas=saidas)
    return ""


def _chave(chave: str, *, pedido: str, slots: dict[str, str], saidas: list[dict[str, Any]]) -> Any:
    """Uma chave de dentro de `{{...}}` ou de uma referência `$N.caminho`."""
    if chave == "pedido":
        return slots.get("pedido_limpo") or pedido
    if chave in slots:
        return slots[chave]
    partes = chave.split(".")
    if partes[0].isdigit():
        indice = int(partes[0]) - 1
        if 0 <= indice < len(saidas):
            resto = ".".join(partes[1:])
            if resto == "resumo":
                return _resumo_da_saida(saidas[indice])
            if resto == "linhas":
                return _linhas_da_saida(saidas[indice])
            return _buscar_caminho(saidas[indice], resto)
    return ""


def _formatar(valor: Any) -> str:
    if isinstance(valor, list):
        return "\n".join(f"- {_formatar(item)}" for item in valor)
    if isinstance(valor, dict):
        return "\n".join(f"{chave}: {_formatar(item)}" for chave, item in valor.items())
    return "" if valor is None else str(valor)


def _resumo_da_saida(saida: dict[str, Any]) -> str:
    """O resumo de qualquer skill, como texto — `summary` vem em lista."""
    resumo: Any = saida.get("summary") or saida.get("resposta") or saida.get("resumo") or ""
    if isinstance(resumo, list):
        return "\n".join(str(item) for item in resumo)
    return str(resumo)


def _linhas_da_saida(saida: dict[str, Any]) -> str:
    """As linhas de resultado como lista markdown, sem inventar campo.

    `sistema.rede` devolve `rows` com titulo/url; outras skills devolvem
    `fontes`. Se não houver nenhum dos dois, devolve o resumo — nunca vazio
    quando há alguma coisa para gravar.
    """
    linhas: list[str] = []
    for item in saida.get("rows") or saida.get("fontes") or []:
        if isinstance(item, dict):
            titulo = item.get("titulo") or item.get("title") or ""
            url = item.get("url") or ""
            pedaco = f"- {titulo}".strip()
            if url:
                pedaco += f" — {url}"
            if not titulo and not url:
                pedaco = "- " + ", ".join(f"{k}: {v}" for k, v in item.items() if v)
            linhas.append(pedaco)
        elif item:
            linhas.append(f"- {item}")
    if linhas:
        return "\n".join(linhas)
    return _resumo_da_saida(saida)


def campos_do_passo(passo: dict[str, Any], *, contexto: dict[str, Any]) -> dict[str, Any]:
    """Resolve os campos de um passo e barra o que ficou obrigatório e vazio."""
    campos = {
        nome: resolver_valor(valor, contexto=contexto)
        for nome, valor in (passo.get("campos") or {}).items()
    }
    faltando = [
        nome for nome in passo.get("obrigatorios") or [] if not str(campos.get(nome) or "").strip()
    ]
    if faltando:
        raise MaestroError(
            f"o passo {passo['n']} ({passo['skill']}) precisa de {', '.join(faltando)} "
            "e o pedido não trouxe esse dado. Falta informação, não é falha do JARVIS: "
            "diga o dado no pedido e repita."
        )
    return campos


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------

Executador = Callable[[str, dict[str, Any], bool], Awaitable[dict[str, Any]]]


async def executar(
    plano: dict[str, Any],
    *,
    registry: Any,
    autorizar: bool = False,
    executador: Executador | None = None,
) -> dict[str, Any]:
    """Roda o plano **na ordem**, parando onde precisa parar.

    Para em três casos, e sempre diz qual:

    - passo com efeito e sem autorização (`precisa_autorizacao`);
    - passo que falhou (`erro`);
    - passo sem dado obrigatório (`falta_dado`).

    Nunca “segue com o que dá”: os passos seguintes dependem dos anteriores.
    """
    rodar = executador or (lambda skill, campos, dry: registry.execute(skill, campos, dry_run=dry))
    saidas: list[dict[str, Any]] = []
    feitos: list[dict[str, Any]] = []
    contexto = _contexto(plano["pedido"], plano["slots"], saidas)

    for passo in plano["passos"]:
        if passo["efeito"] and not autorizar:
            return _parada(
                plano, feitos, saidas, passo, "precisa_autorizacao",
                "este passo tem efeito colateral e ninguém autorizou. "
                "Repita com autorização para ele rodar.",
            )
        try:
            campos = campos_do_passo(passo, contexto=contexto)
        except MaestroError as exc:
            return _parada(plano, feitos, saidas, passo, "falta_dado", str(exc))
        try:
            saida = await rodar(passo["skill"], campos, False)
        except Exception as exc:  # noqa: BLE001 - a falha é o resultado
            return _parada(
                plano, feitos, saidas, passo, "erro",
                f"{type(exc).__name__}: {exc}",
            )
        normalizada = saida if isinstance(saida, dict) else {"resultado": saida}
        exigir = passo.get("exigir") or ""
        if exigir and not normalizada.get(exigir):
            # Rodou, mas não leu/fez o que o próximo passo precisa. Tratar
            # isto como sucesso é o que produz dossiê de erro que não existe.
            motivo_da_skill = _linha_da_saida(normalizada) or "sem detalhe na saída"
            return _parada(
                plano, feitos, saidas, passo, "nao_confirmado",
                f"a skill rodou mas não concluiu ({exigir}=false): {motivo_da_skill}",
            )
        saidas.append(normalizada)
        feitos.append(
            {
                "n": passo["n"],
                "skill": passo["skill"],
                "campos": campos,
                "saida": saidas[-1],
                "mostrar_texto": bool(passo.get("mostrar_texto")),
            }
        )

    return {
        "ok": True,
        "procedimento": plano["procedimento"],
        "nome": plano["nome"],
        "passos": feitos,
        "parou_em": None,
        "motivo": "",
        "resumo": f"{len(feitos)} passo(s) concluído(s): {plano['resumo']}",
        "ultimo": saidas[-1] if saidas else {},
    }


def _linha_da_saida(saida: dict[str, Any], limite: int = 160) -> str:
    """Uma linha do que a skill devolveu — para a pessoa ver, sem despejar JSON."""
    for chave in ("resumo", "summary", "motivo", "resposta", "feito", "mensagem", "texto", "aviso"):
        valor = saida.get(chave)
        if not valor:
            continue
        if isinstance(valor, list):
            valor = " ".join(str(item) for item in valor)
        linha = " ".join(str(valor).split())
        if linha:
            return linha if len(linha) <= limite else linha[: limite - 1] + "…"
    # Sem campo conhecido: mostra os escalares, que é o que dá para afirmar.
    pedacos = [
        f"{chave}={valor}"
        for chave, valor in saida.items()
        if isinstance(valor, (str, int, float, bool)) and str(valor).strip()
    ]
    linha = ", ".join(pedacos)
    return linha if len(linha) <= limite else linha[: limite - 1] + "…"


def _resumo_da_parada(passo: dict[str, Any], motivo: str, feitos: int) -> str:
    """Frase única da parada — com a dica quando o passo declarou uma."""
    if feitos:
        base = f"parei no passo {passo['n']} ({passo['skill']}): {motivo} ({feitos} passo(s) antes deram certo)"
    else:
        base = f"parei antes de fazer qualquer coisa, no passo {passo['n']} ({passo['skill']}): {motivo}"
    dica = (passo.get("dica") or "").strip()
    return f"{base} — o que fazer: {dica}" if dica else base


def _parada(
    plano: dict[str, Any],
    feitos: list[dict[str, Any]],
    saidas: list[dict[str, Any]],
    passo: dict[str, Any],
    tipo: str,
    motivo: str,
) -> dict[str, Any]:
    return {
        "ok": tipo == "precisa_autorizacao" and not feitos,
        "procedimento": plano["procedimento"],
        "nome": plano["nome"],
        "passos": feitos,
        "parou_em": passo["n"],
        "parou_motivo": tipo,
        "passo_que_parou": {
            "n": passo["n"],
            "skill": passo["skill"],
            "porque": passo["porque"],
            "dica": passo.get("dica") or "",
        },
        "motivo": motivo,
        "resumo": _resumo_da_parada(passo, motivo, len(feitos)),
        "ultimo": saidas[-1] if saidas else {},
    }


# ---------------------------------------------------------------------------
# Texto para gente — é o que o chat e o PC mostram
# ---------------------------------------------------------------------------

def catalogo() -> dict[str, Any]:
    """Os procedimentos declarados, sem executar nada."""
    return {
        "total": len(PROCEDIMENTOS),
        "procedimentos": [
            {
                "id": p.id,
                "nome": p.nome,
                "exemplo": p.exemplo,
                "passos": [{"n": i, "skill": passo.skill, "porque": passo.porque} for i, passo in enumerate(p.passos, start=1)],
                "limites": p.limites,
            }
            for p in PROCEDIMENTOS
        ],
        "texto": "\n".join(
            [f"{len(PROCEDIMENTOS)} procedimento(s) declarado(s):"]
            + [f"- {p.id}: {p.nome} — {' → '.join(passo.skill for passo in p.passos)}" for p in PROCEDIMENTOS]
        ),
    }


def por_id(identificador: str) -> Procedimento | None:
    alvo = _normalizar(identificador)
    return next((p for p in PROCEDIMENTOS if _normalizar(p.id) == alvo), None)


def pedido(pedido: str, *, registry: Any, procedimento: str = "") -> dict[str, Any]:
    """`planejar`, aceitando o procedimento por id (o que a skill recebe)."""
    escolhido = None
    if (procedimento or "").strip():
        escolhido = por_id(procedimento)
        if escolhido is None:
            nomes = ", ".join(p.id for p in PROCEDIMENTOS)
            raise MaestroError(f"não conheço o procedimento “{procedimento}”. Os que existem: {nomes}.")
    return planejar(pedido, registry=registry, procedimento=escolhido)


def texto_do_plano(plano: dict[str, Any]) -> str:
    """O plano em português, com a skill de cada passo e o que falta."""
    linhas = [f"Plano para: {plano['pedido']}", f"Procedimento: {plano['nome']} ({plano['procedimento']})", ""]
    for passo in plano["passos"]:
        marca = " [tem efeito: só com autorização]" if passo["efeito"] else ""
        linhas.append(f"{passo['n']}. {passo['skill']}{marca}")
        linhas.append(f"   por quê: {passo['porque']}")
        if passo["vem_do_passo"]:
            linhas.append("   recebe do passo anterior: " + ", ".join(passo["vem_do_passo"]))
        if passo.get("exigir"):
            linhas.append(f"   só vale se voltar {passo['exigir']}=true")
        if passo["faltando"]:
            linhas.append("   FALTA no pedido: " + ", ".join(passo["faltando"]))
    linhas.append("")
    if plano["precisa_autorizacao"]:
        linhas.append("Um dos passos tem efeito colateral. Nada foi executado: sem autorização, a fila para antes dele.")
    else:
        linhas.append("Nenhum passo tem efeito colateral. Ainda assim, nada foi executado: isto é o plano.")
    if plano.get("limites"):
        linhas.append(f"Limite: {plano['limites']}")
    return "\n".join(linhas)


def texto_da_execucao(resultado: dict[str, Any], *, completo: bool = False) -> str:
    """O que rodou, **o que voltou** e — se parou — onde parou.

    Antes de 0.91.2 isto dizia só “feito”. Um passo que devolveu `lido: false`
    aparecia igualzinho a um que leu de verdade, e a pessoa não tinha como
    saber que o resultado estava vazio sem abrir o JSON.

    `completo=True` (o terminal usa assim) imprime inteiro o texto dos passos
    que declaram `mostrar_texto` — o dossiê é o produto do passo 2, e cortá-lo
    em 160 caracteres entrega nada com aparência de entrega.
    """
    linhas: list[str] = []
    for passo in resultado["passos"]:
        linhas.append(f"{passo['n']}. {passo['skill']} — feito")
        saida = passo.get("saida") or {}
        voltou = _linha_da_saida(saida)
        if voltou:
            linhas.append(f"   voltou: {voltou}")
        documento = str(saida.get("texto") or "")
        if completo and passo.get("mostrar_texto") and documento.strip():
            linhas.append("")
            linhas.append(f"   --- {passo['skill']} (documento completo) ---")
            linhas.extend(f"   {linha}" for linha in documento.splitlines())
            linhas.append(f"   --- fim de {passo['skill']} ---")
            linhas.append("")
    if resultado.get("parou_em"):
        alvo = resultado["passo_que_parou"]
        linhas.append(f"Parei no passo {alvo['n']} ({alvo['skill']}): {resultado['motivo']}")
        dica = (alvo.get("dica") or "").strip()
        if dica:
            linhas.append(f"O que fazer: {dica}")
    else:
        linhas.append(f"Todos os {len(resultado['passos'])} passos rodaram.")
    return "\n".join(linhas)
