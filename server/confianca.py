"""Confiança em skill de terceiro — ficha, risco, permissão, instalação, índice e duplicata.

A camada parte do índice `VoltAgent/awesome-openclaw-skills` (MIT), que reúne
milhares de skills de terceiros do registro OpenClaw, e do `CONTRIBUTING.md`
do mesmo repositório, que fixa o formato de entrada e as regras de aceitação.
Nada do upstream é baixado, importado ou executado: a leitura é lexical sobre
o texto que você cola (SKILL.md, receita de instalação ou índice em Markdown)
e as contas são feitas em Python. Nenhum modelo de linguagem participa.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .review import common, finalize, finding

VERSAO = "0.60.9"
MAX_TEXTO = 200_000
MODOS = ("lite", "full", "ultra")

# Hosts aceitos pelo CONTRIBUTING do índice: só o registro canônico.
HOST_CANONICO = "clawhub.ai"
HOSTS_CONHECIDOS = {
    "clawhub.ai": "registro canônico",
    "www.clawhub.ai": "registro canônico com www",
    "clawskills.sh": "espelho do curador",
    "clawhub.com": "domínio parecido, não é o registro",
}
DESC_MAX_PALAVRAS = 10

# Ferramenta declarada -> capacidade que ela concede.
FERRAMENTAS_CAPACIDADE = {
    "bash": "execucao", "exec": "execucao", "shell": "execucao", "terminal": "execucao",
    "process": "execucao", "run": "execucao", "code": "execucao",
    "read": "leitura", "glob": "leitura", "grep": "leitura", "view": "leitura",
    "write": "escrita", "edit": "escrita", "str_replace": "escrita", "notebookedit": "escrita",
    "webfetch": "rede", "websearch": "rede", "fetch": "rede", "http": "rede", "curl": "rede",
    "browser": "navegador", "playwright": "navegador", "puppeteer": "navegador",
    "message": "mensagem", "send": "mensagem", "email": "mensagem", "slack": "mensagem",
    "cron": "agendamento", "schedule": "agendamento", "timer": "agendamento",
    "task": "delegacao", "agent": "delegacao", "subagent": "delegacao",
}

CAPACIDADES = [
    {"id": "execucao", "rotulo": "Executar comando",
     "padroes": [r"```(?:ba)?sh", r"\b(?:subprocess|child_process|os\.system|Runtime\.exec)\b",
                 r"(?m)^\s*\$\s+\w", r"\b(?:run|exec|execute)\s+(?:the\s+)?(?:command|shell|script)\b",
                 r"\b(?:bash|zsh|sh)\s+-c\b"]},
    {"id": "leitura", "rotulo": "Ler arquivo",
     "padroes": [r"\b(?:cat|head|tail|less|read_file|Read)\b[^\n]{0,40}\.",
                 r"\b(?:read|ler|leia)\s+(?:the\s+)?(?:file|arquivo)\b"]},
    {"id": "escrita", "rotulo": "Escrever arquivo",
     "padroes": [r"\b(?:Write|Edit|write_file|str_replace)\b",
                 r"(?:^|\s)>\s*[\w./~-]+\.(?:md|json|ya?ml|txt|sh|py|js)",
                 r"\b(?:tee|mv|cp|rm)\s+[\w./~-]+"]},
    {"id": "rede", "rotulo": "Acessar a rede",
     "padroes": [r"https?://", r"\b(?:curl|wget|httpie)\b", r"\b(?:requests|httpx)\.(?:get|post)\b",
                 r"\bfetch\(", r"\bapi[_ -]?key\b"]},
    {"id": "navegador", "rotulo": "Controlar navegador",
     "padroes": [r"\b(?:playwright|puppeteer|selenium|chromedriver|browser automation)\b"]},
    {"id": "mensagem", "rotulo": "Enviar mensagem",
     "padroes": [r"\b(?:send|enviar|envie)\b[^\n]{0,30}\b(?:message|mensagem|email|e-mail|slack|telegram|whatsapp)\b"]},
    {"id": "agendamento", "rotulo": "Agendar tarefa",
     "padroes": [r"\b(?:crontab|cron job|launchd|launchagent|systemd timer|schtasks|agendad[oa])\b"]},
    {"id": "delegacao", "rotulo": "Delegar para subagente",
     "padroes": [r"\b(?:subagent|sub-agente|subagente)\b", r"\bTask\s+tool\b"]},
]

# Padrões de risco. `grupo` vira a severidade; `classe` agrupa no parecer.
PADROES_RISCO = [
    {"id": "execucao-destrutiva", "classe": "destruicao", "grupo": "must",
     "titulo": "Comando destrutivo",
     "padrao": r"\brm\s+-[a-z]*[rf]|\bmkfs(?:\.\w+)?\b|\bdd\s+if=|>\s*/dev/sd|:\(\)\s*\{\s*:\|:&\s*\};:",
     "porque": "Apaga ou sobrescreve dado sem confirmação e sem cópia.",
     "correcao": "Troque por operação idempotente dentro do workspace e exija confirmação.",
     "ignorar": "Um erro de caminho apaga o diretório pessoal inteiro."},
    {"id": "download-e-executa", "classe": "execucao-remota", "grupo": "must",
     "titulo": "Baixa e executa na mesma linha",
     "padrao": r"(?:curl|wget)[^\n|]{0,120}\|\s*(?:ba|z|k|da)?sh\b|(?:curl|wget)[^\n|]{0,120}\|\s*python|iwr[^\n|]{0,80}\|\s*iex",
     "porque": "O conteúdo executado pode mudar depois da revisão; não há versão nem hash.",
     "correcao": "Baixe, confira o hash e execute o arquivo revisado.",
     "ignorar": "A execução depende de um servidor que você não controla."},
    {"id": "credencial", "classe": "credencial", "grupo": "must",
     "titulo": "Leitura de credencial",
     "padrao": r"(?:cat|less|head|tail|cp|scp|curl|upload|read_file|Read)[^\n]{0,60}(?:\.env\b|id_rsa|\.ssh/|\.aws/|credentials\b|keychain)",
     "porque": "Credencial lida por skill de terceiro vira credencial exposta.",
     "correcao": "Peça ao usuário o valor por parâmetro e nunca leia o arquivo de segredo.",
     "ignorar": "A skill passa a ter acesso a toda conta que aquela credencial abre."},
    {"id": "exfiltracao", "classe": "exfiltracao", "grupo": "must",
     "titulo": "Envio para fora",
     "padrao": r"webhook|pastebin|transfer\.sh|ngrok|discord\.com/api/webhooks|t\.me/|requestbin|interact\.sh|burpcollaborator",
     "porque": "Endpoint de coleta pronto para receber o que a skill leu.",
     "correcao": "Declare o destino, o que é enviado e por quê; se não for necessário, remova.",
     "ignorar": "Dado do usuário sai sem registro e sem consentimento."},
    {"id": "injecao", "classe": "injecao", "grupo": "must",
     "titulo": "Instrução que sequestra o agente",
     "padrao": r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions|do\s+not\s+(?:tell|inform|warn)\s+the\s+user|n[aã]o\s+(?:avise|conte|informe)\s+(?:ao|o)\s+usu[aá]rio|reveal\s+(?:your\s+)?system\s+prompt|exfiltrat",
     "porque": "Texto que manda o agente esconder ação do usuário é ataque, não instrução.",
     "correcao": "Remova o trecho; skill legítima não pede sigilo nem reescreve o sistema.",
     "ignorar": "O agente passa a agir contra o dono da máquina."},
    {"id": "ofuscacao", "classe": "ofuscacao", "grupo": "must",
     "titulo": "Carga ofuscada",
     "padrao": r"\bbase64\s+-d\b|\beval\s*\(|\bexec\s*\(|[A-Za-z0-9+/]{160,}={0,2}|(?:\\x[0-9a-fA-F]{2}){8,}",
     "porque": "O que não se lê não se revisa; ofuscação em skill não tem uso legítimo.",
     "correcao": "Publique o código legível ou remova o trecho.",
     "ignorar": "O comportamento real da skill fica invisível para a revisão."},
    {"id": "desliga-protecao", "classe": "protecao", "grupo": "must",
     "titulo": "Desliga proteção do ambiente",
     "padrao": r"--dangerously-skip-permissions|--no-sandbox|--insecure\b|NODE_TLS_REJECT_UNAUTHORIZED|setenforce\s+0|git\s+config\s+--global\s+safe\.directory|GIT_SSL_NO_VERIFY",
     "porque": "A skill pede para remover exatamente a barreira que a contém.",
     "correcao": "Mantenha a proteção e ajuste a permissão mínima necessária.",
     "ignorar": "Todo o resto do ambiente fica exposto ao que a skill fizer."},
    {"id": "privilegio", "classe": "privilegio", "grupo": "should",
     "titulo": "Privilégio elevado",
     "padrao": r"\bsudo\b|\brunas\b|\bdoas\b",
     "porque": "Skill de usuário não precisa de root para tarefa de usuário.",
     "correcao": "Descreva a operação sem elevação ou declare por que ela é necessária.",
     "ignorar": "Um erro passa a ser capaz de alterar o sistema inteiro."},
    {"id": "persistencia", "classe": "persistencia", "grupo": "should",
     "titulo": "Instalação persistente",
     "padrao": r"\bcrontab\b|LaunchAgents|systemctl\s+enable|schtasks\s+/create|\.bashrc|\.zshrc|authorized_keys",
     "porque": "O que sobrevive ao fim da sessão muda o ambiente sem você ver.",
     "correcao": "Deixe o agendamento explícito na interface e reversível.",
     "ignorar": "A skill continua agindo depois de desinstalada."},
    {"id": "fora-do-workspace", "classe": "escrita", "grupo": "should",
     "titulo": "Escrita fora da área de trabalho",
     "padrao": r"(?:>|>>|Write|Edit)[^\n]{0,40}(?:/etc/|/usr/local/bin|~/\.ssh|~/\.config|~/Library/|/Library/LaunchDaemons)",
     "porque": "O contrato do JARVIS confina escrita ao workspace.",
     "correcao": "Grave dentro de `storage/user-files` e peça confirmação para o resto.",
     "ignorar": "A skill altera configuração do sistema sem trilha."},
    {"id": "auto-modificacao", "classe": "integridade", "grupo": "should",
     "titulo": "Reescreve a própria instrução",
     "padrao": r"(?:edit|update|rewrite|patch|append\s+to)[^\n]{0,40}SKILL\.md|self[- ]?update|auto[- ]?update\s+(?:this|the)\s+skill",
     "porque": "Skill que se edita escapa da versão que você revisou.",
     "correcao": "Separe atualização de execução; atualização passa por nova revisão.",
     "ignorar": "A versão revisada e a versão executada divergem sem aviso."},
    {"id": "segredo-em-claro", "classe": "segredo", "grupo": "must",
     "titulo": "Segredo no texto",
     "padrao": r"sk-[A-Za-z0-9]{20,}|\bghp_[A-Za-z0-9]{20,}|\bAKIA[0-9A-Z]{16}\b|-----BEGIN\s+(?:RSA |OPENSSH |EC )?PRIVATE KEY-----",
     "porque": "Chave no repositório ou na skill já está comprometida.",
     "correcao": "Revogue a chave, remova o trecho e use variável de ambiente.",
     "ignorar": "Qualquer leitor do arquivo usa a conta."},
    {"id": "telemetria", "classe": "telemetria", "grupo": "should",
     "titulo": "Telemetria não declarada",
     "padrao": r"(?:(?:send|post|report|beacon|collect|envie|envia|colete|transmita)[^\n]{0,40}\b(?:telemetry|analytics|tracking|metrics)\b)|(?:\b(?:telemetry|analytics|tracking|metrics)\b[^\n]{0,40}(?:send|post|report|beacon|collect|para\s+https?://))",
     "porque": "Medição de uso sem declaração é coleta silenciosa.",
     "correcao": "Declare o que é enviado, para onde e como desligar.",
     "ignorar": "Uso e conteúdo saem da máquina sem aviso."},
    {"id": "permissao-total", "classe": "permissao", "grupo": "should",
     "titulo": "Permissão total declarada",
     "padrao": r"allowed-tools\s*:\s*[\"']?\*|allowed-tools\s*:\s*.*\ball\b|full\s+access|acesso\s+total",
     "porque": "Quem pede tudo não precisa de tudo.",
     "correcao": "Liste só as ferramentas que o corpo usa.",
     "ignorar": "A skill pode fazer qualquer coisa que o agente pode."},
    {"id": "instalacao-silenciosa", "classe": "instalacao", "grupo": "should",
     "titulo": "Instala pacote sem pedir",
     "padrao": r"\b(?:npm|pnpm|yarn)\s+(?:i|install|add)\b|\bpip3?\s+install\b|\bbrew\s+install\b|\bcargo\s+install\b",
     "porque": "Instalar dependência muda o ambiente e amplia a superfície.",
     "correcao": "Declare a dependência e deixe a instalação para o usuário.",
     "ignorar": "A skill traz código de terceiro sem revisão."},
]

# Afirmações que só valem com prova ao lado.
CLAIMS = [
    ("oficial", "must", "Apresentada como oficial",
     r"\bofficial\b|\boficial\b|first[- ]party|mantid[ao]\s+pel[oa]\s+(?:time|equipe)\s+oficial",
     "Oficial é vínculo verificável, não adjetivo da descrição.",
     "Cite o vínculo: repositório da organização, assinatura ou publicação no registro."),
    ("auditada", "must", "Diz que foi auditada",
     r"\baudited\b|\bauditad[ao]\b|security[- ]reviewed|pen[- ]tested",
     "Auditoria tem escopo, autor, data e relatório.",
     "Aponte o relatório da auditoria, com data e escopo."),
    ("obrigatoria", "should", "Diz que é obrigatória",
     r"\bmandatory\b|\bobrigat[oó]ri[ao]\b|must[- ]install|instala[cç][aã]o\s+obrigat[oó]ria",
     "Urgência inventada é pressão, não requisito técnico.",
     "Explique o que quebra sem ela e quem exige."),
    ("milagre", "should", "Promete resultado",
     r"\b10x\b|revolucion[aá]ri[ao]|game[- ]changer|the\s+only\s+skill|o\s+[uú]nico\s+que\s+resolve",
     "Adjetivo de venda não descreve comportamento.",
     "Troque por o que a skill faz, com entrada e saída."),
]

LIMITES_FICHA = [
    "A ficha é o que o texto declara; nenhum campo é validado contra o registro, o repositório ou o autor.",
    "Frontmatter fora do formato `chave: valor` é lido como corpo e aparece como ausente.",
    "Descrição boa para o modelo não é descrição boa para o índice: aqui só se mede forma, não utilidade.",
    "Nenhum arquivo referenciado pela skill é aberto.",
]

LIMITES_RISCO = [
    "A varredura é lexical: pega o que está escrito, não o que o código faz em tempo de execução.",
    "Ofuscação sofisticada, chamada indireta e payload remoto só aparecem se o texto os mostrar.",
    "Ausência de padrão não é atestado de segurança; é ausência de padrão no texto colado.",
    "Nenhum comando é executado e nenhuma URL é acessada.",
]

LIMITES_PERMISSAO = [
    "O corpo da skill é prosa: a detecção de uso é lexical e pode marcar exemplo como uso real.",
    "Ferramenta declarada com nome fora do vocabulário é tratada como desconhecida, não como permitida.",
    "A permissão efetiva depende do runtime; aqui se compara declaração e indício de uso.",
    "Nenhum escopo de conta, token ou sistema de arquivos é consultado.",
]

LIMITES_INSTALACAO = [
    "A receita é lida como texto: nenhum pacote é resolvido, baixado ou instalado.",
    "Versão travada no texto não garante o que o gerenciador resolve hoje.",
    "Checksum só é conferido se estiver escrito ao lado do download.",
    "Licença e manutenção são o que o texto declara.",
]

LIMITES_INDICE = [
    "O índice é lido como Markdown: nenhum link é aberto e nenhuma contagem é conferida na fonte.",
    "As regras vêm do CONTRIBUTING do repositório de origem; outro índice tem outras regras.",
    "Categoria, autoria e publicação no registro são o que a linha declara.",
    "Duplicata por conteúdo depende de o texto repetir nome, link ou descrição.",
]

LIMITES_DUPLICATA = [
    "A comparação é de nome e descrição, não de comportamento: duas skills podem fazer o mesmo sem parecer.",
    "Distância de edição baixa indica nome parecido, não má-fé.",
    "Só entram as entradas do texto colado; o registro não é consultado.",
    "Lista grande é amostrada por prefixo para manter a conta linear.",
]


class ConfiancaError(ValueError):
    """Erro de entrada da camada de confiança."""


# ------------------------------------------------------------------ helpers

def _modo(modo: str) -> str:
    if modo not in MODOS:
        raise ConfiancaError("`modo` aceita lite, full ou ultra.")
    return modo


def _norm(texto: str) -> str:
    tabela = str.maketrans("áàâãäéèêëíìîïóòôõöúùûüçñ", "aaaaaeeeeiiiiooooouuuucn")
    return texto.lower().translate(tabela)


def _texto(valor: Any) -> str:
    return "" if valor is None else str(valor)


def _num(valor: float, casas: int = 0) -> str:
    inteiro, _, decimal = f"{valor:.{casas}f}".partition(".")
    inteiro = f"{int(inteiro):,}".replace(",", ".")
    return f"{inteiro},{decimal}" if decimal else inteiro


def _pct(valor: float, casas: int = 1) -> str:
    return f"{_num(valor, casas)}%"


def _palavras(texto: str) -> list[str]:
    return [palavra for palavra in re.split(r"\s+", texto.strip()) if palavra]


def _linhas(texto: str) -> list[str]:
    return [linha.rstrip() for linha in texto.splitlines()]


def _trecho(texto: str, inicio: int, fim: int, largura: int = 64) -> str:
    """Recorte legível em volta do achado, cortado em fronteira de palavra."""
    comeco = max(0, inicio - largura // 3)
    if comeco > 0:
        espaco = texto.rfind(" ", comeco, inicio)
        comeco = espaco + 1 if espaco != -1 else comeco
    recorte = texto[comeco:fim + largura].replace("\n", " ")
    recorte = re.sub(r"\s+", " ", recorte).strip()
    if len(recorte) > largura * 2:
        corte = recorte.rfind(" ", 0, largura * 2)
        recorte = recorte[: corte if corte > 0 else largura * 2].rstrip(" ,;") + "…"
    if comeco > 0:
        recorte = "…" + recorte
    return recorte


def _linha_de(texto: str, posicao: int) -> int:
    return texto.count("\n", 0, posicao) + 1


def _lista(valor: str) -> list[str]:
    valor = valor.strip()
    if valor.startswith("[") and valor.endswith("]"):
        valor = valor[1:-1]
    partes = re.split(r"[,\n]", valor)
    return [parte.strip().strip("'\"") for parte in partes if parte.strip().strip("'\"")]


def _frontmatter(texto: str) -> tuple[dict[str, Any], str, bool, str]:
    """Lê o cabeçalho `--- ... ---` sem dependência de YAML."""
    linhas = _linhas(texto)
    if not linhas or linhas[0].strip() != "---":
        return {}, texto, False, ""
    fim = None
    for indice, linha in enumerate(linhas[1:], start=1):
        if linha.strip() in {"---", "..."}:
            fim = indice
            break
    if fim is None:
        return {}, texto, False, ""
    bruto = "\n".join(linhas[1:fim])
    dados: dict[str, Any] = {}
    chave_atual: str | None = None
    bloco: list[str] = []
    for linha in linhas[1:fim]:
        if not linha.strip() or linha.lstrip().startswith("#"):
            continue
        cabeca = re.match(r"^([A-Za-z0-9_.-]+)\s*:\s*(.*)$", linha)
        if cabeca and not linha.startswith((" ", "\t")):
            if chave_atual is not None and bloco:
                dados[chave_atual] = " ".join(parte.strip() for parte in bloco)
            chave_atual = cabeca.group(1).strip().lower()
            valor = cabeca.group(2).strip()
            if valor in {"|", ">", "|-", ">-", "|+", ">+"}:
                bloco = []
                dados[chave_atual] = ""
            elif valor == "":
                bloco = []
                dados[chave_atual] = ""
            else:
                bloco = []
                dados[chave_atual] = valor.strip().strip("'\"")
            continue
        item = re.match(r"^\s+-\s+(.*)$", linha)
        if item and chave_atual is not None:
            atual = dados.get(chave_atual)
            valores = atual if isinstance(atual, list) else ([] if not atual else _lista(str(atual)))
            valores.append(item.group(1).strip().strip("'\""))
            dados[chave_atual] = valores
            continue
        if chave_atual is not None:
            if isinstance(dados.get(chave_atual), list):
                dados[chave_atual].append(linha.strip())
            else:
                bloco.append(linha)
                dados[chave_atual] = " ".join(parte.strip() for parte in bloco).strip()
    if chave_atual is not None and bloco:
        dados[chave_atual] = " ".join(parte.strip() for parte in bloco).strip()
    corpo = "\n".join(linhas[fim + 1:]).strip("\n")
    return dados, corpo, True, bruto


def _ferramentas(dados: dict[str, Any]) -> list[str]:
    for chave in ("allowed-tools", "allowed_tools", "tools", "tool", "permissions"):
        if chave in dados:
            valor = dados[chave]
            itens = valor if isinstance(valor, list) else _lista(_texto(valor))
            return [item.strip() for item in itens if item.strip()]
    return []


def _requisitos(bruto: str) -> tuple[list[str], list[str]]:
    env: list[str] = []
    bins: list[str] = []
    for chave, alvo in (("env", env), ("environment", env), ("bins", bins), ("binaries", bins), ("commands", bins)):
        for achado in re.finditer(rf'"{chave}"\s*:\s*\[([^\]]*)\]', bruto):
            alvo.extend(item.strip().strip("'\"") for item in achado.group(1).split(",") if item.strip().strip("'\""))
    return sorted(set(env)), sorted(set(bins))


# ------------------------------------------------------------------- 1. ficha

def analisar_ficha(*, texto: str, modo: str = "full") -> dict[str, Any]:
    """Lê o SKILL.md e devolve a ficha normalizada com o que falta nela."""
    _modo(modo)
    if len(texto.strip()) < 40:
        raise ConfiancaError("Cole o SKILL.md inteiro; ele precisa de ao menos 40 caracteres.")
    if len(texto) > MAX_TEXTO:
        raise ConfiancaError("Texto acima do limite de leitura.")

    dados, corpo, tem, bruto = _frontmatter(texto)
    achados: list[dict[str, Any]] = []
    perguntas: list[str] = []

    nome = _texto(dados.get("name")).strip()
    if not nome:
        titulo = re.search(r"(?m)^#\s+(.+)$", corpo)
        nome = titulo.group(1).strip() if titulo else ""
    descricao = _texto(dados.get("description")).strip()
    licenca = _texto(dados.get("license") or dados.get("licenca")).strip()
    versao = _texto(dados.get("version") or dados.get("versao")).strip()
    autor = _texto(dados.get("author") or dados.get("maintainer") or dados.get("homepage")).strip()
    ferramentas = _ferramentas(dados)
    env, bins = _requisitos(bruto)
    palavras = _palavras(descricao)

    if not tem:
        achados.append(finding(
            "must", "sem-frontmatter", "Sem cabeçalho de ficha", "início do arquivo",
            "O formato pede um bloco `---` com nome, descrição e o que a skill usa.",
            "Sem ficha, quem instala não sabe o que a skill pede antes de rodar.",
            "Abra o bloco `---` e preencha `name`, `description` e `allowed-tools`.",
            "A skill entra no catálogo sem metadado legível por máquina.",
        ))
    if not nome:
        achados.append(finding(
            "must", "sem-nome", "Sem nome", "ficha",
            "Nem `name` no cabeçalho nem título `#` no corpo.",
            "Nome é a chave de instalação e de busca.",
            "Declare `name` em kebab-case, igual ao diretório da skill.",
            "A skill não pode ser referenciada nem instalada por nome.",
        ))
    elif not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", nome) or len(nome) > 64:
        achados.append(finding(
            "should", "nome-fora-do-padrao", "Nome fora do padrão", nome,
            "O padrão é minúsculas, hífen e até 64 caracteres.",
            "Nome com espaço, maiúscula ou sublinhado quebra busca e instalação.",
            f"Sugestão: `{re.sub(r'[^a-z0-9]+', '-', _norm(nome)).strip('-')[:64]}`.",
            "A skill fica difícil de citar e de deduplicar.",
        ))
    if not descricao:
        achados.append(finding(
            "must", "sem-descricao", "Sem descrição", "ficha",
            "`description` é o que o agente lê para decidir quando usar a skill.",
            "Sem descrição, a skill nunca é escolhida — ou é escolhida por engano.",
            "Escreva uma frase com o gatilho: o que faz e quando usar.",
            "A skill existe e não é encontrada.",
        ))
    elif len(palavras) > 40:
        achados.append(finding(
            "should", "descricao-longa", "Descrição longa demais para rotear", f"{len(palavras)} palavras",
            "Descrição serve para rotear, não para convencer.",
            "Texto longo entra no contexto e dilui o gatilho.",
            "Deixe o gatilho na primeira frase e o detalhe no corpo.",
            "O agente gasta contexto e escolhe pior.",
        ))
    elif len(palavras) < 4:
        achados.append(finding(
            "should", "descricao-curta", "Descrição curta demais", f"{len(palavras)} palavras",
            "Menos de quatro palavras não distingue uma skill de outra.",
            "Sem o que e o quando, a escolha vira sorte.",
            "Diga a ação e o gatilho em uma frase.",
            "A skill perde para concorrente com descrição melhor.",
        ))
    if descricao and not re.search(r"\b(use|usa|quando|when|para|to)\b", _norm(descricao)):
        achados.append(finding(
            "nice", "descricao-sem-gatilho", "Descrição sem gatilho", "ficha",
            "Não há marcador de quando usar.",
            "Descrição que só descreve o tema não ajuda o roteamento.",
            "Inclua “use quando …” ou “use to …”.",
            "A skill é acionada nas horas erradas.",
        ))
    if not licenca:
        achados.append(finding(
            "should", "sem-licenca", "Sem licença", "ficha",
            "Nenhum campo `license` declarado.",
            "Sem licença, quem instala não sabe o que pode fazer com o material.",
            "Declare a licença (MIT, Apache-2.0, proprietária).",
            "A skill não pode ser redistribuída com segurança jurídica.",
        ))
    if not versao:
        achados.append(finding(
            "nice", "sem-versao", "Sem versão", "ficha",
            "Nenhum campo `version` declarado.",
            "Sem versão não há como fixar nem comparar o que mudou.",
            "Declare a versão em semver.",
            "Atualização silenciosa passa despercebida.",
        ))
    if not autor:
        achados.append(finding(
            "should", "sem-autor", "Sem autoria ou origem", "ficha",
            "Nenhum `author`, `maintainer` ou `homepage`.",
            "Autoria é o que permite cobrar correção quando algo quebra.",
            "Declare autor e repositório de origem.",
            "Não há a quem atribuir o comportamento da skill.",
        ))
    if len(corpo.strip()) < 200:
        achados.append(finding(
            "must", "corpo-curto", "Corpo curto demais", f"{len(corpo.strip())} caracteres",
            "O corpo é a instrução que a skill executa.",
            "Com menos de 200 caracteres não há procedimento descrito.",
            "Descreva o passo a passo, a entrada e a saída.",
            "A skill promete e não instrui.",
        ))

    linhas = [
        {"campo": "Nome", "valor": nome or "—", "situacao": "ok" if nome else "ausente"},
        {"campo": "Descrição", "valor": f"{len(palavras)} palavras" if descricao else "—",
         "situacao": "ok" if descricao else "ausente"},
        {"campo": "Licença", "valor": licenca or "—", "situacao": "ok" if licenca else "ausente"},
        {"campo": "Versão", "valor": versao or "—", "situacao": "ok" if versao else "ausente"},
        {"campo": "Autoria", "valor": autor or "—", "situacao": "ok" if autor else "ausente"},
        {"campo": "Ferramentas", "valor": ", ".join(ferramentas) if ferramentas else "—",
         "situacao": "ok" if ferramentas else "ausente"},
        {"campo": "Variáveis de ambiente", "valor": ", ".join(env) if env else "—",
         "situacao": "ok" if env else "ausente"},
        {"campo": "Binários exigidos", "valor": ", ".join(bins) if bins else "—",
         "situacao": "ok" if bins else "ausente"},
        {"campo": "Corpo", "valor": f"{len(corpo.strip())} caracteres", "situacao": "ok" if len(corpo.strip()) >= 200 else "ausente"},
    ]

    metrics = {
        "tem_frontmatter": tem, "campos": len(dados), "ferramentas": len(ferramentas),
        "env": len(env), "bins": len(bins), "palavras_descricao": len(palavras),
        "corpo": len(corpo.strip()), "nome": nome or "",
    }
    if modo == "ultra":
        perguntas = [
            "A skill precisa de rede para o que promete? Se sim, para qual host?",
            "Ela lê alguma credencial ou arquivo fora de `storage/user-files`?",
            "Qual é o efeito colateral irreversível se ela rodar duas vezes?",
        ]

    findings, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    resumo = [
        f"**Ficha:** {nome or 'sem nome'} · {len(palavras)} palavra(s) de descrição · "
        f"{len(ferramentas)} ferramenta(s) · {len(env)} variável(is) de ambiente.",
        f"**Corpo:** {len(corpo.strip())} caracteres; cabeçalho {'presente' if tem else 'ausente'}.",
    ]
    return common(
        analysis="confianca.ficha", mode=modo, title="Ficha da skill",
        summary=resumo, findings=findings, counts=counts, verdict=veredito,
        questions=perguntas, rows=linhas, metrics=metrics, limitations=LIMITES_FICHA,
    )


# ------------------------------------------------------------------- 2. risco

PESOS_RISCO = {"must": 18, "should": 7, "nice": 2}


def _nivel(score: int, bloqueios: int) -> str:
    if bloqueios >= 3 or score >= 70:
        return "crítico"
    if bloqueios >= 1 or score >= 40:
        return "alto"
    if score >= 15:
        return "moderado"
    return "baixo"


def auditar_risco(*, texto: str, modo: str = "full") -> dict[str, Any]:
    """Varre o texto da skill atrás de comando destrutivo, credencial, exfiltração e injeção."""
    _modo(modo)
    if len(texto.strip()) < 40:
        raise ConfiancaError("Cole a skill ou a receita inteira; ela precisa de ao menos 40 caracteres.")
    if len(texto) > MAX_TEXTO:
        raise ConfiancaError("Texto acima do limite de leitura.")

    achados: list[dict[str, Any]] = []
    linhas: list[dict[str, Any]] = []
    score = 0
    vistos: set[str] = set()

    for padrao in PADROES_RISCO:
        achados_regex = list(re.finditer(padrao["padrao"], texto, re.I))
        if not achados_regex:
            continue
        vistos.add(padrao["id"])
        primeiro = achados_regex[0]
        linha = _linha_de(texto, primeiro.start())
        evidencias = "; ".join(_trecho(texto, achado.start(), achado.end(), 40) for achado in achados_regex[:3])
        linhas.append({"classe": padrao["classe"], "evidencia": _trecho(texto, primeiro.start(), primeiro.end()),
                       "linha": linha, "ocorrencias": len(achados_regex)})
        score += PESOS_RISCO[padrao["grupo"]]
        achados.append(finding(
            padrao["grupo"], padrao["id"], padrao["titulo"],
            f"linha {linha} · {len(achados_regex)} ocorrência(s)",
            evidencias,
            padrao["porque"], padrao["correcao"], padrao["ignorar"],
        ))

    for identificador, grupo, titulo, padrao, porque, correcao in CLAIMS:
        achado = re.search(padrao, texto, re.I)
        if not achado:
            continue
        vistos.add(identificador)
        linha = _linha_de(texto, achado.start())
        linhas.append({"classe": "claim", "evidencia": _trecho(texto, achado.start(), achado.end()),
                       "linha": linha, "ocorrencias": 1})
        score += PESOS_RISCO[grupo]
        achados.append(finding(
            grupo, f"claim-{identificador}", titulo, f"linha {linha}",
            _trecho(texto, achado.start(), achado.end()),
            porque, correcao,
            "A promessa entra no lugar da prova e o usuário decide por ela.",
        ))

    # Combinação que caracteriza exfiltração de credencial.
    if {"credencial", "exfiltracao"} <= vistos:
        score = max(score, 85)
        achados.insert(0, finding(
            "must", "credencial-exfiltrada", "Credencial lida e enviada para fora", "texto",
            "Há leitura de segredo e destino de envio no mesmo material.",
            "É a assinatura de roubo de credencial, mesmo quando o texto chama de integração.",
            "Remova as duas partes; se a integração for legítima, use token de escopo mínimo e destino declarado.",
            "Toda credencial lida sai da máquina.",
        ))

    score = min(score, 100)
    bloqueios = sum(1 for item in achados if item["group"] == "must")
    nivel = _nivel(score, bloqueios)
    perguntas = [
        "Você precisa que a skill rode comando de shell? O que ela faria sem isso?",
        "Qual credencial ela realmente precisa, e com qual escopo mínimo?",
        "Ela envia algo para fora da máquina? Para onde, com que frequência e sob qual consentimento?",
    ] if modo == "ultra" else []

    metrics = {"score": score, "nivel": nivel, "padroes": len(vistos),
               "bloqueios": bloqueios, "correcoes": sum(1 for item in achados if item["group"] == "should"),
               "linhas": len(linhas)}
    findings, counts, _veredito, perguntas = finalize(achados, modo, perguntas)
    veredito = f"Risco {nivel} — nota {score} de 100 com {counts['must']} bloqueio(s)." if findings else "Nenhum padrão de risco conhecido no texto colado."
    resumo = [
        f"**Risco {nivel}:** nota {score} de 100.",
        f"**Varredura:** {len(PADROES_RISCO)} padrões e {len(CLAIMS)} afirmações; {len(linhas)} achado(s).",
    ]
    return common(
        analysis="confianca.risco", mode=modo, title="Risco da skill",
        summary=resumo, findings=findings, counts=counts, verdict=veredito,
        questions=perguntas, rows=linhas[:40], metrics=metrics, limitations=LIMITES_RISCO,
    )


# --------------------------------------------------------------- 3. permissão

COMANDOS_CONHECIDOS = {
    "git", "npm", "npx", "pnpm", "yarn", "pip", "pip3", "python", "python3", "node", "bash", "sh",
    "zsh", "curl", "wget", "docker", "kubectl", "make", "cargo", "go", "rg", "jq", "ffmpeg",
    "gh", "aws", "gcloud", "terraform", "sqlite3", "psql", "mysql", "deno", "bun", "uv", "pandoc",
    "ssh", "scp", "rsync", "crontab", "pdftk", "magick", "convert", "yt-dlp", "ollama",
}


def _comandos(corpo: str, bins: list[str]) -> list[str]:
    """Indício de comando no corpo: bloco cercado, linha com `$` ou código inline com flag."""
    achados: list[str] = []
    if re.search(r"```(?:ba|z|k|da)?sh\b", corpo, re.I):
        achados.append("bloco de shell")
    for linha in corpo.splitlines():
        if re.match(r"^\s*\$\s+\S", linha):
            achados.append(linha.strip().lstrip("$ ").strip())
    for achado in re.finditer(r"`([^`\n]{3,120})`", corpo):
        texto = achado.group(1).strip()
        primeiro = re.split(r"\s+", texto)[0]
        if primeiro in COMANDOS_CONHECIDOS or primeiro in bins or re.search(r"\s-[a-zA-Z]", texto):
            achados.append(texto)
    return achados[:20]


def conferir_permissao(*, texto: str, modo: str = "full") -> dict[str, Any]:
    """Compara o que a skill declara usar com o que o corpo dela indica usar."""
    _modo(modo)
    if len(texto.strip()) < 60:
        raise ConfiancaError("Cole a skill inteira; ela precisa de ao menos 60 caracteres.")
    if len(texto) > MAX_TEXTO:
        raise ConfiancaError("Texto acima do limite de leitura.")

    dados, corpo, _tem, bruto = _frontmatter(texto)
    ferramentas = _ferramentas(dados)
    env, bins = _requisitos(bruto)
    achados: list[dict[str, Any]] = []

    declaradas: set[str] = set()
    desconhecidas: list[str] = []
    amplo = any(item.strip() in {"*", "all", "todos"} for item in ferramentas)
    for ferramenta in ferramentas:
        base = re.split(r"[(:/\s]", ferramenta.strip().lower())[0]
        capacidade = FERRAMENTAS_CAPACIDADE.get(base)
        if capacidade:
            declaradas.add(capacidade)
        elif base:
            desconhecidas.append(ferramenta)
    if amplo:
        declaradas.update(capacidade["id"] for capacidade in CAPACIDADES)

    comandos = _comandos(corpo, bins)
    usadas = {
        capacidade["id"] for capacidade in CAPACIDADES
        if any(re.search(padrao, corpo, re.I | re.M) for padrao in capacidade["padroes"])
    }
    if comandos:
        usadas.add("execucao")
    rotulos = {capacidade["id"]: capacidade["rotulo"] for capacidade in CAPACIDADES}
    perigosas = {"execucao", "escrita", "rede", "navegador", "agendamento", "delegacao"}

    if not ferramentas:
        achados.append(finding(
            "must" if usadas & perigosas else "should",
            "sem-declaracao", "Nenhuma ferramenta declarada", "ficha",
            f"O corpo indica {len(usadas)} capacidade(s) e a ficha não declara nenhuma.",
            "Sem declaração não há como conceder o mínimo: o runtime libera tudo ou nada.",
            "Declare `allowed-tools` com a lista exata que o corpo usa.",
            "A skill roda com permissão que ninguém revisou.",
        ))
    if amplo:
        achados.append(finding(
            "should", "escopo-amplo", "Declara acesso total", "ficha",
            "A lista de ferramentas é curinga (`*`) ou equivalente.",
            "Curinga dispensa a revisão justamente no ponto que importa.",
            "Troque o curinga pelas ferramentas que o corpo usa.",
            "Qualquer instrução futura ganha permissão sem revisão.",
        ))
    for capacidade in sorted(usadas - declaradas):
        achados.append(finding(
            "must" if capacidade in perigosas else "should",
            f"nao-declarada-{capacidade}", f"Usa {rotulos[capacidade].lower()} sem declarar",
            rotulos[capacidade],
            "O corpo tem indício de uso e a ficha não concede a capacidade.",
            "Ou a ficha está incompleta, ou o uso é acidental e vai falhar em produção.",
            f"Declare a ferramenta de {rotulos[capacidade].lower()} ou remova o uso do corpo.",
            "A skill falha no runtime ou recebe permissão ampla para compensar.",
        ))
    ociosas = sorted(declaradas - usadas)
    if ociosas:
        achados.append(finding(
            "should", "capacidade-ociosa", "Permissão sem uso no corpo",
            ", ".join(rotulos[item].lower() for item in ociosas),
            "A ficha concede capacidade que o corpo não exercita.",
            "Permissão ociosa é superfície aberta sem necessidade.",
            "Retire da ficha o que o corpo não usa.",
            "A skill pode fazer mais do que promete.",
        ))

    variaveis = {achado.group(1) for achado in re.finditer(r"\$\{?([A-Z][A-Z0-9_]{2,})\}?", corpo)}
    faltando = sorted(variaveis - set(env))
    if faltando:
        achados.append(finding(
            "should", "env-nao-declarado", "Variável de ambiente fora da ficha", ", ".join(faltando[:6]),
            "O corpo referencia variável que a ficha não pede.",
            "Sem declaração, a skill falha ou o usuário exporta segredo no escuro.",
            "Liste as variáveis em `requires.env` e diga como obtê-las.",
            "A instalação quebra no primeiro uso.",
        ))
    binarios_usados = {re.split(r"\s+", comando)[0] for comando in comandos}
    binarios_faltando = sorted(binarios_usados - set(bins)) if bins else []
    if binarios_faltando:
        achados.append(finding(
            "nice", "bin-nao-declarado", "Binário usado fora da ficha", ", ".join(binarios_faltando[:6]),
            "A ficha lista binários e o corpo chama outros.",
            "Dependência não declarada quebra em máquina limpa.",
            "Acrescente os binários à lista de requisitos.",
            "A skill funciona só no computador de quem escreveu.",
        ))
    if desconhecidas:
        achados.append(finding(
            "nice", "ferramenta-desconhecida", "Ferramenta fora do vocabulário", ", ".join(desconhecidas[:4]),
            "O nome não está no vocabulário conhecido de ferramentas.",
            "Ferramenta desconhecida não pode ser mapeada para capacidade.",
            "Use o nome padrão da ferramenta ou documente o mapeamento.",
            "A revisão de permissão fica incompleta.",
        ))

    linhas = [
        {"capacidade": rotulo, "declarado": "sim" if chave in declaradas else "não",
         "usado": "sim" if chave in usadas else "não",
         "situacao": ("ok" if chave in declaradas and chave in usadas
                      else "ociosa" if chave in declaradas
                      else "nao-declarada" if chave in usadas else "livre")}
        for chave, rotulo in rotulos.items()
    ]

    metrics = {
        "ferramentas": len(ferramentas), "declaradas": len(declaradas), "usadas": len(usadas),
        "ociosas": len(ociosas), "nao_declaradas": len(usadas - declaradas),
        "env": len(env), "bins": len(bins),
    }
    perguntas = [
        "A skill precisa de execução de shell para o que promete, ou leitura de arquivo basta?",
        "Qual é o menor conjunto de ferramentas que ainda cumpre o procedimento?",
        "Ela escreve fora de `storage/user-files` em algum passo?",
    ] if modo == "ultra" else []

    findings, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    resumo = [
        f"**Permissão:** {len(ferramentas)} ferramenta(s) declarada(s), {len(usadas)} capacidade(s) em uso no corpo.",
        f"**Diferença:** {len(usadas - declaradas)} capacidade(s) usada(s) sem declaração e {len(ociosas)} declarada(s) sem uso.",
    ]
    return common(
        analysis="confianca.permissao", mode=modo, title="Permissão declarada e usada",
        summary=resumo, findings=findings, counts=counts, verdict=veredito,
        questions=perguntas, rows=linhas, metrics=metrics, limitations=LIMITES_PERMISSAO,
    )


# -------------------------------------------------------------- 4. instalação

GERENCIADORES = [
    ("npm", r"\b(?:npm|npx)\s+(?:i|install|add|exec|dlx)\b|\bnpx\s+[\w@./-]+"),
    ("pnpm", r"\bpnpm\s+(?:i|install|add|dlx)\b"),
    ("yarn", r"\byarn\s+(?:add|install|dlx)\b"),
    ("pip", r"\b(?:pip3?|uv\s+pip)\s+install\b"),
    ("uvx", r"\buvx\b|\buv\s+tool\s+install\b"),
    ("brew", r"\bbrew\s+install\b"),
    ("cargo", r"\bcargo\s+install\b"),
    ("go", r"\bgo\s+install\b"),
    ("git", r"\bgit\s+clone\b"),
    ("docker", r"\bdocker\s+(?:run|pull)\b"),
    ("curl", r"\bcurl\s+(?:-[A-Za-z]+\s+)*https?://"),
    ("wget", r"\bwget\s+https?://"),
    ("apt", r"\b(?:apt|apt-get|dnf|apk)\s+install\b"),
]


def _fixado(comando: str, gerenciador: str) -> bool:
    if gerenciador in {"npm", "pnpm", "yarn", "brew", "cargo"}:
        return bool(re.search(r"@\d+\.\d+\.\d+", comando))
    if gerenciador in {"pip", "uvx", "apt"}:
        return bool(re.search(r"==\s*\d+\.\d+|==\s*\d+", comando))
    if gerenciador == "git":
        return bool(re.search(r"(?:--branch|-b)\s+v?\d|#\s*[0-9a-f]{7,40}\b|--depth", comando))
    if gerenciador == "docker":
        return bool(re.search(r":\d+\.\d+(?:\.\d+)?\b|@sha256:[0-9a-f]+", comando))
    if gerenciador == "go":
        return bool(re.search(r"@v?\d+\.\d+\.\d+", comando))
    return False


def auditar_instalacao(*, texto: str, modo: str = "full") -> dict[str, Any]:
    """Lê a receita de instalação e aponta o que falta para ela ser repetível."""
    _modo(modo)
    if len(texto.strip()) < 30:
        raise ConfiancaError("Cole a receita de instalação; ela precisa de ao menos 30 caracteres.")
    if len(texto) > MAX_TEXTO:
        raise ConfiancaError("Texto acima do limite de leitura.")

    achados: list[dict[str, Any]] = []
    linhas: list[dict[str, Any]] = []
    ordenados: list[tuple[str, str]] = []
    for linha_bruta in _linhas(texto):
        linha = linha_bruta.strip().lstrip("$> ").strip()
        if not linha or linha.startswith("#"):
            continue
        for gerenciador, padrao in GERENCIADORES:
            if re.search(padrao, linha, re.I):
                ordenados.append((gerenciador, linha))
                break

    usados: dict[str, int] = {}
    for gerenciador, comando in ordenados:
        usados[gerenciador] = usados.get(gerenciador, 0) + 1
        fixado = _fixado(comando, gerenciador)
        linhas.append({
            "comando": comando[:120], "gerenciador": gerenciador,
            "versao": "fixada" if fixado else "flutuante",
            "situacao": "ok" if fixado else "corrigir",
        })

    if not ordenados:
        achados.append(finding(
            "nice", "sem-instalacao", "Sem receita de instalação", "texto",
            "Nenhum comando de instalação foi encontrado.",
            "Skill sem caminho de instalação explícito é instalada por conta e risco.",
            "Documente o comando, a versão e o host de onde ele vem.",
            "Cada pessoa instala de um jeito diferente.",
        ))
    flutuantes = [linha for linha in linhas if linha["versao"] == "flutuante"]
    if flutuantes:
        achados.append(finding(
            "should", "versao-flutuante", "Instalação sem versão fixa",
            f"{len(flutuantes)} de {len(linhas)} comando(s)",
            "; ".join(linha["comando"] for linha in flutuantes[:2]),
            "Sem versão, o que instala hoje não é o que instala amanhã.",
            "Fixe a versão (`pkg@1.2.3`, `pkg==1.2.3`, tag ou commit) e atualize de propósito.",
            "A skill muda de comportamento sem mudar de nome.",
        ))
    if re.search(r"(?:curl|wget)[^\n|]{0,120}\|\s*(?:ba|z|k|da)?sh\b", texto, re.I):
        achados.append(finding(
            "must", "executa-instalador", "Instalador baixado e executado", "receita",
            "O download é canalizado direto para o shell.",
            "O conteúdo não passa por revisão nem por hash.",
            "Baixe, confira o hash publicado e execute o arquivo.",
            "A instalação pode mudar a qualquer momento no servidor de origem.",
        ))
    if re.search(r"(?:^|\n)\s*(?:sudo|\$ sudo)\b", texto):
        achados.append(finding(
            "must", "sudo-na-instalacao", "Instalação com privilégio elevado", "receita",
            "A receita usa `sudo`.",
            "Instalar skill pessoal como root altera o sistema inteiro.",
            "Instale no escopo do usuário e documente o que exigiria root.",
            "Um erro da skill passa a poder quebrar o sistema.",
        ))
    if re.search(r"postinstall|preinstall|prepare\s*:", texto, re.I):
        achados.append(finding(
            "must", "script-de-instalacao", "Gancho de instalação no pacote", "receita",
            "Há `postinstall`, `preinstall` ou `prepare` no material.",
            "O gancho roda sozinho no `npm install`, antes de qualquer revisão.",
            "Leia o gancho e, se não for necessário, remova ou use `--ignore-scripts`.",
            "Código roda na instalação sem você ter chamado nada.",
        ))
    if re.search(r"git\s+clone\s+\S+(?!\s+(?:--branch|-b|--depth|#))", texto) or (
        re.search(r"git\s+clone\b", texto) and not re.search(r"(?:--branch|-b)\s+v?\d|#\s*[0-9a-f]{7,40}", texto)
    ):
        achados.append(finding(
            "should", "clone-sem-tag", "Clone sem tag nem commit", "receita",
            "O clone pega o que estiver na branch padrão naquele dia.",
            "Branch padrão muda; a instalação não é reproduzível.",
            "Clone com `--branch vX.Y.Z` ou fixe o commit.",
            "Duas pessoas instalam versões diferentes com o mesmo comando.",
        ))
    if re.search(r"(?:https?://)(?!(?:www\.)?(?:github\.com|gitlab\.com|npmjs\.com|pypi\.org|registry\.npmjs\.org|crates\.io|rubygems\.org|hub\.docker\.com|ghcr\.io))[\w.-]+", texto):
        host = re.search(r"(?:https?://)(?!(?:www\.)?(?:github\.com|gitlab\.com|npmjs\.com|pypi\.org|registry\.npmjs\.org|crates\.io|rubygems\.org|hub\.docker\.com|ghcr\.io))([\w.-]+)", texto)
        achados.append(finding(
            "should", "host-nao-registrado", "Download fora de registro conhecido", host.group(1) if host else "—",
            "O endereço não é de registro público conhecido.",
            "Fora do registro não há contagem de download, assinatura nem remoção por política.",
            "Publique no registro e instale de lá; se o host for interno, declare.",
            "A origem pode desaparecer ou trocar o artefato.",
        ))
    if re.search(r"deprecat|no longer maintained|descontinuad|sem manuten[cç][aã]o|stub\s+for", texto, re.I):
        achados.append(finding(
            "should", "deprecado", "Material depreciado", "texto",
            "O próprio texto diz que a skill foi descontinuada ou virou stub.",
            "Depender do que já foi abandonado é dívida herdada de graça.",
            "Prefira a skill que substituiu esta e registre a migração.",
            "Você herda a manutenção que o autor abandonou.",
        ))
    if re.search(r"npm\s+(?:i|install)\s+(?:-g|--global)|pnpm\s+add\s+(?:-g|--global)", texto):
        achados.append(finding(
            "should", "instalacao-global", "Instalação global", "receita",
            "O pacote é instalado no escopo global da máquina.",
            "Global mistura versões entre projetos e não aparece no manifesto.",
            "Prefira `npx` ou instalação local com versão fixa.",
            "Dois projetos passam a exigir versões incompatíveis do mesmo pacote.",
        ))

    metrics = {"comandos": len(linhas), "gerenciadores": len(usados),
               "fixados": len(linhas) - len(flutuantes), "flutuantes": len(flutuantes),
               "bloqueios": sum(1 for item in achados if item["group"] == "must")}
    perguntas = [
        "De qual registro oficial o artefato vem, e qual é o hash publicado?",
        "A instalação precisa ser global ou o projeto pode fixar a versão?",
        "Qual é o comando de desinstalação?",
    ] if modo == "ultra" else []

    findings, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    resumo = [
        f"**Instalação:** {len(linhas)} comando(s) em {len(usados)} gerenciador(es).",
        f"**Reprodutibilidade:** {len(linhas) - len(flutuantes)} fixado(s) e {len(flutuantes)} flutuante(s).",
    ]
    return common(
        analysis="confianca.instalacao", mode=modo, title="Caminho de instalação",
        summary=resumo, findings=findings, counts=counts, verdict=veredito,
        questions=perguntas, rows=linhas[:40], metrics=metrics, limitations=LIMITES_INSTALACAO,
    )


# ------------------------------------------------------------------ 5. índice

ENTRADA = re.compile(r"^\s*[-*]\s+\[([^\]]+)\]\((\S+?)\)\s*(?:[–—-]\s*(.*))?$")
CONTAGEM = re.compile(r"^\*\*(\d+)\s+(?:skills?|habilidades?)\*\*\s*$")
SECAO = re.compile(r"^(#{1,3})\s+(.+?)\s*$")

PALAVRAS_CRYPTO = (
    r"\b(?:crypto|bitcoin|ethereum|blockchain|defi|nft|web3|solana|memecoin|binance|coinbase|"
    r"hyperliquid|tokenomics|airdrop)\b|\b(?:trading|trade)\b[^\n]{0,24}\b(?:bot|strategy|sinal)\b"
)


def _host(url: str) -> str:
    achado = re.match(r"^[a-z]+://([^/?#]+)", url.strip(), re.I)
    return achado.group(1).lower() if achado else ""


def _entradas_indice(texto: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[int]]:
    secoes: list[dict[str, Any]] = []
    entradas: list[dict[str, Any]] = []
    soltas: list[int] = []
    atual: dict[str, Any] | None = None
    for numero, linha in enumerate(_linhas(texto), start=1):
        cabeca = SECAO.match(linha)
        if cabeca:
            atual = {"nome": cabeca.group(2).strip(), "declarado": None, "entradas": 0}
            secoes.append(atual)
            continue
        contagem = CONTAGEM.match(linha.strip())
        if contagem and atual is not None:
            atual["declarado"] = int(contagem.group(1))
            continue
        achado = ENTRADA.match(linha)
        if achado:
            entrada = {
                "nome": achado.group(1).strip(),
                "url": achado.group(2).strip(),
                "descricao": (achado.group(3) or "").strip(),
                "linha": numero,
                "secao": atual["nome"] if atual else "",
            }
            entradas.append(entrada)
            if atual is not None:
                atual["entradas"] += 1
            continue
        if re.match(r"^\s*[-*]\s+\[", linha):
            soltas.append(numero)
    return entradas, secoes, soltas


def _exemplos(valores: list[str], limite: int = 3) -> str:
    if not valores:
        return "—"
    vistos: list[str] = []
    for valor in valores:
        if valor not in vistos:
            vistos.append(valor)
        if len(vistos) >= limite:
            break
    return "; ".join(vistos)


def auditar_indice(*, texto: str, modo: str = "full") -> dict[str, Any]:
    """Confere o índice contra as regras que o próprio repositório de origem publica."""
    _modo(modo)
    if len(texto.strip()) < 40:
        raise ConfiancaError("Cole o índice em Markdown; ele precisa de ao menos 40 caracteres.")
    if len(texto) > MAX_TEXTO:
        raise ConfiancaError("Texto acima do limite de leitura.")

    entradas, secoes, soltas = _entradas_indice(texto)
    if not entradas:
        raise ConfiancaError("Nenhuma linha no formato `- [nome](url) - descrição` foi encontrada.")

    achados: list[dict[str, Any]] = []
    linhas: list[dict[str, Any]] = []
    def anotar(entrada: dict[str, Any], problema: str) -> None:
        if len(linhas) < 80:
            linhas.append({"linha": entrada["linha"], "entrada": entrada["nome"][:60], "problema": problema})

    fora_host = [(entrada, _host(entrada["url"])) for entrada in entradas
                 if _host(entrada["url"]) not in {HOST_CANONICO, "www." + HOST_CANONICO}]
    for entrada, _ in fora_host[:6]:
        anotar(entrada, "host fora do registro")
    if fora_host:
        hosts = sorted({host for _, host in fora_host})
        achados.append(finding(
            "must", "host-fora-do-canonico", "Link fora do registro canônico",
            f"{len(fora_host)} de {len(entradas)} entrada(s)",
            f"Hosts: {_exemplos(hosts, 4)}. O CONTRIBUTING aceita só `{HOST_CANONICO}`.",
            "Link para espelho não é o registro: não há versão, contagem nem política de remoção.",
            f"Troque o endereço pela página no `{HOST_CANONICO}` (autor/skill).",
            "A lista aponta para um lugar que o registro não controla.",
        ))

    sem_descricao = [entrada for entrada in entradas if not entrada["descricao"]]
    for entrada in sem_descricao[:6]:
        anotar(entrada, "sem descrição")
    if sem_descricao:
        achados.append(finding(
            "must", "sem-descricao", "Entrada sem descrição", f"{len(sem_descricao)} entrada(s)",
            _exemplos([entrada["nome"] for entrada in sem_descricao]),
            "Sem descrição a linha não diz o que a skill faz.",
            "Acrescente uma frase de até 10 palavras depois do hífen.",
            "A entrada é um link cru no meio das outras.",
        ))

    longas = [entrada for entrada in entradas if len(_palavras(entrada["descricao"])) > DESC_MAX_PALAVRAS]
    for entrada in longas[:6]:
        anotar(entrada, f"descrição com {len(_palavras(entrada['descricao']))} palavras")
    if longas:
        achados.append(finding('should', 'descricao-longa', 'Descrição acima de 10 palavras', f'{len(longas)} entrada(s)', _exemplos([f"{entrada['nome']} ({len(_palavras(entrada['descricao']))})" for entrada in longas]), 'A regra do índice é uma frase curta, de 10 palavras ou menos.', 'Descrição longa vira parágrafo e some na leitura por categoria.', 'Corte para o que a skill faz, sem lista de recursos. A lista deixa de ser escaneável.'))

    vazadas = [entrada for entrada in entradas
               if entrada["descricao"] and re.match(r"^(?:[>*|#]|\*\*)", entrada["descricao"])
               or entrada["descricao"].endswith((",", ";", "...", " -", "—"))]
    for entrada in vazadas[:6]:
        anotar(entrada, "descrição com markdown")
    if vazadas:
        achados.append(finding('should', 'descricao-vazada', 'Markdown vazado na descrição', f'{len(vazadas)} entrada(s)', _exemplos([entrada['descricao'][:48] for entrada in vazadas]), 'Sobra de negrito, citação ou vírgula de outra fonte dentro da linha.', 'A descrição sai do registro e não é limpa na importação.', 'Reescreva a linha sem marcação e termine com ponto final. O índice parece copiado e mal colado.'))

    vistos_url: dict[str, dict[str, Any]] = {}
    vistos_nome: dict[str, dict[str, Any]] = {}
    duplicadas: list[dict[str, Any]] = []
    for entrada in entradas:
        chave_url = entrada["url"].rstrip("/").lower()
        chave_nome = _norm(entrada["nome"])
        if chave_url in vistos_url or chave_nome in vistos_nome:
            duplicadas.append(entrada)
            anotar(entrada, "duplicada")
        else:
            vistos_url[chave_url] = entrada
            vistos_nome[chave_nome] = entrada
    if duplicadas:
        achados.append(finding('must', 'duplicada', 'Entrada repetida', f'{len(duplicadas)} entrada(s)', _exemplos([entrada['nome'] for entrada in duplicadas]), 'Mesmo link ou mesmo nome em duas linhas.', 'O CONTRIBUTING pede para não repetir skill com a mesma finalidade.', 'Deixe uma linha e aponte a outra para ela se for continuação. A contagem da categoria infla e a busca devolve o mesmo item duas vezes.'))

    nome_ruim = [entrada for entrada in entradas
                 if not re.fullmatch(r"[a-z0-9]+(?:[-.][a-z0-9]+)*", entrada["nome"])]
    for entrada in nome_ruim[:6]:
        anotar(entrada, "nome fora do padrão")
    if nome_ruim:
        achados.append(finding(
            "should", "nome-fora-do-padrao", "Nome fora do padrão", f"{len(nome_ruim)} entrada(s)",
            _exemplos([entrada["nome"] for entrada in nome_ruim]),
            "Nome com maiúscula, espaço ou emoji quebra busca e deduplicação.",
            "Use o nome publicado no registro, em kebab-case.",
            "A mesma skill aparece com duas grafias.",
        ))

    invalidos = [entrada for entrada in entradas
                 if entrada["url"].startswith("http://") or " " in entrada["url"] or not _host(entrada["url"])]
    for entrada in invalidos[:6]:
        anotar(entrada, "link inválido")
    if invalidos:
        achados.append(finding('must', 'link-invalido', 'Link inválido', f'{len(invalidos)} entrada(s)', _exemplos([entrada['url'] for entrada in invalidos]), 'Sem HTTPS, com espaço ou sem host válido.', 'Link quebrado não instala nada e some na primeira troca de domínio.', 'Confira o endereço na barra do navegador e cole o canônico. A entrada vira ruído morto no índice.'))

    escopo = [entrada for entrada in entradas
              if re.search(PALAVRAS_CRYPTO, _norm(f"{entrada['nome']} {entrada['descricao']}"))]
    for entrada in escopo[:6]:
        anotar(entrada, "fora do escopo declarado")
    if escopo:
        achados.append(finding('should', 'fora-do-escopo', 'Tema fora do escopo declarado', f'{len(escopo)} entrada(s)', _exemplos([f"{entrada['nome']}: {entrada['descricao'][:40]}" for entrada in escopo]), 'O CONTRIBUTING não aceita crypto, blockchain, DeFi nem finanças por enquanto.', 'Entrada fora do escopo abre precedente e muda a natureza da lista.', 'Remova ou proponha a mudança de escopo em discussão pública. A curadoria perde o critério que a distinguia.'))

    divergentes = [secao for secao in secoes
                   if secao["declarado"] is not None and secao["declarado"] != secao["entradas"]]
    if divergentes:
        achados.append(finding('should', 'contagem-divergente', 'Contagem declarada diferente da real', f'{len(divergentes)} seção(ões)', _exemplos([f"{secao['nome']}: diz {secao['declarado']}, tem {secao['entradas']}" for secao in divergentes]), 'O número em negrito não acompanhou a lista.', 'Contagem errada é o primeiro sinal de importação sem conferência.', 'Recalcule o total a partir das linhas. Quem usa o número para decidir trabalha com dado falso.'))

    if soltas:
        achados.append(finding(
            "should", "linha-fora-do-formato", "Linha parecida com entrada e fora do formato",
            f"{len(soltas)} linha(s): {_exemplos([str(numero) for numero in soltas])}",
            "A linha começa com `- [` e não casa com `- [nome](url) - descrição`.",
            "Formato quebrado não é lido pelo gerador e desaparece na publicação.",
            "Corrija o parêntese, o hífen ou o link.",
            "A entrada existe no texto e não existe no índice gerado.",
        ))

    palavras = [len(_palavras(entrada["descricao"])) for entrada in entradas if entrada["descricao"]]
    media = sum(palavras) / len(palavras) if palavras else 0
    metrics = {
        "entradas": len(entradas), "secoes": len([secao for secao in secoes if secao["entradas"]]),
        "com_descricao": len(entradas) - len(sem_descricao), "sem_descricao": len(sem_descricao),
        "media_palavras": round(media, 1), "longas": len(longas),
        "canonico": len(entradas) - len(fora_host), "fora_do_canonico": len(fora_host),
        "duplicadas": len(duplicadas), "vazadas": len(vazadas), "fora_do_escopo": len(escopo),
    }
    perguntas = [
        "O índice é gerado ou editado à mão? Quem garante o formato?",
        "As entradas vêm do registro canônico ou de um espelho?",
        "Qual é a regra de descrição e onde ela está escrita?",
    ] if modo == "ultra" else []

    findings, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    resumo = [
        f"**Índice:** {len(entradas)} entrada(s) em {metrics['secoes']} seção(ões) com conteúdo.",
        f"**Formato:** {len(fora_host)} fora do host canônico · {len(sem_descricao)} sem descrição · {len(longas)} acima de 10 palavras.",
    ]
    return common(
        analysis="confianca.indice", mode=modo, title="Índice de skills",
        summary=resumo, findings=findings, counts=counts, verdict=veredito,
        questions=perguntas, rows=linhas, metrics=metrics, limitations=LIMITES_INDICE,
    )


# --------------------------------------------------------------- 6. duplicata

SUFIXOS = ("-test", "-tests", "-demo", "-copy", "-old", "-new", "-v2", "-beta", "-stub", "-fork")


def _distancia(a: str, b: str, limite: int = 2) -> int:
    if abs(len(a) - len(b)) > limite:
        return limite + 1
    anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        atual = [i]
        for j, cb in enumerate(b, 1):
            atual.append(min(anterior[j] + 1, atual[j - 1] + 1, anterior[j - 1] + (ca != cb)))
        anterior = atual
    return anterior[-1]


def _jaccard(a: str, b: str) -> float:
    esquerda = {_norm(palavra).strip(".,;:!?") for palavra in _palavras(a) if len(palavra) > 2}
    direita = {_norm(palavra).strip(".,;:!?") for palavra in _palavras(b) if len(palavra) > 2}
    if not esquerda or not direita:
        return 0.0
    return len(esquerda & direita) / len(esquerda | direita)


def auditar_duplicatas(*, texto: str, modo: str = "full") -> dict[str, Any]:
    """Procura nome repetido, nome parecido e descrição igual entre as entradas do índice."""
    _modo(modo)
    if len(texto.strip()) < 40:
        raise ConfiancaError("Cole o índice em Markdown; ele precisa de ao menos 40 caracteres.")
    if len(texto) > MAX_TEXTO:
        raise ConfiancaError("Texto acima do limite de leitura.")

    entradas, _secoes, _soltas = _entradas_indice(texto)
    if not entradas:
        entradas = [
            {"nome": partes[0].strip(), "url": partes[1].strip() if len(partes) > 1 else "",
             "descricao": partes[2].strip() if len(partes) > 2 else "", "linha": numero, "secao": ""}
            for numero, linha in enumerate(_linhas(texto), start=1)
            for partes in [re.split(r"\s*[;\t]\s*", linha)]
            if len(partes) >= 2 and partes[0].strip()
        ]
    if not entradas:
        raise ConfiancaError("Nenhuma entrada encontrada: use o índice em Markdown ou linhas `nome;url;descrição`.")

    truncado = len(entradas) > 1500
    amostra = entradas[:1500]
    achados: list[dict[str, Any]] = []
    linhas: list[dict[str, Any]] = []

    por_nome: dict[str, list[dict[str, Any]]] = {}
    por_url: dict[str, list[dict[str, Any]]] = {}
    for entrada in amostra:
        por_nome.setdefault(_norm(entrada["nome"]), []).append(entrada)
        if entrada["url"]:
            por_url.setdefault(entrada["url"].rstrip("/").lower(), []).append(entrada)

    nomes_repetidos = [grupo for grupo in por_nome.values() if len(grupo) > 1]
    links_repetidos = [grupo for grupo in por_url.values() if len(grupo) > 1]
    for grupo in (nomes_repetidos + links_repetidos)[:40]:
        linhas.append({"a": grupo[0]["nome"][:48], "b": grupo[-1]["nome"][:48],
                       "motivo": "nome repetido" if len({item["nome"] for item in grupo}) == 1 else "link repetido",
                       "distancia": "0"})
    if nomes_repetidos:
        achados.append(finding('must', 'nome-repetido', 'Nome repetido', f'{len(nomes_repetidos)} grupo(s)', _exemplos([grupo[0]['nome'] for grupo in nomes_repetidos]), 'A mesma skill aparece mais de uma vez com o mesmo nome.', 'Repetição infla a categoria e confunde a instalação.', 'Deixe uma entrada e remova as demais. A contagem do índice mente.'))
    if links_repetidos:
        achados.append(finding('must', 'link-repetido', 'Link repetido', f'{len(links_repetidos)} grupo(s)', _exemplos([grupo[0]['url'] for grupo in links_repetidos]), 'Duas linhas apontam para a mesma página.', 'Nome diferente para o mesmo destino é duplicata disfarçada.', 'Una as duas entradas em uma. O leitor instala a mesma coisa duas vezes.'))

    suspeitas: list[tuple[str, str, int]] = []
    baldes: dict[str, list[dict[str, Any]]] = {}
    for entrada in amostra:
        chave = _norm(entrada["nome"])[:3]
        if len(chave) == 3:
            baldes.setdefault(chave, []).append(entrada)
    comparacoes = 0
    for grupo in baldes.values():
        if len(grupo) < 2 or len(grupo) > 80:
            continue
        for indice, primeira in enumerate(grupo):
            for segunda in grupo[indice + 1:]:
                if comparacoes > 40_000:
                    break
                comparacoes += 1
                nome_a, nome_b = _norm(primeira["nome"]), _norm(segunda["nome"])
                if nome_a == nome_b or min(len(nome_a), len(nome_b)) < 5:
                    continue
                distancia = _distancia(nome_a, nome_b)
                if distancia <= 2:
                    suspeitas.append((primeira["nome"], segunda["nome"], distancia))
    for primeira, segunda, distancia in suspeitas[:40]:
        linhas.append({"a": primeira[:48], "b": segunda[:48], "motivo": "nome parecido", "distancia": str(distancia)})
    if suspeitas:
        achados.append(finding('should', 'nome-proximo', 'Nome parecido com outro', f'{len(suspeitas)} par(es)', _exemplos([f'{a} × {b} ({d})' for a, b, d in suspeitas]), 'Nomes a uma ou duas letras de distância parecem versão, cópia ou erro de digitação.', 'Nome parecido é o que um typosquat usa e o que a busca do usuário confunde.', 'Renomeie para distinguir a finalidade, ou una as duas entradas. O usuário instala a errada achando que é a certa.'))

    bases = {_norm(entrada["nome"]): entrada["nome"] for entrada in amostra}
    clones = []
    for entrada in amostra:
        nome = _norm(entrada["nome"])
        for sufixo in SUFIXOS:
            if nome.endswith(sufixo) and nome[: -len(sufixo)] in bases:
                clones.append((entrada["nome"], bases[nome[: -len(sufixo)]]))
                break
    for primeira, segunda in clones[:40]:
        linhas.append({"a": primeira[:48], "b": segunda[:48], "motivo": "sufixo de clone", "distancia": "—"})
    if clones:
        achados.append(finding('should', 'sufixo-de-clone', 'Variação de teste ao lado do original', f'{len(clones)} par(es)', _exemplos([f'{a} ao lado de {b}' for a, b in clones]), 'Sufixo `-test`, `-demo` ou `-copy` ao lado do nome base indica duplicata de bancada.', 'O índice pede a skill representativa, não a bancada de testes do autor.', 'Remova a variação ou justifique o que ela acrescenta. A lista enche de rascunho que ninguém mantém.'))

    iguais: list[tuple[str, str]] = []
    por_descricao = [entrada for entrada in amostra if len(_palavras(entrada["descricao"])) >= 4]
    vistos: dict[str, list[str]] = {}
    for entrada in por_descricao:
        chave = " ".join(sorted({palavra for palavra in _norm(entrada["descricao"]).split() if len(palavra) > 2}))
        vistos.setdefault(chave, []).append(entrada["nome"])
    repetidas = [nomes for nomes in vistos.values() if len(nomes) > 1]
    for nomes in repetidas[:20]:
        iguais.append((nomes[0], nomes[1]))
    for primeira, segunda in iguais[:40]:
        linhas.append({"a": primeira[:48], "b": segunda[:48], "motivo": "descrição igual", "distancia": "—"})
    if iguais:
        achados.append(finding('should', 'descricao-igual', 'Descrições iguais em skills diferentes', f'{len(iguais)} par(es)', _exemplos([f'{a} × {b}' for a, b in iguais]), 'Descrição é a assinatura do propósito: igualdade aqui é duplicata ou cópia.', 'Duas skills com a mesma frase não se distinguem na busca.', 'Descreva o que cada uma faz de diferente, ou una as entradas. A escolha entre as duas vira moeda.'))

    metrics = {
        "entradas": len(entradas), "nomes_repetidos": len(nomes_repetidos),
        "links_repetidos": len(links_repetidos), "pares_proximos": len(suspeitas),
        "descricoes_iguais": len(iguais), "clones": len(clones), "truncado": truncado,
    }
    perguntas = [
        "As duas entradas têm o mesmo dono e o mesmo repositório?",
        "A variação existe para testar, ou para aparecer duas vezes na lista?",
        "Qual das duas você indicaria a alguém que nunca viu o assunto?",
    ] if modo == "ultra" else []

    findings, counts, veredito, perguntas = finalize(achados, modo, perguntas)
    resumo = [
        f"**Duplicatas:** {len(nomes_repetidos)} nome(s) repetido(s), {len(links_repetidos)} link(s) repetido(s).",
        f"**Proximidade:** {len(suspeitas)} par(es) de nome parecido e {len(iguais)} par(es) de descrição igual.",
    ]
    return common(
        analysis="confianca.duplicata", mode=modo, title="Duplicata e clone",
        summary=resumo, findings=findings, counts=counts, verdict=veredito,
        questions=perguntas, rows=linhas[:60], metrics=metrics, limitations=LIMITES_DUPLICATA,
    )


# ------------------------------------------------------------------- catálogo

REGRAS_INDICE = [
    ("host-fora-do-canonico", "Só o registro canônico entra; espelho e repositório pessoal não."),
    ("sem-descricao", "Toda linha tem uma frase depois do hífen."),
    ("descricao-longa", "A descrição tem 10 palavras ou menos."),
    ("descricao-vazada", "A descrição não carrega marcação nem pontuação de outra fonte."),
    ("duplicada", "Skill com a mesma finalidade não entra duas vezes."),
    ("nome-fora-do-padrao", "O nome é o publicado no registro, em kebab-case."),
    ("link-invalido", "O link é HTTPS, sem espaço, com host válido."),
    ("fora-do-escopo", "Crypto, blockchain, DeFi e finanças ficam fora do escopo declarado."),
    ("contagem-divergente", "O total em negrito é recalculado a cada entrada nova."),
    ("linha-fora-do-formato", "A linha segue exatamente `- [nome](url) - descrição`."),
]


def confianca_catalogo() -> dict[str, Any]:
    return {
        "fonte": "VoltAgent/awesome-openclaw-skills (MIT)",
        "versao": VERSAO,
        "principio": "Confiança é o que se pode conferir antes de instalar.",
        "hosts": HOSTS_CONHECIDOS,
        "host_canonico": HOST_CANONICO,
        "descricao_max_palavras": DESC_MAX_PALAVRAS,
        "capacidades": [{"id": capacidade["id"], "rotulo": capacidade["rotulo"]} for capacidade in CAPACIDADES],
        "ferramentas": FERRAMENTAS_CAPACIDADE,
        "risco": [
            {"id": padrao["id"], "classe": padrao["classe"], "grupo": padrao["grupo"], "titulo": padrao["titulo"]}
            for padrao in PADROES_RISCO
        ],
        "pesos": PESOS_RISCO,
        "niveis": [
            {"id": "baixo", "regra": "nota < 15 e nenhum bloqueio"},
            {"id": "moderado", "regra": "nota entre 15 e 39"},
            {"id": "alto", "regra": "um ou dois bloqueios, ou nota entre 40 e 69"},
            {"id": "critico", "regra": "três ou mais bloqueios, credencial com envio, ou nota 70+"},
        ],
        "claims": [
            {"id": identificador, "grupo": grupo, "rotulo": rotulo, "padrao": padrao}
            for identificador, grupo, rotulo, padrao, _porque, _correcao in CLAIMS
        ],
        "regras_indice": [{"id": identificador, "regra": regra} for identificador, regra in REGRAS_INDICE],
        "limites": {
            "ficha": LIMITES_FICHA, "risco": LIMITES_RISCO, "permissao": LIMITES_PERMISSAO,
            "instalacao": LIMITES_INSTALACAO, "indice": LIMITES_INDICE, "duplicata": LIMITES_DUPLICATA,
        },
        "deixado_de_fora": [
            "Nenhuma das milhares de skills do índice é baixada, importada ou executada.",
            "Nenhum link, registro, repositório ou assinatura é consultado pela rede.",
            "Nenhum modelo de linguagem julga intenção: a leitura é lexical e a conta é explícita.",
            "Sandbox dinâmico, análise de AST, assinatura de pacote e varredura de malware ficam fora.",
        ],
        "executado": False,
    }
