"""Acesso real ao host onde a API roda: disco, pastas, drivers, Bluetooth, rede e instalação.

Diferente das camadas anteriores, esta lê a máquina de verdade. Isso muda o
contrato: aqui existe escrita (quarentena de download e livro de auditoria) e
existe execução (instalador com allowlist fechada). Por isso três guardas
separam leitura de efeito colateral:

- **token de host** — arquivo `storage/host-token.txt` gerado no primeiro uso e
  exibido no terminal; sem ele nenhuma operação responde;
- **rede** — desligada por padrão (`JARVIS_HOST_REDE=1` liga), com bloqueio de
  endereço privado, laço local e link-local para a API não virar proxy;
- **instalação** — desligada por padrão (`JARVIS_HOST_INSTALAR=1` liga), em dois
  passos: `planejar` mostra o comando exato, `executar` exige o token de
  confirmação devolvido pelo plano.

O que **não** existe aqui: shell livre. O executor só roda uma lista fechada de
instaladores, com argumentos fixos no código. Nenhum texto do usuário entra em
uma linha de comando. Também não existe despejo de conteúdo de arquivo: a
enumeração de pastas devolve nome, tipo, tamanho e data — nunca bytes.

O aviso que a interface repete: os dados são da máquina que executa a API. Num
contêiner, é o contêiner — não o PC de quem abriu a página.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import platform
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen

from .review import common, finalize, finding

VERSAO = "0.30.0"

PROJETO = Path(__file__).resolve().parent.parent
STORAGE = PROJETO / "storage"
TOKEN_ARQUIVO = STORAGE / "host-token.txt"
QUARENTENA = STORAGE / "host-downloads"
AUDITORIA = STORAGE / "host-audit.jsonl"

AMBIENTE_REDE = "JARVIS_HOST_REDE"
AMBIENTE_INSTALAR = "JARVIS_HOST_INSTALAR"

MAX_TEXTO = 1_800_000
MAX_ROWS = 200
MAX_ENTRADAS = 2_000
MAX_PROFUNDIDADE = 6
MODOS = ("lite", "full", "ultra")

# Rede
MAX_DOWNLOAD = 256 * 1024 * 1024
MAX_PAGINA = 2 * 1024 * 1024
TIMEOUT_REDE = 20
AGENTE = "jarvis-host/0.30 (+local)"
DOMINIOS_BLOQUEADOS = (".local", ".internal", ".localdomain")
REDES_PRIVADAS = (
    "10.",
    "127.",
    "0.",
    "169.254.",
    "172.16.",
    "172.17.",
    "172.18.",
    "172.19.",
    "172.20.",
    "172.21.",
    "172.22.",
    "172.23.",
    "172.24.",
    "172.25.",
    "172.26.",
    "172.27.",
    "172.28.",
    "172.29.",
    "172.30.",
    "172.31.",
    "192.168.",
)
PASTAS_PROTEGIDAS = (
    ".ssh",
    ".gnupg",
    ".aws",
    ".azure",
    ".kube",
    ".docker",
    ".config/gcloud",
    "cofre",
    "AppData/Roaming/Microsoft/Credentials",
)
SUFIXOS_PROTEGIDOS = (
    ".key",
    ".pem",
    ".pfx",
    ".p12",
    ".kdbx",
    ".ovpn",
    "credentials",
    "id_rsa",
    "id_ed25519",
    ".env",
    "cookies",
)

# Instalação: allowlist fechada. Nenhum argumento vem do usuário além dos
# interruptores silenciosos abaixo.
GERENCIADORES = {
    "msi": ("msiexec", ("/i", "{arquivo}", "/qb", "/norestart")),
    "deb": ("dpkg", ("-i", "{arquivo}")),
    "rpm": ("rpm", ("-Uvh", "{arquivo}")),
    "exe": ("{arquivo}", ()),
    "pip": ("{python}", ("-m", "pip", "install", "{pacote}")),
    "npm": ("npm", ("install", "{pacote}")),
}
TIPOS = {
    ".msi": "msi",
    ".deb": "deb",
    ".rpm": "rpm",
    ".exe": "exe",
    ".msix": "msi",
    ".appimage": "appimage",
}
CONFIRMACAO_TTL = 600
_CONFIRMACAO: dict[str, dict[str, Any]] = {}


class SistemaError(ValueError):
    """Entrada inválida ou operação recusada por guarda."""


def _modo(valor: str) -> str:
    modo = (valor or "full").strip().lower()
    if modo not in MODOS:
        raise SistemaError(f"Modo inválido: use {', '.join(MODOS)}.")
    return modo


# ---------------------------------------------------------------------------
# Guardas
# ---------------------------------------------------------------------------


def token_host() -> str:
    """Token do modo host, criado no primeiro uso e guardado fora do Git."""
    try:
        if TOKEN_ARQUIVO.exists():
            token = TOKEN_ARQUIVO.read_text(encoding="utf-8").strip()
            if token:
                return token
        STORAGE.mkdir(parents=True, exist_ok=True)
        token = secrets.token_urlsafe(24)
        TOKEN_ARQUIVO.write_text(token + "\n", encoding="utf-8")
        try:
            TOKEN_ARQUIVO.chmod(0o600)
        except OSError:
            pass
        return token
    except OSError:
        return ""


def _autorizado(autorizacao: str) -> tuple[bool, str]:
    esperado = token_host()
    if not esperado:
        return False, "Não foi possível preparar o token de host em storage/host-token.txt."
    if not autorizacao.strip():
        return False, (
            "Modo host exige o token de storage/host-token.txt. "
            "Ele aparece no terminal quando a API sobe e nunca vai para o Git."
        )
    if not hmac.compare_digest(autorizacao.strip(), esperado):
        return False, "Token de host inválido. Confira o valor em storage/host-token.txt."
    return True, ""


def capacidades() -> dict[str, Any]:
    """O que está ligado agora, sem revelar o token."""
    return {
        "token_configurado": bool(token_host()),
        "rede": os.environ.get(AMBIENTE_REDE, "0") == "1",
        "instalar": os.environ.get(AMBIENTE_INSTALAR, "0") == "1",
        "shell_livre": False,
        "quarentena": str(QUARENTENA),
        "auditoria": str(AUDITORIA),
    }


def _exigir(autorizacao: str) -> None:
    ok, motivo = _autorizado(autorizacao)
    if not ok:
        raise SistemaError(motivo)


def _exigir_rede(autorizacao: str) -> None:
    _exigir(autorizacao)
    if os.environ.get(AMBIENTE_REDE, "0") != "1":
        raise SistemaError(
            "Rede desligada. Suba a API com JARVIS_HOST_REDE=1 para liberar busca, leitura de página e download."
        )


def _exigir_instalar(autorizacao: str) -> None:
    _exigir_rede(autorizacao)
    if os.environ.get(AMBIENTE_INSTALAR, "0") != "1":
        raise SistemaError(
            "Instalação desligada. Suba a API com JARVIS_HOST_INSTALAR=1 depois de revisar o plano do instalador."
        )


# ---------------------------------------------------------------------------
# Ambiente
# ---------------------------------------------------------------------------


def _ler_arquivo(caminho: str, limite: int = 200_000) -> str:
    try:
        with open(caminho, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read(limite)
    except OSError:
        return ""


def _memoria() -> dict[str, Any]:
    texto = _ler_arquivo("/proc/meminfo")
    if not texto:
        return {"disponivel": False, "fonte": "sem /proc/meminfo"}
    valores: dict[str, int] = {}
    for linha in texto.splitlines():
        partes = linha.split(":")
        if len(partes) != 2:
            continue
        numero = re.match(r"\s*(\d+)", partes[1])
        if numero:
            valores[partes[0]] = int(numero.group(1)) * 1024
    total = valores.get("MemTotal", 0)
    livre = valores.get("MemAvailable", valores.get("MemFree", 0))
    return {
        "disponivel": True,
        "total": total,
        "livre": livre,
        "emUso": max(total - livre, 0),
        "swapTotal": valores.get("SwapTotal", 0),
        "swapLivre": valores.get("SwapFree", 0),
        "fonte": "/proc/meminfo",
    }


def _cpu() -> dict[str, Any]:
    modelo = ""
    texto = _ler_arquivo("/proc/cpuinfo", 60_000)
    achado = re.search(r"^model name\s*:\s*(.+)$", texto, re.MULTILINE)
    if achado:
        modelo = achado.group(1).strip()
    elif platform.system() == "Windows":
        modelo = platform.processor()
    nucleos = os.cpu_count() or 0
    carga: list[float] = []
    try:
        carga = [round(valor, 2) for valor in os.getloadavg()]
    except (OSError, AttributeError):
        carga = []
    return {"modelo": modelo or "não informado", "nucleos": nucleos, "carga": carga}


def _container() -> dict[str, Any]:
    evidencias: list[str] = []
    if Path("/.dockerenv").exists():
        evidencias.append("/.dockerenv presente")
    if Path("/run/.containerenv").exists():
        evidencias.append("/run/.containerenv presente")
    cgroup = _ler_arquivo("/proc/1/cgroup", 20_000)
    if re.search(r"docker|containerd|kubepods|lxc|garden", cgroup):
        evidencias.append("/proc/1/cgroup cita runtime de contêiner")
    if os.environ.get("KUBERNETES_SERVICE_HOST"):
        evidencias.append("KUBERNETES_SERVICE_HOST definido")
    if os.environ.get("container"):
        evidencias.append("variável container definida")
    # Em host físico, /proc/1 comm costuma ser o init do sistema.
    init = _ler_arquivo("/proc/1/comm", 200).strip()
    if init and init not in {"systemd", "init", "launchd", "runit", "s6-svscan"}:
        evidencias.append(f"processo 1 é {init}")
    return {"provavel": bool(evidencias), "evidencias": evidencias}


def _uptime() -> dict[str, Any]:
    texto = _ler_arquivo("/proc/uptime", 200)
    if not texto:
        return {"disponivel": False}
    segundos = int(float(texto.split()[0]))
    return {
        "disponivel": True,
        "segundos": segundos,
        "legivel": f"{segundos // 86400}d {segundos % 86400 // 3600}h {segundos % 3600 // 60}m",
    }


def ambiente(*, detalhe: str = "full", modo: str = "full", autorizacao: str = "") -> dict[str, Any]:
    """Descreve a máquina que executa a API e o que está liberado nela."""
    modo = _modo(modo)
    _exigir(autorizacao)
    sistema = platform.system() or "desconhecido"
    cont = _container()
    memoria = _memoria()
    cpu = _cpu()
    uptime = _uptime()
    rows = [
        {"chave": "Sistema", "valor": f"{sistema} {platform.release()}"},
        {"chave": "Arquitetura", "valor": platform.machine() or "não informada"},
        {"chave": "Máquina", "valor": platform.node() or "não informada"},
        {"chave": "Usuário", "valor": os.environ.get("USER") or os.environ.get("USERNAME") or "não informado"},
        {"chave": "Python", "valor": platform.python_version()},
        {"chave": "Processo", "valor": str(os.getpid())},
        {"chave": "Diretório", "valor": str(PROJETO)},
        {"chave": "Núcleos", "valor": str(cpu["nucleos"])},
        {"chave": "Processador", "valor": cpu["modelo"]},
        {
            "chave": "Memória",
            "valor": f"{_gb(memoria.get('total', 0))} total, {_gb(memoria.get('livre', 0))} livre"
            if memoria.get("disponivel")
            else "indisponível nesta plataforma",
        },
        {"chave": "Ligado há", "valor": uptime.get("legivel", "indisponível") if uptime.get("disponivel") else "indisponível"},
        {"chave": "Contêiner", "valor": "provável" if cont["provavel"] else "não detectado"},
    ]
    if detalhe == "full":
        for item in cont["evidencias"]:
            rows.append({"chave": "Evidência de contêiner", "valor": item})
        rows.append({"chave": "Token de host", "valor": str(TOKEN_ARQUIVO)})

    findings: list[dict[str, Any]] = []
    if cont["provavel"]:
        findings.append(
            finding(
                "must",
                "origem",
                "Os dados são do contêiner, não do seu PC",
                "ambiente",
                "A API está dentro de um contêiner e lê o sistema de arquivos dele.",
                "Tudo o que esta camada devolver sobre disco, pastas e drivers descreve o contêiner, "
                "não a máquina do navegador. Confundir os dois leva a diagnóstico errado.",
                "Rode a API na máquina que você quer inspecionar (`npm run dev` no seu PC) e recarregue.",
                "Você vai ajustar um disco que não é o seu.",
            )
        )
    caps = capacidades()
    if not caps["rede"]:
        findings.append(
            finding(
                "should",
                "guarda",
                "Rede desligada por padrão",
                AMBIENTE_REDE,
                "Busca, leitura de página e download estão bloqueados.",
                "Sem rede não há como procurar programa nem baixar instalador; a camada declara o limite em vez de fingir.",
                f"Suba a API com {AMBIENTE_REDE}=1 quando quiser liberar a saída para a internet.",
                "Você fica só com a leitura local.",
            )
        )
    if not caps["instalar"]:
        findings.append(
            finding(
                "nice",
                "guarda",
                "Instalação desligada por padrão",
                AMBIENTE_INSTALAR,
                "O passo `executar` da skill de instalação está recusando.",
                "Executar binário de terceiro é o efeito colateral mais forte da camada e por isso é opt-in explícito.",
                f"Suba a API com {AMBIENTE_INSTALAR}=1 depois de conferir o plano em `instalar.planejar`.",
                "Você continua podendo baixar e conferir o hash, sem instalar.",
            )
        )
    if cont["provavel"]:
        limitations = [
            "Memória e carga vêm de /proc; em Windows ficam indisponíveis em vez de estimadas.",
            "Contêiner detectado: disco, pastas e drivers são os do contêiner.",
            "Nenhum comando de shell é executado por esta operação.",
        ]
    else:
        limitations = [
            "Memória e carga vêm de /proc; em Windows ficam indisponíveis em vez de estimadas.",
            "Nenhum comando de shell é executado por esta operação.",
        ]
    findings, counts, verdict, questions = finalize(findings, modo, [
        "Esta é a máquina que você quer inspecionar?",
        "O resultado veio de um contêiner ou do host físico?",
    ])
    return common(
        analysis="ambiente",
        mode=modo,
        title="Ambiente de execução",
        summary=[
            f"A API roda em **{sistema}** ({platform.machine() or 'arquitetura não informada'}) "
            f"com {cpu['nucleos']} núcleos.",
            f"Contêiner: **{'provável' if cont['provavel'] else 'não detectado'}**. "
            f"Rede: **{'ligada' if caps['rede'] else 'desligada'}**. "
            f"Instalação: **{'ligada' if caps['instalar'] else 'desligada'}**.",
        ],
        findings=findings,
        counts=counts,
        verdict=verdict,
        questions=questions,
        rows=rows,
        metrics={
            "nucleos": cpu["nucleos"],
            "memoriaTotal": memoria.get("total", 0),
            "memoriaLivre": memoria.get("livre", 0),
            "container": cont["provavel"],
            "rede": caps["rede"],
            "instalar": caps["instalar"],
        },
        limitations=limitations,
    )


def _gb(valor: int) -> str:
    if not valor:
        return "0 GB"
    return f"{valor / (1024 ** 3):.1f} GB"


def _pct(parte: int, total: int) -> int:
    if total <= 0:
        return 0
    return int(round(parte * 100 / total))


# ---------------------------------------------------------------------------
# Disco
# ---------------------------------------------------------------------------


# Sistemas de arquivos que nunca representam "espaço em disco" para o usuário.
PSEUDO_FS = {
    "proc",
    "sysfs",
    "devpts",
    "cgroup",
    "cgroup2",
    "securityfs",
    "debugfs",
    "tracefs",
    "mqueue",
    "hugetlbfs",
    "configfs",
    "fusectl",
    "binfmt_misc",
    "nsfs",
    "pstore",
    "bpf",
    "autofs",
    "selinuxfs",
    "ramfs",
    "rpc_pipefs",
    "devtmpfs",
    "squashfs",
    "efivarfs",
}
# Voláteis: aparecem na listagem, mas nunca geram alerta de disco cheio.
VOLATIL_FS = {"tmpfs", "overlay", "shm"}


def _montagens_posix() -> list[dict[str, str]]:
    texto = _ler_arquivo("/proc/mounts", 200_000)
    if not texto:
        return []
    itens: list[dict[str, str]] = []
    vistos: set[int] = set()
    for linha in texto.splitlines():
        partes = linha.split()
        if len(partes) < 3:
            continue
        dispositivo, ponto, tipo = partes[0], partes[1], partes[2]
        if tipo in PSEUDO_FS:
            continue
        if ponto.startswith("/run/credentials"):
            continue
        try:
            info = os.stat(ponto)
        except OSError:
            continue
        # Bind mount do mesmo dispositivo não vira linha nova.
        if info.st_dev in vistos:
            continue
        vistos.add(info.st_dev)
        itens.append(
            {
                "dispositivo": dispositivo,
                "ponto": ponto,
                "tipo": tipo,
                "volatil": tipo in VOLATIL_FS,
            }
        )
    return itens


def _unidades_windows() -> list[dict[str, str]]:
    itens: list[dict[str, str]] = []
    for letra in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        raiz = f"{letra}:\\"
        if Path(raiz).exists():
            itens.append({"dispositivo": raiz, "ponto": raiz, "tipo": "volume"})
    return itens


def disco(
    *,
    caminhos: str = "",
    minimo: int = 0,
    modo: str = "full",
    autorizacao: str = "",
) -> dict[str, Any]:
    """Mede espaço total, usado e livre por unidade, sem varrer conteúdo."""
    modo = _modo(modo)
    _exigir(autorizacao)
    pedidos = [item.strip() for item in caminhos.split(",") if item.strip()]
    if pedidos:
        alvos = [{"dispositivo": "", "ponto": item, "tipo": "informado"} for item in pedidos]
    elif platform.system() == "Windows":
        alvos = _unidades_windows()
    else:
        alvos = _montagens_posix()
    rows: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    total_geral = livre_geral = 0
    minimo_geral = 100
    for alvo in alvos[:MAX_ROWS]:
        ponto = alvo["ponto"]
        volatil = bool(alvo.get("volatil"))
        try:
            uso = shutil.disk_usage(ponto)
        except OSError as exc:
            if pedidos:
                findings.append(
                    finding(
                        "should",
                        "leitura",
                        "Caminho sem leitura",
                        ponto,
                        f"Não foi possível medir o espaço ({type(exc).__name__}).",
                        "Sem permissão ou caminho inexistente, o número não pode ser calculado.",
                        "Confira se o caminho existe e se o processo tem permissão.",
                        "A unidade fica fora do total.",
                    )
                )
            continue
        if uso.total <= 0:
            continue
        livre_pct = _pct(uso.free, uso.total)
        total_geral += uso.total
        livre_geral += uso.free
        if not volatil:
            minimo_geral = min(minimo_geral, livre_pct)
        rows.append(
            {
                "unidade": ponto,
                "tipo": alvo["tipo"],
                "dispositivo": alvo["dispositivo"],
                "total": uso.total,
                "usado": uso.used,
                "livre": uso.free,
                "livrePct": livre_pct,
                "volatil": volatil,
                "legivel": f"{_gb(uso.total)} total, {_gb(uso.free)} livre",
            }
        )
        if volatil:
            continue
        if livre_pct <= 5:
            findings.append(
                finding(
                    "must",
                    "espaco",
                    "Disco praticamente cheio",
                    ponto,
                    f"Restam {livre_pct}% ({_gb(uso.free)}) de {_gb(uso.total)}.",
                    "Abaixo de 5% o sistema operacional falha em gravar log, atualizar pacote e abrir programa.",
                    "Libere espaço antes de qualquer instalação nova.",
                    "A próxima atualização do sistema pode falhar.",
                )
            )
        elif livre_pct <= 15:
            findings.append(
                finding(
                    "should",
                    "espaco",
                    "Pouco espaço livre",
                    ponto,
                    f"Restam {livre_pct}% ({_gb(uso.free)}) de {_gb(uso.total)}.",
                    "Instalar um programa grande nessa unidade tende a ser recusado pelo instalador.",
                    "Reserve pelo menos 20% livres ou instale em outra unidade.",
                    "A instalação para no meio por falta de espaço.",
                )
            )
    if minimo > 0:
        rows = [linha for linha in rows if linha["livrePct"] >= minimo]
    if not rows:
        findings.append(
            finding(
                "must",
                "leitura",
                "Nenhuma unidade medida",
                caminhos or "automático",
                "A coleta não conseguiu medir nenhuma unidade.",
                "Sem unidade não há como dizer se cabe uma instalação.",
                "Informe os caminhos manualmente ou confira a permissão do processo.",
                "A resposta fica sem o dado principal.",
            )
        )
    findings, counts, verdict, questions = finalize(findings, modo, [
        "Qual unidade recebe os programas que você instala?",
        "O espaço livre inclui a lixeira e os pontos de restauração?",
    ])
    return common(
        analysis="disco",
        mode=modo,
        title="Espaço em disco",
        summary=[
            f"{len(rows)} unidade(s) medida(s), com {_gb(total_geral)} no total e {_gb(livre_geral)} livres.",
            f"A unidade mais apertada tem **{minimo_geral if rows else 0}%** livre.",
        ],
        findings=findings,
        counts=counts,
        verdict=verdict,
        questions=questions,
        rows=rows,
        metrics={
            "unidades": len(rows),
            "total": total_geral,
            "livre": livre_geral,
            "usado": max(total_geral - livre_geral, 0),
            "livrePct": _pct(livre_geral, total_geral),
            "menorLivrePct": minimo_geral if rows else 0,
        },
        limitations=[
            "O tamanho de uma pasta grande não entra aqui: medir árvore inteira pode levar minutos.",
            "Cotas de contêiner podem reportar o disco do host hospedeiro, não o limite do cgroup.",
            "Nenhum arquivo é apagado ou movido.",
        ],
    )


# ---------------------------------------------------------------------------
# Pastas
# ---------------------------------------------------------------------------


def _protegido(caminho: Path) -> bool:
    texto = caminho.as_posix()
    baixo = texto.lower()
    if any(f"/{pasta}/" in f"/{baixo}/" or baixo.endswith(f"/{pasta}") for pasta in PASTAS_PROTEGIDAS):
        return True
    nome = caminho.name.lower()
    return any(nome == sufixo or nome.endswith(sufixo) for sufixo in SUFIXOS_PROTEGIDOS)


def pastas(
    *,
    raiz: str = ".",
    profundidade: int = 2,
    limite: int = 300,
    incluir_ocultos: bool = False,
    modo: str = "full",
    autorizacao: str = "",
) -> dict[str, Any]:
    """Enumera nomes, tipos, tamanhos e datas — nunca o conteúdo dos arquivos."""
    modo = _modo(modo)
    _exigir(autorizacao)
    profundidade = max(0, min(int(profundidade), MAX_PROFUNDIDADE))
    limite = max(1, min(int(limite), MAX_ENTRADAS))
    base = Path(raiz).expanduser()
    try:
        base = base.resolve()
    except OSError as exc:
        raise SistemaError(f"Caminho inválido: {raiz}.") from exc
    if not base.exists():
        raise SistemaError(f"Caminho não existe nesta máquina: {raiz}.")
    if not base.is_dir():
        raise SistemaError(f"Não é uma pasta: {raiz}.")
    rows: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    truncado = False
    negados = 0
    bytes_total = 0

    def visitar(pasta: Path, nivel: int) -> None:
        nonlocal truncado, negados, bytes_total
        if truncado:
            return
        try:
            entradas = sorted(os.scandir(pasta), key=lambda item: (not _eh_pasta(item), item.name.lower()))
        except PermissionError:
            negados += 1
            return
        except OSError:
            negados += 1
            return
        for entrada in entradas:
            if len(rows) >= limite:
                truncado = True
                return
            nome = entrada.name
            oculto = nome.startswith(".")
            if oculto and not incluir_ocultos:
                continue
            caminho = pasta / nome
            protegido = _protegido(caminho)
            try:
                info = entrada.stat(follow_symlinks=False)
            except OSError:
                negados += 1
                continue
            if entrada.is_symlink():
                tipo = "link"
            elif entrada.is_dir(follow_symlinks=False):
                tipo = "pasta"
            else:
                tipo = "arquivo"
            tamanho = 0 if (tipo == "pasta" or protegido) else info.st_size
            bytes_total += tamanho
            if protegido:
                findings.append(
                    finding(
                        "nice",
                        "privacidade",
                        "Caminho sensível apenas listado",
                        str(caminho),
                        "Pasta ou arquivo de credencial foi reconhecido pelo nome.",
                        "Conteúdo de cofre, chave e token não é lido nem medido por esta camada.",
                        "Se precisar do dado, abra o arquivo fora do JARVIS.",
                        "O tamanho aparece como zero para não vazar metadado.",
                    )
                )
            rows.append(
                {
                    "caminho": str(caminho),
                    "nome": nome,
                    "tipo": tipo,
                    "bytes": tamanho,
                    "modificado": datetime.fromtimestamp(info.st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
                    "protegido": protegido,
                    "nivel": nivel,
                }
            )
            if tipo == "pasta" and nivel < profundidade:
                visitar(caminho, nivel + 1)

    visitar(base, 1)
    if truncado:
        findings.append(
            finding(
                "should",
                "limite",
                "Listagem truncada",
                str(base),
                f"A varredura parou em {limite} entradas.",
                "Árvore maior que o limite esconde justamente a pasta que se procurava.",
                "Reduza a profundidade ou aponte para a subpasta específica.",
                "A resposta parece completa e não é.",
            )
        )
    if negados:
        findings.append(
            finding(
                "should",
                "leitura",
                "Subpastas sem permissão",
                str(base),
                f"{negados} pasta(s) não puderam ser lidas.",
                "Sem permissão o inventário fica incompleto sem avisar.",
                "Rode com um usuário que tenha acesso ou escolha a subpasta certa.",
                "Você conclui que o arquivo não existe quando ele está lá.",
            )
        )
    if not rows:
        findings.append(
            finding(
                "nice",
                "vazio",
                "Pasta vazia ou só com itens ocultos",
                str(base),
                "Nenhuma entrada visível foi encontrada.",
                "Sem entradas não há o que inventariar.",
                "Marque `incluir_ocultos` se a pasta guarda configuração.",
                "A ausência de arquivo pode ser só ausência de visibilidade.",
            )
        )
    pastas_n = sum(1 for linha in rows if linha["tipo"] == "pasta")
    findings, counts, verdict, questions = finalize(findings, modo, [
        "Você quer o tamanho somado das subpastas ou só o nome delas?",
        "Arquivos ocultos entram no inventário?",
    ])
    return common(
        analysis="pastas",
        mode=modo,
        title="Inventário de pastas",
        summary=[
            f"{len(rows)} entrada(s) em **{base}**, {pastas_n} pasta(s) e {len(rows) - pastas_n} arquivo(s).",
            f"Tamanho somado dos arquivos listados: **{_gb(bytes_total)}**"
            + (" — listagem truncada." if truncado else "."),
        ],
        findings=findings,
        counts=counts,
        verdict=verdict,
        questions=questions,
        rows=rows,
        metrics={
            "entradas": len(rows),
            "pastas": pastas_n,
            "arquivos": len(rows) - pastas_n,
            "bytes": bytes_total,
            "truncado": truncado,
            "negados": negados,
            "profundidade": profundidade,
        },
        limitations=[
            "Só nomes, tipos, tamanhos e datas: nenhum byte de conteúdo é lido.",
            "O tamanho de uma pasta é zero; somar a árvore é uma varredura separada e mais lenta.",
            "Links simbólicos são listados e não seguidos.",
            "Cofre, chave e token são reconhecidos pelo nome e listados sem tamanho.",
        ],
    )


def _eh_pasta(entrada: os.DirEntry[str]) -> bool:
    try:
        return entrada.is_dir(follow_symlinks=False)
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Drivers
# ---------------------------------------------------------------------------


def _rodar(comando: list[str], timeout: int = 20) -> tuple[int, str, str]:
    """Executa apenas comandos fixos do código, nunca texto do usuário."""
    try:
        concluido = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            check=False,
        )
        return concluido.returncode, concluido.stdout[:MAX_TEXTO], concluido.stderr[:20_000]
    except FileNotFoundError:
        return 127, "", f"comando não encontrado: {comando[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"tempo esgotado em {timeout}s"
    except OSError as exc:
        return 126, "", f"falha ao executar: {type(exc).__name__}"


def _modulos_linux() -> list[dict[str, Any]]:
    texto = _ler_arquivo("/proc/modules", 1_000_000)
    itens: list[dict[str, Any]] = []
    for linha in texto.splitlines():
        partes = linha.split()
        if len(partes) < 6:
            continue
        nome = partes[0]
        versao = ""
        try:
            versao = Path(f"/sys/module/{nome}/version").read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            versao = ""
        itens.append(
            {
                "nome": nome,
                "versao": versao or "sem versão declarada",
                "bytes": int(partes[1]) if partes[1].isdigit() else 0,
                "usadoPor": int(partes[2]) if partes[2].isdigit() else 0,
                "dependencias": partes[3].strip(",") if partes[3] != "-" else "",
                "estado": partes[4] if partes[4] != "-" else "live",
                "fonte": "/proc/modules",
            }
        )
    return itens


def _drivers_windows() -> tuple[list[dict[str, Any]], str]:
    script = (
        "Get-CimInstance Win32_PnPSignedDriver | "
        "Select-Object DeviceName,DriverVersion,DriverProviderName,DriverDate,IsSigned | "
        "ConvertTo-Json -Compress -Depth 3"
    )
    codigo, saida, erro = _rodar(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], timeout=30)
    if codigo != 0 or not saida.strip():
        return [], erro.strip() or "PowerShell não respondeu."
    try:
        dados = json.loads(saida)
    except json.JSONDecodeError:
        return [], "saída do PowerShell não é JSON."
    if isinstance(dados, dict):
        dados = [dados]
    itens: list[dict[str, Any]] = []
    for item in dados:
        if not isinstance(item, dict):
            continue
        itens.append(
            {
                "nome": str(item.get("DeviceName") or "dispositivo sem nome"),
                "versao": str(item.get("DriverVersion") or "sem versão"),
                "fornecedor": str(item.get("DriverProviderName") or "não informado"),
                "data": str(item.get("DriverDate") or ""),
                "assinado": bool(item.get("IsSigned")),
                "fonte": "Win32_PnPSignedDriver",
            }
        )
    return itens, ""


def drivers(
    *,
    filtro: str = "",
    classe: str = "",
    limite: int = 120,
    modo: str = "full",
    autorizacao: str = "",
) -> dict[str, Any]:
    """Lista drivers e módulos carregados, com assinatura quando a plataforma informa."""
    modo = _modo(modo)
    _exigir(autorizacao)
    limite = max(1, min(int(limite), MAX_ROWS))
    sistema = platform.system()
    erro = ""
    if sistema == "Linux":
        itens = _modulos_linux()
        plataforma_driver = "/proc/modules"
    elif sistema == "Windows":
        itens, erro = _drivers_windows()
        plataforma_driver = "Win32_PnPSignedDriver"
    else:
        itens = []
        plataforma_driver = f"sem fonte para {sistema}"
    termo = (filtro or "").strip().lower()
    classe_baixa = (classe or "").strip().lower()
    if termo:
        itens = [item for item in itens if termo in item["nome"].lower()]
    if classe_baixa and sistema == "Windows":
        itens = [item for item in itens if classe_baixa in item["nome"].lower()]
    rows = itens[:limite]
    findings: list[dict[str, Any]] = []
    if erro:
        findings.append(
            finding(
                "should",
                "leitura",
                "Fonte de drivers indisponível",
                plataforma_driver,
                erro[:200],
                "Sem a fonte, a lista sai vazia por falha e não por ausência de driver.",
                "Confira se o PowerShell está no PATH e se a política de execução permite consulta CIM.",
                "Você conclui que o driver não existe quando ele só não foi listado.",
            )
        )
    sem_versao = [item for item in rows if item.get("versao") in {"", "sem versão declarada"}]
    if sem_versao:
        findings.append(
            finding(
                "nice",
                "versao",
                "Driver sem versão declarada",
                sem_versao[0]["nome"],
                f"{len(sem_versao)} de {len(rows)} itens não informam versão no módulo.",
                "Sem versão não há como comparar com a versão atual do fabricante.",
                "Consulte o site do fabricante pelo nome do dispositivo.",
                "Você não sabe se o driver está velho.",
            )
        )
    nao_assinado = [item for item in rows if item.get("assinado") is False]
    if nao_assinado:
        findings.append(
            finding(
                "should",
                "assinatura",
                "Driver sem assinatura digital",
                nao_assinado[0]["nome"],
                f"{len(nao_assinado)} driver(s) sem assinatura válida.",
                "Driver não assinado pode ser adulterado e é recusado por versões recentes do Windows.",
                "Baixe o driver no site do fabricante e reinstale.",
                "O dispositivo pode deixar de funcionar depois de uma atualização.",
            )
        )
    if not rows and not erro:
        findings.append(
            finding(
                "nice",
                "vazio",
                "Nenhum driver listado",
                plataforma_driver,
                "A fonte respondeu, mas não devolveu item com esse filtro.",
                "Lista vazia pode ser filtro restritivo ou ambiente sem dispositivos físicos.",
                "Rode sem filtro para ver o inventário completo.",
                "Você procura um problema de driver onde não há driver.",
            )
        )
    findings, counts, verdict, questions = finalize(findings, modo, [
        "O dispositivo com problema aparece nesta lista?",
        "O driver veio do fabricante ou do Windows Update?",
    ])
    return common(
        analysis="drivers",
        mode=modo,
        title="Drivers e módulos",
        summary=[
            f"{len(rows)} item(ns) listados a partir de **{plataforma_driver}**.",
            f"{len(nao_assinado)} sem assinatura e {len(sem_versao)} sem versão declarada.",
        ],
        findings=findings,
        counts=counts,
        verdict=verdict,
        questions=questions,
        rows=rows,
        metrics={
            "itens": len(rows),
            "total": len(itens),
            "semVersao": len(sem_versao),
            "naoAssinados": len(nao_assinado),
            "plataforma": sistema,
            "fonte": plataforma_driver,
        },
        limitations=[
            "Linux lista módulos do kernel, não dispositivos PnP: um driver embutido no kernel não aparece.",
            "Windows depende do PowerShell e do provedor CIM disponíveis.",
            "Nenhum driver é baixado, substituído ou reinstalado por esta operação.",
        ],
    )


# ---------------------------------------------------------------------------
# Bluetooth
# ---------------------------------------------------------------------------


def _adaptadores_linux() -> list[dict[str, Any]]:
    base = Path("/sys/class/bluetooth")
    if not base.exists():
        return []
    itens: list[dict[str, Any]] = []
    for entrada in sorted(base.iterdir()):
        item: dict[str, Any] = {"nome": entrada.name, "tipo": "adaptador"}
        for campo, arquivo in (("endereco", "address"), ("ligado", "rfkill")):
            try:
                item[campo] = (entrada / arquivo).read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                item[campo] = ""
        try:
            item["fabricante"] = (entrada / "manufacturer").read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            item["fabricante"] = ""
        itens.append(item)
    return itens


def _emparelhados_linux() -> list[dict[str, Any]]:
    base = Path("/var/lib/bluetooth")
    if not base.exists():
        return []
    itens: list[dict[str, Any]] = []
    for adaptador in sorted(base.iterdir()):
        if not adaptador.is_dir():
            continue
        for dispositivo in sorted(adaptador.iterdir()):
            info = dispositivo / "info"
            if not info.exists():
                continue
            texto = _ler_arquivo(str(info), 20_000)
            dados = {
                "adaptador": adaptador.name,
                "mac": dispositivo.name,
                "nome": "",
                "confiavel": False,
                "conectado": False,
            }
            for linha in texto.splitlines():
                if linha.startswith("Name="):
                    dados["nome"] = linha.split("=", 1)[1].strip()
                elif linha.startswith("Trusted="):
                    dados["confiavel"] = linha.split("=", 1)[1].strip().lower() == "true"
            itens.append(dados)
    return itens


def _bluetooth_windows() -> tuple[list[dict[str, Any]], str]:
    script = (
        "Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue | "
        "Select-Object FriendlyName,Status,InstanceId | ConvertTo-Json -Compress -Depth 3"
    )
    codigo, saida, erro = _rodar(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], timeout=25)
    if codigo != 0:
        return [], erro.strip() or "PowerShell não respondeu."
    if not saida.strip():
        return [], ""
    try:
        dados = json.loads(saida)
    except json.JSONDecodeError:
        return [], "saída do PowerShell não é JSON."
    if isinstance(dados, dict):
        dados = [dados]
    itens = []
    for item in dados:
        if not isinstance(item, dict):
            continue
        itens.append(
            {
                "nome": str(item.get("FriendlyName") or "dispositivo sem nome"),
                "tipo": "adaptador" if "USB" in str(item.get("InstanceId", "")) else "dispositivo",
                "estado": str(item.get("Status") or ""),
                "id": str(item.get("InstanceId") or ""),
            }
        )
    return itens, ""


def bluetooth(
    *,
    filtro: str = "",
    modo: str = "full",
    autorizacao: str = "",
) -> dict[str, Any]:
    """Lista adaptadores e dispositivos Bluetooth emparelhados, sem emparelhar nada."""
    modo = _modo(modo)
    _exigir(autorizacao)
    sistema = platform.system()
    erro = ""
    if sistema == "Linux":
        adaptadores = _adaptadores_linux()
        emparelhados = _emparelhados_linux()
        fonte = "/sys/class/bluetooth e /var/lib/bluetooth"
        itens = adaptadores + emparelhados
    elif sistema == "Windows":
        itens, erro = _bluetooth_windows()
        adaptadores = [item for item in itens if item.get("tipo") == "adaptador"]
        emparelhados = [item for item in itens if item.get("tipo") != "adaptador"]
        fonte = "Get-PnpDevice -Class Bluetooth"
    else:
        itens, adaptadores, emparelhados = [], [], []
        fonte = f"sem fonte para {sistema}"
    termo = (filtro or "").strip().lower()
    if termo:
        itens = [item for item in itens if termo in str(item.get("nome", "")).lower()]
    findings: list[dict[str, Any]] = []
    if not adaptadores and not erro:
        findings.append(
            finding(
                "must",
                "adaptador",
                "Nenhum adaptador Bluetooth encontrado",
                fonte,
                "O sistema não expõe rádio Bluetooth.",
                "Sem rádio não existe programa que faça o fone funcionar: o Windows precisa do hardware, "
                "não de um aplicativo para parear.",
                "Confira se o PC tem Bluetooth: no Windows, Gerenciador de Dispositivos → Bluetooth; "
                "em desktop sem rádio, use um adaptador USB Bluetooth 5.x.",
                "Você vai instalar software para resolver um problema de hardware.",
            )
        )
    if not emparelhados and adaptadores:
        findings.append(
            finding(
                "should",
                "pareamento",
                "Adaptador presente, nenhum dispositivo pareado",
                fonte,
                f"{len(adaptadores)} adaptador(es) sem dispositivo emparelhado.",
                "O fone só aparece depois do modo de emparelhamento e do pareamento concluído.",
                "Coloque o fone em modo de emparelhamento (LED piscando rápido) e pareie em "
                "Configurações → Bluetooth e dispositivos.",
                "O fone não aparece na lista de saída de áudio.",
            )
        )
    for item in adaptadores:
        if str(item.get("estado", "")).lower() in {"disabled", "erro", "error"}:
            findings.append(
                finding(
                    "must",
                    "adaptador",
                    "Adaptador desligado ou com erro",
                    str(item.get("nome", "")),
                    f"Estado reportado: {item.get('estado')}.",
                    "Adaptador desligado não anuncia nem pareia.",
                    "Ative o Bluetooth e, se persistir, atualize o driver do adaptador.",
                    "Nenhum fone vai conectar enquanto o rádio estiver desligado.",
                )
            )
    if erro:
        findings.append(
            finding(
                "should",
                "leitura",
                "Consulta Bluetooth indisponível",
                fonte,
                erro[:200],
                "Sem a consulta, lista vazia significa falha e não ausência de rádio.",
                "Verifique o serviço de Bluetooth do Windows e o acesso ao PowerShell.",
                "Você conclui que o PC não tem Bluetooth quando ele pode ter.",
            )
        )
    findings, counts, verdict, questions = finalize(findings, modo, [
        "O fone aparece no modo de emparelhamento em outro aparelho?",
        "O PC é desktop sem rádio Bluetooth ou notebook com rádio embutido?",
    ])
    return common(
        analysis="bluetooth",
        mode=modo,
        title="Bluetooth",
        summary=[
            f"{len(adaptadores)} adaptador(es) e {len(emparelhados)} dispositivo(s) pareado(s).",
            "Fonte: **" + fonte + "**.",
        ],
        findings=findings,
        counts=counts,
        verdict=verdict,
        questions=questions,
        rows=itens[:MAX_ROWS],
        metrics={
            "adaptadores": len(adaptadores),
            "emparelhados": len(emparelhados),
            "total": len(itens),
            "plataforma": sistema,
        },
        limitations=[
            "Lista o que o sistema já conhece: não inicia varredura, não pareia e não conecta.",
            "No Linux, a pasta de emparelhados pode exigir permissão de root e vir vazia.",
            "Qualidade de áudio, codec e perfil A2DP não são medidos aqui.",
        ],
    )


# ---------------------------------------------------------------------------
# Rede
# ---------------------------------------------------------------------------


def _url_segura(url: str) -> str:
    limpa = (url or "").strip()
    if not limpa:
        raise SistemaError("Informe a URL.")
    partes = urlparse(limpa)
    if partes.scheme not in {"http", "https"}:
        raise SistemaError("Só http e https são aceitos.")
    host = (partes.hostname or "").lower()
    if not host:
        raise SistemaError("URL sem host.")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(DOMINIOS_BLOQUEADOS):
        raise SistemaError("Endereço local bloqueado: a API não fala com a máquina onde roda.")
    if re.fullmatch(r"[\d.]+", host) and host.startswith(REDES_PRIVADAS):
        raise SistemaError("Endereço de rede privada bloqueado.")
    try:
        resolvidos = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except OSError as exc:
        raise SistemaError(f"Host não resolve: {host}.") from exc
    for endereco in resolvidos:
        if endereco.startswith(REDES_PRIVADAS) or endereco in {"::1", "::"}:
            raise SistemaError("O host resolve para rede privada; acesso bloqueado.")
    return limpa


def _baixar_texto(url: str, limite: int | None = None) -> tuple[str, str, int]:
    limite = limite or MAX_PAGINA
    pedido = Request(url, headers={"User-Agent": AGENTE, "Accept": "text/html,application/xhtml+xml"})
    try:
        with urlopen(pedido, timeout=TIMEOUT_REDE) as resposta:
            tipo = resposta.headers.get("content-type", "")
            dados = resposta.read(limite + 1)
            codigo = resposta.status
    except HTTPError as exc:
        raise SistemaError(f"O servidor respondeu {exc.code} para {url}.") from exc
    except (URLError, OSError) as exc:
        raise SistemaError(f"Falha de rede ao abrir {url}: {type(exc).__name__}.") from exc
    if len(dados) > limite:
        raise SistemaError(f"Página maior que {limite} bytes; recusada para não estourar memória.")
    codificacao = "utf-8"
    achado = re.search(r"charset=([\w-]+)", tipo)
    if achado:
        codificacao = achado.group(1)
    try:
        texto = dados.decode(codificacao, errors="replace")
    except LookupError:
        texto = dados.decode("utf-8", errors="replace")
    return texto, tipo, codigo


def _texto_de_html(html: str) -> str:
    sem_script = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    sem_tag = re.sub(r"(?s)<[^>]+>", " ", sem_script)
    sem_entidade = (
        sem_tag.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    return re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\n\s*\n+", "\n\n", sem_entidade)).strip()


def _buscar_ddg(consulta: str, limite: int) -> list[dict[str, str]]:
    url = "https://html.duckduckgo.com/html/?q=" + quote_plus(consulta)
    html, _, _ = _baixar_texto(url)
    itens: list[dict[str, str]] = []
    padrao = re.compile(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S)
    for achado in padrao.finditer(html):
        if len(itens) >= limite:
            break
        destino = achado.group(1)
        titulo = _texto_de_html(achado.group(2))
        if destino.startswith("//"):
            destino = "https:" + destino
        if "uddg=" in destino:
            trecho = re.search(r"uddg=([^&]+)", destino)
            if trecho:
                from urllib.parse import unquote

                destino = unquote(trecho.group(1))
        itens.append({"titulo": titulo[:200], "url": destino[:500]})
    return itens


def rede(
    *,
    acao: str = "buscar",
    consulta: str = "",
    url: str = "",
    limite: int = 8,
    modo: str = "full",
    autorizacao: str = "",
) -> dict[str, Any]:
    """Busca na web ou lê uma página. Nunca grava arquivo."""
    modo = _modo(modo)
    _exigir_rede(autorizacao)
    acao = (acao or "buscar").strip().lower()
    if acao not in {"buscar", "olhar"}:
        raise SistemaError("Ação inválida: use buscar ou olhar. Download é `sistema.baixar`.")
    limite = max(1, min(int(limite), 25))
    rows: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    texto_pagina = ""
    if acao == "buscar":
        termo = (consulta or "").strip()
        if not termo:
            raise SistemaError("Informe a consulta.")
        itens = _buscar_ddg(termo, limite)
        rows = [{"posicao": i + 1, "titulo": item["titulo"], "url": item["url"]} for i, item in enumerate(itens)]
        resumo = [
            f"{len(rows)} resultado(s) para **{termo}**.",
            "Fonte: DuckDuckGo HTML. Sem resultado significa bloqueio ou consulta sem correspondência — não invente link.",
        ]
        if not rows:
            findings.append(
                finding(
                    "should",
                    "rede",
                    "Busca sem resultado",
                    "duckduckgo",
                    "A consulta não devolveu link parseável.",
                    "Bloqueio de rede, captcha ou mudança de marcação produzem o mesmo vazio.",
                    "Tente outra formulação ou informe a URL diretamente em `olhar`.",
                    "Você conclui que o programa não existe.",
                )
            )
    else:
        destino = _url_segura(url)
        html, tipo, codigo = _baixar_texto(destino)
        texto_pagina = _texto_de_html(html)[:20_000] if "html" in tipo.lower() or not tipo else html[:20_000]
        rows = [
            {"campo": "url", "valor": destino},
            {"campo": "status", "valor": str(codigo)},
            {"campo": "tipo", "valor": tipo or "não informado"},
            {"campo": "caracteres", "valor": str(len(texto_pagina))},
        ]
        resumo = [f"Página lida: **{destino}** ({codigo}, {len(texto_pagina)} caracteres)."]
    findings, counts, verdict, questions = finalize(findings, modo, [
        "A fonte é o site oficial do projeto?",
        "O resultado é de 2026 ou pode estar desatualizado?",
    ])
    return common(
        analysis="rede",
        mode=modo,
        title="Acesso à rede",
        summary=resumo,
        findings=findings,
        counts=counts,
        verdict=verdict,
        questions=questions,
        rows=rows[:MAX_ROWS],
        metrics={"acao": acao, "resultados": len(rows), "limite": limite},
        limitations=[
            "Busca usa a página HTML do DuckDuckGo: sem chave, sujeita a bloqueio e a mudança de marcação.",
            "Endereço privado, laço local e link-local são bloqueados de propósito.",
            "Nenhum conteúdo de página é resumido por modelo: é o texto extraído, truncado.",
            "Esta operação não grava arquivo; quem baixa é `sistema.baixar`.",
        ],
        extra_sections=["", "## Conteúdo da página", "", texto_pagina] if texto_pagina else None,
    )


def _auditar(evento: dict[str, Any]) -> None:
    try:
        AUDITORIA.parent.mkdir(parents=True, exist_ok=True)
        linha = {"ts": datetime.now(timezone.utc).isoformat(), **evento}
        with open(AUDITORIA, "a", encoding="utf-8") as saida:
            saida.write(json.dumps(linha, ensure_ascii=False) + "\n")
    except OSError:
        pass


def baixar(
    *,
    url: str,
    modo: str = "full",
    autorizacao: str = "",
) -> dict[str, Any]:
    """Baixa um arquivo para a quarentena e devolve o hash. Não executa nada."""
    modo = _modo(modo)
    _exigir_rede(autorizacao)
    destino = _url_segura(url)
    QUARENTENA.mkdir(parents=True, exist_ok=True)
    nome = Path(urlparse(destino).path).name or "arquivo"
    nome = re.sub(r"[^A-Za-z0-9._-]", "_", nome)[:80] or "arquivo"
    pedido = Request(destino, headers={"User-Agent": AGENTE})
    try:
        with urlopen(pedido, timeout=TIMEOUT_REDE) as resposta:
            digest = hashlib.sha256()
            total = 0
            caminho = QUARENTENA / f"{secrets.token_hex(4)}-{nome}"
            with open(caminho, "wb") as saida:
                while True:
                    bloco = resposta.read(1024 * 256)
                    if not bloco:
                        break
                    total += len(bloco)
                    if total > MAX_DOWNLOAD:
                        saida.close()
                        caminho.unlink(missing_ok=True)
                        raise SistemaError(f"Arquivo maior que {MAX_DOWNLOAD // (1024 * 1024)} MB; recusado.")
                    digest.update(bloco)
                    saida.write(bloco)
            tipo = resposta.headers.get("content-type", "")
    except HTTPError as exc:
        raise SistemaError(f"O servidor respondeu {exc.code} para {destino}.") from exc
    except (URLError, OSError) as exc:
        raise SistemaError(f"Falha de rede ao baixar {destino}: {type(exc).__name__}.") from exc
    baixado = {
        "arquivo": str(caminho),
        "nome": nome,
        "bytes": total,
        "sha256": digest.hexdigest(),
        "tipo": tipo,
    }
    _auditar({"acao": "baixar", "url": destino, "sha256": digest.hexdigest(), "bytes": total})
    rows = [
        {"campo": "arquivo", "valor": str(caminho)},
        {"campo": "bytes", "valor": str(total)},
        {"campo": "sha256", "valor": digest.hexdigest()},
        {"campo": "tipo", "valor": tipo or "não informado"},
    ]
    findings: list[dict[str, Any]] = []
    if not _tipo_instalador(nome):
        findings.append(
            finding(
                "should",
                "formato",
                "Arquivo baixado não é instalador reconhecido",
                nome,
                f"Extensão de `{nome}` não está na lista de instaladores.",
                "O passo de execução só aceita msi, msix, deb, rpm, exe e AppImage.",
                "Baixe o pacote oficial da plataforma certa ou extraia o arquivo manualmente.",
                "Você não vai conseguir instalar por este caminho.",
            )
        )
    if total == 0:
        findings.append(
            finding(
                "must",
                "vazio",
                "Download vazio",
                destino,
                "O servidor respondeu 200 com zero byte.",
                "Arquivo vazio é recusado pelo instalador e indica página de erro disfarçada de download.",
                "Confira a URL no navegador antes de tentar de novo.",
                "O plano de instalação vai falhar sem explicar por quê.",
            )
        )
    findings, counts, verdict, questions = finalize(findings, modo, [
        "A fonte do download é o site oficial do projeto?",
        "Você confere o SHA-256 publicado antes de instalar?",
    ])
    resultado = common(
        analysis="baixar",
        mode=modo,
        title="Download para a quarentena",
        summary=[
            f"Baixado **{nome}** ({_gb(total)}) para a quarentena.",
            f"SHA-256 `{digest.hexdigest()[:32]}…` — confira no site oficial antes de executar.",
        ],
        findings=findings,
        counts=counts,
        verdict=verdict,
        questions=questions,
        rows=rows,
        metrics={
            "bytes": total,
            "limite": MAX_DOWNLOAD,
            "instalavel": bool(_tipo_instalador(nome)),
        },
        limitations=[
            "Arquivo vai para storage/host-downloads e não é executado por esta operação.",
            "Nenhuma assinatura digital é verificada.",
            "Endereço privado, laço local e link-local são bloqueados.",
        ],
    )
    resultado["executed"] = True
    resultado["readOnly"] = False
    resultado["download"] = baixado
    return resultado


# ---------------------------------------------------------------------------
# Instalação
# ---------------------------------------------------------------------------


def _tipo_instalador(nome: str) -> str:
    baixo = nome.lower()
    for sufixo, tipo in TIPOS.items():
        if baixo.endswith(sufixo):
            return tipo
    return ""


def _dentro_da_quarentena(caminho: str) -> Path:
    alvo = Path(caminho).expanduser()
    try:
        resolvido = alvo.resolve()
    except OSError as exc:
        raise SistemaError("Caminho de arquivo inválido.") from exc
    try:
        base = QUARENTENA.resolve()
    except OSError:
        base = QUARENTENA
    if base not in resolvido.parents:
        raise SistemaError(
            "Só instalo arquivo que passou pela quarentena de `sistema.baixar` em storage/host-downloads."
        )
    if not resolvido.exists():
        raise SistemaError("O arquivo não existe mais na quarentena.")
    return resolvido


def _comando_do_plano(tipo: str, arquivo: Path, pacote: str, silencioso: bool) -> list[str]:
    if tipo == "appimage":
        return []
    if tipo in {"pip", "npm"}:
        modelo = GERENCIADORES[tipo]
        nome = modelo[0].format(python=sys.executable)
        return [nome, *[parte.format(pacote=pacote) for parte in modelo[1]]]
    modelo = GERENCIADORES[tipo]
    nome = modelo[0].format(arquivo=str(arquivo))
    partes = [parte.format(arquivo=str(arquivo)) for parte in modelo[1]]
    if silencioso and tipo == "exe":
        partes = ["/S"]
    return [nome, *partes]


def _risco(tipo: str) -> tuple[str, str]:
    if tipo in {"msi", "deb", "rpm"}:
        return "médio", "O pacote roda com privilégio do instalador do sistema e pode pedir elevação."
    if tipo == "exe":
        return "alto", "Executável sem formato pactuado: o que ele faz depende inteiramente do fabricante."
    if tipo == "appimage":
        return "baixo", "O plano só marca o arquivo como executável; nada é executado."
    return "médio", "O gerenciador de pacotes baixa dependências da internet."


def _plano(*, arquivo: str, pacote: str, silencioso: bool) -> tuple[str, str, Path, list[str], str, str]:
    nome_pacote = (pacote or "").strip()
    if nome_pacote and re.search(r"[;&|`$><\s]", nome_pacote):
        raise SistemaError("Nome de pacote inválido: sem espaço, ponto e vírgula ou metacaractere.")
    if nome_pacote:
        tipo = "pip"
        if nome_pacote.startswith("npm:"):
            nome_pacote, tipo = nome_pacote[4:], "npm"
        elif nome_pacote.startswith("pip:"):
            nome_pacote = nome_pacote[4:]
        if not re.fullmatch(r"@?[\w][\w./@-]{0,199}", nome_pacote):
            raise SistemaError("Nome de pacote inválido para o gerenciador.")
        alvo = Path(nome_pacote)
        comando = _comando_do_plano(tipo, alvo, nome_pacote, silencioso)
        return f"pacote {tipo}: {nome_pacote}", tipo, alvo, comando, risco_final(tipo), str(alvo)
    if not arquivo.strip():
        raise SistemaError("Informe `arquivo` (da quarentena) ou `pacote` (pip:/npm:).")
    alvo = _dentro_da_quarentena(arquivo)
    tipo = _tipo_instalador(alvo.name)
    if not tipo:
        suportados = ", ".join(sorted(TIPOS))
        raise SistemaError(f"Extensão não suportada para instalação. Use {suportados}.")
    comando = _comando_do_plano(tipo, alvo, "", silencioso)
    return alvo.name, tipo, alvo, comando, risco_final(tipo), str(alvo)


def risco_final(tipo: str) -> str:
    return _risco(tipo)[0]


def instalar(
    *,
    arquivo: str = "",
    pacote: str = "",
    silencioso: bool = True,
    modo: str = "full",
    autorizacao: str = "",
) -> dict[str, Any]:
    """Monta o plano do instalador com o comando exato e o token de uso único."""
    modo = _modo(modo)
    _exigir(autorizacao)
    rotulo, tipo, alvo, comando, risco, _chave = _plano(arquivo=arquivo, pacote=pacote, silencioso=silencioso)
    motivo = _risco(tipo)[1]
    token = secrets.token_hex(4)
    expira = time.time() + CONFIRMACAO_TTL
    _CONFIRMACAO[token] = {
        "arquivo": str(alvo),
        "tipo": tipo,
        "comando": comando,
        "expira": expira,
        "rotulo": rotulo,
    }
    rows = [
        {"campo": "alvo", "valor": rotulo},
        {"campo": "tipo", "valor": tipo},
        {"campo": "comando", "valor": " ".join(comando) if comando else "(somente chmod +x)"},
        {"campo": "risco", "valor": risco},
        {"campo": "confirmação", "valor": token},
        {"campo": "válida até", "valor": datetime.fromtimestamp(expira, tz=timezone.utc).strftime("%H:%M:%S UTC")},
    ]
    findings: list[dict[str, Any]] = []
    if risco == "alto":
        findings.append(
            finding(
                "must",
                "risco",
                "Executável de terceiro com risco alto",
                str(alvo),
                "O plano executaria um .exe baixado da internet.",
                "Não existe verificação de assinatura nesta camada: o arquivo roda como veio.",
                "Confira o SHA-256 no site oficial e prefira .msi assinado pelo fabricante.",
                "Você instala software não verificado com um clique.",
            )
        )
    if comando and comando[0] not in {"msiexec", "dpkg", "rpm", "npm", sys.executable}:
        findings.append(
            finding(
                "must",
                "allowlist",
                "Comando fora da allowlist",
                comando[0],
                "O binário previsto não está na lista fechada desta camada.",
                "Rodar binário arbitrário transformaria a API em executor genérico.",
                "Use msi, deb, rpm, AppImage, pip ou npm.",
                "O passo de execução recusa.",
            )
        )
    if not capacidades()["instalar"]:
        findings.append(
            finding(
                "should",
                "guarda",
                "Execução bloqueada até você ligar a trava",
                AMBIENTE_INSTALAR,
                "O plano sai, mas `sistema.executar` recusa enquanto a variável não estiver em 1.",
                "Trava explícita evita instalação acidental em servidor exposto.",
                f"Suba a API com {AMBIENTE_INSTALAR}=1 quando for instalar de verdade.",
                "O plano vira rascunho sem efeito.",
            )
        )
    findings, counts, verdict, questions = finalize(findings, modo, [
        "Você conferiu o SHA-256 contra o site oficial do projeto?",
        "Você aceita que o instalador roda com os privilégios do processo da API?",
    ])
    resultado = common(
        analysis="instalar",
        mode=modo,
        title="Plano de instalação",
        summary=[
            f"Plano para **{rotulo}** ({tipo}), risco **{risco}**.",
            motivo,
            "Nada foi executado: este passo só desenha o comando.",
        ],
        findings=findings,
        counts=counts,
        verdict=verdict,
        questions=questions,
        rows=rows,
        metrics={"tipo": tipo, "risco": risco, "passos": len(comando), "executado": False},
        limitations=[
            "Não existe shell livre: só a lista fechada de instaladores com argumentos fixos.",
            "Nenhuma assinatura digital é verificada por esta camada.",
            "O token vale 10 minutos, serve uma vez e só para este arquivo.",
            "Elevação de privilégio não é feita: se o instalador pedir administrador, a execução falha.",
        ],
    )
    resultado["confirmacao"] = token
    return resultado


def executar(
    *,
    confirmacao: str,
    modo: str = "full",
    autorizacao: str = "",
) -> dict[str, Any]:
    """Executa o plano confirmado. Exige a trava ligada e o token de uso único."""
    modo = _modo(modo)
    _exigir_instalar(autorizacao)
    token = (confirmacao or "").strip()
    if not token or token not in _CONFIRMACAO:
        raise SistemaError("Confirmação ausente ou desconhecida. Gere o plano em `sistema.instalar` de novo.")
    registro = _CONFIRMACAO.pop(token)
    if registro["expira"] < time.time():
        raise SistemaError("Confirmação expirada. Gere o plano de novo.")
    alvo = Path(registro["arquivo"])
    if registro["tipo"] in {"msi", "deb", "rpm", "exe"} and not _dentro_da_quarentena(str(alvo)):
        raise SistemaError("O arquivo saiu da quarentena. Gere o plano de novo.")
    rows: list[dict[str, Any]] = [
        {"campo": "alvo", "valor": registro["rotulo"]},
        {"campo": "tipo", "valor": registro["tipo"]},
        {"campo": "comando", "valor": " ".join(registro["comando"]) or "(chmod +x)"},
    ]
    findings: list[dict[str, Any]] = []
    if registro["tipo"] == "appimage":
        try:
            os.chmod(alvo, 0o755)
        except OSError as exc:
            raise SistemaError(f"Não foi possível marcar como executável: {type(exc).__name__}.") from exc
        resultado_exec = {"acao": "chmod", "arquivo": str(alvo), "modo": "755", "codigo": 0}
    else:
        if not registro["comando"]:
            raise SistemaError("O plano não produziu comando executável.")
        codigo, saida, erro = _rodar(registro["comando"], timeout=300)
        resultado_exec = {
            "acao": "executar",
            "comando": " ".join(registro["comando"]),
            "codigo": codigo,
            "saida": saida[-4_000:],
            "erro": erro[-2_000:],
        }
        _auditar(
            {
                "acao": "instalar",
                "alvo": registro["rotulo"],
                "comando": " ".join(registro["comando"]),
                "codigo": codigo,
            }
        )
        if codigo != 0:
            findings.append(
                finding(
                    "must",
                    "execucao",
                    "Instalador terminou com erro",
                    registro["rotulo"],
                    f"Código de saída {codigo}: {(erro or saida)[-300:] or 'sem mensagem'}.",
                    "O pacote não foi instalado ou parou no meio.",
                    "Confira se a execução precisa de elevação e rode de novo como administrador.",
                    "Você acredita que instalou e o programa não existe.",
                )
            )
        elif saida:
            findings.append(
                finding(
                    "nice",
                    "execucao",
                    "Instalador terminou sem erro",
                    registro["rotulo"],
                    f"Código 0. Saída: {saida[-200:] or 'vazia'}.",
                    "Código zero não garante que o programa ficou no PATH nem que abriu.",
                    "Confirme abrindo o programa pelo menu do sistema.",
                    "Você procura um atalho que não foi criado.",
                )
            )
        rows.append({"campo": "execução", "valor": f"código {codigo}"})
    findings, counts, verdict, questions = finalize(findings, modo, [
        "O programa abriu depois da instalação?",
        "Você quer desinstalar se o resultado não servir?",
    ])
    resultado = common(
        analysis="executar",
        mode=modo,
        title="Execução do instalador",
        summary=[
            f"Executado **{registro['rotulo']}** ({registro['tipo']}) com código **{resultado_exec.get('codigo')}**.",
            "O token foi consumido e não serve de novo.",
        ],
        findings=findings,
        counts=counts,
        verdict=verdict,
        questions=questions,
        rows=rows,
        metrics={"tipo": registro["tipo"], "codigo": resultado_exec.get("codigo"), "executado": True},
        limitations=[
            "A execução herdou o usuário e os privilégios do processo da API.",
            "Nenhuma assinatura digital foi verificada.",
            "O comando executado é o que o plano mostrou: nada foi acrescentado depois.",
        ],
    )
    resultado["executed"] = True
    resultado["readOnly"] = False
    resultado["execucao"] = resultado_exec
    return resultado


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------


def catalogo() -> dict[str, Any]:
    """Publica guardas, limites e o que a camada recusa fazer."""
    caps = capacidades()
    return {
        "executed": False,
        "readOnly": True,
        "versao": VERSAO,
        "principio": (
            "Ler a máquina de verdade só é seguro quando o efeito colateral é separado da leitura: "
            "token de host para tudo, rede desligada por padrão, instalação em dois passos com allowlist fechada."
        ),
        "operacoes": [
            {"id": "ambiente", "entrada": "—", "saida": "sistema, CPU, memória, contêiner e capacidades"},
            {"id": "disco", "entrada": "caminhos opcionais", "saida": "total, usado, livre e percentual por unidade"},
            {"id": "pastas", "entrada": "raiz, profundidade, limite", "saida": "nome, tipo, tamanho e data, sem conteúdo"},
            {"id": "drivers", "entrada": "filtro", "saida": "módulos do kernel ou drivers PnP com assinatura"},
            {"id": "bluetooth", "entrada": "filtro", "saida": "adaptadores e dispositivos pareados"},
            {"id": "rede", "entrada": "buscar | olhar", "saida": "resultados de busca ou texto da página"},
            {"id": "baixar", "entrada": "url", "saida": "arquivo em quarentena, bytes e sha256"},
            {"id": "instalar", "entrada": "arquivo ou pacote", "saida": "comando exato, risco e token de uso único"},
            {"id": "executar", "entrada": "confirmacao", "saida": "código de saída e mensagens do instalador"},
            {"id": "regras", "entrada": "—", "saida": "guardas, allowlist, limites e recusas"},
        ],
        "guardas": [
            {"ordem": 1, "guarda": "token de host", "padrao": "obrigatório", "arquivo": "storage/host-token.txt"},
            {"ordem": 2, "guarda": "rede", "padrao": "desligada", "variavel": AMBIENTE_REDE},
            {"ordem": 3, "guarda": "instalação", "padrao": "desligada", "variavel": AMBIENTE_INSTALAR},
            {"ordem": 4, "guarda": "quarentena", "padrao": "obrigatória", "pasta": "storage/host-downloads"},
            {"ordem": 5, "guarda": "confirmação de uso único", "padrao": f"{CONFIRMACAO_TTL}s", "campo": "confirmacao"},
        ],
        "capacidades": caps,
        "limites": {
            "texto": MAX_TEXTO,
            "linhas": MAX_ROWS,
            "entradas": MAX_ENTRADAS,
            "profundidade": MAX_PROFUNDIDADE,
            "download": MAX_DOWNLOAD,
            "pagina": MAX_PAGINA,
            "timeoutRede": TIMEOUT_REDE,
        },
        "instaladores": sorted(TIPOS) + ["pip", "npm", "appimage"],
        "nao_faz": [
            "Não abre shell livre nem aceita comando digitado.",
            "Não lê conteúdo de arquivo: a enumeração devolve só metadado.",
            "Não pareia, conecta ou desconecta dispositivo Bluetooth.",
            "Não verifica assinatura digital de instalador.",
            "Não eleva privilégio.",
            "Não apaga, move ou renomeia arquivo do usuário.",
            "Não alcança endereço privado, laço local ou link-local pela rede.",
        ],
    }
