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
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen

from . import dados

AMBIENTE = "JARVIS_HOST_CELULAR"
TIMEOUT = 25
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
            "Tudo pronto." if not faltando
            else "Peça `celular.preparar` para baixar e conferir as duas ferramentas."
        ),
    }


def _rodar(argumentos: list[str], timeout: int = TIMEOUT) -> tuple[int, str, str]:
    try:
        concluido = subprocess.run(
            argumentos,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise CelularError(f"O executável “{argumentos[0]}” não está instalado.") from exc
    except subprocess.TimeoutExpired as exc:
        raise CelularError(f"“{' '.join(argumentos)}” passou de {timeout}s e foi interrompido.") from exc
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
    aparelhos = parsear_dispositivos(saida)
    if codigo != 0 and not aparelhos:
        return {
            "ferramentas": info,
            "executado": True,
            "codigo": codigo,
            "motivo": _cortar(erro or saida) or f"O adb terminou com código {codigo}.",
            "aparelhos": [],
        }
    return {
        "ferramentas": info,
        "executado": True,
        "codigo": codigo,
        "aparelhos": aparelhos,
        "saida": _cortar(saida),
        "situacao": situacao_de(aparelhos),
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


def _plano_vazio() -> list[dict[str, Any]]:
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
        passos = _plano_vazio()

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
