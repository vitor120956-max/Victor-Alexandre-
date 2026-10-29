"""Escritório assistido — comandos, receitas, páginas, lotes, escopos e erros.

Inspirado em googleworkspace/cli (Apache-2.0, 2026). Implementação própria e
determinística. Nada do upstream é instalado ou executado: não há binário Rust,
download de release, `npm install -g`, extensão do Gemini, `gcloud` nem OAuth.
As skills leem o que você cola — serviço, método, parâmetros, páginas, itens,
escopos e mensagens de erro — e devolvem o comando `gws`, o roteiro da receita,
a leitura da paginação, os lotes, a comparação de escopos e a triagem do erro.

O recorte é o que sobrevive sem rede: o contrato da linha de comando (descoberta
dinâmica, `--params`, `--json`, `--dry-run`, paginação, códigos de saída), o
princípio do menor escopo, o formato dos erros do Google e o registro de
receitas. Nenhuma skill autentica, chama API, lê credencial ou grava arquivo.
"""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from .review import common, finalize, finding

MAX_PARAMS = 20_000
MAX_CORPO = 40_000
MAX_PAGINAS = 200_000
MAX_ITENS = 200_000
MAX_OPERACOES = 20_000
MAX_MENSAGEM = 20_000
MAX_RECEITA = 80

VERSAO = "0.62.3"


class EscritorioError(ValueError):
    """Erro esperado do escritório assistido, seguro para o usuário."""


# --------------------------------------------------------------- vocabulário

SERVICOS: dict[str, dict[str, Any]] = {
    "drive": {"rotulo": "Drive", "api": "drive.googleapis.com", "familia": "drive",
              "ajudantes": ["+upload"]},
    "gmail": {"rotulo": "Gmail", "api": "gmail.googleapis.com", "familia": "gmail",
              "ajudantes": ["+send", "+reply", "+reply-all", "+forward", "+triage", "+watch"]},
    "calendar": {"rotulo": "Calendar", "api": "calendar-json.googleapis.com", "familia": "calendar",
                 "ajudantes": ["+insert", "+agenda"]},
    "sheets": {"rotulo": "Sheets", "api": "sheets.googleapis.com", "familia": "sheets",
               "ajudantes": ["+append", "+read"]},
    "docs": {"rotulo": "Docs", "api": "docs.googleapis.com", "familia": "documents",
             "ajudantes": ["+write"]},
    "slides": {"rotulo": "Slides", "api": "slides.googleapis.com", "familia": "slides",
               "ajudantes": []},
    "chat": {"rotulo": "Chat", "api": "chat.googleapis.com", "familia": "chat",
             "ajudantes": ["+send"]},
    "admin": {"rotulo": "Admin SDK", "api": "admin.googleapis.com", "familia": "admin",
              "ajudantes": []},
    "classroom": {"rotulo": "Classroom", "api": "classroom.googleapis.com", "familia": "classroom",
                  "ajudantes": []},
    "forms": {"rotulo": "Forms", "api": "forms.googleapis.com", "familia": "forms",
              "ajudantes": []},
    "keep": {"rotulo": "Keep", "api": "keep.googleapis.com", "familia": "keep",
             "ajudantes": []},
    "meet": {"rotulo": "Meet", "api": "meet.googleapis.com", "familia": "meet",
             "ajudantes": []},
    "people": {"rotulo": "People", "api": "people.googleapis.com", "familia": "people",
               "ajudantes": []},
    "script": {"rotulo": "Apps Script", "api": "script.googleapis.com", "familia": "script",
               "ajudantes": ["+push"]},
    "tasks": {"rotulo": "Tasks", "api": "tasks.googleapis.com", "familia": "tasks",
              "ajudantes": []},
    "events": {"rotulo": "Workspace Events", "api": "workspaceevents.googleapis.com",
               "familia": "events", "ajudantes": ["+subscribe", "+renew"]},
    "workflow": {"rotulo": "Workflows", "api": "", "familia": "workflow",
                 "ajudantes": ["+standup-report", "+meeting-prep", "+email-to-task",
                               "+weekly-digest", "+file-announce"]},
    "modelarmor": {"rotulo": "Model Armor", "api": "modelarmor.googleapis.com",
                   "familia": "modelarmor", "ajudantes": ["+sanitize-prompt",
                                                          "+sanitize-response",
                                                          "+create-template"]},
}

FLAGS: dict[str, dict[str, Any]] = {
    "--params": {"tipo": "JSON", "padrao": "", "nota": "Parâmetros da descoberta, sempre um objeto JSON."},
    "--json": {"tipo": "JSON", "padrao": "", "nota": "Corpo do pedido, sempre um objeto JSON."},
    "--dry-run": {"tipo": "lógico", "padrao": "desligado", "nota": "Imprime o pedido HTTP sem enviar."},
    "--page-all": {"tipo": "lógico", "padrao": "desligado", "nota": "Pagina sozinho e imprime uma linha JSON por página (NDJSON)."},
    "--page-limit": {"tipo": "inteiro", "padrao": "10", "nota": "Máximo de páginas; só vale com `--page-all`."},
    "--page-delay": {"tipo": "inteiro (ms)", "padrao": "100", "nota": "Intervalo entre páginas; só vale com `--page-all`."},
    "--upload": {"tipo": "caminho", "padrao": "", "nota": "Upload multipart; só em `drive files create`/`update`."},
    "--sanitize": {"tipo": "recurso", "padrao": "", "nota": "Template do Model Armor: `projects/P/locations/L/templates/T`."},
    "--timezone": {"tipo": "fuso IANA", "padrao": "fuso da conta", "nota": "Ajudantes de agenda; `--tz` é o atalho."},
    "--scopes": {"tipo": "lista", "padrao": "preset", "nota": "Só em `gws auth login`; aceita chaves como `drive,gmail`."},
}

CODIGOS_SAIDA: dict[int, tuple[str, str]] = {
    0: ("sucesso", "Comando concluído."),
    1: ("erro de API", "O Google respondeu 4xx/5xx."),
    2: ("erro de autenticação", "Credencial ausente, expirada ou inválida."),
    3: ("erro de validação", "Argumento inválido, serviço desconhecido ou flag errada."),
    4: ("erro de descoberta", "O documento de descoberta não pôde ser obtido."),
    5: ("erro interno", "Falha inesperada do próprio CLI."),
}

ESCOPOS: dict[str, dict[str, str]] = {
    "drive.readonly": {"rotulo": "Drive — leitura", "acesso": "leitura"},
    "drive.file": {"rotulo": "Drive — arquivos criados pelo app", "acesso": "escrita limitada"},
    "drive": {"rotulo": "Drive — completo", "acesso": "completo"},
    "spreadsheets.readonly": {"rotulo": "Sheets — leitura", "acesso": "leitura"},
    "spreadsheets": {"rotulo": "Sheets — leitura e escrita", "acesso": "escrita"},
    "documents.readonly": {"rotulo": "Docs — leitura", "acesso": "leitura"},
    "documents": {"rotulo": "Docs — leitura e escrita", "acesso": "escrita"},
    "presentations.readonly": {"rotulo": "Slides — leitura", "acesso": "leitura"},
    "presentations": {"rotulo": "Slides — leitura e escrita", "acesso": "escrita"},
    "gmail.readonly": {"rotulo": "Gmail — leitura", "acesso": "leitura"},
    "gmail.send": {"rotulo": "Gmail — enviar", "acesso": "envio"},
    "gmail.modify": {"rotulo": "Gmail — modificar e ler", "acesso": "escrita"},
    "gmail.labels": {"rotulo": "Gmail — rótulos", "acesso": "escrita"},
    "calendar.readonly": {"rotulo": "Calendar — leitura", "acesso": "leitura"},
    "calendar.events": {"rotulo": "Calendar — eventos", "acesso": "escrita"},
    "calendar": {"rotulo": "Calendar — completo", "acesso": "completo"},
    "chat.messages.readonly": {"rotulo": "Chat — leitura de mensagens", "acesso": "leitura"},
    "chat.messages": {"rotulo": "Chat — mensagens", "acesso": "escrita"},
    "tasks": {"rotulo": "Tasks", "acesso": "escrita"},
    "contacts.readonly": {"rotulo": "People — contatos", "acesso": "leitura"},
    "directory.readonly": {"rotulo": "Admin — diretório", "acesso": "leitura"},
    "directory.user": {"rotulo": "Admin — usuários", "acesso": "escrita"},
    "classroom.courses.readonly": {"rotulo": "Classroom — cursos", "acesso": "leitura"},
    "forms.responses.readonly": {"rotulo": "Forms — respostas", "acesso": "leitura"},
    "forms.body": {"rotulo": "Forms — formulário", "acesso": "escrita"},
    "keep.readonly": {"rotulo": "Keep — leitura", "acesso": "leitura"},
    "meetings.space.created": {"rotulo": "Meet — espaços", "acesso": "escrita"},
    "script.projects": {"rotulo": "Script — projetos", "acesso": "escrita"},
    "script.deployments": {"rotulo": "Script — implantações", "acesso": "escrita"},
    "workspaceevents.subscriptions": {"rotulo": "Events — assinaturas", "acesso": "escrita"},
    "cloud-platform": {"rotulo": "Model Armor (Cloud Platform)", "acesso": "completo"},
}

PRESETS: dict[str, list[str]] = {
    "recommended": ["drive", "gmail.modify", "calendar", "spreadsheets", "documents",
                    "presentations", "chat.messages", "tasks", "contacts.readonly",
                    "script.projects", "script.deployments"],
    "drive": ["drive.file"],
    "gmail": ["gmail.modify"],
    "calendar": ["calendar"],
    "sheets": ["spreadsheets"],
    "docs": ["documents"],
    "admin": ["directory.user", "directory.readonly"],
}

LIMITE_ESCOPOS = 25


# ------------------------------------------------------------------ utilidades

def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def _slug(texto: str) -> str:
    base = _sem_acento(texto).lower()
    return re.sub(r"[^a-z0-9]+", "-", base).strip("-")


def _quote(valor: str) -> str:
    return "'" + valor.replace("'", "'\\''") + "'"


def _json_obj(texto: str, nome: str) -> dict[str, Any]:
    if not texto.strip():
        return {}
    try:
        valor = json.loads(texto)
    except json.JSONDecodeError as erro:
        raise EscritorioError(
            f"{nome} não é JSON válido (linha {erro.lineno}, coluna {erro.colno}): {erro.msg}."
        ) from erro
    if not isinstance(valor, dict):
        raise EscritorioError(f"{nome} precisa ser um objeto JSON, não {type(valor).__name__}.")
    return valor


def _json_any(texto: str, nome: str) -> Any:
    try:
        return json.loads(texto)
    except json.JSONDecodeError as erro:
        raise EscritorioError(
            f"{nome} não é JSON válido (linha {erro.lineno}, coluna {erro.colno}): {erro.msg}."
        ) from erro


def _compacto(valor: Any) -> str:
    return json.dumps(valor, ensure_ascii=False, separators=(",", ":"))


def _linhas(texto: str) -> list[str]:
    return [linha.strip() for linha in texto.splitlines() if linha.strip() and not linha.strip().startswith("#")]


def _metodo_partes(recurso: str, metodo: str) -> tuple[str, str]:
    metodo = metodo.strip()
    if "." in metodo:
        prefixo, _, final = metodo.rpartition(".")
        recurso = f"{recurso}.{prefixo}" if recurso else prefixo
        metodo = final
    return recurso.strip(), metodo


def _ler_como(valor: str) -> str:
    normal = _sem_acento(valor).lower()
    if normal in {"leitura", "read", "ler"}:
        return "leitura"
    if normal in {"escrita", "write"}:
        return "escrita"
    if normal in {"destrutivo", "delete", "exclusao"}:
        return "destrutivo"
    return "leitura"


# ------------------------------------------------------------------- risco

LEITURA = re.compile(r"^(list|get|export|search|watch|aggregate|query|read)$", re.I)
DESTRUTIVO = re.compile(r"^(delete|trash|empty|remove|clear|move|purge)$", re.I)


def _risco_do_metodo(recurso: str, metodo: str) -> str:
    if DESTRUTIVO.match(metodo) or recurso.endswith("permissions") and metodo in {"delete", "update"}:
        return "destrutivo"
    if LEITURA.match(metodo):
        return "leitura"
    return "escrita"


def _escopos_do_metodo(servico: str, recurso: str, metodo: str, ajudante: str = "") -> list[str]:
    familia = SERVICOS[servico]["familia"]
    risco = _risco_do_metodo(recurso, metodo)
    if ajudante:
        if servico == "gmail":
            if ajudante in {"+triage", "+watch"}:
                return ["gmail.readonly"]
            if ajudante == "+forward":
                return ["gmail.modify"]
            if ajudante in {"+send", "+reply", "+reply-all"}:
                return ["gmail.send"]
        if servico == "sheets":
            return ["spreadsheets" if ajudante == "+append" else "spreadsheets.readonly"]
        if servico == "docs":
            return ["documents"]
        if servico == "drive":
            return ["drive.file"]
        if servico == "calendar":
            return ["calendar.events" if ajudante == "+insert" else "calendar.readonly"]
        if servico == "chat":
            return ["chat.messages"]
        if servico == "modelarmor":
            return ["cloud-platform"]
        if servico == "events":
            return ["workspaceevents.subscriptions"]
        if servico == "script":
            return ["script.projects"]
        if servico == "workflow":
            return ["calendar.readonly", "gmail.readonly", "tasks"]
    leitura = risco == "leitura"
    if familia == "drive":
        if leitura:
            return ["drive.readonly"]
        return ["drive.file"] if metodo in {"create", "update"} and not recurso.endswith("permissions") else ["drive"]
    if familia == "gmail":
        if leitura:
            return ["gmail.readonly"]
        if recurso.endswith("labels"):
            return ["gmail.labels"]
        if metodo in {"modify", "batchModify", "trash", "untrash"}:
            return ["gmail.modify"]
        if metodo in {"send", "insert", "import"}:
            return ["gmail.send"] if metodo == "send" else ["gmail.modify"]
        return ["gmail.modify"]
    if familia == "calendar":
        return ["calendar.readonly"] if leitura else ["calendar.events"]
    if familia == "sheets":
        return ["spreadsheets.readonly"] if leitura else ["spreadsheets"]
    if familia == "documents":
        return ["documents.readonly"] if leitura else ["documents"]
    if familia == "slides":
        return ["presentations.readonly"] if leitura else ["presentations"]
    if familia == "chat":
        return ["chat.messages.readonly"] if leitura else ["chat.messages"]
    if familia == "tasks":
        return ["tasks"]
    if familia == "people":
        return ["contacts.readonly"]
    if familia == "admin":
        return ["directory.readonly"] if leitura else ["directory.user"]
    if familia == "classroom":
        return ["classroom.courses.readonly"]
    if familia == "forms":
        return ["forms.responses.readonly"] if leitura else ["forms.body"]
    if familia == "keep":
        return ["keep.readonly"] if leitura else ["cloud-platform"]
    if familia == "meet":
        return ["meetings.space.created"]
    if familia == "script":
        return ["script.deployments"] if recurso.endswith("deployments") else ["script.projects"]
    if familia == "events":
        return ["workspaceevents.subscriptions"]
    if familia == "modelarmor":
        return ["cloud-platform"]
    if familia == "workflow":
        return ["calendar.readonly", "gmail.readonly", "tasks"]
    return []


def _escopo_url(chave: str) -> str:
    return f"https://www.googleapis.com/auth/{chave}"


def _escopo_detalhe(chave: str) -> dict[str, Any]:
    dado = ESCOPOS.get(chave, {"rotulo": chave, "acesso": "desconhecido"})
    return {"chave": chave, "url": _escopo_url(chave), "rotulo": dado["rotulo"], "acesso": dado["acesso"]}


# ------------------------------------------------------- parâmetros exigidos

EXIGIDOS: dict[str, dict[str, Any]] = {
    "files": {"leitura": ["fileId"], "escrita": ["fileId"]},
    "permissions": {"leitura": ["fileId"], "escrita": ["fileId"]},
    "users.messages": {"leitura": ["userId", "id"], "escrita": ["userId", "id"]},
    "users.threads": {"leitura": ["userId", "id"], "escrita": ["userId", "id"]},
    "users.labels": {"leitura": ["userId"], "escrita": ["userId"]},
    "users.drafts": {"leitura": ["userId"], "escrita": ["userId"]},
    "spreadsheets": {"leitura": ["spreadsheetId"], "escrita": ["spreadsheetId"]},
    "values": {"leitura": ["spreadsheetId", "range"], "escrita": ["spreadsheetId"]},
    "documents": {"leitura": ["documentId"], "escrita": ["documentId"]},
    "presentations": {"leitura": ["presentationId"], "escrita": ["presentationId"]},
    "events": {"leitura": ["calendarId"], "escrita": ["calendarId"]},
    "calendars": {"leitura": ["calendarId"], "escrita": ["calendarId"]},
    "spaces": {"leitura": ["parent"], "escrita": ["parent"]},
    "tasks": {"leitura": ["tasklist"], "escrita": ["tasklist"]},
    "courses": {"leitura": ["courseId"], "escrita": ["courseId"]},
}
EXIGIDOS_LISTA: dict[str, list[str]] = {
    "files": [],
    "users.messages": ["userId"],
    "users.threads": ["userId"],
    "users.labels": ["userId"],
    "users.drafts": ["userId"],
    "spreadsheets": ["spreadsheetId"],
    "values": ["spreadsheetId", "range"],
    "documents": ["documentId"],
    "presentations": ["presentationId"],
    "events": ["calendarId"],
    "spaces": [],
    "tasks": ["tasklist"],
    "courses": [],
}


CRIACAO = {"list", "search", "create", "insert", "append", "import", "send"}


def _exigidos(recurso: str, metodo: str) -> list[str]:
    if metodo.lower() in CRIACAO:
        for prefixo, chaves in EXIGIDOS_LISTA.items():
            if recurso == prefixo or recurso.endswith(f".{prefixo}"):
                return chaves
        return []
    for prefixo, exigencias in EXIGIDOS.items():
        if recurso == prefixo or recurso.endswith(f".{prefixo}"):
            risco = "leitura" if LEITURA.match(metodo) else "escrita"
            return exigencias[risco]
    return []


# ------------------------------------------------------------ argumentos de ajudante

AJUDANTE_FLAGS: dict[str, set[str]] = {
    "+upload": {"--name"},
    "+send": {"--to", "--subject", "--body", "--cc", "--bcc", "--html"},
    "+reply": {"--message-id", "--body"},
    "+reply-all": {"--message-id", "--body"},
    "+forward": {"--message-id", "--to", "--body"},
    "+append": {"--spreadsheet", "--range", "--values"},
    "+read": {"--spreadsheet", "--range"},
    "+write": {"--document", "--text"},
    "+insert": {"--calendar", "--summary", "--start", "--end", "--attendees", "--location"},
    "+agenda": {"--today", "--timezone", "--tz", "--days"},
    "+push": {"--script", "--dir"},
    "+subscribe": {"--target", "--event-types"},
    "+renew": {"--name"},
    "+sanitize-prompt": {"--template", "--text"},
    "+sanitize-response": {"--template", "--text"},
    "+create-template": {"--project", "--location", "--template"},
    "+standup-report": {"--timezone", "--tz"},
    "+meeting-prep": {"--timezone", "--tz"},
    "+email-to-task": {"--message-id", "--tasklist"},
    "+weekly-digest": {"--timezone", "--tz"},
    "+file-announce": {"--file", "--space"},
}


def _argumentos(texto: str, servico: str, ajudante: str) -> tuple[list[str], list[dict[str, Any]]]:
    achados: list[dict[str, Any]] = []
    partes: list[str] = []
    if not texto.strip():
        return partes, achados
    permitidas = AJUDANTE_FLAGS.get(ajudante, set())
    tokens = texto.split()
    indice = 0
    while indice < len(tokens):
        token = tokens[indice]
        if not token.startswith("--"):
            achados.append(finding(
                "must", "argumento-solto", "Argumento sem flag", ajudante,
                "Todo argumento de ajudante precisa de uma flag.",
                f"`{token}` não começa com `--` e seria interpretado como valor solto.",
                "Use o formato `--flag valor` ou `--flag=valor`.",
                "O CLI recusa o comando com código 3.",
            ))
            partes.append(token)
            indice += 1
            continue
        nome, separador, valor = token.partition("=")
        if not separador and indice + 1 < len(tokens) and not tokens[indice + 1].startswith("--"):
            valor = tokens[indice + 1]
            indice += 1
        if nome not in permitidas:
            achados.append(finding(
                "must", "flag-desconhecida", "Flag fora do ajudante", f"{servico} {ajudante} {nome}",
                "O catálogo do ajudante não declara essa flag.",
                f"`{nome}` não é aceita por `{servico} {ajudante}`.",
                f"Use uma de: {', '.join(sorted(permitidas)) or 'nenhuma — o ajudante não tem flags'}.",
                "O CLI devolve erro de validação (código 3).",
            ))
        if nome in permitidas and not valor and nome not in {"--today"}:
            achados.append(finding(
                "should", "flag-sem-valor", "Flag sem valor", f"{servico} {ajudante} {nome}",
                "A flag abre espaço para um valor que não veio.",
                f"`{nome}` foi passada sem valor.",
                f"Passe `{nome} valor` ou remova a flag.",
                "Ajudantes costumam recusar o comando inteiro.",
            ))
        if separador:
            partes.append(f"{nome}={_quote(valor)}" if valor else nome)
        else:
            partes.append(f"{nome} {_quote(valor)}" if valor else nome)
        indice += 1
    return partes, achados


# --------------------------------------------------------------- comando

def montar_comando(
    *,
    servico: str,
    recurso: str,
    metodo: str,
    params: str,
    corpo: str,
    argumentos: str,
    paginas: bool,
    limite_paginas: int,
    atraso_pagina: int,
    simular: bool,
    upload: str,
    sanitizar: str,
    modo: str,
) -> dict[str, Any]:
    servico = servico.strip().lower()
    if servico not in SERVICOS:
        raise EscritorioError(
            f"Serviço desconhecido: `{servico}`. Use um de: {', '.join(sorted(SERVICOS))}."
        )
    recurso, metodo = _metodo_partes(recurso.strip(), metodo.strip())
    if not metodo:
        raise EscritorioError("Informe o método (ex.: `files list`, `users.messages send`).")
    if not metodo.startswith("+") and not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", metodo):
        raise EscritorioError(
            f"Método inválido: `{metodo}`. A descoberta usa nomes como `list`, `get`, `batchUpdate`."
        )
    if recurso and not re.fullmatch(r"[a-z][A-Za-z0-9.]*", recurso):
        raise EscritorioError(
            f"Recurso inválido: `{recurso}`. Use o nome da descoberta, como `users.messages` ou `files`."
        )

    ajudante = metodo if metodo.startswith("+") else ""
    if ajudante:
        if ajudante not in SERVICOS[servico]["ajudantes"]:
            raise EscritorioError(
                f"`{servico}` não tem o ajudante `{ajudante}`. Disponíveis: "
                f"{', '.join(SERVICOS[servico]['ajudantes']) or 'nenhum'}."
            )
        if recurso:
            raise EscritorioError("Ajudantes não usam recurso: informe só `+nome` no método.")
        if params.strip() or corpo.strip():
            raise EscritorioError(
                "Ajudantes não aceitam `--params`/`--json`: os argumentos vão em `argumentos`."
            )
        args, achados = _argumentos(argumentos, servico, ajudante)
        partes = ["gws", servico, ajudante, *args]
        escopos = _escopos_do_metodo(servico, "", ajudante, ajudante)
        LEITURA_AJUDANTE = {"+triage", "+agenda", "+read", "+watch", "+standup-report",
                            "+weekly-digest", "+meeting-prep"}
        risco = "leitura" if ajudante in LEITURA_AJUDANTE else "escrita"
        if simular and risco != "leitura":
            partes.append("--dry-run")
        comando = " ".join(partes)
        rows = [{"parte": indice + 1, "valor": parte} for indice, parte in enumerate(partes)]
        achados = _finalizar_comando(achados, modo, servico, ajudante, risco, escopos, comando,
                                     rows, {}, simular)
        return achados

    params_obj = _json_obj(params, "Parâmetros")
    corpo_obj = _json_obj(corpo, "Corpo")
    risco = _risco_do_metodo(recurso, metodo)
    escopos = _escopos_do_metodo(servico, recurso, metodo)
    achados: list[dict[str, Any]] = []

    partes = ["gws", servico] + ([recurso] if recurso else []) + [metodo]
    if params_obj:
        partes += ["--params", _quote(_compacto(params_obj))]
    if corpo_obj:
        partes += ["--json", _quote(_compacto(corpo_obj))]
    if paginas:
        partes.append("--page-all")
        if limite_paginas != 10:
            partes += ["--page-limit", str(limite_paginas)]
        if atraso_pagina != 100:
            partes += ["--page-delay", str(atraso_pagina)]
    if upload.strip():
        partes += ["--upload", _quote(upload.strip())]
    if sanitizar.strip():
        partes += ["--sanitize", _quote(sanitizar.strip())]
    if simular and risco != "leitura":
        partes.append("--dry-run")
    comando = " ".join(partes)

    # validações
    faltando = [chave for chave in _exigidos(recurso, metodo) if chave not in params_obj]
    if faltando:
        achados.append(finding(
            "must", "parametro-faltando", "Parâmetro obrigatório ausente",
            ", ".join(faltando),
            "A descoberta exige esse parâmetro no caminho ou na consulta.",
            f"Sem {', '.join(faltando)}, o pedido não identifica o recurso.",
            f'Acrescente ao `--params`, por exemplo: {{"{faltando[0]}": "..."}}.',
            "O CLI devolve erro de validação (código 3) ou a API devolve 404.",
        ))
    if risco == "leitura" and corpo_obj:
        achados.append(finding(
            "should", "corpo-em-leitura", "Corpo em método de leitura", f"{recurso} {metodo}",
            "O método lê; corpo só faz sentido em escrita.",
            "O `--json` seria enviado a um método que ignora corpo.",
            "Remova o corpo ou confira se o método é `create`/`update`/`batchUpdate`.",
            "O pedido pode ser recusado com 400.",
        ))
    if risco != "leitura" and not corpo_obj and metodo.lower() not in {"delete", "trash", "empty", "clear"}:
        achados.append(finding(
            "must", "corpo-faltando", "Corpo ausente em escrita", f"{recurso} {metodo}",
            "Métodos de escrita esperam um corpo JSON.",
            "Sem `--json`, a API responde 400 por corpo vazio.",
            'Monte o corpo: `--json \'{"name": "..."}\'`.',
            "O CLI devolve erro de API (código 1).",
        ))
    if paginas and not re.match(r"^(list|search)$", metodo, re.I):
        achados.append(finding(
            "should", "paginar-fora-de-lista", "Paginação em método que não lista",
            f"{recurso} {metodo}",
            "`--page-all` só produz páginas em métodos de listagem.",
            "O flag é ignorado ou imprime uma linha só.",
            "Reserve `--page-all` para `list`/`search`.",
            "O NDJSON sai com uma linha e você acha que terminou.",
        ))
    if not paginas and (limite_paginas != 10 or atraso_pagina != 100):
        achados.append(finding(
            "should", "limite-sem-paginar", "Limite de página sem `--page-all`",
            f"--page-limit {limite_paginas} / --page-delay {atraso_pagina}",
            "Os dois flags pertencem à paginação automática.",
            "Sem `--page-all` eles não têm efeito.",
            "Ligue a paginação ou deixe os valores no padrão.",
            "Você acha que limitou a coleta e não limitou.",
        ))
    if paginas and limite_paginas < 1:
        achados.append(finding(
            "must", "limite-invalido", "Limite de páginas inválido", "--page-limit",
            "O limite precisa ser pelo menos 1.",
            "Zero páginas não devolve nada.",
            "Use 1 ou mais; 10 é o padrão do CLI.",
            "A coleta termina vazia sem erro claro.",
        ))
    if paginas and limite_paginas > 1000:
        achados.append(finding(
            "nice", "limite-grande", "Limite de páginas alto", f"--page-limit {limite_paginas}",
            "Mil páginas ou mais é uma coleta longa.",
            "O tempo e a cota crescem sem sinal no meio.",
            "Comece com 10 e aumente com `--page-delay`.",
            "O comando demora e pode estourar a cota.",
        ))
    if upload.strip():
        if not (servico == "drive" and recurso.endswith("files") and metodo in {"create", "update"}):
            achados.append(finding(
                "must", "upload-fora-do-drive", "Upload fora do Drive", f"{servico} {recurso} {metodo}",
                "`--upload` existe para mídia do Drive.",
                "Outros serviços recusam o flag.",
                "Use `drive files create` ou `update`, com `--json` de metadados.",
                "Erro de validação (código 3).",
            ))
        elif not corpo_obj:
            achados.append(finding(
                "should", "upload-sem-metadados", "Upload sem metadados", "--upload",
                "O Drive aceita o binário, mas o nome vem do corpo.",
                "Sem `--json`, o arquivo sobe com nome derivado do caminho.",
                'Envie `--json \'{"name": "relatorio.pdf"}\'`.',
                "O arquivo fica com nome inesperado.",
            ))
    if sanitizar.strip() and not re.fullmatch(
        r"projects/[^/]+/locations/[^/]+/templates/[^/]+", sanitizar.strip()
    ):
        achados.append(finding(
            "must", "template-invalido", "Template do Model Armor inválido", sanitizar.strip(),
            "O template é um nome de recurso completo.",
            "O formato aceito é `projects/P/locations/L/templates/T`.",
            "Copie o nome do recurso no console do Model Armor.",
            "A sanitização falha com 400.",
        ))
    if risco == "destrutivo":
        achados.append(finding(
            "should", "destrutivo", "Operação destrutiva", f"{recurso} {metodo}",
            "O método apaga, move ou limpa dados.",
            "Não existe desfazer para `delete`, `trash` ou `empty`.",
            "Rode uma vez com `--dry-run`, confira os IDs e só então repita sem simular.",
            "O dado sai da conta sem confirmação.",
        ))
    elif risco == "escrita" and not simular:
        achados.append(finding(
            "nice", "sem-simulacao", "Escrita sem simulação", f"{recurso} {metodo}",
            "`--dry-run` mostra o pedido HTTP sem enviar.",
            "Você descobre o erro só depois de gravar.",
            "Rode com simulação e compare o corpo antes de enviar.",
            "Um erro de forma grava pela metade ou recusa tudo.",
        ))

    rows = [{"parte": indice + 1, "valor": parte} for indice, parte in enumerate(partes)]
    metrics = {
        "parametros": len(params_obj),
        "corpo": len(corpo_obj),
        "flags": sum(1 for parte in partes if parte.startswith("--")),
        "escopos": len(escopos),
        "risco": risco,
    }
    return _finalizar_comando(achados, modo, servico, f"{recurso} {metodo}".strip(), risco,
                              escopos, comando, rows, metrics, simular)


def _finalizar_comando(
    achados: list[dict[str, Any]],
    modo: str,
    servico: str,
    alvo: str,
    risco: str,
    escopos: list[str],
    comando: str,
    rows: list[dict[str, Any]],
    metrics: dict[str, Any],
    simular: bool,
) -> dict[str, Any]:
    perguntas: list[str] = []
    if risco != "leitura" and not simular:
        perguntas.append("Você já rodou a versão com `--dry-run` e conferiu o caminho e o corpo?")
    if risco == "destrutivo":
        perguntas.append("Os IDs listados são exatamente os que você quer remover?")
    if "drive" in escopos or "cloud-platform" in escopos:
        perguntas.append("O escopo completo é necessário, ou `drive.file`/um template específico bastam?")
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    detalhes = [_escopo_detalhe(chave) for chave in escopos]
    resumo = [
        f"Comando proposto para **{servico}** (`{alvo}`), risco **{risco}**.",
        f"Escopos necessários: {', '.join(f'`{chave}`' for chave in escopos) or 'nenhum declarado'}.",
        "O comando é texto: nada foi autenticado, enviado ou executado.",
    ]
    extra = ["", "## Comando", "", "```bash", comando, "```", ""]
    extra += ["## Escopos", ""]
    if detalhes:
        extra += [f"- `{item['chave']}` — {item['rotulo']} ({item['acesso']}): {item['url']}" for item in detalhes]
    else:
        extra += ["- Nenhum escopo mapeado para este serviço."]
    return {
        **common(
            analysis=f"escritorio.comando · {servico} {alvo}",
            mode=modo,
            title="Comando gws",
            summary=resumo,
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=rows,
            metrics=metrics,
            limitations=LIMITES_COMANDO,
            extra_sections=extra,
        ),
        "comando": comando,
        "servico": servico,
        "alvo": alvo,
        "risco": risco,
        "escopos": detalhes,
        "simular": simular,
        "executado": False,
    }


LIMITES_COMANDO = [
    "O comando é texto: nenhuma autenticação, chamada HTTP ou gravação acontece.",
    "A lista de serviços e ajudantes vem do README do upstream em outubro de 2026; `gws <serviço> --help` é a fonte final.",
    "A checagem de parâmetros obrigatórios é curada por recurso, não derivada da descoberta ao vivo.",
    "Escopos são mapeados por serviço e tipo de método; a descoberta pode exigir um escopo adicional.",
]


# --------------------------------------------------------------- receitas

RECEITAS: dict[str, dict[str, Any]] = {
    "agenda-do-dia": {
        "titulo": "Agenda do dia",
        "resumo": "Lê o fuso da conta e resume os compromissos de hoje.",
        "servicos": ["calendar"],
        "entradas": [
            {"nome": "FUSO", "exemplo": "America/Sao_Paulo", "obrigatorio": False,
             "nota": "Vazio usa o fuso da conta Google."},
        ],
        "passos": [
            {"titulo": "Conferir o fuso da conta",
             "comando": "gws calendar settings get --params '{\"setting\":\"timezone\"}'",
             "porque": "O ajudante de agenda usa o fuso da conta quando nenhum é passado.",
             "verifica": "o JSON traz `value` com um fuso IANA",
             "risco": "leitura", "simular": False},
            {"titulo": "Listar os compromissos",
             "comando": "gws calendar +agenda --today --timezone \"$FUSO\"",
             "porque": "Sem `--today`, a agenda cobre a janela padrão do ajudante.",
             "verifica": "a saída lista eventos com hora de início e participantes",
             "risco": "leitura", "simular": False},
        ],
        "verificacao": "Hoje tem os eventos esperados e nenhum deles está em outro fuso por engano.",
    },
    "standup": {
        "titulo": "Standup de hoje",
        "resumo": "Reúne as reuniões do dia e as tarefas abertas em um resumo.",
        "servicos": ["workflow", "calendar", "tasks"],
        "entradas": [
            {"nome": "FUSO", "exemplo": "America/Sao_Paulo", "obrigatorio": False,
             "nota": "Opcional; o ajudante usa o fuso da conta."},
        ],
        "passos": [
            {"titulo": "Gerar o resumo",
             "comando": "gws workflow +standup-report --timezone \"$FUSO\"",
             "porque": "O ajudante junta reuniões de hoje e tarefas pendentes.",
             "verifica": "o JSON tem as seções de agenda e de tarefas",
             "risco": "leitura", "simular": False},
        ],
        "verificacao": "As reuniões de hoje e as tarefas em aberto aparecem no mesmo resumo.",
    },
    "digest-semanal": {
        "titulo": "Digest da semana",
        "resumo": "Conta as reuniões da semana e os e-mails não lidos.",
        "servicos": ["workflow"],
        "entradas": [
            {"nome": "FUSO", "exemplo": "America/Sao_Paulo", "obrigatorio": False,
             "nota": "Opcional; vale para a janela da semana."},
        ],
        "passos": [
            {"titulo": "Gerar o digest",
             "comando": "gws workflow +weekly-digest --timezone \"$FUSO\"",
             "porque": "Uma chamada produz o resumo semanal.",
             "verifica": "o JSON traz contagem de reuniões e de não lidos",
             "risco": "leitura", "simular": False},
        ],
        "verificacao": "As contagens batem com a agenda e a caixa de entrada.",
    },
    "triagem-da-caixa": {
        "titulo": "Triagem da caixa",
        "resumo": "Lista remetente, assunto e data dos não lidos, com paginação.",
        "servicos": ["gmail"],
        "entradas": [
            {"nome": "CONSULTA", "exemplo": "is:unread newer_than:2d", "obrigatorio": False,
             "nota": "Vazio usa `is:unread`."},
        ],
        "passos": [
            {"titulo": "Resumo rápido",
             "comando": "gws gmail +triage",
             "porque": "O ajudante já devolve remetente, assunto e data.",
             "verifica": "a saída lista mensagens recentes",
             "risco": "leitura", "simular": False},
            {"titulo": "Coletar com paginação",
             "comando": "gws gmail users messages list --params '{\"userId\":\"me\",\"q\":\"$CONSULTA\",\"maxResults\":100}' --page-all --page-limit 5",
             "porque": "A triagem mostra uma amostra; a lista pagina.",
             "verifica": "cada linha NDJSON tem `messages` e o último não tem `nextPageToken`",
             "risco": "leitura", "simular": False},
        ],
        "verificacao": "A soma de mensagens por página bate com o total que a interface mostra.",
    },
    "enviar-email": {
        "titulo": "Enviar e-mail",
        "resumo": "Ensaia o envio, confere destinatário e assunto e só então envia.",
        "servicos": ["gmail"],
        "entradas": [
            {"nome": "PARA", "exemplo": "ana@exemplo.com", "obrigatorio": True, "nota": "Um ou mais endereços."},
            {"nome": "ASSUNTO", "exemplo": "Fechamento de outubro", "obrigatorio": True, "nota": "Texto curto."},
            {"nome": "CORPO", "exemplo": "Segue o resumo da semana.", "obrigatorio": True, "nota": "Texto puro."},
        ],
        "passos": [
            {"titulo": "Ensaiar",
             "comando": "gws gmail +send --to \"$PARA\" --subject \"$ASSUNTO\" --body \"$CORPO\" --dry-run",
             "porque": "O ensaio imprime o pedido sem enviar.",
             "verifica": "o JSON traz o `raw` com o cabeçalho `To:` correto",
             "risco": "leitura", "simular": True},
            {"titulo": "Enviar",
             "comando": "gws gmail +send --to \"$PARA\" --subject \"$ASSUNTO\" --body \"$CORPO\"",
             "porque": "Repetição sem `--dry-run` envia de verdade.",
             "verifica": "a resposta traz `id` e `threadId` do envio",
             "risco": "escrita", "simular": False},
        ],
        "verificacao": "O e-mail aparece em Enviados com o destinatário e o assunto ensaiados.",
        "rollback": "Não existe desfazer envio; confira o ensaio antes de repetir.",
    },
    "responder-email": {
        "titulo": "Responder e-mail",
        "resumo": "Confere a mensagem original e responde mantendo a conversa.",
        "servicos": ["gmail"],
        "entradas": [
            {"nome": "MENSAGEM", "exemplo": "18f2c9a1b7d4", "obrigatorio": True, "nota": "ID da mensagem."},
            {"nome": "CORPO", "exemplo": "Obrigado, resolvido.", "obrigatorio": True, "nota": "Texto puro."},
        ],
        "passos": [
            {"titulo": "Ler a original",
             "comando": "gws gmail users messages get --params '{\"userId\":\"me\",\"id\":\"$MENSAGEM\",\"format\":\"metadata\"}'",
             "porque": "O `threadId` e o remetente definem a resposta certa.",
             "verifica": "o JSON traz `threadId` e o cabeçalho `From`",
             "risco": "leitura", "simular": False},
            {"titulo": "Ensaiar a resposta",
             "comando": "gws gmail +reply --message-id \"$MENSAGEM\" --body \"$CORPO\" --dry-run",
             "porque": "O ajudante monta o cabeçalho `In-Reply-To`.",
             "verifica": "o `raw` cita o `Message-ID` original",
             "risco": "leitura", "simular": True},
            {"titulo": "Responder",
             "comando": "gws gmail +reply --message-id \"$MENSAGEM\" --body \"$CORPO\"",
             "porque": "Sem ensaio, um erro de thread vira resposta solta.",
             "verifica": "a resposta aparece na mesma conversa",
             "risco": "escrita", "simular": False},
        ],
        "verificacao": "A resposta está na mesma thread e com o destinatário original.",
        "rollback": "Não existe desfazer envio; se errado, responda corrigindo e registre o ocorrido.",
    },
    "ler-planilha": {
        "titulo": "Ler planilha",
        "resumo": "Lê um intervalo e confere o cabeçalho antes de usar os valores.",
        "servicos": ["sheets"],
        "entradas": [
            {"nome": "PLANILHA", "exemplo": "1AbC...", "obrigatorio": True, "nota": "ID da planilha."},
            {"nome": "INTERVALO", "exemplo": "Vendas!A1:F50", "obrigatorio": True,
             "nota": "Aba e intervalo; o `!` exige aspas simples."},
        ],
        "passos": [
            {"titulo": "Ler o intervalo",
             "comando": "gws sheets +read --spreadsheet \"$PLANILHA\" --range \"$INTERVALO\"",
             "porque": "O ajudante devolve as linhas já normalizadas.",
             "verifica": "o JSON traz `values` com a primeira linha de cabeçalho",
             "risco": "leitura", "simular": False},
        ],
        "verificacao": "A primeira linha tem os nomes de coluna que você espera e nenhuma coluna ficou de fora.",
    },
    "acrescentar-linha": {
        "titulo": "Acrescentar linha",
        "resumo": "Confere o cabeçalho, ensaia o append e acrescenta uma linha.",
        "servicos": ["sheets"],
        "entradas": [
            {"nome": "PLANILHA", "exemplo": "1AbC...", "obrigatorio": True, "nota": "ID da planilha."},
            {"nome": "ABA", "exemplo": "Vendas", "obrigatorio": True, "nota": "Nome da aba."},
            {"nome": "VALORES", "exemplo": "Ana,95,2026-10-23", "obrigatorio": True,
             "nota": "Valores separados por vírgula, na ordem do cabeçalho."},
        ],
        "passos": [
            {"titulo": "Conferir o cabeçalho",
             "comando": "gws sheets +read --spreadsheet \"$PLANILHA\" --range \"$ABA!A1:Z1\"",
             "porque": "A ordem das colunas define a ordem dos valores.",
             "verifica": "o cabeçalho tem a mesma quantidade de colunas dos valores",
             "risco": "leitura", "simular": False},
            {"titulo": "Ensaiar o append",
             "comando": "gws sheets +append --spreadsheet \"$PLANILHA\" --range \"$ABA!A1\" --values \"$VALORES\" --dry-run",
             "porque": "Mostra o `values` final sem gravar.",
             "verifica": "o corpo traz uma linha com os valores na ordem certa",
             "risco": "leitura", "simular": True},
            {"titulo": "Acrescentar",
             "comando": "gws sheets +append --spreadsheet \"$PLANILHA\" --range \"$ABA!A1\" --values \"$VALORES\"",
             "porque": "O append escreve no fim do intervalo.",
             "verifica": "a resposta traz `updates.updatedRange` com a linha nova",
             "risco": "escrita", "simular": False},
        ],
        "verificacao": "A linha nova está no fim da aba e os tipos foram interpretados como esperado.",
        "rollback": "Desfazer no histórico da planilha; o append não tem inverso automático.",
    },
    "subir-arquivo": {
        "titulo": "Subir arquivo",
        "resumo": "Ensaia o upload com metadados, envia e confere o arquivo na pasta.",
        "servicos": ["drive"],
        "entradas": [
            {"nome": "ARQUIVO", "exemplo": "/home/ana/relatorio.pdf", "obrigatorio": True,
             "nota": "Caminho local do binário."},
            {"nome": "NOME", "exemplo": "Relatório de outubro", "obrigatorio": True, "nota": "Nome no Drive."},
            {"nome": "PASTA", "exemplo": "1Pasta...", "obrigatorio": False,
             "nota": "Vazio sobe na raiz do Meu Drive."},
        ],
        "passos": [
            {"titulo": "Ensaiar o envio",
             "comando": "gws drive files create --json '{\"name\":\"$NOME\",\"parents\":[\"$PASTA\"]}' --upload \"$ARQUIVO\" --dry-run",
             "porque": "Confere nome, pasta e tipo do arquivo sem subir.",
             "verifica": "o pedido mostra `uploadType=multipart` e o nome certo",
             "risco": "leitura", "simular": True},
            {"titulo": "Enviar",
             "comando": "gws drive files create --json '{\"name\":\"$NOME\",\"parents\":[\"$PASTA\"]}' --upload \"$ARQUIVO\"",
             "porque": "O mesmo pedido, agora de verdade.",
             "verifica": "a resposta traz `id` e `size` do arquivo",
             "risco": "escrita", "simular": False},
            {"titulo": "Confirmar na pasta",
             "comando": "gws drive files list --params '{\"q\":\"name = '\\''$NOME'\\'' and trashed = false\",\"fields\":\"files(id,name,size,webViewLink)\"}'",
             "porque": "A criação não prova que o arquivo ficou na pasta esperada.",
             "verifica": "o `id` coincide com o retorno do envio",
             "risco": "leitura", "simular": False},
        ],
        "verificacao": "O arquivo existe uma vez, com o nome e a pasta ensaiados.",
        "rollback": "Mover para a lixeira com `files trash` se o upload estiver duplicado.",
    },
    "organizar-pasta": {
        "titulo": "Organizar pasta",
        "resumo": "Lista os filhos de uma pasta e move os que casam com um filtro.",
        "servicos": ["drive"],
        "entradas": [
            {"nome": "ORIGEM", "exemplo": "1PastaOrigem...", "obrigatorio": True, "nota": "ID da pasta de origem."},
            {"nome": "DESTINO", "exemplo": "1PastaDestino...", "obrigatorio": True, "nota": "ID da pasta de destino."},
            {"nome": "FILTRO", "exemplo": "mimeType = 'application/pdf'", "obrigatorio": False,
             "nota": "Consulta q adicional; vazio move todos os filhos."},
        ],
        "passos": [
            {"titulo": "Listar os filhos",
             "comando": "gws drive files list --params '{\"q\":\"'\\''$ORIGEM'\\'' in parents and trashed = false and $FILTRO\",\"pageSize\":100,\"fields\":\"files(id,name,mimeType),nextPageToken\"}' --page-all",
             "porque": "A mudança de pai exige os IDs reais.",
             "verifica": "o NDJSON terminou sem `nextPageToken`",
             "risco": "leitura", "simular": False},
            {"titulo": "Mover um arquivo por vez",
             "comando": "gws drive files update --params '{\"fileId\":\"$ARQUIVO\",\"addParents\":\"$DESTINO\",\"removeParents\":\"$ORIGEM\",\"fields\":\"id,parents\"}'",
             "porque": "Não há lote de pais; cada arquivo é uma chamada.",
             "verifica": "a resposta lista `parents` só com o destino",
             "risco": "escrita", "simular": False},
        ],
        "verificacao": "A pasta de origem ficou vazia para o filtro e o destino tem todos os arquivos.",
        "rollback": "Repetir o update invertendo `addParents` e `removeParents`.",
    },
    "convidar-evento": {
        "titulo": "Criar evento com convidados",
        "resumo": "Ensaiar o evento, criar e conferir a lista de participantes.",
        "servicos": ["calendar"],
        "entradas": [
            {"nome": "CALENDARIO", "exemplo": "primary", "obrigatorio": False, "nota": "Vazio usa `primary`."},
            {"nome": "RESUMO", "exemplo": "Revisão do trimestre", "obrigatorio": True, "nota": "Título do evento."},
            {"nome": "INICIO", "exemplo": "2026-11-03T10:00:00-03:00", "obrigatorio": True, "nota": "ISO 8601 com fuso."},
            {"nome": "FIM", "exemplo": "2026-11-03T11:00:00-03:00", "obrigatorio": True, "nota": "ISO 8601 com fuso."},
            {"nome": "CONVIDADOS", "exemplo": "ana@exemplo.com,bruno@exemplo.com", "obrigatorio": False,
             "nota": "Lista separada por vírgula; vazio cria sem convidados."},
        ],
        "passos": [
            {"titulo": "Ensaiar o evento",
             "comando": "gws calendar events insert --params '{\"calendarId\":\"$CALENDARIO\"}' --json '{\"summary\":\"$RESUMO\",\"start\":{\"dateTime\":\"$INICIO\"},\"end\":{\"dateTime\":\"$FIM\"}}' --dry-run",
             "porque": "Confere datas e fuso antes de notificar convidados.",
             "verifica": "o corpo tem `start` e `end` com o mesmo fuso",
             "risco": "leitura", "simular": True},
            {"titulo": "Criar",
             "comando": "gws calendar events insert --params '{\"calendarId\":\"$CALENDARIO\"}' --json '{\"summary\":\"$RESUMO\",\"start\":{\"dateTime\":\"$INICIO\"},\"end\":{\"dateTime\":\"$FIM\"},\"attendees\":[\"$CONVIDADOS\"]}'",
             "porque": "O `attendees` dispara os convites.",
             "verifica": "a resposta traz `id` e `htmlLink`",
             "risco": "escrita", "simular": False},
            {"titulo": "Conferir participantes",
             "comando": "gws calendar events get --params '{\"calendarId\":\"$CALENDARIO\",\"eventId\":\"$EVENTO\"}'",
             "porque": "Convite enviado não é convite aceito.",
             "verifica": "`attendees[].responseStatus` foi preenchido",
             "risco": "leitura", "simular": False},
        ],
        "verificacao": "O evento está no calendário certo, no fuso certo, com os convidados esperados.",
        "rollback": "Apagar o evento errado com `events delete` avisa os convidados; avise antes.",
    },
    "arquivar-rotulados": {
        "titulo": "Arquivar por rótulo",
        "resumo": "Lista as mensagens de um rótulo e tira o `INBOX` em lotes.",
        "servicos": ["gmail"],
        "entradas": [
            {"nome": "ROTULO", "exemplo": "Label_12", "obrigatorio": True, "nota": "ID do rótulo, não o nome."},
            {"nome": "LIMITE", "exemplo": "200", "obrigatorio": False, "nota": "Máximo de mensagens; vazio usa 200."},
        ],
        "passos": [
            {"titulo": "Resolver o ID do rótulo",
             "comando": "gws gmail users labels list --params '{\"userId\":\"me\"}'",
             "porque": "O filtro usa o ID (`Label_12`), não o nome exibido.",
             "verifica": "o ID corresponde ao nome que você vê na interface",
             "risco": "leitura", "simular": False},
            {"titulo": "Listar as mensagens",
             "comando": "gws gmail users messages list --params '{\"userId\":\"me\",\"q\":\"label:$ROTULO\",\"maxResults\":100}' --page-all --page-limit 2",
             "porque": "A lista devolve só IDs; o lote precisa deles.",
             "verifica": "a soma por página cobre o `LIMITE`",
             "risco": "leitura", "simular": False},
            {"titulo": "Arquivar em lote",
             "comando": "gws gmail users messages batchModify --params '{\"userId\":\"me\"}' --json '{\"ids\":[\"<ids>\"],\"removeLabelIds\":[\"INBOX\"]}' --dry-run",
             "porque": "`batchModify` aceita até 1000 IDs por chamada.",
             "verifica": "o corpo tem exatamente os IDs listados, sem repetição",
             "risco": "escrita", "simular": True},
        ],
        "verificacao": "As mensagens do rótulo saíram da caixa de entrada e continuam no rótulo.",
        "rollback": "Reaplicar `addLabelIds: [\"INBOX\"]` no mesmo lote.",
    },
    "tarefa-do-email": {
        "titulo": "Tarefa a partir de e-mail",
        "resumo": "Transforma uma mensagem em tarefa e confere a lista escolhida.",
        "servicos": ["workflow", "tasks", "gmail"],
        "entradas": [
            {"nome": "MENSAGEM", "exemplo": "18f2c9a1b7d4", "obrigatorio": True, "nota": "ID da mensagem."},
            {"nome": "LISTA", "exemplo": "Minhas tarefas", "obrigatorio": False, "nota": "Lista de destino."},
        ],
        "passos": [
            {"titulo": "Conferir a mensagem",
             "comando": "gws gmail users messages get --params '{\"userId\":\"me\",\"id\":\"$MENSAGEM\",\"format\":\"metadata\"}'",
             "porque": "Assunto e remetente viram o título da tarefa.",
             "verifica": "o JSON traz `snippet` e o assunto",
             "risco": "leitura", "simular": False},
            {"titulo": "Criar a tarefa",
             "comando": "gws workflow +email-to-task --message-id \"$MENSAGEM\" --tasklist \"$LISTA\"",
             "porque": "O ajudante copia assunto, remetente e link.",
             "verifica": "a resposta traz o `id` da tarefa criada",
             "risco": "escrita", "simular": False},
        ],
        "verificacao": "A tarefa está na lista certa, com o link para a mensagem.",
        "rollback": "Apagar a tarefa criada com `tasks delete`.",
    },
    "relatorio-de-planilha": {
        "titulo": "Relatório a partir da planilha",
        "resumo": "Lê os dados, resume com `jq` e escreve o texto em um Doc.",
        "servicos": ["sheets", "docs"],
        "entradas": [
            {"nome": "PLANILHA", "exemplo": "1AbC...", "obrigatorio": True, "nota": "ID da planilha."},
            {"nome": "INTERVALO", "exemplo": "Vendas!A1:F200", "obrigatorio": True, "nota": "Aba e intervalo."},
            {"nome": "DOC", "exemplo": "1Doc...", "obrigatorio": True, "nota": "ID do documento."},
        ],
        "passos": [
            {"titulo": "Ler os dados",
             "comando": "gws sheets +read --spreadsheet \"$PLANILHA\" --range \"$INTERVALO\" > /tmp/planilha.json",
             "porque": "Guarda a leitura para o resumo local.",
             "verifica": "o arquivo termina em `}` e tem `values`",
             "risco": "leitura", "simular": False},
            {"titulo": "Resumir",
             "comando": "jq -r '.values[] | @tsv' /tmp/planilha.json | head -20",
             "porque": "O resumo é texto; nenhuma conta é feita pelo CLI.",
             "verifica": "as linhas têm o mesmo número de colunas do cabeçalho",
             "risco": "leitura", "simular": False},
            {"titulo": "Escrever no Doc",
             "comando": "gws docs +write --document \"$DOC\" --text \"$TEXTO\"",
             "porque": "O ajudante acrescenta texto no fim do documento.",
             "verifica": "o Doc ganhou o bloco e manteve o conteúdo anterior",
             "risco": "escrita", "simular": False},
        ],
        "verificacao": "O Doc tem o resumo e a planilha segue intacta.",
        "rollback": "O Doc guarda o histórico de versões; volte a uma versão anterior.",
    },
    "checar-arquivos-grandes": {
        "titulo": "Arquivos grandes",
        "resumo": "Lista os maiores arquivos do Drive para decidir o que limpar.",
        "servicos": ["drive"],
        "entradas": [
            {"nome": "MINIMO", "exemplo": "10485760", "obrigatorio": False,
             "nota": "Tamanho mínimo em bytes; vazio usa 10 MB."},
        ],
        "passos": [
            {"titulo": "Coletar os arquivos",
             "comando": "gws drive files list --params '{\"q\":\"trashed = false\",\"pageSize\":1000,\"fields\":\"files(id,name,size,mimeType,owners),nextPageToken\"}' --page-all",
             "porque": "Sem `--page-all` você vê só a primeira página.",
             "verifica": "o NDJSON terminou sem `nextPageToken`",
             "risco": "leitura", "simular": False},
            {"titulo": "Ordenar por tamanho",
             "comando": "jq -s '[.[].files[]] | sort_by(-(.size|tonumber)) | .[0:20] | .[] | \"\\(.size)\\t\\(.name)\"'",
             "porque": "A API não ordena por tamanho; o `jq` ordena localmente.",
             "verifica": "os números vêm decrescentes e `size` é string numérica",
             "risco": "leitura", "simular": False},
        ],
        "verificacao": "A lista aponta arquivos que existem e cujo tamanho você reconhece.",
    },
}


def _receita_por_id(receita: str) -> dict[str, Any]:
    chave = _slug(receita)
    if chave not in RECEITAS:
        raise EscritorioError(
            f"Receita desconhecida: `{receita}`. Disponíveis: {', '.join(sorted(RECEITAS))}."
        )
    return {"id": chave, **RECEITAS[chave]}


def planejar_receita(*, receita: str, entradas: str, simular: bool, modo: str) -> dict[str, Any]:
    plano = _receita_por_id(receita)
    valores = _json_obj(entradas, "Entradas")
    achados: list[dict[str, Any]] = []
    faltando: list[str] = []
    for entrada in plano["entradas"]:
        chave = entrada["nome"]
        valor = str(valores.get(chave, "") or "").strip()
        if entrada["obrigatorio"] and not valor:
            faltando.append(chave)
            achados.append(finding(
                "must", "entrada-faltando", "Entrada obrigatória vazia", chave,
                entrada["nota"],
                f"Sem `{chave}`, o passo não tem como montar o comando.",
                f"Defina `{chave}` (exemplo: {entrada['exemplo']}).",
                "O comando sai com o marcador literal e falha no CLI.",
            ))
        elif not valor and entrada["exemplo"]:
            achados.append(finding(
                "nice", "entrada-padrao", "Entrada opcional vazia", chave,
                entrada["nota"],
                f"`{chave}` vai ficar como marcador `${{{chave}}}`.",
                f"Preencha ou use o exemplo `{entrada['exemplo']}`.",
                "Você precisa substituir o marcador na hora de rodar.",
            ))
    passos: list[dict[str, Any]] = []
    for indice, passo in enumerate(plano["passos"], start=1):
        comando = passo["comando"]
        for entrada in plano["entradas"]:
            comando = comando.replace(f"${entrada['nome']}", str(valores.get(entrada["nome"], "") or f"${{{entrada['nome']}}}"))
        passo_simulado = bool(passo["simular"]) or (simular and passo["risco"] != "leitura" and "--dry-run" not in comando)
        if passo_simulado and "--dry-run" not in comando:
            comando = f"{comando} --dry-run"
        passos.append({
            "ordem": indice,
            "titulo": passo["titulo"],
            "comando": comando,
            "porque": passo["porque"],
            "verifica": passo["verifica"],
            "risco": passo["risco"],
            "simular": passo_simulado,
        })
        if passo["risco"] != "leitura" and not passo_simulado:
            achados.append(finding(
                "should", "passo-sem-ensaio", "Passo de escrita sem ensaio", passo["titulo"],
                "Todo passo que grava precisa de um ensaio equivalente.",
                "Sem `--dry-run` o primeiro erro acontece já gravando.",
                "Duplique o passo com `--dry-run` e confira o corpo.",
                "Uma escrita errada custa correção manual.",
            ))
    if simular and any(passo["risco"] != "leitura" for passo in passos):
        achados.append(finding(
            "nice", "ensaio-global", "Plano inteiro em ensaio", "--dry-run",
            "Você ligou a simulação: as escritas saem com `--dry-run`.",
            "Os passos de verificação não vão encontrar o efeito que ainda não aconteceu.",
            "Rode uma vez ensaiando, confira os corpos e repita sem simular.",
            "Você acha que o plano falhou quando só não gravou.",
        ))
    servicos = plano["servicos"]
    escopos: list[str] = []
    for servico in servicos:
        familia = SERVICOS.get(servico, {}).get("familia", "")
        if familia == "drive":
            escopos.append("drive.file")
        elif familia == "gmail":
            escopos.extend(["gmail.readonly", "gmail.modify"])
        elif familia == "calendar":
            escopos.extend(["calendar.readonly", "calendar.events"])
        elif familia == "sheets":
            escopos.extend(["spreadsheets.readonly", "spreadsheets"])
        elif familia == "documents":
            escopos.extend(["documents.readonly", "documents"])
        elif familia == "tasks":
            escopos.append("tasks")
        elif familia == "workflow":
            escopos.extend(["calendar.readonly", "gmail.readonly", "tasks"])
    escopos = sorted(set(escopos))
    if len(escopos) > 5:
        achados.append(finding(
            "should", "muitos-escopos", "Receita pede muitos escopos", ", ".join(escopos),
            "Cada serviço novo amplia o consentimento.",
            f"{len(escopos)} escopos numa receita só.",
            "Divida a receita por serviço ou use presets.",
            "O consentimento fica difícil de revisar.",
        ))
    metrics = {
        "passos": len(passos),
        "servicos": len(servicos),
        "escopos": len(escopos),
        "entradas": len(plano["entradas"]),
        "faltando": len(faltando),
        "simulados": sum(1 for passo in passos if passo["simular"]),
    }
    perguntas = []
    if faltando:
        perguntas.append(f"Quem preenche {', '.join(faltando)}?")
    if plano.get("rollback"):
        perguntas.append(f"Se der errado: {plano['rollback']}")
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    extra = ["", "## Passos", ""]
    for passo in passos:
        extra += [
            f"### {passo['ordem']}. {passo['titulo']} · {passo['risco']}",
            "",
            "```bash",
            passo["comando"],
            "```",
            "",
            f"- **Por quê:** {passo['porque']}",
            f"- **Como saber que deu certo:** {passo['verifica']}",
            "",
        ]
    if plano.get("rollback"):
        extra += ["## Se der errado", "", plano["rollback"], ""]
    extra += ["## Escopos", ""] + [f"- `{chave}` — {ESCOPOS.get(chave, {}).get('rotulo', chave)}" for chave in escopos]
    rows = [{
        "ordem": passo["ordem"], "titulo": passo["titulo"], "risco": passo["risco"],
        "simular": passo["simular"], "comando": passo["comando"], "verifica": passo["verifica"],
    } for passo in passos]
    return {
        **common(
            analysis=f"escritorio.receita · {plano['id']}",
            mode=modo,
            title=f"Receita · {plano['titulo']}",
            summary=[
                plano["resumo"],
                f"{len(passos)} passos em {len(servicos)} serviço(s), risco máximo "
                f"**{max((passo['risco'] for passo in passos), key=lambda r: ['leitura', 'escrita', 'destrutivo'].index(r), default='leitura')}**.",
                "Nada é executado: os comandos são texto para você revisar e rodar.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=rows,
            metrics=metrics,
            limitations=LIMITES_RECEITA,
            extra_sections=extra,
        ),
        "receita": plano["id"],
        "titulo": plano["titulo"],
        "passos": passos,
        "entradas": plano["entradas"],
        "escopos": [_escopo_detalhe(chave) for chave in escopos],
        "verificacao": plano["verificacao"],
        "rollback": plano.get("rollback", ""),
        "executado": False,
    }


LIMITES_RECEITA = [
    "Os comandos são texto: nenhuma chamada ao Google acontece e nenhuma credencial é lida.",
    "As flags dos ajudantes (`+send`, `+append`…) vêm do README do upstream; confirme com `gws <serviço> <ajudante> --help`.",
    "Marcadores `${NOME}` que sobrarem precisam ser substituídos por você antes de rodar.",
    "A receita não simula resultado: ela só ordena passos, ensaios e verificações.",
]


# ------------------------------------------------------------------ páginas

CHAVES_ITENS = [
    "files", "messages", "threads", "drafts", "labels", "history", "items", "events",
    "spaces", "users", "values", "responses", "tasks", "courses", "changes",
    "permissions", "calendars", "channels", "members", "replies",
]


def _paginas_do_texto(texto: str) -> list[dict[str, Any]]:
    bruto = texto.strip()
    if not bruto:
        raise EscritorioError("Cole ao menos uma página JSON.")
    paginas: list[dict[str, Any]] = []
    if bruto.startswith("["):
        valor = _json_any(bruto, "Páginas")
        if not isinstance(valor, list) or not all(isinstance(item, dict) for item in valor):
            raise EscritorioError("O array precisa conter objetos JSON, um por página.")
        paginas = list(valor)
    elif bruto.startswith("{"):
        decodificador = json.JSONDecoder()
        indice = 0
        while indice < len(bruto):
            while indice < len(bruto) and bruto[indice] in " \t\r\n":
                indice += 1
            if indice >= len(bruto):
                break
            try:
                valor, fim = decodificador.raw_decode(bruto, indice)
            except json.JSONDecodeError as erro:
                raise EscritorioError(
                    f"Página inválida na linha {erro.lineno}, coluna {erro.colno}: {erro.msg}."
                ) from erro
            if not isinstance(valor, dict):
                raise EscritorioError("Cada página precisa ser um objeto JSON.")
            paginas.append(valor)
            indice = fim
    else:
        raise EscritorioError("O texto precisa começar com `{` (uma página ou NDJSON) ou `[` (lista de páginas).")
    if not paginas:
        raise EscritorioError("Nenhuma página encontrada no texto.")
    if len(paginas) > 500:
        raise EscritorioError("Mais de 500 páginas num pedido só; divida a leitura.")
    return paginas


def _itens_da_pagina(pagina: dict[str, Any], chave: str) -> tuple[str, list[Any]]:
    if chave:
        valor = pagina.get(chave)
        if valor is None:
            return chave, []
        return chave, valor if isinstance(valor, list) else [valor]
    candidatas = [nome for nome in CHAVES_ITENS if isinstance(pagina.get(nome), list)]
    if not candidatas:
        return "", []
    if len(candidatas) > 1:
        candidatas.sort(key=lambda nome: len(pagina.get(nome, [])), reverse=True)
    return candidatas[0], list(pagina.get(candidatas[0]) or [])


def ler_paginas(
    *,
    paginas: str,
    chave_itens: str,
    campo_id: str,
    comando_base: str,
    params_base: str,
    modo: str,
) -> dict[str, Any]:
    lista = _paginas_do_texto(paginas)
    achados: list[dict[str, Any]] = []
    tokens: list[str] = []
    vistos: set[str] = set()
    duplicados = 0
    sem_id = 0
    itens_total = 0
    chaves: set[str] = set()
    rows: list[dict[str, Any]] = []
    ids: list[str] = []

    for indice, pagina in enumerate(lista, start=1):
        if "error" in pagina:
            achados.append(finding(
                "must", "pagina-com-erro", "Página trouxe erro", f"página {indice}",
                "A resposta tem o objeto `error` do Google.",
                "Uma página com erro no meio da coleta invalida o total.",
                "Pare a coleta, triague o erro e só então repita a paginação.",
                "O total fica incompleto sem aviso.",
            ))
        chave, itens = _itens_da_pagina(pagina, chave_itens.strip())
        if chave:
            chaves.add(chave)
        if chave_itens.strip() and chave_itens.strip() not in pagina:
            achados.append(finding(
                "should", "chave-ausente", "Chave de itens ausente", f"página {indice}",
                f"A chave `{chave_itens.strip()}` não existe nessa página.",
                "A página pode ser de outro método ou estar vazia.",
                "Confira a chave (`files`, `messages`, `values`…) ou deixe o campo vazio.",
                "A contagem sai zerada mesmo com dados.",
            ))
        for item in itens:
            itens_total += 1
            if isinstance(item, str):
                identificador = item
            elif isinstance(item, dict):
                identificador = str(item.get(campo_id.strip() or "id", "") or "")
            else:
                identificador = ""
            if not identificador:
                sem_id += 1
                continue
            ids.append(identificador)
            if identificador in vistos:
                duplicados += 1
            else:
                vistos.add(identificador)
        token = str(pagina.get("nextPageToken", "") or "")
        if token:
            tokens.append(token)
        rows.append({
            "pagina": indice,
            "chave": chave or "—",
            "itens": len(itens),
            "unicos": len({str(item.get(campo_id.strip() or "id", "") or item) if isinstance(item, dict) else str(item) for item in itens}),
            "token": token[:24] if token else "",
            "sync": str(pagina.get("nextSyncToken", "") or "")[:24],
        })

    # laço: token repetido entre páginas
    if len(tokens) != len(set(tokens)):
        achados.append(finding(
            "must", "pagina-repetida", "Token repetido entre páginas", "nextPageToken",
            "Duas páginas seguidas trouxeram o mesmo token.",
            "A paginação entrou em laço: a segunda página repetiu a primeira.",
            "Pare, descarte as duplicatas e recomece a coleta do zero.",
            "A coleta não termina e o total fica inflado.",
        ))
    if len(chaves) > 1:
        achados.append(finding(
            "should", "chaves-misturadas", "Chaves de itens diferentes", ", ".join(sorted(chaves)),
            "Páginas do mesmo comando precisam da mesma chave.",
            "Misturar `messages` com `threads` soma coisas diferentes.",
            "Fixe a chave no campo próprio ou colete um método por vez.",
            "O total mistura mensagens e conversas.",
        ))
    completa = not tokens
    if not completa:
        achados.append(finding(
            "should", "pagina-incompleta", "A coleta terminou antes do fim", f"{len(tokens)} token(s)",
            "A última página ainda tem `nextPageToken`.",
            "Você está lendo uma amostra, não o conjunto.",
            "Continue com o token da última página ou use `--page-all`.",
            "A soma por página fica abaixo do total real.",
        ))
    if duplicados:
        achados.append(finding(
            "should", "ids-repetidos", "IDs repetidos na coleta", f"{duplicados} repetição(ões)",
            "O mesmo ID apareceu em mais de uma página.",
            "Reenvio de página ou sobreposição de janela.",
            "Deduplique pelo ID antes de agir em lote.",
            "O lote processa o mesmo item duas vezes.",
        ))
    if sem_id:
        achados.append(finding(
            "should", "item-sem-id", "Item sem identificador", f"{sem_id} item(ns)",
            f"O campo `{campo_id.strip() or 'id'}` não veio no item.",
            "Sem ID não há como chamar o método seguinte.",
            "Peça o campo em `fields` ou use outro campo de identidade.",
            "O item fica de fora do lote.",
        ))
    if itens_total and all(isinstance(item, str) for pagina in lista for item in _itens_da_pagina(pagina, chave_itens.strip())[1]):
        achados.append(finding(
            "nice", "itens-finos", "Itens só com ID", f"{itens_total} item(ns)",
            "A lista devolveu apenas identificadores.",
            "Cada detalhe exige uma chamada `get` extra.",
            "Peça `fields` na lista ou prepare um lote de leitura.",
            "Você planeja um lote sem saber o custo real.",
        ))

    proximo = ""
    if not completa and comando_base.strip():
        params = _json_obj(params_base, "Parâmetros base")
        params["pageToken"] = tokens[-1]
        proximo = f"{comando_base.strip()} --params {_quote(_compacto(params))}"
    elif not completa:
        proximo = "Repita o mesmo comando com `--params` incluindo `pageToken` da última página."

    metrics = {
        "paginas": len(lista),
        "itens": itens_total,
        "unicos": len(vistos),
        "duplicados": duplicados,
        "sem_id": sem_id,
        "tokens": len(tokens),
        "completa": completa,
    }
    perguntas = []
    if not completa:
        perguntas.append("Quantas páginas faltam e qual é o volume esperado no total?")
    if duplicados:
        perguntas.append("De onde vem a sobreposição: reenvio ou janela de consulta?")
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)

    extra = ["", "## Páginas", ""]
    for row in rows:
        extra += [f"- Página {row['pagina']}: {row['itens']} item(ns), chave `{row['chave']}`"
                  + (f", token `{row['token']}…`" if row["token"] else ", sem token")]
    if proximo:
        extra += ["", "## Próxima chamada", "", "```bash", proximo, "```"]
    if ids:
        extra += ["", "## IDs", "", "```", " ".join(ids[:50]) + (" …" if len(ids) > 50 else ""), "```"]

    return {
        **common(
            analysis="escritorio.paginas",
            mode=modo,
            title="Leitura de páginas",
            summary=[
                f"{len(lista)} página(s), {itens_total} item(ns), {len(vistos)} único(s).",
                "A coleta está **completa**." if completa else "A coleta está **incompleta**: ainda há token.",
                "Nada foi baixado: o texto colado é a única fonte.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=rows,
            metrics=metrics,
            limitations=LIMITES_PAGINAS,
            extra_sections=extra,
        ),
        "paginas": rows,
        "completa": completa,
        "proximoComando": proximo,
        "ids": ids,
        "executado": False,
    }


LIMITES_PAGINAS = [
    "O parser lê o texto colado; nenhuma página é buscada e nenhum token é validado no servidor.",
    "A chave de itens é inferida por uma lista de campos conhecidos; métodos novos podem usar outro nome.",
    "`nextSyncToken` é lido como informação, não como prova de sincronização completa.",
    "A contagem não conhece itens filtrados pelo próprio Google antes da resposta.",
]


# -------------------------------------------------------------------- lotes

LOTES: dict[str, dict[str, Any]] = {
    "sheets.valores": {
        "rotulo": "Sheets — valores",
        "limite": 100,
        "comando": "gws sheets spreadsheets values batchUpdate --params '{\"spreadsheetId\":\"$PLANILHA\"}'",
        "envelope": "data",
        "verifica": "`totalUpdatedCells` cobre a soma das células enviadas",
        "atomo": True,
    },
    "sheets.requisicoes": {
        "rotulo": "Sheets — requisições",
        "limite": 100,
        "comando": "gws sheets spreadsheets batchUpdate --params '{\"spreadsheetId\":\"$PLANILHA\"}'",
        "envelope": "requests",
        "verifica": "`replies` tem uma entrada por requisição",
        "atomo": True,
    },
    "docs.requisicoes": {
        "rotulo": "Docs — requisições",
        "limite": 100,
        "comando": "gws docs documents batchUpdate --params '{\"documentId\":\"$DOCUMENTO\"}'",
        "envelope": "requests",
        "verifica": "`replies` tem uma entrada por requisição",
        "atomo": True,
    },
    "gmail.ids": {
        "rotulo": "Gmail — IDs",
        "limite": 1000,
        "comando": "gws gmail users messages batchModify --params '{\"userId\":\"me\"}'",
        "envelope": "ids",
        "verifica": "a resposta não traz `failedMessages`",
        "atomo": False,
    },
    "drive.permissoes": {
        "rotulo": "Drive — permissões",
        "limite": 1,
        "comando": "gws drive permissions create --params '{\"fileId\":\"$ARQUIVO\"}'",
        "envelope": "",
        "verifica": "cada arquivo tem a permissão nova em `permissions.list`",
        "atomo": False,
    },
    "calendar.eventos": {
        "rotulo": "Calendar — eventos",
        "limite": 1,
        "comando": "gws calendar events insert --params '{\"calendarId\":\"$CALENDARIO\"}'",
        "envelope": "",
        "verifica": "cada evento tem `id` e `htmlLink` próprios",
        "atomo": False,
    },
}


def _validar_item(operacao: str, item: Any, indice: int) -> str:
    if operacao == "sheets.valores":
        if not isinstance(item, dict):
            return "cada item precisa ser um objeto `{range, values}`"
        if not str(item.get("range", "")).strip():
            return "falta `range`"
        if not isinstance(item.get("values"), list) or not item["values"]:
            return "`values` precisa ser uma lista de linhas não vazia"
        if any(not isinstance(linha, list) for linha in item["values"]):
            return "cada linha de `values` precisa ser uma lista"
        return ""
    if operacao in {"sheets.requisicoes", "docs.requisicoes"}:
        if not isinstance(item, dict):
            return "cada requisição precisa ser um objeto"
        if len(item) != 1:
            return "cada requisição precisa ter exatamente uma chave (`updateCells`, `insertText`…)"
        return ""
    if operacao == "gmail.ids":
        valor = item if isinstance(item, str) else (item.get("id") if isinstance(item, dict) else "")
        return "" if str(valor or "").strip() else "cada item precisa ser um ID ou um objeto com `id`"
    if operacao == "drive.permissoes":
        if not isinstance(item, dict):
            return "cada item precisa ser `{fileId, permission}`"
        if not str(item.get("fileId", "")).strip():
            return "falta `fileId`"
        if not isinstance(item.get("permission"), dict) or not item["permission"]:
            return "`permission` precisa ser um objeto não vazio"
        return ""
    if operacao == "calendar.eventos":
        if not isinstance(item, dict):
            return "cada evento precisa ser um objeto"
        if not str(item.get("summary", "")).strip():
            return "falta `summary`"
        inicio = item.get("start")
        fim = item.get("end")
        if not isinstance(inicio, dict) or not isinstance(fim, dict):
            return "`start` e `end` precisam ser objetos"
        return ""
    return "operação desconhecida"


def planejar_lote(
    *,
    operacao: str,
    itens: str,
    parametros: str,
    limite: int,
    simular: bool,
    modo: str,
) -> dict[str, Any]:
    chave = operacao.strip().lower().replace(" ", ".")
    if chave not in LOTES:
        raise EscritorioError(
            f"Operação de lote desconhecida: `{operacao}`. Use uma de: {', '.join(sorted(LOTES))}."
        )
    dados = _json_any(itens, "Itens")
    if not isinstance(dados, list):
        raise EscritorioError("`Itens` precisa ser um array JSON.")
    if not dados:
        raise EscritorioError("A lista de itens está vazia.")
    tabela = LOTES[chave]
    teto = max(1, min(int(limite) if limite else tabela["limite"], tabela["limite"]))
    extra = _json_obj(parametros, "Parâmetros do envelope")
    achados: list[dict[str, Any]] = []
    validos: list[Any] = []
    invalidos: list[dict[str, Any]] = []
    for indice, item in enumerate(dados, start=1):
        motivo = _validar_item(chave, item, indice)
        if motivo:
            invalidos.append({"item": indice, "motivo": motivo})
            achados.append(finding(
                "must", "item-invalido", "Item fora do formato", f"item {indice}",
                tabela["rotulo"],
                motivo,
                "Corrija o item antes de montar o lote.",
                "Um item inválido derruba a chamada inteira." if tabela["atomo"] else "O item fica de fora sem aviso.",
            ))
        else:
            validos.append(item)
    if len(dados) > teto:
        achados.append(finding(
            "should", "acima-do-teto", "Lote acima do teto curado", f"{len(dados)} itens",
            f"O planejamento usa {teto} item(ns) por chamada.",
            "Uma chamada grande demais demora e falha sem meio-termo.",
            f"Divida em lotes de até {teto}.",
            "A chamada pode ser recusada por tamanho.",
        ))
    if teto == 1:
        achados.append(finding(
            "should", "sem-lote", "Operação não tem lote", tabela["rotulo"],
            "Esse método não aceita várias operações por chamada.",
            "O plano vira N chamadas independentes.",
            "Trate cada item como uma escrita própria, com ensaio e verificação.",
            "Você conta uma chamada e faz dezenas.",
        ))
    if tabela["atomo"]:
        achados.append(finding(
            "should", "lote-atomico", "Lote é atômico", tabela["rotulo"],
            "O `batchUpdate` aplica tudo ou nada por chamada.",
            "Um item errado no meio desfaz o lote inteiro.",
            "Valide antes e guarde o corpo para reenviar.",
            "Metade do trabalho não fica gravada.",
        ))

    lotes: list[dict[str, Any]] = []
    passo = teto if teto > 1 else 1
    for numero, inicio in enumerate(range(0, len(validos), passo), start=1):
        fatia = validos[inicio:inicio + passo]
        if tabela["envelope"] == "ids":
            corpo: Any = {**extra, "ids": [item if isinstance(item, str) else item.get("id") for item in fatia]}
        elif tabela["envelope"]:
            corpo = {**extra, tabela["envelope"]: fatia}
        else:
            corpo = {**extra, **fatia[0]}
        comando = f"{tabela['comando']} --json {_quote(_compacto(corpo))}"
        if simular or not tabela["atomo"]:
            comando += " --dry-run"
        lotes.append({
            "numero": numero,
            "itens": len(fatia),
            "comando": comando,
            "corpo": corpo,
        })
    if simular:
        achados.append(finding(
            "nice", "ensaio", "Todo lote sai com ensaio", "--dry-run",
            "Os comandos estão marcados para simulação.",
            "Para gravar, remova `--dry-run` depois de conferir o corpo.",
            "Rode um lote de cada vez e verifique antes do próximo.",
            "Você pode esquecer de remover o flag e achar que gravou.",
        ))
    if not validos:
        achados.append(finding(
            "must", "sem-itens-validos", "Nenhum item válido", tabela["rotulo"],
            "Todos os itens foram recusados pela validação.",
            "Não há lote para montar.",
            "Corrija os itens apontados e repita.",
            "O plano sai vazio.",
        ))

    metrics = {
        "itens": len(dados),
        "validos": len(validos),
        "invalidos": len(invalidos),
        "lotes": len(lotes),
        "chamadas": len(lotes),
        "limite": teto,
    }
    perguntas = []
    if invalidos:
        perguntas.append(f"Quem corrige os {len(invalidos)} item(ns) recusados?")
    if not tabela["atomo"]:
        perguntas.append("Cada escrita independente será ensaiada e conferida antes da próxima?")
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)

    extra_md = ["", "## Lotes", ""]
    for lote in lotes:
        extra_md += [
            f"### Lote {lote['numero']} · {lote['itens']} item(ns)",
            "",
            "```bash",
            lote["comando"],
            "```",
            "",
        ]
    extra_md += ["## Como verificar", "", tabela["verifica"], ""]
    rows = [{"lote": lote["numero"], "itens": lote["itens"], "comando": lote["comando"]} for lote in lotes]

    return {
        **common(
            analysis=f"escritorio.lote · {chave}",
            mode=modo,
            title=f"Lote · {tabela['rotulo']}",
            summary=[
                f"{len(dados)} item(ns), {len(validos)} válido(s), {len(lotes)} lote(s).",
                f"Teto curado: {teto} item(ns) por chamada; "
                f"{'atômico' if tabela['atomo'] else 'uma escrita por item'}.",
                "Nada é enviado: o `--json` é montado a partir do que você colou.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=rows,
            metrics=metrics,
            limitations=LIMITES_LOTE,
            extra_sections=extra_md,
        ),
        "operacao": chave,
        "lotes": lotes,
        "invalidos": invalidos,
        "verificacao": tabela["verifica"],
        "executado": False,
    }


LIMITES_LOTE = [
    "Os tetos por chamada são curados aqui (100 para Sheets/Docs, 1000 para Gmail) e podem mudar no Google.",
    "O planejamento não mede o tamanho em bytes do corpo; um lote dentro do teto ainda pode ser grande demais.",
    "Nenhum lote é enviado: o comando é texto e o `--dry-run` só existe quando você o mantém.",
    "Operações sem lote viram N chamadas e não têm garantia de ordem.",
]


# ------------------------------------------------------------------ escopos

def _operacao_escopo(linha: str) -> dict[str, Any]:
    partes = linha.split()
    servico = partes[0].lower().lstrip("+")
    if servico not in SERVICOS:
        raise EscritorioError(
            f"Serviço desconhecido na linha `{linha}`. Use um de: {', '.join(sorted(SERVICOS))}."
        )
    resto = partes[1:]
    if not resto:
        raise EscritorioError(f"A linha `{linha}` precisa dizer o recurso e o método.")
    ajudante = resto[0] if resto[0].startswith("+") else ""
    recurso = ""
    metodo = ""
    if ajudante:
        if len(resto) > 1:
            raise EscritorioError(f"Ajudantes não usam recurso: `{linha}`.")
    else:
        metodo = resto[-1]
        recurso = ".".join(resto[:-1])
    if ajudante and ajudante not in SERVICOS[servico]["ajudantes"]:
        raise EscritorioError(f"`{servico}` não tem o ajudante `{ajudante}`.")
    escopos = _escopos_do_metodo(servico, recurso, metodo or "list", ajudante)
    risco = "leitura" if (not ajudante and LEITURA.match(metodo or "list")) or ajudante in {"+triage", "+agenda", "+read", "+watch"} else "escrita"
    return {
        "linha": linha,
        "servico": servico,
        "recurso": recurso,
        "metodo": metodo,
        "ajudante": ajudante,
        "escopos": escopos,
        "risco": risco,
    }


def _satisfeito(exigido: str, concedidos: set[str]) -> bool:
    if exigido in concedidos:
        return True
    if exigido.endswith(".readonly") and exigido.split(".")[0] in concedidos:
        return True
    if exigido == "drive.file" and "drive" in concedidos:
        return True
    return False


def _concedido(chave: str) -> str:
    valor = chave.strip()
    prefixo = "https://www.googleapis.com/auth/"
    if valor.startswith(prefixo):
        valor = valor[len(prefixo):]
    return valor


def planejar_escopos(*, operacoes: str, concedidos: str, modo: str) -> dict[str, Any]:
    linhas = _linhas(operacoes)
    if not linhas:
        raise EscritorioError("Liste ao menos uma operação, uma por linha.")
    if len(linhas) > 40:
        raise EscritorioError("Mais de 40 operações num pedido só; divida a revisão.")
    achados: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    exigidos: set[str] = set()
    for linha in linhas:
        op = _operacao_escopo(linha)
        exigidos.update(op["escopos"])
        rows.append({
            "operacao": linha,
            "servico": op["servico"],
            "risco": op["risco"],
            "escopos": ", ".join(op["escopos"]),
        })
    concedidos_lista = [_concedido(item) for item in re.split(r"[,\s]+", concedidos) if item.strip()]
    desconhecidos = sorted({item for item in concedidos_lista if item not in ESCOPOS})
    if desconhecidos:
        achados.append(finding(
            "should", "escopo-desconhecido", "Escopo fora do catálogo", ", ".join(desconhecidos),
            "O catálogo local não reconhece esse escopo.",
            "Pode ser um escopo novo do Google ou um erro de digitação.",
            "Confira a URL no console de credenciais e acrescente ao catálogo se for real.",
            "A comparação trata o escopo como sobra.",
        ))
    concedidos_set = {item for item in concedidos_lista if item in ESCOPOS}
    faltando = sorted(chave for chave in exigidos if not _satisfeito(chave, concedidos_set))
    usados = set(exigidos)
    for chave in list(concedidos_set):
        if chave in usados:
            continue
        if any(exigido.endswith(".readonly") and exigido.split(".")[0] == chave for exigido in exigidos):
            usados.add(chave)
        elif chave == "drive" and "drive.file" in exigidos:
            usados.add(chave)
    sobrando = sorted(concedidos_set - usados)
    if faltando:
        achados.append(finding(
            "must", "escopo-faltando", "Escopo necessário não concedido", ", ".join(faltando),
            "A operação foi mapeada para esse escopo.",
            "Sem ele, a API responde 403 `insufficientPermissions`.",
            f"Reautentique com `gws auth login --scopes {','.join(sorted(exigidos))}`.",
            "O comando falha na primeira chamada.",
        ))
    if sobrando:
        achados.append(finding(
            "should", "escopo-sobrando", "Escopo concedido sem uso", ", ".join(sobrando),
            "A credencial carrega acesso que nenhuma operação declarada usa.",
            "Cada escopo extra amplia o dano possível e o consentimento.",
            "Reautentique só com o necessário; o consentimento antigo fica no navegador até ser revogado.",
            "O app continua com mais poder do que precisa.",
        ))
    if len(exigidos) > LIMITE_ESCOPOS:
        achados.append(finding(
            "must", "escopos-demais", "Acima do limite de consentimento", f"{len(exigidos)} escopos",
            "Apps em teste aceitam cerca de 25 escopos.",
            "Acima disso o login é recusado.",
            "Agrupe serviços ou use presets menores.",
            "O fluxo de consentimento falha antes de abrir.",
        ))
    if "recommended" in PRESETS and len(exigidos) >= 8:
        achados.append(finding(
            "nice", "preset-largo", "Preset largo", "recommended",
            "O preset `recommended` cobre muitos serviços.",
            "É cômodo para uso pessoal e ruim para consentimento mínimo.",
            "Prefira `--scopes` com os escopos que as operações pedem.",
            "Você aceita mais acesso do que o trabalho exige.",
        ))
    comando = f"gws auth login --scopes {','.join(sorted(exigidos))}" if exigidos else ""
    metrics = {
        "operacoes": len(linhas),
        "exigidos": len(exigidos),
        "concedidos": len(concedidos_set),
        "faltando": len(faltando),
        "sobrando": len(sobrando),
        "limite": LIMITE_ESCOPOS,
    }
    perguntas = []
    if sobrando:
        perguntas.append("Algum fluxo não declarado ainda depende dos escopos que sobraram?")
    if len(exigidos) >= 8:
        perguntas.append("Dá para dividir as operações em mais de uma credencial?")
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)

    extra = ["", "## Escopos exigidos", ""]
    for chave in sorted(exigidos):
        detalhe = _escopo_detalhe(chave)
        extra += [f"- `{chave}` — {detalhe['rotulo']} ({detalhe['acesso']}): {detalhe['url']}"]
    if faltando:
        extra += ["", "## Faltando", ""] + [f"- `{chave}`" for chave in faltando]
    if sobrando:
        extra += ["", "## Sobrando", ""] + [f"- `{chave}`" for chave in sobrando]
    if comando:
        extra += ["", "## Reautenticar", "", "```bash", comando, "```", ""]
        extra += ["Para revogar o consentimento antigo, abra https://myaccount.google.com/permissions.", ""]
    return {
        **common(
            analysis="escritorio.escopos",
            mode=modo,
            title="Escopos e consentimento",
            summary=[
                f"{len(linhas)} operação(ões), {len(exigidos)} escopo(s) exigido(s), {len(concedidos_set)} concedido(s).",
                f"Faltam {len(faltando)} e sobram {len(sobrando)}.",
                "Nada é autenticado: a comparação é entre texto e catálogo.",
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=rows,
            metrics=metrics,
            limitations=LIMITES_ESCOPOS,
            extra_sections=extra,
        ),
        "exigidos": [_escopo_detalhe(chave) for chave in sorted(exigidos)],
        "faltando": faltando,
        "sobrando": sobrando,
        "comando": comando,
        "executado": False,
    }


LIMITES_ESCOPOS = [
    "O mapa operação → escopo é curado, não lido da descoberta ao vivo.",
    "Escopos restritos (Gmail, Drive, Calendar) exigem verificação do Google além do consentimento.",
    "O catálogo não julga se o escopo é aprovado para o seu projeto; isso é política do Google Cloud.",
    "Revogar consentimento antigo é ação no navegador, fora destas skills.",
]


# -------------------------------------------------------------------- erros

ERROS: dict[str, dict[str, Any]] = {
    "accessNotConfigured": {
        "grupo": "configuracao", "causa": "A API não está ativada no projeto do Google Cloud.",
        "acao": "Ative a API no projeto e aguarde alguns segundos.",
        "comando": "Abra o `enable_url` do JSON; ou rode `gws auth setup` de novo.",
        "repetir": True, "espera": 10,
    },
    "rateLimitExceeded": {
        "grupo": "cota", "causa": "Cota por projeto estourou.",
        "acao": "Espere e repita; reduza o tamanho da página.",
        "comando": "Repita com `--page-limit 2 --page-delay 1000`.",
        "repetir": True, "espera": 30,
    },
    "userRateLimitExceeded": {
        "grupo": "cota", "causa": "Cota por usuário estourou.",
        "acao": "Espere e repita com folga entre páginas.",
        "comando": "Repita com `--page-delay 1000`.",
        "repetir": True, "espera": 30,
    },
    "quotaExceeded": {
        "grupo": "cota", "causa": "Limite diário do serviço foi atingido.",
        "acao": "Pare até a cota renovar; não insista em laço.",
        "comando": "Nenhum comando resolve agora; reveja o volume.",
        "repetir": False, "espera": 0,
    },
    "backendError": {
        "grupo": "transitorio", "causa": "Falha temporária do lado do Google.",
        "acao": "Repita com espera progressiva.",
        "comando": "Repita a mesma chamada depois de alguns segundos.",
        "repetir": True, "espera": 5,
    },
    "invalid_grant": {
        "grupo": "autenticacao", "causa": "O token expirou ou foi revogado.",
        "acao": "Faça login novamente.",
        "comando": "gws auth login",
        "repetir": False, "espera": 0,
    },
    "invalid_token": {
        "grupo": "autenticacao", "causa": "O token de acesso não é válido.",
        "acao": "Gere um token novo ou faça login.",
        "comando": "gws auth login",
        "repetir": False, "espera": 0,
    },
    "insufficientPermissions": {
        "grupo": "permissoes", "causa": "A credencial não tem o escopo necessário.",
        "acao": "Reautentique com o escopo que a operação pede.",
        "comando": "gws auth login --scopes <lista>",
        "repetir": False, "espera": 0,
    },
    "ACCESS_TOKEN_SCOPE_INSUFFICIENT": {
        "grupo": "permissoes", "causa": "O token foi emitido sem o escopo necessário.",
        "acao": "Reautentique incluindo o escopo faltante.",
        "comando": "gws auth login --scopes <lista>",
        "repetir": False, "espera": 0,
    },
    "redirect_uri_mismatch": {
        "grupo": "configuracao", "causa": "O cliente OAuth não é do tipo Desktop app.",
        "acao": "Crie um cliente Desktop app e baixe o JSON de novo.",
        "comando": "gws auth setup",
        "repetir": False, "espera": 0,
    },
    "notFound": {
        "grupo": "nao-encontrado", "causa": "O ID, o intervalo ou o recurso não existe.",
        "acao": "Confira o identificador antes de repetir.",
        "comando": "Liste o recurso pai para confirmar o ID.",
        "repetir": False, "espera": 0,
    },
    "failedPrecondition": {
        "grupo": "validacao", "causa": "O estado atual não permite a operação.",
        "acao": "Leia o recurso e ajuste o pedido.",
        "comando": "Rode o `get` correspondente.",
        "repetir": False, "espera": 0,
    },
    "invalid": {
        "grupo": "validacao", "causa": "O pedido tem campo ou valor inválido.",
        "acao": "Corrija o corpo ou os parâmetros.",
        "comando": "Rode com `--dry-run` e confira o JSON.",
        "repetir": False, "espera": 0,
    },
}

POR_STATUS: dict[int, str] = {
    400: "invalid", 401: "invalid_token", 403: "insufficientPermissions",
    404: "notFound", 409: "failedPrecondition", 429: "rateLimitExceeded",
    500: "backendError", 503: "backendError",
}


def _extrair_erro(texto: str) -> tuple[str, int, str]:
    reason = ""
    status = 0
    mensagem = ""
    try:
        valor = json.loads(texto)
    except json.JSONDecodeError:
        valor = None
    if isinstance(valor, dict):
        erro = valor.get("error") if isinstance(valor.get("error"), dict) else valor
        if isinstance(erro, dict):
            reason = str(erro.get("reason", "") or "")
            codigo = erro.get("code")
            if isinstance(codigo, int):
                status = codigo
            mensagem = str(erro.get("message", "") or "")
            erros = erro.get("errors")
            if not reason and isinstance(erros, list) and erros and isinstance(erros[0], dict):
                reason = str(erros[0].get("reason", "") or "")
    if not reason:
        achado = re.search(r'"reason"\s*:\s*"([^"]+)"', texto)
        if achado:
            reason = achado.group(1)
    if not status:
        achado = re.search(r'"code"\s*:\s*(\d{3})', texto)
        if achado:
            status = int(achado.group(1))
    if not reason:
        achado = re.search(r"\b(4\d\d|5\d\d)\b", texto)
        if achado:
            status = status or int(achado.group(1))
    if not mensagem:
        achado = re.search(r'"message"\s*:\s*"([^"]+)"', texto)
        if achado:
            mensagem = achado.group(1)
    return reason, status, mensagem


def triar_erro(
    *,
    codigo: int,
    mensagem: str,
    tentativas: int,
    idempotente: bool,
    modo: str,
) -> dict[str, Any]:
    reason, status, detalhe = _extrair_erro(mensagem.strip())
    achados: list[dict[str, Any]] = []
    if codigo not in CODIGOS_SAIDA:
        raise EscritorioError("O código de saída vai de 0 a 5.")
    if codigo == 0 and not reason and not status:
        achados.append(finding(
            "nice", "sem-erro", "Nada a triar", f"código {codigo}",
            "O código de saída é 0 e o texto não traz erro.",
            "Sem erro, não há ação de correção.",
            "Se o problema é outro, cole a mensagem de erro do stderr.",
            "Você fica sem diagnóstico.",
        ))
    chave = reason if reason in ERROS else POR_STATUS.get(status, "")
    if not reason and codigo == 2:
        chave = "invalid_grant"
    if not reason and codigo == 3:
        chave = "invalid"
    if not reason and codigo == 4:
        chave = "backendError"
    if not chave and codigo == 3:
        chave = "invalid"
    if not chave:
        achados.append(finding(
            "should", "erro-desconhecido", "Erro sem classificação", f"código {codigo}",
            "Nem `reason` nem status HTTP foram reconhecidos.",
            "A ação sugerida pode não ser a certa.",
            "Cole a mensagem completa do stderr e o comando que falhou.",
            "Você repete o comando sem entender a causa.",
        ))
    dado = ERROS.get(chave, {})
    repetir = bool(dado.get("repetir", False))
    espera = 0
    if repetir:
        base = int(dado.get("espera", 5))
        espera = min(60, max(base, 2 ** min(tentativas, 5)))
    if repetir and not idempotente:
        achados.append(finding(
            "must", "repetir-escrita", "Não repita escrita às cegas", f"tentativa {tentativas}",
            "A operação grava e pode ter sido aplicada mesmo com erro.",
            "Um retry cego duplica envio, evento ou linha.",
            "Confira o efeito antes de repetir: leia o recurso e compare com o pedido.",
            "O dado é aplicado duas vezes.",
        ))
        repetir = False
        espera = 0
    if chave in {"insufficientPermissions", "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}:
        achados.append(finding(
            "should", "escopo", "Confira o escopo antes do login", chave,
            "Reautenticar sem o escopo certo repete o 403.",
            "O consentimento precisa incluir o escopo que a operação exige.",
            "Rode `escritorio.escopos` com as operações e conceda só o necessário.",
            "O login funciona e a chamada continua negada.",
        ))
    if codigo == 5:
        achados.append(finding(
            "should", "interno", "Erro interno do CLI", f"código {codigo}",
            "O código 5 não vem da API do Google.",
            "Pode ser bug do binário ou do ambiente.",
            "Rode com `GOOGLE_WORKSPACE_CLI_LOG=gws=debug` e guarde o stderr.",
            "Você culpa a API por uma falha local.",
        ))
    if status == 403 and "accessNotConfigured" not in reason:
        achados.append(finding(
            "nice", "403", "403 sem `accessNotConfigured`", reason or "sem reason",
            "Nem todo 403 é cota: pode ser escopo, teste do app ou API desativada.",
            "A correção muda conforme o motivo.",
            "Leia o `reason` antes de reautenticar.",
            "Você reautentica à toa.",
        ))

    triagem = {
        "codigo": codigo,
        "significado": CODIGOS_SAIDA[codigo][0],
        "reason": reason,
        "status": status,
        "grupo": dado.get("grupo", "desconhecido"),
        "causa": dado.get("causa", detalhe or "Causa não identificada."),
        "acao": dado.get("acao", "Cole a mensagem completa do stderr."),
        "comando": dado.get("comando", ""),
        "repetir": repetir,
        "espera": espera,
        "mensagem": detalhe,
    }
    metrics = {
        "codigo": codigo,
        "status": status,
        "reason": reason or "—",
        "grupo": triagem["grupo"],
        "tentativas": tentativas,
        "repetir": repetir,
        "espera": espera,
    }
    perguntas = []
    if repetir:
        perguntas.append(f"Vale esperar {espera}s e repetir, ou o volume já era grande demais?")
    if not idempotente:
        perguntas.append("Como você confirma que a escrita não foi aplicada antes de repetir?")
    achados, counts, veredito, perguntas = finalize(achados, modo, perguntas)

    extra = ["", "## Diagnóstico", ""]
    for rotulo, valor in [
        ("Código", f"{codigo} — {CODIGOS_SAIDA[codigo][0]}"),
        ("Status HTTP", str(status) if status else "—"),
        ("Reason", reason or "—"),
        ("Grupo", triagem["grupo"]),
        ("Causa", triagem["causa"]),
        ("Ação", triagem["acao"]),
        ("Comando", triagem["comando"] or "—"),
        ("Repetir", f"sim, em {espera}s" if repetir else "não"),
    ]:
        extra += [f"- **{rotulo}:** {valor}"]
    if detalhe:
        extra += ["", "## Mensagem", "", "```", detalhe, "```"]
    rows = [{
        "codigo": codigo, "status": status, "reason": reason or "—", "grupo": triagem["grupo"],
        "acao": triagem["acao"], "repetir": repetir, "espera": espera,
    }]

    return {
        **common(
            analysis="escritorio.erros",
            mode=modo,
            title="Triagem de erro",
            summary=[
                f"Código **{codigo}** ({CODIGOS_SAIDA[codigo][0]}); status {status or '—'}; reason `{reason or '—'}`.",
                triagem["causa"],
                "Repetir é " + (f"possível em {espera}s." if repetir else "**não recomendado** agora."),
            ],
            findings=achados,
            counts=counts,
            verdict=veredito,
            questions=perguntas,
            rows=rows,
            metrics=metrics,
            limitations=LIMITES_ERROS,
            extra_sections=extra,
        ),
        "triagem": triagem,
        "executado": False,
    }


LIMITES_ERROS = [
    "A triagem lê o texto e o código de saída; ela não reproduz a chamada nem lê o log do CLI.",
    "O `Retry-After` do Google não é lido: a espera é calculada de forma determinística.",
    "Um erro de escrita pode ter sido aplicado mesmo com resposta de erro; por isso não há retry cego.",
    "A lista de `reason` cobre os casos comuns, não todos os que a API pode devolver.",
]


# ------------------------------------------------------------------ catálogo

def escritorio_catalog() -> dict[str, Any]:
    return {
        "fonte": "googleworkspace/cli (Apache-2.0)",
        "versao": VERSAO,
        "principio": "A descoberta define o comando; o escopo mínimo define o consentimento; escrita nunca repete às cegas.",
        "servicos": [
            {"id": chave, "rotulo": valor["rotulo"], "api": valor["api"],
             "ajudantes": valor["ajudantes"]}
            for chave, valor in sorted(SERVICOS.items())
        ],
        "flags": [
            {"flag": chave, "tipo": valor["tipo"], "padrao": valor["padrao"], "nota": valor["nota"]}
            for chave, valor in FLAGS.items()
        ],
        "codigos": [
            {"codigo": chave, "significado": valor[0], "nota": valor[1]}
            for chave, valor in sorted(CODIGOS_SAIDA.items())
        ],
        "escopos": [
            {"chave": chave, "url": _escopo_url(chave), "rotulo": valor["rotulo"],
             "acesso": valor["acesso"]}
            for chave, valor in sorted(ESCOPOS.items())
        ],
        "presets": [{"id": chave, "escopos": valor} for chave, valor in sorted(PRESETS.items())],
        "receitas": [
            {"id": chave, "titulo": valor["titulo"], "resumo": valor["resumo"],
             "servicos": valor["servicos"], "passos": len(valor["passos"]),
             "entradas": valor["entradas"]}
            for chave, valor in sorted(RECEITAS.items())
        ],
        "lotes": [
            {"operacao": chave, "rotulo": valor["rotulo"], "limite": valor["limite"],
             "comando": valor["comando"], "verifica": valor["verifica"]}
            for chave, valor in sorted(LOTES.items())
        ],
        "erros": [
            {"reason": chave, "grupo": valor["grupo"], "causa": valor["causa"],
             "acao": valor["acao"], "repetir": valor["repetir"]}
            for chave, valor in sorted(ERROS.items())
        ],
        "limites": [
            {"regra": "Escopos em app de teste", "valor": "cerca de 25"},
            {"regra": "Páginas por `--page-all`", "valor": "10 (padrão), ajustável em `--page-limit`"},
            {"regra": "Intervalo entre páginas", "valor": "100 ms (padrão)"},
            {"regra": "Lote de Sheets/Docs", "valor": "100 itens por chamada (curado)"},
            {"regra": "Lote de Gmail", "valor": "1000 IDs por chamada"},
            {"regra": "Códigos de saída", "valor": "0 a 5"},
        ],
        "executado": False,
    }
