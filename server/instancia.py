"""Quem já está na porta 8000 — e por que “JARVIS já está em uso” é boa notícia.

A frase que gerou isto foi a tela de quem rodou o atalho e leu:

    Já existe uma API respondendo em http://127.0.0.1:8000
    Não precisa subir outra: abra o endereço no navegador.

Isso **não é erro**: é o JARVIS avisando que já tem um dele mesmo rodando. Mas a
mensagem tinha dois buracos que custam tempo de quem está na frente da máquina:

1. **não dizia qual versão está rodando.** Se você acabou de atualizar a pasta e
   a janela antiga continua aberta, o navegador mostra o código velho e parece
   que a atualização não funcionou;
2. **não dizia como fechar a janela antiga** quando ela não está mais à vista
   (minimizada, ou aberta por `npm run dev` em outro terminal).

Este módulo resolve os dois. Ele lê o `/api/health` da porta, compara com a
versão desta pasta e responde em uma frase o que fazer. E, quando você pede
explicitamente, encerra **apenas** o processo que se identifica como
`jarvis-python-api` naquela porta — nunca “qualquer coisa que esteja na 8000”.

Regra herdada do resto do projeto: **nada é encerrado sem você mandar**. O
`encerrar()` exige confirmação no console e recusa quando a identidade não bate.
"""
from __future__ import annotations

import json
import platform
import re
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

CRIACAO_SEM_JANELA = 0x08000000
SERVICO = "jarvis-python-api"

RAIZ = Path(__file__).resolve().parent.parent


class InstanciaError(RuntimeError):
    """Falha ao consultar ou encerrar a instância."""


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------


def versao_da_pasta(raiz: Path | None = None) -> str | None:
    """Versão do `package.json` desta pasta — é ela que o zip trouxe."""
    caminho = (raiz or RAIZ) / "package.json"
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    versao = dados.get("version")
    return str(versao) if versao else None


def ler_health(host: str = "127.0.0.1", porta: int = 8000, timeout: float = 2.0) -> dict[str, Any] | None:
    """O `/api/health` de quem estiver na porta. `None` se ninguém respondeu."""
    from urllib.error import URLError  # noqa: PLC0415
    from urllib.request import urlopen  # noqa: PLC0415

    alvo = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    try:
        with urlopen(f"http://{alvo}:{porta}/api/health", timeout=timeout) as resposta:
            bruto = resposta.read().decode("utf-8", "replace") or "{}"
    except (URLError, OSError, ValueError):
        return None
    try:
        dados = json.loads(bruto)
    except ValueError:
        return None
    return dados if isinstance(dados, dict) else None


def porta_ocupada(host: str, porta: int) -> bool:
    """Alguém está escutando? (sem perguntar quem é)"""
    alvo = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sonda:
        sonda.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sonda.bind((alvo, porta))
        except OSError:
            return True
    return False


# ---------------------------------------------------------------------------
# Análise (pura) — é o que os testes exercitam
# ---------------------------------------------------------------------------


def _mesma_versao(a: str | None, b: str | None) -> bool:
    return bool(a) and bool(b) and a.strip() == b.strip()


def avaliar(health: dict[str, Any] | None, versao_pasta: str | None, porta: int = 8000,
            ocupada: bool = False) -> dict[str, Any]:
    """Decide o estado da porta e o que dizer. Função pura, sem rede.

    Estados:

    - `livre`          — ninguém escutando: pode subir;
    - `jarvis_mesma`   — JARVIS rodando **desta** versão: só abrir o navegador;
    - `jarvis_antiga`  — JARVIS rodando de outra versão: fechar antes de subir;
    - `outro_programa` — a porta está ocupada por algo que não é o JARVIS.
    """
    if health is None:
        if ocupada:
            return {
                "estado": "outro_programa",
                "titulo": f"A porta {porta} está ocupada por outro programa",
                "detalhe": "Não é o JARVIS: ele não respondeu em /api/health.",
                "versao_rodando": None,
                "versao_da_pasta": versao_pasta,
                "o_que_fazer": [
                    f"Suba em outra porta: .venv\\Scripts\\python iniciar.py --porta {porta + 1}",
                    "Ou feche o programa que está usando essa porta (ele não é o JARVIS).",
                ],
            }
        return {
            "estado": "livre",
            "titulo": f"A porta {porta} está livre",
            "detalhe": "Ninguém escutando: pode subir o JARVIS.",
            "versao_rodando": None,
            "versao_da_pasta": versao_pasta,
            "o_que_fazer": [],
        }

    if health.get("service") != SERVICO:
        return {
            "estado": "outro_programa",
            "titulo": f"A porta {porta} responde, mas não é o JARVIS",
            "detalhe": f"Respondeu um serviço chamado “{health.get('service') or 'sem nome'}”.",
            "versao_rodando": health.get("version"),
            "versao_da_pasta": versao_pasta,
            "o_que_fazer": [
                f"Suba em outra porta: .venv\\Scripts\\python iniciar.py --porta {porta + 1}",
                "Não encerre esse processo: o JARVIS não sabe o que ele é.",
            ],
        }

    rodando = health.get("version")
    if _mesma_versao(rodando, versao_pasta):
        return {
            "estado": "jarvis_mesma",
            "titulo": f"O JARVIS {rodando} já está rodando",
            "detalhe": "É esta mesma pasta: nada a fazer além de abrir o navegador.",
            "versao_rodando": rodando,
            "versao_da_pasta": versao_pasta,
            "o_que_fazer": [f"Abra http://127.0.0.1:{porta}"],
        }

    detalhe = (
        f"Rodando: {rodando or 'sem versão'}. Esta pasta: {versao_pasta or 'sem versão'}."
        if rodando and versao_pasta
        else "A janela aberta é de outra cópia do JARVIS."
    )
    return {
        "estado": "jarvis_antiga",
        "titulo": f"Já existe um JARVIS na porta {porta} — mas é de outra versão",
        "detalhe": detalhe + " O navegador mostraria o código antigo e pareceria que a atualização não pegou.",
        "versao_rodando": rodando,
        "versao_da_pasta": versao_pasta,
        "o_que_fazer": [
            "Feche a janela antiga no X (procure “JARVIS” na barra de tarefas)",
            "Se a janela sumiu: duplo clique em parar-jarvis.bat",
            "Depois rode iniciar-jarvis.bat de novo",
        ],
    }


def resumo(situacao: dict[str, Any]) -> str:
    """Uma linha para o console."""
    if situacao["estado"] == "livre":
        return f"Porta livre ({situacao['titulo']})."
    if situacao["estado"] == "jarvis_mesma":
        return f"JARVIS {situacao['versao_rodando']} já está no ar — abra o navegador."
    if situacao["estado"] == "jarvis_antiga":
        return (
            f"JARVIS {situacao['versao_rodando'] or '?'} rodando, pasta em "
            f"{situacao['versao_da_pasta'] or '?'} — feche a janela antiga antes de subir."
        )
    return situacao["titulo"]


# ---------------------------------------------------------------------------
# Processo: achar o PID e encerrar só o JARVIS
# ---------------------------------------------------------------------------

LINHA_NETSTAT = re.compile(
    r"^\s*(?P<proto>TCP)\s+(?P<local>\S+)\s+(?P<remoto>\S+)\s+(?P<estado>LISTENING)\s+(?P<pid>\d+)\s*$",
    re.IGNORECASE,
)


def pids_da_saida_netstat(texto: str, porta: int) -> list[int]:
    """PIDs que escutam na porta, lidos da saída do `netstat -ano`. Puro."""
    encontrados: list[int] = []
    for linha in texto.splitlines():
        achado = LINHA_NETSTAT.match(linha)
        if not achado:
            continue
        local = achado.group("local")
        if not local.rsplit(":", 1)[-1] == str(porta):
            continue
        pid = int(achado.group("pid"))
        if pid and pid not in encontrados:
            encontrados.append(pid)
    return encontrados


def pids_na_porta(porta: int = 8000, timeout: int = 20) -> list[int]:
    """Consulta o Windows. Fora dele, lista vazia com o motivo em `NotImplemented`."""
    if platform.system() != "Windows":
        return []
    try:
        concluido = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=CRIACAO_SEM_JANELA if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise InstanciaError("Não consegui rodar o netstat.") from exc
    return pids_da_saida_netstat(concluido.stdout or "", porta)


def encerrar_pid(pid: int, timeout: int = 20) -> bool:
    """`taskkill /PID` — só para PID que o chamador já confirmou ser o JARVIS."""
    if platform.system() != "Windows":
        raise InstanciaError("Encerrar processo é do Windows; aqui não se aplica.")
    try:
        concluido = subprocess.run(
            ["taskkill", "/PID", str(int(pid)), "/F"],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=CRIACAO_SEM_JANELA if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise InstanciaError(f"Não consegui encerrar o PID {pid}.") from exc
    return concluido.returncode == 0


def encerrar(porta: int = 8000, *, espera: float = 8.0) -> dict[str, Any]:
    """Encerra o JARVIS desta porta — **se** a identidade bater. Nunca outro processo.

    A ordem é proposital: primeiro pergunta ao `/api/health` quem é; só depois
    procura o PID. Assim, uma porta ocupada por outro programa nunca vira alvo.
    """
    health = ler_health(porta=porta)
    if health is None:
        return {"encerrado": False, "motivo": "Não há JARVIS respondendo nessa porta."}
    if health.get("service") != SERVICO:
        return {
            "encerrado": False,
            "motivo": f"Quem responde na porta não é o JARVIS ({health.get('service') or 'sem nome'}).",
        }
    versao = health.get("version")
    pids = pids_na_porta(porta)
    if not pids:
        return {
            "encerrado": False,
            "motivo": "O JARVIS responde, mas não achei o processo dono da porta (netstat vazio).",
            "versao": versao,
        }
    fechados: list[int] = []
    for pid in pids:
        if encerrar_pid(pid):
            fechados.append(pid)
    limite = time.monotonic() + espera
    while time.monotonic() < limite:
        if ler_health(porta=porta, timeout=0.5) is None:
            break
        time.sleep(0.4)
    livre = ler_health(porta=porta, timeout=0.5) is None
    return {
        "encerrado": bool(fechados) and livre,
        "pids": pids,
        "fechados": fechados,
        "versao": versao,
        "porta_livre": livre,
        "motivo": "" if livre else "Mandei encerrar, mas a porta ainda responde. Feche a janela no X.",
    }


# ---------------------------------------------------------------------------
# CLI — é o que o parar-jarvis.bat chama
# ---------------------------------------------------------------------------


def _cli(argv: list[str] | None = None) -> int:
    import argparse  # noqa: PLC0415
    import sys  # noqa: PLC0415

    parser = argparse.ArgumentParser(description="Quem está na porta do JARVIS.")
    parser.add_argument("--porta", type=int, default=8000)
    parser.add_argument("--parar", action="store_true", help="Encerrar o JARVIS desta porta (pede confirmação).")
    parser.add_argument("--sim", action="store_true", help="Não perguntar (usar só em script).")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    health = ler_health(porta=args.porta)
    situacao = avaliar(
        health,
        versao_da_pasta(),
        porta=args.porta,
        ocupada=porta_ocupada("127.0.0.1", args.porta),
    )
    if args.json:
        print(json.dumps({"situacao": situacao, "health": health}, ensure_ascii=False, indent=2))
        return 0

    print()
    print(f"  {situacao['titulo']}")
    print(f"  {situacao['detalhe']}")
    for passo in situacao["o_que_fazer"]:
        print(f"    - {passo}")
    print()

    if not args.parar:
        return 0
    if situacao["estado"] not in {"jarvis_mesma", "jarvis_antiga"}:
        # Não é falha: simplesmente não há JARVIS para encerrar. O .bat só deve
        # mostrar o plano B manual quando algo deu errado de verdade.
        print("  Nada a encerrar: não há JARVIS nessa porta.")
        print()
        return 0

    if not args.sim:
        try:
            resposta = input(f"  Encerrar o JARVIS {situacao['versao_rodando'] or ''} da porta {args.porta}? [s/N] ").strip().lower()
        except EOFError:
            resposta = ""
        if resposta not in {"s", "sim", "y", "yes"}:
            print("  Cancelado: nada foi encerrado.")
            print()
            return 0

    resultado = encerrar(args.porta)
    if resultado.get("encerrado"):
        print(f"  Encerrado (PID {', '.join(str(p) for p in resultado.get('fechados', []))}). A porta está livre.")
        print("  Agora rode iniciar-jarvis.bat para subir a versão desta pasta.")
    else:
        print(f"  Não consegui encerrar: {resultado.get('motivo')}")
    print()
    return 0 if resultado.get("encerrado") else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
