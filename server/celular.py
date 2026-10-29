"""Celular — operar o Android pelo PC, inclusive com a tela morta.

O pedido: *“e se não conseguir criar um programa para o JARVIS fazer essa
depuração mesmo sem nunca ter sido ligada?”* Vale separar o que é possível do que
não é, porque prometer o impossível é o pior serviço que este projeto poderia
prestar:

- **Impossível, por desenho do Android:** ligar a Depuração USB e tocar em
  “Permitir depuração USB?” sem uma pessoa na frente da tela. O sistema exige
  consentimento local e assinatura RSA por computador. Nenhum programa no PC
  contorna isso — nem este, nem os “unlock tools” que prometem milagre.
- **Possível, e é o que este módulo faz:** tudo em volta. Achar e instalar
  `adb` + `scrcpy` com hash, medir o estado do aparelho quando a depuração já
  existe, espelhar a tela numa janela do Windows, puxar fotos e documentos sem
  perder nada, e montar o plano exato — passo a passo, com os comandos — para o
  caso em que a depuração **nunca** foi ligada.

O caminho que funciona sem depuração nenhuma é o `scrcpy --otg`: o PC se passa
por teclado e mouse USB e opera o aparelho às cegas. Este módulo entrega a
sequência de teclas, o mapa do menu e as alternativas (TalkBack, tela de teste de
bancada, TWRP quando o bootloader já está desbloqueado).

Como todo o resto do projeto: nada roda sem a variável `JARVIS_HOST_CELULAR=1`,
sem confirmação e — fora do modo dono — sem o token de host.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen

from . import dados

AMBIENTE = "JARVIS_HOST_CELULAR"
TIMEOUT = 45
MAX_SAIDA = 4_000
MAX_ZIP = 400 * 1024 * 1024

# Fontes oficiais. O scrcpy muda de versão a cada release; o endereço do arquivo
# é resolvido na hora pela API do GitHub, e não fixado aqui.
URL_PLATFORM_TOOLS = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
API_SCRCPY = "https://api.github.com/repos/Genymobile/scrcpy/releases/latest"
PAGINA_SCRCPY = "https://github.com/Genymobile/scrcpy/releases/latest"

# Pastas do armazenamento compartilhado que o `adb pull` pode copiar. O que não
# está aqui não é lido — nada de `/data`, nada de chave de app, nada de conta.
PASTAS_PERMITIDAS = {
    "dcim": "DCIM",
    "camera": "DCIM/Camera",
    "pictures": "Pictures",
    "download": "Download",
    "downloads": "Download",
    "documents": "Documents",
    "documentos": "Documents",
    "movies": "Movies",
    "music": "Music",
    "whatsapp": "WhatsApp",
    "telegram": "Telegram",
}

ADB_NOMES = ("adb.exe", "adb")
SCRCPY_NOMES = ("scrcpy.exe", "scrcpy")


class CelularError(RuntimeError):
    """Erro de uso do módulo, sempre em português e sempre acionável."""


def ligado() -> bool:
    return os.environ.get(AMBIENTE, "0").strip() == "1"


def _exigir_ligado() -> None:
    if not ligado():
        raise CelularError(
            f"Operar o celular está desligado. Suba a API com {AMBIENTE}=1 "
            "(junto de JARVIS_HOST_REDE=1, que é de onde saem as ferramentas)."
        )


def pasta_ferramentas() -> Path:
    return dados.raiz() / "ferramentas"


def _achar(nomes: tuple[str, ...]) -> Path | None:
    """Procura o executável no PATH e na pasta de ferramentas do projeto.

    A busca fixa cobre o layout canônico (`ferramentas/adb/adb.exe`), mas o zip do
    scrcpy extrai numa pasta com a versão no nome (`scrcpy-win64-v3.3.1/`). Por
    isso existe o passo recursivo: sem ele, ter baixado direito não bastava.
    """
    for nome in nomes:
        achado = shutil.which(nome)
        if achado:
            return Path(achado)
    for nome in nomes:
        for raiz in (pasta_ferramentas() / "platform-tools", pasta_ferramentas() / "scrcpy", pasta_ferramentas()):
            candidato = raiz / nome
            if candidato.is_file():
                return candidato
    base = pasta_ferramentas()
    if not base.is_dir():
        return None
    for nome in nomes:
        encontrados = sorted(
            (caminho for caminho in base.rglob(nome) if caminho.is_file()),
            key=lambda caminho: (len(caminho.parts), str(caminho)),
        )
        if encontrados:
            return encontrados[0]
    return None


def ferramentas() -> dict[str, Any]:
    """Onde estão `adb` e `scrcpy` — ou o que falta. Não executa nada."""
    adb = _achar(ADB_NOMES)
    scrcpy = _achar(SCRCPY_NOMES)
    faltando = [nome for nome, achado in (("adb (platform-tools)", adb), ("scrcpy", scrcpy)) if not achado]
    return {
        "ligado": ligado(),
        "variavel": AMBIENTE,
        "pasta": str(pasta_ferramentas()),
        "adb": str(adb) if adb else "",
        "scrcpy": str(scrcpy) if scrcpy else "",
        "completo": not faltando,
        "faltando": faltando,
        "nota": (
            "As duas ferramentas estão instaladas." if not faltando
            else "Peça `celular.preparar` para baixar e conferir as duas ferramentas."
        ),
    }


def _rodar(argumentos: list[str], timeout: int = TIMEOUT) -> tuple[int, str, str]:
    # No Windows, sem isto cada chamada do adb abre e fecha uma janela preta por
    # cima da interface. CREATE_NO_WINDOW só existe lá.
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
        raise CelularError(f"O executável “{argumentos[0]}” não está instalado.") from exc
    except subprocess.TimeoutExpired as exc:
        raise CelularError(
            f"“{' '.join(argumentos)}” passou de {timeout}s e foi interrompido. "
            "Na primeira vez o adb sobe um serviço próprio e o antivírus costuma "
            "escaneá-lo; tente de novo. Se repetir, libere o adb no antivírus."
        ) from exc
    except OSError as exc:
        raise CelularError(f"O sistema recusou rodar “{argumentos[0]}”: {exc}") from exc
    return concluido.returncode, concluido.stdout or "", concluido.stderr or ""


def _cortar(texto: str, limite: int = MAX_SAIDA) -> str:
    limpo = (texto or "").strip()
    return limpo if len(limpo) <= limite else limpo[:limite] + "\n… (saída cortada)"


def parsear_dispositivos(saida: str) -> list[dict[str, str]]:
    """Lê a tabela do `adb devices -l` — uma linha por aparelho conectado."""
    aparelhos: list[dict[str, str]] = []
    for linha in (saida or "").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("List of devices") or linha.startswith("*"):
            continue
        partes = linha.split()
        if len(partes) < 2:
            continue
        serial, estado = partes[0], partes[1]
        if estado not in {"device", "unauthorized", "offline", "recovery", "sideload", "bootloader", "no"}:
            continue
        item = {"serial": serial, "estado": estado}
        for extra in partes[2:]:
            if ":" in extra:
                chave, valor = extra.split(":", 1)
                if chave in {"model", "product", "device", "transport_id"}:
                    item[chave] = valor
        aparelhos.append(item)
    return aparelhos


# A sonda pergunta ao Windows o que está na USB e, principalmente, o InstanceId:
# é lá que está o VID/PID. Sem isso, "USB Composite Device" — nome genérico do
# driver que qualquer webcam, hub ou teclado usa — passava por celular, e o
# plano mandava a pessoa ligar a Depuração USB de um aparelho que nem estava
# conectado.
VID_SAMSUNG = "04e8"
# A sonda pergunta por USB, mas também por tudo que um celular vira no Windows:
# "Portable Devices"/WPD (MTP), modem, Android USB, e — o mais revelador — o
# dispositivo que a porta viu e o Windows não conseguiu identificar
# ("Dispositivo USB desconhecido", VID_0000). Esse último é a assinatura de
# cabo só-carga ou conector sem contato, e sem ele a resposta diria "não é o
# celular" quando na verdade o celular está lá, mudo.
#
# A sétima coluna é o **modelo** (SM-A346B, SM-G610M): o Windows publica isso em
# `DEVPKEY_Device_BusReportedDeviceDesc` e ele é a única coisa que separa um
# Galaxy de outro quando o nome do driver é o genérico "USB Composite Device".
# A consulta só é feita nos candidatos a aparelho — numa máquina de 4 GB cada
# `Get-PnpDeviceProperty` custa uma ida ao registro.
_SONDA_WINDOWS = (
    "$d = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | "
    "Where-Object { $_.Class -in @('USB','WPD','Portable Devices','AndroidUsbDeviceClass','Modem') "
    "-or $_.FriendlyName -match 'SAMSUNG|Android|Galaxy|ADB|MTP|SM-|esconhecid|nknown|escritor|escriptor' "
    "-or $_.InstanceId -match 'VID_04E8' }; "
    "if ($d) { $d | ForEach-Object { "
    "$m = ''; "
    "if ($_.InstanceId -match 'VID_04E8' -or $_.FriendlyName -match 'SAMSUNG|Galaxy|SM-|MTP|Android') { "
    "try { $p = Get-PnpDeviceProperty -InstanceId $_.InstanceId "
    "-KeyName 'DEVPKEY_Device_BusReportedDeviceDesc' -ErrorAction SilentlyContinue; "
    "if ($p -and $p.Data) { $m = [string]$p.Data } } catch { $m = '' } }; "
    "\"$($_.Status)`t$($_.Class)`t$($_.FriendlyName)`t$($_.InstanceId)`t$($_.Manufacturer)`t$($_.Problem)`t$m\" } }"
)

# Nome que só existe em aparelho, não em driver genérico.
_RE_NOME_DE_APARELHO = re.compile(r"SAMSUNG|Galaxy|Android|ADB|MTP|SM-\w", re.I)


def _vid(instance_id: str) -> str:
    achado = re.search(r"VID_([0-9A-Fa-f]{4})", instance_id or "")
    return achado.group(1).lower() if achado else ""


_RE_MODELO = re.compile(r"^(SM-[A-Z0-9]{2,}|GT-[A-Z0-9]{2,}|SCH-[A-Z0-9]{2,}|SAMSUNG[- ]?[A-Z0-9]+)$", re.I)


def _modelo_limpo(instance: str, modelo: str) -> str:
    """Aceita o modelo só quando é de aparelho e combina com o VID da Samsung.

    Em dispositivo de outro fabricante o mesmo campo traz o caminho interno do
    Windows (algo como `\\Device\\USBPDO-3`), que não ajuda ninguém.
    """
    modelo = (modelo or "").strip()
    if not modelo or modelo.startswith("\\"):
        return ""
    if not _RE_MODELO.match(modelo):
        return ""
    # Só vale em dispositivo com o VID da Samsung: um "SM-..." pendurado em
    # aparelho de outra marca é ruído do registro, não modelo de celular.
    if "vid_04e8" not in (instance or "").lower():
        return ""
    return modelo.upper()


def _limpar_sonda(linhas: list[str]) -> list[dict[str, str]]:
    """Lê a saída da sonda: status, classe, nome, InstanceId, fabricante e problema."""
    achados: list[dict[str, str]] = []
    for linha in linhas:
        partes = (linha or "").rstrip("\r").split("\t")
        if len(partes) < 3:
            continue
        nome = partes[2].strip()
        if not nome:
            continue
        instance = partes[3].strip() if len(partes) > 3 else ""
        fabricante = partes[4].strip() if len(partes) > 4 else ""
        problema = partes[5].strip() if len(partes) > 5 else ""
        # `DEVPKEY_Device_BusReportedDeviceDesc`: o modelo que o próprio aparelho
        # informa ("SM-A346B", "SM-G610M"). Sem ele, todo Galaxy é "USB Composite
        # Device" e não há como saber qual dos dois está na porta.
        modelo = partes[6].strip() if len(partes) > 6 else ""
        achados.append(
            {
                "status": partes[0].strip(),
                "classe": partes[1].strip(),
                "nome": nome,
                "instance": instance,
                "vid": _vid(instance),
                "fabricante": fabricante,
                "problema": "" if problema.upper() in {"CM_PROB_NONE", "NONE"} else problema,
                "modelo": _modelo_limpo(instance, modelo),
            }
        )
    vistos: set[str] = set()
    unicos: list[dict[str, str]] = []
    for item in achados:
        chave = (item["instance"] or item["nome"]).lower()
        if chave in vistos:
            continue
        vistos.add(chave)
        unicos.append(item)
    # 40 é teto de sanidade, não de exibição: a comparação entre duas checagens
    # precisa da lista inteira (o chat mostra só os primeiros).
    return unicos[:40]


def e_aparelho(item: dict[str, str]) -> bool:
    """É o celular — não um webcam, hub ou teclado usando o mesmo driver?

    Samsung é identificada pelo VID (04E8), que vem do hardware e não depende de
    nome de driver instalado. Nome com marca/modelo também vale; "USB Composite
    Device" sozinho, não.
    """
    if item.get("vid") == VID_SAMSUNG:
        return True
    if _RE_NOME_DE_APARELHO.search(item.get("nome") or ""):
        return True
    return "samsung" in (item.get("fabricante") or "").lower()


def windows_ve(*, rodar: Callable[[list[str]], tuple[int, str, str]] | None = None) -> dict[str, Any]:
    """O que o **Windows** vê na USB, sem passar pelo adb. Só leitura.

    É a pergunta que decide o próximo passo quando o `adb devices` volta vazio:
    - Windows vê o **celular** e ele está OK → cabo e porta estão bons; falta a
      Depuração USB (com a tela morta, o problema é o consentimento);
    - Windows vê o celular com problema (driver) → instalar o Samsung USB Driver;
    - Windows só vê dispositivo USB genérico → o celular **não** está na porta;
    - Windows não vê nada → cabo, porta ou aparelho desligado.
    """
    if os.name != "nt" or sys.platform != "win32":
        return {
            "consulta": False,
            "motivo": "A sonda de USB só existe no Windows.",
            "dispositivos": [],
            "telefones": [],
            "visivel": False,
            "com_problema": False,
        }
    executar = rodar or _rodar
    try:
        codigo, saida, erro = executar(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _SONDA_WINDOWS]
        )
    except CelularError:
        return {
            "consulta": False,
            "motivo": "Não consegui consultar o Windows.",
            "dispositivos": [],
            "telefones": [],
            "visivel": False,
            "com_problema": False,
        }
    if codigo != 0 and not saida.strip():
        return {
            "consulta": False,
            "motivo": _cortar(erro or "O PowerShell não respondeu."),
            "dispositivos": [],
            "telefones": [],
            "visivel": False,
            "com_problema": False,
        }
    achados = _limpar_sonda(saida.splitlines())
    telefones = [item for item in achados if e_aparelho(item)]
    com_problema = [item for item in telefones if item["status"] and item["status"].upper() != "OK"]
    desconhecidos = [item for item in achados if item not in telefones and e_desconhecido(item)]
    genericos = [item for item in achados if item not in telefones and item not in desconhecidos]
    resultado = {
        "consulta": True,
        "dispositivos": achados,
        "telefones": telefones,
        "genericos": genericos,
        "desconhecidos": desconhecidos,
        "visivel": bool(telefones),
        "com_problema": bool(com_problema),
    }
    resultado["resumo"] = _resumo_da_sonda(resultado)
    return resultado


def sem_driver_samsung(telefones: list[dict[str, str]]) -> bool:
    """Aparelho da Samsung reconhecido pelo VID, mas com nome/driver genérico.

    Quando o driver da Samsung não está instalado, o Windows chama o aparelho de
    "USB Composite Device" ou "MTP" — mesmo com a Depuração USB ligada, o adb não
    enxerga esse aparelho. Instalar o driver é o passo que destrava.
    """
    for item in telefones:
        nome = (item.get("nome") or "").lower()
        if item.get("vid") == VID_SAMSUNG and "samsung" not in nome:
            return True
    return False


# "Dispositivo USB desconhecido (falha na solicitação do descritor do
# dispositivo)" / "Unknown USB Device (Device Descriptor Request Failed)".
_RE_DESCONHECIDO = re.compile(r"esconhecid|unknown|escritor|escriptor", re.I)


def e_desconhecido(item: dict[str, str]) -> bool:
    """A porta viu alguma coisa, mas o Windows não conseguiu perguntar o quê.

    Esse item (VID_0000, sem nome de verdade) aparece quando o PC energiza o
    aparelho e a conversa USB não acontece: cabo só de carga, conector com
    poeira/oxidação ou porta fraca. Não é falta de driver nem de Depuração USB —
    e é um diagnóstico diferente de "a porta está vazia".
    """
    return bool(_RE_DESCONHECIDO.search(item.get("nome") or ""))


def _arquivo_da_sonda() -> Path:
    """Onde fica a última lista de USB — na pasta de dados, não no repositório."""
    return dados.raiz() / "celular" / "usb-ultima.json"


def _chave(item: dict[str, str]) -> str:
    return (item.get("instance") or item.get("nome") or "").strip().lower()


def _ler_ultima_sonda() -> dict[str, Any] | None:
    try:
        anterior = json.loads(_arquivo_da_sonda().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return anterior if isinstance(anterior, dict) else None


def _guardar_ultima_sonda(dispositivos: list[dict[str, str]]) -> None:
    arquivo = _arquivo_da_sonda()
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(
        json.dumps(
            {"quando": datetime.now().isoformat(timespec="seconds"), "dispositivos": dispositivos},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )


def _hora_curta(quando: str) -> str:
    try:
        return datetime.fromisoformat(str(quando)).strftime("%H:%M")
    except (TypeError, ValueError):
        return "?"


def _nomes(itens: list[dict[str, str]], limite: int = 2) -> str:
    return ", ".join(_descrever(item) for item in itens[:limite]) + (
        f" e mais {len(itens) - limite}" if len(itens) > limite else ""
    )


def comparar_com_ultima(sonda: dict[str, Any]) -> dict[str, Any]:
    """O teste conectar/desconectar, feito pelo JARVIS em vez de pela pessoa.

    A sonda de agora é comparada com a da checagem anterior (guardada em
    `storage/celular/usb-ultima.json`) e a lista atual substitui a antiga. Assim
    "nada mudou" deixa de ser uma conclusão que a pessoa tira de olho: é uma
    comparação de máquina — e ela vale para qualquer dispositivo, não só Samsung.
    """
    atual = sonda.get("dispositivos") or []
    anterior = _ler_ultima_sonda()
    _guardar_ultima_sonda(atual)
    if anterior is None:
        return {
            "primeira": True,
            "mudou": False,
            "novos": [],
            "saidos": [],
            "quando": "",
            "frase": "Guardei esta lista: na próxima checagem eu comparo sozinho e digo o que mudou.",
        }
    antes = {_chave(item): item for item in anterior.get("dispositivos") or [] if isinstance(item, dict)}
    agora = {_chave(item): item for item in atual}
    novos = [item for chave, item in agora.items() if chave not in antes]
    saidos = [item for chave, item in antes.items() if chave not in agora]
    quando = str(anterior.get("quando") or "")
    hora = _hora_curta(quando)
    if not novos and not saidos:
        frase = (
            f"Comparando com a checagem das {hora}: a lista está idêntica — a porta USB "
            "não viu nada novo entre uma vez e outra."
        )
    else:
        partes = []
        if novos:
            partes.append(f"entrou {_nomes(novos)}")
        if saidos:
            partes.append(f"saiu {_nomes(saidos)}")
        frase = f"Comparando com a checagem das {hora}: " + "; ".join(partes) + "."
        if any(e_desconhecido(item) for item in novos):
            frase += (
                " A porta viu algo, mas o Windows não identificou o que era: isso é cabo "
                "(precisa ser de dados) ou conector, não driver."
            )
        elif any(e_aparelho(item) for item in novos):
            frase += " O celular apareceu na USB agora — o próximo passo é driver/depuração."
    return {
        "primeira": False,
        "mudou": bool(novos or saidos),
        "novos": novos,
        "saidos": saidos,
        "quando": quando,
        "frase": frase,
    }


# Códigos do Windows que valem tradução; o resto sai como veio.
_PROBLEMAS = {
    "CM_PROB_FAILED_START": "driver não iniciou",
    "CM_PROB_FAILED_INSTALL": "driver não instalou",
    "CM_PROB_FAILED_POST_START": "parou logo depois de iniciar",
    "CM_PROB_DEVICE_DISABLED": "desativado",
    "CM_PROB_DRIVER_FAILED_LOAD": "driver não carregou",
}


def _traduzir_problema(codigo: str) -> str:
    return _PROBLEMAS.get((codigo or "").upper(), codigo)


def _nome_curto(item: dict[str, str], limite: int = 44) -> str:
    """Nome para caber numa linha de chat, sem cortar a parte que informa.

    No desconhecido, o que interessa é "Dispositivo USB desconhecido"; o
    "(Falha na solicitação do descritor…)" entre parênteses só ocupa espaço.
    """
    nome = (item.get("nome") or "").strip()
    if e_desconhecido(item):
        nome = (nome.split("(")[0] or nome).strip()
    return nome[:limite]


def _arquivo_de_vistos() -> Path:
    """Quem já apareceu nesta máquina — a memória que prova "a porta funciona"."""
    return dados.raiz() / "celular" / "aparelhos-vistos.json"


def _ler_vistos() -> dict[str, Any]:
    try:
        dados_lidos = json.loads(_arquivo_de_vistos().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dados_lidos if isinstance(dados_lidos, dict) else {}


def registrar_aparelhos(telefones: list[dict[str, str]]) -> None:
    """Guarda o que apareceu, para o próximo "nada aparece" não culpar o PC.

    Quando o A34 entra e o J7 não, essa memória é o que permite dizer a verdade
    em vez de repetir o teste: **esta porta já viu um Samsung**.
    """
    if not telefones:
        return
    vistos = _ler_vistos()
    agora = datetime.now().isoformat(timespec="seconds")
    mudou = False
    for item in telefones:
        chave = f"{item.get('vid') or '?'}|{item.get('modelo') or item.get('nome') or '?'}"
        if chave in vistos and not item.get("modelo"):
            continue
        vistos[chave] = {
            "vid": item.get("vid") or "",
            "modelo": item.get("modelo") or "",
            "nome": (item.get("nome") or "")[:64],
            "quando": agora,
        }
        mudou = True
    if not mudou:
        return
    arquivo = _arquivo_de_vistos()
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(json.dumps(vistos, ensure_ascii=False, indent=1), encoding="utf-8")


def aparelhos_ja_vistos() -> list[dict[str, str]]:
    """Os aparelhos Samsung que já passaram por esta máquina, o mais recente antes."""
    itens = [
        item
        for item in _ler_vistos().values()
        if isinstance(item, dict) and item.get("vid") == VID_SAMSUNG
    ]
    itens.sort(key=lambda item: str(item.get("quando") or ""), reverse=True)
    return itens


def _frase_do_que_ja_passou() -> str:
    vistos = aparelhos_ja_vistos()
    if not vistos:
        return ""
    recente = vistos[0]
    quem = recente.get("modelo") or recente.get("nome") or "um Samsung"
    try:
        quando = datetime.fromisoformat(str(recente.get("quando"))).strftime("%d/%m %H:%M")
    except (TypeError, ValueError):
        quando = "antes"
    return (
        f"Esta porta já viu um Samsung ({quem}, em {quando}): o PC, a porta e a "
        "instalação do Windows estão provados bons. O que não aparece agora é o "
        "aparelho que você plugou — cabo de dados ou o conector dele."
    )


def _descrever(item: dict[str, str]) -> str:
    vid = ""
    if item.get("vid") and item["vid"] != "0000":
        vid = f" VID_{item['vid'].upper()}"
    modelo = f" {item['modelo']}" if item.get("modelo") else ""
    return f"{_nome_curto(item)}{modelo}{vid}"


def _resumo_da_sonda(sonda: dict[str, Any]) -> str:
    telefones = sonda.get("telefones") or []
    genericos = sonda.get("genericos") or []
    desconhecidos = sonda.get("desconhecidos") or []
    if telefones:
        nomes = ", ".join(_descrever(item) for item in telefones[:3])
        if sonda.get("com_problema"):
            return f"O Windows vê o celular, mas com problema de driver ({nomes})."
        return f"O Windows vê o celular ({nomes})."
    if desconhecidos:
        nomes = _nomes(desconhecidos)
        return (
            "A porta USB viu um dispositivo que o Windows NÃO conseguiu identificar "
            f"({nomes}). Isso é o que aparece quando o PC energiza o aparelho mas a "
            "conversa não acontece: cabo só de carga, conector com poeira/oxidação ou "
            "porta fraca — não é driver nem Depuração USB."
        )
    if genericos:
        quantos = len(genericos)
        exemplo = _descrever(genericos[0])
        return (
            f"O Windows vê {quantos} dispositivo(s) USB, mas nenhum parece ser o celular "
            f"(ex.: {exemplo}, que não é Samsung)."
        )
    return "O Windows não vê nenhum aparelho na USB."


def estado(*, rodar: Callable[[list[str]], tuple[int, str, str]] | None = None) -> dict[str, Any]:
    """Mede o que o `adb` vê. Só leitura: nenhum comando muda o aparelho."""
    info = ferramentas()
    if not info["adb"]:
        return {
            "ferramentas": info,
            "executado": False,
            "motivo": "O `adb` não está instalado. Rode `celular.preparar` primeiro.",
            "aparelhos": [],
        }
    if not ligado():
        return {
            "ferramentas": info,
            "executado": False,
            "motivo": f"{AMBIENTE} está desligado; não vou executar nada sem a variável.",
            "aparelhos": [],
        }
    executar = rodar or _rodar
    codigo, saida, erro = executar([info["adb"], "devices", "-l"])
    if codigo != 0 and "server version" in f"{saida}{erro}".lower():
        # Um adb de outra ferramenta já está na porta 5037. Derruba e sobe o nosso.
        executar([info["adb"], "kill-server"])
        codigo, saida, erro = executar([info["adb"], "devices", "-l"])
    aparelhos = parsear_dispositivos(saida)
    if codigo != 0 and not aparelhos:
        return {
            "ferramentas": info,
            "executado": True,
            "codigo": codigo,
            "motivo": _cortar(erro or saida) or f"O adb terminou com código {codigo}.",
            "aparelhos": [],
        }
    resultado = {
        "ferramentas": info,
        "executado": True,
        "codigo": codigo,
        "aparelhos": aparelhos,
        "saida": _cortar(saida),
        "situacao": situacao_de(aparelhos),
    }
    if not aparelhos:
        # Sem aparelho no adb a pergunta seguinte é sempre a mesma: o Windows vê?
        sonda = windows_ve(rodar=executar)
        if sonda.get("consulta") and sonda.get("telefones"):
            try:
                registrar_aparelhos(sonda["telefones"])
            except OSError:
                pass
        if sonda.get("consulta"):
            # O teste conectar/desconectar sai pronto daqui: comparo com a
            # checagem anterior em vez de pedir que a pessoa compare listas.
            try:
                sonda["comparacao"] = comparar_com_ultima(sonda)
            except OSError:
                sonda["comparacao"] = {}
        resultado["windows"] = sonda
    return resultado


# ------------------------------------------------------------------ rede local
#
# A pergunta que motivou isto: *"ele está no Wi-Fi de casa, não dá para acessar
# por aí?"* Não por adivinhação — por medição. O que a rede pode (e não pode) dar:
#
# - **Não substitui o cabo.** O Android não abre porta nenhuma por padrão. O
#   `adb` por rede existe em duas formas: `adb tcpip 5555`, que precisa ser
#   rodado **uma vez pelo cabo**, ou a "Depuração sem fio" do Android 11+ (com
#   código de pareamento na tela). Sem uma das duas, não há o que conectar.
# - **Dá o retrato:** se o aparelho está na rede, qual IP/MAC/nome ele tem e se
#   alguma porta está aberta (a 5555 é o jackpot; 8080/9000 aparecem quando há
#   app com servidor instalado).
# - **Derrubar o Wi-Fi não dá acesso a nada.** Quando ele volta, reconecta ao
#   roteador como antes; quem está na rede só vê tráfego, não o aparelho.
#
# Tudo aqui é leitura: um toque TCP em cada host para popular a tabela ARP, sem
# enviar pacote de dados a ninguém e sem tentar login.

PORTAS_DE_APARELHO = {
    5555: "adb sem fio",
    8022: "SSH de app (Termux)",
    8080: "servidor HTTP de app",
    8443: "servidor HTTPS de app",
    9000: "servidor de app",
    62078: "serviço de sincronização",
}

# Prefixos Samsung registrados no IEEE. Lista parcial: serve para marcar
# "provavelmente Samsung", não para provar — o nome do host diz mais.
_OUIS_SAMSUNG = frozenset(
    {
        "0012fb", "001632", "002119", "0021d1", "3423ba", "38aa3c", "503237",
        "5c0a5b", "781fdb", "78abbb", "8c7712", "8c71f8", "a02195", "b479a7",
        "c0bdd1", "c819f7", "d022be", "d857ef", "dc7144", "e8508b", "f409d8",
        "f49f54",
    }
)


def _ip_local() -> str:
    """IP desta máquina na rede — sem enviar pacote (o UDP só resolve a rota)."""
    sonda = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sonda.connect(("8.8.8.8", 80))
        return str(sonda.getsockname()[0])
    except OSError:
        return ""
    finally:
        sonda.close()


def _prefixo(ip: str) -> str:
    partes = ip.split(".")
    return ".".join(partes[:3]) if len(partes) == 4 else ""


def _ler_arp(tabela: str) -> dict[str, str]:
    """Lê `arp -a` (Windows e Linux) e devolve {ip: mac}."""
    achados: dict[str, str] = {}
    for linha in (tabela or "").splitlines():
        mac = re.search(r"\b([0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5})\b", linha)
        ip = re.search(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b", linha)
        if not mac or not ip:
            continue
        achados[ip.group(1)] = mac.group(1).lower().replace("-", ":")
    return achados


def _endereco_de_dispositivo(ip: str, mac: str) -> bool:
    """Broadcast, endereço de rede e multicast não são dispositivos.

    A tabela ARP guarda a linha `192.168.15.255` (broadcast) e às vezes
    `...0` da faixa — listar isso como "dispositivo que respondeu" só confunde
    quem está contando o que tem em casa.
    """
    if ip.rsplit(".", 1)[-1] in {"0", "255"}:
        return False
    if (mac or "").lower() in {"ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00"}:
        return False
    return ip.split(".", 1)[0] not in {"224", "239", "255"}


def _nome_util(ip: str, nome: str) -> str:
    """`gethostbyaddr` devolve o próprio IP quando não resolve — isso não é nome."""
    nome = (nome or "").strip()
    if not nome or nome == ip or re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", nome):
        return ""
    return nome


def _fabricante_do_mac(mac: str) -> str:
    prefixo = (mac or "").replace(":", "")[:6].lower()
    return "prefixo Samsung" if prefixo in _OUIS_SAMSUNG else ""


def _gethostbyaddr(ip: str) -> str:
    try:
        return socket.gethostbyaddr(ip)[0]
    except (OSError, IndexError):
        return ""


def _tocar_hosts(prefixo: str, tempo: float = 0.2, limite: float = 8.0) -> None:
    """Um connect TCP em cada IP: quem existe responde ARP e entra na tabela.

    Não manda dado nenhum — a resposta não importa, só o fato de o host existir.
    """
    from concurrent.futures import ThreadPoolExecutor, wait  # noqa: PLC0415

    def tocar(numero: int) -> None:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(tempo)
                s.connect_ex((f"{prefixo}.{numero}", 9))
        except OSError:
            pass

    with ThreadPoolExecutor(max_workers=64) as pool:
        futuros = [pool.submit(tocar, numero) for numero in range(1, 255)]
        wait(futuros, timeout=limite)


def _portas_abertas(hosts: list[str], tempo: float = 0.3) -> dict[str, list[int]]:
    from concurrent.futures import ThreadPoolExecutor, wait  # noqa: PLC0415

    resultado: dict[str, list[int]] = {ip: [] for ip in hosts}

    def testar(ip: str, porta: int) -> None:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(tempo)
                if s.connect_ex((ip, porta)) == 0:
                    resultado[ip].append(porta)
        except OSError:
            pass

    with ThreadPoolExecutor(max_workers=64) as pool:
        futuros = [pool.submit(testar, ip, porta) for ip in hosts for porta in PORTAS_DE_APARELHO]
        wait(futuros, timeout=20.0)
    return resultado


def rede(
    *,
    rodar: Callable[[list[str]], tuple[int, str, str]] | None = None,
    tocar: Callable[[str], None] | None = None,
    ip_local: str = "",
) -> dict[str, Any]:
    """Retrato da rede local: o celular está nela? Alguma porta aberta? Só leitura."""
    if not ligado():
        return {
            "executado": False,
            "motivo": f"{AMBIENTE} está desligado, então nada foi executado.",
            "hosts": [],
        }
    meu_ip = ip_local or _ip_local()
    prefixo = _prefixo(meu_ip)
    if not prefixo:
        return {
            "executado": False,
            "motivo": "Este PC não está em rede (sem IP de rede local) — a varredura não tem o que ver.",
            "hosts": [],
        }
    executar = rodar or _rodar
    try:
        if tocar:
            tocar(prefixo)
        else:
            _tocar_hosts(prefixo)
        codigo, saida, erro = executar(["arp", "-a"])
    except (CelularError, OSError):
        return {
            "executado": False,
            "motivo": "Não consegui ler a tabela ARP do sistema (comando arp -a).",
            "hosts": [],
        }
    if codigo != 0 and not saida.strip():
        return {
            "executado": False,
            "motivo": _cortar(erro or "O comando arp não respondeu."),
            "hosts": [],
        }
    tabela = _ler_arp(saida)
    enderecos = sorted(
        (
            ip
            for ip in tabela
            if _prefixo(ip) == prefixo and ip != meu_ip and _endereco_de_dispositivo(ip, tabela[ip])
        ),
        key=lambda ip: int(ip.split(".")[-1]),
    )[:32]
    portas = _portas_abertas(enderecos) if enderecos else {}
    hosts = []
    for ip in enderecos:
        mac = tabela[ip]
        abertas = sorted(portas.get(ip) or [])
        hosts.append(
            {
                "ip": ip,
                "mac": mac,
                "nome": _nome_util(ip, _gethostbyaddr(ip)),
                "fabricante": _fabricante_do_mac(mac),
                "portas": abertas,
                "servicos": [PORTAS_DE_APARELHO.get(porta, str(porta)) for porta in abertas],
            }
        )
    return {
        "executado": True,
        "pc": meu_ip,
        "rede": f"{prefixo}.0/24",
        "hosts": hosts,
        "com_adb": [host for host in hosts if 5555 in host["portas"]],
    }


# ------------------------------------------------- o que passou (histórico)
#
# A vigia olha a USB a cada 2 segundos. Um conector com solda trincada pode
# apresentar o aparelho por menos que isso — e a janela diria "nada mudou" com
# toda a honestidade. O log de eventos do Windows guarda esses instantes: aqui a
# leitura é do canal System (não exige administrador) filtrado por PnP/USB.

_EVENTOS_WINDOWS = (
    "$desde = (Get-Date).AddMinutes(-{minutos}); "
    "try { $e = @(Get-WinEvent -FilterHashtable @{{LogName='System'; StartTime=$desde}} -ErrorAction Stop) } "
    "catch {{ $e = @() }}; "
    "$e | Where-Object {{ $_.ProviderName -match 'PnP|USB|DriverFrameworks|Hub' }} | "
    "ForEach-Object {{ \"$($_.TimeCreated.ToString('HH:mm:ss'))`t$($_.Id)`t$($_.ProviderName)`t"
    "$($_.Message -replace '`r|`n', ' ')\" }}"
)


def _linha_de_evento(linha: str) -> dict[str, str] | None:
    partes = (linha or "").rstrip("\r").split("\t")
    if len(partes) < 3:
        return None
    hora, codigo, provedor = partes[0].strip(), partes[1].strip(), partes[2].strip()
    mensagem = partes[3].strip() if len(partes) > 3 else ""
    if not hora or not provedor:
        return None
    return {
        "hora": hora,
        "codigo": codigo,
        "provedor": provedor,
        "mensagem": mensagem[:240],
    }


def _menciona_aparelho(evento: dict[str, str]) -> bool:
    texto = f"{evento.get('mensagem') or ''} {evento.get('provedor') or ''}".lower()
    return any(marca in texto for marca in ("04e8", "samsung", "galaxy", "sm-", "android"))


def eventos(*, minutos: int = 30, rodar: Callable[[list[str]], tuple[int, str, str]] | None = None) -> dict[str, Any]:
    """O que o Windows registrou na USB no período — inclusive o que durou pouco."""
    if not ligado():
        return {"executado": False, "motivo": f"{AMBIENTE} está desligado, então nada foi executado.", "eventos": []}
    if os.name != "nt" or sys.platform != "win32":
        return {"executado": False, "motivo": "O histórico de eventos do Windows só existe no Windows.", "eventos": []}
    minutos = max(1, min(int(minutos or 30), 1440))
    executar = rodar or _rodar
    try:
        codigo, saida, erro = executar(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _EVENTOS_WINDOWS.format(minutos=minutos)]
        )
    except CelularError:
        return {"executado": False, "motivo": "Não consegui ler o histórico do Windows.", "eventos": []}
    if codigo != 0 and not saida.strip():
        return {
            "executado": False,
            "motivo": _cortar(erro or "O PowerShell não respondeu."),
            "eventos": [],
            "minutos": minutos,
        }
    lidos = [_linha_de_evento(linha) for linha in saida.splitlines()]
    lista = [evento for evento in lidos if evento]
    return {
        "executado": True,
        "minutos": minutos,
        "eventos": lista[:60],
        "total": len(lista),
        "com_aparelho": [evento for evento in lista if _menciona_aparelho(evento)][:20],
    }


def resumo_de_eventos(medido: dict[str, Any]) -> dict[str, Any]:
    """Traduz o histórico em resposta: o aparelho chegou a ser visto, mesmo rápido?"""
    if not medido.get("executado"):
        return {
            "titulo": "Não deu para ler o histórico",
            "resposta": str(medido.get("motivo") or "A leitura não rodou."),
            "proximo_passo": "A vigia (vigiar-usb.bat) continua sendo o teste ao vivo; o histórico é o que fica depois.",
            "eventos": medido,
        }
    minutos = medido.get("minutos") or 30
    eventos_lidos = medido.get("eventos") or []
    com_aparelho = medido.get("com_aparelho") or []
    linhas = [f"Últimos {minutos} min no log do Windows: {medido.get('total', 0)} evento(s) de USB/PnP."]
    if eventos_lidos:
        for evento in eventos_lidos[:10]:
            linhas.append(f"• {evento['hora']} #{evento['codigo']} {evento['provedor']} — {evento['mensagem'][:140]}")
        if len(eventos_lidos) > 10:
            linhas.append(f"• … e mais {len(eventos_lidos) - 10}")
    if com_aparelho:
        titulo = "O Windows viu o aparelho — mesmo que por pouco tempo"
        resposta = "\n\n".join(
            linhas
            + [
                "Alguns eventos citam Samsung/VID_04E8/Android: o celular chegou a ser "
                "apresentado ao Windows nesta janela. Se a vigia não o mostrou, ele durou "
                "menos que o intervalo — sintoma clássico de conector com mau contato.",
            ]
        )
        proximo_passo = (
            "Rode `vigiar-usb-atento.bat` (5 leituras por segundo, 10 min) com o cabo "
            "plugado e mexa o conector devagar: a janela pega a piscada."
        )
    elif eventos_lidos:
        titulo = "Nenhum evento citando o celular"
        resposta = "\n\n".join(
            linhas
            + [
                "Os eventos acima são do PC (hub, controladora, driver). Nada citando "
                "Samsung, VID_04E8 ou Android: nesta janela o aparelho não foi apresentado "
                "ao Windows nenhuma vez, nem por um instante.",
            ]
        )
        proximo_passo = (
            "Isso reforça cabo ou conector: teste o mesmo cabo em outro aparelho de "
            "entrada micro-USB. Se nada aparecer lá também, o cabo é de carga."
        )
    else:
        titulo = "Nenhum evento de USB no período"
        resposta = "\n\n".join(
            linhas
            + [
                "Nem do PC: o log do Windows não registrou nada de USB nesse intervalo. "
                "Isso é normal quando a porta não teve nenhuma mudança.",
            ]
        )
        proximo_passo = (
            "Plugue o celular com a vigia aberta e confira; depois rode este histórico de "
            "novo — o que passar fica registrado mesmo com a janela fechada."
        )
    return {"titulo": titulo, "resposta": resposta, "proximo_passo": proximo_passo, "eventos": medido}


def resumo_da_rede(medido: dict[str, Any]) -> dict[str, Any]:
    """Traduz a varredura em resposta de chat — inclusive quando ela não serve."""
    if not medido.get("executado"):
        motivo = str(medido.get("motivo") or "A varredura não rodou.")
        return {
            "titulo": "Não deu para olhar a rede",
            "resposta": motivo,
            "proximo_passo": (
                "Se o celular está no Wi-Fi, nada disso muda o diagnóstico do cabo: sem "
                "Depuração USB ligada o Android não abre porta para o PC, e sem porta não "
                "existe acesso por rede."
            ),
            "rede": medido,
        }
    hosts = medido.get("hosts") or []
    com_adb = medido.get("com_adb") or []
    linhas = [f"Rede local: {medido.get('rede')} — este PC é {medido.get('pc')}."]
    if hosts:
        linhas.append(f"{len(hosts)} dispositivo(s) responderam:")
        for host in hosts[:12]:
            nome = f" {host['nome']}" if host.get("nome") else ""
            marca = f" [{host['fabricante']}]" if host.get("fabricante") else ""
            if host["portas"]:
                portas = ", ".join(f"{porta} ({servico})" for porta, servico in zip(host["portas"], host["servicos"]))
            else:
                portas = "nenhuma porta aberta"
            # O MAC entra na linha: quando o nome não diz nada ("A34", vazio), é
            # ele que permite reconhecer o aparelho.
            mac = f" · {host['mac']}" if host.get("mac") else ""
            linhas.append(f"• {host['ip']}{nome}{marca}{mac} — {portas}")
        if len(hosts) > 12:
            linhas.append(f"• … e mais {len(hosts) - 12}")
    else:
        linhas.append("Nenhum outro dispositivo respondeu na rede.")

    if com_adb:
        host = com_adb[0]
        titulo = "Tem adb por rede: dá para conectar sem cabo"
        resposta = "\n\n".join(
            linhas
            + [
                f"O aparelho em {host['ip']} tem a porta 5555 aberta — é o adb sem fio. "
                f"Com as ferramentas instaladas, `adb connect {host['ip']}:5555` conecta."
            ]
        )
        proximo_passo = (
            "Rode `celular.status` depois do connect: autorizado, o `celular.espelhar` "
            "abre a tela numa janela do PC."
        )
    elif hosts:
        titulo = "A rede não dá acesso ao celular"
        resposta = "\n\n".join(
            linhas
            + [
                "Nenhuma porta de aparelho aberta. O Android não abre nada por padrão: o adb "
                "por rede só existe depois de `adb tcpip 5555` (que se roda uma vez **pelo "
                "cabo**) ou da Depuração sem fio do Android 11+ (que pede código na tela).",
                "Ou seja: o Wi-Fi mostra que o aparelho está vivo e qual é o IP dele, mas não "
                "substitui o cabo. Derrubar o Wi-Fi para ele reconectar também não abre nada — "
                "só faz o aparelho voltar para a mesma rede.",
            ]
        )
        proximo_passo = (
            "O caminho continua sendo a linha de dados: cabo de dados, porta traseira e "
            "conector. Use `vigiar-usb.bat` enquanto troca."
        )
    else:
        titulo = "Ninguém respondeu na rede"
        resposta = "\n\n".join(
            linhas
            + [
                "Nenhum vizinho respondeu: este PC pode estar em outra rede (Wi-Fi de visitante, "
                "4G, isolamento de clientes do roteador) ou o firewall bloqueia a varredura.",
            ]
        )
        proximo_passo = (
            "Confira se este PC e o celular estão no mesmo Wi-Fi de casa (mesmo nome de rede) "
            "e rode de novo."
        )
    return {
        "titulo": titulo,
        "resposta": resposta,
        "proximo_passo": proximo_passo,
        "rede": medido,
    }


def situacao_de(aparelhos: list[dict[str, str]]) -> str:
    if not aparelhos:
        return "vazio"
    if any(item["estado"] == "device" for item in aparelhos):
        return "autorizado"
    if any(item["estado"] == "unauthorized" for item in aparelhos):
        return "nao-autorizado"
    if any(item["estado"] == "recovery" for item in aparelhos):
        return "recovery"
    return "offline"


# --- o plano -----------------------------------------------------------------

def _linhas_da_usb(windows: dict[str, Any]) -> str:
    """Lista o que a sonda viu, com VID — para a pessoa julgar, não adivinhar."""
    itens = windows.get("dispositivos") or []
    if not itens:
        return ""
    linhas = []
    for item in itens[:5]:
        if e_aparelho(item):
            marca = "celular"
        elif e_desconhecido(item):
            marca = "não identificado"
        else:
            marca = "não é Samsung"
        # VID_0000 é o "não consegui perguntar": mostrar como VID daria a
        # impressão de que o Windows identificou o aparelho.
        tem_vid = bool(item.get("vid")) and item["vid"] != "0000"
        vid = f" VID_{item['vid'].upper()}" if tem_vid else " sem VID"
        status = item.get("status") or "?"
        problema = item.get("problema") or ""
        if problema and status.upper() != "OK":
            status = f"{status}: {_traduzir_problema(problema)}"
        modelo = f" {item['modelo']}" if item.get("modelo") else ""
        linhas.append(f"• {_nome_curto(item, 44)}{modelo}{vid} [{status}, {marca}]")
    if len(itens) > 5:
        linhas.append(f"• … e mais {len(itens) - 5}")
    return "\n".join(linhas)


def _linhas_dos_aparelhos(aparelhos: list[dict[str, str]]) -> list[str]:
    linhas = []
    for item in aparelhos:
        modelo = item.get("model") or item.get("produto") or ""
        detalhe = f" ({modelo})" if modelo else ""
        traduzido = {
            "device": "autorizado",
            "unauthorized": "não autorizado neste PC",
            "offline": "offline",
            "recovery": "no recovery",
            "sideload": "em sideload",
            "bootloader": "no bootloader",
        }.get(item["estado"], item["estado"])
        linhas.append(f"• {item['serial']}{detalhe}: {traduzido}")
    return linhas


def resumo(medido: dict[str, Any]) -> dict[str, Any]:
    """Traduz o que foi medido em uma resposta de chat — e o próximo passo.

    `celular.status` olhava só a pasta das ferramentas: dizia "Tudo pronto" com
    o celular desligado, sem cabo e sem depuração. Aqui a resposta parte do que
    o adb e o Windows realmente viram, e o campo `resposta` já traz a ação
    seguinte (cabo, driver, depuração ou espelhar).
    """
    info = medido.get("ferramentas") or {}
    aparelhos = medido.get("aparelhos") or []
    windows = medido.get("windows") or {}
    # `estado()` só devolve `situacao` quando chegou a rodar o adb; os caminhos de
    # recusa (sem ferramenta, trava desligada, adb quebrado) vêm com `motivo`.
    if medido.get("situacao"):
        situacao = medido["situacao"]
    elif not info.get("completo"):
        situacao = "sem-ferramentas"
    elif medido.get("executado") and medido.get("motivo"):
        situacao = "erro-adb"
    elif not medido.get("executado"):
        situacao = "desligado"
    else:
        situacao = "vazio"

    ferramentas_txt = (
        f"adb: {info.get('adb') or 'não encontrado'} · scrcpy: {info.get('scrcpy') or 'não encontrado'}"
    )
    linhas: list[str] = [ferramentas_txt]
    if aparelhos:
        linhas.append("Aparelhos no adb:\n" + "\n".join(_linhas_dos_aparelhos(aparelhos)))
    if windows and windows.get("consulta"):
        linhas.append("Windows na USB: " + str(windows.get("resumo") or "sem resposta"))
        detalhe = _linhas_da_usb(windows)
        if detalhe:
            linhas.append(detalhe)
        frase = (windows.get("comparacao") or {}).get("frase")
        if frase:
            linhas.append(str(frase))

    if situacao == "sem-ferramentas":
        acao = (
            "Faltam as ferramentas. Rode `celular.preparar` para baixar adb e scrcpy "
            "(com hash) — sem elas o JARVIS não fala com o aparelho."
        )
        titulo = "Faltam as ferramentas"
    elif situacao == "desligado":
        acao = (
            f"{AMBIENTE} está desligado, então nada foi executado. "
            "Rode `ligar-celular.bat` e reinicie a API."
        )
        titulo = "A camada do celular está desligada"
    elif situacao == "erro-adb":
        acao = (
            "O adb rodou e terminou com erro: "
            + (str(medido.get("motivo") or "sem detalhe").splitlines()[0][:240])
            + ". Se falar de versão de servidor, feche outros programas que usam adb "
            "(Android Studio, emuladores) e rode de novo."
        )
        titulo = "O adb falhou"
    elif situacao == "autorizado":
        serial = next((a["serial"] for a in aparelhos if a["estado"] == "device"), "")
        acao = (
            f"Pronto: {serial} autorizado. Próximo passo é `celular.espelhar` — a janela "
            "do scrcpy abre no PC com a tela do aparelho. Para puxar arquivo, "
            "`celular.puxar`."
        )
        titulo = "Aparelho pronto"
    elif situacao == "nao-autorizado":
        acao = (
            "A Depuração USB está ligada, mas este PC ainda não foi autorizado. Falta o "
            "toque em “Permitir depuração USB?” na tela do aparelho — nenhum programa "
            "substitui esse toque. Com a tela quebrada, `celular.plano` traz o caminho de "
            "autorizar às cegas por teclado USB."
        )
        titulo = "Depuração ligada, PC não autorizado"
    elif situacao == "recovery":
        acao = (
            "O aparelho está no recovery — é a janela boa para resgatar arquivo antes de "
            "qualquer flash: `celular.puxar` (no recovery o ADB costuma dispensar "
            "autorização)."
        )
        titulo = "Aparelho no recovery"
    elif situacao == "offline":
        acao = (
            "O aparelho aparece como offline: o cabo ou a porta está instável. Troque o "
            "cabo, use a porta de trás do PC e rode de novo."
        )
        titulo = "Aparelho offline"
    elif windows.get("com_problema") and windows.get("telefones"):
        acao = (
            "O Windows vê o celular, mas com problema de driver — enquanto ele estiver "
            "com ⚠ no Gerenciador de Dispositivos o adb não enxerga nada. Instale o "
            "Samsung USB Driver for Mobile Phones, reconecte o cabo e rode de novo."
        )
        titulo = "Nenhum aparelho no adb: falta driver"
    elif windows.get("visivel") and sem_driver_samsung(windows.get("telefones") or []):
        quem = next((item.get("modelo") for item in windows.get("telefones") or [] if item.get("modelo")), "")
        acao = (
            "O Windows reconhece a Samsung"
            + (f" ({quem})" if quem else "")
            + " pelo VID_04E8, com nome genérico de driver. MTP (copiar arquivo à mão) "
            "funciona assim, mas o adb precisa de um driver para a interface ADB: ligue a "
            "Depuração USB e rode `status do celular`; se o adb continuar sem ver o "
            "aparelho, instale o Samsung USB Driver for Mobile Phones — é o passo que "
            "publica essa interface no Windows."
        )
        titulo = "Celular reconhecido, mas sem o driver da Samsung"
    elif windows.get("visivel"):
        acao = (
            "O Windows vê o celular, mas o adb não: cabo e porta estão bons, e o que "
            "falta é ligar a Depuração USB (ou o consentimento dele). Rode "
            "`celular.plano` para o caminho sem tela."
        )
        titulo = "Nenhum aparelho no adb: falta a Depuração USB"
    elif windows.get("desconhecidos"):
        acao = (
            "A porta USB viu um dispositivo que o Windows não conseguiu identificar — é a "
            "assinatura de cabo só de carga, conector sujo/oxidado ou porta fraca: o PC "
            "manda energia e a conversa não acontece. Troque o cabo por um de dados, use a "
            "porta de trás do PC, limpe o conector do celular — e deixe `vigiar-usb.bat` "
            "aberto enquanto troca: ele apita no instante em que algo entrar. Driver e "
            "Depuração USB não mudam nada enquanto isso não for resolvido."
        )
        titulo = "A porta viu algo que o Windows não identificou"
    elif windows.get("genericos"):
        comparacao = windows.get("comparacao") or {}
        passado = _frase_do_que_ja_passou()
        if comparacao and not comparacao.get("primeira") and not comparacao.get("mudou"):
            acao = (
                "A lista de USB é idêntica à da checagem anterior: nem com o cabo o Windows "
                "viu algo novo, então o aparelho não chegou a ser visto — não é driver nem "
                "Depuração USB. Teste físico, nesta ordem: cabo que transfira dados, porta "
                "de trás do PC sem hub, e o conector do celular (poeira/oxidação). Para ver "
                "o instante em que algo muda, abra `vigiar-usb.bat` e deixe a janela aberta "
                "trocando de cabo. Enquanto nada novo aparecer, ligar a Depuração USB não "
                "mudaria nada."
                + (f" {_frase_do_que_ja_passou()}" if _frase_do_que_ja_passou() else "")
            )
            if passado:
                acao = f"{passado} {acao}"
            titulo = "A USB não mudou nada entre as duas checagens"
        else:
            acao = (
                "O Windows lista dispositivo(s) USB, mas nenhum é o celular (sem VID de "
                "Samsung 04E8). Pluge o cabo no celular e rode `celular.status` de novo: eu "
                "comparo com esta lista e digo exatamente o que entrou ou saiu — não precisa "
                "anotar nada no olho."
            )
            if passado:
                acao = f"{passado} {acao}"
            titulo = "O que o Windows vê não é o celular"
    elif windows.get("consulta"):
        passado = _frase_do_que_ja_passou()
        acao = (
            "O Windows não vê nada na USB: aqui é cabo, porta, bateria ou a placa USB do "
            "aparelho — antes de qualquer coisa de software. Troque o cabo, use a porta de "
            "trás do PC, segure Power por 10 s e ligue de novo. Tela bloqueada não é causa: "
            "o aparelho aparece na USB mesmo travado — o desbloqueio muda o acesso a "
            "arquivo, não a presença na porta."
        )
        if passado:
            acao = f"{passado} {acao}"
        titulo = "Nenhum aparelho no adb — e o Windows também não vê"
    else:
        acao = (
            "O adb não vê aparelho. Confira o cabo e rode `celular.plano` para o passo a "
            "passo do seu caso."
        )
        titulo = "Nenhum aparelho no adb"

    return {
        "situacao": situacao,
        "titulo": titulo,
        "aparelhos": aparelhos,
        "windows": windows,
        "ferramentas": info,
        "executado": bool(medido.get("executado")),
        "motivo": medido.get("motivo", ""),
        "proximo_passo": acao,
        "resposta": "\n\n".join([*linhas, acao]),
    }


def _passo(titulo: str, comandos: list[str], nota: str) -> dict[str, Any]:
    return {"titulo": titulo, "comandos": comandos, "nota": nota}


def _plano_sem_ferramentas(info: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _passo(
            "1. Baixar adb e scrcpy",
            ["celular.preparar"],
            "Baixa o platform-tools (Google) e o scrcpy (GitHub) para "
            f"{pasta_ferramentas()}, confere o SHA-256 de cada arquivo e não executa nada.",
        ),
        _passo(
            "2. Se preferir na mão",
            [
                f"baixar {URL_PLATFORM_TOOLS}",
                f"abrir {PAGINA_SCRCPY}",
            ],
            "Os mesmos arquivos oficiais. O scrcpy já vem com um adb próprio; o "
            "platform-tools separado evita conflito de versão.",
        ),
        _passo(
            "3. Voltar aqui",
            ["celular.status"],
            "Com as duas ferramentas no lugar, o plano passa a medir o aparelho.",
        ),
    ]


def _plano_desligado() -> list[dict[str, Any]]:
    return [
        _passo(
            "1. Ligar a permissão",
            [f"definir {AMBIENTE}=1 no .env", "reiniciar a API"],
            "Sem a variável o JARVIS não executa adb nenhum — é a mesma regra de "
            "`JARVIS_HOST_PC`, `JARVIS_HOST_INSTALAR` e `JARVIS_HOST_REDE`.",
        ),
        _passo("2. Conferir", ["celular.status"], "Deve mostrar adb e scrcpy encontrados."),
    ]


def _plano_vazio(windows: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if windows and windows.get("consulta"):
        return _plano_vazio_com_sonda(windows)
    return [
        _passo(
            "1. Testar com o cabo",
            ["trocar o cabo (de preferência o original)", "conectar na porta USB de trás do PC"],
            "`adb devices` vazio quase sempre é cabo, porta ou driver — não é o celular.",
        ),
        _passo(
            "2. Ver se o Windows vê o aparelho",
            ["Gerenciador de Dispositivos → Procurar “SAMSUNG Mobile” ou “MTP”"],
            "Se aparecer MTP, a placa inicializa e o problema é só a depuração. "
            "Se não aparecer nada, teste em outro PC antes de abrir o aparelho.",
        ),
        _passo(
            "3. Tentar o modo Download (às cegas)",
            [
                "desligar o aparelho",
                "segurar Volume − + Home + Power até vibrar",
                "apertar Volume + uma vez",
                "conferir no PC: adb devices  (no modo Download o Odin vê, o adb não)",
            ],
            "O modo Download existe sem tela e sem depuração. Ele sozinho não dá "
            "acesso a arquivo nem permite flash: o Odin recusa com *BLOCKED BY FRP "
            "LOCK* enquanto o Desbloqueio OEM não estiver ligado — e esse botão "
            "fica atrás da tela.",
        ),
        _passo(
            "4. Sem depuração nunca ligada: tela de teste",
            ["assistência técnica com display de teste (5 minutos)"],
            "Ligar uma vez `Depuração USB`, `Desativar tempo limite de autorização "
            "do adb`, `Desbloqueio OEM` e marcar “sempre permitir este computador” "
            "resolve o aparelho para sempre, mesmo que o painel seja descartado. "
            "Costuma sair mais barato que comprar o módulo.",
        ),
        _passo(
            "5. Navegar às cegas (paliativo)",
            [
                "scrcpy --otg",
                "segurar Volume + e Volume − por 3 s para ligar o TalkBack",
                "teclado USB por OTG para navegar ouvindo o foco",
            ],
            "O TalkBack fala o item focado, o que permite “ver” o menu sem ver. "
            "Funciona, mas chegar em Configurações → Sobre → Número da compilação "
            "7× sem imagem é lento e não é garantido em MIUI/One UI antigas.",
        ),
    ]


def _plano_vazio_com_sonda(windows: dict[str, Any]) -> list[dict[str, Any]]:
    """O mesmo plano, mas começando pelo que o Windows já respondeu."""
    telefones = windows.get("telefones") or []
    genericos = windows.get("genericos") or []
    nomes = "; ".join(_descrever(item) for item in telefones[:3])

    if windows.get("com_problema") and telefones:
        primeiro = _passo(
            "1. Driver, não depuração",
            [
                "Gerenciador de Dispositivos → procure o item com ⚠ amarelo",
                "instalar o Samsung USB Driver for Mobile Phones (Windows)",
                "reconectar o cabo e rodar celular.status de novo",
            ],
            f"O Windows vê o celular ({nomes}), mas com problema de driver. Enquanto "
            "o driver não estiver certo, o adb não enxerga o aparelho — e nenhum "
            "passo seguinte muda nada.",
        )
    elif telefones and sem_driver_samsung(telefones):
        primeiro = _passo(
            "1. Reconhecido pela Samsung — falta o driver",
            [
                "baixar o Samsung USB Driver for Mobile Phones (site da Samsung)",
                "instalar, reiniciar o PC se ele pedir",
                "reconectar o cabo e rodar celular.status de novo",
            ],
            f"O Windows vê um aparelho Samsung ({nomes}), mas com nome de driver "
            "genérico. MTP funciona assim; o adb precisa de um driver para a "
            "interface ADB. Ligue a Depuração USB e teste; se o adb continuar sem "
            "ver, instale o Samsung USB Driver for Mobile Phones — ele publica "
            "essa interface.",
        )
    elif telefones:
        primeiro = _passo(
            "1. Cabo e porta estão bons",
            [
                "o Windows já vê o celular — não troque cabo ainda",
                "ligar a Depuração USB (ver o caminho sem tela abaixo)",
                "conferir: adb devices",
            ],
            f"O Windows vê o celular ({nomes}). Ou seja: a placa e o cabo "
            "funcionam, e o adb vazio significa que a Depuração USB nunca foi "
            "ligada (ou foi desligada).",
        )
    elif windows.get("desconhecidos"):
        nomes_desc = _nomes(windows["desconhecidos"])
        primeiro = _passo(
            "1. A porta viu algo, mas não conversou",
            [
                "trocar o cabo por um que transfira dados — cabo de carga pura não serve",
                "usar a porta USB de trás do PC, direto na placa, sem hub nem extensão",
                "passar a lanterna no conector do celular: poeira e oxidação tiram o contato dos dados",
                "conferir se o celular está ligado (desligado, ele só carrega, não aparece)",
                "abrir vigiar-usb.bat e trocar de cabo com a janela aberta: ela apita quando algo entra",
                "rodar celular.status com o cabo fora e de novo com ele: a comparação é automática",
            ],
            f"O Windows listou {nomes_desc}: um dispositivo que ele não conseguiu "
            "identificar. Traduzindo: o PC mandou energia, mas a conversa USB não "
            "aconteceu — a assinatura de cabo só de carga, conector sujo/oxidado ou "
            "porta fraca. Driver e Depuração USB não mudam nada enquanto isso não "
            "for resolvido.",
        )
    elif genericos:
        comparacao = windows.get("comparacao") or {}
        if comparacao and not comparacao.get("primeira") and not comparacao.get("mudou"):
            hora = _hora_curta(comparacao.get("quando", ""))
            primeiro = _passo(
                f"1. A USB está idêntica à das {hora}",
                [
                    "abrir vigiar-usb.bat e deixar a janela aberta (apita quando algo entra)",
                    "plugar o cabo no celular e rodar celular.status",
                    "tirar o cabo do celular e rodar celular.status de novo",
                    "eu comparo as duas listas e digo exatamente o que entrou ou saiu",
                    "o que já está na lista é do PC: hub, controladora, pendrive, teclado",
                ],
                "A lista de dispositivos USB não mudou nada entre as duas checagens "
                "— nem com o cabo plugado o Windows viu algo novo. Isso descarta "
                "driver e Depuração USB: o aparelho não chegou a ser visto. O "
                "próximo teste é físico (cabo, porta, conector).",
            )
        else:
            primeiro = _passo(
                "1. O que o Windows vê não é o celular",
                [
                    "abrir vigiar-usb.bat (apita na hora em que algo entra ou sai)",
                    "plugar o cabo no celular e rodar celular.status",
                    "tirar o cabo e rodar celular.status de novo — eu comparo as duas listas",
                    "se nada mudar, o aparelho não está sendo visto (cabo, porta ou conector)",
                    "se algo aparecer, o passo seguinte passa a ser driver ou Depuração USB",
                ],
                "O Windows lista dispositivo(s) USB genérico(s), sem VID de Samsung "
                "(04E8) e sem nome de aparelho. Isso NÃO prova que o celular está na "
                "porta: a comparação entre duas checagens é que prova. Enquanto o "
                "celular não aparecer, ligar a Depuração USB não muda nada.",
            )
    else:
        primeiro = _passo(
            "1. Nada aparece na USB",
            [
                "usar o MESMO cabo em outro aparelho de entrada igual (outro micro-USB): se nada aparecer, o cabo é só de carga",
                "trocar o cabo por um que transfira dados (o original da Samsung, se houver)",
                "usar a porta USB de trás do PC, sem hub — e conferir que ela funciona com um pendrive",
                "abrir vigiar-usb.bat e apertar/balançar o conector do aparelho devagar, olhando a janela",
                "segurar Power por 10 s e ligar de novo",
            ],
            "O Windows não vê aparelho nenhum. Aqui o problema é físico: cabo, "
            "porta, bateria ou a placa USB do aparelho — antes de qualquer coisa "
            "de software. Tela bloqueada NÃO explica: o aparelho aparece na USB "
            "mesmo travado (o desbloqueio muda o acesso a arquivo, não a presença "
            "na porta).",
        )
    # O passo 2 do plano genérico é justamente "abra o Gerenciador de Dispositivos
    # e veja se o Windows enxerga" — já respondido pela sonda, sai do caminho.
    resto = _plano_vazio()[2:]
    for indice, passo in enumerate(resto, start=2):
        passo["titulo"] = passo["titulo"].split(". ", 1)[-1]
        passo["titulo"] = f"{indice}. {passo['titulo']}"
    return [primeiro, *resto]


def _plano_nao_autorizado() -> list[dict[str, Any]]:
    return [
        _passo(
            "1. Entender o que falta",
            ["adb devices  →  unauthorized"],
            "A depuração já está ligada: falta só este computador ser autorizado. "
            "E o Android só autoriza com um toque em “Permitir” — nenhum programa "
            "no PC substitui esse toque. O resto do plano contorna a tela.",
        ),
        _passo(
            "2. Autorizar às cegas com teclado USB",
            [
                "scrcpy --otg",
                "digitar o PIN da tela de bloqueio e Enter",
                "fechar a janela",
                "scrcpy            (o popup “Permitir depuração USB?” aparece no celular)",
                "scrcpy --otg      (foco no popup: Tab, Enter, Tab, Tab, Enter)",
                "scrcpy",
            ],
            "Em alguns aparelhos o Enter é Espaço. Se o popup não aparecer, repita "
            "a sequência: o diálogo só nasce quando o adb tenta conectar.",
        ),
        _passo(
            "3. Não digitar PIN às cegas nunca mais",
            ["adb shell locksettings clear --old 1234"],
            "Troque 1234 pelo PIN atual. Depois disso o aparelho acorda sem senha, "
            "e o `scrcpy` entra direto.",
        ),
        _passo(
            "4. Fixar a autorização",
            ["Opções do desenvolvedor → Desativar tempo limite de autorização do adb"],
            "Sem isso o Android esquece este PC em 7 dias e você volta ao passo 2.",
        ),
        _passo(
            "5. Se o `--otg` não abrir no Windows",
            ["instalar o driver WinUSB/libusb pelo Zadig, apontando para o aparelho"],
            "No Linux e no macOS o `--otg` funciona direto. No Windows ele é o modo "
            "mais chato — mas é o único que não depende de depuração.",
        ),
    ]


def _plano_autorizado(nome: str) -> list[dict[str, Any]]:
    return [
        _passo(
            "1. Espelhar a tela no PC",
            [f"scrcpy -s {nome}" if nome else "celular.espelhar"],
            "A partir daqui a tela física é opcional: mouse vira toque e teclado "
            "vira digitação. `celular.espelhar` faz exatamente isso.",
        ),
        _passo(
            "2. Resgatar os arquivos antes de qualquer coisa",
            ["celular.puxar"],
            "Copia DCIM, Pictures, Download, Documents, WhatsApp e Telegram para "
            f"{dados.raiz() / 'celular'}. Nada de /data, nada de chave de aplicativo.",
        ),
        _passo(
            "3. Só então pensar em Linux",
            ["celular.espelhar → Termux (F-Droid) → proot-distro install debian"],
            "Com a tela no PC, o Termux pode ser instalado e operado normalmente; "
            "é o caminho de risco zero antes de considerar Nura/LineageOS.",
        ),
    ]


def plano(estado_atual: str = "auto", *, rodar: Callable[[list[str]], tuple[int, str, str]] | None = None) -> dict[str, Any]:
    """Monta o caminho exato para o estado medido — sem executar nada além de `adb devices`."""
    medido: dict[str, Any] | None = None
    conhecidos = {"autorizado", "nao-autorizado", "vazio", "recovery", "offline"}
    if estado_atual not in {"auto", ""}:
        if estado_atual not in conhecidos:
            raise CelularError(
                "Estado desconhecido. Use auto, autorizado, nao-autorizado, vazio, recovery ou offline."
            )
        situacao = estado_atual
    else:
        medido = estado(rodar=rodar)
        sem_ferramenta = not medido["ferramentas"]["completo"]
        desligado_ou_sem_adb = not medido["executado"]
        if sem_ferramenta:
            situacao = "sem-ferramentas"
        elif desligado_ou_sem_adb:
            situacao = "desligado"
        else:
            situacao = medido.get("situacao", "vazio")

    if situacao == "sem-ferramentas":
        passos = _plano_sem_ferramentas(medido["ferramentas"] if medido else ferramentas())
    elif situacao == "desligado":
        passos = _plano_desligado()
    elif situacao == "nao-autorizado":
        passos = _plano_nao_autorizado()
    elif situacao == "autorizado":
        nome = ""
        if medido:
            nome = next((a["serial"] for a in medido["aparelhos"] if a["estado"] == "device"), "")
        passos = _plano_autorizado(nome)
    elif situacao == "recovery":
        passos = [
            _passo(
                "1. O aparelho está no recovery",
                ["adb devices  →  recovery", "adb pull /sdcard D:\\resgate\\"],
                "No recovery o ADB costuma dispensar autorização — é a janela boa "
                "para resgatar arquivo antes de qualquer flash.",
            ),
            _passo("2. Depois", ["reiniciar o aparelho", "celular.plano"], "Recalcula o estado."),
        ]
    else:
        passos = _plano_vazio((medido or {}).get("windows"))

    titulos = {
        "sem-ferramentas": "Faltam as ferramentas",
        "desligado": "A permissão está desligada",
        "vazio": "Nenhum aparelho aparece no adb",
        "nao-autorizado": "Depuração ligada, PC não autorizado",
        "autorizado": "Aparelho pronto",
        "recovery": "Aparelho no recovery",
        "offline": "Aparelho em estado offline",
    }
    linhas = [f"{titulos[situacao]}.", ""]
    for passo in passos:
        linhas.append(passo["titulo"])
        for comando in passo["comandos"]:
            linhas.append(f"    {comando}")
        linhas.append(f"    {passo['nota']}")
        linhas.append("")
    linhas.append(
        "O que nenhum programa faz: tocar em “Permitir depuração USB?”. Esse "
        "consentimento é do Android, na tela. Todo o resto acima é automatizável."
    )
    return {
        "situacao": situacao,
        "titulo": titulos[situacao],
        "passos": passos,
        "total": len(passos),
        "medido": medido,
        "resposta": "\n".join(linhas).strip(),
    }


# --- ações -------------------------------------------------------------------

def espelhar(
    *,
    gravar: bool = False,
    desligar_painel: bool = True,
    rodar: Callable[[list[str]], tuple[int, str, str]] | None = None,
    abrir: Callable[[list[str]], Any] | None = None,
) -> dict[str, Any]:
    """Abre o aparelho numa janela do Windows — a tela física deixa de importar."""
    _exigir_ligado()
    info = ferramentas()
    if not info["scrcpy"]:
        raise CelularError("O `scrcpy` não está instalado. Rode `celular.preparar` ou `celular.plano`.")
    argumentos = [info["scrcpy"]]
    if desligar_painel:
        argumentos.append("--turn-screen-off")
    if gravar:
        argumentos.append("--record")
        argumentos.append(datetime.now().strftime("celular-%Y%m%d-%H%M%S.mp4"))
    comando = " ".join(argumentos)
    if abrir is not None:
        abrir(argumentos)
    else:
        try:
            subprocess.Popen(argumentos, shell=False, close_fds=True)
        except OSError as exc:
            raise CelularError(f"O Windows recusou abrir o scrcpy: {exc}") from exc
    return {
        "comando": comando,
        "gravando": gravar,
        "aberto": True,
        "resposta": (
            f"Abri o espelhamento — `{comando}`. A janela do celular deve aparecer; "
            "se não aparecer, rode `celular.plano` para ver o estado do aparelho."
        ),
    }


def pastas_para_puxar(nomes: list[str] | None) -> list[str]:
    """Traduz o que foi pedido para caminhos fixos do armazenamento compartilhado."""
    pedidos = [n for n in (nomes or []) if (n or "").strip()] or ["DCIM", "Pictures", "Download", "Documents", "WhatsApp"]
    escolhidas: list[str] = []
    for bruto in pedidos:
        chave = re.sub(r"[^a-z]", "", (bruto or "").lower()) or ""
        if chave not in PASTAS_PERMITIDAS:
            raise CelularError(
                f"Não copio “{bruto}”. Aceito: " + ", ".join(sorted(PASTAS_PERMITIDAS)) + "."
            )
        caminho = PASTAS_PERMITIDAS[chave]
        if caminho not in escolhidas:
            escolhidas.append(caminho)
    return escolhidas


def puxar(
    pastas: list[str] | None = None,
    pasta_destino: str = "",
    *,
    rodar: Callable[[list[str]], tuple[int, str, str]] | None = None,
) -> dict[str, Any]:
    """`adb pull` das pastas de mídia — resgate de dados sem tocar em `/data`."""
    _exigir_ligado()
    info = ferramentas()
    if not info["adb"]:
        raise CelularError("O `adb` não está instalado. Rode `celular.preparar` primeiro.")
    escolhidas = pastas_para_puxar(pastas)
    if pasta_destino.strip():
        destino = Path(pasta_destino).expanduser()
        if not destino.is_absolute():
            destino = dados.raiz() / destino
    else:
        destino = dados.raiz() / "celular" / datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        destino = destino.resolve()
    except OSError as exc:
        raise CelularError(f"Não consegui resolver o destino: {exc}") from exc
    raiz = dados.raiz().resolve()
    if raiz not in destino.parents and destino != raiz:
        raise CelularError("O destino precisa ficar dentro da raiz de dados do JARVIS.")
    executar = rodar or _rodar
    itens: list[dict[str, Any]] = []
    for pasta in escolhidas:
        alvo = destino / pasta.replace("/", "-")
        alvo.mkdir(parents=True, exist_ok=True)
        codigo, saida, erro = executar([info["adb"], "pull", f"/sdcard/{pasta}", str(alvo)])
        itens.append(
            {
                "pasta": pasta,
                "destino": str(alvo),
                "codigo": codigo,
                "ok": codigo == 0,
                "saida": _cortar(saida or erro, 600),
            }
        )
    bons = [i for i in itens if i["ok"]]
    return {
        "destino": str(destino),
        "total": len(itens),
        "ok": len(bons),
        "itens": itens,
        "resposta": (
            f"Copiei {len(bons)} de {len(itens)} pasta(s) para {destino}. "
            "Se alguma falhou, o celular provavelmente não está autorizado — veja `celular.plano`."
        ),
    }


def _extrair(zip_path: Path, destino: Path) -> int:
    """Extrai um zip recusando caminho que escape da pasta (zip-slip) e teto de tamanho."""
    destino.mkdir(parents=True, exist_ok=True)
    base = destino.resolve()
    total = 0
    with zipfile.ZipFile(zip_path) as pacote:
        for info in pacote.infolist():
            alvo = (base / info.filename).resolve()
            if base != alvo and base not in alvo.parents:
                raise CelularError(f"O zip tentou escrever fora da pasta ({info.filename}); recusado.")
            total += max(info.file_size, 0)
            if total > MAX_ZIP:
                raise CelularError("O conteúdo do zip passa do teto de 400 MB; recusado.")
            if info.is_dir():
                alvo.mkdir(parents=True, exist_ok=True)
                continue
            alvo.parent.mkdir(parents=True, exist_ok=True)
            with pacote.open(info) as origem, open(alvo, "wb") as saida:
                shutil.copyfileobj(origem, saida)
    return total


def normalizar(nome: str, executaveis: tuple[str, ...]) -> Path | None:
    """Renomeia a pasta extraída para `ferramentas/<nome>` quando o zip usa outro nome.

    O zip oficial do scrcpy vem como `scrcpy-win64-v3.3.1/` e o do platform-tools
    como `platform-tools/`. O primeiro caso precisa de ajuste para o caminho ficar
    previsível e o `scrcpy.exe` ser achado sem busca recursiva.
    """
    base = pasta_ferramentas()
    destino = base / nome
    achado = _achar(executaveis)
    if achado is None:
        return None
    if achado.parent.name == nome:
        return destino

    # procura a pasta que contém o executável e move para o nome canônico
    origem = achado.parent
    if destino.exists():
        return destino
    try:
        origem.rename(destino)
    except OSError:
        return achado.parent
    return destino


def url_do_scrcpy(*, abrir: Callable[[str], Any] | None = None) -> dict[str, Any]:
    """Resolve o endereço do zip do scrcpy para Windows na última release."""
    if abrir is None:
        def consultar(url: str) -> Any:
            pedido = Request(url, headers={"User-Agent": "JARVIS/1.0", "Accept": "application/vnd.github+json"})
            with urlopen(pedido, timeout=30) as resposta:
                return json.loads(resposta.read().decode("utf-8", "replace"))

        abrir = consultar
    try:
        dados_release = abrir(API_SCRCPY)
    except Exception as exc:  # noqa: BLE001 - rede: qualquer falha vira instrução
        raise CelularError(
            f"Não consegui consultar a última versão do scrcpy ({type(exc).__name__}). "
            f"Baixe na mão em {PAGINA_SCRCPY} e peça `sistema.baixar` com o link."
        ) from exc
    ativos = (dados_release or {}).get("assets") or []
    for ativo in ativos:
        nome = ativo.get("name") or ""
        if re.match(r"^scrcpy-win(64|32)-.*\.zip$", nome):
            return {"versao": (dados_release or {}).get("tag_name", ""), "nome": nome, "url": ativo.get("browser_download_url", "")}
    raise CelularError(
        "A release do scrcpy não trouxe zip para Windows. "
        f"Veja {PAGINA_SCRCPY} e baixe na mão com `sistema.baixar`."
    )


def _dados_do_download(baixado: dict[str, Any]) -> dict[str, Any]:
    """Acha o arquivo no que `sistema.baixar` devolve.

    `sistema.baixar` é skill de análise: devolve o envelope (`analysis`, `rows`,
    `metrics`, `findings`) e guarda o bônus em `download`. A 0.60.0 lia
    `baixado["arquivo"]` direto e por isso nunca achava o zip — daí o
    "não deixou arquivo utilizável" logo no primeiro download real.
    """
    interno = baixado.get("download")
    if isinstance(interno, dict) and interno.get("arquivo"):
        return interno
    return baixado


def preparar(
    *,
    baixar: Callable[..., dict[str, Any]] | None = None,
    resolver_scrcpy: Callable[[], dict[str, Any]] | None = None,
    autorizacao: str = "",
) -> dict[str, Any]:
    """Baixa platform-tools e scrcpy, confere o SHA-256 e extrai em `ferramentas/`."""
    _exigir_ligado()
    if baixar is None:
        from . import sistema

        def baixar(url: str, autorizacao: str = "") -> dict[str, Any]:  # type: ignore[misc]
            return sistema.baixar(url=url, autorizacao=autorizacao)

    resolver = resolver_scrcpy or url_do_scrcpy
    remoto = resolver() or {}
    destino = pasta_ferramentas()
    resultado: dict[str, Any] = {"pasta": str(destino), "baixados": [], "scrcpy": remoto}
    partes = [("platform-tools", URL_PLATFORM_TOOLS), ("scrcpy", remoto.get("url", ""))]
    for nome, url in partes:
        if not url:
            raise CelularError(f"Não achei o endereço oficial do {nome}.")
        baixado = baixar(url, autorizacao=autorizacao)
        info = _dados_do_download(baixado if isinstance(baixado, dict) else {})
        caminho = Path(str(info.get("arquivo") or ""))
        if not caminho.is_file():
            onde = f" ({caminho})" if str(caminho) not in {"", "."} else ""
            raise CelularError(
                f"O download de {nome} não deixou arquivo utilizável{onde}. "
                "Confira a pasta storage/host-downloads: se ela estiver vazia, o "
                "arquivo não chegou ao disco e o problema é a conexão."
            )
        extraido = _extrair(caminho, destino)
        # O zip já cumpriu o papel. Guardar 90 MB num pendrive de 4 GB só atrapalha
        # o próximo download; a quarentena é do próprio JARVIS, não do usuário.
        try:
            caminho.unlink(missing_ok=True)
        except OSError:
            pass
        pasta = normalizar(nome, ADB_NOMES if nome == "platform-tools" else SCRCPY_NOMES)
        resultado["baixados"].append(
            {
                "ferramenta": nome,
                "url": url,
                "arquivo": str(caminho),
                "sha256": info.get("sha256", ""),
                "bytes": info.get("bytes", 0),
                "extraido": extraido,
                "pasta": str(pasta) if pasta else "",
            }
        )
    final = ferramentas()
    resultado["ferramentas"] = final
    resultado["resposta"] = (
        "Baixei e extraí as duas ferramentas em "
        f"{destino}. adb: {final['adb'] or 'não achei'} · scrcpy: {final['scrcpy'] or 'não achei'}. "
        "Nada foi executado — o primeiro uso é `celular.status`."
    ) if final["completo"] else (
        f"Baixei os arquivos em {destino}, mas não achei os executáveis. "
        "Confira a pasta e me diga o que apareceu."
    )
    return resultado
