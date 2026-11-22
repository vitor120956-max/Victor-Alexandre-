"""Anatomia — ler o que um aparelho é, sem mudar nada nele.

O pedido do dono, vindo de uma conversa colada: *“conectar um aparelho no USB e
fazer uma varredura… não para modificar, mas para entender todos os componentes
e arquivos, igual anatomia humana”*. E, depois: *“e uma TV antiga que pega
wifi, tipo uma TCL Roku?”*.

Este módulo entrega a parte que **existe** e diz onde a conversa que ele colou
prometia demais. Três alvos, todos de leitura:

- **`local`** — a máquina onde a API roda: CPU, memória, discos, GPU e
  temperatura, cada um com a fonte e, quando não há leitura, o motivo.
- **`android`** (USB) — `adb` já existe no projeto (`celular.py`); aqui só se
  usa `shell` de leitura: `getprop`, `dumpsys battery`, `/proc/*`, `df`,
  `pm list packages`, `/sys/class/thermal`. Nada é instalado, puxado,
  desligado ou reiniciado, e `su` nunca é chamado.
- **`roku`** (rede) — o ECP da TV na porta 8060: `/query/device-info`,
  `/query/apps`, `/query/active-app`. Só `GET`. **Não** existe `POST
  /keypress` aqui: apertar botão muda a TV, e este módulo não muda nada.

O que ele **não** faz, e por quê:

- ler a memória de outro aplicativo ou partição criptografada sem root — o
  Android não entrega, e quem diz que entrega está vendendo;
- enxergar temperatura de CPU no Windows sem um sensor exposto — o sistema não
  publica; quando o modelo não expõe, a resposta é “não exposta”, com o motivo;
- “varredura automática ao plugar o cabo”: o Android exige **Depuração USB**
  ligada e o toque em “Permitir” na tela, uma vez por computador;
- descompilar o app do celular sozinho: o `adb pull` copia o APK e a aba
  Reversa analisa o arquivo — são dois passos, e o JARVIS diz isso em vez de
  fingir que é um.

Guardas, iguais às do resto do projeto: Android exige `JARVIS_HOST_CELULAR=1`
(mesma variável da aba Máquina/celular) e Roku exige `JARVIS_HOST_REDE=1`. A
máquina local é lida sempre — são dados que o próprio sistema publica para
qualquer processo, sem privilégio.
"""
from __future__ import annotations

import ctypes
import ipaddress
import os
import platform
import shutil
import socket
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import celular

AMBIENTE_ANDROID = "JARVIS_HOST_CELULAR"
AMBIENTE_REDE = "JARVIS_HOST_REDE"
TIMEOUT = 20
TIMEOUT_REDE = 4
MAX_SAIDA = 60_000
PORTA_ROKU = 8060
PORTA_ROKU_DEV = 8085

# As propriedades que respondem “o que é este aparelho”. O `getprop` devolve
# centenas; despejar todas seria ruído, e escolher na hora do código é o que
# permite um teste que não depende do aparelho do dono.
PROPS = (
    ("ro.product.manufacturer", "Fabricante"),
    ("ro.product.brand", "Marca"),
    ("ro.product.model", "Modelo"),
    ("ro.product.device", "Nome interno"),
    ("ro.build.version.release", "Android"),
    ("ro.build.version.sdk", "API (SDK)"),
    ("ro.build.version.security_patch", "Patch de segurança"),
    ("ro.soc.manufacturer", "Fabricante do SoC"),
    ("ro.soc.model", "SoC"),
    ("ro.board.platform", "Plataforma"),
    ("ro.hardware", "Hardware"),
    ("ro.product.cpu.abi", "ABI principal"),
    ("ro.product.cpu.abilist", "ABIs"),
    ("ro.bootloader", "Bootloader"),
    ("ro.build.type", "Tipo de build"),
    ("ro.secure", "Secure boot"),
    ("ro.build.fingerprint", "Fingerprint"),
    # 0.92.7 — o estado do bootloader é o que separa "dá para pôr root" de
    # "não dá sem apagar o aparelho". Sem estas três, o mapa de degraus chutava.
    ("ro.boot.verifiedbootstate", "Verified boot"),
    ("ro.boot.flash.locked", "Bootloader travado"),
    ("ro.debuggable", "Depurável"),
    ("service.adb.tcp.port", "ADB pela rede (porta)"),
)

ROTULOS_ELETRICO = {
    "1": "desconhecido",
    "2": "carregando",
    "3": "descarregando",
    "4": "sem carga",
    "5": "cheia",
}

SAUDE_BATERIA = {
    "1": "desconhecida",
    "2": "boa",
    "3": "superaquecida",
    "4": "danificada",
    "5": "tensão acima do limite",
    "6": "falha",
    "7": "fria demais",
}

NAO_FAZ = (
    "Não instala, não desinstala, não reinicia e não altera configuração nenhuma no aparelho.",
    "Não lê a memória de outros aplicativos nem partição criptografada: sem root, o Android não entrega.",
    "Não faz “varredura automática ao plugar o cabo”: a Depuração USB e o “Permitir” na tela são de uma pessoa, uma vez.",
    "Não descompila o app do celular sozinho: copiar o APK (`adb pull`) e analisar na aba Reversa são dois passos.",
)


class AnatomiaError(RuntimeError):
    """Falha que a tela mostra como frase, não como rastro de pilha."""


# ---------------------------------------------------------------- utilidades


def _agora() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _rodar(argumentos: list[str], timeout: int = TIMEOUT) -> tuple[int, str, str]:
    extra: dict[str, Any] = {}
    if os.name == "nt":
        extra["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        concluido = subprocess.run(
            argumentos,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            errors="replace",
            **extra,
        )
    except FileNotFoundError as exc:
        raise AnatomiaError(f"O executável “{argumentos[0]}” não está instalado.") from exc
    except subprocess.TimeoutExpired as exc:
        raise AnatomiaError(
            f"“{' '.join(argumentos[:3])}…” passou de {timeout}s. "
            "Na primeira chamada o adb sobe um serviço próprio; tente de novo."
        ) from exc
    except OSError as exc:
        raise AnatomiaError(f"O sistema recusou rodar “{argumentos[0]}”: {exc}") from exc
    return concluido.returncode, concluido.stdout or "", concluido.stderr or ""


def _cortar(texto: str, limite: int = MAX_SAIDA) -> str:
    limpo = (texto or "").strip()
    return limpo if len(limpo) <= limite else limpo[:limite] + "\n… (saída cortada)"


def _secao(identificador: str, titulo: str, itens: list[dict[str, str]]) -> dict[str, Any]:
    return {"id": identificador, "titulo": titulo, "itens": [i for i in itens if i.get("valor")]}


def _item(rotulo: str, valor: Any) -> dict[str, str]:
    texto = "" if valor is None else str(valor).strip()
    return {"rotulo": rotulo, "valor": texto}


def _mb(bytes_: float) -> str:
    return f"{bytes_ / (1024 * 1024):,.0f} MB".replace(",", ".")


def _gb(bytes_: float) -> str:
    return f"{bytes_ / (1024 ** 3):,.1f} GB".replace(",", ".").replace(".", ",")


def _temperatura_legivel(mili_celsius: int) -> str:
    """`/sys/class/thermal` fala em milésimos de grau."""
    return f"{mili_celsius / 1000:.1f} °C".replace(".", ",")


def _decimos_celsius(decimos: int) -> str:
    """O `dumpsys battery` fala em décimos — 312 é 31,2 °C, não 0,3 °C."""
    return f"{decimos / 10:.1f} °C".replace(".", ",")


# ---------------------------------------------------------------- local


def _cpu_linux(raiz: Path) -> list[dict[str, str]]:
    itens: list[dict[str, str]] = []
    caminho = raiz / "cpuinfo"
    if not caminho.is_file():
        return itens
    try:
        texto = caminho.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return itens
    modelo = ""
    for linha in texto.splitlines():
        if linha.lower().startswith("model name") and not modelo:
            modelo = linha.split(":", 1)[-1].strip()
    if modelo:
        itens.append(_item("Modelo da CPU", modelo))
    nucleos = texto.count("processor\t:") or sum(
        1 for linha in texto.splitlines() if linha.startswith("processor")
    )
    if nucleos:
        itens.append(_item("Núcleos vistos", nucleos))
    return itens


def _memoria_linux(raiz: Path) -> list[dict[str, str]]:
    caminho = raiz / "meminfo"
    if not caminho.is_file():
        return []
    valores: dict[str, int] = {}
    try:
        for linha in caminho.read_text(encoding="utf-8", errors="replace").splitlines():
            if ":" not in linha:
                continue
            chave, resto = linha.split(":", 1)
            numero = resto.strip().split(" ")[0]
            if numero.isdigit():
                valores[chave.strip()] = int(numero) * 1024
    except OSError:
        return []
    itens: list[dict[str, str]] = []
    if "MemTotal" in valores:
        itens.append(_item("Memória total", _gb(valores["MemTotal"])))
    if "MemAvailable" in valores:
        itens.append(_item("Disponível agora", _gb(valores["MemAvailable"])))
    if "SwapTotal" in valores and valores["SwapTotal"]:
        itens.append(_item("Swap", _gb(valores["SwapTotal"])))
    return itens


def _memoria_windows() -> list[dict[str, str]]:
    class _Status(ctypes.Structure):
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

    status = _Status()
    status.dwLength = ctypes.sizeof(_Status)
    try:
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):  # type: ignore[attr-defined]
            return []
    except (AttributeError, OSError):
        return []
    return [
        _item("Memória total", _gb(float(status.ullTotalPhys))),
        _item("Disponível agora", _gb(float(status.ullAvailPhys))),
        _item("Uso", f"{status.dwMemoryLoad}%"),
    ]


def _cpu_windows() -> list[dict[str, str]]:
    try:
        import winreg  # type: ignore[import-not-found]
    except ImportError:
        return []
    try:
        with winreg.OpenKey(  # type: ignore[attr-defined]
            winreg.HKEY_LOCAL_MACHINE,  # type: ignore[attr-defined]
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
        ) as chave:
            nome, _ = winreg.QueryValueEx(chave, "ProcessorNameString")  # type: ignore[attr-defined]
    except OSError:
        return []
    return [_item("Modelo da CPU", str(nome).strip())]


def _discos() -> list[dict[str, str]]:
    itens: list[dict[str, str]] = []
    if os.name == "nt":
        unidades = [f"{letra}:\\" for letra in "CDEFGHIJKLMNOPQRSTUVWXYZ" if Path(f"{letra}:\\").exists()]
    else:
        unidades = ["/"]
    for unidade in unidades[:8]:
        try:
            uso = shutil.disk_usage(unidade)
        except OSError:
            continue
        itens.append(
            _item(
                f"Disco {unidade}",
                f"{_gb(uso.free)} livres de {_gb(uso.total)}",
            )
        )
    return itens


def _gpu(rodar: Callable[[list[str]], tuple[int, str, str]]) -> tuple[list[dict[str, str]], str]:
    """GPU e o motivo quando não dá para ler. Nunca inventa modelo."""
    nvidia = shutil.which("nvidia-smi")
    if nvidia:
        try:
            codigo, saida, _erro = rodar(
                [nvidia, "--query-gpu=name,memory.total,temperature.gpu", "--format=csv,noheader"]
            )
        except AnatomiaError:
            codigo, saida = 1, ""
        linhas = [l.strip() for l in saida.splitlines() if l.strip()]
        if codigo == 0 and linhas:
            itens = []
            for indice, linha in enumerate(linhas[:4], start=1):
                partes = [p.strip() for p in linha.split(",")]
                nome = partes[0] if partes else "GPU NVIDIA"
                extra = " · ".join(p for p in partes[1:] if p)
                itens.append(_item(f"GPU {indice}", f"{nome}{' · ' + extra if extra else ''}"))
            return itens, "nvidia-smi"
    if os.name == "nt":
        script = (
            "Get-CimInstance Win32_VideoController | "
            "Select-Object -ExpandProperty Name"
        )
        try:
            codigo, saida, _erro = rodar(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script]
            )
        except AnatomiaError as exc:
            return [], f"O PowerShell não respondeu: {exc}"
        nomes = [l.strip() for l in saida.splitlines() if l.strip()]
        if codigo == 0 and nomes:
            return [_item(f"GPU {i}", nome) for i, nome in enumerate(nomes[:4], start=1)], "Win32_VideoController"
        return [], "O Windows não respondeu à consulta de vídeo (Win32_VideoController)."
    alvo = Path("/sys/class/drm")
    if alvo.is_dir():
        nomes = sorted(p.name for p in alvo.iterdir() if p.name.startswith("card") and "-" not in p.name)
        if nomes:
            return [_item("Placas de vídeo", ", ".join(nomes))], "/sys/class/drm"
    return [], "Este sistema não expõe o modelo da GPU por arquivo nem por comando."


def _temperatura(raiz_sys: Path, rodar: Callable[[list[str]], tuple[int, str, str]]) -> tuple[list[dict[str, str]], str]:
    """Temperatura de CPU/GPU — com a fonte e o motivo quando não há."""
    try:
        import psutil  # type: ignore[import-not-found]
    except ImportError:
        psutil = None  # type: ignore[assignment]
    if psutil is not None:
        try:
            sensores = psutil.sensors_temperatures()  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            sensores = {}
        itens = [
            _item(f"{nome} · {leitura.label or 'sensor'}", f"{leitura.current:.1f} °C".replace(".", ","))
            for nome, leituras in (sensores or {}).items()
            for leitura in leituras[:3]
            if getattr(leitura, "current", None)
        ]
        if itens:
            return itens, "psutil"
    zonas = raiz_sys / "class" / "thermal"
    if zonas.is_dir():
        itens = []
        for zona in sorted(zonas.glob("thermal_zone*"))[:8]:
            try:
                bruto = int((zona / "temp").read_text(encoding="utf-8").strip())
                tipo = (zona / "type").read_text(encoding="utf-8").strip()
            except (OSError, ValueError):
                continue
            itens.append(_item(tipo or zona.name, _temperatura_legivel(bruto)))
        if itens:
            return itens, "/sys/class/thermal"
    if os.name == "nt":
        # No Windows, o caminho honesto é o WMI térmico — que só existe quando o
        # firmware publica. Se vier vazio, é vazio, e a resposta diz por quê.
        script = (
            "Get-CimInstance -Namespace root/WMI -ClassName MSAcpi_ThermalZoneTemperature "
            "-ErrorAction SilentlyContinue | Select-Object -ExpandProperty CurrentTemperature"
        )
        try:
            codigo, saida, _erro = rodar(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script]
            )
        except AnatomiaError as exc:
            return [], f"O Windows não respondeu à consulta térmica: {exc}"
        valores = [l.strip() for l in saida.splitlines() if l.strip().isdigit()]
        if codigo == 0 and valores:
            itens = [
                _item(
                    f"Zona térmica {i}",
                    f"{(int(valor) / 10 - 273.15):.1f} °C".replace(".", ","),
                )
                for i, valor in enumerate(valores[:6], start=1)
            ]
            return itens, "MSAcpi_ThermalZoneTemperature"
        return [], (
            "Este Windows não publica temperatura por WMI (vários notebooks e placas não publicam). "
            "Para ler de verdade, o caminho é o LibreHardwareMonitor aberto em segundo plano."
        )
    return [], "Este sistema não tem sensor térmico legível por arquivo nem por comando."


def ler_local(
    *,
    raiz_proc: Path | None = None,
    raiz_sys: Path | None = None,
    rodar: Callable[[list[str]], tuple[int, str, str]] | None = None,
) -> dict[str, Any]:
    """Anatomia da máquina onde a API roda. Somente leitura."""
    raiz_proc = raiz_proc or Path("/proc")
    raiz_sys = raiz_sys or Path("/sys")
    executor = rodar or (lambda argumentos: _rodar(argumentos, timeout=12))
    windows = os.name == "nt"

    cpu = _cpu_windows() if windows else _cpu_linux(raiz_proc)
    if not cpu:
        cpu = [_item("Modelo da CPU", platform.processor() or platform.machine())]
    nucleos = os.cpu_count()
    if nucleos:
        cpu.append(_item("Núcleos lógicos", nucleos))

    memoria = _memoria_windows() if windows else _memoria_linux(raiz_proc)
    gpu, fonte_gpu = _gpu(executor)
    temperatura, fonte_temp = _temperatura(raiz_sys, executor)

    secoes = [
        _secao("sistema", "Sistema", [
            _item("Sistema", f"{platform.system()} {platform.release()}"),
            _item("Arquitetura", platform.machine()),
            _item("Python", platform.python_version()),
            _item("Máquina", platform.node()),
        ]),
        _secao("cpu", "Processador", cpu),
        _secao("memoria", "Memória", memoria),
        _secao("discos", "Discos", _discos()),
        _secao("gpu", "Vídeo", gpu or [_item("Situação", "não exposta")]),
        _secao(
            "temperatura",
            "Temperatura",
            temperatura or [_item("Situação", "não exposta")],
        ),
    ]
    limitacoes: list[str] = []
    if not gpu:
        limitacoes.append(f"GPU: {fonte_gpu}")
    if not temperatura:
        limitacoes.append(f"Temperatura: {fonte_temp}")
    if windows:
        limitacoes.append(
            "A leitura é da máquina que executa a API. Num contêiner ou noutro PC, os números são do contêiner."
        )
    return {
        "ok": True,
        "alvo": "local",
        "titulo": f"{platform.system()} · {platform.node()}",
        "lido_em": _agora(),
        "secoes": [s for s in secoes if s["itens"]],
        "limitacoes": limitacoes,
        "nao_faz": list(NAO_FAZ),
        "fontes": {"gpu": fonte_gpu, "temperatura": fonte_temp},
    }


# ---------------------------------------------------------------- android


def _exigir_android() -> None:
    if not celular.ligado():
        raise AnatomiaError(
            "A leitura do Android está desligada. Acrescente `set "
            f"{AMBIENTE_ANDROID}=1` no iniciar-jarvis.bat, feche e abra de novo. "
            "Sem isso, o JARVIS não fala com nenhum aparelho."
        )


def _adb() -> str:
    ferramentas = celular.ferramentas()
    caminho = ferramentas.get("adb") or ""
    if not caminho:
        raise AnatomiaError(
            "O `adb` não está instalado. Na aba Máquina, peça “Preparar celular” para baixar "
            "o platform-tools: ele vem do site oficial do Google e o JARVIS confere o hash."
        )
    return caminho


def aparelhos(*, rodar: Callable[[list[str]], tuple[int, str, str]] | None = None) -> list[dict[str, str]]:
    """Quem está na USB agora. Sem a variável ligada, devolve lista vazia."""
    if not celular.ligado():
        return []
    try:
        caminho = _adb()
    except AnatomiaError:
        return []
    executor = rodar or (lambda argumentos: _rodar(argumentos))
    codigo, saida, erro = executor([caminho, "devices", "-l"])
    if codigo != 0 and not saida:
        raise AnatomiaError(f"O adb não respondeu: {_cortar(erro, 400)}")
    return celular.parsear_dispositivos(saida)


def _propriedades(saida: str) -> dict[str, str]:
    """Lê `[chave]: [valor]` do `getprop`."""
    valores: dict[str, str] = {}
    for linha in (saida or "").splitlines():
        if not linha.startswith("["):
            continue
        if not linha.endswith("]"):
            # 0.93.0 — linha cortada no meio (o `_cortar` de 60 KB pode cair
            # dentro do valor). `rsplit` não acha o `]` final e devolve o resto
            # **truncado como se fosse o valor inteiro**: o relatório do dono
            # saiu com “SM-A346M” quando o modelo é “SM-A346M…” — e teria saído
            # “SM-A346” se o corte caísse dois caracteres antes. Truncado não é
            # resposta: a chave fica de fora e o fallback por comando resolve.
            continue
        try:
            chave, resto = linha[1:].split("]: [", 1)
            valor = resto.rsplit("]", 1)[0]
        except ValueError:
            continue
        valores[chave.strip()] = valor.strip()
    return valores


def _ler_bateria(saida: str) -> list[dict[str, str]]:
    campos: dict[str, str] = {}
    for linha in (saida or "").splitlines():
        if ":" not in linha:
            continue
        chave, valor = linha.split(":", 1)
        campos[chave.strip()] = valor.strip()
    itens: list[dict[str, str]] = []
    if "level" in campos and campos["level"].isdigit():
        itens.append(_item("Carga", f"{campos['level']}%"))
    if "temperature" in campos and campos["temperature"].lstrip("-").isdigit():
        itens.append(_item("Temperatura da bateria", _decimos_celsius(int(campos["temperature"]))))
    if "voltage" in campos and campos["voltage"].isdigit():
        itens.append(_item("Tensão", f"{int(campos['voltage']) / 1000:.2f} V".replace(".", ",")))
    if campos.get("status") in ROTULOS_ELETRICO:
        itens.append(_item("Estado", ROTULOS_ELETRICO[campos["status"]]))
    if campos.get("health") in SAUDE_BATERIA:
        itens.append(_item("Saúde", SAUDE_BATERIA[campos["health"]]))
    if campos.get("AC powered") == "true":
        itens.append(_item("Carregador", "conectado"))
    return itens


def _ler_meminfo(saida: str) -> list[dict[str, str]]:
    valores: dict[str, int] = {}
    for linha in (saida or "").splitlines():
        partes = linha.replace(":", " ").split()
        if len(partes) >= 2 and partes[1].isdigit():
            valores[partes[0]] = int(partes[1]) * 1024
    itens: list[dict[str, str]] = []
    if "MemTotal" in valores:
        itens.append(_item("Memória total", _gb(valores["MemTotal"])))
    if "MemAvailable" in valores:
        itens.append(_item("Disponível", _gb(valores["MemAvailable"])))
    if "SwapTotal" in valores and valores["SwapTotal"]:
        itens.append(_item("Swap/ZRAM", _gb(valores["SwapTotal"])))
    return itens


def _ler_discos(saida: str) -> list[dict[str, str]]:
    itens: list[dict[str, str]] = []
    for linha in (saida or "").splitlines()[1:]:
        partes = linha.split()
        if len(partes) < 6:
            continue
        ponto = partes[-1]
        if ponto not in {"/data", "/", "/storage/emulated", "/storage/emulated/0", "/system"}:
            continue
        tamanho = int(partes[1]) * 1024 if partes[1].isdigit() else 0
        livre = int(partes[3]) * 1024 if partes[3].isdigit() else 0
        if tamanho:
            itens.append(_item(f"{ponto}", f"{_gb(livre)} livres de {_gb(tamanho)}"))
    return itens


def _ler_cpuinfo(saida: str) -> list[dict[str, str]]:
    texto = saida or ""
    itens: list[dict[str, str]] = []
    nucleos = sum(1 for linha in texto.splitlines() if linha.lower().startswith("processor"))
    if nucleos:
        itens.append(_item("Núcleos", nucleos))
    for linha in texto.splitlines():
        chave = linha.split(":", 1)[0].strip().lower()
        if chave in {"hardware", "model name", "processor"} and ":" in linha:
            valor = linha.split(":", 1)[1].strip()
            if valor and not valor.isdigit() and not any(i["valor"] == valor for i in itens):
                itens.append(_item("Identificação", valor))
    return itens


def _ler_termico(saida: str) -> list[dict[str, str]]:
    itens: list[dict[str, str]] = []
    for linha in (saida or "").splitlines():
        if ":" not in linha:
            continue
        tipo, valor = linha.split(":", 1)
        valor = valor.strip()
        if not valor.lstrip("-").isdigit():
            continue
        numero = int(valor)
        celsius = numero / 1000 if abs(numero) > 1000 else float(numero)
        itens.append(_item(tipo.strip() or "sensor", f"{celsius:.1f} °C".replace(".", ",")))
    return itens


def ler_android(
    serial: str = "",
    *,
    rodar: Callable[[list[str]], tuple[int, str, str]] | None = None,
) -> dict[str, Any]:
    """Anatomia do Android plugado por USB. Só comandos de leitura."""
    _exigir_android()
    executor = rodar or (lambda argumentos: _rodar(argumentos))
    adb = _adb()

    alvo = serial.strip()
    if not alvo:
        conectados = aparelhos(rodar=executor)
        prontos = [a for a in conectados if a.get("estado") == "device"]
        if not prontos:
            if conectados:
                raise AnatomiaError(
                    "O aparelho está na USB, mas não autorizou este computador. "
                    "Desbloqueie a tela e toque em “Permitir” no aviso “Permitir depuração USB?”."
                )
            raise AnatomiaError(
                "Nenhum Android apareceu. Confira o cabo (tem de ser de dados, não só de carga), "
                "ligue a Depuração USB em Opções do desenvolvedor e aceite o aviso na tela."
            )
        alvo = prontos[0]["serial"]

    falhas: list[str] = []

    def ler(*argumentos: str) -> str:
        try:
            codigo, saida, erro = executor([adb, "-s", alvo, *argumentos])
        except AnatomiaError as exc:
            falhas.append(str(exc))
            return ""
        if codigo != 0 and not saida:
            falhas.append(_cortar(erro or f"“{' '.join(argumentos)}” falhou", 240))
            return ""
        return _cortar(saida)

    props = _propriedades(ler("shell", "getprop"))
    # 0.92.6 — o título vinha do `getprop` **cortado** em `MAX_SAIDA`. Num aparelho
    # com muitas propriedades (o Android 16 do dono tem centenas), a linha do
    # modelo cai depois do corte e o cabeçalho saía só "Android 16" — sem dizer
    # qual aparelho era. Três propriedades custam um comando; a leitura inteira
    # continua servindo à tabela de identidade.
    # `ro.product.model` entra sempre: é o único cujo truncamento muda o nome do
    # aparelho na tela. Os outros dois só quando faltam.
    for chave in ("ro.product.model", "ro.build.version.release", "ro.product.manufacturer"):
        if not props.get(chave):
            valor = ler("shell", "getprop", chave).strip()
            if valor:
                props[chave] = valor
    identidade = [_item(rotulo, props.get(chave, "")) for chave, rotulo in PROPS]
    titulo = " · ".join(
        p for p in (props.get("ro.product.model"), f"Android {props.get('ro.build.version.release', '')}".strip()) if p
    ) or "Android"

    bateria = _ler_bateria(ler("shell", "dumpsys", "battery"))
    memoria = _ler_meminfo(ler("shell", "cat", "/proc/meminfo"))
    cpu = _ler_cpuinfo(ler("shell", "cat", "/proc/cpuinfo"))
    discos = _ler_discos(ler("shell", "df", "-k"))
    particoes_saida = ler("shell", "cat", "/proc/partitions")
    particoes = [
        f"{linha.split()[3]} ({int(linha.split()[2]) // 1024} MB)"
        for linha in particoes_saida.splitlines()[1:]
        if len(linha.split()) >= 4 and linha.split()[3].startswith(("mmcblk", "sda", "sdd", "dm-", "nvme"))
    ]
    termico = _ler_termico(
        ler(
            "shell",
            "for z in /sys/class/thermal/thermal_zone*; do echo \"$(cat $z/type 2>/dev/null):$(cat $z/temp 2>/dev/null)\"; done",
        )
    )
    apps = [
        linha.strip().removeprefix("package:")
        for linha in ler("shell", "pm", "list", "packages", "-3").splitlines()
        if linha.strip().startswith("package:")
    ]
    total_apps = sum(
        1 for linha in ler("shell", "pm", "list", "packages").splitlines() if linha.strip().startswith("package:")
    )

    secoes = [
        _secao("identidade", "Identidade", identidade),
        _secao("bateria", "Bateria", bateria),
        _secao("cpu", "Processador", cpu),
        _secao("memoria", "Memória", memoria),
        _secao("discos", "Armazenamento", discos),
        _secao(
            "particoes",
            "Partições vistas",
            [_item(f"{len(particoes)} partições", ", ".join(particoes[:10]))] if particoes else [],
        ),
        _secao("termico", "Sensores térmicos", termico),
        _secao(
            "apps",
            "Aplicativos instalados",
            [
                _item("Total instalado", total_apps or "não respondeu"),
                _item("Fora da loja (terceiros)", len(apps) or "0"),
                _item("Amostra", ", ".join(apps[:15])),
            ],
        ),
    ]

    limitacoes = list(dict.fromkeys(falhas))
    if not termico:
        limitacoes.append(
            "Sem temperatura no aparelho: muitos Androids escondem `/sys/class/thermal` de quem não é root. "
            "Isso é desenho do sistema, não falha do JARVIS."
        )
    limitacoes.append(
        "A leitura é do que o Android publica sem root: não inclui memória de outros apps nem partição criptografada."
    )
    return {
        "ok": True,
        "alvo": "android",
        "serial": alvo,
        "titulo": titulo,
        "lido_em": _agora(),
        "secoes": [s for s in secoes if s["itens"]],
        "limitacoes": limitacoes,
        "nao_faz": list(NAO_FAZ),
        # 0.92.7 — o mesmo `getprop` que já foi lido, sem rótulo no meio. Quem
        # decide degrau não pode depender de texto de tela (era assim que o
        # `verified_boot` chegava vazio e o bootloader parecia sempre travado).
        "propriedades": {chave: props.get(chave, "") for chave, _ in PROPS},
    }


# ---------------------------------------------------------------- roku


def _ip_valido(ip: str) -> str:
    limpo = (ip or "").strip()
    try:
        endereco = ipaddress.ip_address(limpo)
    except ValueError as exc:
        raise AnatomiaError(
            f"“{limpo}” não é um IP. Na TV, veja Ajustes → Rede → Sobre para achar o endereço (algo como 192.168.0.23)."
        ) from exc
    if endereco.is_loopback or endereco.is_link_local or endereco.is_multicast:
        raise AnatomiaError("Esse endereço não é de aparelho na rede: laço local, link-local e multicast não servem.")
    if not endereco.is_private:
        raise AnatomiaError("Só endereço da própria rede (192.168.x.x, 10.x.x.x ou 172.16–31.x.x) é aceito aqui.")
    return str(endereco)


def _buscar(url: str, timeout: int = TIMEOUT_REDE) -> str:
    pedido = Request(url, headers={"User-Agent": "JARVIS-anatomia", "Accept": "text/xml, */*"})
    try:
        with urlopen(pedido, timeout=timeout) as resposta:  # noqa: S310 - endereço privado validado antes
            return resposta.read(400_000).decode("utf-8", errors="replace")
    except HTTPError as exc:
        raise AnatomiaError(f"A TV respondeu {exc.code} em {url}. O ECP pode estar desligado.") from exc
    except URLError as exc:
        raise AnatomiaError(
            f"A TV em {url} não respondeu ({exc.reason}). Confira o IP, se ela está na mesma rede Wi-Fi "
            "e se o controle por app está ligado em Ajustes → Sistema → Controle por app."
        ) from exc
    except (socket.timeout, TimeoutError) as exc:
        raise AnatomiaError(f"A TV não respondeu em {timeout}s. Ela está ligada e na mesma rede?") from exc


def _texto_xml(elemento: ET.Element, tag: str) -> str:
    achado = elemento.find(tag)
    return (achado.text or "").strip() if achado is not None else ""


def _segundos_humanos(bruto: str) -> str:
    if not bruto.strip().isdigit():
        return bruto
    total = int(bruto)
    dias, resto = divmod(total, 86400)
    horas, resto = divmod(resto, 3600)
    minutos = resto // 60
    partes = [f"{dias}d" if dias else "", f"{horas}h" if horas else "", f"{minutos}min" if minutos else ""]
    return " ".join(p for p in partes if p) or f"{total}s"


def _porta_aberta(ip: str, porta: int, timeout: float = 0.6) -> bool:
    try:
        with socket.create_connection((ip, porta), timeout=timeout):
            return True
    except OSError:
        return False


def ler_roku(ip: str, *, buscar: Callable[[str], str] | None = None, portas: Callable[[str, int], bool] | None = None) -> dict[str, Any]:
    """Anatomia de uma TV Roku pela rede (ECP, porta 8060). Somente GET."""
    if os.getenv(AMBIENTE_REDE, "0").strip() != "1":
        raise AnatomiaError(
            "A leitura pela rede está desligada. Acrescente `set "
            f"{AMBIENTE_REDE}=1` no iniciar-jarvis.bat, feche e abra de novo."
        )
    endereco = _ip_valido(ip)
    buscar = buscar or _buscar
    base = f"http://{endereco}:{PORTA_ROKU}"

    info_xml = buscar(f"{base}/query/device-info")
    try:
        info = ET.fromstring(info_xml)
    except ET.ParseError as exc:
        raise AnatomiaError(
            "A porta 8060 respondeu, mas não com XML de Roku. Ou é outro aparelho nesse IP, "
            "ou é uma TV que não usa ECP."
        ) from exc
    if info.tag != "device-info":
        raise AnatomiaError(
            f"O aparelho em {endereco} respondeu “{info.tag}”, não “device-info”. Não parece um Roku."
        )

    identidade = [
        _item("Nome na rede", _texto_xml(info, "friendly-device-name")),
        _item("Modelo", _texto_xml(info, "model-name")),
        _item("Número do modelo", _texto_xml(info, "model-number")),
        _item("Fabricante", _texto_xml(info, "vendor-name")),
        _item("Roku OS", _texto_xml(info, "software-version")),
        _item("Build", _texto_xml(info, "software-build")),
        _item("Série", _texto_xml(info, "serial-number")),
        _item("MAC", _texto_xml(info, "wifi-mac") or _texto_xml(info, "ethernet-mac")),
        _item("Resolução", _texto_xml(info, "display-type")),
        _item("Tipo de rede", _texto_xml(info, "network-type")),
        _item("Ligada há", _segundos_humanos(_texto_xml(info, "uptime"))),
        _item("Energia", _texto_xml(info, "power-mode")),
    ]

    aplicativos: list[dict[str, str]] = []
    try:
        apps = ET.fromstring(buscar(f"{base}/query/apps"))
        for app in apps.findall("app")[:20]:
            nome = (app.text or "").strip()
            versao = app.get("version", "")
            aplicativos.append(_item(nome or app.get("id", "app"), f"versão {versao}" if versao else ""))
    except AnatomiaError:
        pass

    ativo = ""
    try:
        ativo_xml = ET.fromstring(buscar(f"{base}/query/active-app"))
        app = ativo_xml.find("app")
        if app is not None:
            ativo = (app.text or "").strip() or app.get("id", "")
    except AnatomiaError:
        pass

    portas = portas or _porta_aberta
    dev = portas(endereco, PORTA_ROKU_DEV)
    secoes = [
        _secao("identidade", "Identidade", identidade),
        _secao(
            "apps",
            "Canais instalados",
            ([_item(f"{len(aplicativos)} canais", ", ".join(i["rotulo"] for i in aplicativos[:12]))] if aplicativos else []),
        ),
        _secao("agora", "Agora na tela", [_item("Canal ativo", ativo)] if ativo else []),
        _secao(
            "portas",
            "Portas",
            [
                _item(f"{PORTA_ROKU} (ECP, HTTP)", "aberta — é por aqui que o JARVIS lê"),
                _item(f"{PORTA_ROKU_DEV} (logs de dev)", "aberta" if dev else "fechada"),
            ],
        ),
    ]
    limitacoes = [
        "O Roku não publica temperatura de CPU no ECP. As telas secretas do controle mostram, mas só na TV.",
        "Não há leitura de arquivos do sistema pela rede: o Roku OS não expõe shell, e o firmware é assinado.",
        "Não aperta botão nenhum: controle remoto pela rede existe no ECP, mas muda o estado da TV — este módulo não faz.",
    ]
    if not aplicativos:
        limitacoes.append("A lista de canais não respondeu desta vez; o resto da leitura vale.")
    return {
        "ok": True,
        "alvo": "roku",
        "ip": endereco,
        "titulo": _texto_xml(info, "friendly-device-name") or f"Roku em {endereco}",
        "lido_em": _agora(),
        "secoes": [s for s in secoes if s["itens"]],
        "limitacoes": limitacoes,
        "nao_faz": list(NAO_FAZ),
    }


# ---------------------------------------------------------------- fontes


def fontes(*, rodar: Callable[[list[str]], tuple[int, str, str]] | None = None) -> dict[str, Any]:
    """O que dá para ler agora, com o motivo quando não dá. Não lê nada pesado."""
    executor = rodar or (lambda argumentos: _rodar(argumentos))
    ferramentas = celular.ferramentas()
    android_ligado = bool(ferramentas.get("ligado"))
    rede_ligada = os.getenv(AMBIENTE_REDE, "0").strip() == "1"
    conectados: list[dict[str, str]] = []
    aviso_android = ""
    if android_ligado and ferramentas.get("adb"):
        try:
            conectados = aparelhos(rodar=executor)
        except AnatomiaError as exc:
            aviso_android = str(exc)
    elif not android_ligado:
        aviso_android = f"Ligado com `{AMBIENTE_ANDROID}=1` no iniciar-jarvis.bat."
    else:
        aviso_android = "O `adb` não está instalado: use “Preparar celular” na aba Máquina."

    return {
        "ok": True,
        "alvos": [
            {
                "id": "local",
                "titulo": "Este computador",
                "disponivel": True,
                "motivo": "",
            },
            {
                "id": "android",
                "titulo": "Android por USB",
                "disponivel": android_ligado and bool(ferramentas.get("adb")),
                "motivo": aviso_android,
                "aparelhos": conectados,
            },
            {
                "id": "roku",
                "titulo": "TV Roku pela rede",
                "disponivel": rede_ligada,
                "motivo": "" if rede_ligada else f"Ligado com `{AMBIENTE_REDE}=1` no iniciar-jarvis.bat.",
            },
        ],
        "flags": {AMBIENTE_ANDROID: android_ligado, AMBIENTE_REDE: rede_ligada},
        "lido_em": _agora(),
    }
