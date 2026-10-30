"""Antes de instalar: onde guardar, se roda neste PC e o que falta.

A pergunta que abriu esta camada foi: *“se eu pedir para baixar um programa, ele
pergunta onde deixar, dá as opções, avisa se pode instalar e antes confere se o
programa é compatível com o meu PC?”*

A ordem aqui é a mesma do resto do projeto: **medir antes de prometer**. Três
degraus, do mais barato ao que mexe na máquina:

1. `destinos()` — onde o arquivo pode ficar, com espaço livre real de cada pasta.
   O instalador só executa o que está dentro da quarentena; então as opções são
   subpastas dela, e as pastas de fora aparecem marcadas como “guardar sim,
   instalar não”.
2. `analisar()` — lê o **cabeçalho** do arquivo (não executa, não instala) e
   compara com o que foi medido da máquina: arquitetura, versão mínima de
   sistema declarada no binário, .NET exigido, tamanho contra o espaço livre.
   Quando o arquivo não declara algo, isso é dito — não é inventado.
3. `baixar()` — reusa `sistema.baixar` (rede + token + quarentena) e muda o
   arquivo para a subpasta escolhida; depois analisa o que chegou.

A instalação em si continua em `sistema.instalar` (plano + token de uso único) e
`sistema.executar` (trava `JARVIS_HOST_INSTALAR=1`). Esta camada não instala
nada: ela evita instalar o que não vai rodar.
"""
from __future__ import annotations

import ctypes
import os
import platform
import re
import secrets
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from . import sistema as sistema_mod

VERSAO = "0.62.5"

MAX_CABECALHO = 8 * 1024 * 1024
TIMEOUT_CABECALHO = 12
RAIZ = Path(__file__).resolve().parent.parent
# `None` = perguntar a `sistema` a cada chamada: quando o modo dados troca a
# raiz (`JARVIS_DADOS`), `sistema.QUARENTENA` muda de lugar depois do import.
QUARENTENA: Path | None = None


def _quarentena() -> Path:
    """Pasta real da quarentena — inclusive depois de o modo dados trocar a raiz."""
    if QUARENTENA is not None:
        return Path(QUARENTENA)
    return Path(getattr(sistema_mod, "QUARENTENA"))

# build do Windows → nome comercial da versão
RELEASES = {
    10240: "1507",
    10586: "1511",
    14393: "1607",
    15063: "1703",
    16299: "1709",
    17134: "1803",
    17763: "1809",
    18362: "1903",
    18363: "1909",
    19041: "2004",
    19042: "20H2",
    19043: "21H1",
    19044: "21H2",
    19045: "22H2",
    22000: "11 21H2",
    22621: "11 22H2",
    22631: "11 23H2",
    26100: "11 24H2",
}

# requisito mínimo que o formato impõe por si só
BUILD_MINIMO = {
    "msix": (17763, "MSIX só existe a partir do Windows 10 1809 (build 17763)."),
    "appx": (10240, "APPX precisa de Windows 10."),
}

# pacote de outro sistema — não roda aqui
OUTROS_SISTEMAS = {
    ".dmg": "macOS",
    ".pkg": "macOS",
    ".deb": "Linux (Debian/Ubuntu)",
    ".rpm": "Linux (Fedora/RHEL)",
    ".appimage": "Linux",
    ".apk": "Android",
    ".ipa": "iOS",
}

SCRIPTS = {".bat", ".cmd", ".ps1", ".vbs", ".js", ".py", ".sh"}

MAQUINAS_PE = {
    0x014C: ("x86", 32),
    0x8664: ("x64", 64),
    0xAA64: ("arm64", 64),
    0x01C0: ("arm", 32),
    0x01C4: ("arm", 32),
    0x0200: ("ia64", 64),
}

MAGIC_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


class InstaladorError(Exception):
    """Recusa da camada: nada foi baixado, aberto ou executado."""


# ---------------------------------------------------------------------------
# Medir a máquina
# ---------------------------------------------------------------------------


def _u16(dados: bytes, pos: int) -> int | None:
    if pos < 0 or pos + 2 > len(dados):
        return None
    return int.from_bytes(dados[pos : pos + 2], "little")


def _u32(dados: bytes, pos: int) -> int | None:
    if pos < 0 or pos + 4 > len(dados):
        return None
    return int.from_bytes(dados[pos : pos + 4], "little")


def _versao_windows() -> dict[str, Any] | None:
    """Versão real do Windows, com o build e o nome comercial (1607, 22H2…)."""
    if not sys.platform.startswith("win"):
        return None
    try:
        v = sys.getwindowsversion()
    except (AttributeError, OSError):
        return None
    build = int(getattr(v, "build", 0))
    if build >= 22000:
        nome = "Windows 11"
    elif v.major == 10:
        nome = "Windows 10"
    else:
        nome = f"Windows {v.major}.{v.minor}"
    return {
        "major": int(v.major),
        "minor": int(v.minor),
        "build": build,
        "release": RELEASES.get(build, ""),
        "nome": nome,
        "service_pack": getattr(v, "service_pack", "") or "",
    }


def _ram_gb() -> float | None:
    if os.name == "nt":
        class _Mem(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        try:
            info = _Mem()
            info.dwLength = ctypes.sizeof(_Mem)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(info)):
                return None
            return round(info.ullTotalPhys / (1024**3), 1)
        except (AttributeError, OSError):
            return None
    try:
        with open("/proc/meminfo", encoding="utf-8") as arquivo:
            for linha in arquivo:
                if linha.startswith("MemTotal:"):
                    return round(int(linha.split()[1]) / (1024**2), 1)
    except OSError:
        return None
    return None


def _discos() -> list[dict[str, Any]]:
    achados: list[dict[str, Any]] = []
    if os.name == "nt":
        for letra in "CDEFGHIJKLMNOPQRSTUVWXYZ":
            raiz = f"{letra}:\\"
            try:
                if not Path(raiz).exists():
                    continue
                uso = shutil.disk_usage(raiz)
            except OSError:
                continue
            achados.append(
                {
                    "nome": f"{letra}:",
                    "livre_gb": round(uso.free / (1024**3), 1),
                    "total_gb": round(uso.total / (1024**3), 1),
                }
            )
        return achados
    try:
        uso = shutil.disk_usage("/")
        achados.append(
            {
                "nome": "/",
                "livre_gb": round(uso.free / (1024**3), 1),
                "total_gb": round(uso.total / (1024**3), 1),
            }
        )
    except OSError:
        pass
    return achados


def _dotnet() -> list[str]:
    """Versões do .NET Framework instaladas (o que muitos instaladores exigem)."""
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []
    faixas = [
        (533320, "4.8.1"),
        (528040, "4.8"),
        (461808, "4.7.2"),
        (460798, "4.7"),
        (394802, "4.6.2"),
        (393295, "4.6"),
        (379893, "4.5.2"),
        (378758, "4.5.1"),
        (378389, "4.5"),
    ]
    achados: list[str] = []
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full"
        ) as chave:
            release, _tipo = winreg.QueryValueEx(chave, "Release")
        for minimo, nome in faixas:
            if int(release) >= minimo:
                achados.append(nome)
                break
    except (OSError, ValueError):
        pass
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v3.5"
        ) as chave:
            instalado, _tipo = winreg.QueryValueEx(chave, "Install")
        if int(instalado) == 1:
            achados.append("3.5")
    except (OSError, ValueError):
        pass
    return achados


def _arquitetura_do_sistema() -> tuple[str, int]:
    bruto = (platform.machine() or "").lower()
    if bruto in {"amd64", "x86_64", "x64"}:
        return "x64", 64
    if bruto in {"arm64", "aarch64"}:
        return "arm64", 64
    if bruto in {"i386", "i686", "x86"}:
        return "x86", 32
    return bruto or "desconhecida", 64 if sys.maxsize > 2**32 else 32


def maquina() -> dict[str, Any]:
    """O que este PC é, medido — não estimado."""
    arquitetura, bits = _arquitetura_do_sistema()
    win = _versao_windows()
    discos = _discos()
    dados = {
        "windows": win,
        "plataforma": (
            f"{win['nome']} {win['release']} (build {win['build']})".strip()
            if win
            else f"{platform.system()} {platform.release()}"
        ),
        "arquitetura": arquitetura,
        "bits": bits,
        "ram_gb": _ram_gb(),
        "nucleos": os.cpu_count(),
        "discos": discos,
        "dotnet": _dotnet(),
    }
    if win:
        dados["resumo"] = (
            f"{dados['plataforma']}, {arquitetura} ({bits} bits), "
            f"{dados['ram_gb']} GB de RAM, {dados['nucleos']} núcleos."
        )
    else:
        dados["resumo"] = (
            f"{dados['plataforma']}, {arquitetura}, {dados['ram_gb']} GB de RAM. "
            "A camada de PC e de instalação é do Windows; fora dele só a análise roda."
        )
    dados["nota"] = (
        "Medido agora, com o que o sistema informa. Espaço livre é o de hoje — "
        "o Windows engorda a cada atualização."
    )
    return dados


# ---------------------------------------------------------------------------
# Onde guardar
# ---------------------------------------------------------------------------


def _livre_gb(caminho: Path) -> float | None:
    alvo = caminho
    while not alvo.exists() and alvo != alvo.parent:
        alvo = alvo.parent
    try:
        return round(shutil.disk_usage(alvo).free / (1024**3), 1)
    except OSError:
        return None


def _pasta(destino: str) -> Path:
    """Resolve o nome da opção para uma pasta **dentro** da quarentena."""
    nome = (destino or "").strip().strip("/\\")
    baixo = nome.lower()
    base = _quarentena()
    if baixo in {"", "padrao", "padrão", "quarentena"}:
        return base
    if baixo in {"programas", "instaladores"}:
        return base / "programas"
    if baixo in {"temporarios", "temporários", "temp"}:
        return base / "temporarios"
    if baixo in {"por-data", "por data", "data"}:
        return base / datetime.now().strftime("%Y-%m")
    if "/" in nome or "\\" in nome or nome.startswith(".") or ".." in nome:
        raise InstaladorError(
            "Nome de pasta inválido: use um nome simples, sem barra, sem `..` e sem ponto inicial."
        )
    return base / nome


def destinos() -> dict[str, Any]:
    """Onde o instalador pode ficar — com o espaço livre real de cada lugar."""
    base = _quarentena()
    opcoes = [
        {
            "nome": "padrao",
            "rotulo": "Quarentena (padrão)",
            "caminho": str(base),
            "nota": "É daqui que `sistema.executar` aceita instalar.",
            "recomendado": True,
        },
        {
            "nome": "programas",
            "rotulo": "Pasta de programas",
            "caminho": str(base / "programas"),
            "nota": "Para separar instaladores do que é só download.",
            "recomendado": False,
        },
        {
            "nome": "temporarios",
            "rotulo": "Temporários",
            "caminho": str(base / "temporarios"),
            "nota": "Para o que você vai apagar depois de instalar.",
            "recomendado": False,
        },
        {
            "nome": "por-data",
            "rotulo": "Separado por mês",
            "caminho": str(base / datetime.now().strftime("%Y-%m")),
            "nota": "Uma pasta por mês; útil quando se baixa muita coisa.",
            "recomendado": False,
        },
    ]
    for opcao in opcoes:
        pasta = Path(opcao["caminho"])
        opcao["existe"] = pasta.exists()
        opcao["livre_gb"] = _livre_gb(pasta)

    fora: list[dict[str, Any]] = []
    for pasta in (Path.home() / "Downloads", Path.home() / "Desktop"):
        if not pasta.exists():
            continue
        fora.append(
            {
                "nome": pasta.name,
                "caminho": str(pasta),
                "livre_gb": _livre_gb(pasta),
                "nota": "Guardar aqui funciona, mas instalar não: o instalador só executa de dentro da quarentena.",
            }
        )
    if os.name == "nt":
        for disco in _discos():
            prefixo = f"{disco['nome']}\\".upper()
            if any(str(item["caminho"]).upper().startswith(prefixo) for item in fora):
                continue
            fora.append(
                {
                    "nome": f"disco {disco['nome']}",
                    "caminho": f"{disco['nome']}\\",
                    "livre_gb": disco["livre_gb"],
                    "nota": "Fora da quarentena: guardar sim, instalar não.",
                }
            )

    return {
        "pasta_base": str(base),
        "opcoes": opcoes,
        "fora": fora,
        "nota": (
            "O `sistema.executar` só instala arquivo que passou pela quarentena "
            "(`storage/host-downloads`). Por isso as opções são subpastas dela: "
            "mudar de pasta não muda a trava."
        ),
        "resposta": "Onde guardar: " + ", ".join(f"{o['nome']} ({o['livre_gb']} GB livres)" for o in opcoes),
    }


# ---------------------------------------------------------------------------
# Ler o arquivo — cabeçalho, não execução
# ---------------------------------------------------------------------------


def _pe(dados: bytes) -> dict[str, Any] | None:
    """Lê o cabeçalho PE/NE: bits, arquitetura e versão mínima de Windows."""
    if len(dados) < 0x40 or dados[:2] != b"MZ":
        return None
    inicio = _u32(dados, 0x3C)
    if inicio is None or inicio + 24 > len(dados):
        return None
    assinatura = dados[inicio : inicio + 4]
    if assinatura == b"NE\x00\x00":
        return {"formato": "ne", "bits": 16, "arquitetura": "x86", "os_minimo": None}
    if assinatura != b"PE\x00\x00":
        return {"formato": "mz", "bits": 16, "arquitetura": "desconhecida", "os_minimo": None}

    identificador = _u16(dados, inicio + 4) or 0
    arquitetura, bits = MAQUINAS_PE.get(identificador, ("desconhecida", 0))
    opt = inicio + 24
    magic = _u16(dados, opt) or 0
    if magic not in {0x10B, 0x20B}:
        return {"formato": "pe", "bits": bits, "arquitetura": arquitetura, "os_minimo": None}

    maior = _u16(dados, opt + 40) or 0
    menor = _u16(dados, opt + 42) or 0
    os_minimo = (maior, menor) if (maior or menor) else None
    sub_maior = _u16(dados, opt + 48) or 0
    sub_menor = _u16(dados, opt + 50) or 0
    subsistema_id = _u16(dados, opt + 68) or 0
    subsistema = {2: "janela", 3: "console"}.get(subsistema_id, "")

    base_dir = opt + (96 if magic == 0x10B else 112)
    rva_clr = _u32(dados, base_dir + 14 * 8) or 0
    dotnet = ""
    if rva_clr:
        if b"v4.0.30319" in dados:
            dotnet = "4.x"
        elif b"v2.0.50727" in dados:
            dotnet = "2.0"
        else:
            dotnet = "clr"
    elif b"hostfxr" in dados[: 2 * 1024 * 1024]:
        dotnet = "core"

    return {
        "formato": "pe",
        "bits": bits,
        "arquitetura": arquitetura,
        "os_minimo": os_minimo,
        "subsistema_versao": (sub_maior, sub_menor) if (sub_maior or sub_menor) else None,
        "subsistema": subsistema,
        "dotnet": dotnet,
    }


def _msi(dados: bytes) -> dict[str, Any]:
    arquitetura = "desconhecida"
    if b"x\x006\x004\x00;\x00" in dados:
        arquitetura = "x64"
    elif b"I\x00n\x00t\x00e\x00l\x00;\x00" in dados:
        arquitetura = "x86"
    return {"formato": "msi", "arquitetura": arquitetura, "bits": 64 if arquitetura == "x64" else 32}


def _info_do_arquivo(caminho: Path) -> dict[str, Any]:
    extensao = caminho.suffix.lower()
    try:
        tamanho = caminho.stat().st_size
        with open(caminho, "rb") as arquivo:
            dados = arquivo.read(MAX_CABECALHO)
    except OSError as exc:
        raise InstaladorError(f"Não consegui ler {caminho.name}: {type(exc).__name__}.") from exc

    info: dict[str, Any] = {"nome": caminho.name, "bytes": tamanho, "extensao": extensao}

    if extensao in OUTROS_SISTEMAS:
        info.update({"formato": "outro-sistema", "sistema": OUTROS_SISTEMAS[extensao], "arquitetura": ""})
        return info

    if extensao in SCRIPTS:
        info.update({"formato": "script", "arquitetura": "", "bits": 0})
        return info

    if dados[:8] == MAGIC_OLE:
        info.update(_msi(dados))
        return info

    if dados[:2] == b"PK" and zipfile.is_zipfile(caminho):
        try:
            with zipfile.ZipFile(caminho) as pacote:
                nomes = pacote.namelist()[:400]
        except (zipfile.BadZipFile, OSError):
            nomes = []
        if any(nome.lower().endswith("appxmanifest.xml") for nome in nomes):
            info.update(
                {
                    "formato": "msix" if extensao == ".msix" else "appx",
                    "arquitetura": "",
                    "bits": 0,
                }
            )
            return info
        internos = [nome for nome in nomes if nome.lower().endswith((".exe", ".msi"))]
        info.update(
            {
                "formato": "zip",
                "arquitetura": "",
                "bits": 0,
                "internos": internos[:5],
            }
        )
        return info

    pe = _pe(dados)
    if pe is not None:
        info.update(pe)
        return info

    info.update({"formato": "desconhecido", "arquitetura": "", "bits": 0})
    return info


def _assinatura(caminho: Path) -> dict[str, Any]:
    """Assinatura Authenticode. Só no Windows; fora dele, diz que não verificou."""
    if os.name != "nt":
        return {"estado": "não verificável", "detalhe": "a verificação de assinatura é do Windows"}
    script = (
        "$s = Get-AuthenticodeSignature -LiteralPath $env:JARVIS_ALVO; "
        "Write-Output ($s.Status.ToString() + '|' + $s.SignerCertificate.Subject)"
    )
    ambiente = dict(os.environ)
    ambiente["JARVIS_ALVO"] = str(caminho)
    try:
        saida = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=20,
            env=ambiente,
        )
    except (OSError, subprocess.SubprocessError):
        return {"estado": "não verificável", "detalhe": "não consegui chamar o PowerShell"}
    linha = (saida.stdout or "").strip().splitlines()
    if not linha:
        return {"estado": "não verificável", "detalhe": "o PowerShell não respondeu"}
    estado, _, signatario = linha[0].partition("|")
    mapa = {
        "Valid": "válida",
        "NotSigned": "não assinada",
        "HashMismatch": "inválida",
        "NotTrusted": "inválida",
        "UnknownError": "indeterminada",
    }
    return {
        "estado": mapa.get(estado.strip(), "indeterminada"),
        "signatario": signatario.strip()[:160],
        "detalhe": f"Authenticode respondeu {estado.strip() or 'nada'}",
    }


def _cabecalho_remoto(url: str) -> dict[str, Any]:
    """Só o cabeçalho HTTP: tamanho e nome. Não baixa o arquivo."""
    limpa = sistema_mod._url_segura(url)  # mesma trava de rede privada do resto
    pedido = Request(
        limpa,
        method="HEAD",
        headers={"User-Agent": "jarvis-instalador/1.0"},
    )
    try:
        with urlopen(pedido, timeout=TIMEOUT_CABECALHO) as resposta:
            tamanho = int(resposta.headers.get("content-length") or 0)
            tipo = resposta.headers.get("content-type", "")
    except Exception as exc:  # HTTPError, URLError, timeout, SSL
        raise InstaladorError(
            f"O servidor não respondeu ao cabeçalho de {limpa}: {type(exc).__name__}. "
            "Dá para baixar mesmo assim e analisar depois."
        ) from exc
    nome = Path(urlparse(limpa).path).name or "arquivo"
    return {"url": limpa, "nome": nome, "bytes": tamanho, "tipo": tipo}


def _na_quarentena(caminho: Path) -> bool:
    try:
        resolvido = caminho.resolve()
        base = _quarentena().resolve()
    except OSError:
        return False
    return resolvido == base or base in resolvido.parents


# ---------------------------------------------------------------------------
# Julgar compatibilidade
# ---------------------------------------------------------------------------


def _build_de(texto: str) -> int | None:
    """Aceita 1607, 1809, 22H2, 'Windows 11' e devolve o build mínimo."""
    bruto = (texto or "").strip().lower()
    if not bruto:
        return None
    if re.search(r"windows\s*11|\bwin\s*11\b|\b11\b", bruto):
        return 22000
    if re.search(r"windows\s*7|\bwin\s*7\b|^7$", bruto):
        return 7601
    if re.search(r"windows\s*8\.1|\b8\.1\b", bruto):
        return 9600
    if re.search(r"windows\s*8\b|\bwin\s*8\b|^8$", bruto):
        return 9200
    if re.search(r"windows\s*10\b|\bwin\s*10\b|^10$", bruto):
        return 10240
    for build, release in RELEASES.items():
        if len(release) >= 4 and release.lower() in bruto:
            return build
    for numero in re.findall(r"\d{4,5}", bruto):
        valor = int(numero)
        if valor in RELEASES:
            return valor
        if valor >= 10240:
            return valor
    return None


def _avaliar(
    *,
    maquina: dict[str, Any],
    info: dict[str, Any],
    assinatura: dict[str, Any],
    min_os: str,
    ram_gb: float,
    disco_gb: float,
    arquitetura: str,
    livre_gb: float | None,
) -> dict[str, Any]:
    bloqueios: list[str] = []
    ressalvas: list[str] = []
    nao_verificado: list[str] = []
    avisos: list[str] = []

    win = maquina.get("windows")
    formato = info.get("formato", "")
    alvo = (arquitetura or info.get("arquitetura") or "").lower()
    bits_sistema = int(maquina.get("bits") or 0)

    if formato == "outro-sistema":
        bloqueios.append(
            f"É pacote de {info.get('sistema')}; o Windows não abre este formato."
        )
    if formato in {"ne", "mz"}:
        bloqueios.append(
            "É um programa de 16 bits. O Windows 10 de 64 bits não executa 16 bits "
            "(nem com compatibilidade)."
        )
    if formato == "desconhecido":
        ressalvas.append("O cabeçalho não é de instalador conhecido; não sei dizer o que é sem abrir.")
    if formato == "script":
        ressalvas.append(
            "É um script, não um instalador: roda o que estiver escrito nele, sem tela de instalação."
        )
    if formato == "zip":
        internos = info.get("internos") or []
        if internos:
            ressalvas.append(
                "É um ZIP com instalador dentro (" + ", ".join(internos) + "). "
                "A análise de dentro só acontece depois de extrair — e extrair ainda não instala."
            )
        else:
            ressalvas.append("É um ZIP sem instalador reconhecido dentro.")

    if formato in {"pe", "ne", "mz", "msi"}:
        if alvo == "arm64" and maquina.get("arquitetura") != "arm64":
            bloqueios.append(
                "Compilado para ARM64; este PC é x64 e o Windows 10 não emula ARM."
            )
        if alvo == "ia64":
            bloqueios.append("Compilado para Itanium: nenhum Windows atual executa.")
        if alvo == "x64" and bits_sistema == 32:
            bloqueios.append("É de 64 bits e este Windows é de 32 bits.")
        if alvo and alvo not in {"desconhecida", "x64", "x86", "arm64", "arm", "ia64"}:
            nao_verificado.append(f"Arquitetura declarada no arquivo: {alvo}.")

    if formato == "msi" and alvo == "desconhecida":
        nao_verificado.append(
            "Não consegui ler a arquitetura do MSI pelo cabeçalho; o Windows Installer "
            "recusa sozinho se for a errada."
        )

    # versão mínima que o próprio binário declara
    minimo = info.get("os_minimo")
    if minimo and win:
        atual = (int(win["major"]), int(win["minor"]))
        if tuple(minimo) > atual:
            bloqueios.append(
                f"O arquivo declara exigir Windows {minimo[0]}.{minimo[1]} ou maior; "
                f"este PC é {win['major']}.{win['minor']} (build {win['build']})."
            )

    # formato que já impõe build mínimo
    if formato in BUILD_MINIMO and win:
        build_minimo, motivo = BUILD_MINIMO[formato]
        if int(win["build"]) < build_minimo:
            bloqueios.append(f"{motivo} Este PC está no build {win['build']}.")

    # requisito de sistema que você informou (da página do fabricante)
    exigido = _build_de(min_os)
    if exigido and win and int(win["build"]) < exigido:
        nome = RELEASES.get(exigido, str(exigido))
        bloqueios.append(
            f"A página do fabricante pede Windows {nome} (build {exigido}); este PC está no build {win['build']}."
        )

    # .NET
    dotnet = info.get("dotnet") or ""
    if dotnet == "4.x":
        instaladas = [item for item in maquina.get("dotnet") or [] if item != "3.5"]
        if not instaladas:
            ressalvas.append("Feito para .NET Framework 4.x e não achei .NET 4 instalado (raro no Windows 10).")
    elif dotnet == "2.0":
        if "3.5" not in (maquina.get("dotnet") or []):
            ressalvas.append(
                "Feito para .NET 2.0/3.5, que no Windows 10 vem **desligado** por padrão: "
                "ligar exige administrador e download."
            )
    elif dotnet == "core":
        ressalvas.append(
            "Parece app .NET moderno: se for “framework-dependent”, precisa do .NET 6/8 instalado; "
            "se for autossuficiente, não precisa de nada."
        )

    # RAM e disco
    ram_maquina = maquina.get("ram_gb")
    if ram_gb:
        if ram_maquina and ram_gb > float(ram_maquina):
            bloqueios.append(f"Pede {ram_gb:g} GB de RAM; este PC tem {ram_maquina:g} GB.")
        elif ram_maquina and ram_gb > float(ram_maquina) * 0.9:
            ressalvas.append(f"Pede {ram_gb:g} GB de RAM e o PC tem {ram_maquina:g} GB: vai ficar apertado.")
    if disco_gb and livre_gb is not None:
        if disco_gb > livre_gb:
            bloqueios.append(f"Pede {disco_gb:g} GB livres; a pasta escolhida tem {livre_gb:g} GB.")
        elif disco_gb > livre_gb * 0.5:
            ressalvas.append(
                f"Pede {disco_gb:g} GB e a pasta tem {livre_gb:g} GB: vai ocupar mais da metade."
            )

    tamanho = int(info.get("bytes") or 0)
    if livre_gb is not None and tamanho and tamanho / (1024**3) > livre_gb * 0.6:
        ressalvas.append(
            f"O próprio arquivo tem {tamanho / (1024**3):.1f} GB, mais da metade do espaço livre ({livre_gb:g} GB)."
        )
    if tamanho and tamanho > 2 * 1024**3:
        nao_verificado.append("Instaladores grandes costumam precisar de espaço extra para descompactar.")

    estado = (assinatura or {}).get("estado", "")
    if estado == "inválida":
        ressalvas.append("A assinatura digital não confere: o arquivo pode ter sido alterado ou não ser do fabricante.")
    elif estado == "não assinada":
        ressalvas.append("Sem assinatura digital: não dá para confirmar quem publicou.")
    elif estado == "não verificável":
        nao_verificado.append("Assinatura não verificada fora do Windows.")

    if win and int(win["build"]) < 19041:
        avisos.append(
            f"Windows {win['release'] or win['build']} (build {win['build']}) é antigo: muitos "
            "instaladores de 2025/2026 pedem 1809/1903 ou mais novo e recusam na instalação."
        )
    if maquina.get("ram_gb") and float(maquina["ram_gb"]) <= 4:
        avisos.append(
            f"{maquina['ram_gb']:g} GB de RAM: programas com Electron/navegador embutido "
            "abrem, mas ficam pesados com outras coisas abertas."
        )

    if win is None:
        nao_verificado.append(
            "Build do Windows: esta análise está rodando fora do Windows, então não há "
            "build para comparar — quem decide é o instalador do seu PC."
        )

    if bloqueios:
        veredito = "não roda"
    elif win is None:
        # Sem o build do Windows na mão, "roda" seria promessa, não medição.
        veredito = "não dá para saber"
    elif formato in {"desconhecido", "zip"} and not ressalvas:
        veredito = "não dá para saber"
    elif ressalvas:
        veredito = "roda com ressalva"
    elif nao_verificado and not info.get("arquitetura"):
        veredito = "não dá para saber"
    else:
        veredito = "roda"

    sistema_txt = maquina.get("plataforma", "?")
    partes = [f"Veredito: **{veredito}**."]
    if veredito == "roda":
        partes.append(f"Pelo que o arquivo declara, roda neste PC ({sistema_txt}).")
    elif veredito == "roda com ressalva":
        partes.append(f"Deve rodar neste PC ({sistema_txt}), com os pontos abaixo.")
    elif veredito == "não roda":
        partes.append(f"Não roda neste PC ({sistema_txt}).")
    elif win is None:
        partes.append(
            "Não estou no Windows, então não comparo com o build do seu PC; "
            "o que dá para ler do arquivo está abaixo."
        )
    else:
        partes.append("O arquivo não declara o suficiente; não vou chutar.")

    return {
        "veredito": veredito,
        "resumo": " ".join(partes),
        "bloqueios": bloqueios,
        "ressalvas": ressalvas,
        "nao_verificado": nao_verificado,
        "avisos": avisos,
        "medido": {
            "sistema": sistema_txt,
            "arquitetura": maquina.get("arquitetura"),
            "bits": maquina.get("bits"),
            "ram_gb": maquina.get("ram_gb"),
            "nucleos": maquina.get("nucleos"),
            "dotnet": maquina.get("dotnet"),
            "livre_gb": livre_gb,
        },
    }


def _proximos_passos(caminho: Path | None, veredito: str) -> list[str]:
    if caminho is None:
        return [
            "Baixar e guardar: `instalador.baixar` (precisa de `JARVIS_HOST_REDE=1` e do token).",
            "Depois, analisar de novo o arquivo que chegou.",
        ]
    if veredito == "não roda":
        return [
            "Não instale esta versão: procure a build compatível com o seu Windows no site do fabricante.",
            "Se for programa que exige Windows novo, a alternativa é usar no navegador ou em outra máquina.",
        ]
    passos = []
    if _na_quarentena(caminho):
        passos.append("Plano com token: `sistema.instalar` (arquivo + `exigir_assinatura` se quiser).")
        passos.append(
            "Instalar de verdade: `sistema.executar` com o token, `JARVIS_HOST_INSTALAR=1` e a confirmação."
        )
        passos.append("Desfazer depois: `sistema.desinstalar`.")
    else:
        passos.append(
            f"Para instalar, o arquivo precisa estar na quarentena: `{_quarentena()}`. "
            "Mova para lá e rode `instalador.analisar` de novo."
        )
    return passos


def analisar(
    *,
    arquivo: str = "",
    url: str = "",
    min_os: str = "",
    ram_gb: float = 0.0,
    disco_gb: float = 0.0,
    arquitetura: str = "",
    conferir_assinatura: bool = True,
    maquina_dada: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Julga se o programa roda neste PC, só pelo que dá para medir."""
    alvo = (arquivo or "").strip()
    link = (url or "").strip()

    if not alvo and not link:
        dados = maquina_dada or maquina()
        quem = (dados.get("resumo") or dados.get("plataforma") or "não identificado").rstrip(".")
        resumo = (
            f"Seu PC: {quem}. "
            "Manda o link do instalador (ou o arquivo já baixado) que eu leio o cabeçalho e digo se roda."
        )
        return {
            "alvo": "",
            "veredito": "não dá para saber",
            "resposta": resumo,
            "resumo": resumo,
            "bloqueios": [],
            "ressalvas": [],
            "nao_verificado": ["Sem link nem arquivo não há o que medir no programa."],
            "medido": dados,
            "declarado": {},
            "assinatura": {},
            "proximos_passos": _proximos_passos(None, ""),
        }

    remoto: dict[str, Any] = {}
    if link:
        remoto = _cabecalho_remoto(link)

    caminho: Path | None = None
    if alvo:
        bruto = Path(alvo).expanduser()
        candidatos = [bruto]
        if not bruto.is_absolute():
            candidatos += [_quarentena() / alvo, RAIZ / alvo]
        for candidato in candidatos:
            if candidato.is_file():
                caminho = candidato
                break
        if caminho is None:
            raise InstaladorError(f"Não achei o arquivo “{alvo}”. Informe o caminho completo ou o link.")

    dados = maquina_dada or maquina()
    info: dict[str, Any]
    if caminho is not None:
        info = _info_do_arquivo(caminho)
        livre = _livre_gb(caminho.parent)
        assinatura = _assinatura(caminho) if conferir_assinatura else {"estado": "não verificada"}
    else:
        info = {
            "nome": remoto.get("nome", "arquivo"),
            "bytes": remoto.get("bytes", 0),
            "extensao": Path(remoto.get("nome", "")).suffix.lower(),
            "formato": "remoto",
            "arquitetura": "",
            "bits": 0,
        }
        if info["extensao"] in OUTROS_SISTEMAS:
            info["formato"] = "outro-sistema"
            info["sistema"] = OUTROS_SISTEMAS[info["extensao"]]
        elif info["extensao"] in {".msix", ".appx"}:
            info["formato"] = info["extensao"].lstrip(".")
        elif info["extensao"] in SCRIPTS:
            info["formato"] = "script"
        elif info["extensao"] in {".exe", ".msi"}:
            info["formato"] = "instalador-remoto"
        livre = _livre_gb(_quarentena())
        assinatura = {
            "estado": "não verificada",
            "detalhe": "só dá para conferir assinatura depois de baixar",
        }
        nao_verificado = [
            "O link ainda não foi baixado: arquitetura, versão mínima e .NET só aparecem no arquivo."
        ]
    if caminho is None:
        base = _avaliar(
            maquina=dados,
            info=info,
            assinatura=assinatura,
            min_os=min_os,
            ram_gb=ram_gb,
            disco_gb=disco_gb,
            arquitetura=arquitetura,
            livre_gb=livre,
        )
        base["nao_verificado"] = nao_verificado + base["nao_verificado"]
        base["resumo"] += " Baixe para eu ler o cabeçalho."
        base["veredito"] = "não dá para saber" if base["veredito"] == "roda" else base["veredito"]
    else:
        base = _avaliar(
            maquina=dados,
            info=info,
            assinatura=assinatura,
            min_os=min_os,
            ram_gb=ram_gb,
            disco_gb=disco_gb,
            arquitetura=arquitetura,
            livre_gb=livre,
        )

    declarado = {
        "min_os": min_os,
        "ram_gb": ram_gb or None,
        "disco_gb": disco_gb or None,
        "arquitetura": arquitetura or None,
    }
    resultado = {
        "alvo": str(caminho) if caminho else remoto.get("url", ""),
        "nome": info.get("nome"),
        "bytes": info.get("bytes"),
        "formato": info.get("formato"),
        "arquitetura_do_arquivo": info.get("arquitetura"),
        "os_minimo_do_arquivo": (
            f"{info['os_minimo'][0]}.{info['os_minimo'][1]}" if info.get("os_minimo") else ""
        ),
        "dotnet": info.get("dotnet", ""),
        "assinatura": assinatura,
        "declarado": declarado,
        "proximos_passos": _proximos_passos(caminho, base["veredito"]),
        **base,
    }
    resultado["resposta"] = _texto(resultado)
    return resultado


def _texto(resultado: dict[str, Any]) -> str:
    linhas = [str(resultado.get("resumo") or "")]
    nome = resultado.get("nome")
    if nome:
        linhas.append(f"Arquivo: {nome} — {resultado.get('formato')} "
                      f"({resultado.get('arquitetura_do_arquivo') or 'arquitetura não declarada'}), "
                      f"{_mb(resultado.get('bytes'))}.")
    for rotulo, chave in (
        ("Não roda porque", "bloqueios"),
        ("Ressalvas", "ressalvas"),
        ("Sobre o seu PC", "avisos"),
        ("O que não deu para medir", "nao_verificado"),
    ):
        itens = resultado.get(chave) or []
        if itens:
            linhas.append("")
            linhas.append(rotulo + ":")
            linhas += [f"• {item}" for item in itens]
    if resultado.get("proximos_passos"):
        linhas.append("")
        linhas.append("Próximo passo:")
        linhas += [f"• {item}" for item in resultado["proximos_passos"]]
    return "\n".join(linhas)


def _mb(bytes_: Any) -> str:
    try:
        valor = int(bytes_ or 0)
    except (TypeError, ValueError):
        return "tamanho desconhecido"
    if valor <= 0:
        return "tamanho não informado"
    if valor < 1024 * 1024:
        return f"{valor / 1024:.0f} KB"
    return f"{valor / (1024**2):.1f} MB"


# ---------------------------------------------------------------------------
# Baixar para a pasta escolhida
# ---------------------------------------------------------------------------


EXTENSAO_POR_TIPO = {
    "application/zip": ".zip",
    "application/x-zip-compressed": ".zip",
    "application/x-msdownload": ".exe",
    "application/vnd.microsoft.portable-executable": ".exe",
    "application/x-msi": ".msi",
    "application/x-msix": ".msix",
}


def _nome_com_extensao(nome: str, tipo: str) -> str:
    """Link sem nome de arquivo (`/refs/heads/main`) ganha extensão pelo content-type."""
    if Path(nome).suffix:
        return nome
    limpo = (tipo or "").split(";")[0].strip().lower()
    return nome + EXTENSAO_POR_TIPO.get(limpo, "")


def baixar(
    *,
    url: str,
    destino: str = "padrao",
    modo: str = "full",
    autorizacao: str = "",
    baixar_arquivo: Callable[..., dict[str, Any]] | None = None,
    conferir_assinatura: bool = True,
) -> dict[str, Any]:
    """Baixa pela quarentena (rede + token) e guarda na subpasta escolhida."""
    pasta = _pasta(destino)
    try:
        pasta.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise InstaladorError(f"Não consegui criar a pasta {pasta}: {type(exc).__name__}.") from exc

    livre = _livre_gb(pasta)
    if livre is not None and livre < 0.2:
        raise InstaladorError(f"A pasta escolhida tem só {livre:g} GB livres. Escolha outra opção em `instalador.destinos`.")

    fn = baixar_arquivo or sistema_mod.baixar
    try:
        bruto = fn(url=url, modo=modo, autorizacao=autorizacao)
    except sistema_mod.SistemaError as exc:
        raise InstaladorError(str(exc)) from exc
    except TypeError as exc:
        raise InstaladorError(f"Não consegui chamar o download: {exc}") from exc

    # `sistema.baixar` devolve os dados do arquivo dentro de `download`.
    baixado = bruto.get("download") if isinstance(bruto.get("download"), dict) else bruto
    origem = Path(str(baixado.get("arquivo") or ""))
    if not origem.is_file():
        raise InstaladorError("O download não deixou arquivo na quarentena.")

    nome = _nome_com_extensao(origem.name, str(baixado.get("tipo") or ""))
    final = pasta / nome
    if final.exists():
        final = pasta / f"{Path(nome).stem}-{secrets.token_hex(2)}{Path(nome).suffix}"
    try:
        if final != origem:
            shutil.move(str(origem), str(final))
    except OSError as exc:
        raise InstaladorError(f"Baixou, mas não consegui mover para {pasta}: {type(exc).__name__}.") from exc

    analise = analisar(arquivo=str(final), conferir_assinatura=conferir_assinatura)
    resultado = {
        "arquivo": str(final),
        "pasta": str(pasta),
        "destino": destino or "padrao",
        "bytes": baixado.get("bytes"),
        "sha256": baixado.get("sha256"),
        "analise": analise,
        "veredito": analise.get("veredito"),
        "proximos_passos": analise.get("proximos_passos"),
    }
    resultado["resposta"] = (
        f"Baixei para {final} ({_mb(baixado.get('bytes'))}, sha256 {str(baixado.get('sha256') or '')[:16]}…).\n\n"
        + str(analise.get("resposta") or analise.get("resumo") or "")
    )
    return resultado
