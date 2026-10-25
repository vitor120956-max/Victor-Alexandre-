"""Auto-alteração com permissão: mapear, propor, medir risco, ensaiar e promover.

Esta camada é a única que pode mudar o próprio código do projeto. Por isso o
desenho inverte a ordem usual: nada é escrito antes de ser ensaiado, e o ensaio
acontece numa **cópia** em `storage/evolucao/ensaios/<id>/`, nunca na árvore
viva. A promoção só existe depois de três provas:

1. **proposta** — o diff aplica de fato sobre o arquivo atual, hunk por hunk;
2. **guardas** — o diff não desmonta nenhuma das leis do projeto (token de host,
   allowlist, `shell=False`, `executed: false` das skills de leitura);
3. **ensaio** — a suíte roda na cópia com o patch aplicado e passa.

Promover exige ainda a trava `JARVIS_HOST_EVOLUIR=1`, o token de uso único
devolvido pelo ensaio, e que o arquivo vivo esteja **idêntico** ao que foi
ensaiado e **sem alteração não commitada**. Antes de escrever, cada arquivo
tocado é copiado para `storage/evolucao/backups/<id>/`, e `evoluir.reverter`
restaura a partir dali.

O que esta camada não faz: criar branch, commitar, reiniciar a API, gerar o
patch (quem gera é você ou o modelo externo) e julgar se a mudança é boa.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .review import common, finalize, finding

VERSAO = "0.40.0"

PROJETO = Path(__file__).resolve().parent.parent
STORAGE = PROJETO / "storage" / "evolucao"
ENSAIOS = STORAGE / "ensaios"
BACKUPS = STORAGE / "backups"
AUDITORIA = STORAGE / "audit.jsonl"
TOKEN_ARQUIVO = PROJETO / "storage" / "host-token.txt"

AMBIENTE_EVOLUIR = "JARVIS_HOST_EVOLUIR"

MAX_DIFF = 900_000
MAX_ARQUIVOS = 40
MAX_HUNKS = 200
MAX_ROWS = 200
MODOS = ("lite", "full", "ultra")

# O que um patch pode tocar. Fora disso, recusa.
RAIZES_PERMITIDAS = ("server/", "src/", "docs/", "public/", "tests/")
ARQUIVOS_RAIZ = {
    "README.md",
    "package.json",
    "pytest.ini",
    "tsconfig.json",
    "vite.config.ts",
    "index.html",
    "requirements.txt",
    "requirements-dev.txt",
    ".env.example",
    ".gitignore",
    "package-lock.json",
}
EXTENSOES = {
    ".py",
    ".ts",
    ".tsx",
    ".css",
    ".md",
    ".json",
    ".html",
    ".toml",
    ".txt",
    ".ini",
    ".example",
}

# Nada disto entra num patch, nem por engano.
PROIBIDOS = (
    ".git/",
    "storage/",
    "node_modules/",
    ".venv/",
    "dist/",
    "cofre/",
    "uploads/",
)
PROIBIDOS_ARQUIVO = (".env", ".key", ".pem", ".pfx", ".p12", ".pem")

# Marca de guarda: se o patch **remove** uma destas linhas, é bloqueio.
MARCAS_DE_GUARDA = {
    "_exigir(": "exigência de token de host",
    "compare_digest": "comparação constante do token",
    "shell=False": "execução sem shell",
    "_dentro_da_quarentena": "confinamento na quarentena",
    "requires_confirmation": "confirmação obrigatória",
    '"executed": False': "marca de não execução",
    '"readOnly": True': "marca de leitura",
    "_autorizado(": "checagem de autorização",
    "JARVIS_HOST_REDE": "trava de rede",
    "JARVIS_HOST_INSTALAR": "trava de instalação",
}

# Elevação de privilégio: o achado que a camada não podia deixar passar.
# Casa `sudo comando`, `sudo -n comando` e `"sudo"` dentro de uma lista de argv.
PADRAO_SUDO = r"[\"']sudo[\"']|(?<![\w-])sudo\s+(?:-{1,2}[\w-]+\s+)*[\w/.\-]"
PADRAO_ELEVACAO = r"[\"'](?:pkexec|doas|runas|su)[\"']|\bpkexec\b|\bdoas\s+|\brunas\s+/|\bsu\s+-\s+"

# Padrões que um patch **acrescenta** e que mudam o perfil de risco.
PERIGOS: tuple[tuple[str, str, str, str], ...] = (
    (r"\beval\s*\(", "must", "Código avaliado em tempo de execução", "`eval` executa texto como código."),
    (r"(?<![\w.])exec\s*\(", "must", "Código executado dinamicamente", "`exec` executa texto como código."),
    (r"os\.system\s*\(", "must", "Shell do sistema", "`os.system` abre shell e junta a linha de comando."),
    (r"shell\s*=\s*True", "must", "Shell ligado", "`shell=True` transforma argumento em linha de comando interpretada."),
    (r"pickle\.(loads|load)\s*\(", "must", "Desserialização insegura", "`pickle` executa código ao carregar."),
    (r"__import__\s*\(", "must", "Importação dinâmica", "`__import__` carrega módulo por nome em tempo de execução."),
    (r"yaml\.load\s*\((?!.*Loader)", "should", "YAML sem Loader seguro", "`yaml.load` sem `SafeLoader` instancia objetos arbitrários."),
    (r"chmod\s*\(\s*[^,]+,\s*0o?777", "should", "Permissão 777", "777 dá escrita a qualquer usuário do sistema."),
    (r"verify\s*=\s*False", "must", "Verificação de TLS desligada", "Sem verificação, qualquer intermediário se passa pelo servidor."),
    (r"disable_warnings|InsecureRequestWarning", "should", "Aviso de TLS silenciado", "Silenciar o aviso esconde o risco em vez de resolvê-lo."),
    (r"(?i)(api[_-]?key|secret|password|senha|token)\s*=\s*[\"'][A-Za-z0-9_\-]{16,}[\"']", "must", "Segredo embutido no código", "Chave no fonte vaza no histórico do Git."),
    (r"AKIA[0-9A-Z]{16}", "must", "Chave da AWS embutida", "Credencial de nuvem no código."),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "must", "Chave privada no patch", "Chave privada nunca entra no repositório."),
    (
        PADRAO_SUDO,
        "must",
        "Elevação de privilégio com sudo",
        "`sudo` troca o usuário do processo por root e escapa de todas as travas da camada.",
    ),
    (
        PADRAO_ELEVACAO,
        "must",
        "Elevação de privilégio por outro caminho",
        "`pkexec`, `doas`, `runas` e `su -` existem para virar root; num patch, isso é sempre decisão humana.",
    ),
    (
        r"chmod\s+(?:[ugoa]*\+s|0?[4-7][0-7]{3})\b",
        "should",
        "Bit setuid ou setgid",
        "Binário com bit setuid roda como o dono, não como quem chamou.",
    ),
)

# Padrões que, sozinhos, já pedem revisão humana: somam além do peso normal.
PADROES_CRITICOS = (PADRAO_SUDO, PADRAO_ELEVACAO)

# Arquivos cujo toque eleva o risco por concentrarem as travas do projeto.
ARQUIVOS_CENTRAIS = {
    "server/sistema.py": 18,
    "server/app.py": 16,
    "server/skill_registry.py": 15,
    "server/review.py": 10,
    "server/evolucao.py": 20,
    ".env.example": 8,
}

DIFF_GIT = re.compile(r"^diff --git a/(\S+) b/(\S+)$")
ANTIGO = re.compile(r"^--- (?:a/)?(\S+)")
NOVO = re.compile(r"^\+\+\+ (?:b/)?(\S+)")
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@ ?(.*)$")

CONFIRMACAO_TTL = 900
_CONFIRMACAO: dict[str, dict[str, Any]] = {}


class EvolucaoError(ValueError):
    """Entrada inválida ou operação recusada por guarda."""


def _modo(valor: str) -> str:
    modo = (valor or "full").strip().lower()
    if modo not in MODOS:
        raise EvolucaoError(f"Modo inválido: use {', '.join(MODOS)}.")
    return modo


# ---------------------------------------------------------------------------
# Travas
# ---------------------------------------------------------------------------


def _token_host() -> str:
    try:
        if TOKEN_ARQUIVO.exists():
            return TOKEN_ARQUIVO.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return ""


def _autorizado(autorizacao: str) -> tuple[bool, str]:
    esperado = _token_host()
    if not esperado:
        return False, "Token de host ausente: suba a API uma vez para gerar storage/host-token.txt."
    if not (autorizacao or "").strip():
        return False, "Modo host exige o token de storage/host-token.txt."
    if not hmac.compare_digest(autorizacao.strip(), esperado):
        return False, "Token de host inválido."
    return True, ""


def _exigir(autorizacao: str) -> None:
    ok, motivo = _autorizado(autorizacao)
    if not ok:
        raise EvolucaoError(motivo)


def _exigir_evoluir(autorizacao: str) -> None:
    _exigir(autorizacao)
    if os.environ.get(AMBIENTE_EVOLUIR, "0") != "1":
        raise EvolucaoError(
            f"Evolução desligada. Suba a API com {AMBIENTE_EVOLUIR}=1 para ensaiar e promover. "
            "Ensaio executa o código do patch: é a trava mais forte da camada."
        )


def capacidades() -> dict[str, Any]:
    """Estado das travas, sem revelar o token."""
    return {
        "token_configurado": bool(_token_host()),
        "evoluir": os.environ.get(AMBIENTE_EVOLUIR, "0") == "1",
        "cria_branch": False,
        "commita": False,
        "reinicia_processo": False,
        "diretorio": str(STORAGE),
    }


def _auditar(evento: dict[str, Any]) -> None:
    try:
        AUDITORIA.parent.mkdir(parents=True, exist_ok=True)
        linha = {"ts": datetime.now(timezone.utc).isoformat(), **evento}
        with open(AUDITORIA, "a", encoding="utf-8") as saida:
            saida.write(json.dumps(linha, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _rodar(comando: list[str], *, cwd: Path | None = None, timeout: int = 60) -> tuple[int, str, str]:
    """Comando fixo do código, nunca texto do usuário, sempre com shell=False."""
    try:
        concluido = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            check=False,
            cwd=str(cwd) if cwd else None,
        )
        return concluido.returncode, concluido.stdout[-200_000:], concluido.stderr[-40_000:]
    except FileNotFoundError:
        return 127, "", f"comando não encontrado: {comando[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"tempo esgotado em {timeout}s"
    except OSError as exc:
        return 126, "", f"falha ao executar: {type(exc).__name__}"


# ---------------------------------------------------------------------------
# Parser de diff unificado
# ---------------------------------------------------------------------------


class Hunk:
    def __init__(self, velho_inicio: int, velho_qtd: int, novo_inicio: int, novo_qtd: int, linhas: list[str]):
        self.velho_inicio = velho_inicio
        self.velho_qtd = velho_qtd
        self.novo_inicio = novo_inicio
        self.novo_qtd = novo_qtd
        self.linhas = linhas

    @property
    def velhas(self) -> list[str]:
        return [linha[1:] for linha in self.linhas if linha[:1] in (" ", "-")]

    @property
    def novas(self) -> list[str]:
        return [linha[1:] for linha in self.linhas if linha[:1] in (" ", "+")]

    @property
    def adicoes(self) -> int:
        return sum(1 for linha in self.linhas if linha.startswith("+"))

    @property
    def remocoes(self) -> int:
        return sum(1 for linha in self.linhas if linha.startswith("-"))


class ArquivoDiff:
    def __init__(self, caminho: str, novo: bool = False, removido: bool = False):
        self.caminho = caminho
        self.novo = novo
        self.removido = removido
        self.hunks: list[Hunk] = []

    @property
    def adicoes(self) -> int:
        return sum(hunk.adicoes for hunk in self.hunks)

    @property
    def remocoes(self) -> int:
        return sum(hunk.remocoes for hunk in self.hunks)

    def linhas_adicionadas(self) -> list[str]:
        return [linha[1:] for hunk in self.hunks for linha in hunk.linhas if linha.startswith("+")]

    def linhas_removidas(self) -> list[str]:
        return [linha[1:] for hunk in self.hunks for linha in hunk.linhas if linha.startswith("-")]


def _sem_prefixo(caminho: str) -> str:
    """Remove `a/`, `b/` ou `./` sem comer o ponto de `.env.example`."""
    limpo = caminho.strip().replace("\\", "/")
    if limpo.startswith("./"):
        limpo = limpo[2:]
    if limpo[:2] in {"a/", "b/"}:
        limpo = limpo[2:]
    return limpo


def ler_diff(texto: str) -> list[ArquivoDiff]:
    """Lê diff unificado com ou sem cabeçalho `diff --git`."""
    if not (texto or "").strip():
        raise EvolucaoError("Informe o diff unificado da mudança proposta.")
    if len(texto) > MAX_DIFF:
        raise EvolucaoError(f"Diff acima de {MAX_DIFF} caracteres; divida a proposta.")
    arquivos: list[ArquivoDiff] = []
    atual: ArquivoDiff | None = None
    hunk_atual: Hunk | None = None
    antigo_lido = False
    antigo_vazio = False
    for linha in texto.splitlines():
        achado_git = DIFF_GIT.match(linha)
        if achado_git:
            atual = _novo_arquivo(arquivos, achado_git.group(2))
            hunk_atual = None
            antigo_lido = False
            continue
        if linha.startswith("--- "):
            achado = ANTIGO.match(linha)
            if achado:
                caminho = achado.group(1)
                antigo_vazio = caminho == "/dev/null"
                if antigo_vazio:
                    atual = None
                    antigo_lido = True
                    continue
                if atual is None or _sem_prefixo(atual.caminho) != _sem_prefixo(caminho):
                    atual = _novo_arquivo(arquivos, caminho)
                atual.novo = False
                antigo_lido = True
            continue
        if linha.startswith("+++ ") and antigo_lido:
            achado = NOVO.match(linha)
            if achado:
                caminho = achado.group(1)
                if caminho == "/dev/null":
                    if atual is not None:
                        atual.removido = True
                else:
                    if atual is None:
                        atual = _novo_arquivo(arquivos, caminho)
                    atual.caminho = _sem_prefixo(caminho)
                    atual.novo = antigo_vazio
            antigo_lido = False
            antigo_vazio = False
            continue
        achado_hunk = HUNK.match(linha)
        if achado_hunk:
            if atual is None:
                raise EvolucaoError("Hunk sem arquivo: o diff precisa de `--- a/arquivo` antes de `@@`.")
            hunk_atual = Hunk(
                int(achado_hunk.group(1)),
                int(achado_hunk.group(2) or 1),
                int(achado_hunk.group(3)),
                int(achado_hunk.group(4) or 1),
                [],
            )
            atual.hunks.append(hunk_atual)
            if len(atual.hunks) > MAX_HUNKS:
                raise EvolucaoError(f"Mais de {MAX_HUNKS} hunks em {atual.caminho}.")
            continue
        if hunk_atual is not None:
            if linha.startswith(("+", "-", " ")):
                hunk_atual.linhas.append(linha)
            elif linha.startswith("\\"):
                continue
            elif linha == "":
                hunk_atual.linhas.append(" ")
    arquivos = [item for item in arquivos if item.hunks or item.removido]
    if not arquivos:
        raise EvolucaoError("Nenhum hunk encontrado: confira se o texto é um diff unificado.")
    if len(arquivos) > MAX_ARQUIVOS:
        raise EvolucaoError(f"Patch toca {len(arquivos)} arquivos; o teto é {MAX_ARQUIVOS}.")
    for item in arquivos:
        item.caminho = _limpar_caminho(item.caminho, item.novo)
    return arquivos


def _novo_arquivo(arquivos: list[ArquivoDiff], caminho: str) -> ArquivoDiff:
    limpo = _sem_prefixo(caminho)
    for item in arquivos:
        if item.caminho == limpo:
            return item
    criado = ArquivoDiff(limpo)
    arquivos.append(criado)
    return criado


def _limpar_caminho(caminho: str, novo: bool) -> str:
    limpo = _sem_prefixo(caminho)
    if ".." in Path(limpo).parts:
        raise EvolucaoError(f"Caminho com `..` recusado: {caminho}.")
    if limpo.startswith("/"):
        raise EvolucaoError(f"Caminho absoluto recusado: {caminho}.")
    for proibido in PROIBIDOS:
        if limpo.startswith(proibido) or f"/{proibido}" in limpo:
            raise EvolucaoError(f"Patch não pode tocar `{proibido}`.")
    if Path(limpo).name in PROIBIDOS_ARQUIVO or limpo.endswith(PROIBIDOS_ARQUIVO):
        raise EvolucaoError(f"Arquivo de credencial recusado: {limpo}.")
    if not (limpo in ARQUIVOS_RAIZ or limpo.startswith(RAIZES_PERMITIDAS)):
        raise EvolucaoError(
            f"Arquivo fora das raízes permitidas: {limpo}. Use {', '.join(RAIZES_PERMITIDAS)} ou um arquivo de raiz conhecido."
        )
    sufixo = Path(limpo).suffix.lower()
    if sufixo and sufixo not in EXTENSOES:
        raise EvolucaoError(f"Extensão não permitida em patch: {sufixo or limpo}.")
    if novo is False and not (PROJETO / limpo).exists():
        raise EvolucaoError(f"Arquivo não existe no projeto: {limpo}.")
    return limpo


def _aplicar_texto(texto: str, hunks: list[Hunk], *, busca: int = 40) -> str:
    """Aplica hunks em texto. Recusa quando o contexto não casa."""
    if "\x00" in texto:
        raise EvolucaoError("Arquivo binário: patch só vale para texto.")
    linhas = texto.splitlines()
    termina = texto.endswith("\n")
    for indice, hunk in enumerate(hunks, start=1):
        velhas = hunk.velhas
        novas = hunk.novas
        if not velhas:
            posicao = max(0, min(hunk.velho_inicio, len(linhas)))
            linhas[posicao:posicao] = novas
            continue
        esperado = max(0, hunk.velho_inicio - 1)
        achado = -1
        for deslocamento in range(0, busca + 1):
            for candidato in (esperado - deslocamento, esperado + deslocamento):
                if candidato < 0 or candidato + len(velhas) > len(linhas):
                    continue
                if linhas[candidato : candidato + len(velhas)] == velhas:
                    achado = candidato
                    break
            if achado >= 0:
                break
        if achado < 0:
            primeira = velhas[0].strip()[:60] if velhas else ""
            raise EvolucaoError(
                f"Hunk {indice} não aplica: contexto não encontrado perto da linha {hunk.velho_inicio} (`{primeira}`)."
            )
        linhas[achado : achado + len(velhas)] = novas
    return "\n".join(linhas) + ("\n" if termina else "")


def _resultado_do_patch(arquivo: ArquivoDiff) -> str | None:
    """Conteúdo final do arquivo, ou None quando o patch o remove."""
    if arquivo.removido:
        return None
    alvo = PROJETO / arquivo.caminho
    if arquivo.novo and not alvo.exists():
        return _aplicar_texto("", arquivo.hunks)
    if not alvo.exists():
        raise EvolucaoError(f"Arquivo não existe: {arquivo.caminho}.")
    return _aplicar_texto(alvo.read_text(encoding="utf-8"), arquivo.hunks)


# ---------------------------------------------------------------------------
# 1. Mapa do código
# ---------------------------------------------------------------------------


def _linhas(caminho: Path) -> int:
    try:
        return sum(1 for _ in caminho.open("r", encoding="utf-8", errors="replace"))
    except OSError:
        return 0


def _defs(caminho: Path) -> tuple[list[str], int]:
    funcoes: list[str] = []
    classes = 0
    try:
        texto = caminho.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return funcoes, classes
    for linha in texto.splitlines():
        if linha.startswith("def ") and not linha.startswith("def _"):
            funcoes.append(linha[4 : linha.find("(")].strip())
        elif linha.startswith("class "):
            classes += 1
    return funcoes, classes


def mapa(*, area: str = "tudo", modo: str = "full", autorizacao: str = "") -> dict[str, Any]:
    """Inventaria módulos, testes e páginas, com tamanho e superfície pública."""
    modo = _modo(modo)
    _exigir(autorizacao)
    area = (area or "tudo").strip().lower()
    if area not in {"tudo", "server", "testes", "web", "docs"}:
        raise EvolucaoError("Área inválida: use tudo, server, testes, web ou docs.")
    rows: list[dict[str, Any]] = []
    grupos: dict[str, list[Path]] = {"server": [], "testes": [], "web": [], "docs": []}
    if area in {"tudo", "server"}:
        grupos["server"] = sorted((PROJETO / "server").glob("*.py"))
    if area in {"tudo", "testes"}:
        grupos["testes"] = sorted((PROJETO / "server" / "tests").glob("test_*.py"))
    if area in {"tudo", "web"}:
        grupos["web"] = sorted((PROJETO / "src" / "pages").glob("*.tsx")) + sorted((PROJETO / "src").glob("*.css"))
    if area in {"tudo", "docs"}:
        grupos["docs"] = sorted((PROJETO / "docs").glob("*.md"))
    total_linhas = 0
    for grupo, arquivos in grupos.items():
        for arquivo in arquivos:
            linhas = _linhas(arquivo)
            total_linhas += linhas
            funcoes, classes = _defs(arquivo) if arquivo.suffix == ".py" else ([], 0)
            rows.append(
                {
                    "arquivo": arquivo.relative_to(PROJETO).as_posix(),
                    "grupo": grupo,
                    "linhas": linhas,
                    "bytes": arquivo.stat().st_size if arquivo.exists() else 0,
                    "publicas": len(funcoes),
                    "classes": classes,
                }
            )
    rows.sort(key=lambda item: item["linhas"], reverse=True)
    findings: list[dict[str, Any]] = []
    gigantes = [item for item in rows if item["linhas"] > 2_000]
    if gigantes:
        findings.append(
            finding(
                "should",
                "tamanho",
                "Módulo acima de 2.000 linhas",
                gigantes[0]["arquivo"],
                f"{len(gigantes)} arquivo(s) passam de 2.000 linhas; o maior tem {gigantes[0]['linhas']}.",
                "Arquivo grande esconde acoplamento e encarece qualquer patch: cada hunk concorre com mais contexto.",
                "Divida por responsabilidade antes de propor mudança estrutural nele.",
                "O patch aplica hoje e conflita com o próximo.",
            )
        )
    modulos = {Path(item["arquivo"]).stem for item in rows if item["grupo"] == "server"}
    testados = {Path(item["arquivo"]).stem.replace("test_", "", 1) for item in rows if item["grupo"] == "testes"}
    sem_teste = sorted(modulos - testados - {"__init__"})
    if sem_teste:
        findings.append(
            finding(
                "nice",
                "cobertura",
                "Módulo sem teste de mesmo nome",
                ", ".join(sem_teste[:5]),
                f"{len(sem_teste)} módulo(s) sem `test_<nome>.py`.",
                "Sem teste dedicado a mudança nesse módulo só é pega por teste de outro.",
                "Crie o teste antes de propor o patch: é ele que vai reprovar a regressão.",
                "A promoção pode passar sem provar nada sobre o arquivo.",
            )
        )
    findings, counts, verdict, questions = finalize(findings, modo, [
        "A mudança é local a um módulo ou atravessa a arquitetura?",
        "Existe teste que reprova se essa mudança quebrar?",
    ])
    return common(
        analysis="mapa",
        mode=modo,
        title="Mapa do projeto",
        summary=[
            f"{len(rows)} arquivo(s), {total_linhas} linhas no total.",
            f"{sum(1 for i in rows if i['grupo'] == 'server')} módulos Python, "
            f"{sum(1 for i in rows if i['grupo'] == 'testes')} arquivos de teste, "
            f"{sum(1 for i in rows if i['grupo'] == 'web')} de interface.",
        ],
        findings=findings,
        counts=counts,
        verdict=verdict,
        questions=questions,
        rows=rows[:MAX_ROWS],
        metrics={
            "arquivos": len(rows),
            "linhas": total_linhas,
            "modulos": len(modulos),
            "testes": sum(1 for i in rows if i["grupo"] == "testes"),
            "maior": rows[0]["linhas"] if rows else 0,
            "semTeste": len(sem_teste),
        },
        limitations=[
            "Conta linhas, não complexidade: um arquivo curto pode ser mais difícil que um longo.",
            "Não executa import nem resolve grafo de dependência entre módulos.",
            "Páginas e CSS entram pelo tamanho, sem análise de componente.",
        ],
    )


# ---------------------------------------------------------------------------
# 2. Proposta: o diff aplica?
# ---------------------------------------------------------------------------


def _validar_arquivos(arquivos: list[ArquivoDiff]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for item in arquivos:
        try:
            final = _resultado_do_patch(item)
        except EvolucaoError as exc:
            rows.append(
                {
                    "arquivo": item.caminho,
                    "estado": "não aplica",
                    "adicoes": item.adicoes,
                    "remocoes": item.remocoes,
                    "hunks": len(item.hunks),
                    "motivo": str(exc)[:160],
                }
            )
            findings.append(
                finding(
                    "must",
                    "aplicação",
                    "Hunk não casa com o arquivo atual",
                    item.caminho,
                    str(exc)[:300],
                    "O diff foi escrito sobre outra versão do arquivo: aplicar assim corromperia o conteúdo.",
                    "Regere o diff a partir do conteúdo atual do repositório.",
                    "A promoção escreveria um arquivo que não compila.",
                )
            )
            continue
        estado = "remove" if final is None else ("cria" if item.novo else "altera")
        linhas_finais = len(final.splitlines()) if final is not None else 0
        rows.append(
            {
                "arquivo": item.caminho,
                "estado": estado,
                "adicoes": item.adicoes,
                "remocoes": item.remocoes,
                "hunks": len(item.hunks),
                "linhasFinais": linhas_finais,
                "motivo": "",
            }
        )
        if final is not None and final.strip() == "" and item.hunks:
            findings.append(
                finding(
                    "must",
                    "aplicação",
                    "Patch esvazia o arquivo",
                    item.caminho,
                    "O resultado do patch é um arquivo vazio.",
                    "Esvaziar módulo em uso quebra o import de todo mundo que depende dele.",
                    "Confira se a remoção era intencional e remova as referências antes.",
                    "A API sobe sem o módulo e falha no primeiro uso.",
                )
            )
    return rows, findings


def proposta(*, diff: str, modo: str = "full", autorizacao: str = "") -> dict[str, Any]:
    """Lê o diff, lista o que muda e prova se cada hunk aplica no arquivo atual."""
    modo = _modo(modo)
    _exigir(autorizacao)
    arquivos = ler_diff(diff)
    rows, findings = _validar_arquivos(arquivos)
    nao_aplicam = [linha for linha in rows if linha["estado"] == "não aplica"]
    adicoes = sum(linha["adicoes"] for linha in rows)
    remocoes = sum(linha["remocoes"] for linha in rows)
    if not nao_aplicam:
        findings.append(
            finding(
                "nice",
                "aplicação",
                "Todos os hunks casam",
                f"{len(arquivos)} arquivo(s)",
                f"{sum(len(i.hunks) for i in arquivos)} hunk(s) encontram o contexto esperado.",
                "Aplicar é pré-requisito, não aprovação: um patch pode aplicar perfeitamente e quebrar tudo.",
                "Siga para risco, guardas e ensaio.",
                "Você confunde 'aplica' com 'está certo'.",
            )
        )
    testes = [linha for linha in rows if linha["arquivo"].startswith("server/tests/")]
    if testes and remocoes > adicoes:
        findings.append(
            finding(
                "must",
                "testes",
                "Patch reduz a suíte",
                testes[0]["arquivo"],
                f"{remocoes} linha(s) removidas contra {adicoes} adicionadas, com teste entre os arquivos.",
                "Remover teste para passar é o caminho mais rápido para degradar sem perceber.",
                "Reponha o teste removido ou explique por escrito por que ele não vale mais.",
                "A suíte fica verde sem provar nada.",
            )
        )
    findings, counts, verdict, questions = finalize(findings, modo, [
        "O diff foi gerado a partir do commit atual?",
        "O arquivo final foi revisado linha a linha por você?",
    ])
    return common(
        analysis="proposta",
        mode=modo,
        title="Proposta de mudança",
        summary=[
            f"{len(arquivos)} arquivo(s): **+{adicoes} / -{remocoes}** linhas, {sum(len(i.hunks) for i in arquivos)} hunk(s).",
            "Aplica em todos os arquivos." if not nao_aplicam else f"{len(nao_aplicam)} arquivo(s) não aplicam.",
        ],
        findings=findings,
        counts=counts,
        verdict=verdict,
        questions=questions,
        rows=rows[:MAX_ROWS],
        metrics={
            "arquivos": len(arquivos),
            "adicoes": adicoes,
            "remocoes": remocoes,
            "hunks": sum(len(item.hunks) for item in arquivos),
            "aplicavel": not nao_aplicam,
            "naoAplicam": len(nao_aplicam),
        },
        limitations=[
            "A prova é textual: o hunk casa com o conteúdo atual, não que o resultado compile.",
            "Nenhum linter, type check ou teste roda aqui — isso é o ensaio.",
            "Diff binário e patch de rename não são suportados.",
        ],
    )


# ---------------------------------------------------------------------------
# 3. Risco
# ---------------------------------------------------------------------------


def _perigos(arquivos: list[ArquivoDiff]) -> list[dict[str, Any]]:
    achados: list[dict[str, Any]] = []
    for item in arquivos:
        for numero, linha in enumerate(item.linhas_adicionadas(), start=1):
            for padrao, grupo, titulo, motivo in PERIGOS:
                if re.search(padrao, linha):
                    achados.append(
                        {
                            "arquivo": item.caminho,
                            "grupo": grupo,
                            "titulo": titulo,
                            "linha": linha.strip()[:120],
                            "motivo": motivo,
                            "padrao": padrao,
                            "numero": numero,
                        }
                    )
    vistos: set[tuple[str, str]] = set()
    unicos: list[dict[str, Any]] = []
    for achado in achados:
        chave = (achado["arquivo"], achado["titulo"])
        if chave in vistos:
            continue
        vistos.add(chave)
        unicos.append(achado)
    return unicos


def _guardas_removidas(arquivos: list[ArquivoDiff]) -> list[dict[str, Any]]:
    removidas: list[dict[str, Any]] = []
    for item in arquivos:
        for linha in item.linhas_removidas():
            for marca, descricao in MARCAS_DE_GUARDA.items():
                if marca in linha:
                    removidas.append(
                        {"arquivo": item.caminho, "marca": marca, "descricao": descricao, "linha": linha.strip()[:120]}
                    )
    vistos: set[tuple[str, str]] = set()
    unicas: list[dict[str, Any]] = []
    for item in removidas:
        chave = (item["arquivo"], item["marca"])
        if chave in vistos:
            continue
        vistos.add(chave)
        unicas.append(item)
    return unicas


def _pontuar(arquivos: list[ArquivoDiff], perigos: list[dict[str, Any]], guardas: list[dict[str, Any]]) -> int:
    pontos = 0
    for achado in perigos:
        pontos += 30 if achado["grupo"] == "must" else 12
        if achado.get("padrao") in PADROES_CRITICOS:
            pontos += 20
    for _ in guardas:
        pontos += 25
    for item in arquivos:
        pontos += ARQUIVOS_CENTRAIS.get(item.caminho, 0)
    total_linhas = sum(item.adicoes + item.remocoes for item in arquivos)
    if total_linhas > 300:
        pontos += 15
    elif total_linhas > 100:
        pontos += 8
    if len(arquivos) > 5:
        pontos += 10
    if any(item.caminho.startswith("server/tests/") for item in arquivos):
        pontos -= 5
    return max(0, min(100, pontos))


def risco(*, diff: str, modo: str = "full", autorizacao: str = "") -> dict[str, Any]:
    """Classifica o patch por perigo, guardas removidas e superfície tocada."""
    modo = _modo(modo)
    _exigir(autorizacao)
    arquivos = ler_diff(diff)
    perigos = _perigos(arquivos)
    guardas = _guardas_removidas(arquivos)
    pontos = _pontuar(arquivos, perigos, guardas)
    nivel = "alto" if pontos >= 50 else ("médio" if pontos >= 20 else "baixo")
    findings: list[dict[str, Any]] = []
    for achado in perigos:
        findings.append(
            finding(
                achado["grupo"],
                "perigo",
                achado["titulo"],
                achado["arquivo"],
                f"Linha adicionada: `{achado['linha']}`.",
                achado["motivo"],
                "Reescreva sem o construto ou justifique por escrito no corpo da proposta.",
                "O código ganha um caminho de execução que os guardas não cobrem.",
            )
        )
    for achado in guardas:
        findings.append(
            finding(
                "must",
                "guarda",
                "Patch remove guarda do projeto",
                achado["arquivo"],
                f"Linha removida que implementa {achado['descricao']}: `{achado['linha']}`.",
                "Cada uma dessas linhas é o que separa leitura de efeito colateral.",
                "Reintroduza a guarda ou mude a proposta para não tocar nela.",
                "A camada perde a trava e passa a aceitar o que recusava.",
            )
        )
    centrais = [item.caminho for item in arquivos if item.caminho in ARQUIVOS_CENTRAIS]
    if len(centrais) > 1:
        findings.append(
            finding(
                "should",
                "superfície",
                "Patch toca mais de um arquivo central",
                ", ".join(centrais[:4]),
                f"{len(centrais)} arquivos que concentram travas entram no patch.",
                "Mudança simultânea em dois pontos de guarda é difícil de revisar e de reverter.",
                "Divida em dois patches, um por guarda.",
                "A revisão passa por cima de um dos pontos.",
            )
        )
    if nivel == "alto":
        findings.append(
            finding(
                "must",
                "risco",
                "Risco alto: revisão humana antes de qualquer ensaio",
                f"pontuação {pontos}",
                f"O patch soma {pontos} de 100 pontos de risco.",
                "Ensaio verde não cobre efeito fora do teste: rede, permissão e escrita em disco passam despercebidos.",
                "Reduza a superfície do patch e mova o que for perigoso para uma skill declarada.",
                "Você aprova às cegas uma mudança que o teste não julga.",
            )
        )
    findings, counts, verdict, questions = finalize(findings, modo, [
        "Alguma linha adicionada executa texto ou abre shell?",
        "Você entende o que cada guarda removida protegia?",
    ])
    rows = [
        {
            "arquivo": item.caminho,
            "central": item.caminho in ARQUIVOS_CENTRAIS,
            "adicoes": item.adicoes,
            "remocoes": item.remocoes,
            "peso": ARQUIVOS_CENTRAIS.get(item.caminho, 0),
        }
        for item in arquivos
    ]
    return common(
        analysis="risco",
        mode=modo,
        title="Risco da mudança",
        summary=[
            f"Risco **{nivel}** ({pontos}/100).",
            f"{len(perigos)} padrão(ões) de perigo, {len(guardas)} guarda(s) removida(s), {len(centrais)} arquivo(s) central(is).",
        ],
        findings=findings,
        counts=counts,
        verdict=verdict,
        questions=questions,
        rows=rows,
        metrics={
            "pontuacao": pontos,
            "nivel": nivel,
            "perigos": len(perigos),
            "guardas": len(guardas),
            "centrais": len(centrais),
        },
        limitations=[
            "É análise de padrão sobre as linhas adicionadas, não execução simbólica.",
            "Um perigo pode estar em linha adicionada e nunca ser chamado.",
            "Não avalia intenção: código limpo pode ser malicioso e vice-versa.",
        ],
    )


# ---------------------------------------------------------------------------
# 4. Guardas do projeto
# ---------------------------------------------------------------------------

REGRAS_GUARDA: tuple[tuple[str, str, str], ...] = (
    ("G1", "Toda skill de leitura continua devolvendo `executed: false`", "review.py e as camadas novas"),
    ("G2", "Nenhum comando novo fora da allowlist fechada, e nenhum binário de elevação", "sistema.py, elevacao.py"),
    ("G3", "`shell=False` preservado em toda chamada de processo", "sistema.py, evolucao.py"),
    ("G4", "Token de host continua exigido antes de qualquer leitura do host", "sistema.py, evolucao.py"),
    ("G5", "Nenhuma dependência nova sem entrada em requirements", "requirements.txt"),
    ("G6", "A contagem de skills no teste acompanha o registro", "test_*.py"),
    ("G7", "Nenhum arquivo de credencial ou runtime entra no patch", "*.env, storage/, .git/"),
    ("G8", "A suíte não pode encolher", "server/tests/"),
    ("G9", "Skill com efeito colateral declara `sideEffects` e `requiresConfirmation`", "skill_registry.py"),
    ("G10", "Nenhuma camada de leitura ganha rede sem variável de ambiente própria", "sistema.py"),
)


def guardas(*, diff: str, modo: str = "full", autorizacao: str = "") -> dict[str, Any]:
    """Confere as dez leis do projeto contra o patch proposto."""
    modo = _modo(modo)
    _exigir(autorizacao)
    arquivos = ler_diff(diff)
    adicionadas = [(item.caminho, linha) for item in arquivos for linha in item.linhas_adicionadas()]
    removidas = [(item.caminho, linha) for item in arquivos for linha in item.linhas_removidas()]
    resultados: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []

    def violar(codigo: str, regra: str, local: str, detalhe: str, correcao: str, se_ignorar: str, grupo: str = "must") -> None:
        resultados.append({"codigo": codigo, "regra": regra, "estado": "viola", "local": local, "detalhe": detalhe})
        findings.append(finding(grupo, "guarda", regra, local, detalhe, "A lei vale para toda camada desde a 0.19.0.", correcao, se_ignorar))

    def aprovar(codigo: str, regra: str) -> None:
        resultados.append({"codigo": codigo, "regra": regra, "estado": "preserva", "local": "—", "detalhe": ""})

    # G1 — executed:false removido
    if any('"executed": False' in linha or 'executed": False' in linha for _, linha in removidas):
        violar("G1", REGRAS_GUARDA[0][1], "review.py", "O patch remove a marca `executed: false` de uma resposta.", "Mantenha a marca e declare a exceção na camada que executa.", "Uma skill de leitura passa a parecer executora.")
    else:
        aprovar("G1", REGRAS_GUARDA[0][1])

    # G2 — allowlist
    suspeitos = [
        (c, l)
        for c, l in adicionadas
        if re.search(r"GERENCIADORES|DESINSTALADORES|ACOES\b|_comando_do_plano", l)
    ]
    novos_binarios = [
        (c, l)
        for c, l in adicionadas
        if re.search(r"\[\s*\"(sh|bash|cmd|powershell|curl|wget|sudo|doas|pkexec|runas)\"", l)
    ]
    if novos_binarios:
        violar("G2", REGRAS_GUARDA[1][1], novos_binarios[0][0], f"Binário novo na allowlist: `{novos_binarios[0][1].strip()[:80]}`.", "Binário de shell ou de elevação não entra na allowlist sem decisão explícita.", "A API vira executor genérico — ou executor como root.")
    elif suspeitos:
        resultados.append({"codigo": "G2", "regra": REGRAS_GUARDA[1][1], "estado": "revisar", "local": suspeitos[0][0], "detalhe": "O patch mexe na allowlist de instaladores."})
        findings.append(finding("should", "guarda", "Allowlist alterada", suspeitos[0][0], "O patch toca a tabela de comandos permitidos.", "Alterar allowlist muda o que a camada aceita executar.", "Explique no corpo da proposta qual entrada mudou e por quê.", "A lista cresce sem revisão."))
    else:
        aprovar("G2", REGRAS_GUARDA[1][1])

    # G3 — shell=False removido
    if any("shell=False" in linha for _, linha in removidas) and not any("shell=False" in linha for _, linha in adicionadas):
        violar("G3", REGRAS_GUARDA[2][1], "subprocess", "O patch remove `shell=False` sem repor.", "Mantenha `shell=False` em toda chamada.", "Argumento passa a ser interpretado pelo shell.")
    elif any(re.search(r"shell\s*=\s*True", linha) for _, linha in adicionadas):
        violar("G3", REGRAS_GUARDA[2][1], "subprocess", "O patch adiciona `shell=True`.", "Use lista de argumentos com `shell=False`.", "Injeção de comando fica possível.")
    else:
        aprovar("G3", REGRAS_GUARDA[2][1])

    # G4 — token
    if any("_exigir(" in linha or "compare_digest" in linha for _, linha in removidas) and not any("_exigir(" in linha for _, linha in adicionadas):
        violar("G4", REGRAS_GUARDA[3][1], "sistema.py", "O patch remove chamada de exigência de token.", "Toda leitura de host começa com `_exigir`.", "Endpoint lê a máquina sem prova de acesso.")
    else:
        aprovar("G4", REGRAS_GUARDA[3][1])

    # G5 — dependências
    requirements = [c for c, _ in adicionadas if c in {"requirements.txt", "requirements-dev.txt"}]
    imports = [(c, l) for c, l in adicionadas if re.match(r"\s*(import|from)\s+([a-z_]+)", l)]
    novos_imports = {re.match(r"\s*(?:import|from)\s+([a-z_]+)", l).group(1) for _, l in imports if re.match(r"\s*(?:import|from)\s+([a-z_]+)", l)}
    if novos_imports and not requirements:
        externos = sorted(novos_imports - set(sys.stdlib_module_names) - {"server"})
        if externos:
            violar("G5", REGRAS_GUARDA[4][1], externos[0], f"Import novo sem requirements: {', '.join(externos[:4])}.", "Acrescente a dependência em `requirements.txt` com faixa de versão.", "A instalação limpa falha no primeiro import.", grupo="should")
        else:
            aprovar("G5", REGRAS_GUARDA[4][1])
    else:
        aprovar("G5", REGRAS_GUARDA[4][1])

    # G6 — contagem de skills
    mexeu_registro = any(c == "server/skill_registry.py" for c, _ in adicionadas)
    mexeu_teste = any(c.startswith("server/tests/") and "== " in l for c, l in adicionadas)
    if mexeu_registro and not mexeu_teste:
        resultados.append({"codigo": "G6", "regra": REGRAS_GUARDA[5][1], "estado": "revisar", "local": "server/skill_registry.py", "detalhe": "Registro muda sem ajuste de contagem nos testes."})
        findings.append(finding("should", "guarda", "Registro muda sem contagem", "server/skill_registry.py", "Skill nova ou removida sem atualizar o total nos testes.", "Contagem divergente quebra a suíte na próxima execução.", "Atualize o total em todos os testes de registro.", "A suíte fica vermelha por motivo bobo."))
    else:
        aprovar("G6", REGRAS_GUARDA[5][1])

    # G7 — credencial
    proibidos = [c for c, _ in adicionadas if c.endswith((".env", ".pem", ".key")) or c.startswith(("storage/", ".git/"))]
    if proibidos:
        violar("G7", REGRAS_GUARDA[6][1], proibidos[0], "O patch toca arquivo de credencial ou de runtime.", "Remova esse arquivo da proposta.", "Segredo entra no histórico do Git.")
    else:
        aprovar("G7", REGRAS_GUARDA[6][1])

    # G8 — suíte encolhe
    remocoes_teste = sum(1 for c, _ in removidas if c.startswith("server/tests/"))
    adicoes_teste = sum(1 for c, _ in adicionadas if c.startswith("server/tests/"))
    if remocoes_teste > adicoes_teste + 5:
        violar("G8", REGRAS_GUARDA[7][1], "server/tests/", f"{remocoes_teste} linha(s) de teste removidas contra {adicoes_teste} adicionadas.", "Reponha os testes ou justifique cada remoção.", "A suíte perde poder de reprovar regressão.")
    else:
        aprovar("G8", REGRAS_GUARDA[7][1])

    # G9 — side effects
    efeito_novo = [l for c, l in adicionadas if c == "server/skill_registry.py" and "SkillDefinition(" in l]
    sem_declaracao = [l for l in efeito_novo if "side_effects=True" not in l and re.search(r"(write|create|baixar|executar|promover|reverter|merge|organize)", l)]
    if sem_declaracao:
        violar("G9", REGRAS_GUARDA[8][1], "skill_registry.py", "Skill com nome de efeito registrada sem `side_effects=True`.", "Declare `side_effects`, `dry_run_supported` e `requires_confirmation`.", "A interface mostra como leitura algo que escreve.", grupo="should")
    else:
        aprovar("G9", REGRAS_GUARDA[8][1])

    # G10 — rede sem trava
    rede = [(c, l) for c, l in adicionadas if re.search(r"urllib\.request|httpx\.|requests\.", l)]
    trava = any("JARVIS_HOST_REDE" in l or "_exigir_rede" in l for _, l in adicionadas)
    if rede and not trava and all("sistema.py" not in c for c, _ in rede):
        violar("G10", REGRAS_GUARDA[9][1], rede[0][0], "Camada nova acessa a rede sem variável de ambiente própria.", "Acrescente uma trava `JARVIS_HOST_*` e exija o token.", "Saída de rede fica sempre ligada.", grupo="should")
    else:
        aprovar("G10", REGRAS_GUARDA[9][1])

    violadas = [item for item in resultados if item["estado"] == "viola"]
    revisar = [item for item in resultados if item["estado"] == "revisar"]
    findings, counts, verdict, questions = finalize(findings, modo, [
        "Cada guarda violada tem justificativa escrita?",
        "Você aceita que o ensaio não cobre efeito fora do teste?",
    ])
    return common(
        analysis="guardas",
        mode=modo,
        title="Guardas do projeto",
        summary=[
            f"{len(REGRAS_GUARDA) - len(violadas)} de {len(REGRAS_GUARDA)} guardas preservadas, {len(violadas)} violada(s), {len(revisar)} para revisar.",
            "Nenhuma violação." if not violadas else "Resolva as violações antes do ensaio.",
        ],
        findings=findings,
        counts=counts,
        verdict=verdict,
        questions=questions,
        rows=resultados,
        metrics={
            "regras": len(REGRAS_GUARDA),
            "preservadas": len(REGRAS_GUARDA) - len(violadas) - len(revisar),
            "violadas": len(violadas),
            "revisar": len(revisar),
        },
        limitations=[
            "As dez regras são heurísticas sobre linhas do diff, não prova formal.",
            "Uma regra pode passar porque o padrão mudou de nome.",
            "Nenhuma regra julga intenção: só o que está escrito no patch.",
        ],
    )


# ---------------------------------------------------------------------------
# 5. Ensaio em cópia isolada
# ---------------------------------------------------------------------------


def _copia_segura(origem: Path, destino: Path) -> None:
    shutil.copytree(
        origem,
        destino,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "node_modules", ".venv"),
        dirs_exist_ok=True,
    )


def _preparar_ensaio(arquivos: list[ArquivoDiff], destino: Path) -> list[str]:
    """Copia o projeto para o ensaio e aplica o patch só na cópia."""
    destino.mkdir(parents=True, exist_ok=True)
    _copia_segura(PROJETO / "server", destino / "server")
    for nome in ("pytest.ini", "requirements.txt", "requirements-dev.txt"):
        origem = PROJETO / nome
        if origem.exists():
            shutil.copy2(origem, destino / nome)
    (destino / "storage").mkdir(exist_ok=True)
    tocados: list[str] = []
    for item in arquivos:
        final = _resultado_do_patch(item)
        alvo = destino / item.caminho
        if final is None:
            alvo.unlink(missing_ok=True)
            tocados.append(f"-{item.caminho}")
            continue
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(final, encoding="utf-8")
        tocados.append(item.caminho)
    return tocados


ALVO_TESTE = re.compile(r"^[A-Za-z0-9_./:=*-]+$")


def _argumentos_de_teste(testes: str) -> list[str]:
    """Divide o campo de testes em argv validado: caminho ou flag curta, nada mais."""
    bruto = (testes or "").strip() or "server/tests"
    if len(bruto) > 300:
        raise EvolucaoError("Campo de testes longo demais.")
    partes = bruto.split()
    if len(partes) > 12:
        raise EvolucaoError("No máximo 12 argumentos de teste.")
    for parte in partes:
        if not ALVO_TESTE.match(parte):
            raise EvolucaoError(f"Argumento de teste inválido: `{parte}`. Use caminho, `-k`, `-x` ou `-q`.")
        if ".." in parte:
            raise EvolucaoError(f"Caminho com `..` recusado em testes: `{parte}`.")
    return partes


def _resumo_pytest(saida: str) -> dict[str, Any]:
    numeros = re.findall(r"(\d+) (passed|failed|error|errors|skipped)", saida)
    contagem = {nome: int(valor) for valor, nome in numeros}
    linha = ""
    for candidata in reversed(saida.splitlines()):
        if "passed" in candidata or "failed" in candidata or "error" in candidata:
            linha = candidata.strip()[:200]
            break
    return {
        "passed": contagem.get("passed", 0),
        "failed": contagem.get("failed", 0) + contagem.get("error", 0) + contagem.get("errors", 0),
        "skipped": contagem.get("skipped", 0),
        "resumo": linha,
    }


def ensaiar(
    *,
    diff: str,
    testes: str = "",
    timeout: int = 600,
    modo: str = "full",
    autorizacao: str = "",
) -> dict[str, Any]:
    """Aplica o patch numa cópia isolada e roda a suíte. Nunca toca o código vivo."""
    modo = _modo(modo)
    _exigir_evoluir(autorizacao)
    inicio = time.time()
    arquivos = ler_diff(diff)
    rows, findings = _validar_arquivos(arquivos)
    nao_aplicam = [linha for linha in rows if linha["estado"] == "não aplica"]
    if nao_aplicam:
        raise EvolucaoError(
            "O patch não aplica integralmente; corrija antes de ensaiar. "
            f"Primeiro problema em {nao_aplicam[0]['arquivo']}."
        )
    identificador = secrets.token_hex(5)
    destino = ENSAIOS / identificador
    antes = {item.caminho: _sha(PROJETO / item.caminho) for item in arquivos if (PROJETO / item.caminho).exists()}
    tocados = _preparar_ensaio(arquivos, destino)
    (destino / "_proposta.diff").write_text(diff, encoding="utf-8")
    # pytest roda na cópia: é o código do patch sendo executado, de propósito.
    alvos = _argumentos_de_teste(testes)
    # Um único `-q`: `-qq` apaga a linha de resumo e o ensaio fica sem número.
    alvos = [parte for parte in alvos if parte not in {"-q", "--quiet", "-qq"}]
    # `-o addopts=` neutraliza o `-q` do pytest.ini: sem isso o duplo quiet
    # apaga a linha de resumo e o ensaio fica sem contagem.
    comando = [sys.executable, "-m", "pytest", *alvos, "-o", "addopts=", "-q", "--no-header", "-p", "no:cacheprovider"]
    timeout = max(30, min(int(timeout), 1_800))
    codigo, saida, erro = _rodar(comando, cwd=destino, timeout=timeout)
    duracao = round(time.time() - inicio, 1)
    resumo = _resumo_pytest(saida)
    if codigo == 124:
        resumo = {"passed": 0, "failed": 0, "skipped": 0, "resumo": f"tempo esgotado em {timeout}s"}
    aprovado = codigo == 0 and resumo["failed"] == 0 and resumo["passed"] > 0
    if codigo == 5 and resumo["passed"] == 0:
        findings.append(
            finding(
                "must",
                "ensaio",
                "Nenhum teste coletado",
                " ".join(alvos),
                "pytest saiu com código 5: nenhum teste corresponde ao caminho.",
                "Suíte vazia aprova qualquer coisa.",
                "Confira o caminho do arquivo de teste.",
                "A promoção ficaria liberada sem prova.",
            )
        )
    if codigo == 4:
        findings.append(
            finding(
                "must",
                "ensaio",
                "pytest recusou os argumentos",
                " ".join(alvos),
                f"Código 4 (erro de uso): {(erro or saida)[-300:] or 'sem mensagem'}.",
                "O caminho de teste não existe ou o argumento não é aceito: nada foi provado.",
                "Confira o caminho e use só caminho, `-k`, `-x` ou `-q`.",
                "Você recebe 'reprovado' quando o problema era o comando.",
            )
        )
    if codigo == 0 and resumo["passed"] == 0:
        findings.append(
            finding(
                "must",
                "ensaio",
                "Nenhum teste executado",
                testes or "server/tests",
                "O pytest saiu com código 0 sem ter rodado teste nenhum.",
                "Suíte vazia aprova qualquer coisa: é o pior resultado possível.",
                "Confira o caminho dos testes e rode de novo.",
                "Você promove código nunca testado.",
            )
        )
    if resumo["failed"]:
        findings.append(
            finding(
                "must",
                "ensaio",
                "Suíte reprovou com o patch aplicado",
                f"ensaio {identificador}",
                f"{resumo['failed']} falha(s) em {resumo['passed'] + resumo['failed']} teste(s).",
                "Mudança que quebra teste não é melhoria: é regressão com aparência de avanço.",
                "Corrija o patch e ensaie de novo; a promoção fica bloqueada.",
                "O projeto piora de forma rastreável.",
            )
        )
    elif aprovado:
        findings.append(
            finding(
                "nice",
                "ensaio",
                "Suíte verde na cópia",
                f"ensaio {identificador}",
                resumo["resumo"] or "pytest saiu com 0.",
                "Verde prova que os testes existentes continuam passando, não que a mudança é boa.",
                "Revise o diff e promova com consciência do escopo.",
                "Você trata verde como aprovação de mérito.",
            )
        )
    if codigo == 124:
        findings.append(
            finding(
                "must",
                "ensaio",
                "Ensaio estourou o tempo",
                f"{timeout}s",
                "A suíte não terminou dentro do limite.",
                "Sem resultado completo, não há prova.",
                "Reduza o escopo dos testes ou aumente o timeout.",
                "A promoção fica bloqueada.",
            )
        )
    token = secrets.token_hex(4)
    expira = time.time() + CONFIRMACAO_TTL
    _CONFIRMACAO[token] = {
        "acao": "promover",
        "ensaio": identificador,
        "diff": diff,
        "antes": antes,
        "expira": expira,
        "aprovado": aprovado,
    }
    manifesto = {
        "id": identificador,
        "criado": datetime.now(timezone.utc).isoformat(),
        "arquivos": tocados,
        "shas": antes,
        "codigo": codigo,
        "duracao": duracao,
        "aprovado": aprovado,
        **resumo,
    }
    try:
        (destino / "_manifesto.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
        AUDITORIA.parent.mkdir(parents=True, exist_ok=True)
        with open(AUDITORIA, "a", encoding="utf-8") as saida_auditoria:
            saida_auditoria.write(json.dumps({"ts": manifesto["criado"], "acao": "ensaiar", "id": identificador, "aprovado": aprovado}, ensure_ascii=False) + "\n")
    except OSError:
        pass
    findings, counts, verdict, questions = finalize(findings, modo, [
        "Você leu o diff inteiro antes de promover?",
        "Algum teste novo deveria nascer junto com a mudança?",
    ])
    rows_teste = [
        {"arquivo": item.caminho, "estado": "aplicado na cópia", "adicoes": item.adicoes, "remocoes": item.remocoes}
        for item in arquivos
    ]
    resultado = common(
        analysis="ensaiar",
        mode=modo,
        title="Ensaio em cópia isolada",
        summary=[
            f"Ensaio **{identificador}**: {resumo['passed']} passaram, {resumo['failed']} falharam, {resumo['skipped']} pulados.",
            f"Cópia em `{_relativo(destino)}` — o código vivo não foi tocado.",
            "**Aprovado para promoção.**" if aprovado else "**Não aprovado**: a promoção vai recusar.",
        ],
        findings=findings,
        counts=counts,
        verdict=verdict,
        questions=questions,
        rows=rows_teste,
        metrics={
            "ensaio": identificador,
            "passed": resumo["passed"],
            "failed": resumo["failed"],
            "skipped": resumo["skipped"],
            "codigo": codigo,
            "duracao": duracao,
            "aprovado": aprovado,
        },
        limitations=[
            "O ensaio roda o código do patch: um teste malicioso executa com o usuário da API.",
            "Só pytest: interface (vitest) e build do front não são ensaiados.",
            "Verde significa que os testes existentes passam, não que a mudança é correta.",
            "A cópia ocupa disco em storage/evolucao/ensaios até você apagar.",
        ],
        extra_sections=["", "## Saída do pytest", "", "```text", (saida or erro)[-6_000:], "```"],
    )
    resultado["executed"] = True
    resultado["readOnly"] = False
    resultado["ensaio"] = identificador
    resultado["aprovado"] = aprovado
    resultado["confirmacao"] = token if aprovado else ""
    return resultado


def _relativo(caminho: Path) -> str:
    """Caminho relativo ao projeto quando possível; absoluto quando o teste aponta para fora."""
    try:
        return caminho.relative_to(PROJETO).as_posix()
    except ValueError:
        return str(caminho)


def _sha(caminho: Path) -> str:
    try:
        return hashlib.sha256(caminho.read_bytes()).hexdigest()
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# 6. Promoção
# ---------------------------------------------------------------------------


def _git_limpo(caminho: str) -> tuple[bool, str]:
    codigo, saida, erro = _rodar(["git", "status", "--porcelain", "--", caminho], timeout=20)
    if codigo == 127:
        return True, "git indisponível: checagem de árvore limpa pulada."
    if codigo != 0:
        return True, f"git falhou ({codigo}): checagem pulada."
    return not saida.strip(), saida.strip()[:200]


def promover(*, confirmacao: str, modo: str = "full", autorizacao: str = "") -> dict[str, Any]:
    """Aplica no código vivo o patch de um ensaio aprovado, com backup e token."""
    modo = _modo(modo)
    _exigir_evoluir(autorizacao)
    token = (confirmacao or "").strip()
    if not token or token not in _CONFIRMACAO:
        raise EvolucaoError("Confirmação ausente ou desconhecida. Gere um ensaio novo.")
    registro = _CONFIRMACAO.pop(token)
    if registro["expira"] < time.time():
        raise EvolucaoError("Confirmação expirada. Gere um ensaio novo.")
    if not registro.get("aprovado"):
        raise EvolucaoError("O ensaio não foi aprovado: a suíte reprovou ou não rodou teste. Promoção recusada.")
    identificador = registro["ensaio"]
    arquivos = ler_diff(registro["diff"])
    # O arquivo vivo precisa ser idêntico ao ensaiado e estar sem alteração pendente.
    for caminho, sha_ensaio in registro["antes"].items():
        atual = _sha(PROJETO / caminho)
        if atual != sha_ensaio:
            raise EvolucaoError(
                f"`{caminho}` mudou depois do ensaio. Gere a proposta e o ensaio de novo."
            )
        limpo, detalhe = _git_limpo(caminho)
        if not limpo:
            raise EvolucaoError(
                f"`{caminho}` tem alteração não commitada nesta árvore ({detalhe}). "
                "Commite ou descarte antes de promover: a promoção não pisa em trabalho em andamento."
            )
    destino_backup = BACKUPS / identificador
    destino_backup.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    escritos: list[str] = []
    for item in arquivos:
        origem = PROJETO / item.caminho
        if origem.exists():
            alvo_backup = destino_backup / item.caminho
            alvo_backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origem, alvo_backup)
        final = _resultado_do_patch(item)
        if final is None:
            origem.unlink(missing_ok=True)
            rows.append({"arquivo": item.caminho, "acao": "removido", "bytes": 0})
            escritos.append(item.caminho)
            continue
        origem.parent.mkdir(parents=True, exist_ok=True)
        origem.write_text(final, encoding="utf-8")
        rows.append({"arquivo": item.caminho, "acao": "escrito", "bytes": len(final.encode("utf-8"))})
        escritos.append(item.caminho)
    _auditar({"acao": "promover", "ensaio": identificador, "arquivos": escritos})
    findings: list[dict[str, Any]] = [
        finding(
            "should",
            "reinício",
            "A API continua rodando o código antigo",
            "processo",
            "Os arquivos em disco já são os novos, mas o processo Python não recarrega módulo sozinho.",
            "Promover sem reiniciar dá a impressão de que a mudança não funcionou.",
            "Reinicie a API (`npm run dev` recarrega, `uvicorn` sem `--reload` não) e rode a suíte de novo.",
            "Você depura um bug que já foi corrigido no disco.",
        ),
        finding(
            "nice",
            "reversão",
            "Cópia de segurança pronta",
            f"storage/evolucao/backups/{identificador}",
            f"{len(arquivos)} arquivo(s) copiados antes da escrita.",
            "Sem backup, reverter exige git e perde alteração não commitada.",
            f"Use `evoluir.reverter` com o ensaio `{identificador}` para voltar.",
            "Você depende do git para desfazer.",
        ),
    ]
    findings, counts, verdict, questions = finalize(findings, modo, [
        "Você vai reiniciar a API agora?",
        "Vai commitar a mudança ou reverter?",
    ])
    resultado = common(
        analysis="promover",
        mode=modo,
        title="Promoção para o código vivo",
        summary=[
            f"Patch do ensaio **{identificador}** aplicado em {len(escritos)} arquivo(s).",
            "Nenhum commit, nenhuma branch: a árvore viva está modificada e o git vai mostrar o diff.",
            "**Reinicie a API** para o código novo entrar em vigor.",
        ],
        findings=findings,
        counts=counts,
        verdict=verdict,
        questions=questions,
        rows=rows,
        metrics={
            "ensaio": identificador,
            "arquivos": len(escritos),
            "reinicioPendente": True,
            "backup": _relativo(destino_backup),
        },
        limitations=[
            "Não cria branch nem commita: o diff fica na árvore para você revisar.",
            "Não reinicia o processo: Python não recarrega módulo em execução.",
            "Se a escrita falhar no meio, use `evoluir.reverter` para restaurar o backup.",
            "Front-end promovido só aparece depois do rebuild.",
        ],
    )
    resultado["executed"] = True
    resultado["readOnly"] = False
    resultado["ensaio"] = identificador
    resultado["reinicio_pendente"] = True
    resultado["backup"] = _relativo(destino_backup)
    return resultado


# ---------------------------------------------------------------------------
# 7. Reversão
# ---------------------------------------------------------------------------


def reverter(*, ensaio: str, modo: str = "full", autorizacao: str = "") -> dict[str, Any]:
    """Restaura os arquivos a partir do backup de uma promoção."""
    modo = _modo(modo)
    _exigir_evoluir(autorizacao)
    identificador = (ensaio or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{4,32}", identificador):
        raise EvolucaoError(
            "Identificador inválido: use os 4 a 32 caracteres hexadecimais devolvidos por `evoluir.promover`."
        )
    destino = BACKUPS / identificador
    if not destino.exists() or not destino.is_dir():
        raise EvolucaoError(f"Não existe backup para o ensaio `{identificador}`.")
    restaurados: list[dict[str, Any]] = []
    for arquivo in sorted(destino.rglob("*")):
        if not arquivo.is_file():
            continue
        relativo = arquivo.relative_to(destino).as_posix()
        alvo = PROJETO / relativo
        alvo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(arquivo, alvo)
        restaurados.append({"arquivo": relativo, "acao": "restaurado", "bytes": arquivo.stat().st_size})
    if not restaurados:
        raise EvolucaoError(f"O backup de `{identificador}` está vazio.")
    _auditar({"acao": "reverter", "ensaio": identificador, "arquivos": [i["arquivo"] for i in restaurados]})
    findings, counts, verdict, questions = finalize(
        [
            finding(
                "should",
                "reinício",
                "Reinicie a API para voltar ao código anterior",
                "processo",
                "Os arquivos restaurados só valem depois de reiniciar o processo.",
                "Módulo já importado continua em memória.",
                "Reinicie a API e rode a suíte para confirmar.",
                "Você acha que reverteu e o processo segue com o código novo.",
            )
        ],
        modo,
        ["O comportamento voltou ao anterior?", "Você quer manter o ensaio arquivado para reaplicar?"],
    )
    resultado = common(
        analysis="reverter",
        mode=modo,
        title="Reversão de promoção",
        summary=[
            f"{len(restaurados)} arquivo(s) restaurados do backup `{identificador}`.",
            "Reinicie a API: módulo já carregado não volta sozinho.",
        ],
        findings=findings,
        counts=counts,
        verdict=verdict,
        questions=questions,
        rows=restaurados,
        metrics={"ensaio": identificador, "arquivos": len(restaurados), "reinicioPendente": True},
        limitations=[
            "Só restaura o que a promoção tocou; arquivo criado fora do patch permanece.",
            "Não desfaz commit já feito.",
            "Não reinicia o processo.",
        ],
    )
    resultado["executed"] = True
    resultado["readOnly"] = False
    resultado["reinicio_pendente"] = True
    return resultado


# ---------------------------------------------------------------------------
# 8. Catálogo
# ---------------------------------------------------------------------------


def catalogo() -> dict[str, Any]:
    """Publica o fluxo, as travas e o que a camada recusa fazer."""
    return {
        "executed": False,
        "readOnly": True,
        "versao": VERSAO,
        "principio": (
            "Código que se altera precisa provar antes de escrever: aplica, respeita as guardas e passa na suíte "
            "numa cópia — só então toca a árvore viva, com backup e token."
        ),
        "fluxo": [
            {"passo": 1, "skill": "evoluir.mapa", "prova": "onde a mudança cai"},
            {"passo": 2, "skill": "evoluir.proposta", "prova": "o diff aplica no arquivo atual"},
            {"passo": 3, "skill": "evoluir.risco", "prova": "o patch não abre shell nem embute segredo"},
            {"passo": 4, "skill": "evoluir.guardas", "prova": "as dez leis do projeto continuam de pé"},
            {"passo": 5, "skill": "evoluir.ensaiar", "prova": "a suíte passa na cópia isolada"},
            {"passo": 6, "skill": "evoluir.promover", "prova": "árvore limpa, hash igual ao ensaiado, backup feito"},
            {"passo": 7, "skill": "evoluir.reverter", "prova": "volta pelo backup se o resultado não servir"},
        ],
        "travas": [
            {"ordem": 1, "trava": "token de host", "padrao": "obrigatória", "vale_para": "todas"},
            {"ordem": 2, "trava": "JARVIS_HOST_EVOLUIR=1", "padrao": "desligada", "vale_para": "ensaiar, promover, reverter"},
            {"ordem": 3, "trava": "ensaio aprovado", "padrao": "obrigatória", "vale_para": "promover"},
            {"ordem": 4, "trava": "hash idêntico ao ensaiado", "padrao": "obrigatória", "vale_para": "promover"},
            {"ordem": 5, "trava": "árvore git limpa no arquivo", "padrao": "obrigatória", "vale_para": "promover"},
            {"ordem": 6, "trava": "backup antes da escrita", "padrao": "obrigatória", "vale_para": "promover"},
        ],
        "guardas": [{"codigo": codigo, "regra": regra, "onde": onde} for codigo, regra, onde in REGRAS_GUARDA],
        "perigos_monitorados": [{"padrao": padrao, "grupo": grupo, "titulo": titulo} for padrao, grupo, titulo, _ in PERIGOS],
        "raizes_permitidas": list(RAIZES_PERMITIDAS),
        "capacidades": capacidades(),
        "limites": {
            "diff": MAX_DIFF,
            "arquivos": MAX_ARQUIVOS,
            "hunks": MAX_HUNKS,
            "linhas": MAX_ROWS,
            "confirmacao": CONFIRMACAO_TTL,
        },
        "nao_faz": [
            "Não gera o patch: quem escreve a mudança é você ou o modelo externo.",
            "Não cria branch nem commita: a árvore viva fica modificada para revisão.",
            "Não reinicia a API: Python não recarrega módulo em execução.",
            "Não ensaia a interface: vitest e build do front ficam fora do ensaio.",
            "Não julga mérito: verde na suíte não significa que a mudança é boa.",
            "Não pisa em trabalho não commitado: promoção recusa árvore suja.",
        ],
    }
