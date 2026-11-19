"""Ler o OBB do jogo — o arquivo onde mora quase todo o peso (0.91.45).

O pedido (19/11):

    pq o obb mao e analisado? pode fazer o javis analisar pfv

A resposta antiga era “o OBB não é analisado”, e ela era **verdade pela metade**:
o OBB não é um APK — não tem `AndroidManifest.xml`, não tem DEX, não tem
assinatura —, então as perguntas do APK (pacote, motor, SDK) não se respondem
nele. Mas muita coisa se responde **sem abrir um byte**:

- **o nome** é metade da análise: o Android procura o arquivo pelo padrão
  `main.<versionCode>.<pacote>.obb` (ou `patch.`). Se o número ou o pacote não
  batem com o APK, o jogo não acha os dados — e isso é achado crítico, não
  detalhe;
- **se é ZIP** (o caso do OBB gerado pelo Unity/`jobb` sem cifragem), o
  diretório central lista tudo: quantos arquivos, quanto pesa cada área
  (`assets/`, `Audio/`, `Textures/`…) e os dez maiores;
- **se não é ZIP**, o que dá para dizer é o tamanho, a entropia e o motivo de
  não dar para listar — e é isso que o relatório diz, em vez de inventar.

## O que este módulo **não** faz

Não extrai, não descompacta em disco, não decifra. Um OBB cifrado com o `jobb`
(ou empacotado em formato proprietário do motor) continua opaco: o relatório
diz “não consigo listar o conteúdo deste” e mostra o que **consegue** — nome,
tamanho, entropia e a conferência com o APK.

## Regras (as mesmas do resto do projeto)

1. Nada é executado nem descompactado: ZIP lido pelo diretório central.
2. Nada é inventado: sem ZIP, não há lista de arquivos; há o motivo.
3. Todo achado diz o que é, por que importa, como melhorar e onde.
"""
from __future__ import annotations

import math
import re
import zipfile
from pathlib import Path
from typing import Any

EXTENSAO = ".obb"

# Mesmo teto do APK (server/jogo.py): 2 GB.
MAXIMO_BYTES = 2_000_000_000
MAX_ENTRADAS = 60_000

# Amostra de entropia: ler 2 GB para calcular um número não se justifica.
AMOSTRA_ENTROPIA = 2 * 1024 * 1024

# O limite do Play para um asset pack (Play Asset Delivery) é 1,5 GB; o OBB
# aceita 2 GB. Acima de 1,5 GB, o caminho recomendado muda.
LIMITE_ASSET_PACK = 1_500_000_000

# Extensões que comprimem bem: guardadas sem compressão, elas só engordam o
# download. Formatos já comprimidos (png, jpg, ogg, mp4) ficam de fora.
COMPRIMIVEIS = {".wav", ".json", ".txt", ".xml", ".csv", ".tga", ".bmp", ".obj", ".mtl", ".atlas", ".fnt"}

_PADRAO_NOME = re.compile(r"^(main|patch)\.(\d+)\.([A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*)\.obb$", re.IGNORECASE)


class ObbError(ValueError):
    """Erro esperado, em português, seguro para mostrar na tela."""


# ---------------------------------------------------------------------------
# O nome: `main.<versionCode>.<pacote>.obb`
# ---------------------------------------------------------------------------

def do_nome(nome: str) -> dict[str, Any] | None:
    """O que o **nome** do OBB diz — ou `None` se ele está fora do padrão.

    O Android (e a biblioteca de expansão do Google) procura o arquivo por esse
    nome exato. Um OBB renomeado para `dados.obb` continua sendo um arquivo
    válido, mas o jogo não o encontra pelo caminho normal — por isso o nome é
    lido antes de qualquer outra coisa.
    """
    achado = _PADRAO_NOME.match(Path(str(nome)).name)
    if not achado:
        return None
    return {
        "tipo": achado.group(1).lower(),
        "versaoCodigo": int(achado.group(2)),
        "pacote": achado.group(3),
    }


# ---------------------------------------------------------------------------
# Pequenos utilitários (sem dependência de jogo.py: evita import circular)
# ---------------------------------------------------------------------------

def _mb(valor: float) -> str:
    """Tamanho legível — KB abaixo de 1 MB, senão “0,0 MB” para 17 KB."""
    if valor < 1_000_000:
        return f"{valor / 1e3:.0f} KB".replace(".", ",")
    return f"{valor / 1e6:.1f} MB".replace(".", ",")


def _achado(severidade: str, titulo: str, oque: str, porque: str, como: str, onde: str = "") -> dict[str, Any]:
    return {
        "severidade": severidade,  # critico | atencao | info
        "titulo": titulo,
        "o_que_e": oque,
        "por_que_importa": porque,
        "como_melhorar": como,
        "onde": onde,
    }


def _entropia(dados: bytes) -> float:
    """Entropia de Shannon em bits por byte (0 a 8)."""
    if not dados:
        return 0.0
    contagem = [0] * 256
    for byte in dados:
        contagem[byte] += 1
    total = len(dados)
    return -sum((n / total) * math.log2(n / total) for n in contagem if n)


def entropia_amostra(caminho: Path) -> float:
    """Entropia de uma amostra (começo e fim), sem ler um OBB de 2 GB inteiro."""
    tamanho = caminho.stat().st_size
    pedacos: list[bytes] = []
    with caminho.open("rb") as arquivo:
        pedacos.append(arquivo.read(min(AMOSTRA_ENTROPIA, tamanho)))
        if tamanho > AMOSTRA_ENTROPIA:
            arquivo.seek(max(0, tamanho - AMOSTRA_ENTROPIA))
            pedacos.append(arquivo.read(AMOSTRA_ENTROPIA))
    return round(_entropia(b"".join(pedacos)), 4)


def _areas(entradas: list[dict[str, Any]]) -> dict[str, int]:
    areas: dict[str, int] = {}
    for entrada in entradas:
        nome = entrada["nome"]
        area = nome.split("/", 1)[0] if "/" in nome else "(raiz)"
        areas[area] = areas.get(area, 0) + int(entrada["bytes"])
    return dict(sorted(areas.items(), key=lambda item: item[1], reverse=True))


def _dica_de_tamanho(area: str) -> str:
    """Conselho pelo **nome da pasta** — comparado por palavra, não por pedaço.

    “tex” dentro de “textos” dava conselho de textura para pasta de diálogo.
    """
    palavras = set(re.split(r"[^a-z0-9]+", area.lower())) - {""}
    if palavras & {"audio", "audios", "sound", "sounds", "music", "musica", "voice", "voices", "sfx"}:
        return (
            "Áudio é o que mais pesa em muitos jogos: exporte em OGG/Vorbis ou AAC "
            "em vez de WAV, e baixe a taxa para 44,1 kHz quando o som é efeito."
        )
    if palavras & {"texture", "textures", "tex", "sprites", "sprite", "art", "arts", "images", "image"}:
        return (
            "Texturas: use ASTC (ou ETC2) em vez de PNG/TGA, reduza as que só aparecem "
            "de longe e tire do build as variantes que nenhuma cena usa."
        )
    if palavras & {"text", "textos", "localization", "loc", "language", "languages", "lang", "idiomas"}:
        return (
            "Texto é barato sozinho, mas costuma vir multiplicado por idioma: tire do build "
            "os idiomas que você não vai publicar e separe o que é dado de cena do que é tradução."
        )
    return (
        "Tire do OBB o que não é usado no build: cenas cortadas, idiomas que você não "
        "traduziu e assets de teste costumam ser a maior parte do peso."
    )


# ---------------------------------------------------------------------------
# A análise
# ---------------------------------------------------------------------------

def analisar(caminho: Path) -> dict[str, Any]:
    """O relatório do OBB: nome, tamanho, conteúdo (se ZIP) e o que fazer."""
    caminho = Path(caminho)
    if caminho.suffix.lower() != EXTENSAO:
        raise ObbError("A análise de OBB aceita arquivos .obb.")
    if not caminho.is_file() or caminho.is_symlink():
        raise ObbError(f"Não achei “{caminho.name}” na pasta do jogo.")
    tamanho = caminho.stat().st_size
    if tamanho <= 0:
        raise ObbError("O OBB está vazio (0 byte). Envie o arquivo de novo.")
    if tamanho > MAXIMO_BYTES:
        raise ObbError(
            f"O OBB tem {_mb(tamanho)}; o limite é {_mb(MAXIMO_BYTES)}. "
            "Acima disso, divida os dados em main + patch ou use Play Asset Delivery."
        )

    dados_do_nome = do_nome(caminho.name)
    entradas: list[dict[str, Any]] = []
    cifradas = 0
    formato = "opaco"
    try:
        with zipfile.ZipFile(caminho) as zip_aberto:
            infos = zip_aberto.infolist()[:MAX_ENTRADAS]
            entradas = [
                {
                    "nome": info.filename,
                    "bytes": info.file_size,
                    "comprimido": info.compress_size,
                    "metodo": info.compress_type,
                    "cifrada": bool(info.flag_bits & 0x1),
                }
                for info in infos
            ]
            cifradas = sum(1 for item in entradas if item["cifrada"])
            formato = "zip"
    except (zipfile.BadZipFile, OSError, ValueError):
        entradas = []
        formato = "opaco"

    entropia = entropia_amostra(caminho)
    areas = _areas(entradas)
    total = sum(item["bytes"] for item in entradas)
    comprimido = sum(item["comprimido"] for item in entradas)
    maiores = sorted(entradas, key=lambda item: item["bytes"], reverse=True)[:10]

    achados: list[dict[str, Any]] = []

    if dados_do_nome is None:
        achados.append(
            _achado(
                "atencao",
                "Nome fora do padrão do Android",
                "O arquivo não segue `main.<versionCode>.<pacote>.obb` (nem `patch.`).",
                "O Android e a biblioteca de expansão do Google procuram o OBB **pelo nome**. "
                "Renomeado, o arquivo pode até existir no aparelho — mas o jogo não o encontra "
                "pelo caminho normal e baixa tudo de novo, ou abre sem os dados.",
                "Renomeie para main.<versionCode>.<pacote>.obb, com o versionCode e o pacote "
                "do APK que está na mesma pasta.",
                "Pasta do OBB (Unity: Build Settings → “Split Application Binary” gera o nome certo)",
            )
        )

    if formato != "zip":
        achados.append(
            _achado(
                "info",
                "Conteúdo não listável (OBB opaco ou cifrado)",
                f"O arquivo não abre como ZIP e tem entropia {entropia:.2f} de 8 bits por byte.",
                "OBB gerado com o `jobb -k` (cifrado) ou empacotado pelo motor em formato "
                "próprio não expõe a lista de arquivos sem a chave. Dizer “não deu para listar” "
                "é melhor que inventar nomes.",
                "Se você tem a chave com que o OBB foi gerado, deixe-o sem cifragem apenas "
                "para esta análise — ou analise o export/pasta de origem. Tamanho, nome e "
                "conferência com o APK continuam valendo.",
                "Build do motor (Unity: Player Settings → Publishing Settings)",
            )
        )
    elif cifradas:
        achados.append(
            _achado(
                "info",
                "Parte das entradas está cifrada",
                f"{cifradas} de {len(entradas)} arquivos dentro do OBB estão marcados como cifrados.",
                "Os nomes e tamanhos aparecem (o diretório central não é cifrado), mas o "
                "conteúdo de cada um não abre sem a senha.",
                "Nada a corrigir se foi de propósito; para analisar o conteúdo, gere uma "
                "cópia sem cifragem.",
                "Ferramenta que gerou o OBB",
            )
        )

    if tamanho > LIMITE_ASSET_PACK:
        achados.append(
            _achado(
                "atencao",
                "OBB acima de 1,5 GB",
                f"O arquivo tem {_mb(tamanho)}; o Play distribui até 1,5 GB por asset pack "
                "no Play Asset Delivery (o OBB aceita 2 GB).",
                "Acima de 2 GB por arquivo o formato não aceita; entre 1,5 GB e 2 GB o "
                "caminho recomendado pela Google é o AAB com Play Asset Delivery, que baixa "
                "por partes e não exige o OBB instalado.",
                "Divida os dados em main + patch (até 2 GB cada) ou migre para Play Asset "
                "Delivery com o AAB.",
                "Build do motor → Publishing Settings",
            )
        )

    if formato == "zip" and entradas:
        sem_compressao = sum(
            item["bytes"]
            for item in entradas
            if item["metodo"] == zipfile.ZIP_STORED
            and Path(item["nome"]).suffix.lower() in COMPRIMIVEIS
        )
        if sem_compressao > 20_000_000:
            achados.append(
                _achado(
                    "atencao",
                    "Arquivos que comprimem bem estão sem compressão",
                    f"{_mb(sem_compressao)} em WAV/TGA/JSON/texto dentro do OBB estão "
                    "guardados sem compressão.",
                    "O download fica maior sem nenhum ganho: esses formatos perdem "
                    "tipicamente 50% a 80% de tamanho com deflate.",
                    "Gere o OBB com compressão ligada (Unity: Build Settings → "
                    "“Compress Assets on Build”) e reavalie os WAV.",
                    "Build do motor",
                )
            )

        if areas:
            area, bytes_area = next(iter(areas.items()))
            achados.append(
                _achado(
                    "info",
                    "Onde está o peso do OBB",
                    f"{area}: {_mb(bytes_area)} de {_mb(total)} — "
                    f"{bytes_area / max(total, 1) * 100:.0f}% dos dados.",
                    "É nesta pasta que qualquer corte de tamanho rende; mexer no resto é "
                    "esforço sem resultado visível.",
                    _dica_de_tamanho(area),
                    "Conteúdo do OBB",
                )
            )

    limitacoes = [
        "OBB não tem manifesto nem assinatura: pacote e versão são lidos do **nome do arquivo**.",
        "Nada é descompactado nem decifrado; sem ZIP legível, a lista de arquivos não existe.",
        "O conteúdo só é conferido contra o APK da mesma pasta, quando existe.",
    ]

    return {
        "arquivo": caminho.name,
        "bytes": tamanho,
        "formato": "ZIP" if formato == "zip" else "opaco (não abre como ZIP)",
        "zip": formato == "zip",
        "tipo": (dados_do_nome or {}).get("tipo", ""),
        "versaoCodigo": (dados_do_nome or {}).get("versaoCodigo"),
        "pacote": (dados_do_nome or {}).get("pacote", ""),
        "entradas": len(entradas),
        "tamanhoDescompactado": total,
        "comprimido": comprimido,
        "areas": areas,
        "maiores": [{"nome": item["nome"], "mb": round(item["bytes"] / 1e6, 2)} for item in maiores],
        "entropia": entropia,
        "entradasCifradas": cifradas,
        "achados": achados,
        "limitacoes": limitacoes,
        "conferencia": {
            "pacote": "desconhecido",
            "versaoCodigo": "desconhecido",
            "pacoteDoApk": "",
            "versaoDoApk": None,
        },
    }


def conferir(relatorio_obb: dict[str, Any], relatorio_apk: dict[str, Any] | None) -> dict[str, Any]:
    """Compara o OBB com o APK da mesma pasta — e transforma a diferença em achado.

    É a pergunta que ninguém faz e que quebra o jogo em silêncio: o OBB é da
    versão **20** e o APK é a **14**? O downloader procura
    `main.14.<pacote>.obb`, não acha o arquivo, e o jogo abre sem os dados —
    ou tenta baixar de novo o que já está ali.
    """
    conferencia = relatorio_obb.setdefault(
        "conferencia",
        {"pacote": "desconhecido", "versaoCodigo": "desconhecido", "pacoteDoApk": "", "versaoDoApk": None},
    )
    if not relatorio_apk:
        return conferencia

    pacote_apk = relatorio_apk.get("pacote") or ""
    versao_apk = relatorio_apk.get("versaoCodigo")
    conferencia["pacoteDoApk"] = pacote_apk
    conferencia["versaoDoApk"] = versao_apk

    pacote_obb = relatorio_obb.get("pacote") or ""
    if not pacote_obb or not pacote_apk:
        conferencia["pacote"] = "desconhecido"
    elif pacote_obb == pacote_apk:
        conferencia["pacote"] = "igual"
    else:
        conferencia["pacote"] = "diferente"
        relatorio_obb["achados"].append(
            _achado(
                "critico",
                "O OBB é de outro jogo",
                f"O nome do OBB diz “{pacote_obb}”; o APK desta pasta é “{pacote_apk}”.",
                "O Android procura o OBB pelo pacote do app: um OBB de outro jogo nunca é "
                "encontrado, e o jogo abre sem os dados (ou baixa tudo de novo).",
                "Use o OBB gerado junto com este APK — os dois saem do mesmo build.",
                "Pasta do jogo",
            )
        )

    versao_obb = relatorio_obb.get("versaoCodigo")
    if versao_obb is None or versao_apk is None:
        conferencia["versaoCodigo"] = "desconhecido"
    elif int(versao_obb) == int(versao_apk):
        conferencia["versaoCodigo"] = "igual"
    else:
        conferencia["versaoCodigo"] = "diferente"
        relatorio_obb["achados"].append(
            _achado(
                "critico",
                "O número do OBB não bate com a versão do APK",
                f"O OBB se chama “{relatorio_obb.get('arquivo')}” (versão {versao_obb}); "
                f"o APK desta pasta é a versão {versao_apk}.",
                "O arquivo é encontrado pelo nome `main.<versionCode>.<pacote>.obb`. Com o "
                "número antigo, o jogo procura `main."
                f"{versao_apk}.{pacote_apk or relatorio_obb.get('pacote')}.obb`, não acha, e "
                "abre sem os dados — mesmo com o OBB do lado do APK.",
                "Gere o OBB de novo junto com este APK (o build assina e numera os dois) ou "
                f"renomeie para main.{versao_apk}.{pacote_apk or relatorio_obb.get('pacote')}.obb.",
                "Pasta do jogo",
            )
        )

    return conferencia
