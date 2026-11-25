"""Instalação do JARVIS em outras distribuições Linux — e onde ele não roda.

Pedido do dono (0.95.5): o JARVIS precisa saber se instalar no Lindows, Parrot,
TempleOS, Astra, Red Star, Whonix, NeoKylin e "Windows Gaming Edition".

A regra que este módulo obedece é a mesma do resto do projeto: **não inventar**.
Instalar é uma ação com efeito, então:

- a lista de sistemas é **dado**, não texto solto: cada um sabe sua família de
  pacote, se tem suporte vivo, e o que quebra nele;
- o passo a passo só é gerado para quem tem chance real — dizer "rode
  `apt install`" em TempleOS seria mentir com convicção;
- quando o sistema é o da máquina, ele **mede** (`/etc/os-release`, `python3`,
  `pip`, `adb`, `git`) em vez de supor;
- nada é instalado por este módulo: ele devolve o **plano**. Quem executa é a
  skill `sistema.instalar`, atrás de `JARVIS_HOST_REDE`/`JARVIS_HOST_INSTALAR`.

Por que alguns ficam de fora, em uma linha cada:

- **TempleOS** (2003–2013, 640x480, linguagem HolyC): não tem Python, não tem
  `pip`, não tem pilha TCP no sentido que o JARVIS usa. Não existe caminho.
- **Lindows** (2001, virou Linspire, encerrado em 2008): base Debian morta, sem
  repositório que responda. Rodaria em teoria; não há de onde instalar.
- **Red Star OS** (Coreia do Norte, base Fedora, modificado): ele marca arquivos
  e o repositório não é alcançável de fora. Fora de escopo por rede, não por código.
- **"Windows Gaming Edition"**: não é produto da Microsoft — são ISOs alteradas
  que circulam sem procedência. Não é sistema para o JARVIS recomendar.
"""
from __future__ import annotations

import os
import platform
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .sistema import SistemaError


@dataclass(frozen=True)
class Sistema:
    """Um sistema operacional que o JARVIS considerou.

    `situacao` é o veredito curto e é o que o dono lê primeiro:

    - `roda` — família viva, instalação possível e conhecida;
    - `roda_com_ressalva` — instala, mas alguma coisa importante degrada;
    - `impossivel` — falta o mínimo (Python, gerenciador, rede);
    - `nao_recomendado` — nada de errado com o Linux, mas é ISO de origem
      desconhecida.
    """

    id: str
    nome: str
    familia: str
    situacao: str
    ano: str
    porque: str
    o_que_quebra: tuple[str, ...] = ()
    como_instalar: tuple[str, ...] = ()
    ainda_existe: bool = True
    notas: dict[str, str] = field(default_factory=dict)


SISTEMAS: tuple[Sistema, ...] = (
    Sistema(
        id="parrot",
        nome="Parrot OS",
        familia="debian",
        situacao="roda",
        ano="2013 (vivo)",
        porque="É Debian com ferramentas de segurança; tudo que o JARVIS usa existe no repositório.",
        o_que_quebra=(),
        como_instalar=(
            "sudo apt update",
            "sudo apt install -y python3 python3-venv python3-pip git android-tools-adb ffmpeg",
            "python3 -m venv .venv && . .venv/bin/activate",
            "pip install -r requirements.txt",
            "python iniciar.py",
        ),
        notas={
            "adb": "android-tools-adb é o pacote do `adb` no Debian e derivados.",
            "firewall": "O Parrot vem com firewall ligado: a API em 127.0.0.1 não é afetada.",
        },
    ),
    Sistema(
        id="astra",
        nome="Astra Linux",
        familia="debian",
        situacao="roda",
        ano="2009 (vivo, usado por órgãos na Rússia)",
        porque="É Debian por baixo (mais antigo), com `apt`. Os pacotes do JARVIS vêm daí.",
        o_que_quebra=(
            "A versão do Python pode ser 3.7–3.9; o JARVIS usa recursos de 3.9+ "
            "(anotações `dict[str, Any]` funcionam com `from __future__`).",
        ),
        como_instalar=(
            "sudo apt update",
            "sudo apt install -y python3 python3-venv python3-pip git android-tools-adb ffmpeg",
            "python3 -m venv .venv && . .venv/bin/activate",
            "pip install -r requirements.txt",
            "python iniciar.py",
        ),
        notas={
            "python": "Se `python3 --version` der menos que 3.9, instale o Python do "
            "repositório backports ou use pyenv — o JARVIS não roda em 3.7.",
        },
    ),
    Sistema(
        id="neokylin",
        nome="NeoKylin",
        familia="rpm",
        situacao="roda_com_ressalva",
        ano="2006 (vivo, chinês)",
        porque="Base RHEL/Fedora: `dnf`/`yum` funcionam, mas os nomes dos pacotes mudam.",
        o_que_quebra=(
            "O `adb` não está no repositório base do NeoKylin — é preciso baixar o "
            "platform-tools do Google à mão (o JARVIS faz isso pela skill `celular.preparar`).",
            "`ffmpeg` costuma vir de repositório extra (EPEL); sem ele a conversão de vídeo falha.",
        ),
        como_instalar=(
            "sudo dnf install -y python3 python3-pip git",
            "sudo dnf install -y epel-release && sudo dnf install -y ffmpeg",
            "python3 -m venv .venv && . .venv/bin/activate",
            "pip install -r requirements.txt",
            "python iniciar.py",
            "# depois, no chat: peça `celular.preparar` — ele baixa o platform-tools do Google",
        ),
        notas={
            "adb": "O platform-tools vai para storage/ferramentas, não para o sistema.",
        },
    ),
    Sistema(
        id="whonix",
        nome="Whonix",
        familia="debian",
        situacao="roda_com_ressalva",
        ano="2012 (vivo)",
        porque="É Debian dentro de duas VMs (Gateway + Workstation). Instalar funciona.",
        o_que_quebra=(
            "Todo o tráfego passa pelo Tor por desenho. O updater (que fala com o "
            "GitHub), o driver da Samsung e qualquer download direto podem ser "
            "recusados ou ficar lentos demais.",
            "A API em 127.0.0.1 continua funcionando; o que cai é a parte de rede.",
        ),
        como_instalar=(
            "sudo apt update",
            "sudo apt install -y python3 python3-venv python3-pip git android-tools-adb",
            "python3 -m venv .venv && . .venv/bin/activate",
            "pip install -r requirements.txt",
            "python iniciar.py",
        ),
        notas={
            "privacidade": "No Whonix, `JARVIS_HOST_REDE=0` é o padrão certo: o JARVIS "
            "funciona para diagnóstico local sem tocar a rede.",
        },
    ),
    Sistema(
        id="lindows",
        nome="Lindows",
        familia="debian",
        situacao="impossivel",
        ano="2001–2008 (encerrado; virou Linspire)",
        porque="Empresa fechou em 2008; os repositórios não respondem mais.",
        o_que_quebra=(
            "Sem repositório vivo, `apt update` falha e não há de onde instalar Python 3.9+.",
            "O Python da época é 2.x — o JARVIS nem abre (usa sintaxe de 3.9+).",
            "Código-fonte compilado à mão é possível em teoria, mas o sistema é de "
            "2001: bibliotecas C antigas, OpenSSL sem TLS 1.2.",
        ),
        como_instalar=(),
        ainda_existe=False,
        notas={
            "alternativa": "Se o interesse é o visual dos anos 2000, use Debian atual "
            "com um tema — o JARVIS roda e você não fica sem repositório.",
        },
    ),
    Sistema(
        id="redstar",
        nome="Red Star OS",
        familia="rpm",
        situacao="impossivel",
        ano="2002 (Coreia do Norte; 3.0 em 2013)",
        porque="É Fedora modificado, mas a rede e o sistema são fechados por desenho.",
        o_que_quebra=(
            "O sistema marca arquivos com identificador de máquina (watermarking), "
            "documentado por pesquisadores que o examinaram.",
            "Não há repositório alcançável de fora; `dnf` não resolve dependência.",
            "Sem `pip` alcançável: instalar Flask, FastAPI e httpx fica impossível.",
        ),
        como_instalar=(),
        notas={
            "aviso": "Não é um sistema para uso pessoal: as versões conhecidas marcam "
            "documentos e restringem a rede.",
        },
    ),
    Sistema(
        id="templeos",
        nome="TempleOS",
        familia="proprio",
        situacao="impossivel",
        ano="2003–2013 (encerrado; autor faleceu em 2016)",
        porque="Não é Unix nem Windows: é um sistema próprio, de 640x480, com a "
        "linguagem HolyC.",
        o_que_quebra=(
            "Não existe Python para TempleOS — nem interpretador, nem porta. O JARVIS "
            "é Python de ponta a ponta (API, skills, testes).",
            "Não existe `pip`, então nem as bibliotecas (FastAPI, httpx) teriam onde ser instaladas.",
            "A pilha de rede é mínima e não tem TLS: nada de HTTPS, ou seja, nem "
            "baixar o `adb` nem falar com o GitHub.",
            "Sem TLS 1.2+, o updater por `raw.githubusercontent.com` é impossível.",
            "A memória é endereçada de forma fixa e o sistema roda em um único processo "
            "cooperativo — o modelo de subprocesso (`adb`, `ffmpeg`) não existe.",
        ),
        como_instalar=(),
        notas={
            "o_que_seria_preciso": "Reescrever o JARVIS inteiro em HolyC e escrever um "
            "cliente TLS do zero. Não é uma questão de esforço: é outro projeto.",
            "homenagem": "O TempleOS é fascinante como peça de software — 100 mil linhas "
            "escritas por uma pessoa. Só não é onde este programa roda.",
        },
    ),
    Sistema(
        id="windows-gaming",
        nome='"Windows Gaming Edition"',
        familia="windows",
        situacao="nao_recomendado",
        ano="—",
        porque="Não é produto da Microsoft. São ISOs de terceiros que circulam com "
        "nome de edição que não existe oficialmente.",
        o_que_quebra=(
            "A procedência é desconhecida: não há assinatura da Microsoft na ISO e "
            "ninguém sabe o que foi alterado nela.",
            "Edições \"gaming\" costumam desligar serviços (Windows Update, Defender) "
            "justamente os que o JARVIS consulta para diagnóstico.",
            "O driver da Samsung exige assinatura válida; em sistema alterado a "
            "instalação pode ser recusada.",
            "Atualização do Windows desfeita por falta de Update = o JARVIS fica sem "
            "as correções que ele mesmo recomenda instalar.",
        ),
        como_instalar=(),
        notas={
            "alternativa": "Windows 10/11 **Home ou Pro** (as oficiais, do site da "
            "Microsoft) com os ajustes de jogo feitos à mão: modo de jogo, plano de "
            "energia e driver de vídeo. É o mesmo efeito, com procedência.",
        },
    ),
)

# Apelidos: como o dono pode escrever no chat e onde cada um cai.
_APELIDOS: dict[str, str] = {
    "parrot": "parrot",
    "parrot os": "parrot",
    "parrotos": "parrot",
    "astra": "astra",
    "astra linux": "astra",
    "neokylin": "neokylin",
    "neo kylin": "neokylin",
    "neokylin linux": "neokylin",
    "whonix": "whonix",
    "lindows": "lindows",
    "linspire": "lindows",
    "red star": "redstar",
    "redstar": "redstar",
    "red star os": "redstar",
    "templeos": "templeos",
    "temple os": "templeos",
    "windows gaming": "windows-gaming",
    "windows gaming edition": "windows-gaming",
    "gaming edition": "windows-gaming",
}

_STATUS = {
    "roda": "roda",
    "roda_com_ressalva": "roda, com ressalva",
    "impossivel": "não roda",
    "nao_recomendado": "não recomendado",
}


def _achar(nome: str) -> Sistema:
    chave = re.sub(r"\s+", " ", (nome or "").strip().lower())
    alvo = _APELIDOS.get(chave)
    if not alvo:
        for sistema in SISTEMAS:
            if chave == sistema.id or chave == sistema.nome.lower():
                alvo = sistema.id
                break
    if not alvo:
        conhecidos = ", ".join(s.nome for s in SISTEMAS)
        raise SistemaError(f"Não conheço “{nome}”. Tenho: {conhecidos}.")
    return next(s for s in SISTEMAS if s.id == alvo)


def _os_release() -> dict[str, str]:
    """Lê `/etc/os-release` sem tocar em nada. Vazio quando não existe."""
    caminho = Path("/etc/os-release")
    if not caminho.is_file():
        return {}
    dados: dict[str, str] = {}
    try:
        for linha in caminho.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" not in linha or linha.strip().startswith("#"):
                continue
            chave, valor = linha.split("=", 1)
            dados[chave.strip()] = valor.strip().strip('"').strip("'")
    except OSError:
        return {}
    return dados


def _versao_python() -> tuple[int, int, int] | None:
    try:
        partes = platform.python_version().split(".")
        return int(partes[0]), int(partes[1]), int(partes[2])
    except (ValueError, IndexError):
        return None


def medir() -> dict[str, Any]:
    """O que esta máquina tem — medido, não suposto.

    0.95.5 — é o que separa “o JARVIS diz que roda” de “o JARVIS diz que roda
    **aqui**”. As três perguntas que decidem: tem Python 3.9+, tem `pip`, tem
    `adb` (ou pode baixar).
    """
    release = _os_release()
    versao = _versao_python()
    achados = {
        "python3": bool(shutil.which("python3")),
        "pip": bool(shutil.which("pip3") or shutil.which("pip")),
        "adb": bool(shutil.which("adb")),
        "git": bool(shutil.which("git")),
        "ffmpeg": bool(shutil.which("ffmpeg")),
    }
    faltando = [nome for nome, tem in achados.items() if not tem]
    problemas: list[str] = []
    if versao and versao < (3, 9):
        problemas.append(
            f"Python {platform.python_version()}: o JARVIS precisa de 3.9 ou mais novo."
        )
    if not achados["pip"]:
        problemas.append("Sem `pip`: nada das bibliotecas pode ser instalado.")
    return {
        "sistema": platform.system(),
        "distribuicao": release.get("PRETTY_NAME") or release.get("NAME") or "",
        "id": release.get("ID", ""),
        "familia_base": release.get("ID_LIKE", ""),
        "versao": release.get("VERSION_ID", ""),
        "arquitetura": platform.machine(),
        "python": platform.python_version(),
        "python_ok": bool(versao and versao >= (3, 9)),
        "ferramentas": achados,
        "faltando": faltando,
        "problemas": problemas,
        "pode_rodar_aqui": not problemas,
        "conteiner": Path("/.dockerenv").exists() or bool(os.environ.get("JARVIS_CONTEINER")),
    }


def sistemas() -> list[dict[str, Any]]:
    """A lista toda, com o veredito curto de cada um. Não instala nada."""
    linhas = []
    for sistema in SISTEMAS:
        linhas.append(
            {
                "id": sistema.id,
                "nome": sistema.nome,
                "familia": sistema.familia,
                "situacao": _STATUS.get(sistema.situacao, sistema.situacao),
                "roda": sistema.situacao in {"roda", "roda_com_ressalva"},
                "porque": sistema.porque,
                "quebra": list(sistema.o_que_quebra),
                "ainda_existe": sistema.ainda_existe,
            }
        )
    return linhas


def plano(nome: str) -> dict[str, Any]:
    """O passo a passo para instalar **neste** sistema — ou a recusa explicada.

    Nunca devolve comando para quem não roda: em TempleOS/Lindows/Red Star/Gaming
    Edition a resposta é `pode_instalar=False` com o motivo. Sem plano inventado.
    """
    sistema = _achar(nome)
    aqui = medir() if sistema.familia in {"debian", "rpm", "windows"} else {}
    pode = bool(sistema.como_instalar)
    resposta: dict[str, Any] = {
        "id": sistema.id,
        "nome": sistema.nome,
        "situacao": _STATUS.get(sistema.situacao, sistema.situacao),
        "pode_instalar": pode,
        "porque": sistema.porque,
        "quebra": list(sistema.o_que_quebra),
        "comandos": list(sistema.como_instalar),
        "notas": dict(sistema.notas),
        "ano": sistema.ano,
    }
    if not pode:
        resposta["em_vez_disso"] = (
            sistema.notas.get("alternativa")
            or sistema.notas.get("o_que_seria_preciso")
            or sistema.notas.get("aviso")
            or "Não há caminho de instalação para este sistema."
        )
        return resposta

    # Aqui só entram os que têm caminho. A comparação é com o sistema ATUAL.
    if aqui:
        resposta["esta_maquina"] = {
            "distribuicao": aqui["distribuicao"],
            "pode_rodar_aqui": aqui["pode_rodar_aqui"],
            "faltando": aqui["faltando"],
            "problemas": aqui["problemas"],
        }
        # Se a máquina já é deste sistema, o passo a passo é o que falta, não o genérico.
        if aqui["pode_rodar_aqui"] and aqui["faltando"] == []:
            resposta["comandos"] = [
                "python3 -m venv .venv && . .venv/bin/activate",
                "pip install -r requirements.txt",
                "python iniciar.py",
            ]
            resposta["observacao"] = (
                "As ferramentas que o JARVIS usa já estão nesta máquina. "
                "O passo a passo virou só o que falta."
            )
    return resposta


def em_texto(nome: str) -> str:
    """A mesma resposta em linhas de terminal, sem jargão."""
    dados = plano(nome)
    linhas = [f"{dados['nome']} — {dados['situacao']}", ""]
    linhas.append(dados["porque"])
    if dados["quebra"]:
        linhas.append("")
        linhas.append("O que quebra:")
        linhas.extend(f"  - {item}" for item in dados["quebra"])
    if dados["pode_instalar"]:
        linhas.append("")
        linhas.append("Como instalar:")
        linhas.extend(f"  {comando}" for comando in dados["comandos"])
        if dados.get("observacao"):
            linhas.append("")
            linhas.append(dados["observacao"])
    else:
        linhas.append("")
        linhas.append("Não há instalação possível.")
        linhas.append(f"Em vez disso: {dados['em_vez_disso']}")
    return "\n".join(linhas)
