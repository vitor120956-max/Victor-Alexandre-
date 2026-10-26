"""Diz por que o PC está lento — sem instalar nada, sem internet e sem admin.

A dúvida é sempre a mesma: "foi o programa que instalei ou o que já estava
rodando?". Este script responde com número, não com palpite:

1. **máquina** — versão do Windows, RAM total e livre, núcleos e modelo da CPU;
2. **disco** — quanto sobra, e se ele é mecânico (HDD) ou SSD;
3. **quem está comendo** — os dez processos que mais gastam memória e os que
   mais gastam CPU no momento;
4. **os suspeitos de sempre** — Google Drive, Steam, Chrome e o próprio JARVIS,
   com o quanto cada um ocupa;
5. **o que abre junto com o Windows** — a lista de inicialização;
6. **veredito** — frases prontas do tipo "a memória está em 92%: o gargalo é
   RAM", tiradas dos números medidos.

No fim grava `relatorio-lentidao.txt` ao lado do projeto, para você mandar de
volta sem copiar a tela.

Uso:
    diagnostico-lento.bat                        (duplo clique no Windows)
    .venv\\Scripts\\python diagnostico.py
    .venv\\Scripts\\python diagnostico.py --json   (dados crus, para conferir)
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
RELATORIO = RAIZ / "relatorio-lentidao.txt"
LIMITE_SAIDA = 200_000

SUSPEITOS = {
    "googledrivefs": "Google Drive (sincronização)",
    "googlecrashhandler": "Google Crash Handler",
    "steam": "Steam",
    "steamwebhelper": "Steam (interface)",
    "chrome": "Chrome",
    "msedge": "Edge",
    "firefox": "Firefox",
    "python": "Python (API do JARVIS)",
    "uvicorn": "API do JARVIS",
    "node": "Node (interface em modo dev)",
    "onedrive": "OneDrive",
    "dropbox": "Dropbox",
    "antimalware": "Antivírus (Windows Defender)",
    "msmpeng": "Antivírus (Windows Defender)",
    "searchindexer": "Indexador de busca do Windows",
    "svchost": "Serviços do Windows",
}


@dataclass
class Processo:
    nome: str
    memoria_mb: float = 0.0
    cpu_pct: float = 0.0


@dataclass
class Dados:
    sistema: str = ""
    maquina: str = ""
    cpu: str = ""
    nucleos: int = 0
    ram_total_gb: float = 0.0
    ram_livre_gb: float = 0.0
    ram_uso_pct: float = 0.0
    discos: list[dict[str, object]] = field(default_factory=list)
    discos_fisicos: list[dict[str, object]] = field(default_factory=list)
    processos: list[Processo] = field(default_factory=list)
    por_nome: dict[str, Processo] = field(default_factory=dict)
    inicializacao: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    def para_json(self) -> dict[str, object]:
        return {
            **asdict(self),
            "processos": [asdict(item) for item in self.processos],
            "por_nome": {chave: asdict(valor) for chave, valor in self.por_nome.items()},
        }


# ------------------------------------------------------------------ utilidades

def _rodar(comando: list[str], timeout: int = 25) -> str:
    """Roda um comando do Windows e devolve a saída; nunca levanta exceção."""
    try:
        processo = subprocess.run(
            comando,
            capture_output=True,
            timeout=timeout,
            check=False,
            text=True,
            encoding="cp850",
            errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return (processo.stdout or "")[:LIMITE_SAIDA]


def _mb(bytes_: float) -> float:
    return round(bytes_ / (1024 * 1024), 1)


def _gb(bytes_: float) -> float:
    return round(bytes_ / (1024 * 1024 * 1024), 2)


# --------------------------------------------------------------------- memória

class _MemoriaWindows(ctypes.Structure):
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


def memoria() -> tuple[float, float, float]:
    """(total GB, livre GB, uso %) — Windows por API; Linux por /proc."""
    if sys.platform == "win32":
        try:
            estado = _MemoriaWindows()
            estado.dwLength = ctypes.sizeof(_MemoriaWindows)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(estado)):
                total = float(estado.ullTotalPhys)
                livre = float(estado.ullAvailPhys)
                return _gb(total), _gb(livre), round(100 - (livre / total * 100), 1)
        except Exception:
            pass
    try:
        info = {}
        for linha in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            chave, _, resto = linha.partition(":")
            if chave in {"MemTotal", "MemAvailable"}:
                info[chave] = int(resto.strip().split()[0]) * 1024
        total = float(info.get("MemTotal", 0))
        livre = float(info.get("MemAvailable", 0))
        if total:
            return _gb(total), _gb(livre), round(100 - (livre / total * 100), 1)
    except OSError:
        pass
    return 0.0, 0.0, 0.0


# ---------------------------------------------------------------------- discos

def discos() -> list[dict[str, object]]:
    itens: list[dict[str, object]] = []
    if sys.platform == "win32":
        letras = [f"{letra}:\\" for letra in "CDEFGH"]
    else:
        letras = ["/"]
    for letra in letras:
        try:
            uso = shutil.disk_usage(letra)
        except OSError:
            continue
        total = float(uso.total)
        livre = float(uso.free)
        itens.append(
            {
                "unidade": letra,
                "total_gb": _gb(total),
                "livre_gb": _gb(livre),
                "livre_pct": round(livre / total * 100, 1) if total else 0.0,
            }
        )
    return itens


def discos_fisicos() -> list[dict[str, object]]:
    """Modelo e tipo do disco. `MediaType` do wmic não distingue SSD; o nome sim."""
    if sys.platform != "win32":
        return []
    bruto = _rodar(["wmic", "diskdrive", "get", "Model,MediaType,Size", "/format:csv"])
    itens: list[dict[str, object]] = []
    for linha in bruto.splitlines():
        partes = [parte.strip() for parte in linha.split(",")]
        if len(partes) < 5 or partes[0].upper() == "NODE" or not partes[0]:
            continue
        modelo, tipo, tamanho = partes[2], partes[3], partes[4]
        if not modelo:
            continue
        texto = modelo.upper()
        mecanico = "SSD" not in texto and "NVME" not in texto and "SOLID" not in texto
        itens.append(
            {
                "modelo": modelo,
                "tipo": tipo or "?",
                "tamanho_gb": _gb(float(tamanho)) if tamanho.isdigit() else 0.0,
                "parece_ssd": not mecanico,
            }
        )
    return itens


# ------------------------------------------------------------------ processos

def parse_tasklist(texto: str) -> list[Processo]:
    """`tasklist /fo csv /nh` → nome e memória em MB."""
    processos: list[Processo] = []
    for linha in (texto or "").splitlines():
        if not linha.startswith('"'):
            continue
        partes = [parte.strip('"') for parte in linha.split('","')]
        if len(partes) < 5:
            continue
        nome = partes[0]
        mem = partes[4].replace(".", "").replace(",", "").replace(" K", "").strip()
        try:
            megabytes = float(mem) / 1024
        except ValueError:
            continue
        processos.append(Processo(nome=nome, memoria_mb=round(megabytes, 1)))
    return processos


def parse_cpu(texto: str) -> dict[str, float]:
    """`Win32_PerfFormattedData_PerfProc_Process` → CPU % somada por nome."""
    por_nome: dict[str, float] = {}
    for linha in (texto or "").splitlines():
        partes = linha.split()
        if len(partes) < 2:
            continue
        nome, valor = partes[0], partes[-1]
        if not valor.isdigit():
            continue
        base = nome.split("#")[0]
        if base in {"Name", "_Total"}:
            continue
        por_nome[base] = por_nome.get(base, 0.0) + float(valor)
    return por_nome


def base_nome(nome: str) -> str:
    """`Chrome.exe` e `chrome` são o mesmo processo para quem olha a lista."""
    return nome.strip().lower().removesuffix(".exe")


def juntar(processos: list[Processo], cpu: dict[str, float]) -> tuple[list[Processo], dict[str, Processo]]:
    """Aplica a CPU medida e agrupa processos iguais (chrome, chrome#1...)."""
    agrupado: dict[str, Processo] = {}
    for processo in processos:
        chave = base_nome(processo.nome)
        if chave in agrupado:
            agrupado[chave].memoria_mb = round(agrupado[chave].memoria_mb + processo.memoria_mb, 1)
        else:
            agrupado[chave] = Processo(nome=processo.nome, memoria_mb=processo.memoria_mb)
    normalizada = {base_nome(nome): valor for nome, valor in cpu.items()}
    for chave, processo in agrupado.items():
        processo.cpu_pct = round(normalizada.get(chave, 0.0), 1)
    lista = sorted(agrupado.values(), key=lambda item: item.memoria_mb, reverse=True)
    return lista, agrupado


def inicializacao() -> list[str]:
    if sys.platform != "win32":
        return []
    bruto = _rodar(["wmic", "startup", "get", "Caption,Command", "/format:csv"])
    itens: list[str] = []
    for linha in bruto.splitlines():
        partes = [parte.strip() for parte in linha.split(",")]
        if len(partes) < 3 or not partes[1]:
            continue
        legenda = partes[1]
        if legenda.lower() == "caption":
            continue
        itens.append(legenda[:90])
    return sorted(set(itens))


def coletar() -> Dados:
    dados = Dados()
    dados.sistema = platform.platform()
    dados.maquina = platform.machine()
    dados.nucleos = os.cpu_count() or 0
    dados.cpu = platform.processor() or ""
    if sys.platform == "win32" and not dados.cpu:
        dados.cpu = _rodar(["wmic", "cpu", "get", "Name"]).replace("Name", "").strip()

    total, livre, uso = memoria()
    dados.ram_total_gb, dados.ram_livre_gb, dados.ram_uso_pct = total, livre, uso

    dados.discos = discos()
    dados.discos_fisicos = discos_fisicos()

    if sys.platform == "win32":
        processos = parse_tasklist(_rodar(["tasklist", "/fo", "csv", "/nh"]))
        cpu = parse_cpu(
            _rodar(
                [
                    "wmic",
                    "path",
                    "Win32_PerfFormattedData_PerfProc_Process",
                    "get",
                    "Name,PercentProcessorTime",
                ]
            )
        )
        dados.processos, dados.por_nome = juntar(processos, cpu)
        dados.inicializacao = inicializacao()
    else:
        dados.avisos.append("Fora do Windows, memória de processo e inicialização não são medidas.")
        dados.processos, dados.por_nome = juntar([], {})

    if not dados.processos:
        dados.avisos.append("Não consegui listar processos (tasklist indisponível).")
    if not dados.inicializacao and sys.platform == "win32":
        dados.avisos.append("Não consegui ler a inicialização do Windows (wmic indisponível).")
    return dados


# --------------------------------------------------------------------- veredito

def _soma(dados: Dados, *nomes: str) -> float:
    total = 0.0
    for nome in nomes:
        processo = dados.por_nome.get(nome)
        if processo is not None:
            total += processo.memoria_mb
    return round(total, 1)


def veredito(dados: Dados) -> list[str]:
    """Frases curtas tiradas dos números — a ordem é a da importância."""
    frases: list[str] = []

    if dados.ram_total_gb and dados.ram_uso_pct >= 85:
        frases.append(
            f"A memória está em {dados.ram_uso_pct:.0f}% de {dados.ram_total_gb:.1f} GB: "
            "o gargalo é RAM. Fechar programa resolve mais que qualquer ajuste."
        )
    elif dados.ram_total_gb:
        frases.append(
            f"Memória em {dados.ram_uso_pct:.0f}% de {dados.ram_total_gb:.1f} GB — "
            "ela não é o gargalo agora."
        )

    if any(disco.get("parece_ssd") is False for disco in dados.discos_fisicos):
        frases.append(
            "O disco é mecânico (HDD): no Windows 10 isso pesa mais que a CPU. "
            "Se o disco fica em 100% no Gerenciador de Tarefas, trocar por SSD é o que resolve."
        )

    if dados.discos:
        principal = dados.discos[0]
        if float(principal.get("livre_pct") or 0) < 10:
            frases.append(
                f"A unidade {principal['unidade']} está com {principal['livre_pct']}% livre. "
                "Abaixo de 10% o Windows fica lento para gravar arquivo temporário."
            )

    drive = _soma(dados, "googledrivefs", "googlecrashhandler", "googledrive")
    if drive >= 150:
        frases.append(
            f"O Google Drive está usando {drive:.0f} MB agora. Ele sincroniza e indexa em "
            "segundo plano: pausar a sincronização por 10 minutos é o teste mais rápido."
        )
    elif drive > 0:
        frases.append(f"O Google Drive está rodando e usando {drive:.0f} MB — pouco para culpar ele.")

    steam = _soma(dados, "steam", "steamwebhelper", "steamservice")
    if steam >= 100:
        frases.append(
            f"A Steam está aberta e usando {steam:.0f} MB. Se ela abre junto com o Windows, "
            "desligue isso em Steam → Configurações → Interface."
        )

    navegador = _soma(dados, "chrome", "msedge", "firefox", "opera", "brave")
    if navegador >= 500:
        frases.append(
            f"O navegador responde por {navegador:.0f} MB. Cada aba é um processo: "
            "fechar abas paradas devolve memória na hora."
        )

    jarvis = _soma(dados, "python", "uvicorn", "node")
    if jarvis >= 100:
        frases.append(
            f"O JARVIS (Python) está rodando e usando {jarvis:.0f} MB. "
            "Ele não roda escondido: só ocupa enquanto a janela está aberta."
        )
    elif jarvis > 0:
        frases.append(f"O JARVIS está rodando e usando {jarvis:.0f} MB — não é ele.")

    if len(dados.inicializacao) > 10:
        frases.append(
            f"{len(dados.inicializacao)} programas abrem junto com o Windows. "
            "Cada um come um pouco de RAM e disco logo na subida."
        )

    if not frases:
        frases.append("Não medi nada — rode este script no Windows para ter o retrato da máquina.")
    return frases


# ------------------------------------------------------------------- relatório

def formatar(dados: Dados) -> str:
    linhas: list[str] = ["JARVIS — por que o PC está lento", "=" * 34, ""]
    linhas.append(f"Sistema: {dados.sistema}")
    linhas.append(f"CPU: {dados.cpu or '?'} · {dados.nucleos} núcleos")
    linhas.append(f"Memória: {dados.ram_livre_gb:.1f} GB livres de {dados.ram_total_gb:.1f} GB ({dados.ram_uso_pct:.0f}% em uso)")
    for disco in dados.discos:
        linhas.append(
            f"Disco {disco['unidade']}: {disco['livre_gb']} GB livres de {disco['total_gb']} GB "
            f"({disco['livre_pct']}%)"
        )
    for fisico in dados.discos_fisicos:
        tipo = "SSD" if fisico.get("parece_ssd") else "HDD (mecânico)"
        linhas.append(f"Disco físico: {fisico['modelo']} — {tipo}")

    linhas += ["", "Quem mais ocupa memória agora", "-" * 34]
    for processo in dados.processos[:10]:
        cpu = f" · {processo.cpu_pct:.0f}% CPU" if processo.cpu_pct else ""
        linhas.append(f"{processo.memoria_mb:8.0f} MB  {processo.nome}{cpu}")
    if not dados.processos:
        linhas.append("(não medido)")

    presentes = [
        (rotulo, dados.por_nome[chave])
        for chave, rotulo in SUSPEITOS.items()
        if chave in dados.por_nome
    ]
    if presentes:
        linhas += ["", "Os suspeitos de sempre", "-" * 34]
        for rotulo, processo in presentes:
            linhas.append(f"{processo.memoria_mb:8.0f} MB  {rotulo} ({processo.nome})")

    if dados.inicializacao:
        linhas += ["", f"Abrem junto com o Windows ({len(dados.inicializacao)})", "-" * 34]
        linhas += [f"- {item}" for item in dados.inicializacao[:15]]

    linhas += ["", "Veredito", "-" * 34]
    linhas += [f"- {frase}" for frase in veredito(dados)]

    if dados.avisos:
        linhas += ["", "Avisos", "-" * 34]
        linhas += [f"- {aviso}" for aviso in dados.avisos]

    linhas += ["", "Medido por `diagnostico.py` — nada foi instalado, alterado ou enviado.", ""]
    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diz por que o PC está lento, com número.")
    parser.add_argument("--json", action="store_true", help="mostra os dados crus")
    parser.add_argument("--saida", default=str(RELATORIO), help="arquivo do relatório")
    parser.add_argument("--segundos", type=float, default=0.0, help="espera antes de medir CPU")
    argumentos = parser.parse_args(argv)

    if argumentos.segundos:
        time.sleep(argumentos.segundos)

    dados = coletar()
    if argumentos.json:
        print(json.dumps(dados.para_json(), ensure_ascii=False, indent=2))
        return 0

    texto = formatar(dados)
    print(texto)
    try:
        Path(argumentos.saida).write_text(texto, encoding="utf-8", newline="\r\n")
        print(f"Relatório gravado em {argumentos.saida}")
    except OSError as exc:
        print(f"Não consegui gravar o relatório: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
