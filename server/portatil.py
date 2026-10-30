"""O que cabe no pendrive do JARVIS — e o que nunca vai caber.

Duas perguntas juntas, e elas são diferentes de propósito:

1. **“Dá para baixar mais plugins/drivers e deixar no pendrive?”** — ferramenta
   portátil sim; driver **não**. Driver não é arquivo que se carrega: é coisa que
   se **instala** no Windows, com serviço e reinício. Quem promete driver portátil
   está vendendo engano. O catálogo aqui só lista o que roda do pendrive sem
   instalar nada.
2. **“Tem coisa no PC e não no pendrive?”** — tem, e é a maior parte do que faz
   o PC funcionar: driver de vídeo, .NET, runtime do Visual C++, pacote de
   captura de rede, antivírus. Nada disso é portátil, e o relatório diz por quê.

Regra de honestidade do catálogo: cada item tem **licença**, **site oficial**,
**tamanho aproximado**, se é **portátil de verdade** (descompacta e roda) e se
**precisa de administrador**. Item que precisa de driver ou de instalação fica na
lista de “não dá”, com o motivo — não some.

Nada aqui baixa nada. Baixar é `sistema.baixar` (quarentena + SHA-256); este
módulo só diz **o que vale a pena**, **de onde** e **para quê**.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from . import dados as dados_locais

# ---------------------------------------------------------------------------
# Ferramentas que rodam do pendrive, sem instalar.
# tamanho_mb é ordem de grandeza do ZIP/portátil, para caber num pendrive de 8 GB.
# ---------------------------------------------------------------------------

FERRAMENTAS: list[dict[str, Any]] = [
    {
        "id": "7zip", "nome": "7-Zip (versão portátil)", "tamanho_mb": 2,
        "licenca": "LGPL", "url": "https://www.7-zip.org/download.html",
        "para_que": "abrir .7z/.rar/.tar e zipar backups sem instalar",
        "libera_skill": "backup.criar, backup.restaurar, files.*",
        "portatil": True, "admin": False,
        "nota": "baixe o .exe extraível (7zXXXX-x64.exe) e extraia na pasta do pendrive",
    },
    {
        "id": "everything", "nome": "Everything", "tamanho_mb": 3,
        "licenca": "freeware (gratuito, código fechado)", "url": "https://www.voidtools.com/downloads/",
        "para_que": "achar qualquer arquivo do PC na hora, sem indexar horas",
        "libera_skill": "complementa files.list e sistema.pastas",
        "portatil": True, "admin": False,
        "nota": "versão “portable” no ZIP; não precisa indexar de novo a cada uso",
    },
    {
        "id": "sysinternals", "nome": "Process Explorer + Autoruns (Sysinternals)", "tamanho_mb": 12,
        "licenca": "Microsoft EULA (uso livre)", "url": "https://learn.microsoft.com/sysinternals/downloads/",
        "para_que": "ver quem abriu um arquivo, e desligar o que inicia com o Windows com interface",
        "libera_skill": "complementa a skill de processos (leitura) com o autoruns",
        "portatil": True, "admin": True,
        "nota": "roda direto; sem admin mostra menos. É o par visual do diagnóstico de processos",
    },
    {
        "id": "hwmonitor", "nome": "HWiNFO (portátil)", "tamanho_mb": 10,
        "licenca": "freeware para uso pessoal", "url": "https://www.hwinfo.com/download/",
        "para_que": "temperatura, clock e throttling: por que o PC trava em 4 GB",
        "libera_skill": "alimenta o diagnóstico de lentidão com número de hardware",
        "portatil": True, "admin": True,
        "nota": "a versão “portable” vem no ZIP",
    },
    {
        "id": "crystaldiskinfo", "nome": "CrystalDiskInfo (portátil)", "tamanho_mb": 6,
        "licenca": "MIT", "url": "https://crystalmark.info/en/download/",
        "para_que": "saúde do HD/SSD (SMART): disco morrendo explica lentidão e travamento",
        "libera_skill": "complementa sistema.disco",
        "portatil": True, "admin": False,
        "nota": "versão ZIP; a padrão também serve",
    },
    {
        "id": "sumatrapdf", "nome": "SumatraPDF (portátil)", "tamanho_mb": 8,
        "licenca": "AGPL", "url": "https://www.sumatrapdfreader.org/download-free-pdf-viewer",
        "para_que": "ler PDF leve — abre petição em 1 segundo num PC de 4 GB",
        "libera_skill": "abre o que document.read e pdf.merge produzem",
        "portatil": True, "admin": False,
        "nota": "a versão “portable” é um único .exe",
    },
    {
        "id": "notepadpp", "nome": "Notepad++ (portátil)", "tamanho_mb": 6,
        "licenca": "GPL", "url": "https://notepad-plus-plus.org/downloads/",
        "para_que": "editar .env, .bat e código com quebra de linha certa",
        "libera_skill": "edição manual do .env e de scripts",
        "portatil": True, "admin": False,
        "nota": "pegue o pacote “Portable” (zip), não o instalador",
    },
    {
        "id": "vlc", "nome": "VLC (portátil)", "tamanho_mb": 45,
        "licenca": "GPL", "url": "https://www.videolan.org/vlc/download-windows.html",
        "para_que": "tocar qualquer vídeo/áudio sem codec instalado",
        "libera_skill": "abre mídia do storage",
        "portatil": True, "admin": False,
        "nota": "no instalador existe a opção “portable”; no ZIP já vem assim",
    },
    {
        "id": "ffmpeg", "nome": "FFmpeg", "tamanho_mb": 90,
        "licenca": "LGPL/GPL", "url": "https://ffmpeg.org/download.html",
        "para_que": "cortar, converter e extrair áudio/vídeo por linha de comando",
        "libera_skill": "habilita transcrição e recorte de mídia no JARVIS",
        "portatil": True, "admin": False,
        "nota": "builds “essentials”; basta pôr ffmpeg.exe numa pasta do PATH do projeto",
    },
    {
        "id": "adb-scrcpy", "nome": "ADB + scrcpy (platform-tools)", "tamanho_mb": 30,
        "licenca": "Apache 2.0", "url": "https://developer.android.com/tools/releases/platform-tools",
        "para_que": "falar com o celular por USB: espelhar, puxar foto, instalar app",
        "libera_skill": "celular.* (status, espelhar, puxar, otg)",
        "portatil": True, "admin": False,
        "nota": "já é baixado por celular.preparar com SHA-256; fica em storage/ferramentas",
    },
    {
        "id": "tesseract", "nome": "Tesseract OCR (build portátil)", "tamanho_mb": 60,
        "licenca": "Apache 2.0", "url": "https://github.com/UB-Mannheim/tesseract/wiki",
        "para_que": "ler texto de imagem e PDF escaneado (OCR de verdade, não simulação)",
        "libera_skill": "biblioteca.ocr deixa de usar motor falso nos testes",
        "portatil": True, "admin": False,
        "nota": "o build do UB-Mannheim tem opção portátil; precisa da pasta tessdata",
    },
    {
        "id": "keepassxc", "nome": "KeePassXC (portátil)", "tamanho_mb": 40,
        "licenca": "GPL", "url": "https://keepassxc.org/download/",
        "para_que": "cofre local para as chaves — separado do .env",
        "libera_skill": "disciplina de credencial: só em D:\\JARVIS\\.env",
        "portatil": True, "admin": False,
        "nota": "cofre criptografado num arquivo; não sincroniza sozinho",
    },
    {
        "id": "hxd", "nome": "HxD (editor hexadecimal portátil)", "tamanho_mb": 3,
        "licenca": "freeware", "url": "https://mh-nexus.de/en/hxd/",
        "para_que": "inspecionar e corrigir byte a byte um arquivo binário",
        "libera_skill": "reverse.inspect com olho humano",
        "portatil": True, "admin": False,
        "nota": "versão “portable” no site",
    },
    {
        "id": "testdisk", "nome": "TestDisk + PhotoRec", "tamanho_mb": 25,
        "licenca": "GPL", "url": "https://www.cgsecurity.org/wiki/TestDisk_Download",
        "para_que": "recuperar arquivo apagado de cartão e pendrive",
        "libera_skill": "resgate de cartão quando o sistema de arquivos corrompe",
        "portatil": True, "admin": True,
        "nota": "roda em console; é o único caminho quando o cartão não monta",
    },
    {
        "id": "rufus", "nome": "Rufus (portátil)", "tamanho_mb": 2,
        "licenca": "GPL", "url": "https://rufus.ie/",
        "para_que": "gravar ISO em pendrive (instalar Windows/Linux)",
        "libera_skill": "preparar mídia de instalação de sistema",
        "portatil": True, "admin": True,
        "nota": "um único .exe; pede admin para escrever no pendrive",
    },
    {
        "id": "ventoy", "nome": "Ventoy", "tamanho_mb": 70,
        "licenca": "GPL", "url": "https://www.ventoy.net/en/download.html",
        "para_que": "várias ISOs no mesmo pendrive, escolhidas no boot",
        "libera_skill": "testar sistema sem reinstalar o pendrive",
        "portatil": True, "admin": True,
        "nota": "precisa de um pendrive dedicado: ele formata a unidade escolhida",
    },
    {
        "id": "winmerge", "nome": "WinMerge (portátil)", "tamanho_mb": 12,
        "licenca": "GPL", "url": "https://winmerge.org/downloads/",
        "para_que": "comparar duas versões de arquivo lado a lado",
        "libera_skill": "review de mudança com olho humano",
        "portatil": True, "admin": False,
        "nota": "o ZIP é a versão portátil",
    },
    {
        "id": "imagemagick", "nome": "ImageMagick (portátil)", "tamanho_mb": 30,
        "licenca": "ImageMagick License (livre)", "url": "https://imagemagick.org/script/download.php",
        "para_que": "redimensionar, converter e recortar imagem em lote",
        "libera_skill": "preparo de imagem para diagrama e documento",
        "portatil": True, "admin": False,
        "nota": "build “portable”; o PATH é do projeto, não do sistema",
    },
]

# ---------------------------------------------------------------------------
# O que NÃO dá para levar no pendrive, e o motivo técnico.
# ---------------------------------------------------------------------------

NAO_PORTATIL: list[dict[str, str]] = [
    {"nome": "Driver de vídeo da NVIDIA", "por_que": "driver não é arquivo solto: vira serviço no Windows e pede reinício. É o que roda o NVIDIA Container que você viu no Gerenciador de Tarefas"},
    {"nome": ".NET Framework", "por_que": "registra componentes no sistema; programas dependem dele instalado, não copiado"},
    {"nome": "Visual C++ Redistributable", "por_que": "DLL de runtime registrada no sistema; sem ela o programa portátil nem abre"},
    {"nome": "Npcap / WinPcap", "por_que": "instala driver de captura de rede — é driver, não programa. Sem ele não existe Wireshark"},
    {"nome": "Antivírus", "por_que": "precisa de serviço em segundo plano e assinatura de kernel"},
    {"nome": "Office (Word/Excel)", "por_que": "licença e registro; a alternativa portátil é LibreOffice, mais pesado e diferente"},
    {"nome": "Docker / WSL", "por_que": "depende de recurso do Windows (virtualização) ligado e reinício"},
    {"nome": "Java (JRE) do sistema", "por_que": "existe JRE portátil, mas programas que procuram Java no registro não o encontram"},
    {"nome": "Drivers de impressora, Bluetooth e Wi-Fi", "por_que": "são de kernel, específicos da máquina e assinados pelo fabricante"},
]


class PortatilError(ValueError):
    """Erro esperado do catálogo, seguro para o usuário."""


def _raiz_ferramentas() -> Path:
    return Path(dados_locais.caminho("ferramentas"))


def _projeto() -> Path:
    return Path(__file__).resolve().parents[1]


def _onde_esta_o_projeto() -> dict[str, Any]:
    """Diz se o projeto está num disco removível (pendrive) ou no disco do PC."""
    projeto = _projeto()
    letra = projeto.drive or ""
    removivel = False
    if os.name == "nt" and letra:
        try:
            import ctypes

            tipo = ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(letra + "\\"))
            removivel = tipo == 2
        except Exception:  # pragma: no cover - depende do Windows
            removivel = False
    return {"caminho": str(projeto), "unidade": letra, "removivel": removivel}


def medir() -> dict[str, Any]:
    """Compara o catálogo com o que já existe na pasta de ferramentas do projeto."""
    base = _raiz_ferramentas()
    projeto = _projeto()
    # Nome de arquivo que denuncia cada ferramenta. "adb-scrcpy" vira "scrcpy":
    # o split por hífen daria "adb" e nunca acharia o scrcpy.exe já baixado.
    marcas = {
        "adb-scrcpy": ("scrcpy", "adb"),
        "sysinternals": ("procexp", "autoruns"),
        "testdisk": ("testdisk", "photorec"),
        "7zip": ("7z",),
    }
    presentes: list[str] = []
    for item in FERRAMENTAS:
        chave = marcas.get(item["id"], (item["id"],))[0]
        achou = False
        for raiz in (base, projeto):
            if not raiz.exists():
                continue
            try:
                for _ in raiz.rglob("*"):
                    nome = _.name.lower()
                    if chave in nome and (nome.endswith(".exe") or nome.endswith(".dll")):
                        achou = True
                        break
            except OSError:
                continue
            if achou:
                break
        if achou:
            presentes.append(item["id"])

    total_presente = 0
    tamanho = 0
    if base.exists():
        for caminho in base.rglob("*"):
            if caminho.is_file():
                total_presente += 1
                try:
                    tamanho += caminho.stat().st_size
                except OSError:
                    pass

    faltando = [item for item in FERRAMENTAS if item["id"] not in presentes]
    return {
        "pasta": str(base),
        "existe": base.exists(),
        "arquivos": total_presente,
        "tamanho_mb": round(tamanho / (1024 * 1024), 1),
        "presentes": presentes,
        "faltando": [{"id": item["id"], "nome": item["nome"], "tamanho_mb": item["tamanho_mb"]} for item in faltando],
        "espaco_para_tudo_mb": sum(item["tamanho_mb"] for item in FERRAMENTAS),
        "onde": _onde_esta_o_projeto(),
    }


def plano(prioridade: str = "essencial") -> dict[str, Any]:
    """Diz o que baixar primeiro, e por quê — sem baixar nada."""
    medido = medir()
    faltando_ids = {item["id"] for item in medido["faltando"]}

    # A ordem não é alfabética: é "o que destrava mais coisa primeiro".
    ordem = ["adb-scrcpy", "7zip", "sumatrapdf", "everything", "sysinternals",
             "crystaldiskinfo", "hwmonitor", "tesseract", "ffmpeg", "notepadpp",
             "keepassxc", "winmerge", "imagemagick", "hxd", "vlc", "rufus", "ventoy", "testdisk"]

    etapas = []
    acumulado = 0
    for identificador in ordem:
        if identificador not in faltando_ids:
            continue
        item = next(f for f in FERRAMENTAS if f["id"] == identificador)
        acumulado += item["tamanho_mb"]
        etapas.append(
            {
                "id": item["id"],
                "nome": item["nome"],
                "tamanho_mb": item["tamanho_mb"],
                "baixar_de": item["url"],
                "licenca": item["licenca"],
                "para_que": item["para_que"],
                "libera": item["libera_skill"],
                "acumulado_mb": acumulado,
            }
        )

    return {
        "onde": medido["onde"],
        "ja_tem": medido["presentes"],
        "tamanho_atual_mb": medido["tamanho_mb"],
        "etapas": etapas,
        "tamanho_total_mb": acumulado,
        "cabe": acumulado < 4_000,
        "como_baixar": (
            "Nada é baixado por este comando. Para baixar com conferência, use a skill "
            "sistema.baixar (baixa em quarentena e calcula o SHA-256) e depois "
            "sistema.assinatura para conferir antes de usar."
        ),
        "aviso": (
            "Ferramenta portátil não precisa de instalação e não pede administrador, "
            "exceto as marcadas (Process Explorer com detalhe, TestDisk, Rufus e Ventoy)."
        ),
        "nao_da_para_levar": NAO_PORTATIL,
    }


def catalogo() -> dict[str, Any]:
    """O catálogo inteiro, com o que já está no pendrive marcado."""
    medido = medir()
    presentes = set(medido["presentes"])
    itens = [{**item, "presente": item["id"] in presentes} for item in FERRAMENTAS]
    return {
        "ferramentas": itens,
        "total": len(itens),
        "presentes": len(presentes),
        "tamanho_total_mb": medido["espaco_para_tudo_mb"],
        "nao_portatil": NAO_PORTATIL,
        "onde": medido["onde"],
        "regra": (
            "Só entra no catálogo o que roda do pendrive sem instalar. Driver e "
            "runtime ficam na lista de “não dá”, com o motivo."
        ),
    }


def resumo(dados: dict[str, Any]) -> str:
    """Uma linha para o chat."""
    if "ferramentas" in dados:
        return (
            f"{dados['presentes']} de {dados['total']} ferramentas portáteis já estão no "
            f"pendrive; o catálogo inteiro ocupa cerca de {dados['tamanho_total_mb']} MB."
        )
    etapas = dados.get("etapas") or []
    if not etapas:
        return "Todas as ferramentas do catálogo já estão no pendrive."
    return (
        f"Faltam {len(etapas)} ferramentas ({dados.get('tamanho_total_mb')} MB). "
        f"A primeira é {etapas[0]['nome']} — {etapas[0]['para_que']}."
    )
