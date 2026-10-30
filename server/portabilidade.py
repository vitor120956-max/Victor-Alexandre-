"""Portabilidade e empacotamento de skill entre ferramentas e marketplaces.

O upstream é o `alirezarezvani/claude-skills` (MIT, 28 mil estrelas): 398 skills
que precisam funcionar em 13 ferramentas de código — cada uma com formato,
caminho e frontmatter próprios — e ser publicadas em plugins de marketplace.
Lá a conversão é feita por `scripts/convert.sh`, os espelhos por
`scripts/sync-*.py` e a checagem por `scripts/check_dual_publish.py`,
`check_plugin_json.py` e `check_skill_names.py`. Aqui o desenho é reimplementado
em Python determinístico, sem copiar script nenhum e sem tocar a rede:

- **alvo** é o formato da ferramenta (pasta com `SKILL.md`, regra `.mdc`,
  arquivo único de convenções, espelho por symlink);
- **conversão** é o plano arquivo a arquivo, com o que é copiado, renomeado,
  embutido ou descartado;
- **deriva** é a comparação entre a árvore fonte e o espelho publicado;
- **colisão** é o caminho que duas skills disputam no alvo;
- **lote** é o plugin de marketplace que agrupa skills sem sobrepor.

Nada é escrito, copiado ou instalado: o parecer é o plano.
"""
from __future__ import annotations

import hashlib
import json
import posixpath
import re
from dataclasses import dataclass
from typing import Any

from .review import common, finalize, finding
from .submissao import SubmissaoError, ler_front_matter

VERSAO = "0.64.0"

MAX_TEXTO = 1_800_000
MAX_ARQUIVOS = 2_000
MAX_ROWS = 200
MAX_SKILLS = 500
MAX_PLUGINS = 200
MODOS = ("lite", "full", "ultra")

# Limites do alvo
CAMINHO_MAX = 200
SLUG_MIN, SLUG_MAX = 1, 64
DESCRICAO_MAX = 500
MAX_KEYWORDS = 10
TAMANHO_PLUGIN_MAX = 25 * 1024 * 1024
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# Estrutura de uma skill
ARQUIVO_ENTRADA = "SKILL.md"
PASTAS = {"scripts": "script", "references": "referencia", "assets": "asset"}
NOMES_RESERVADOS = {
    "skills-index.json",
    "marketplace.json",
    "plugin.json",
    "conventions.md",
    "skill.md",
    "readme.md",
    "license",
    "license.md",
}
EXT_BINARIA = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz", ".tar",
    ".woff", ".woff2", ".ttf", ".otf", ".mp3", ".mp4", ".wav", ".mov", ".wasm",
}


class PortabilidadeError(ValueError):
    """Entrada recusada antes do cálculo."""


def _modo(valor: str) -> str:
    if valor not in MODOS:
        raise PortabilidadeError(f"Modo inválido: {valor}. Use {', '.join(MODOS)}.")
    return valor


def _resumo(texto: str, limite: int) -> str:
    limpo = re.sub(r"\s+", " ", (texto or "").strip())
    return limpo if len(limpo) <= limite else limpo[: limite - 1].rstrip() + "…"


def _slug(texto: str) -> str:
    limpo = re.sub(r"[^a-z0-9]+", "-", (texto or "").lower()).strip("-")
    return limpo


def _nome(caminho: str) -> str:
    return caminho.rsplit("/", 1)[-1]


def _extensao(caminho: str) -> str:
    nome = _nome(caminho).lower()
    return "." + nome.rsplit(".", 1)[1] if "." in nome else ""


def _sha(conteudo: str) -> str:
    return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()[:16]


def _questoes() -> list[str]:
    return [
        "Quais alvos essa skill precisa atender de verdade, e não por simetria?",
        "Quem atualiza o espelho quando a skill muda — o script ou a mão?",
    ]


# ------------------------------------------------------------------- alvos

@dataclass(frozen=True)
class Alvo:
    """Formato de destino e o que ele consegue carregar."""

    id: str
    nome: str
    estilo: str  # pasta | regra | convencao | espelho
    base: str
    extensao: str
    scripts: bool
    referencias: bool
    assets: bool
    agentes: bool
    comandos: bool
    mantem: tuple[str, ...]
    remove: tuple[str, ...]
    gera: tuple[tuple[str, str], ...]
    nota: str


ALVOS: tuple[Alvo, ...] = (
    Alvo(
        "claude-code", "Claude Code", "pasta", "~/.claude/skills/<slug>", "SKILL.md",
        True, True, True, True, True,
        ("name", "description", "allowed-tools", "model", "version", "license"),
        (),
        (),
        "Plugin via marketplace; qualquer chave fora do schema derruba a instalação inteira.",
    ),
    Alvo(
        "codex", "OpenAI Codex", "espelho", ".codex/skills/<slug>", "SKILL.md",
        True, True, True, False, False,
        ("name", "description"),
        ("allowed-tools", "model", "license", "version"),
        (),
        "Symlink no espelho e índice em `skills-index.json`; no Windows exige `core.symlinks=true`.",
    ),
    Alvo(
        "gemini", "Gemini CLI", "pasta", ".gemini/skills/<slug>", "SKILL.md",
        True, True, True, False, False,
        ("name", "description"),
        ("allowed-tools", "model"),
        (),
        "Ativação por `activate_skill(name=…)`; a descrição é o gatilho.",
    ),
    Alvo(
        "openclaw", "OpenClaw", "pasta", "<plugin>/skills/<slug>", "SKILL.md",
        True, True, True, False, False,
        ("name", "description"),
        ("allowed-tools",),
        (),
        "Distribuído como plugin npm; o pacote precisa de `plugin.json` válido.",
    ),
    Alvo(
        "hermes", "Hermes Agent", "espelho", "~/.hermes/skills/claude-skills/<slug>", "SKILL.md",
        True, True, True, False, False,
        ("name", "description"),
        ("allowed-tools", "model"),
        (),
        "Espelho pré-gerado exige um passo local de sincronização antes de instalar.",
    ),
    Alvo(
        "vibe", "Mistral Vibe", "espelho", "~/.vibe/skills/claude-skills/<slug>", "SKILL.md",
        True, True, True, False, False,
        ("name", "description"),
        ("allowed-tools", "model"),
        (),
        "Espelho pré-gerado exige um passo local de sincronização antes de instalar.",
    ),
    Alvo(
        "windsurf", "Windsurf", "pasta", ".windsurf/skills/<slug>", "SKILL.md",
        True, True, True, False, False,
        ("name", "description"),
        ("allowed-tools", "model"),
        (),
        "Pasta com `SKILL.md`, sem hooks nem comandos.",
    ),
    Alvo(
        "opencode", "OpenCode", "pasta", ".opencode/skills/<slug>", "SKILL.md",
        True, True, True, False, False,
        ("name", "description"),
        ("allowed-tools", "model"),
        (),
        "Pasta com `SKILL.md`; o script continua executável por caminho relativo.",
    ),
    Alvo(
        "antigravity", "Antigravity", "pasta", "~/.gemini/antigravity/skills/<slug>", "SKILL.md",
        True, True, True, False, False,
        ("name", "description"),
        ("allowed-tools", "model"),
        (),
        "Pasta com `SKILL.md` sob o diretório do Gemini.",
    ),
    Alvo(
        "cursor", "Cursor", "regra", ".cursor/rules/<slug>.mdc", "mdc",
        False, False, False, False, False,
        ("description",),
        ("name", "allowed-tools", "model", "version", "license"),
        (("alwaysApply", "false"),),
        "Regra em arquivo próprio: script, referência e asset não acompanham.",
    ),
    Alvo(
        "kilocode", "Kilo Code", "regra", ".kilocode/rules/<slug>.md", "md",
        False, False, False, False, False,
        ("description",),
        ("name", "allowed-tools", "model", "version", "license"),
        (),
        "Regra em Markdown, sem frontmatter obrigatório e sem pasta de apoio.",
    ),
    Alvo(
        "augment", "Augment", "regra", ".augment/rules/<slug>.md", "md",
        False, False, False, False, False,
        ("description",),
        ("name", "allowed-tools", "model", "version", "license"),
        (),
        "Regra em Markdown; conteúdo longo entra inteiro no contexto do projeto.",
    ),
    Alvo(
        "aider", "Aider", "convencao", "CONVENTIONS.md", "md",
        False, False, False, False, False,
        (),
        ("name", "description", "allowed-tools", "model", "version", "license"),
        (),
        "Um único arquivo por projeto: todas as skills viram seções dele, na ordem de instalação.",
    ),
)

POR_ID = {alvo.id: alvo for alvo in ALVOS}


def _alvo(valor: str) -> Alvo:
    limpo = (valor or "").strip().lower()
    if limpo not in POR_ID:
        raise PortabilidadeError(f"Alvo desconhecido: {valor}. Use um de: {', '.join(POR_ID)}.")
    return POR_ID[limpo]


# -------------------------------------------------------------- inventário

@dataclass
class Arquivo:
    caminho: str
    conteudo: str = ""
    bytes: int = 0
    sha: str = ""
    symlink: bool = False

    @property
    def tipo(self) -> str:
        nome = _nome(self.caminho)
        if nome == ARQUIVO_ENTRADA:
            return "entrada"
        partes = self.caminho.split("/")
        for pasta, rotulo in PASTAS.items():
            if pasta in partes[:-1]:
                return rotulo
        if _extensao(self.caminho) in EXT_BINARIA:
            return "binario"
        return "outro"

    @property
    def skill(self) -> str:
        """Diretório da skill: o pai de `SKILL.md` ou o próprio caminho de config."""
        if _nome(self.caminho) == ARQUIVO_ENTRADA:
            return posixpath.dirname(self.caminho)
        return ""


def _linha_de_inventario(linha: str, numero: int) -> Arquivo:
    partes = [parte.strip() for parte in linha.split("|")]
    caminho = partes[0].lstrip("./")
    if not caminho:
        raise PortabilidadeError(f"Linha {numero} sem caminho.")
    tamanho = 0
    sha = ""
    symlink = False
    if len(partes) > 1 and partes[1]:
        if not re.fullmatch(r"\d+", partes[1]):
            raise PortabilidadeError(f"Linha {numero}: o tamanho precisa ser inteiro.")
        tamanho = int(partes[1])
    if len(partes) > 2 and partes[2]:
        sha = partes[2].replace("sha256:", "").strip()
        if not re.fullmatch(r"[0-9a-fA-F]{6,64}", sha):
            raise PortabilidadeError(f"Linha {numero}: hash inválido em {caminho}.")
        sha = sha.lower()
    if len(partes) > 3 and partes[3]:
        tipo = partes[3].lower()
        if tipo not in {"arquivo", "symlink"}:
            raise PortabilidadeError(f"Linha {numero}: tipo precisa ser `arquivo` ou `symlink`.")
        symlink = tipo == "symlink"
    return Arquivo(caminho=caminho, bytes=tamanho, sha=sha, symlink=symlink)


def ler_inventario(*, texto: str, conteudo: bool = True) -> list[Arquivo]:
    """Lê `>>> caminho` com conteúdo, JSON com arquivos, ou `caminho | bytes | hash | tipo`."""
    bruto = (texto or "").strip()
    if not bruto:
        raise PortabilidadeError("Informe os arquivos: bundle com `>>> caminho`, JSON, ou `caminho | bytes | hash`.")
    if len(bruto) > MAX_TEXTO:
        raise PortabilidadeError(f"O texto passa de {MAX_TEXTO:,} caracteres.")

    arquivos: list[Arquivo] = []
    tem_conteudo = False
    if bruto.startswith("{"):
        try:
            dados = json.loads(bruto)
        except json.JSONDecodeError as exc:
            raise PortabilidadeError(f"JSON inválido na linha {exc.lineno}: {exc.msg}.") from exc
        itens = dados.get("arquivos") if isinstance(dados, dict) else None
        tem_conteudo = True
        if isinstance(itens, dict):
            for caminho, valor in itens.items():
                corpo = valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False)
                arquivos.append(Arquivo(caminho=str(caminho).lstrip("./"), conteudo=corpo, bytes=len(corpo.encode()), sha=_sha(corpo)))
        elif isinstance(itens, list):
            for indice, item in enumerate(itens, start=1):
                if not isinstance(item, dict) or not item.get("caminho"):
                    raise PortabilidadeError(f"Item {indice} do JSON sem `caminho`.")
                corpo = str(item.get("conteudo") or "")
                arquivos.append(
                    Arquivo(
                        caminho=str(item["caminho"]).lstrip("./"),
                        conteudo=corpo,
                        bytes=int(item.get("bytes") or len(corpo.encode())),
                        sha=str(item.get("sha") or (_sha(corpo) if corpo else "")),
                        symlink=bool(item.get("symlink")),
                    )
                )
        else:
            raise PortabilidadeError("O JSON precisa da chave `arquivos` (objeto caminho→conteúdo ou lista).")
    elif bruto.split("\n", 1)[0].lstrip().startswith(">>>"):
        tem_conteudo = True
        atual: Arquivo | None = None
        corpo: list[str] = []
        for linha in bruto.split("\n"):
            if linha.lstrip().startswith(">>>"):
                if atual is not None:
                    texto_atual = "\n".join(corpo).rstrip("\n")
                    atual.conteudo = texto_atual
                    atual.bytes = len(texto_atual.encode())
                    atual.sha = _sha(texto_atual)
                    arquivos.append(atual)
                atual = Arquivo(caminho=linha.lstrip()[3:].strip().lstrip("./"))
                corpo = []
                continue
            corpo.append(linha)
        if atual is not None:
            texto_atual = "\n".join(corpo).rstrip("\n")
            atual.conteudo = texto_atual
            atual.bytes = len(texto_atual.encode())
            atual.sha = _sha(texto_atual)
            arquivos.append(atual)
    else:
        for numero, linha in enumerate(bruto.split("\n"), start=1):
            limpa = linha.strip()
            if not limpa or limpa.startswith("#"):
                continue
            arquivos.append(_linha_de_inventario(limpa, numero))

    vistos: set[str] = set()
    for arquivo in arquivos:
        if not arquivo.caminho:
            raise PortabilidadeError("Há arquivo sem caminho no inventário.")
        if arquivo.caminho in vistos:
            raise PortabilidadeError(f"Caminho repetido no inventário: `{arquivo.caminho}`.")
        vistos.add(arquivo.caminho)
    if len(arquivos) > MAX_ARQUIVOS:
        raise PortabilidadeError(f"O inventário passa de {MAX_ARQUIVOS:,} arquivos: divida por domínio.")
    if conteudo and tem_conteudo and not any(arquivo.conteudo for arquivo in arquivos):
        raise PortabilidadeError("Nenhum arquivo trouxe conteúdo: use o bundle `>>> caminho` ou o JSON.")
    return arquivos


def _pastas_de_skill(arquivos: list[Arquivo]) -> list[str]:
    return sorted(
        {posixpath.dirname(item.caminho) for item in arquivos if _nome(item.caminho).lower() == ARQUIVO_ENTRADA.lower()}
    )


def _skills(arquivos: list[Arquivo]) -> dict[str, list[Arquivo]]:
    """Agrupa cada arquivo na skill mais próxima acima dele na árvore."""
    pastas = _pastas_de_skill(arquivos)
    grupos: dict[str, list[Arquivo]] = {}
    for arquivo in arquivos:
        dono = ""
        for pasta in pastas:
            if arquivo.caminho.startswith(pasta + "/") and len(pasta) > len(dono):
                dono = pasta
        if dono:
            grupos.setdefault(dono, []).append(arquivo)
    for itens in grupos.values():
        itens.sort(key=lambda item: item.caminho)
    return dict(sorted(grupos.items()))


def _soltos(arquivos: list[Arquivo]) -> list[Arquivo]:
    pastas = _pastas_de_skill(arquivos)
    return [item for item in arquivos if not any(item.caminho.startswith(p + "/") for p in pastas)]


def _sem_conteudo(arquivos: list[Arquivo]) -> bool:
    return not any(arquivo.conteudo for arquivo in arquivos)


# ------------------------------------------------------- validação de skill

LIMITES_CORPO = {"ok": 6_000, "longo": 12_000}
GATILHOS = ("use quando", "use para", "use this", "usar quando", "quando o usuário", "when the user", "trigger")


@dataclass
class Skill:
    pasta: str
    nome_pasta: str
    arquivos: list[Arquivo]
    dados: dict[str, Any]
    problemas: list[str]
    corpo: str

    @property
    def nome(self) -> str:
        valor = self.dados.get("name")
        return str(valor).strip() if valor is not None else ""

    @property
    def descricao(self) -> str:
        valor = self.dados.get("description")
        return re.sub(r"\s+", " ", str(valor)).strip() if valor is not None else ""

    @property
    def bytes(self) -> int:
        return sum(item.bytes for item in self.arquivos)

    def por_tipo(self, tipo: str) -> list[Arquivo]:
        return [item for item in self.arquivos if item.tipo == tipo]


def _montar_skill(pasta: str, arquivos: list[Arquivo]) -> Skill:
    entrada = next((item for item in arquivos if _nome(item.caminho).lower() == ARQUIVO_ENTRADA.lower()), None)
    dados: dict[str, Any] = {}
    problemas: list[str] = []
    corpo = ""
    if entrada is not None and entrada.conteudo:
        try:
            dados, problemas, corpo = ler_front_matter(entrada.conteudo)
        except SubmissaoError as exc:
            problemas = [str(exc)]
    elif entrada is not None:
        problemas = ["sem conteúdo para ler o front matter (inventário só com metadados)"]
    else:
        problemas = [f"falta o `{ARQUIVO_ENTRADA}` na raiz da pasta"]
    return Skill(
        pasta=pasta,
        nome_pasta=_nome(pasta).lower(),
        arquivos=arquivos,
        dados=dados,
        problemas=problemas,
        corpo=corpo,
    )


def _relativo(skill: Skill, arquivo: Arquivo) -> str:
    prefixo = skill.pasta + "/"
    return arquivo.caminho[len(prefixo):] if arquivo.caminho.startswith(prefixo) else arquivo.caminho


def _menciona(corpo: str, arquivo: Arquivo) -> bool:
    if not corpo:
        return False
    alvo_texto = corpo.lower()
    relativo = arquivo.caminho.split("/", 1)[-1].lower() if "/" in arquivo.caminho else arquivo.caminho.lower()
    return _nome(arquivo.caminho).lower() in alvo_texto or relativo in alvo_texto


def _auditar_skill(skill: Skill, alvo: Alvo | None) -> list[dict[str, Any]]:
    achados: list[dict[str, Any]] = []
    local = skill.pasta or "(raiz)"

    if not skill.dados and skill.problemas:
        achados.append(
            finding(
                "must", "frontmatter", "Skill sem front matter legível",
                local,
                f"A pasta não entrega `name`/`description` utilizáveis: {skill.problemas[0]}.",
                "Sem esses dois campos a ferramenta não indexa a skill — ela existe no disco e não aparece para o agente.",
                f"Coloque um bloco `---` na primeira linha de `{ARQUIVO_ENTRADA}` com `name` e `description`.",
                "A skill fica invisível em todos os alvos, mesmo nos que aceitam regra sem cabeçalho.",
            )
        )
        return achados

    nome = skill.nome
    if not nome:
        achados.append(
            finding(
                "must", "frontmatter", "`name` ausente no front matter",
                local,
                "O bloco de front matter existe, mas não declara `name`.",
                "O nome é a chave de instalação: sem ele o alvo usa o nome da pasta e a colisão fica silenciosa.",
                f"Declare `name: {skill.nome_pasta}` para casar com o diretório.",
                "Cada ferramenta escolhe um nome diferente e a skill aparece duplicada.",
            )
        )
    else:
        if not SLUG.fullmatch(nome):
            achados.append(
                finding(
                    "must", "nome", "`name` fora do padrão de slug",
                    local,
                    f"O nome declarado é `{nome}`.",
                    "Letra maiúscula, espaço ou sublinhado quebram o espelhamento em sistema de arquivos e o índice de plugin.",
                    "Use só minúsculas, dígitos e hífen simples — sem repetir hífen.",
                    "O alvo cria um caminho que não casa com o índice e a skill não carrega.",
                )
            )
        if len(nome) > SLUG_MAX:
            achados.append(
                finding(
                    "should", "nome", "`name` mais longo que o limite",
                    local,
                    f"O nome tem {len(nome)} caracteres.",
                    f"Acima de {SLUG_MAX} o caminho do espelho passa do teto de {CAMINHO_MAX} em alvos com diretório profundo.",
                    "Encurte para até 64 caracteres, mantendo o termo que o agente usa para reconhecer a tarefa.",
                    "O espelho estoura o limite de caminho em uma ou duas ferramentas.",
                )
            )
        if nome != skill.nome_pasta:
            achados.append(
                finding(
                    "should", "nome", "`name` diverge do nome da pasta",
                    local,
                    f"O front matter diz `{nome}` e a pasta se chama `{skill.nome_pasta}`.",
                    "O upstream chama de drift de nome: um dos dois vira a chave de instalação e o outro é ignorado.",
                    f"Renomeie a pasta para `{nome}` (ou corrija o campo), e sincronize os espelhos.",
                    "A skill é instalada com um nome e procurada com outro.",
                )
            )

    descricao = skill.descricao
    if not descricao:
        achados.append(
            finding(
                "must", "descricao", "`description` ausente ou vazia",
                local,
                "O campo existe, mas não descreve nada.",
                "A descrição é o único texto que o agente lê para decidir se ativa a skill.",
                "Escreva uma frase no imperativo dizendo o que a skill faz e quando usar.",
                "A skill só é ativada quando o usuário a chama pelo nome exato.",
            )
        )
    else:
        if len(descricao) > DESCRICAO_MAX:
            achados.append(
                finding(
                    "should", "descricao", "Descrição acima do teto do marketplace",
                    local,
                    f"A descrição tem {len(descricao)} caracteres.",
                    f"Acima de {DESCRICAO_MAX} o `marketplace.json` corta o texto e a frase útil fica fora da listagem.",
                    "Mova o detalhe para o corpo e deixe a descrição com uma frase.",
                    "A vitrine mostra um recorte truncado no meio da frase.",
                )
            )
        if len(descricao) < 40:
            achados.append(
                finding(
                    "should", "descricao", "Descrição curta demais para servir de gatilho",
                    local,
                    f"A descrição tem {len(descricao)} caracteres: \"{_resumo(descricao, 80)}\".",
                    "Frase de três palavras não diferencia esta skill de outras parecidas no mesmo domínio.",
                    "Diga o verbo, o objeto e o contexto de uso em uma frase.",
                    "Duas skills do mesmo domínio empatam e o agente escolhe a errada.",
                )
            )
        if not any(gatilho in descricao.lower() for gatilho in GATILHOS):
            achados.append(
                finding(
                    "nice", "descricao", "Descrição sem gatilho explícito",
                    local,
                    "A descrição explica o que a skill faz, mas não quando ativar.",
                    "Sem a cláusula de ativação o agente depende de semelhança lexical para escolher.",
                    "Acrescente um trecho do tipo \"Use quando o usuário pedir …\".",
                    "A skill funciona, mas é acionada menos do que deveria.",
                )
            )

    scripts = skill.por_tipo("script")
    referencias = skill.por_tipo("referencia")
    assets = skill.por_tipo("asset")
    for arquivo in scripts:
        if not _menciona(skill.corpo, arquivo):
            achados.append(
                finding(
                    "should", "script", "Script que o corpo da skill não menciona",
                    f"{skill.pasta}/{_relativo(skill, arquivo)}",
                    f"O arquivo existe, mas `{ARQUIVO_ENTRADA}` não cita o nome nem o caminho.",
                    "Script não documentado é script que o agente nunca executa — custa peso no bundle e não entrega nada.",
                    "Cite o comando exato com `--help` no corpo, ou remova o script.",
                    "O bundle publica código morto e o usuário paga o download.",
                )
            )
    for arquivo in referencias:
        if not _menciona(skill.corpo, arquivo):
            achados.append(
                finding(
                    "nice", "referencia", "Referência não citada no corpo",
                    f"{skill.pasta}/{_relativo(skill, arquivo)}",
                    "O documento de referência não é apontado por nenhum trecho do `SKILL.md`.",
                    "Referência só serve se o corpo disser quando abri-la; sem isso vira leitura não feita.",
                    "Adicione uma linha \"Consulte `references/…` quando …\".",
                    "O material de apoio fica no bundle sem ser lido.",
                )
            )

    if scripts and not skill.dados.get("allowed-tools"):
        achados.append(
            finding(
                "should", "permissoes", "Skill com script e sem `allowed-tools`",
                local,
                f"Há {len(scripts)} script(s) e o front matter não declara ferramentas permitidas.",
                "Sem a lista, a skill herda o conjunto inteiro de ferramentas da sessão.",
                "Declare o mínimo necessário (por exemplo leitura e execução de shell) em `allowed-tools`.",
                "A skill roda com mais permissão do que precisa em todo alvo que respeita o campo.",
            )
        )
    if not skill.dados.get("license"):
        achados.append(
            finding(
                "nice", "licenca", "Skill sem `license` no front matter",
                local,
                "Nenhum campo de licença no cabeçalho.",
                "O marketplace distribui o pacote fora do repositório; sem campo a licença só existe no arquivo do projeto.",
                "Acrescente `license: MIT` (ou a licença real) no front matter.",
                "Quem instala pelo plugin não recebe a informação de licença.",
            )
        )
    if not skill.dados.get("version"):
        achados.append(
            finding(
                "nice", "versao", "Skill sem `version` própria",
                local,
                "A versão só existe no plugin que agrupa a skill.",
                "Atualizar uma skill sem tocar o plugin deixa o instalador sem como detectar a mudança.",
                "Declare `version: X.Y.Z` e suba no patch quando o conteúdo mudar.",
                "O usuário reinstala e recebe a mesma versão antiga em cache.",
            )
        )

    if skill.corpo:
        tamanho_corpo = len(skill.corpo)
        if tamanho_corpo > LIMITES_CORPO["longo"]:
            achados.append(
                finding(
                    "should", "corpo", "Corpo da skill longo demais para carregar",
                    local,
                    f"O corpo tem {tamanho_corpo:,} caracteres.",
                    "Acima de ~12 mil caracteres o texto inteiro entra no contexto para qualquer ativação, mesmo quando só um trecho seria usado.",
                    "Mova explicação extensa para `references/` e deixe no corpo o roteiro curto.",
                    "A skill consome contexto de todas as outras skills da sessão.",
                )
            )
        elif tamanho_corpo < 200:
            achados.append(
                finding(
                    "nice", "corpo", "Corpo curto demais para instruir",
                    local,
                    f"O corpo tem {tamanho_corpo} caracteres.",
                    "Instrução de menos de 200 caracteres raramente cobre caso de erro, limite ou exemplo.",
                    "Inclua um exemplo de entrada e o que fazer quando faltar dado.",
                    "O agente improvisa no primeiro caso fora do caminho feliz.",
                )
            )

    for arquivo in skill.arquivos:
        if arquivo.tipo == "outro" and _nome(arquivo.caminho).lower() not in NOMES_RESERVADOS:
            achados.append(
                finding(
                    "nice", "estrutura", "Arquivo fora das pastas previstas",
                    f"{skill.pasta}/{_relativo(skill, arquivo)}",
                    "O arquivo não está em `scripts/`, `references/` nem `assets/`.",
                    "A estrutura de skill prevê três pastas; arquivo solto na raiz é copiado sem papel definido.",
                    "Mova para a pasta correspondente ou remova.",
                    "O alvo publica o arquivo sem que nenhuma skill o use.",
                )
            )
        if arquivo.tipo == "binario" and arquivo.bytes > 512 * 1024:
            achados.append(
                finding(
                    "should", "tamanho", "Binário acima de meio megabyte",
                    f"{skill.pasta}/{_relativo(skill, arquivo)}",
                    f"O arquivo pesa {arquivo.bytes:,} bytes.",
                    "Asset grande é publicado em todos os espelhos e entra no pacote de cada alvo.",
                    "Comprima, ou hospede fora do bundle e referencie por URL.",
                    "O plugin pode passar do limite de tamanho e a instalação falhar inteira.",
                )
            )

    if alvo is not None and skill.dados:
        fora = []
        for chave in sorted(skill.dados):
            if chave in alvo.remove or (chave not in alvo.mantem and chave not in {"name", "description"}):
                fora.append(chave)
        if fora:
            achados.append(
                finding(
                    "nice", "alvo", f"Campos que o alvo {alvo.nome} descarta",
                    local,
                    f"O front matter declara {', '.join(f'`{chave}`' for chave in fora)}.",
                    "O alvo não lê esses campos: a informação é removida na conversão, não convertida.",
                    "Guarde o que for essencial no corpo do `SKILL.md`, que é copiado para todos os alvos.",
                    "A informação existe no repositório e não existe na ferramenta.",
                )
            )
    return achados


def _resumo_alvos(arquivos: list[Arquivo]) -> list[dict[str, Any]]:
    linhas: list[dict[str, Any]] = []
    for alvo in ALVOS:
        skills = _skills(arquivos)
        mantem = True
        motivo = ""
        if alvo.estilo == "regra" and any(item.tipo in {"script", "referencia", "asset"} for item in arquivos):
            mantem = False
            motivo = "regra é arquivo único: pasta de apoio não acompanha"
        elif alvo.estilo == "convencao" and len(skills) > 1:
            motivo = f"{len(skills)} skills viram seções de um arquivo só"
        linhas.append(
            {
                "id": alvo.id,
                "alvo": alvo.nome,
                "estilo": alvo.estilo,
                "base": alvo.base,
                "estrutura": "completa" if alvo.scripts else "texto",
                "mantem": mantem,
                "motivo": motivo or "estrutura compatível",
            }
        )
    return linhas


def auditar(*, arquivos: str, alvo: str = "", modo: str = "full") -> dict[str, Any]:
    """Confere as skills de um bundle antes de converter para qualquer alvo."""
    modo = _modo(modo)
    inventario = ler_inventario(texto=arquivos)
    grupos = _skills(inventario)
    if not grupos:
        raise PortabilidadeError(f"Nenhuma pasta com `{ARQUIVO_ENTRADA}` no inventário.")
    if len(grupos) > MAX_SKILLS:
        raise PortabilidadeError(f"O bundle passa de {MAX_SKILLS} skills: audite por domínio.")
    alvo_escolhido = _alvo(alvo) if alvo.strip() else None

    findings: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for pasta, itens in grupos.items():
        skill = _montar_skill(pasta, itens)
        achados = _auditar_skill(skill, alvo_escolhido)
        findings.extend(achados)
        rows.append(
            {
                "skill": skill.nome or skill.nome_pasta,
                "pasta": pasta,
                "nome_bate": skill.nome == skill.nome_pasta,
                "descricao": _resumo(skill.descricao, 90) or "—",
                "arquivos": len(itens),
                "scripts": len(skill.por_tipo("script")),
                "referencias": len(skill.por_tipo("referencia")),
                "bytes": skill.bytes,
                "problemas": len(achados),
            }
        )

    soltos = _soltos(inventario)
    if soltos:
        achados_soltos = [item.caminho for item in soltos[:5]]
        findings.append(
            finding(
                "nice", "bundle", "Arquivos fora de qualquer skill",
                ", ".join(f"`{caminho}`" for caminho in achados_soltos) + (" …" if len(soltos) > 5 else ""),
                f"{len(soltos)} arquivo(s) não estão sob nenhuma pasta com `{ARQUIVO_ENTRADA}`.",
                "A conversão publica a skill e ignora o resto: o que está solto não chega a alvo nenhum.",
                "Mova para dentro da pasta da skill (em `scripts/`, `references/` ou `assets/`) ou remova do bundle.",
                "A informação existe no repositório e não existe em nenhuma ferramenta.",
            )
        )

    findings, counts, veredito, perguntas = finalize(findings, modo, _questoes())
    total_bytes = sum(item.bytes for item in inventario)
    com_entrada = sum(1 for pasta in grupos.values() if any(_nome(i.caminho) == ARQUIVO_ENTRADA for i in pasta))
    metrics = {
        "skills": len(grupos),
        "arquivos": len(inventario),
        "comEntrada": com_entrada,
        "scripts": sum(1 for item in inventario if item.tipo == "script"),
        "referencias": sum(1 for item in inventario if item.tipo == "referencia"),
        "assets": sum(1 for item in inventario if item.tipo == "asset"),
        "bytes": total_bytes,
        "soltos": len(soltos),
        "alvo": alvo_escolhido.nome if alvo_escolhido else "todos",
    }
    summary = [
        f"{len(grupos)} skill(s) e {len(inventario)} arquivo(s) — {total_bytes:,} bytes no bundle.",
        f"{counts['must']} bloqueio(s), {counts['should']} correção(ões) e {counts['nice']} ajuste(s) fino(s).",
        "A auditoria lê o bundle; ela não corrige arquivo, não escreve espelho e não instala nada.",
    ]
    achados_alvo = _resumo_alvos(inventario)
    extra = [
        "",
        "## Alvos que aceitam esta estrutura",
        "",
        "| Alvo | Estilo | Base | Estrutura | Veredito |",
        "| --- | --- | --- | --- | --- |",
    ]
    extra += [
        f"| {linha['alvo']} | {linha['estilo']} | `{linha['base']}` | {linha['estrutura']} | {linha['motivo']} |"
        for linha in achados_alvo
    ]
    extra += [
        "",
        "## Skills",
        "",
        "| Skill | Arquivos | Scripts | Referências | Bytes | Problemas |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    extra += [
        f"| `{linha['skill']}` | {linha['arquivos']} | {linha['scripts']} | {linha['referencias']} | {linha['bytes']:,} | {linha['problemas']} |"
        for linha in rows[:MAX_ROWS]
    ]

    resultado = common(
        analysis="auditoria",
        mode=modo,
        title="Auditoria de bundle de skills",
        summary=summary,
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows[:MAX_ROWS],
        metrics=metrics,
        limitations=[
            "Não executa script nenhum das skills: `--help` e smoke test ficam para a etapa de publicação.",
            "Não lê repositório remoto: o inventário é o que foi colado, com ou sem conteúdo.",
            "Não valida YAML completo: lê o subconjunto de front matter que o catálogo usa.",
            "Não mede qualidade da instrução: aponta sintoma estrutural, não se a skill resolve a tarefa.",
        ],
        extra_sections=extra,
    )
    resultado["alvos"] = achados_alvo
    resultado["skills"] = rows[:MAX_ROWS]
    return resultado


# --------------------------------------------------------------- conversão

def _rebaixar_headings(corpo: str) -> str:
    """Rebaixa `#` do corpo para caber sob o cabeçalho da seção."""
    linhas = []
    for linha in corpo.split("\n"):
        if linha.startswith("#"):
            linhas.append("#" + linha)
        else:
            linhas.append(linha)
    return "\n".join(linhas)


def _render_front_matter(dados: dict[str, Any]) -> str:
    if not dados:
        return ""
    linhas = ["---"]
    for chave in dados:
        valor = dados[chave]
        if isinstance(valor, (list, tuple)):
            linhas.append(f"{chave}:")
            linhas.extend(f"  - {str(item)}" for item in valor)
        else:
            texto = str(valor).replace("\n", " ").strip()
            linhas.append(f"{chave}: {texto}")
    linhas.append("---")
    return "\n".join(linhas)


def _front_matter_do_alvo(skill: Skill, alvo: Alvo) -> dict[str, Any]:
    dados: dict[str, Any] = {"description": skill.descricao}
    if "name" in alvo.mantem:
        dados = {"name": skill.nome or skill.nome_pasta, **dados}
    for chave, valor in skill.dados.items():
        if chave in {"name", "description"} or chave in alvo.remove:
            continue
        if chave in alvo.mantem:
            dados[chave] = valor
    return dados


def _destino(skill: Skill, alvo: Alvo, arquivo: Arquivo) -> tuple[str, str]:
    """Devolve (caminho de destino, ação) do arquivo dentro do alvo."""
    slug = skill.nome or skill.nome_pasta
    if alvo.estilo in {"pasta", "espelho"}:
        return f"{alvo.base.replace('<slug>', slug)}/{_relativo(skill, arquivo)}", "copiar"
    if alvo.estilo == "regra":
        if arquivo.tipo == "entrada":
            return f"{alvo.base.replace('<slug>', slug)}", "reescrever"
        return "", "descartar"
    if arquivo.tipo == "entrada":
        return alvo.base, "embutir"
    return "", "descartar"


def converter(*, arquivos: str, alvo: str, modo: str = "full") -> dict[str, Any]:
    """Monta o plano de conversão de um bundle para o formato de uma ferramenta."""
    modo = _modo(modo)
    destino = _alvo(alvo)
    inventario = ler_inventario(texto=arquivos)
    grupos = _skills(inventario)
    if not grupos:
        raise PortabilidadeError(f"Nenhuma pasta com `{ARQUIVO_ENTRADA}` no inventário.")
    if len(grupos) > MAX_SKILLS:
        raise PortabilidadeError(f"O bundle passa de {MAX_SKILLS} skills para um alvo só.")

    findings: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    saida: list[dict[str, Any]] = []
    ocupados: dict[str, str] = {}
    bytes_escritos = 0
    descartados = 0

    for pasta, itens in grupos.items():
        skill = _montar_skill(pasta, itens)
        slug = skill.nome or skill.nome_pasta
        if not SLUG.fullmatch(slug):
            slug = _slug(slug) or "skill"
        for arquivo in itens:
            caminho, acao = _destino(skill, destino, arquivo)
            if not caminho:
                descartados += 1
                rows.append(
                    {
                        "skill": slug,
                        "origem": arquivo.caminho,
                        "destino": "—",
                        "acao": "descartar",
                        "bytes": arquivo.bytes,
                    }
                )
                continue
            if len(caminho) > CAMINHO_MAX:
                findings.append(
                    finding(
                        "should", "caminho", "Destino acima do limite de caminho",
                        arquivo.caminho,
                        f"O caminho de destino tem {len(caminho)} caracteres.",
                        f"O alvo {destino.nome} recusa caminho acima de {CAMINHO_MAX} e a instalação falha por arquivo, não por conteúdo.",
                        "Encurte o slug ou a pasta de origem.",
                        "Um arquivo derruba a instalação inteira do alvo.",
                    )
                )
            dono = ocupados.get(caminho)
            if dono and dono != arquivo.caminho:
                findings.append(
                    finding(
                        "must", "colisao", "Dois arquivos disputam o mesmo destino",
                        caminho,
                        f"`{dono}` e `{arquivo.caminho}` convergem para o mesmo caminho em {destino.nome}.",
                        "A cópia silenciosa sobrescreve: o segundo arquivo apaga o primeiro e o alvo carrega metade da skill.",
                        "Dê nomes distintos às skills ou converta em lotes separados.",
                        "A conversão termina com sucesso e publica uma skill incompleta.",
                    )
                )
            ocupados[caminho] = arquivo.caminho
            if acao == "copiar":
                corpo = arquivo.conteudo
                if arquivo.tipo == "entrada" and skill.dados:
                    cabecalho = _render_front_matter(_front_matter_do_alvo(skill, destino))
                    corpo = (cabecalho + "\n" if cabecalho else "") + skill.corpo
                elif arquivo.tipo == "entrada" and arquivo.conteudo:
                    corpo = arquivo.conteudo
                saida.append({"caminho": caminho, "conteudo": corpo, "acao": "copiar"})
                bytes_escritos += len(corpo.encode())
            elif acao == "reescrever":
                cabecalho = _front_matter_do_alvo(skill, destino)
                for chave, valor in destino.gera:
                    cabecalho[chave] = valor
                cabecalho_texto = _render_front_matter(cabecalho)
                corpo = (cabecalho_texto + "\n" if cabecalho_texto else "") + skill.corpo
                saida.append({"caminho": caminho, "conteudo": corpo, "acao": "reescrever"})
                bytes_escritos += len(corpo.encode())
            rows.append(
                {
                    "skill": slug,
                    "origem": arquivo.caminho,
                    "destino": caminho,
                    "acao": acao,
                    "bytes": len(arquivo.conteudo.encode()) if arquivo.conteudo else arquivo.bytes,
                }
            )

        if destino.estilo == "regra":
            apoios = len([item for item in itens if item.tipo in {"script", "referencia", "asset"}])
            if apoios:
                findings.append(
                    finding(
                        "must", "suporte", "Alvo de regra não carrega a pasta de apoio",
                        skill.pasta,
                        f"A skill tem {apoios} arquivo(s) fora do `SKILL.md` e o alvo {destino.nome} aceita um arquivo só.",
                        "O texto converte, mas o script e a referência citados deixam de existir no projeto do usuário.",
                        "Publique esta skill em um alvo de pasta, ou reescreva o corpo sem depender dos arquivos.",
                        "A regra manda rodar um script que não foi instalado.",
                    )
                )
        if destino.estilo == "convencao":
            if skill.bytes > 20_000:
                findings.append(
                    finding(
                        "nice", "contexto", "Skill grande em arquivo único de convenções",
                        skill.pasta,
                        f"A skill ocupa {skill.bytes:,} bytes no arquivo único.",
                        "`CONVENTIONS.md` é lido inteiro em toda tarefa do projeto; skill de 20 KB compete com o código.",
                        "Deixe no arquivo único só o que vale para toda tarefa e mova o resto para outro alvo.",
                        "Cada mensagem do projeto carrega o bundle de todas as skills instaladas.",
                    )
                )

    if destino.estilo == "espelho":
        indice = json.dumps(
            {
                "generatedBy": "portabilidade.converter",
                "tool": destino.id,
                "skills": [
                    {
                        "name": row["skill"],
                        "path": f"{destino.base.replace('<slug>', row['skill'])}/SKILL.md",
                    }
                    for row in {r["skill"]: r for r in rows}.values()
                ],
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n"
        saida.append({"caminho": "skills-index.json", "conteudo": indice, "acao": "gerar"})
        rows.append(
            {"skill": "—", "origem": "(índice)", "destino": "skills-index.json", "acao": "gerar", "bytes": len(indice.encode())}
        )
        bytes_escritos += len(indice.encode())

    if destino.estilo == "convencao":
        secoes = ["# Convenções do projeto", ""]
        for pasta, itens in grupos.items():
            skill = _montar_skill(pasta, itens)
            secoes += [f"## {skill.nome or skill.nome_pasta}", "", skill.descricao or "(sem descrição)", "", _rebaixar_headings(skill.corpo).strip(), ""]
        convencao = "\n".join(secoes)
        saida = [item for item in saida if item["caminho"] != destino.base]
        saida.append({"caminho": destino.base, "conteudo": convencao, "acao": "reescrever"})
        bytes_escritos += len(convencao.encode())
        rows.append(
            {"skill": "—", "origem": "(seções)", "destino": destino.base, "acao": "reescrever", "bytes": len(convencao.encode())}
        )

    findings, counts, veredito, perguntas = finalize(findings, modo, _questoes())
    lista = [item for item in ocupados if ocupados[item]]
    metrics = {
        "alvo": destino.nome,
        "estilo": destino.estilo,
        "skills": len(grupos),
        "arquivosOrigem": len(inventario),
        "arquivosDestino": len(saida),
        "descartados": descartados,
        "bytes": bytes_escritos,
        "caminhoMaximo": max((len(item["caminho"]) for item in saida), default=0),
        "unico": len(lista) == 1,
    }
    summary = [
        f"{len(grupos)} skill(s) convertida(s) para {destino.nome} no estilo `{destino.estilo}`.",
        f"{len(saida)} arquivo(s) no destino, {descartados} descartado(s), {bytes_escritos:,} bytes escritos.",
        f"Base: `{destino.base}`. {destino.nota}",
    ]
    extra = [
        "",
        "## Plano de escrita",
        "",
        "| Origem | Destino | Ação | Bytes |",
        "| --- | --- | --- | --- |",
    ]
    extra += [
        f"| `{row['origem']}` | `{row['destino']}` | {row['acao']} | {row['bytes']:,} |"
        for row in rows[:MAX_ROWS]
    ]
    resultado = common(
        analysis="conversao",
        mode=modo,
        title=f"Conversão para {destino.nome}",
        summary=summary,
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows[:MAX_ROWS],
        metrics=metrics,
        limitations=[
            "Não escreve nada no disco nem instala: o plano é a lista de arquivos que a conversão faria.",
            "Não executa o `convert.sh` do upstream: o formato de cada alvo é declarado aqui, não absorvido.",
            "Não valida a ferramenta de destino: gatilho, precedência e ativação dependem da versão instalada.",
            f"Campos fora de {', '.join(destino.mantem)} são removidos na conversão, não traduzidos.",
        ],
        extra_sections=extra,
    )
    resultado["saida"] = saida
    return resultado


# ------------------------------------------------------------------ deriva

IGNORAR = {"__pycache__", ".ds_store", ".gitkeep", "thumbs.db"}
STATUS = ("igual", "alterado", "faltando", "sobrando", "nao_comparavel")


def _comparavel(arquivo: Arquivo) -> str:
    if arquivo.conteudo:
        return "conteudo"
    if arquivo.sha:
        return "hash"
    return ""


def _diferenca(fonte: Arquivo, espelho: Arquivo) -> str:
    if fonte.conteudo and espelho.conteudo:
        return "igual" if _sha(fonte.conteudo) == _sha(espelho.conteudo) else "alterado"
    if fonte.sha and espelho.sha:
        curto, outro = fonte.sha[:16], espelho.sha[:16]
        if len(curto) != len(outro):
            tamanho = min(len(curto), len(outro))
            curto, outro = curto[:tamanho], outro[:tamanho]
        return "igual" if curto == outro else "alterado"
    return "nao_comparavel"


def deriva(*, arquivos: str, espelho: str, modo: str = "full", estrito: bool = False) -> dict[str, Any]:
    """Compara a árvore fonte com o espelho publicado e aponta o que divergiu."""
    modo = _modo(modo)
    inventario = ler_inventario(texto=arquivos)
    publicado = ler_inventario(texto=espelho, conteudo=False)
    fonte = {item.caminho: item for item in inventario}
    alvo_mapa = {item.caminho: item for item in publicado}
    if not fonte:
        raise PortabilidadeError("A fonte não trouxe arquivo nenhum.")
    if not alvo_mapa:
        raise PortabilidadeError("O espelho não trouxe arquivo nenhum.")

    findings: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    contagem = {status: 0 for status in STATUS}
    por_conteudo = por_hash = 0

    for caminho in sorted(set(fonte) | set(alvo_mapa)):
        origem = fonte.get(caminho)
        copia = alvo_mapa.get(caminho)
        if origem is not None and copia is not None:
            jeito = "conteudo" if (origem.conteudo and copia.conteudo) else ("hash" if origem.sha and copia.sha else "")
            status = _diferenca(origem, copia)
            if status == "nao_comparavel" and estrito:
                status = "alterado"
            if jeito == "conteudo":
                por_conteudo += 1
            elif jeito == "hash":
                por_hash += 1
            if status == "alterado":
                findings.append(
                    finding(
                        "must", "deriva", "Espelho divergente da fonte",
                        caminho,
                        f"O arquivo existe dos dois lados e o conteúdo não bate ({jeito or 'sem hash'}).",
                        "O espelho é publicado como está: quem instala pela ferramenta recebe uma versão que não existe no repositório.",
                        "Rode a sincronização do espelho a partir da fonte e publique a diferença.",
                        "Duas versões circulam com o mesmo nome e a mais antiga é a que chega ao usuário.",
                    )
                )
        elif origem is not None:
            status = "faltando"
            findings.append(
                finding(
                    "should", "espelho", "Arquivo da fonte ausente no espelho",
                    caminho,
                    "O arquivo está no bundle e não está na árvore publicada.",
                    "A skill chega incompleta: o corpo cita um script ou uma referência que o alvo não recebe.",
                    "Republique o espelho depois de acrescentar o arquivo.",
                    "A instrução manda abrir um arquivo que não foi instalado.",
                )
            )
        else:
            status = "sobrando"
            nome = _nome(caminho).lower()
            if nome not in IGNORAR:
                findings.append(
                    finding(
                        "should", "espelho", "Arquivo no espelho sem fonte",
                        caminho,
                        "O espelho tem um arquivo que a fonte não produz.",
                        "Arquivo órfão sobrevive a todas as sincronizações e ninguém consegue reproduzi-lo.",
                        "Remova do espelho ou traga a origem para o repositório.",
                        "A árvore publicada deixa de ser derivável do repositório.",
                    )
                )
        contagem[status] += 1
        rows.append(
            {
                "arquivo": caminho,
                "status": status,
                "fonte": origem.bytes if origem else 0,
                "espelho": copia.bytes if copia else 0,
                "comparacao": _comparavel(origem) if origem and copia else "—",
            }
        )

    quebrados = [item.caminho for item in publicado if item.symlink and item.caminho not in fonte]
    for caminho in quebrados[:MAX_ROWS]:
        findings.append(
            finding(
                "must", "symlink", "Ponteiro sem destino no espelho",
                caminho,
                "O espelho declara um symlink e a fonte não tem o caminho correspondente.",
                "Symlink quebrado é arquivo vazio para a ferramenta: a skill aparece na lista e falha ao abrir.",
                "Recrie o ponteiro a partir da fonte, ou copie o arquivo em vez de apontar.",
                "A ferramenta lista uma skill que não carrega.",
            )
        )
    duplicados = [item.caminho for item in publicado if item.symlink]
    if duplicados and not quebrados:
        findings.append(
            finding(
                "nice", "symlink", "Espelho depende de ponteiro",
                duplicados[0],
                f"{len(duplicados)} arquivo(s) do espelho são symlink.",
                "Clone sem `core.symlinks=true` transforma ponteiro em arquivo de texto — o Windows é o caso comum.",
                "Prefira cópia real, ou documente o `git clone -c core.symlinks=true` antes da instalação.",
                "O usuário Windows instala um arquivo de texto no lugar da skill.",
            )
        )

    comparados = por_conteudo + por_hash
    total = len(rows)
    cobertura = round(100 * comparados / total) if total else 0
    if contagem["nao_comparavel"]:
        findings.append(
            finding(
                "should", "cobertura", "Comparação parcial por falta de hash",
                f"{contagem['nao_comparavel']} arquivo(s) sem conteúdo nem hash dos dois lados",
                f"{comparados} de {total} caminho(s) puderam ser comparados; {contagem['nao_comparavel']} ficaram sem veredito.",
                "Sem hash dos dois lados a deriva passa despercebida mesmo quando o arquivo mudou.",
                "Gere o inventário com `caminho | bytes | sha256 | tipo` dos dois lados.",
                "A checagem dá verde sem ter olhado o conteúdo.",
            )
        )
    achados, counts, veredito, perguntas = finalize(
        findings, modo, ["Qual dos lados é a fonte da verdade quando a sincronização falhar?"]
    )
    metrics = {
        "fonte": len(fonte),
        "espelho": len(alvo_mapa),
        "iguais": contagem["igual"],
        "alterados": contagem["alterado"],
        "faltando": contagem["faltando"],
        "sobrando": contagem["sobrando"],
        "naoComparaveis": contagem["nao_comparavel"],
        "porConteudo": por_conteudo,
        "porHash": por_hash,
        "cobertura": cobertura,
        "symlinks": len(duplicados),
    }
    summary = [
        f"{len(fonte)} arquivo(s) na fonte e {len(alvo_mapa)} no espelho.",
        f"{contagem['igual']} igual(is), {contagem['alterado']} alterado(s), {contagem['faltando']} faltando, {contagem['sobrando']} sobrando.",
        f"Cobertura da comparação: {cobertura}% ({por_conteudo} por conteúdo, {por_hash} por hash).",
    ]
    extra = [
        "",
        "## Arquivos",
        "",
        "| Arquivo | Status | Fonte | Espelho | Comparação |",
        "| --- | --- | --- | --- | --- |",
    ]
    extra += [
        f"| `{row['arquivo']}` | {row['status']} | {row['fonte']:,} | {row['espelho']:,} | {row['comparacao']} |"
        for row in rows[:MAX_ROWS]
    ]
    resultado = common(
        analysis="deriva",
        mode=modo,
        title="Deriva entre fonte e espelho",
        summary=summary,
        findings=achados,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows[:MAX_ROWS],
        metrics=metrics,
        limitations=[
            "Não acessa o repositório nem o espelho: compara os dois inventários colados.",
            "Não resolve symlink: com só o caminho, o ponteiro é tratado pelo nome, não pelo destino real.",
            "Hash truncado compara só o prefixo comum aos dois lados.",
            "Não executa `diff -rq`: a comparação é de conteúdo ou de hash declarado.",
        ],
        extra_sections=extra,
    )
    resultado["status"] = rows[:MAX_ROWS]
    return resultado


# --------------------------------------------------------------- colisões

def colisoes(*, arquivos: str, modo: str = "full") -> dict[str, Any]:
    """Encontra nome repetido, cópia duplicada e espelho divergente dentro do bundle."""
    modo = _modo(modo)
    inventario = ler_inventario(texto=arquivos)
    grupos = _skills(inventario)
    if not grupos:
        raise PortabilidadeError(f"Nenhuma pasta com `{ARQUIVO_ENTRADA}` no inventário.")

    skills = {pasta: _montar_skill(pasta, itens) for pasta, itens in grupos.items()}
    findings: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []

    por_nome: dict[str, list[Skill]] = {}
    por_chave: dict[str, list[Skill]] = {}
    for skill in skills.values():
        chave = (skill.nome or skill.nome_pasta).lower()
        por_nome.setdefault(chave, []).append(skill)
        slug = _slug(chave)
        por_chave.setdefault(slug, []).append(skill)

    vistos: set[str] = set()
    for chave, lista in sorted(por_nome.items()):
        if len(lista) < 2:
            rows.append(
                {
                    "skill": chave,
                    "pastas": lista[0].pasta,
                    "arquivos": len(lista[0].arquivos),
                    "bytes": lista[0].bytes,
                    "estado": "unica",
                }
            )
            continue
        vistos.add(chave)
        pastas = ", ".join(f"`{item.pasta}`" for item in sorted(lista, key=lambda s: s.pasta))
        hashes = {_sha(item.corpo or json.dumps(item.dados, sort_keys=True)) for item in lista}
        identicas = len(hashes) == 1
        rows.append(
            {
                "skill": chave,
                "pastas": pastas,
                "arquivos": sum(len(item.arquivos) for item in lista),
                "bytes": sum(item.bytes for item in lista),
                "estado": "copia-identica" if identicas else "divergente",
            }
        )
        if identicas:
            findings.append(
                finding(
                    "should", "duplicata", "Skill publicada em dois lugares com o mesmo conteúdo",
                    pastas,
                    f"`{chave}` aparece {len(lista)} vezes e os corpos são idênticos.",
                    "Duas cópias iguais só permanecem iguais enquanto ninguém edita uma delas — o upstream mantém um script de sincronização só para isso.",
                    "Escolha uma cópia canônica e gere a outra por cópia, ou remova a duplicata do bundle.",
                    "A próxima edição de um lado transforma a duplicata em divergência silenciosa.",
                )
            )
        else:
            findings.append(
                finding(
                    "must", "duplicata", "Duas cópias da mesma skill com conteúdo diferente",
                    pastas,
                    f"`{chave}` aparece {len(lista)} vezes com corpos diferentes.",
                    "O mesmo nome em dois caminhos: qual das versões instala depende da ordem do alvo.",
                    "Una as versões (ou torne uma derivada da outra) antes de publicar.",
                    "O usuário recebe uma versão arbitrária da skill.",
                )
            )

    for chave, lista in sorted(por_chave.items()):
        nomes = {((item.nome or item.nome_pasta)) for item in lista}
        if chave in vistos or len(nomes) < 2:
            continue
        findings.append(
            finding(
                "must", "colisao", "Nomes que colidem no mesmo slug",
                ", ".join(f"`{nome}`" for nome in sorted(nomes)),
                f"{', '.join(sorted(nomes))} geram o mesmo slug `{chave}`.",
                "O destino é uma pasta por slug: as duas skills escrevem no mesmo lugar e uma sobrescreve a outra.",
                "Diferencie os nomes com o domínio (por exemplo `eng-…` e `mkt-…`).",
                "A conversão publica uma skill e a outra some.",
            )
        )

    # conteúdo idêntico com nomes diferentes
    por_conteudo: dict[str, list[Skill]] = {}
    for skill in skills.values():
        if skill.corpo:
            por_conteudo.setdefault(_sha(skill.corpo), []).append(skill)
    for digest, lista in sorted(por_conteudo.items()):
        nomes = sorted({(item.nome or item.nome_pasta) for item in lista})
        if len(nomes) < 2:
            continue
        findings.append(
            finding(
                "should", "conteudo", "Skills com corpo idêntico e nomes diferentes",
                ", ".join(f"`{nome}`" for nome in nomes),
                f"{len(nomes)} skills compartilham o mesmo corpo ({digest}).",
                "Cópia com identidade nova dobra o contexto carregado e envelhece igual nos dois lugares.",
                "Extraia o conteúdo comum para `references/` e diferencie o `SKILL.md`, ou mantenha só uma.",
                "O bundle cresce sem entregar capacidade nova.",
            )
        )

    entradas = [item for item in inventario if _nome(item.caminho).lower() == ARQUIVO_ENTRADA.lower()]
    for arquivo in entradas:
        if _nome(arquivo.caminho) != ARQUIVO_ENTRADA:
            findings.append(
                finding(
                    "should", "caixa", "Arquivo de entrada com caixa trocada",
                    arquivo.caminho,
                    "O nome do arquivo não é exatamente `SKILL.md`.",
                    "Sistemas de arquivo com maiúscula e minúscula distintas convivem com o alvo que compara literal.",
                    "Renomeie para `SKILL.md`.",
                    "A skill carrega no Linux e desaparece no alvo que compara o nome do arquivo.",
                )
            )

    achados, counts, veredito, perguntas = finalize(
        findings, modo, ["Quem é a fonte canônica quando as duas cópias forem editadas no mesmo dia?"]
    )
    metrics = {
        "skills": len(skills),
        "nomes": len(por_nome),
        "duplicadas": sum(1 for lista in por_nome.values() if len(lista) > 1),
        "divergentes": sum(1 for row in rows if row["estado"] == "divergente"),
        "slugs": len(por_chave),
        "arquivos": len(inventario),
    }
    summary = [
        f"{metrics['skills']} skill(s) em {len(grupos)} pasta(s); {metrics['nomes']} nome(s) distinto(s).",
        f"{metrics['duplicadas']} nome(s) publicado(s) mais de uma vez, {metrics['divergentes']} com conteúdo diferente.",
        "Colisão é detectada pelo destino, não pelo nome declarado: dois nomes podem gerar o mesmo slug.",
    ]
    extra = [
        "",
        "## Nomes",
        "",
        "| Skill | Pastas | Arquivos | Bytes | Estado |",
        "| --- | --- | --- | --- | --- |",
    ]
    extra += [
        f"| `{row['skill']}` | {row['pastas']} | {row['arquivos']} | {row['bytes']:,} | {row['estado']} |"
        for row in rows[:MAX_ROWS]
    ]
    resultado = common(
        analysis="colisoes",
        mode=modo,
        title="Colisões e duplicatas do bundle",
        summary=summary,
        findings=achados,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows[:MAX_ROWS],
        metrics=metrics,
        limitations=[
            "Não segue symlink: compara caminhos declarados no inventário.",
            "Não sabe qual cópia o alvo escolhe quando a ordem de instalação decide.",
            "Não compara corpo inteiro quando o inventário vem só com hash.",
            "Não corrige nada: aponta a colisão e o caminho que a resolve.",
        ],
        extra_sections=extra,
    )
    return resultado


# ------------------------------------------------------------------ lote

CHAVES_PLUGIN = {"name", "description", "version", "author", "homepage", "repository", "license", "skills"}
RE_REPO = re.compile(r"^https://[a-z0-9.-]+/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
DESCRICAO_PLUGIN_MAX = 400


def _validar_identidade(*, marketplace: str, versao: str, autor: str, repo: str, licenca: str) -> dict[str, str]:
    if not SLUG.fullmatch(marketplace):
        raise PortabilidadeError(f"Nome de marketplace inválido: `{marketplace}`. Use slug em minúsculas.")
    if len(marketplace) > SLUG_MAX:
        raise PortabilidadeError(f"O nome do marketplace passa de {SLUG_MAX} caracteres.")
    if not SEMVER.fullmatch(versao):
        raise PortabilidadeError(f"Versão inválida: `{versao}`. Use `X.Y.Z` (semver).")
    if not autor.strip():
        raise PortabilidadeError("Informe o autor: o `plugin.json` recusa instalação sem `author`.")
    if not repo.strip():
        raise PortabilidadeError("Informe o repositório: `homepage` e `repository` são chaves obrigatórias.")
    if not RE_REPO.fullmatch(repo.strip()):
        raise PortabilidadeError(f"Repositório inválido: `{repo}`. Use `https://github.com/dono/repo`.")
    if not licenca.strip():
        raise PortabilidadeError("Informe a licença: é uma das oito chaves obrigatórias.")
    return {
        "marketplace": marketplace,
        "versao": versao,
        "autor": autor.strip(),
        "repo": repo.strip(),
        "licenca": licenca.strip(),
    }


def _url_autor(repo: str) -> str:
    limpo = repo.rstrip("/")
    partes = limpo.split("/")
    if len(partes) >= 2 and partes[-1] and partes[-2]:
        return "/".join(partes[:-1])
    return limpo


def _dominio(pasta: str, forcar: str) -> str:
    if forcar:
        return _slug(forcar) or forcar
    partes = pasta.split("/")
    if len(partes) > 1 and partes[0] not in {"skills"}:
        return _slug(partes[0]) or "geral"
    return "geral"


def lote(
    *,
    arquivos: str,
    marketplace: str = "skills-do-projeto",
    versao: str = "1.0.0",
    autor: str = "",
    repo: str = "",
    licenca: str = "MIT",
    dominio: str = "",
    modo: str = "full",
) -> dict[str, Any]:
    """Agrupa as skills em plugins de marketplace com `plugin.json` válido."""
    modo = _modo(modo)
    identidade = _validar_identidade(
        marketplace=marketplace, versao=versao, autor=autor, repo=repo, licenca=licenca
    )
    inventario = ler_inventario(texto=arquivos)
    grupos = _skills(inventario)
    if not grupos:
        raise PortabilidadeError(f"Nenhuma pasta com `{ARQUIVO_ENTRADA}` no inventário.")
    if len(grupos) > MAX_SKILLS:
        raise PortabilidadeError(f"O bundle passa de {MAX_SKILLS} skills: publique por domínio.")

    findings: list[dict[str, Any]] = []
    plugins: dict[str, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    ocupados: dict[str, str] = {}

    for pasta, itens in grupos.items():
        skill = _montar_skill(pasta, itens)
        slug = _slug(skill.nome or skill.nome_pasta) or "skill"
        if slug in ocupados and ocupados[slug] != pasta:
            findings.append(
                finding(
                    "must", "colisao", "Duas skills com o mesmo slug no lote",
                    f"`{ocupados[slug]}` e `{pasta}`",
                    "O plugin aponta para o mesmo diretório duas vezes.",
                    "A segunda entrada sobrescreve a primeira na instalação.",
                    "Renomeie uma das skills antes de gerar o lote.",
                    "O plugin instala uma skill e promete duas.",
                )
            )
            continue
        ocupados[slug] = pasta
        dono = _dominio(pasta, dominio)
        if not skill.descricao:
            findings.append(
                finding(
                    "must", "descricao", "Skill sem descrição não entra no plugin",
                    pasta,
                    "O marketplace usa a descrição da skill para montar a vitrine.",
                    "Sem descrição o plugin publica uma entrada em branco.",
                    "Acrescente `description` no front matter antes de publicar.",
                    "A vitrine mostra um item vazio e ninguém instala.",
                )
            )
        entrada = plugins.setdefault(
            dono,
            {"nome": dono, "skills": [], "bytes": 0, "descricao": "", "keywords": []},
        )
        entrada["skills"].append({"slug": slug, "pasta": pasta, "descricao": skill.descricao})
        entrada["bytes"] += skill.bytes

    if not plugins:
        raise PortabilidadeError("Nenhuma skill válida para agrupar em plugin.")

    saida: list[dict[str, Any]] = []
    manifestos: list[dict[str, Any]] = []
    for nome, entrada in sorted(plugins.items()):
        skills = entrada["skills"]
        descricao = f"{len(skills)} skill(s) de {nome}: " + "; ".join(
            _resumo(item["descricao"], 60) for item in skills[:3]
        )
        descricao = _resumo(descricao, DESCRICAO_PLUGIN_MAX - 1)
        keywords = sorted({palavra for item in skills for palavra in re.findall(r"[a-z]{4,}", item["slug"])})[:MAX_KEYWORDS]
        plugin = {
            "name": nome,
            "description": descricao,
            "version": identidade["versao"],
            "author": {"name": identidade["autor"], "url": _url_autor(identidade["repo"])},
            "homepage": identidade["repo"],
            "repository": identidade["repo"],
            "license": identidade["licenca"],
            "skills": [f"./skills/{item['slug']}" for item in skills],
        }
        saida.append({"caminho": f"{nome}/.claude-plugin/plugin.json", "conteudo": json.dumps(plugin, ensure_ascii=False, indent=2) + "\n", "acao": "gerar"})
        manifestos.append(plugin)
        if entrada["bytes"] > TAMANHO_PLUGIN_MAX:
            findings.append(
                finding(
                    "must", "tamanho", "Plugin acima do limite de empacotamento",
                    nome,
                    f"O plugin soma {entrada['bytes']:,} bytes; o limite prático é {TAMANHO_PLUGIN_MAX:,}.",
                    "Pacote grande é recusado ou fica lento demais para instalar em todas as ferramentas.",
                    "Divida o domínio em dois plugins ou mova assets para armazenamento externo.",
                    "A instalação falha no meio e deixa lixo no projeto.",
                )
            )
        if len(skills) > 24:
            findings.append(
                finding(
                    "should", "tamanho", "Plugin com mais skills do que cabe em uma vitrine",
                    nome,
                    f"O plugin agrupa {len(skills)} skills.",
                    "Vitrine longa esconde a skill que o usuário procura; o upstream trabalha com pods de até 24.",
                    "Divida por tarefa (conteúdo, canais, análise) em vez de por área.",
                    "O usuário instala o pacote inteiro para usar uma skill.",
                )
            )
        if len(skills) == 1:
            findings.append(
                finding(
                    "nice", "tamanho", "Plugin de uma skill só",
                    nome,
                    "O grupo tem uma única skill.",
                    "Plugin de skill única é melhor publicado como skill avulsa: o usuário evita um pacote.",
                    "Publique a skill direto no marketplace, sem nível de plugin.",
                    "O marketplace fica com plugins que só repetem o nome da skill.",
                )
            )
        rows.append(
            {
                "plugin": nome,
                "skills": len(skills),
                "bytes": entrada["bytes"],
                "keywords": len(keywords),
                "manifesto": len(json.dumps(plugin, ensure_ascii=False)),
            }
        )

    mercado = {
        "name": identidade["marketplace"],
        "owner": {"name": identidade["autor"], "url": _url_autor(identidade["repo"])},
        "description": f"{len(ocupados)} skill(s) em {len(plugins)} plugin(s) publicados a partir de um bundle.",
        "homepage": identidade["repo"],
        "repository": identidade["repo"],
        "metadata": {"version": identidade["versao"], "license": identidade["licenca"]},
        "plugins": [
            {
                "name": item["name"],
                "source": f"./{item['name']}",
                "description": item["description"],
                "version": item["version"],
                "author": {"name": identidade["autor"]},
                "category": "engineering",
            }
            for item in manifestos
        ],
    }
    saida.append({"caminho": ".claude-plugin/marketplace.json", "conteudo": json.dumps(mercado, ensure_ascii=False, indent=2) + "\n", "acao": "gerar"})

    for plugin in manifestos:
        fora = set(plugin) - CHAVES_PLUGIN
        if fora:
            findings.append(
                finding(
                    "must", "schema", "Chave fora do schema no `plugin.json`",
                    f"{plugin['name']}/.claude-plugin/plugin.json",
                    f"Chaves não previstas: {', '.join(sorted(fora))}.",
                    "Qualquer chave extra faz o validador recusar o manifesto e derrubar a instalação do plugin inteiro.",
                    "Mova a informação para um arquivo irmão que a ferramenta não lê.",
                    "O plugin fica ininstalável mesmo com o conteúdo correto.",
                )
            )
        if not SEMVER.fullmatch(str(plugin["version"])):
            findings.append(
                finding(
                    "must", "schema", "Versão fora de semver no `plugin.json`",
                    f"{plugin['name']}/.claude-plugin/plugin.json",
                    f"A versão é `{plugin['version']}`.",
                    "O marketplace ordena e compara versão por semver; fora disso a atualização não é detectada.",
                    "Use `X.Y.Z` e suba o patch a cada publicação.",
                    "O usuário não recebe atualização.",
                )
            )
        if problem := [item for item in plugin["skills"] if not item.startswith("./")]:
            findings.append(
                finding(
                    "must", "schema", "Caminho de skill sem `./` no manifesto",
                    f"{plugin['name']}/.claude-plugin/plugin.json",
                    f"{len(problem)} caminho(s) não começam com `./`: {', '.join(problem[:3])}.",
                    "A versão atual do Claude Code recusa caminho relativo sem o prefixo — o manifesto inteiro falha.",
                    "Prefixe cada caminho com `./`.",
                    "A instalação do plugin para no manifesto, antes de copiar arquivo.",
                )
            )

    achados, counts, veredito, perguntas = finalize(
        findings,
        modo,
        ["Quem é o dono de cada plugin quando o domínio mudar de nome?", "O versionamento acompanha o plugin ou a skill?"],
    )
    total_bytes = sum(entrada["bytes"] for entrada in plugins.values())
    metrics = {
        "marketplace": identidade["marketplace"],
        "versao": identidade["versao"],
        "plugins": len(plugins),
        "skills": len(ocupados),
        "bytes": total_bytes,
        "maiorPlugin": max((entrada["bytes"] for entrada in plugins.values()), default=0),
        "manifestos": len(saida),
    }
    summary = [
        f"{len(ocupados)} skill(s) distribuída(s) em {len(plugins)} plugin(s) sob `{identidade['marketplace']}`.",
        f"{len(saida)} manifesto(s) gerado(s), {total_bytes:,} bytes de conteúdo.",
        f"Chaves do `plugin.json`: {', '.join(sorted(CHAVES_PLUGIN))} — nenhuma a mais.",
    ]
    extra = [
        "",
        "## Plugins",
        "",
        "| Plugin | Skills | Bytes | Keywords | Manifesto |",
        "| --- | --- | --- | --- | --- |",
    ]
    extra += [
        f"| `{row['plugin']}` | {row['skills']} | {row['bytes']:,} | {row['keywords']} | {row['manifesto']:,} |"
        for row in rows[:MAX_ROWS]
    ]
    extra += ["", "## `plugin.json` proposto", "", "```json", json.dumps(manifestos[0], ensure_ascii=False, indent=2), "```"]
    resultado = common(
        analysis="lote",
        mode=modo,
        title="Lote para marketplace",
        summary=summary,
        findings=achados,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows[:MAX_ROWS],
        metrics=metrics,
        limitations=[
            "Não escreve os manifestos nem empacota: o JSON do parecer é a proposta.",
            "Não valida contra o servidor do marketplace: as oito chaves vêm do schema declarado pelo upstream.",
            "Não publica nem versiona: o número de versão é o informado na chamada.",
            "Não separa skill de domínio por assunto — o agrupamento é pela primeira pasta do caminho.",
        ],
        extra_sections=extra,
    )
    resultado["saida"] = saida
    resultado["manifestos"] = manifestos
    return resultado


# ----------------------------------------------------------------- matriz

def _suporta(alvo: Alvo, arquivo: Arquivo) -> bool:
    if arquivo.tipo == "entrada":
        return True
    if alvo.estilo == "convencao":
        return False
    if alvo.estilo == "regra":
        return False
    if arquivo.tipo == "script":
        return alvo.scripts
    if arquivo.tipo == "referencia":
        return alvo.referencias
    if arquivo.tipo == "asset":
        return alvo.assets
    return True


def matriz(*, arquivos: str, alvos: str = "", modo: str = "full") -> dict[str, Any]:
    """Cruza cada skill com cada ferramenta e mostra o que sobrevive na conversão."""
    modo = _modo(modo)
    inventario = ler_inventario(texto=arquivos)
    grupos = _skills(inventario)
    if not grupos:
        raise PortabilidadeError(f"Nenhuma pasta com `{ARQUIVO_ENTRADA}` no inventário.")
    if alvos.strip():
        escolhidos = [_alvo(item) for item in re.split(r"[,\s]+", alvos.strip()) if item]
        if not escolhidos:
            raise PortabilidadeError("Nenhum alvo válido na lista.")
        if len(escolhidos) > len(ALVOS):
            raise PortabilidadeError("Lista de alvos maior que o catálogo.")
    else:
        escolhidos = list(ALVOS)

    findings: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    celulas: dict[tuple[str, str], str] = {}
    totais = {alvo.id: {"ok": 0, "parcial": 0, "zero": 0} for alvo in escolhidos}

    for pasta, itens in grupos.items():
        skill = _montar_skill(pasta, itens)
        slug = skill.nome or skill.nome_pasta
        for alvo in escolhidos:
            apoios = [item for item in itens if item.tipo != "entrada"]
            mantidos = sum(1 for item in apoios if _suporta(alvo, item))
            perdidos = len(apoios) - mantidos
            if not apoios:
                estado = "completo"
            elif mantidos == 0:
                estado = "so-entrada"
            elif perdidos:
                estado = "parcial"
            else:
                estado = "completo"
            celulas[(pasta, alvo.id)] = {"completo": "ok", "parcial": "parcial", "so-entrada": "zero"}[estado]
            totais[alvo.id][{"completo": "ok", "parcial": "parcial", "so-entrada": "zero"}[estado]] += 1
            rows.append(
                {
                    "skill": slug,
                    "alvo": alvo.nome,
                    "estado": estado,
                    "mantidos": mantidos,
                    "perdidos": perdidos,
                    "base": alvo.base.replace("<slug>", _slug(slug)),
                }
            )
            if estado == "so-entrada" and perdidos:
                findings.append(
                    finding(
                        "must", "alvo", f"Skill perde todo o apoio em {alvo.nome}",
                        f"{pasta} → `{alvo.base.replace('<slug>', _slug(slug))}`",
                        f"{perdidos} arquivo(s) de apoio não têm equivalente no alvo {alvo.nome}.",
                        "O `SKILL.md` chega sozinho e o procedimento cita arquivos que não existem na ferramenta.",
                        "Publique em um alvo de pasta, ou reescreva a skill para não depender dos arquivos.",
                        "A skill carrega e falha no primeiro passo que abre o arquivo de apoio.",
                    )
                )
            elif estado == "parcial":
                findings.append(
                    finding(
                        "should", "alvo", f"Conversão parcial para {alvo.nome}",
                        f"{pasta} → `{alvo.base.replace('<slug>', _slug(slug))}`",
                        f"{perdidos} de {len(apoios)} arquivo(s) de apoio são descartados.",
                        "Conteúdo que existe no repositório não chega à ferramenta e a diferença não aparece para quem instala.",
                        "Declare no README do alvo o que não acompanha, ou mova o essencial para o corpo.",
                        "Duas pessoas usam a mesma skill com capacidades diferentes.",
                    )
                )

    for alvo in escolhidos:
        conta = totais[alvo.id]
        if conta["ok"] == 0 and conta["parcial"] == 0:
            findings.append(
                finding(
                    "nice", "alvo", f"{alvo.nome} não recebe nenhuma skill completa",
                    alvo.base,
                    "Todas as skills do bundle perdem apoio neste alvo.",
                    "Alvo que só recebe texto raramente justifica o esforço de conversão.",
                    "Converta apenas os alvos em que o bundle mantém a estrutura.",
                    "O trabalho de conversão rende uma versão capenga da skill.",
                )
            )

    achados, counts, veredito, perguntas = finalize(
        findings, modo, ["Qual alvo é o principal — aquele em que a perda de apoio é aceitável?"]
    )
    grade = ["| Skill | " + " | ".join(alvo.nome for alvo in escolhidos) + " |"]
    grade.append("| --- | " + " | ".join("---" for _ in escolhidos) + " |")
    simbolos = {"ok": "✓", "parcial": "parte", "zero": "—"}
    for pasta in list(grupos)[:60]:
        skill = _montar_skill(pasta, grupos[pasta])
        linha = [f"| `{skill.nome or skill.nome_pasta}` "]
        linha += [f"| {simbolos[celulas[(pasta, alvo.id)]]} " for alvo in escolhidos]
        grade.append("".join(linha) + "|")
    if len(grupos) > 60:
        grade.append(f"| *(+{len(grupos) - 60} skills)* |" + " |" * len(escolhidos))

    metrics = {
        "skills": len(grupos),
        "alvos": len(escolhidos),
        "pares": len(rows),
        "completos": sum(1 for row in rows if row["estado"] == "completo"),
        "parciais": sum(1 for row in rows if row["estado"] == "parcial"),
        "perdidos": sum(1 for row in rows if row["estado"] == "so-entrada"),
        "melhorAlvo": max(escolhidos, key=lambda a: totais[a.id]["ok"]).nome,
    }
    summary = [
        f"{len(grupos)} skill(s) × {len(escolhidos)} alvo(s) = {len(rows)} par(es).",
        f"{metrics['completos']} conversão(ões) sem perda, {metrics['parciais']} parciais e {metrics['perdidos']} sem apoio.",
        f"Alvo que preserva mais estrutura: {metrics['melhorAlvo']}.",
    ]
    extra = ["", "## Matriz skill × alvo", "", *grade]
    resultado = common(
        analysis="matriz",
        mode=modo,
        title="Matriz de portabilidade",
        summary=summary,
        findings=achados,
        counts=counts,
        verdict=veredito,
        questions=perguntas,
        rows=rows[:MAX_ROWS],
        metrics=metrics,
        limitations=[
            "Não testa a ferramenta: a matriz vem da estrutura declarada de cada alvo, não de execução.",
            "Não considera limite de contexto do alvo — só a perda de arquivo.",
            "Não mede qualidade da conversão de texto: regra e convenção mudam o formato, não a prosa.",
            "Não cobre alvo fora dos treze declarados no catálogo.",
        ],
        extra_sections=extra,
    )
    resultado["matriz"] = [
        {
            "skill": _montar_skill(pasta, grupos[pasta]).nome or _montar_skill(pasta, grupos[pasta]).nome_pasta,
            "alvos": {alvo.id: celulas[(pasta, alvo.id)] for alvo in escolhidos},
        }
        for pasta in grupos
    ]
    resultado["totais"] = {alvo.id: totais[alvo.id] for alvo in escolhidos}
    return resultado


# --------------------------------------------------------------- catálogo

def catalogo() -> dict[str, Any]:
    """Publica alvos, estilos, regras e limites da camada de portabilidade."""
    return {
        "versao": VERSAO,
        "origem": {
            "projeto": "alirezarezvani/claude-skills",
            "licenca": "MIT",
            "estrelas": 28_656,
            "forks": 3_980,
            "scripts": ["convert.sh", "install.sh", "sync-*-skills.py", "check_dual_publish.py", "check_plugin_json.py"],
        },
        "principio": (
            "Uma skill só é portátil quando o formato do alvo é declarado antes da conversão: "
            "o que copia, o que reescreve, o que embute e o que se perde fica no plano, não na sorte."
        ),
        "alvos": [
            {
                "id": alvo.id,
                "nome": alvo.nome,
                "estilo": alvo.estilo,
                "base": alvo.base,
                "extensao": alvo.extensao,
                "carrega": [
                    rotulo
                    for rotulo, suporta in (
                        ("scripts", alvo.scripts),
                        ("referencias", alvo.referencias),
                        ("assets", alvo.assets),
                        ("agentes", alvo.agentes),
                        ("comandos", alvo.comandos),
                    )
                    if suporta
                ],
                "mantem": list(alvo.mantem),
                "remove": list(alvo.remove),
                "nota": alvo.nota,
            }
            for alvo in ALVOS
        ],
        "estilos": {
            "pasta": "diretório próprio com SKILL.md e as três pastas de apoio",
            "espelho": "diretório gerado a partir da fonte, mais um índice de skills",
            "regra": "arquivo único no diretório de regras da ferramenta",
            "convencao": "um arquivo por projeto, com todas as skills como seções",
        },
        "estrutura": {
            "entrada": ARQUIVO_ENTRADA,
            "pastas": dict(PASTAS),
            "reservados": sorted(NOMES_RESERVADOS),
            "binarios": sorted(EXT_BINARIA),
        },
        "regras": [
            "Front matter reduzido ao que o alvo lê: campo fora da lista é removido, não traduzido.",
            "Nome da skill é slug: minúscula, dígito e hífen simples, até 64 caracteres.",
            "Caminho de skill no manifesto começa com `./`; sem isso o `plugin.json` inteiro é recusado.",
            "`plugin.json` tem exatamente oito chaves: name, description, version, author, homepage, repository, license, skills.",
            "Alvo de regra e de convenção não carregam script, referência nem asset — a perda é declarada.",
            "Espelho é derivado: divergência entre fonte e espelho é bloqueio, não observação.",
            "Duas skills com o mesmo slug no mesmo lote é colisão de destino, mesmo que os nomes declarados difiram.",
            "Skill com script e sem `allowed-tools` herda todas as ferramentas da sessão.",
            "`CONVENTIONS.md` é lido inteiro em toda tarefa: skill grande ali compete com o código.",
            "Nada é escrito, copiado ou instalado: o plano de conversão é o produto.",
        ],
        "limites": {
            "texto": MAX_TEXTO,
            "arquivos": MAX_ARQUIVOS,
            "skills": MAX_SKILLS,
            "plugins": MAX_PLUGINS,
            "caminho": CAMINHO_MAX,
            "slug": SLUG_MAX,
            "descricao": DESCRICAO_MAX,
            "plugin_bytes": TAMANHO_PLUGIN_MAX,
            "linhas": MAX_ROWS,
        },
        "operacoes": [
            {"id": "auditar", "entrada": "bundle", "saida": "achados por skill"},
            {"id": "converter", "entrada": "bundle + alvo", "saida": "plano de arquivos"},
            {"id": "deriva", "entrada": "fonte + espelho", "saida": "status por arquivo"},
            {"id": "colisoes", "entrada": "bundle", "saida": "duplicata e slug repetido"},
            {"id": "lote", "entrada": "bundle + identidade", "saida": "plugin.json e marketplace.json"},
            {"id": "matriz", "entrada": "bundle + alvos", "saida": "skill × alvo"},
        ],
        "nao_faz": [
            "Não baixa repositório nem lê o GitHub: o inventário é o que foi colado.",
            "Não executa script de skill, `convert.sh` ou `install.sh`.",
            "Não chama modelo de linguagem para reescrever instrução de skill.",
            "Não publica no marketplace nem versiona pacote.",
        ],
    }
