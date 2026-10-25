"""Camada de submissão de artefatos para catálogo de skills (0.26.0).

Inspirada no pipeline determinístico do `github/awesome-copilot` (MIT): antes de
qualquer revisão humana, todo envio passa por um portão que confere front
matter, estrutura de pasta, risco no texto, licença e link. Nada é executado,
nada é baixado e nenhum rótulo é aplicado no GitHub: a camada lê o bundle de
arquivos que foi colado e devolve parecer, contagens e veredito.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from .review import common, finalize, finding

VERSAO = "0.37.4"

MAX_TEXTO = 1_800_000
MAX_ARQUIVOS = 300
MAX_ACHADOS = 1_000
MAX_LINHA = 400
MAX_ASSET = 5 * 1024 * 1024
MAX_ROWS = 200
MODOS = ("lite", "full", "ultra")

NOME_MIN, NOME_MAX = 1, 64
DESCRICAO_MIN, DESCRICAO_MAX = 10, 1024
TAG_MIN, TAG_MAX = 1, 30
MAX_TAGS = 10

TIPOS = ("skill", "agent", "instruction", "hook", "plugin", "workflow", "prompt", "desconhecido")
SEVERIDADES_RISCO = ("alto", "medio", "info")
ROTULOS = (
    "awaiting-review",
    "ready-for-review",
    "requires-submitter-fixes",
    "approved",
    "rejected",
)


class SubmissaoError(ValueError):
    """Entrada recusada pela camada de submissão."""


def _modo(valor: str) -> str:
    if valor not in MODOS:
        raise SubmissaoError(f"Modo inválido: {valor}. Use {', '.join(MODOS)}.")
    return valor


def _normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", (texto or "").strip().lower())


def _sem_acento(texto: str) -> str:
    return "".join(
        caractere
        for caractere in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caractere) != "Mn"
    )


def _percentual(parte: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(100.0 * parte / total, 1)


def _fmt_pct(valor: float) -> str:
    return f"{valor:g}%"


def _resumo(valor: Any, limite: int = 90) -> str:
    texto = re.sub(r"\s+", " ", str(valor if valor is not None else "")).strip()
    if len(texto) <= limite:
        return texto or "—"
    return texto[:limite].rstrip() + "…"


def _nome_valido(nome: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", nome or ""))


def _slug(texto: str) -> str:
    """Âncora do GitHub: minúscula, sem formatação, espaço vira hífen."""
    limpo = re.sub(r"`([^`]*)`", r"\1", texto or "")
    limpo = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", limpo)
    limpo = re.sub(r"[*_~]", "", limpo)
    limpo = _sem_acento(limpo).strip().lower()
    limpo = re.sub(r"[^\w\s-]", "", limpo, flags=re.UNICODE)
    limpo = re.sub(r"\s+", "-", limpo)
    return limpo.strip("-")


# --- YAML mínimo ------------------------------------------------------------

RE_CHAVE = re.compile(r"^([A-Za-z0-9_.-]+)\s*:\s*(.*)$")
RE_LISTA_INLINE = re.compile(r"^\[(.*)\]$", re.S)


def _escalar(valor: str) -> Any:
    texto = valor.strip()
    if not texto or texto.startswith("#"):
        return ""
    if texto[0] in "'\"":
        fechamento = texto.find(texto[0], 1)
        if fechamento > 0:
            return texto[1:fechamento]
    sem_comentario = re.split(r"\s+#", texto, maxsplit=1)[0].strip()
    baixo = sem_comentario.lower()
    if baixo in {"true", "yes", "sim"}:
        return True
    if baixo in {"false", "no", "nao", "não"}:
        return False
    if baixo in {"null", "~", "none"}:
        return None
    if re.fullmatch(r"-?\d+", sem_comentario):
        return int(sem_comentario)
    if re.fullmatch(r"-?\d+\.\d+", sem_comentario):
        return float(sem_comentario)
    return sem_comentario


def _dividir_lista(conteudo: str) -> list[str]:
    itens: list[str] = []
    atual = ""
    aspas = ""
    for caractere in conteudo:
        if aspas:
            atual += caractere
            if caractere == aspas:
                aspas = ""
        elif caractere in "'\"":
            aspas = caractere
            atual += caractere
        elif caractere == ",":
            itens.append(atual)
            atual = ""
        else:
            atual += caractere
    if atual.strip():
        itens.append(atual)
    return [item.strip() for item in itens if item.strip()]


def _parse_yaml(linhas: list[str], deslocamento: int = 0) -> tuple[dict[str, Any], list[str]]:
    dados: dict[str, Any] = {}
    problemas: list[str] = []
    pilha: list[tuple[int, dict[str, Any]]] = [(-1, dados)]
    indice = 0
    while indice < len(linhas):
        bruta = linhas[indice]
        numero = indice + deslocamento + 1
        if not bruta.strip() or bruta.strip().startswith("#"):
            indice += 1
            continue
        recuo = len(bruta) - len(bruta.lstrip(" "))
        texto = bruta.strip()
        while len(pilha) > 1 and recuo <= pilha[-1][0]:
            pilha.pop()
        atual = pilha[-1][1]
        if texto.startswith("- "):
            problemas.append(f"linha {numero}: item de lista sem chave")
            indice += 1
            continue
        casado = RE_CHAVE.match(texto)
        if not casado:
            problemas.append(f"linha {numero}: esperado `chave: valor`")
            indice += 1
            continue
        chave, resto = casado.group(1), casado.group(2).strip()
        if chave in atual:
            problemas.append(f"linha {numero}: chave repetida `{chave}`")
        if resto.startswith("|") or resto.startswith(">"):
            partes: list[str] = []
            indice += 1
            while indice < len(linhas):
                seguinte = linhas[indice]
                if seguinte.strip() and (len(seguinte) - len(seguinte.lstrip(" "))) <= recuo:
                    break
                partes.append(seguinte.strip())
                indice += 1
            separador = "\n" if resto.startswith("|") else " "
            atual[chave] = separador.join(partes).strip()
            continue
        if resto == "":
            proximo: int | None = None
            lista = False
            mapa = False
            varredura = indice + 1
            while varredura < len(linhas):
                seguinte = linhas[varredura]
                if not seguinte.strip() or seguinte.strip().startswith("#"):
                    varredura += 1
                    continue
                profundidade = len(seguinte) - len(seguinte.lstrip(" "))
                if profundidade <= recuo:
                    break
                if seguinte.strip().startswith("- "):
                    lista = True
                else:
                    mapa = True
                proximo = varredura
                varredura += 1
            if lista:
                itens: list[Any] = []
                indice += 1
                while indice < len(linhas):
                    seguinte = linhas[indice]
                    if not seguinte.strip() or seguinte.strip().startswith("#"):
                        indice += 1
                        continue
                    profundidade = len(seguinte) - len(seguinte.lstrip(" "))
                    if profundidade <= recuo:
                        break
                    if seguinte.strip().startswith("- "):
                        itens.append(_escalar(seguinte.strip()[2:]))
                    indice += 1
                atual[chave] = itens
                continue
            if mapa or proximo is not None:
                novo: dict[str, Any] = {}
                atual[chave] = novo
                pilha.append((recuo, novo))
                indice += 1
                continue
            atual[chave] = ""
            indice += 1
            continue
        lista_inline = RE_LISTA_INLINE.match(resto)
        if lista_inline:
            atual[chave] = [_escalar(item) for item in _dividir_lista(lista_inline.group(1))]
            indice += 1
            continue
        atual[chave] = _escalar(resto)
        indice += 1
    return dados, problemas


def ler_front_matter(texto: str) -> tuple[dict[str, Any], list[str], str]:
    """Lê o bloco `---` do topo e devolve (dados, problemas, corpo)."""
    if len(texto) > MAX_TEXTO:
        raise SubmissaoError(f"O arquivo passa de {MAX_TEXTO:,} caracteres.")
    linhas = texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not linhas or linhas[0].strip() != "---":
        return {}, ["arquivo sem front matter: o bloco `---` não está na primeira linha"], texto
    fim = None
    for indice in range(1, len(linhas)):
        if linhas[indice].strip() in {"---", "..."}:
            fim = indice
            break
    if fim is None:
        return {}, ["front matter não fechado: falta o `---` de encerramento"], texto
    dados, problemas = _parse_yaml(linhas[1:fim], deslocamento=1)
    corpo = "\n".join(linhas[fim + 1:])
    return dados, problemas, corpo


# --- tipo e campos ----------------------------------------------------------

RE_TIPO: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("skill", re.compile(r"(^|/)skills/[^/]+/SKILL\.md$", re.I)),
    ("agent", re.compile(r"(^|/)agents/[^/]+\.agent\.md$", re.I)),
    ("instruction", re.compile(r"(^|/)instructions/[^/]+\.instructions\.md$", re.I)),
    ("hook", re.compile(r"(^|/)hooks/[^/]+/README\.md$", re.I)),
    ("plugin", re.compile(r"(^|/)plugins/[^/]+/plugin\.json$", re.I)),
    ("workflow", re.compile(r"(^|/)workflows/[^/]+\.md$", re.I)),
    ("prompt", re.compile(r"(^|/)prompts/[^/]+\.prompt\.md$", re.I)),
)


def inferir_tipo(caminho: str) -> str:
    """Deduz o tipo do artefato pelo caminho, como o pipeline do catálogo faz."""
    limpo = caminho.replace("\\", "/").lstrip("./")
    for tipo, padrao in RE_TIPO:
        if padrao.search(limpo):
            return tipo
    nome = limpo.rsplit("/", 1)[-1].lower()
    if nome == "skill.md":
        return "skill"
    if nome.endswith(".agent.md"):
        return "agent"
    if nome.endswith(".instructions.md"):
        return "instruction"
    if nome.endswith(".prompt.md"):
        return "prompt"
    if nome == "plugin.json":
        return "plugin"
    return "desconhecido"


CAMPOS: dict[str, dict[str, list[str]]] = {
    "skill": {"obrigatorios": ["name", "description"], "opcionais": ["license", "version", "allowed-tools", "metadata"]},
    "agent": {"obrigatorios": ["name", "description"], "opcionais": ["model", "tools", "mcp-servers", "title"]},
    "instruction": {"obrigatorios": ["description", "applyTo"], "opcionais": ["title", "tools"]},
    "hook": {"obrigatorios": ["name", "description"], "opcionais": ["tags", "version"]},
    "plugin": {"obrigatorios": ["name", "description", "version", "author"], "opcionais": ["keywords", "license", "repository", "homepage", "$schema", "extensions"]},
    "workflow": {"obrigatorios": ["description"], "opcionais": ["name", "on", "permissions", "tools"]},
    "prompt": {"obrigatorios": ["description"], "opcionais": ["name", "mode", "tools", "model"]},
    "desconhecido": {"obrigatorios": [], "opcionais": []},
}

MODELOS_CONHECIDOS = {
    "gpt-5", "gpt-5-mini", "gpt-4.1", "gpt-4o", "o3", "o4-mini",
    "claude-sonnet-4-6", "claude-sonnet-4", "claude-opus-4-1", "claude-haiku-4-5",
    "gemini-2.5-pro", "gemini-2.5-flash",
}


def _problema_campo(tipo: str, campo: str, valor: Any) -> tuple[str, str] | None:
    """Devolve (situação, mensagem) quando o campo desobedece à regra do tipo."""
    if campo == "name":
        nome = str(valor)
        if tipo == "hook":
            if not 3 <= len(nome.strip()) <= 100:
                return "inválido", "o nome de exibição do hook precisa ter entre 3 e 100 caracteres"
            if re.search(r"[\r\n]", nome):
                return "inválido", "nome de exibição em uma linha só"
            return None
        if not _nome_valido(nome):
            return "inválido", "use só minúsculas, números e hífen simples (`meu-artefato`)"
        if not NOME_MIN <= len(nome) <= NOME_MAX:
            return "inválido", f"o nome precisa ter entre {NOME_MIN} e {NOME_MAX} caracteres"
        return None
    if campo == "description":
        if not isinstance(valor, str):
            return "inválido", "a descrição precisa ser texto"
        if not DESCRICAO_MIN <= len(valor.strip()) <= DESCRICAO_MAX:
            return "inválido", f"a descrição precisa ter entre {DESCRICAO_MIN} e {DESCRICAO_MAX} caracteres"
        if re.search(r"[\r\n]", valor.strip()):
            return "inválido", "quebra de linha na descrição: use uma frase só"
        return None
    if campo == "applyTo":
        if not isinstance(valor, str) or not valor.strip():
            return "inválido", "informe o glob de aplicação, por exemplo `**/*.py`"
        if valor.count("[") != valor.count("]") or valor.count("{") != valor.count("}"):
            return "inválido", "glob desbalanceado em `applyTo`"
        return None
    if campo == "version":
        if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", str(valor)):
            return "inválido", "versão precisa seguir semver (`1.2.3`)"
        return None
    if campo == "author":
        if isinstance(valor, str):
            return "inválido", "use `author.name`; só texto não carrega o autor"
        if isinstance(valor, dict) and not str(valor.get("name", "")).strip():
            return "inválido", "`author.name` é obrigatório"
        if not isinstance(valor, dict):
            return "inválido", "`author` precisa ser um mapa com `name`"
        return None
    if campo == "tools":
        if not isinstance(valor, (list, str)):
            return "inválido", "`tools` precisa ser lista"
        return None
    if campo in {"tags", "keywords"}:
        if not isinstance(valor, list):
            return "inválido", f"`{campo}` precisa ser lista"
        if len(valor) > MAX_TAGS:
            return "inválido", f"no máximo {MAX_TAGS} entradas em `{campo}`"
        for item in valor:
            if not _nome_valido(str(item)):
                return "inválido", f"`{item}` não é tag minúscula com hífen"
            if not TAG_MIN <= len(str(item)) <= TAG_MAX:
                return "inválido", f"`{item}` passa de {TAG_MAX} caracteres"
        return None
    if campo == "model" and str(valor) not in MODELOS_CONHECIDOS:
        return "aviso", "modelo fora da lista conhecida: confira se o host aceita"
    if campo == "repository" and not re.match(r"^https://", str(valor)):
        return "inválido", "`repository` precisa ser URL https"
    return None


def validar_ficha(
    *,
    caminho: str,
    texto: str = "",
    tipo: str = "",
    modo: str = "full",
) -> dict[str, Any]:
    """Lê o front matter de um artefato e confere os campos que o catálogo exige."""
    modo = _modo(modo)
    if tipo and tipo not in TIPOS:
        raise SubmissaoError(f"Tipo inválido: {tipo}. Use {', '.join(TIPOS)}.")
    if len(texto) > MAX_TEXTO:
        raise SubmissaoError(f"O arquivo passa de {MAX_TEXTO:,} caracteres.")
    caminho = (caminho or "").strip()
    if not caminho and not tipo:
        raise SubmissaoError("Informe o caminho do artefato (`skills/meu-skill/SKILL.md`) ou o tipo.")
    if not (texto or "").strip():
        raise SubmissaoError("Informe o conteúdo do arquivo: o front matter não é deduzido do caminho.")
    tipo_real = tipo or inferir_tipo(caminho)

    if tipo_real == "plugin":
        dados, problemas = _ler_json(texto, caminho)
    else:
        dados, problemas, _corpo = ler_front_matter(texto or "")
    especificacao = CAMPOS.get(tipo_real, CAMPOS["desconhecido"])
    obrigatorios = especificacao["obrigatorios"]
    opcionais = especificacao["opcionais"]
    conhecidos = set(obrigatorios) | set(opcionais)

    rows: list[dict[str, Any]] = []
    achados: list[dict[str, Any]] = []
    ausentes: list[str] = []
    invalidos: list[str] = []
    extras: list[str] = []

    for campo in obrigatorios:
        if campo not in dados or dados[campo] in ("", None, []):
            ausentes.append(campo)
            rows.append({"campo": campo, "valor": "—", "situacao": "ausente", "regra": "obrigatório"})
            continue
        problema = _problema_campo(tipo_real, campo, dados[campo])
        if problema and problema[0] == "inválido":
            invalidos.append(campo)
            rows.append({"campo": campo, "valor": _resumo(dados[campo]), "situacao": "inválido", "regra": problema[1]})
            continue
        rows.append({"campo": campo, "valor": _resumo(dados[campo]), "situacao": "ok", "regra": "obrigatório"})

    for campo in opcionais:
        if campo not in dados or dados[campo] in ("", None, []):
            continue
        problema = _problema_campo(tipo_real, campo, dados[campo])
        situacao = "ok" if not problema else ("aviso" if problema[0] == "aviso" else "inválido")
        if situacao == "inválido":
            invalidos.append(campo)
        rows.append({"campo": campo, "valor": _resumo(dados[campo]), "situacao": situacao, "regra": problema[1] if problema else "opcional"})

    for campo in sorted(set(dados) - conhecidos):
        extras.append(campo)
        rows.append({"campo": campo, "valor": _resumo(dados[campo]), "situacao": "extra", "regra": "não é campo deste tipo"})

    if tipo_real in {"skill", "plugin"} and _nome_valido(str(dados.get("name", ""))):
        pasta = caminho.replace("\\", "/").rsplit("/", 2)
        if len(pasta) >= 2 and pasta[-2] != str(dados["name"]):
            achados.append(
                finding(
                    "must",
                    "nome-divergente",
                    "Nome do artefato não bate com a pasta",
                    f"{pasta[-2]}/{pasta[-1]}",
                    f"`name: {dados['name']}` e pasta `{pasta[-2]}` divergem.",
                    "O catálogo indexa pelo nome da pasta: divergência quebra a instalação e o índice.",
                    f"Renomeie a pasta para `{dados['name']}` ou o campo para `{pasta[-2]}`.",
                    "A skill aparece com dois nomes e o usuário instala a errada.",
                )
            )

    if tipo_real == "desconhecido":
        achados.append(
            finding(
                "should",
                "tipo-desconhecido",
                "Caminho fora das pastas do catálogo",
                caminho or "(sem caminho)",
                "O caminho não casa com `skills/`, `agents/`, `instructions/`, `hooks/`, `plugins/`, `workflows/` nem `prompts/`.",
                "Artefato fora da convenção não entra nos índices gerados nem no site.",
                "Mova o arquivo para a pasta do tipo e use a extensão dele.",
                "O envio é aceito no PR, mas não é listado em lugar nenhum.",
            )
        )
    if problemas:
        achados.append(
            finding(
                "must",
                "front-matter-invalido",
                "Front matter não foi lido por inteiro",
                "; ".join(problemas[:3]),
                "O bloco `---` tem linha que não é `chave: valor` ou está sem fechamento.",
                "Front matter quebrado derruba o índice do catálogo inteiro, não só este artefato.",
                "Corrija a linha indicada e confira a indentação dos blocos.",
                "O arquivo entra no repositório e some da lista publicada.",
            )
        )
    if ausentes:
        achados.append(
            finding(
                "must",
                "campo-obrigatorio-ausente",
                f"{len(ausentes)} campo(s) obrigatório(s) ausente(s)",
                ", ".join(ausentes),
                f"O tipo `{tipo_real}` exige {', '.join(obrigatorios)}.",
                "Campo obrigatório é o que o catálogo lê para indexar e para exibir o cartão.",
                "Preencha o campo no front matter antes de abrir o PR.",
                "O validador do repositório recusa o arquivo e o PR fica parado.",
            )
        )
    if invalidos:
        achados.append(
            finding(
                "must",
                "campo-invalido",
                f"{len(invalidos)} campo(s) fora do formato",
                ", ".join(invalidos),
                "O valor existe, mas desobedece à regra do tipo.",
                "Formato fora da regra quebra o índice mesmo com o campo presente.",
                "Siga a regra indicada na coluna de cada campo.",
                "O arquivo é aceito no PR e falha na geração do catálogo.",
            )
        )
    if extras:
        achados.append(
            finding(
                "nice",
                "campo-extra",
                f"{len(extras)} campo(s) fora do esquema",
                ", ".join(extras),
                "O campo não é lido por nenhum consumidor do catálogo.",
                "Campo extra costuma ser typo (`applyto`, `descriptions`) que anula o campo real.",
                "Confira se não é erro de digitação e remova o que não for usado.",
                "Um typo em `applyTo` faz a instrução valer para todo arquivo — ou para nenhum.",
            )
        )
    if modo == "ultra" and dados.get("description") and len(str(dados["description"])) > 500:
        achados.append(
            finding(
                "nice",
                "descricao-longa",
                "Descrição perto do teto",
                f"{len(str(dados['description']))} caracteres",
                "A descrição entra no índice e no cartão de busca.",
                "Descrição longa é cortada na interface e perde o final, que costuma ser o critério.",
                "Leve o critério para o corpo e deixe uma frase na descrição.",
                "O que diferencia o artefato fica fora da tela.",
            )
        )

    findings, counts, veredito, perguntas = finalize(
        achados,
        modo,
        [
            "Quem é o dono deste artefato para aprovar mudança de nome?",
            "O campo extra é typo ou extensão combinada com outro consumidor?",
            "A descrição cabe no cartão de busca do site?",
        ],
    )
    metrics = {
        "campos": len(dados),
        "obrigatorios": len(obrigatorios),
        "ausentes": len(ausentes),
        "invalidos": len(invalidos),
        "extras": len(extras),
        "descricao": len(str(dados.get("description", ""))),
        "tipo_conhecido": 0 if tipo_real == "desconhecido" else 1,
    }
    summary = [
        f"Tipo `{tipo_real}` em `{caminho or '(sem caminho)'}`: {len(dados)} campo(s) lido(s), "
        f"{len(obrigatorios) - len(ausentes)} de {len(obrigatorios)} obrigatório(s) preenchido(s).",
        f"Descrição com {metrics['descricao']} caractere(s); {len(extras)} campo(s) fora do esquema.",
    ]
    limitations = [
        "O leitor de YAML cobre o subconjunto do catálogo: escalar, lista inline, lista em bloco, mapa de um nível e bloco `|`/`>`.",
        "Ancoragem, alias, tag e multi-documento do YAML não são suportados.",
        "A lista de modelos conhecidos é local e não consulta o catálogo do host.",
        "Nada é gravado ou publicado: o front matter é lido do texto colado.",
    ]
    return common(
        analysis="submissao.ficha",
        mode=modo,
        title="Ficha do artefato",
        summary=summary,
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows,
        metrics=metrics,
        limitations=limitations,
    )


def _ler_json(texto: str, caminho: str) -> tuple[dict[str, Any], list[str]]:
    bruto = (texto or "").strip()
    if not bruto:
        return {}, ["arquivo vazio"]
    try:
        dados = json.loads(bruto)
    except json.JSONDecodeError as exc:
        return {}, [f"JSON inválido na linha {exc.lineno}: {exc.msg}"]
    if not isinstance(dados, dict):
        return {}, ["o manifesto precisa ser um objeto JSON"]
    return dados, []


# --- bundle -----------------------------------------------------------------

RE_CABECALHO = re.compile(r"^(?:>>>|===|###)\s+(\S.*?)\s*$")
RE_NOME_DE_ARQUIVO = re.compile(
    r"[\w.-]+\.(md|json|ya?ml|txt|py|sh|bash|ps1|ts|tsx|js|mjs|css|html|png|jpe?g|svg|webp|gif|toml|ini|cfg|m4a|mp3|pdf|zip)$",
    re.I,
)
NOMES_IGNORADOS = {"readme.md", "license", "license.md", "changelog.md", "contributing.md", "index.json"}
SUFIXOS_DE_ENTRADA = (".agent.md", ".instructions.md", ".prompt.md", ".chatmode.md")
NOMES_CANONICOS = {"skill.md", "readme.md", "hooks.json", "plugin.json", "license", "license.md", "changelog.md", "contributing.md"}


def _parece_caminho(valor: str) -> bool:
    """Só trata a linha como cabeçalho quando ela parece um caminho de arquivo."""
    limpo = valor.strip().strip("`").strip('"')
    if not limpo or " " in limpo and "/" not in limpo:
        return False
    return "/" in limpo or bool(RE_NOME_DE_ARQUIVO.fullmatch(limpo.rsplit("/", 1)[-1]))
EXT_SCRIPT = {".sh", ".bash", ".ps1", ".py", ".js", ".mjs", ".ts"}
EXT_BINARIO = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".zip", ".pdf", ".m4a", ".mp3", ".woff2"}


def ler_bundle(texto: str) -> dict[str, str]:
    """Lê o bundle `>>> caminho` (`### caminho` também vale) e devolve caminho -> conteúdo.

    Também aceita um objeto JSON `{"arquivos": {"caminho": "conteúdo"}}`.
    """
    if len(texto or "") > MAX_TEXTO:
        raise SubmissaoError(f"O bundle passa de {MAX_TEXTO:,} caracteres.")
    bruto = (texto or "").strip()
    if not bruto:
        raise SubmissaoError(
            "Informe os arquivos num bundle `>>> caminho/arquivo` seguido do conteúdo, ou num objeto JSON."
        )
    if bruto.startswith("{"):
        try:
            dados = json.loads(bruto)
        except json.JSONDecodeError as exc:
            raise SubmissaoError(f"Bundle JSON inválido na linha {exc.lineno}: {exc.msg}.") from exc
        mapa = dados.get("arquivos") or dados.get("files") if isinstance(dados, dict) else None
        if not isinstance(mapa, dict):
            raise SubmissaoError("O JSON do bundle precisa ter a chave `arquivos` com caminho -> conteúdo.")
        arquivos = {str(_limpar_caminho(chave)): str(valor) for chave, valor in mapa.items()}
    else:
        arquivos: dict[str, str] = {}
        atual: str | None = None
        pedacos: list[str] = []

        def fechar() -> None:
            nonlocal atual, pedacos
            if atual is not None:
                arquivos[atual] = "\n".join(pedacos).strip("\n")
            atual, pedacos = None, []

        for linha in bruto.split("\n"):
            cabecalho = RE_CABECALHO.match(linha)
            if cabecalho and _parece_caminho(cabecalho.group(1)):
                fechar()
                atual = _limpar_caminho(cabecalho.group(1))
                continue
            if atual is not None:
                pedacos.append(linha)
        fechar()
    if not arquivos:
        raise SubmissaoError("Nenhum arquivo reconhecido: cada bloco precisa começar com `>>> caminho`.")
    if len(arquivos) > MAX_ARQUIVOS:
        raise SubmissaoError(f"O bundle tem mais de {MAX_ARQUIVOS:,} arquivos.")
    return arquivos


def _limpar_caminho(caminho: str) -> str:
    limpo = str(caminho or "").strip().strip("`").strip('"').replace("\\", "/")
    while limpo.startswith("./"):
        limpo = limpo[2:]
    return limpo


def _caminhos(entrada: str) -> list[tuple[str, int]]:
    """Lista `caminho [bytes]`, uma por linha; aceita também o bundle inteiro."""
    if len(entrada or "") > MAX_TEXTO:
        raise SubmissaoError(f"A lista passa de {MAX_TEXTO:,} caracteres.")
    bruto = (entrada or "").strip()
    if not bruto:
        raise SubmissaoError("Informe ao menos um caminho de arquivo.")
    primeira = RE_CABECALHO.match(bruto.split("\n", 1)[0])
    if primeira and _parece_caminho(primeira.group(1)):
        return [(caminho, len(conteudo.encode("utf-8"))) for caminho, conteudo in ler_bundle(bruto).items()]
    itens: list[tuple[str, int]] = []
    for linha in bruto.splitlines():
        limpa = linha.strip()
        if not limpa or limpa.startswith("#"):
            continue
        com_tamanho = re.match(r"^(.*\S)\s+(\d+)$", limpa)
        if com_tamanho:
            itens.append((_limpar_caminho(com_tamanho.group(1)), int(com_tamanho.group(2))))
        else:
            itens.append((_limpar_caminho(limpa), 0))
    if not itens:
        raise SubmissaoError("Nenhum caminho reconhecido na lista.")
    if len(itens) > MAX_ARQUIVOS:
        raise SubmissaoError(f"A lista tem mais de {MAX_ARQUIVOS:,} arquivos.")
    return itens


# --- 2. estrutura -----------------------------------------------------------


def _pasta(caminho: str) -> str:
    return caminho.rsplit("/", 1)[0] if "/" in caminho else ""


def _nome(caminho: str) -> str:
    return caminho.rsplit("/", 1)[-1]


def _extensao(caminho: str) -> str:
    nome = _nome(caminho).lower()
    return "." + nome.rsplit(".", 1)[1] if "." in nome else ""


def _pai(caminho: str) -> str:
    partes = caminho.split("/")
    return partes[-2] if len(partes) >= 2 else ""


def _chave_nome(caminho: str) -> str:
    """Nome do artefato, não do arquivo: `skills/x/SKILL.md` e `agents/x.agent.md` são `x`."""
    nome = _nome(caminho).lower()
    if nome in NOMES_IGNORADOS:
        return ""
    if nome in {"skill.md", "plugin.json", "hooks.json"}:
        return _pai(caminho).lower()
    for sufixo in SUFIXOS_DE_ENTRADA:
        if nome.endswith(sufixo):
            return nome[: -len(sufixo)]
    return nome.rsplit(".", 1)[0] if "." in nome else nome


def validar_estrutura(
    *,
    arquivos: str,
    modo: str = "full",
) -> dict[str, Any]:
    """Confere nome, pasta, vizinhos obrigatórios e peso dos assets do envio."""
    modo = _modo(modo)
    itens = _caminhos(arquivos)
    mapa = dict(itens)
    problemas: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []

    ocultos = [
        caminho
        for caminho, _ in itens
        if any(parte.startswith(".") and parte not in {".github", ".", ".."} for parte in caminho.split("/"))
    ]
    absolutos = [caminho for caminho, _ in itens if caminho.startswith("/") or re.match(r"^[A-Za-z]:/", caminho)]
    escapes = [caminho for caminho, _ in itens if ".." in caminho.split("/")]
    vazios = [caminho for caminho, tamanho in itens if tamanho == 0 and _extensao(caminho) in EXT_BINARIO]
    grandes = [(caminho, tamanho) for caminho, tamanho in itens if tamanho > MAX_ASSET]
    maiusculos = [
        caminho
        for caminho, _ in itens
        if _nome(caminho) != _nome(caminho).lower()
        and _nome(caminho).lower() not in NOMES_CANONICOS
        and caminho not in ocultos
        and _extensao(caminho) not in EXT_BINARIO
    ]
    profundos = [caminho for caminho, _ in itens if caminho.count("/") > 4]

    for caminho, tamanho in itens:
        tipo = inferir_tipo(caminho)
        extensao = _extensao(caminho)
        pasta_pai = _pai(caminho)
        observacoes = []
        situacao = "ok"
        if caminho in absolutos:
            situacao, observacoes = "inválido", ["caminho absoluto"]
        elif caminho in escapes:
            situacao, observacoes = "inválido", ["`..` no caminho"]
        elif caminho in ocultos:
            situacao, observacoes = "aviso", ["arquivo oculto"]
        if tipo == "skill" and not _nome_valido(pasta_pai):
            situacao = "inválido"
            observacoes.append(f"pasta `{pasta_pai}` fora do padrão")
        if tipo == "agent" and not _nome_valido(_nome(caminho).removesuffix(".agent.md")):
            situacao = "inválido"
            observacoes.append("nome do agente fora do padrão")
        if tipo == "instruction" and not _nome_valido(_nome(caminho).removesuffix(".instructions.md")):
            situacao = "inválido"
            observacoes.append("nome da instrução fora do padrão")
        if tamanho > MAX_ASSET:
            observacoes.append(f"{tamanho / 1024 / 1024:.1f} MB acima de 5 MB")
            situacao = "inválido" if situacao != "inválido" else situacao
        if extensao in EXT_SCRIPT and tipo in {"skill", "hook"}:
            observacoes.append("script empacotado")
        rows.append(
            {
                "arquivo": caminho,
                "tipo": tipo,
                "extensao": extensao or "—",
                "bytes": tamanho,
                "situacao": situacao,
                "observacao": "; ".join(observacoes) or "—",
            }
        )

    pastas = sorted({_pasta(caminho) for caminho, _ in itens})
    nomes = [chave for chave in map(_chave_nome, (caminho for caminho, _ in itens)) if chave]
    repetidos = sorted({nome for nome in nomes if nomes.count(nome) > 1})

    vizinhos_faltando: list[str] = []
    for caminho, _ in itens:
        tipo = inferir_tipo(caminho)
        pasta = _pasta(caminho)
        if tipo == "hook" and f"{pasta}/hooks.json" not in mapa:
            vizinhos_faltando.append(f"{pasta}/hooks.json")
        if tipo == "plugin" and f"{pasta}/README.md" not in mapa and not mapa.get(f"{pasta}/readme.md"):
            vizinhos_faltando.append(f"{pasta}/README.md")
        if tipo == "skill" and not any(
            outro.startswith(f"{pasta}/") and outro != caminho for outro, _ in itens
        ):
            pass

    if absolutos:
        problemas.append(
            finding(
                "must",
                "caminho-absoluto",
                f"{len(absolutos)} caminho(s) absoluto(s)",
                ", ".join(absolutos[:3]),
                "O caminho começa em `/` ou em unidade do Windows.",
                "Caminho absoluto não existe no repositório de destino: o arquivo cai fora do pacote.",
                "Use caminho relativo à raiz do repositório.",
                "O PR passa e o arquivo nunca é publicado.",
            )
        )
    if escapes:
        problemas.append(
            finding(
                "must",
                "caminho-com-saida",
                f"{len(escapes)} caminho(s) com `..`",
                ", ".join(escapes[:3]),
                "O caminho sobe de diretório.",
                "Caminho que escapa da raiz é recusado pelo validador e é sinal de empacotamento errado.",
                "Reescreva o caminho dentro da pasta do artefato.",
                "O envio inteiro é recusado na validação.",
            )
        )
    if grandes:
        problemas.append(
            finding(
                "must",
                "asset-grande",
                f"{len(grandes)} asset(s) acima de 5 MB",
                ", ".join(f"{caminho} ({tamanho / 1024 / 1024:.1f} MB)" for caminho, tamanho in grandes[:3]),
                f"O teto por asset é {MAX_ASSET // 1024 // 1024} MB.",
                "Asset grande infla o clone do catálogo e o tempo de instalação da skill.",
                "Comprima, hospede fora ou reduza o arquivo antes de enviar.",
                "O validador recusa e o PR não avança.",
            )
        )
    if vizinhos_faltando:
        problemas.append(
            finding(
                "must",
                "vizinho-obrigatorio",
                f"{len(vizinhos_faltando)} arquivo(s) obrigatório(s) faltando",
                ", ".join(sorted(set(vizinhos_faltando))[:4]),
                "Hook precisa de `hooks.json` e plugin precisa de `README.md` na mesma pasta.",
                "Sem o vizinho obrigatório o artefato não é instalável.",
                "Inclua o arquivo no mesmo PR.",
                "O plugin aparece no índice e falha na instalação.",
            )
        )
    if repetidos:
        problemas.append(
            finding(
                "should",
                "nome-repetido",
                f"{len(repetidos)} nome(s) repetido(s) no envio",
                ", ".join(repetidos[:4]),
                "Dois arquivos têm o mesmo nome de arquivo em pastas diferentes.",
                "Índice por nome colide quando dois artefatos compartilham o mesmo nome.",
                "Renomeie um deles com um sufixo que diga o domínio.",
                "Um dos dois some do índice.",
            )
        )
    if ocultos:
        problemas.append(
            finding(
                "should",
                "arquivo-oculto",
                f"{len(ocultos)} arquivo(s) oculto(s) no envio",
                ", ".join(ocultos[:4]),
                "Arquivo ou pasta começa com ponto.",
                "Arquivo oculto costuma ser resíduo de sistema operacional ou configuração local.",
                "Remova o que não faz parte do artefato.",
                "O repositório acumula lixo que ninguém revisa.",
            )
        )
    if maiusculos:
        problemas.append(
            finding(
                "should",
                "caixa-alta",
                f"{len(maiusculos)} arquivo(s) com maiúscula",
                ", ".join(maiusculos[:4]),
                "O catálogo usa nome minúsculo com hífen.",
                "Nome com maiúscula quebra em sistema de arquivo sensível a caixa e aparece duplicado no índice.",
                "Renomeie para minúsculas.",
                "O mesmo artefato aparece duas vezes para quem usa macOS e Linux.",
            )
        )
    if profundos:
        problemas.append(
            finding(
                "nice",
                "pasta-profunda",
                f"{len(profundos)} arquivo(s) com mais de 4 níveis",
                ", ".join(profundos[:3]),
                "Caminho com cinco ou mais níveis de pasta.",
                "Pasta funda esconde o artefato da listagem e dificulta a instalação por nome.",
                "Achate a estrutura para `tipo/nome/arquivo`.",
                "O arquivo existe, mas ninguém acha.",
            )
        )
    if vazios:
        problemas.append(
            finding(
                "nice",
                "binario-vazio",
                f"{len(vazios)} binário(s) de 0 byte",
                ", ".join(vazios[:3]),
                "O arquivo binário foi declarado sem conteúdo.",
                "Asset vazio quebra a prévia e ocupa espaço no índice sem servir para nada.",
                "Remova o arquivo ou envie o conteúdo real.",
                "A página do artefato mostra imagem quebrada.",
            )
        )
    if not itens:
        problemas.append(
            finding(
                "must",
                "sem-arquivos",
                "Nenhum arquivo no envio",
                "lista vazia",
                "Não há caminho para conferir.",
                "Envio sem arquivo não é artefato.",
                "Inclua ao menos o `SKILL.md`, o `.agent.md` ou o `plugin.json`.",
                "O PR não tem o que publicar.",
            )
        )

    findings, counts, veredito, perguntas = finalize(
        problemas,
        modo,
        [
            "A pasta pode ser renomeada sem quebrar link publicado?",
            "Algum asset é gerado em vez de versionado?",
            "O vizinho obrigatório existe em outro PR aberto?",
        ],
    )
    metrics = {
        "arquivos": len(itens),
        "pastas": len(pastas),
        "bytes": sum(tamanho for _, tamanho in itens),
        "grandes": len(grandes),
        "ocultos": len(ocultos),
        "repetidos": len(repetidos),
        "vizinhos": len(set(vizinhos_faltando)),
        "tipos": len({inferir_tipo(caminho) for caminho, _ in itens} - {"desconhecido"}),
    }
    summary = [
        f"{len(itens)} arquivo(s) em {len(pastas)} pasta(s), {metrics['bytes']:,} byte(s) no total.".replace(",", "."),
        f"{metrics['tipos']} tipo(s) de artefato reconhecido(s); {metrics['vizinhos']} vizinho(s) obrigatório(s) faltando.",
    ]
    limitations = [
        "A estrutura é conferida pela lista de caminhos: o conteúdo só entra na conta quando o bundle é colado.",
        "O tamanho vem da lista (`caminho bytes`) ou do conteúdo; arquivo binário colado não tem esse tamanho real.",
        "Não há leitura de git: renomeação e histórico não são reconstruídos.",
        "O teto de 5 MB por asset é o do catálogo de referência, não uma regra universal.",
    ]
    return common(
        analysis="submissao.estrutura",
        mode=modo,
        title="Estrutura do envio",
        summary=summary,
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows[:MAX_ROWS],
        metrics=metrics,
        limitations=limitations,
    )


# --- 3. risco ---------------------------------------------------------------

GRUPO_RISCO = {"alto": "must", "medio": "should", "info": "nice"}


@dataclass
class RegraRisco:
    regra: str
    severidade: str
    motivo: str
    correcao: str
    padrao: re.Pattern[str] | None = None
    avaliador: Any = None
    mascara: bool = False

    def casa(self, linha: str) -> bool:
        if self.padrao is not None and self.padrao.search(linha):
            return True
        if callable(self.avaliador):
            return bool(self.avaliador(linha))
        return False


def _versao_flutuante(linha: str) -> bool:
    limpa = linha.strip()
    if not limpa:
        return False
    if re.search(r"\b(npm|pnpm|yarn|bun|npx|uvx|pip|pipx)\b[^\n]*(?:@latest\b|\blatest\b)", limpa, re.I):
        return True
    if re.search(r"""["'][^"']+["']\s*:\s*["'](?:\^|~|\*|latest\b)[^"']*["']""", limpa, re.I):
        return True
    if re.search(r"\b(?:pip|pip3|uv|uvx|poetry|pdm)\s+install\b[^\n#]*\b[a-z0-9][a-z0-9_.-]*\s*(?:>=|>|~=)\s*\d+(?:\.\d+){0,2}\b(?!\s*,\s*<)", limpa, re.I):
        return True
    if re.fullmatch(r"\s*(?:-\s*)?[a-z0-9][a-z0-9_.-]*(?:\[[A-Za-z0-9_,.-]+\])?\s*(?:>=|>|~=)\s*\d+(?:\.\d+){0,2}\s*(?:#.*)?", limpa, re.I):
        return True
    return False


def _comando_util(linha: str) -> bool:
    return bool(re.search(r"(^|[;&|]\s*)(sudo\s+)?(curl|wget|npm|npx|pnpm|yarn|pip|uv|uvx|python3?|node|bash|sh|rm|git|docker|kubectl|chmod|powershell)\b", linha.strip(), re.I))


def _destrutivo(linha: str) -> bool:
    alvo = linha.strip()
    padroes = (
        r"\brm\s+-[a-z]*[rf][a-z]*\s+(/|~|\$HOME|\*)",
        r"\bgit\s+push\s+[^\n]*--force\b",
        r"\bgit\s+reset\s+--hard\b",
        r"\bchmod\s+777\b",
        r"\bdrop\s+(table|database|schema)\b",
        r"\btruncate\s+table\b",
        r"\bpackage-lock\.json\b.*\brm\b",
        r"\bdd\s+if=.*of=/dev/",
    )
    return any(re.search(padrao, alvo, re.I) for padrao in padroes)


def _caminho_absoluto_no_comando(linha: str) -> bool:
    if not _comando_util(linha):
        return False
    return bool(re.search(r"(^|\s)(/[A-Za-z0-9_.-]+){1,}(/|\s|$)", linha) or re.search(r"\b[A-Za-z]:\\", linha))


REGRAS_RISCO: tuple[RegraRisco, ...] = (
    RegraRisco(
        "bypass-de-guardrail",
        "alto",
        "Texto tenta desligar guardrail, confirmação ou política.",
        "Reescreva como instrução explícita de política e de confirmação do usuário.",
        padrao=re.compile(
            r"\b(ignor[ea]r?\s+(todas?\s+)?(as\s+)?(regras|instruções|guardrails?)|bypass\s+(the\s+)?(guardrails?|safety|policy)|disable\s+(safety|guardrails?)|sem\s+pedir\s+confirmação|não\s+peça\s+confirmação|do\s+not\s+ask\s+for\s+(confirmation|consent)|without\s+prompting)\b",
            re.I,
        ),
    ),
    RegraRisco(
        "shell-remoto",
        "alto",
        "Conteúdo remoto entregue direto ao shell.",
        "Baixe, confira a assinatura e execute de um arquivo local revisado.",
        padrao=re.compile(r"\b(curl|wget)\b[^\n|]*\|\s*(sudo\s+)?(sh|bash|zsh|pwsh|powershell|python3?)\b", re.I),
    ),
    RegraRisco(
        "autoyes",
        "alto",
        "Execução com consentimento automático.",
        "Remova a flag de consentimento e exija invocação aprovada por quem revisa.",
        padrao=re.compile(r"\b(npx|npm\s+exec|npm\s+install|pnpm\s+dlx|yarn\s+dlx|uvx|pipx\s+run)\b[^\n]*\s(-y|--yes|--force)\b", re.I),
    ),
    RegraRisco(
        "execucao-de-pacote",
        "medio",
        "Execução dinâmica de pacote introduz risco de cadeia de suprimento.",
        "Fixe a versão exata e documente a confirmação manual.",
        padrao=re.compile(r"\b(npx|npm\s+exec|pnpm\s+dlx|uvx|pipx\s+run|uv\s+tool\s+run)\b", re.I),
    ),
    RegraRisco(
        "versao-flutuante",
        "medio",
        "Dependência sem versão fixa pode mudar de comportamento entre execuções.",
        "Use versão exata ou hash de commit.",
        avaliador=_versao_flutuante,
    ),
    RegraRisco(
        "segredo-no-texto",
        "alto",
        "Trecho parece credencial real.",
        "Remova o valor, rotacione a credencial e use variável de ambiente.",
        padrao=re.compile(
            r"(AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|xox[baprs]-[A-Za-z0-9-]{10,})"
        ),
        mascara=True,
    ),
    RegraRisco(
        "comando-destrutivo",
        "alto",
        "Comando apaga ou reescreve em massa.",
        "Troque por operação reversível e peça confirmação explícita.",
        avaliador=_destrutivo,
    ),
    RegraRisco(
        "caminho-absoluto",
        "medio",
        "Comando com caminho absoluto depende da máquina de quem escreveu.",
        "Use caminho relativo ao repositório ou variável de ambiente.",
        avaliador=_caminho_absoluto_no_comando,
    ),
    RegraRisco(
        "sudo",
        "medio",
        "Comando exige privilégio elevado.",
        "Documente o requisito e evite `sudo` dentro do artefato.",
        padrao=re.compile(r"(?<![\w-])sudo\s+\S", re.I),
    ),
)

RE_SEGREDO_MASCARA = re.compile(r"(AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,})")


def _mascarar(trecho: str) -> str:
    return RE_SEGREDO_MASCARA.sub(lambda m: m.group(1)[:4] + "***", trecho)


def _varrer_arquivo(caminho: str, conteudo: str) -> list[dict[str, Any]]:
    achados: list[dict[str, Any]] = []
    for numero, linha in enumerate(conteudo.split("\n"), start=1):
        if len(linha) > MAX_LINHA * 4:
            linha = linha[: MAX_LINHA * 4]
        for regra in REGRAS_RISCO:
            if not regra.casa(linha):
                continue
            trecho = linha.strip()[:180]
            if regra.mascara:
                trecho = _mascarar(trecho)
            achados.append(
                {
                    "arquivo": caminho,
                    "linha": numero,
                    "regra": regra.regra,
                    "severidade": regra.severidade,
                    "trecho": trecho or "—",
                    "motivo": regra.motivo,
                }
            )
            if len(achados) >= MAX_ACHADOS:
                return achados
    return achados


def varrer_risco(*, arquivos: str, max_achados: int = 100, modo: str = "full") -> dict[str, Any]:
    """Varre o texto do envio atrás de guardrail desligado, shell remoto, segredo e afins."""
    modo = _modo(modo)
    if max_achados < 1 or max_achados > MAX_ACHADOS:
        raise SubmissaoError(f"O limite de achados precisa estar entre 1 e {MAX_ACHADOS:,}.")
    bruto = (arquivos or "").strip()
    if not bruto:
        raise SubmissaoError("Informe os arquivos em bundle `>>> caminho` ou em lista de caminhos.")
    conteudos: dict[str, str]
    primeira = RE_CABECALHO.match(bruto.split("\n", 1)[0])
    if (primeira and _parece_caminho(primeira.group(1))) or bruto.startswith("{"):
        conteudos = ler_bundle(bruto)
        caminhos = [(caminho, len(conteudo.encode("utf-8"))) for caminho, conteudo in conteudos.items()]
    else:
        caminhos = _caminhos(bruto)
        conteudos = {}

    achados: list[dict[str, Any]] = []
    for caminho, _tamanho in caminhos:
        achados.extend(_varrer_arquivo(caminho, conteudos.get(caminho, "")))
        if len(achados) >= MAX_ACHADOS:
            break
    achados = achados[:max_achados]

    por_regra: dict[str, int] = {}
    por_severidade = {sev: 0 for sev in SEVERIDADES_RISCO}
    for item in achados:
        por_regra[item["regra"]] = por_regra.get(item["regra"], 0) + 1
        por_severidade[item["severidade"]] = por_severidade.get(item["severidade"], 0) + 1

    scripts = [caminho for caminho, _ in caminhos if _extensao(caminho) in EXT_SCRIPT]
    binarios = [caminho for caminho, _ in caminhos if _extensao(caminho) in EXT_BINARIO]

    problemas: list[dict[str, Any]] = []
    altos = [item for item in achados if item["severidade"] == "alto"]
    medios = [item for item in achados if item["severidade"] == "medio"]
    if altos:
        problemas.append(
            finding(
                "must",
                f"risco-{altos[0]['regra']}",
                f"{len(altos)} achado(s) de risco alto",
                ", ".join(f"{item['arquivo']}:{item['linha']}" for item in altos[:4]),
                "; ".join(sorted({item["regra"] for item in altos}))[:180],
                "Risco alto no envio é o que o portão existe para barrar antes da revisão humana.",
                "Corrija ou justifique no PR cada ocorrência, começando pela regra mais frequente.",
                "O artefato entra no catálogo com instrução insegura para quem instalar.",
            )
        )
    if medios:
        problemas.append(
            finding(
                "should",
                "risco-medio",
                f"{len(medios)} achado(s) de risco médio",
                "; ".join(sorted({item["regra"] for item in medios}))[:160],
                "Execução de pacote, versão flutuante ou caminho absoluto no texto.",
                "Risco médio não bloqueia sozinho, mas é o que mais aparece em retrabalho de PR.",
                "Fixe versão e troque caminho absoluto por relativo.",
                "O artefato quebra na máquina de outra pessoa.",
            )
        )
    if scripts and any(inferir_tipo(caminho) == "skill" for caminho, _ in caminhos):
        problemas.append(
            finding(
                "nice",
                "script-empacotado",
                f"{len(scripts)} script(s) no pacote",
                ", ".join(scripts[:4]),
                "Script dentro da pasta da skill depende de runtime externo.",
                "Script empacotado é o ponto do pacote em que dependência implícita aparece.",
                "Documente dependências fixas e evite instalação de rede no meio da execução.",
                "A skill instala e falha no primeiro uso.",
            )
        )
    if binarios:
        problemas.append(
            finding(
                "nice",
                "binario-no-envio",
                f"{len(binarios)} binário(s) no envio",
                ", ".join(binarios[:4]),
                "Arquivo binário não é revisável linha a linha.",
                "Binário entra sem revisão de conteúdo e é o vetor mais direto de asset inesperado.",
                "Confira origem e licença do binário; prefira gerar a partir de fonte versionada.",
                "O binário muda sem ninguém conseguir revisar.",
            )
        )
    if not conteudos and not achados:
        problemas.append(
            finding(
                "should",
                "sem-conteudo",
                "Só caminhos, sem conteúdo para varrer",
                f"{len(caminhos)} caminho(s)",
                "Sem o texto dos arquivos, a varredura de linha não roda.",
                "Envio sem conteúdo passa no portão de risco por omissão, não por limpeza.",
                "Cole o bundle com `>>> caminho` e o conteúdo.",
                "O portão aprova sem ter lido nada.",
            )
        )
    if not achados and conteudos:
        problemas.append(
            finding(
                "nice",
                "risco-limpo",
                "Nenhum padrão de risco no texto",
                f"{len(conteudos)} arquivo(s) varrido(s)",
                "Nenhuma regra de linha casou.",
                "Limpo aqui não quer dizer seguro: a varredura é lexical.",
                "Mantenha a revisão humana do conteúdo.",
                "O selo de limpo pode dar confiança indevida.",
            )
        )

    findings, counts, veredito, perguntas = finalize(
        problemas,
        modo,
        [
            "Quem revisa o script empacotado antes do merge?",
            "Algum achado de risco alto é falso positivo por exemplo didático?",
            "A versão flutuante é intencional para acompanhar a última release?",
        ],
    )
    rows = achados[:max_achados]
    metrics = {
        "arquivos": len(caminhos),
        "varridos": len(conteudos),
        "linhas": sum(len(conteudo.split("\n")) for conteudo in conteudos.values()),
        "achados": len(achados),
        "altos": por_severidade["alto"],
        "medios": por_severidade["medio"],
        "infos": por_severidade["info"],
        "regras": len(por_regra),
        "scripts": len(scripts),
        "binarios": len(binarios),
    }
    summary = [
        f"{metrics['arquivos']} arquivo(s), {metrics['linhas']} linha(s) varrida(s): "
        f"{por_severidade['alto']} risco(s) alto, {por_severidade['medio']} médio(s) e "
        f"{por_severidade['info']} informativo(s).",
        f"{len(por_regra)} regra(s) casaram de {len(REGRAS_RISCO)} disponíveis.",
    ]
    limitations = [
        "A varredura é lexical, linha a linha: ofuscação, texto em imagem e payload codificado não são detectados.",
        "O conteúdo entre blocos não é interpretado: markdown, YAML e código recebem as mesmas regras.",
        "Segredo encontrado aparece mascarado no parecer; o valor real não é reproduzido.",
        "Exemplo didático que cita `curl | sh` é indistinguível de instrução real.",
    ]
    return common(
        analysis="submissao.risco",
        mode=modo,
        title="Risco do envio",
        summary=summary,
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows,
        metrics=metrics,
        limitations=limitations,
    )


# --- 4. licença -------------------------------------------------------------

SPDX_IDS = {
    "0BSD", "AFL-3.0", "AGPL-3.0", "AGPL-3.0-only", "AGPL-3.0-or-later", "Apache-1.1", "Apache-2.0",
    "Artistic-2.0", "BSD-2-Clause", "BSD-3-Clause", "BSL-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "CC0-1.0",
    "CDDL-1.0", "ECL-2.0", "EPL-1.0", "EPL-2.0", "EUPL-1.2", "GPL-2.0", "GPL-2.0-only", "GPL-2.0-or-later",
    "GPL-3.0", "GPL-3.0-only", "GPL-3.0-or-later", "ISC", "LGPL-2.1", "LGPL-2.1-only", "LGPL-2.1-or-later",
    "LGPL-3.0", "LGPL-3.0-only", "LGPL-3.0-or-later", "MIT", "MPL-2.0", "MS-PL", "NCSA", "OFL-1.1",
    "OSL-3.0", "PostgreSQL", "Python-2.0", "Ruby", "Unlicense", "UPL-1.0", "WTFPL", "Zlib",
}
SPDX_EXCECOES = {
    "Classpath-exception-2.0", "GCC-exception-3.1", "LLVM-exception", "Autoconf-exception-3.0",
    "Bison-exception-2.2", "Font-exception-2.0", "GPL-3.0-linking-exception", "Linux-syscall-note",
    "OpenSSL-exception", "Qt-GPL-exception-1.0",
}
OPERADORES = {"AND", "OR", "WITH"}
COPYLEFT = {"AGPL", "GPL", "LGPL", "MPL", "EPL", "EUPL", "OSL", "CC-BY-SA", "CDDL"}
RE_SPDX_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+-]*$")

ALIASES_LICENCA = {
    "mit license": "MIT",
    "the mit license": "MIT",
    "apache 2": "Apache-2.0",
    "apache 2.0": "Apache-2.0",
    "apache-2": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "bsd": "BSD-3-Clause",
    "bsd 3": "BSD-3-Clause",
    "bsd-3": "BSD-3-Clause",
    "isc license": "ISC",
    "gplv2": "GPL-2.0-only",
    "gplv3": "GPL-3.0-only",
    "gpl-3": "GPL-3.0-only",
    "agplv3": "AGPL-3.0-only",
    "lgplv3": "LGPL-3.0-only",
    "mpl 2.0": "MPL-2.0",
    "mpl-2": "MPL-2.0",
    "unlicensed": "Unlicense",
    "public domain": "Unlicense",
}


@dataclass
class ExpressaoLicenca:
    valida: bool
    motivos: list[str] = field(default_factory=list)
    tokens: list[tuple[str, str]] = field(default_factory=list)
    desconhecidos: list[str] = field(default_factory=list)
    ids: list[str] = field(default_factory=list)


def _tokenizar_licenca(licenca: str) -> list[str]:
    return [token for token in re.sub(r"([()])", r" \1 ", licenca).split() if token]


def _token_reconhecido(token: str) -> str:
    """Devolve `id`, `excecao`, `referencia` ou `desconhecido`."""
    base = token[:-1] if token.endswith("+") else token
    if base.startswith("LicenseRef-") and RE_SPDX_TOKEN.match(base[len("LicenseRef-"):]):
        return "referencia"
    if base.startswith("DocumentRef-") and ":LicenseRef-" in base:
        documento, referencia = base[len("DocumentRef-"):].split(":LicenseRef-", 1)
        if RE_SPDX_TOKEN.match(documento) and RE_SPDX_TOKEN.match(referencia):
            return "referencia"
    if base in SPDX_EXCECOES:
        return "excecao"
    if base in SPDX_IDS:
        return "id"
    return "desconhecido"


def ler_expressao_licenca(licenca: str) -> ExpressaoLicenca:
    """Parser SPDX: id, exceção, `+`, `AND`, `OR`, `WITH` e parênteses."""
    texto = (licenca or "").strip()
    resultado = ExpressaoLicenca(valida=False)
    if not texto:
        resultado.motivos.append("licença vazia")
        return resultado
    tokens = _tokenizar_licenca(texto)
    posicao = 0

    def espiar() -> str | None:
        return tokens[posicao] if posicao < len(tokens) else None

    def consumir() -> str:
        nonlocal posicao
        token = tokens[posicao]
        posicao += 1
        resultado.tokens.append((token, token))
        return token

    def primario() -> bool:
        token = espiar()
        if token == "(":
            consumir()
            if not ou_expressao():
                return False
            if espiar() != ")":
                resultado.motivos.append("parêntese não fechado")
                return False
            consumir()
            return True
        if not token or token in {")"} or token.upper() in OPERADORES:
            return False
        consumir()
        tipo = _token_reconhecido(token)
        base = token[:-1] if token.endswith("+") else token
        if tipo == "desconhecido":
            resultado.desconhecidos.append(token)
            return True
        if tipo in {"id", "referencia"}:
            resultado.ids.append(base)
        return True

    def simples() -> bool:
        token = espiar()
        if not token or token == ")" or token.upper() in OPERADORES:
            return False
        consumir()
        tipo = _token_reconhecido(token)
        if tipo == "excecao":
            resultado.motivos.append(f"`{token}` é exceção e só vale depois de `WITH`")
            return False
        if tipo == "desconhecido":
            resultado.desconhecidos.append(token)
        else:
            resultado.ids.append(token[:-1] if token.endswith("+") else token)
        return True

    def com_excecao() -> bool:
        if espiar() == "(":
            return primario() and (espiar() or "").upper() != "WITH"
        if not simples():
            return False
        if (espiar() or "").upper() != "WITH":
            return True
        consumir()
        token = espiar()
        if not token or token == ")" or token.upper() in OPERADORES:
            resultado.motivos.append("`WITH` sem exceção")
            return False
        consumir()
        if _token_reconhecido(token) != "excecao":
            resultado.motivos.append(f"`{token}` não é exceção SPDX conhecida")
        return True

    def e_expressao() -> bool:
        if not com_excecao():
            return False
        while (espiar() or "").upper() == "AND":
            consumir()
            if not com_excecao():
                return False
        return True

    def ou_expressao() -> bool:
        if not e_expressao():
            return False
        while (espiar() or "").upper() == "OR":
            consumir()
            if not e_expressao():
                return False
        return True

    try:
        resultado.valida = ou_expressao() and posicao == len(tokens)
    except (IndexError, ValueError):
        resultado.valida = False
    if not resultado.valida and not resultado.motivos:
        resultado.motivos.append("expressão SPDX malformada")
    return resultado


def _copyleft(ids: list[str]) -> list[str]:
    return sorted({ident for ident in ids if any(ident.upper().startswith(prefixo.upper()) for prefixo in COPYLEFT)})


def analisar_licenca(
    *,
    licenca: str,
    esperada: str = "MIT",
    obrigatoria: bool = False,
    modo: str = "full",
) -> dict[str, Any]:
    """Confere a licença como expressão SPDX e compara com a política do catálogo."""
    modo = _modo(modo)
    if len(licenca or "") > 500:
        raise SubmissaoError("A licença passa de 500 caracteres.")
    texto = (licenca or "").strip()
    esperada_limpa = (esperada or "").strip()
    if esperada_limpa and not ler_expressao_licenca(esperada_limpa).valida:
        raise SubmissaoError(f"Licença esperada inválida: {esperada_limpa}. Use um identificador SPDX.")

    expressao = ler_expressao_licenca(texto)
    normalizada = ALIASES_LICENCA.get(_normalizar(texto).removesuffix(" license").strip(), "")
    if not normalizada:
        normalizada = ALIASES_LICENCA.get(_normalizar(texto), "")
    efetiva = normalizada or texto

    rows = [
        {
            "token": token,
            "tipo": "operador" if token.upper() in OPERADORES else ("parêntese" if token in {"(", ")"} else _token_reconhecido(token)),
            "reconhecido": "sim" if token.upper() in OPERADORES or token in {"(", ")"} or _token_reconhecido(token) != "desconhecido" else "não",
            "sugestao": ALIASES_LICENCA.get(_normalizar(token), ""),
        }
        for token, _ in expressao.tokens
    ]
    copyleft = _copyleft(expressao.ids)
    problemas: list[dict[str, Any]] = []

    if not texto:
        if obrigatoria:
            problemas.append(
                finding(
                    "must",
                    "licenca-ausente",
                    "Licença ausente",
                    "campo vazio",
                    "O manifesto não declara licença e a política exige uma.",
                    "Sem licença, ninguém pode redistribuir o artefato com segurança jurídica.",
                    "Declare um identificador SPDX (`MIT`, `Apache-2.0`, …) no campo `license`.",
                    "O catálogo publica conteúdo sem direito claro de uso.",
                )
            )
        else:
            problemas.append(
                finding(
                    "should",
                    "licenca-ausente",
                    "Licença não declarada",
                    "campo vazio",
                    "O artefato não diz sob qual licença é distribuído.",
                    "Licença implícita é a origem mais comum de disputa em catálogo comunitário.",
                    "Declare um identificador SPDX no campo `license`.",
                    "Quem instala não sabe o que pode fazer com o conteúdo.",
                )
            )
    elif not expressao.valida:
        problemas.append(
            finding(
                "must",
                "licenca-malformada",
                "Licença fora do padrão SPDX",
                _resumo(texto, 60),
                "; ".join(expressao.motivos[:3]) or "expressão não reconhecida",
                "`GPLv3`, `MIT License` e `Apache 2.0` não são identificadores SPDX e quebram a leitura automática.",
                f"Use o identificador canônico{(' — por exemplo `' + normalizada + '`') if normalizada else ''}.",
                "Ferramenta de conformidade lê a licença como desconhecida.",
            )
        )
    elif expressao.desconhecidos:
        problemas.append(
            finding(
                "should",
                "licenca-desconhecida",
                f"{len(expressao.desconhecidos)} identificador(es) fora da lista",
                ", ".join(expressao.desconhecidos[:4]),
                "A expressão é válida, mas o identificador não está na lista local de SPDX.",
                "Identificador não reconhecido aqui pode ser válido no registro SPDX completo.",
                "Confira em spdx.org/licenses e mantenha o identificador oficial.",
                "A leitura automática marca a licença como suspeita.",
            )
        )
    if expressao.valida and copyleft:
        problemas.append(
            finding(
                "should",
                "licenca-copyleft",
                f"{len(copyleft)} licença(s) com copyleft",
                ", ".join(copyleft),
                "O catálogo distribui o conteúdo sob licença permissiva.",
                "Conteúdo copyleft exige aviso próprio e não pode ser relicenciado como MIT.",
                "Inclua o texto da licença no pacote e registre a exceção no PR.",
                "O repositório passa a distribuir conteúdo em condição que não pode cumprir.",
            )
        )
    if esperada_limpa and texto and expressao.valida and not normalizada and texto != esperada_limpa:
        problemas.append(
            finding(
                "should",
                "licenca-divergente",
                "Licença diferente da esperada",
                f"{_resumo(texto, 40)} ≠ {esperada_limpa}",
                "O campo não bate com a licença declarada pela política do catálogo.",
                "Divergência impede a checagem automática de compatibilidade.",
                f"Use `{esperada_limpa}` ou registre a exceção no PR.",
                "A conformidade é conferida à mão em todo envio.",
            )
        )
    if normalizada and normalizada != texto:
        problemas.append(
            finding(
                "should",
                "licenca-alias",
                "Licença escrita como texto livre",
                f"{_resumo(texto, 40)} → {normalizada}",
                "O valor é reconhecível, mas não é o identificador SPDX.",
                "Alias resolve na leitura humana e falha na automação.",
                f"Troque por `{normalizada}`.",
                "Ferramenta de conformidade não reconhece o campo.",
            )
        )
    if not texto and not obrigatoria:
        pass

    findings, counts, veredito, perguntas = finalize(
        problemas,
        modo,
        [
            "A política do catálogo aceita copyleft com aviso próprio?",
            "Quem confere a licença do conteúdo de terceiro que o artefato embarca?",
            "O identificador é o oficial ou um alias que a ferramenta não lê?",
        ],
    )
    metrics = {
        "caracteres": len(texto),
        "tokens": len(expressao.tokens),
        "ids": len(expressao.ids),
        "operadores": sum(1 for token, _ in expressao.tokens if token.upper() in OPERADORES),
        "excecoes": sum(1 for token, _ in expressao.tokens if _token_reconhecido(token) == "excecao"),
        "desconhecidos": len(expressao.desconhecidos),
        "valida": 1 if expressao.valida else 0,
        "copyleft": len(copyleft),
        "normalizada": 1 if normalizada and normalizada != texto else 0,
    }
    summary = [
        f"`{_resumo(efetiva, 60)}`: expressão {'válida' if expressao.valida else 'inválida'} "
        f"com {len(expressao.ids)} identificador(es) e {metrics['operadores']} operador(es).",
        f"Política esperada: `{esperada_limpa or '(não definida)'}`"
        + (f"; copyleft em {', '.join(copyleft)}." if copyleft else "; nenhum copyleft."),
    ]
    limitations = [
        "A lista de identificadores SPDX é local e parcial: identificador ausente vira aviso, não erro.",
        "O parser valida a forma da expressão, não a compatibilidade jurídica entre as licenças.",
        "O texto integral da licença não é lido: só o identificador declarado.",
        "Alias conhecido é sugerido, nunca aplicado sozinho.",
    ]
    return common(
        analysis="submissao.licenca",
        mode=modo,
        title="Licença do artefato",
        summary=summary,
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows,
        metrics=metrics,
        limitations=limitations,
    )


# --- 5. links ---------------------------------------------------------------

RE_TITULO = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
RE_LINK = re.compile(r"(!?\[([^\]]*)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\))")
RE_DEFINICAO = re.compile(r"^\s{0,3}\[([^\]]+)\]:\s*<?(\S+)>?")
RE_HTML = re.compile(r"""\b(?:href|src)\s*=\s*["']([^"']+)["']""", re.I)
RE_ESQUEMA = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
TEXTO_GENERICO = {
    "clique aqui", "click here", "aqui", "here", "saiba mais", "leia mais", "read more",
    "more", "link", "este link", "this link", "veja", "see here",
}


def _titulos(conteudo: str) -> list[str]:
    titulos: list[str] = []
    for linha in conteudo.split("\n"):
        casado = RE_TITULO.match(linha)
        if casado:
            titulos.append(_slug(casado.group(2)))
    return titulos


def _ancoras(conteudo: str) -> set[str]:
    vistos: dict[str, int] = {}
    ancoras: set[str] = set()
    for base in _titulos(conteudo):
        if base in vistos:
            vistos[base] += 1
            ancoras.add(f"{base}-{vistos[base]}")
        else:
            vistos[base] = 0
            ancoras.add(base)
    return ancoras


RE_CERCA = re.compile(r"^\s{0,3}(```+|~~~+)")
RE_CODIGO = re.compile(r"`[^`]*`")


def _sem_codigo(conteudo: str) -> list[tuple[int, str]]:
    """Devolve (linha, texto) sem bloco cercado nem trecho em crase: código não é link."""
    saida: list[tuple[int, str]] = []
    cerca = ""
    for numero, linha in enumerate(conteudo.split("\n"), start=1):
        achado = RE_CERCA.match(linha)
        if achado:
            marca = achado.group(1)
            if not cerca:
                cerca = marca[0] * 3
                continue
            if marca.startswith(cerca):
                cerca = ""
                continue
        if cerca:
            continue
        saida.append((numero, RE_CODIGO.sub(lambda m: " " * len(m.group(0)), linha)))
    return saida


def _ocorrencias(conteudo: str) -> list[tuple[int, str, str]]:
    """Devolve (linha, texto, destino) de cada link do arquivo."""
    itens: list[tuple[int, str, str]] = []
    for numero, linha in _sem_codigo(conteudo):
        if numero > 5_000:
            break
        for casado in RE_LINK.finditer(linha):
            itens.append((numero, casado.group(2).strip(), casado.group(3).strip()))
        definicao = RE_DEFINICAO.match(linha)
        if definicao:
            itens.append((numero, definicao.group(1).strip(), definicao.group(2).strip()))
        if "<" in linha:
            for casado in RE_HTML.finditer(linha):
                itens.append((numero, "", casado.group(1).strip()))
    return itens


def conferir_links(*, arquivos: str, modo: str = "full") -> dict[str, Any]:
    """Confere link relativo, âncora de título e arquivo referenciado do envio."""
    modo = _modo(modo)
    bruto = (arquivos or "").strip()
    if not bruto:
        raise SubmissaoError("Informe os arquivos em bundle `>>> caminho` com o conteúdo.")
    primeira = RE_CABECALHO.match(bruto.split("\n", 1)[0])
    if (primeira and _parece_caminho(primeira.group(1))) or bruto.startswith("{"):
        conteudos = ler_bundle(bruto)
    else:
        raise SubmissaoError("Informe o bundle com `>>> caminho` (ou `### caminho`) e o conteúdo: link e âncora não são conferidos só pelo nome.")

    existentes = set(conteudos)
    minusculos = {caminho.lower(): caminho for caminho in existentes}
    ancoras = {caminho: _ancoras(conteudo) for caminho, conteudo in conteudos.items()}
    rows: list[dict[str, Any]] = []
    contagem = {"ok": 0, "arquivo-ausente": 0, "ancora-ausente": 0, "saida": 0, "absoluto": 0, "caixa": 0, "texto-generico": 0, "inseguro": 0}
    usados: set[str] = set()

    for caminho, conteudo in conteudos.items():
        pasta = _pasta(caminho)
        for numero, texto, destino in _ocorrencias(conteudo):
            if not destino:
                continue
            alvo, _, ancora = destino.partition("#")
            situacao = "ok"
            sugestao = ""
            if alvo.lower().startswith("https://"):
                contagem["ok"] += 1
                continue
            if alvo.lower().startswith("http://"):
                situacao = "inseguro"
                sugestao = alvo.replace("http://", "https://", 1)
            elif RE_ESQUEMA.match(alvo):
                contagem["ok"] += 1
                continue
            elif alvo.startswith("/"):
                situacao = "absoluto"
                sugestao = "use caminho relativo"
            elif alvo:
                alvo_limpo = _limpar_caminho(alvo)
                resolvido = alvo_limpo if alvo_limpo in existentes else "/".join(parte for parte in f"{pasta}/{alvo_limpo}".split("/") if parte)
                if ".." in alvo_limpo.split("/"):
                    situacao = "saida"
                    sugestao = "caminho sobe de diretório"
                elif resolvido in existentes:
                    usados.add(resolvido)
                    if ancora and resolvido in ancoras and ancora.lower() not in ancoras[resolvido]:
                        situacao = "ancora-ausente"
                        sugestao = next(iter(sorted(ancoras[resolvido])), "sem título no destino")
                elif resolvido.lower() in minusculos:
                    situacao = "caixa"
                    usados.add(minusculos[resolvido.lower()])
                    sugestao = minusculos[resolvido.lower()]
                elif alvo_limpo.startswith("#"):
                    situacao = "ancora-ausente"
                else:
                    situacao = "arquivo-ausente"
                    sugestao = "arquivo não está no envio"
            elif ancora:
                if conteudo and ancora.lower() not in ancoras[caminho]:
                    situacao = "ancora-ausente"
                    sugestao = f"âncoras: {', '.join(sorted(ancoras[caminho])[:3]) or 'nenhum título'}"
                else:
                    situacao = "ok"
            generico = bool(texto) and _normalizar(texto) in TEXTO_GENERICO
            if situacao == "ok" and generico:
                situacao = "texto-generico"
                sugestao = "descreva o destino no texto do link"
            contagem[situacao] = contagem.get(situacao, 0) + 1
            rows.append(
                {
                    "arquivo": caminho,
                    "linha": numero,
                    "texto": _resumo(texto, 40) if texto else "—",
                    "destino": _resumo(destino, 70),
                    "situacao": situacao,
                    "sugestao": sugestao or "—",
                    "generico": "sim" if generico else "não",
                }
            )

    orfaos = sorted(
        caminho
        for caminho in existentes
        if caminho not in usados
        and _extensao(caminho) not in {".md", ".json"}
        and any(parte in caminho.split("/")[:-1] for parte in {"skills", "hooks", "plugins", "agents", "instructions"})
    )

    problemas: list[dict[str, Any]] = []
    ausentes = [row for row in rows if row["situacao"] == "arquivo-ausente"]
    saidas = [row for row in rows if row["situacao"] == "saida"]
    ancoras_quebradas = [row for row in rows if row["situacao"] == "ancora-ausente"]
    caixa = [row for row in rows if row["situacao"] == "caixa"]
    absolutos = [row for row in rows if row["situacao"] == "absoluto"]
    inseguros = [row for row in rows if row["situacao"] == "inseguro"]
    genericos = [row for row in rows if row.get("generico") == "sim"]

    if ausentes:
        problemas.append(
            finding(
                "must",
                "link-quebrado",
                f"{len(ausentes)} link(s) para arquivo fora do envio",
                ", ".join(f"{row['arquivo']}:{row['linha']}" for row in ausentes[:4]),
                "O destino é relativo e não existe entre os arquivos colados.",
                "Link quebrado é o defeito mais visível de um README de catálogo.",
                "Inclua o arquivo no PR ou corrija o caminho.",
                "A página do artefato mostra link morto.",
            )
        )
    if saidas:
        problemas.append(
            finding(
                "must",
                "link-escapa",
                f"{len(saidas)} link(s) com `..`",
                ", ".join(f"{row['arquivo']}:{row['linha']}" for row in saidas[:3]),
                "O destino sobe de diretório e sai do pacote do artefato.",
                "Link que escapa da pasta quebra na instalação, porque o alvo não é copiado junto.",
                "Mova o alvo para dentro da pasta do artefato.",
                "O link funciona no repositório e falha em quem instalou.",
            )
        )
    if ancoras_quebradas:
        problemas.append(
            finding(
                "should",
                "ancora-quebrada",
                f"{len(ancoras_quebradas)} âncora(s) sem título correspondente",
                ", ".join(f"{row['arquivo']}:{row['linha']} → {row['destino']}" for row in ancoras_quebradas[:3]),
                "O `#trecho` do link não casa com nenhum título do destino.",
                "A âncora do GitHub deriva do título: título renomeado quebra todo link que apontava para ele.",
                "Aponte para o título atual ou atualize o link.",
                "O leitor cai no topo do arquivo e não encontra o trecho.",
            )
        )
    if caixa:
        problemas.append(
            finding(
                "should",
                "caixa-do-caminho",
                f"{len(caixa)} link(s) com caixa diferente",
                ", ".join(f"{row['destino']} → {row['sugestao']}" for row in caixa[:3]),
                "O caminho existe, mas com outra combinação de maiúsculas.",
                "Funciona em macOS e quebra em Linux, onde o sistema de arquivos diferencia caixa.",
                "Copie o nome exato do arquivo.",
                "O link passa na máquina de quem escreveu e falha na CI.",
            )
        )
    if absolutos:
        problemas.append(
            finding(
                "should",
                "link-absoluto",
                f"{len(absolutos)} link(s) absoluto(s)",
                ", ".join(f"{row['arquivo']}:{row['linha']}" for row in absolutos[:3]),
                "O destino começa em `/`.",
                "Caminho absoluto só resolve no site do catálogo, não no pacote instalado.",
                "Use caminho relativo ao arquivo.",
                "O link funciona no site e quebra fora dele.",
            )
        )
    if inseguros:
        problemas.append(
            finding(
                "nice",
                "link-inseguro",
                f"{len(inseguros)} link(s) `http://`",
                ", ".join(row["destino"] for row in inseguros[:3]),
                "O destino usa HTTP sem TLS.",
                "Endereço sem TLS é interceptável e o host pode ter migrado para HTTPS.",
                "Troque para `https://`.",
                "O leitor é levado a uma versão insegura do mesmo site.",
            )
        )
    if genericos:
        problemas.append(
            finding(
                "nice",
                "texto-de-link-generico",
                f"{len(genericos)} link(s) com texto genérico",
                ", ".join(f"“{row['texto']}”" for row in genericos[:4]),
                "O texto do link não diz para onde ele leva.",
                "Texto genérico é ruim para leitor de tela e para busca; é achado de SEO recorrente.",
                "Escreva no texto o assunto do destino.",
                "O leitor de tela ouve “clique aqui” fora de contexto.",
            )
        )
    if orfaos:
        problemas.append(
            finding(
                "nice",
                "asset-nao-referenciado",
                f"{len(orfaos)} arquivo(s) sem referência",
                ", ".join(orfaos[:4]),
                "O arquivo está no pacote e nenhum link aponta para ele.",
                "Asset sem referência pode ser resto de versão anterior ou arquivo que faltou citar.",
                "Remova o que não é usado ou cite no documento.",
                "O pacote carrega peso e conteúdo que ninguém vê.",
            )
        )
    if not rows:
        problemas.append(
            finding(
                "nice",
                "sem-links",
                "Nenhum link no envio",
                f"{len(conteudos)} arquivo(s)",
                "Não há link, imagem ou referência para conferir.",
                "Artefato sem link é raro e costuma indicar documento incompleto.",
                "Confirme se o README e o corpo do artefato foram enviados.",
                "O artefato entra sem instrução de uso.",
            )
        )

    findings, counts, veredito, perguntas = finalize(
        problemas,
        modo,
        [
            "O link usa caminho relativo à raiz do repositório ou ao arquivo?",
            "O asset órfão é usado por script em vez de markdown?",
            "A âncora aponta para título que ainda existe na versão publicada?",
        ],
    )
    total = len(rows)
    metrics = {
        "arquivos": len(conteudos),
        "links": total,
        "ok": contagem.get("ok", 0),
        "quebrados": len(ausentes) + len(saidas),
        "ancoras": len(ancoras_quebradas),
        "caixa": len(caixa),
        "absolutos": len(absolutos),
        "genericos": len(genericos),
        "orfaos": len(orfaos),
        "saude": _percentual(contagem.get("ok", 0), total),
    }
    summary = [
        f"{total} link(s) em {len(conteudos)} arquivo(s): {contagem.get('ok', 0)} ok, "
        f"{metrics['quebrados']} quebrado(s), {metrics['ancoras']} âncora(s) e {metrics['caixa']} de caixa.",
        f"Saúde dos links: {_fmt_pct(metrics['saude'])}; {len(orfaos)} asset(s) sem referência.",
    ]
    limitations = [
        "Só o que está no bundle é conferido: link para arquivo do repositório que ficou fora do envio aparece como quebrado.",
        "A âncora segue a regra de slug do GitHub e não cobre HTML âncora nem cabeçalho com caractere especial raro.",
        "Nada é baixado: link remoto é aceito pela forma, não pela resposta HTTP.",
        "Asset referenciado por script, e não por markdown, aparece como órfão.",
    ]
    return common(
        analysis="submissao.links",
        mode=modo,
        title="Links e referências",
        summary=summary,
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows[:MAX_ROWS],
        metrics=metrics,
        limitations=limitations,
    )


# --- 6. portão --------------------------------------------------------------


def _sem_id(itens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{chave: valor for chave, valor in item.items() if chave != "id"} for item in itens]


def portao_submissao(*, arquivos: str, esperada: str = "MIT", modo: str = "full") -> dict[str, Any]:
    """Roda ficha, estrutura, risco, licença e links e decide o estado do envio."""
    modo = _modo(modo)
    bruto = (arquivos or "").strip()
    if not bruto:
        raise SubmissaoError("Informe o bundle do envio com `>>> caminho` seguido do conteúdo.")
    primeira = RE_CABECALHO.match(bruto.split("\n", 1)[0])
    com_conteudo = bool(primeira and _parece_caminho(primeira.group(1))) or bruto.startswith("{")
    conteudos = ler_bundle(bruto) if com_conteudo else {caminho: "" for caminho, _ in _caminhos(bruto)}
    caminhos = list(conteudos)

    tipos = {caminho: inferir_tipo(caminho) for caminho in caminhos}
    conhecidos = [caminho for caminho, tipo in tipos.items() if tipo != "desconhecido"]

    checagens: list[tuple[str, dict[str, Any]]] = []
    estrutura = validar_estrutura(arquivos=bruto, modo="full")
    checagens.append(("estrutura", estrutura))

    fichas: list[dict[str, Any]] = []
    for caminho in conhecidos if com_conteudo else []:
        conteudo = conteudos[caminho]
        tipo = tipos[caminho]
        if tipo in {"skill", "agent", "instruction", "hook", "workflow", "prompt", "plugin"} and conteudo.strip():
            fichas.append(validar_ficha(caminho=caminho, texto=conteudo, tipo=tipo, modo="full"))
    if not fichas:
        fichas.append({"findings": [], "rows": []})

    risco = varrer_risco(arquivos=bruto, modo="full") if com_conteudo else {"findings": [], "rows": [], "metrics": {}}
    checagens.append(("risco", risco))

    links = conferir_links(arquivos=bruto, modo="full") if com_conteudo and any(caminho.lower().endswith(".md") for caminho in caminhos) else {"findings": [], "rows": [], "metrics": {}}
    checagens.append(("links", links))

    licencas: list[dict[str, Any]] = []
    for caminho in conhecidos if com_conteudo else []:
        if tipos[caminho] != "plugin":
            continue
        dados, _ = _ler_json(conteudos[caminho], caminho)
        licencas.append(analisar_licenca(licenca=str(dados.get("license", "")), esperada=esperada, obrigatoria=True, modo="full"))
    checagens.append(("licenca", {"findings": [item for analise in licencas for item in analise["findings"]]}))

    achados: list[dict[str, Any]] = []
    for nome, analise in checagens:
        for item in _sem_id(analise.get("findings", [])):
            achados.append({**item, "origem": nome})
    for analise in fichas:
        for item in _sem_id(analise.get("findings", [])):
            achados.append({**item, "origem": "ficha"})

    if not conhecidos:
        achados.append(
            finding(
                "must",
                "sem-artefato",
                "Nenhum artefato reconhecido no envio",
                ", ".join(caminhos[:3]),
                "Nenhum caminho casa com as pastas do catálogo.",
                "Sem artefato não há o que publicar.",
                "Mova o arquivo para `skills/`, `agents/`, `instructions/`, `hooks/`, `plugins/`, `workflows/` ou `prompts/`.",
                "O PR fica aberto sem nada para o catálogo indexar.",
            )
        )
    if len(caminhos) > 60:
        achados.append(
            finding(
                "should",
                "envio-grande",
                f"{len(caminhos)} arquivo(s) no envio",
                "acima de 60",
                "Envio grande mistura vários artefatos num PR só.",
                "PR grande é onde a revisão humana perde o fio e o portão automático fica lento.",
                "Divida por artefato, mantendo os assets junto do seu dono.",
                "Um defeito no meio do envio trava todos os artefatos.",
            )
        )
    if not com_conteudo:
        achados.append(
            finding(
                "should",
                "sem-conteudo",
                "Envio sem conteúdo",
                f"{len(caminhos)} caminho(s)",
                "Só os caminhos foram informados.",
                "O portão não consegue conferir front matter, risco nem link sem o texto.",
                "Cole o bundle com `>>> caminho` e o conteúdo de cada arquivo.",
                "O envio passa sem validação e o defeito aparece na revisão humana.",
            )
        )

    must = sum(1 for item in achados if item["group"] == "must")
    should = sum(1 for item in achados if item["group"] == "should")
    nice = sum(1 for item in achados if item["group"] == "nice")
    if must:
        decisao = "requires-submitter-fixes"
        explicacao = "Há bloqueio: o envio volta para quem submeteu antes da revisão humana."
    elif not com_conteudo:
        decisao = "awaiting-review"
        explicacao = "Sem bloqueio, mas sem conteúdo conferido: aguarda validação automática."
    else:
        decisao = "ready-for-review"
        explicacao = "Nenhum bloqueio: o envio pode ir para a revisão humana."
        if should:
            explicacao += f" Restam {should} ponto(s) de atenção que não impedem o merge."

    rows = [
        {
            "checagem": "ficha",
            "achados": sum(len(analise["findings"]) for analise in fichas),
            "must": sum(1 for analise in fichas for item in analise["findings"] if item["group"] == "must"),
            "estado": "bloqueia" if any(item["group"] == "must" for analise in fichas for item in analise["findings"]) else "ok",
        },
    ]
    for nome, analise in checagens:
        itens = analise.get("findings", [])
        rows.append(
            {
                "checagem": nome,
                "achados": len(itens),
                "must": sum(1 for item in itens if item["group"] == "must"),
                "estado": "bloqueia" if any(item["group"] == "must" for item in itens) else "ok",
            }
        )
    rows.append(
        {
            "checagem": "portão",
            "achados": len(achados),
            "must": must,
            "estado": decisao,
        }
    )

    findings, counts, _veredito, perguntas = finalize(achados, modo, [
        "Quem corrige os bloqueios: quem submeteu ou quem mantém o catálogo?",
        "O envio pode ser dividido em mais de um PR?",
        "Algum achado de risco alto é exemplo didático documentado?",
    ])
    if must:
        veredito = f"{must} bloqueio(s): decisão `{decisao}`."
    elif decisao == "awaiting-review":
        veredito = "Sem conteúdo conferido: decisão `awaiting-review`."
    else:
        veredito = f"Nenhum bloqueio: decisão `{decisao}`" + (f" com {should} atenção(ões)." if should else ".")
    metrics = {
        "arquivos": len(caminhos),
        "com_conteudo": len(conteudos) if com_conteudo else 0,
        "tipos": len({tipo for tipo in tipos.values() if tipo != "desconhecido"}),
        "fichas": len(fichas),
        "achados": len(achados),
        "must": must,
        "should": should,
        "nice": nice,
        "decisao": decisao,
        "rotulo": decisao,
    }
    summary = [
        f"{len(caminhos)} arquivo(s), {metrics['tipos']} tipo(s) de artefato; {len(achados)} achado(s): "
        f"{must} bloqueio(s), {should} atenção(ões) e {nice} sugestão(ões).",
        f"Decisão do portão: **{decisao}** — {explicacao}",
        f"Rótulo a aplicar: `{decisao}`; a remover: `awaiting-review`.",
    ]
    limitations = [
        "O portão não aplica rótulo, não comenta no PR e não abre issue: a decisão é texto.",
        "Cada checagem roda sobre o bundle colado; arquivo do repositório fora do envio não é lido.",
        "A decisão é binária por bloqueio: atenção não impede o merge, mesmo quando é muita.",
        "Nada é executado: a instalação do artefato e o lint do plugin de referência não rodam aqui.",
    ]
    return common(
        analysis="submissao.gate",
        mode=modo,
        title="Portão de submissão",
        summary=summary,
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows,
        metrics=metrics,
        limitations=limitations,
    )


# --- 7. catálogo ------------------------------------------------------------


def submissao_catalogo() -> dict[str, Any]:
    """Publica tipos, campos, limites, regras de risco, SPDX e a semântica do portão."""
    return {
        "versao": VERSAO,
        "origem": {
            "projeto": "github/awesome-copilot",
            "licenca": "MIT",
            "estrelas": 40_376,
            "pipeline": "eng/ (validate-skills, pr-risk-scan, validate-plugins, lib/license)",
        },
        "principio": (
            "Todo envio passa por um portão determinístico antes da revisão humana: "
            "front matter, estrutura, risco, licença e link. O que é conta, não é opinião."
        ),
        "tipos": [
            {"tipo": tipo, "pasta": pasta, "arquivo": arquivo, "obrigatorios": CAMPOS[tipo]["obrigatorios"], "opcionais": CAMPOS[tipo]["opcionais"]}
            for tipo, pasta, arquivo in [
                ("skill", "skills/<nome>/", "SKILL.md"),
                ("agent", "agents/", "<nome>.agent.md"),
                ("instruction", "instructions/", "<nome>.instructions.md"),
                ("hook", "hooks/<nome>/", "README.md + hooks.json"),
                ("plugin", "plugins/<nome>/", "plugin.json + README.md"),
                ("workflow", "workflows/", "<nome>.md"),
                ("prompt", "prompts/", "<nome>.prompt.md"),
            ]
        ],
        "limites": {
            "texto": MAX_TEXTO,
            "arquivos": MAX_ARQUIVOS,
            "achados": MAX_ACHADOS,
            "linhas_por_tabela": MAX_ROWS,
            "asset_bytes": MAX_ASSET,
            "nome": {"min": NOME_MIN, "max": NOME_MAX, "padrao": "^[a-z0-9]+(-[a-z0-9]+)*$"},
            "descricao": {"min": DESCRICAO_MIN, "max": DESCRICAO_MAX},
            "tags": {"max": MAX_TAGS, "tamanho": TAG_MAX},
        },
        "risco": {
            "regras": [
                {"regra": regra.regra, "severidade": regra.severidade, "motivo": regra.motivo, "correcao": regra.correcao}
                for regra in REGRAS_RISCO
            ],
            "grupo": GRUPO_RISCO,
            "mascara_segredo": True,
            "trecho_maximo": 180,
        },
        "licenca": {
            "ids": sorted(SPDX_IDS),
            "excecoes": sorted(SPDX_EXCECOES),
            "operadores": sorted(OPERADORES),
            "copyleft": sorted(COPYLEFT),
            "aliases": dict(sorted(ALIASES_LICENCA.items())),
            "regra": "Expressão SPDX válida; não SPDX bloqueia, identificador desconhecido avisa, copyleft avisa.",
        },
        "links": {
            "situacoes": ["ok", "arquivo-ausente", "ancora-ausente", "saida", "absoluto", "caixa", "texto-generico", "inseguro"],
            "ancora": "slug do GitHub: minúscula, sem formatação, espaço vira hífen",
            "texto_generico": sorted(TEXTO_GENERICO),
        },
        "portao": {
            "decisoes": list(ROTULOS),
            "regra": {
                "requires-submitter-fixes": "qualquer achado must",
                "awaiting-review": "sem conteúdo para conferir",
                "ready-for-review": "nenhum must e conteúdo conferido",
            },
            "rotulo_a_remover": "awaiting-review",
        },
        "modos": list(MODOS),
        "deixado_de_fora": [
            "Rodar `vally lint` ou instalar o plugin num marketplace efêmero.",
            "Aplicar rótulo, comentar no PR ou abrir issue no GitHub.",
            "Baixar o repositório do artefato ou seguir link externo.",
            "Interpretar YAML completo (âncora, alias, tag, multi-documento).",
            "Julgar mérito do conteúdo: isso continua na revisão humana.",
        ],
        "executed": False,
        "readOnly": True,
    }
