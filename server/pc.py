"""PC — abrir programa e rodar comando pronto, sem entregar o shell.

O pedido: *“se eu pedir para ele abrir um programa ou usar meu PowerShell ou o cmd,
ele consegue?”* Conseguir, consegue — mas do jeito seguro, que é o único jeito que
este projeto aceita:

- **abrir programa**: lista fechada de programas (`notepad`, `calc`, `mspaint`,
  `explorer`, `cmd`, `powershell`, `taskmgr`, `control`, `charmap`, `magnify`).
  O nome vem da lista; nada de caminho livre, nada de argumento.
- **abrir arquivo**: só arquivo que já está em `storage/`, `Downloads`,
  `Documentos` ou `Área de trabalho`, e só de formato que abre em programa de
  leitura (PDF, Office, texto, imagem, áudio, vídeo). `.exe`, `.bat`, `.ps1`,
  `.lnk` e `.url` são recusados de propósito.
- **rodar comando**: lista fechada de comandos **de leitura** (`ipconfig`,
  `systeminfo`, `tasklist`, `ver`, `query user` e três consultas de PowerShell
  com script fixo). O comando é escolhido por nome, não digitado — então não
  existe espaço para injetar `; rm -rf`, pipe ou redirecionamento.

O que este módulo **não** faz, e não vai fazer: executar linha de comando livre
digitada por você ou por um modelo. Um agente com shell aberto é um agente que
pode apagar o disco por causa de uma frase ambígua. Para instalar programa existe
`sistema.executar` (com allowlist, token e `JARVIS_HOST_INSTALAR=1`); para rodar
código de repositório existe `repos.executar` (interpretador de lista fechada).

Tudo aqui exige `JARVIS_HOST_PC=1` e confirmação explícita. Sem a variável, a
skill responde que está desligada e explica como ligar.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from . import dados

AMBIENTE = "JARVIS_HOST_PC"
MAX_SAIDA = 4_000
TIMEOUT = 25

# nome interno → (executável, rótulo em português)
PROGRAMAS: dict[str, tuple[str, str]] = {
    "notepad": ("notepad.exe", "Bloco de notas"),
    "calc": ("calc.exe", "Calculadora"),
    "mspaint": ("mspaint.exe", "Paint"),
    "explorer": ("explorer.exe", "Explorador de arquivos"),
    "cmd": ("cmd.exe", "Prompt de comando"),
    "powershell": ("powershell.exe", "PowerShell"),
    "taskmgr": ("taskmgr.exe", "Gerenciador de tarefas"),
    "control": ("control.exe", "Painel de controle"),
    "charmap": ("charmap.exe", "Mapa de caracteres"),
    "magnify": ("magnify.exe", "Lupa"),
}

# como se fala → nome interno
APELIDOS: dict[str, str] = {
    "bloco de notas": "notepad",
    "notepad": "notepad",
    "calculadora": "calc",
    "calc": "calc",
    "paint": "mspaint",
    "mspaint": "mspaint",
    "explorador": "explorer",
    "explorer": "explorer",
    "meu computador": "explorer",
    "arquivos": "explorer",
    "prompt": "cmd",
    "cmd": "cmd",
    "prompt de comando": "cmd",
    "powershell": "powershell",
    "power shell": "powershell",
    "gerenciador de tarefas": "taskmgr",
    "task manager": "taskmgr",
    "painel de controle": "control",
    "configuracoes": "control",
    "configurações": "control",
    "mapa de caracteres": "charmap",
    "lupa": "magnify",
}

# nome → (comando fixo, rótulo). Nada aqui aceita argumento do usuário.
COMANDOS: dict[str, tuple[list[str], str]] = {
    "ip": (["ipconfig"], "Endereços de rede"),
    "ip-tudo": (["ipconfig", "/all"], "Rede completo (MAC, DNS, DHCP)"),
    "sistema": (["systeminfo"], "Informações do sistema"),
    "processos": (["tasklist"], "Processos em execução"),
    "usuarios": (["query", "user"], "Sessões de usuário abertas"),
    "versao": (["cmd", "/c", "ver"], "Versão do Windows"),
    "disco": (
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "Get-PSDrive -PSProvider FileSystem | Select-Object Name,@{n='UsadoGB';e={[math]::Round($_.Used/1GB,1)}},@{n='LivreGB';e={[math]::Round($_.Free/1GB,1)}} | Format-Table -AutoSize",
        ],
        "Espaço em disco",
    ),
    "data": (
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", "Get-Date -Format 'yyyy-MM-dd HH:mm:ss'"],
        "Data e hora do PC",
    ),
    "boot": (
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime",
        ],
        "Quando o PC foi ligado",
    ),
}

EXTENSOES_ABRIVEIS = {
    ".pdf", ".txt", ".md", ".csv", ".log", ".json",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
    ".mp3", ".wav", ".ogg", ".mp4", ".mkv", ".webm",
}

EXTENSOES_EXECUTAVEIS = {".exe", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".msi", ".lnk", ".url", ".scr", ".hta"}


class PcError(ValueError):
    """Programa fora da lista, arquivo recusado ou camada desligada."""


def ligado() -> bool:
    return os.getenv(AMBIENTE) == "1"


def _exigir_ligado() -> None:
    if not ligado():
        raise PcError(
            "A camada do PC está desligada. Suba a API com JARVIS_HOST_PC=1 "
            "(é o mesmo cuidado de JARVIS_HOST_REDE e JARVIS_HOST_INSTALAR)."
        )


def _exigir_windows(acao: str) -> None:
    if sys.platform != "win32":
        raise PcError(f"{acao} só funciona no Windows — esta API está em {sys.platform}.")


def programas() -> dict[str, Any]:
    """O que ele consegue abrir e rodar — sem executar nada."""
    return {
        "ligado": ligado(),
        "variavel": AMBIENTE,
        "programas": [{"nome": nome, "rotulo": rotulo, "executavel": exe} for nome, (exe, rotulo) in PROGRAMAS.items()],
        "comandos": [{"nome": nome, "rotulo": rotulo, "linha": " ".join(linha)} for nome, (linha, rotulo) in COMANDOS.items()],
        "nota": (
            "Lista fechada de propósito: o JARVIS abre o programa e roda o comando pelo nome, "
            "nunca por uma linha digitada. Shell livre continua fora do projeto."
        ),
    }


def _resolver(nome: str) -> str:
    chave = " ".join((nome or "").strip().lower().split())
    if chave in APELIDOS:
        return APELIDOS[chave]
    if chave in PROGRAMAS:
        return chave
    raise PcError(
        f"Não abro “{nome}”. A lista é: " + ", ".join(sorted(PROGRAMAS)) + "."
    )


def abrir_programa(
    nome: str,
    *,
    abrir: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Abre um programa da lista fechada — sem argumento, sem caminho livre."""
    _exigir_ligado()
    chave = _resolver(nome)
    executavel, rotulo = PROGRAMAS[chave]
    acao = abrir or (lambda exe: subprocess.Popen([exe], shell=False, close_fds=True))
    _exigir_windows("Abrir programa")
    tentativas = [executavel]
    if chave == "powershell" and shutil.which("pwsh"):
        tentativas.append("pwsh.exe")
    erro = ""
    for exe in tentativas:
        try:
            acao(exe)
        except FileNotFoundError:
            erro = exe
            continue
        except OSError as exc:
            raise PcError(f"O Windows recusou abrir {exe}: {exc}") from exc
        return {
            "programa": chave,
            "rotulo": rotulo,
            "executavel": exe,
            "aberto": True,
            "resposta": f"Abri o {rotulo} ({exe}). Se a janela não aparecer, veja a barra de tarefas.",
        }
    raise PcError(f"Não achei o executável ({erro}). Ele está instalado neste PC?")


def _raizes_permitidas() -> list[Path]:
    casa = Path.home()
    candidatas = [dados.raiz(), casa / "Downloads", casa / "Documents", casa / "Desktop", casa / "OneDrive"]
    raizes: list[Path] = []
    for candidata in candidatas:
        try:
            resolvida = Path(candidata).resolve()
        except OSError:
            continue
        if resolvida not in raizes:
            raizes.append(resolvida)
    return raizes


def abrir_arquivo(
    caminho: str,
    *,
    abrir: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Abre um documento com o programa padrão — só dentro das pastas do usuário."""
    _exigir_ligado()
    bruto = (caminho or "").strip()
    if not bruto:
        raise PcError("Diga qual arquivo abrir.")
    alvo = Path(bruto).expanduser()
    if not alvo.is_absolute():
        alvo = dados.raiz() / bruto
    try:
        alvo = alvo.resolve()
    except OSError as exc:
        raise PcError(f"Não consegui resolver o caminho: {exc}") from exc
    if not any(alvo == raiz or raiz in alvo.parents for raiz in _raizes_permitidas()):
        raise PcError(
            "Só abro arquivo de dentro de storage/, Downloads, Documentos ou Área de trabalho."
        )
    if not alvo.is_file():
        raise PcError("Arquivo não encontrado.")
    sufixo = alvo.suffix.lower()
    if sufixo in EXTENSOES_EXECUTAVEIS:
        raise PcError(
            f"“{sufixo}” é executável — abrir isso é rodar programa, e isso não faço por aqui. "
            "Use `sistema.executar` (com token e allowlist) se for instalar algo."
        )
    if sufixo not in EXTENSOES_ABRIVEIS:
        raise PcError(
            "Formato fora da lista de leitura. Aceito: " + ", ".join(sorted(EXTENSOES_ABRIVEIS)) + "."
        )
    _exigir_windows("Abrir arquivo")
    acao = abrir or (lambda caminho: os.startfile(caminho))  # type: ignore[attr-defined]
    try:
        acao(str(alvo))
    except OSError as exc:
        raise PcError(f"O Windows recusou abrir o arquivo: {exc}") from exc
    return {
        "arquivo": str(alvo),
        "nome": alvo.name,
        "formato": sufixo,
        "aberto": True,
        "resposta": f"Abri “{alvo.name}” no programa padrão do Windows.",
    }


def _cortar(texto: str, limite: int = MAX_SAIDA) -> str:
    limpo = (texto or "").strip()
    if len(limpo) <= limite:
        return limpo
    return limpo[:limite] + "\n… (saída cortada)"


def rodar_comando(
    nome: str,
    *,
    executar: Callable[[list[str]], tuple[int, str, str]] | None = None,
) -> dict[str, Any]:
    """Roda um comando de leitura da lista fechada e devolve a saída."""
    _exigir_ligado()
    chave = (nome or "").strip().lower()
    if chave not in COMANDOS:
        raise PcError("Comando fora da lista. Aceito: " + ", ".join(sorted(COMANDOS)) + ".")
    linha, rotulo = COMANDOS[chave]
    _exigir_windows("Rodar comando")

    if executar is None:
        def executar(argumentos: list[str]) -> tuple[int, str, str]:
            try:
                concluido = subprocess.run(
                    argumentos,
                    shell=False,
                    capture_output=True,
                    text=True,
                    timeout=TIMEOUT,
                    errors="replace",
                )
            except FileNotFoundError as exc:
                raise PcError(f"O comando “{argumentos[0]}” não existe neste PC.") from exc
            except subprocess.TimeoutExpired as exc:
                raise PcError(f"O comando passou de {TIMEOUT}s e foi interrompido.") from exc
            return concluido.returncode, concluido.stdout, concluido.stderr

    codigo, saida, erro = executar(linha)
    texto = _cortar(saida) if saida.strip() else _cortar(erro)
    if codigo != 0 and not texto:
        texto = f"O comando terminou com código {codigo} e não devolveu texto."
    return {
        "comando": chave,
        "rotulo": rotulo,
        "linha": " ".join(linha),
        "codigo": codigo,
        "saida": texto,
        "vazio": not bool(texto),
        "resposta": f"{rotulo} — `{' '.join(linha)}`\n\n{texto}" if texto else f"{rotulo}: o comando não devolveu texto.",
    }
