"""Analisar o APK do seu jogo e dizer o que melhorar — com o porquê e onde clicar.

O pedido (18/11):

    ta ok eu to criando um jogo q ele e apk quero q o jarvis possa analisar meu
    jogo e melhorar ele

O JARVIS não abre o seu projeto no Unity, no Godot nem no Android Studio: o que
chega aqui é o **pacote pronto** — e dele dá para dizer muita coisa de verdade,
sem adivinhar.

## O que este módulo lê (e o que ele **não** faz)

Ele abre o APK como ZIP e lê **sem descompactar nada em disco**:

- o `AndroidManifest.xml` **binário** (AXML): pacote, versão, `minSdk`,
  `targetSdk`, permissões, `debuggable`, `allowBackup`, tráfego em claro;
- de que motor o jogo foi feito: Unity, Godot, Unreal, GameMaker, Cocos,
  Defold, LibGDX, Flutter, React Native, Construct/Cordova;
- as arquiteturas (ABIs) que foram embaladas e quanto cada uma pesa;
- onde o tamanho está: `assets/`, `lib/`, `res/`, `classes.dex`, e os dez
  maiores arquivos;
- se a assinatura é v1, v2/v3 (bloco APK Sig) ou nenhuma;
- **o OBB do jogo**, quando ele está na mesma pasta (0.91.45): nome
  (`main.<versionCode>.<pacote>.obb`), tamanho, conteúdo (quando abre como
  ZIP) e a conferência de pacote e versão contra o APK — o OBB da versão 20
  com APK da 14 é achado crítico, porque o jogo não acha os dados.

Ele **não** descompila DEX, não recompila, não assina e não promete “deixar o
jogo melhor” no sentido de diversão. O que ele entrega é: **o diagnóstico do
pacote** e um **plano priorizado** com o lugar exato onde cada ajuste é feito —
a maioria no próprio motor, antes de gerar o APK de novo.

## Uma pasta por APK (0.91.41)

O dono testa com **dois APKs do mesmo jogo**. Para não misturar, cada pacote
ganha a própria pasta em `storage/user-files/jogos/`:

    jogos/
      meu-jogo/            <- parte 1
        meu-jogo.apk
        analise.txt        <- o relatório em português
        analise.json       <- o mesmo relatório, para a tela
      meu-jogo-beta/       <- parte 2
        meu-jogo-beta.apk
        analise.txt
        analise.json

APK solto na raiz de `jogos/` (das versões anteriores) continua sendo lido e
analisado — nada quebra. O que muda é onde o que chega agora é guardado.

## As regras

1. **Nada é extraído.** Só cabeçalhos, diretório central e o manifesto (que é
   lido em memória, com teto). ZIP bomb não ganha nada porque nada infla.
2. **Nada é inventado.** O que não deu para ler aparece como “não deu”, com o
   motivo. Achado sem base não entra no relatório.
3. **O texto diz o que fazer**, não só o que está errado: cada achado traz
   severidade, o que é, por que importa e o caminho do ajuste.
"""
from __future__ import annotations

import json
import re
import shutil
import struct
import zipfile
from pathlib import Path
from typing import Any

from . import obb as obb_mod
from .workspace import safe_path

EXTENSOES = {".apk", ".aab", ".apks", ".xapk"}

# 0.91.45 — o OBB deixou de ser “arquivo que eu não leio”. Ele não é APK (sem
# manifesto, sem DEX, sem assinatura), mas o nome, o tamanho, o conteúdo
# interno (quando é ZIP) e a conferência com o APK dizem muito — e é o que o
# dono pediu: *“pq o obb não é analisado? pode fazer o javis analisar pfv”*.
EXTENSOES_OBB = {obb_mod.EXTENSAO}
EXTENSOES_ACEITAS = EXTENSOES | EXTENSOES_OBB

# 0.91.44 — o teto era 600 MB, e o dono perguntou o que acontece com 1 GB.
# A resposta honesta era “não entra” — e não precisava ser: o envio já é feito
# em pedaços de 1 MB (a memória do servidor não cresce com o tamanho do APK) e
# a análise lê só o diretório central do ZIP. O que faltava era espaço em disco,
# e disso dá para cuidar antes de escrever. 2 GB cobre um APK de jogo com OBB
# embutido; acima disso a recusa diz o número e o que fazer.
MAXIMO_BYTES = 2_000_000_000

# Quanto precisa sobrar no disco depois do APK. Durante o envio o arquivo
# existe duas vezes por alguns segundos: o pedido HTTP é guardado num
# temporário do sistema e só depois copiado para `jogos/<parte>/`.
MARGEM_DISCO = 500_000_000

MAX_ENTRADAS = 60_000
MAX_MANIFESTO = 4 * 1024 * 1024
MAX_BIBLIOTECA = 12 * 1024 * 1024


def rotulo_bytes(total: int | None) -> str:
    """“2 GB”, “600 MB” — o número que a pessoa lê, com a mesma régua da tela."""
    if not total:
        return "0 MB"
    if total >= 1_000_000_000:
        texto = f"{total / 1e9:.1f}".rstrip("0").rstrip(".")
        return f"{texto} GB".replace(".", ",")
    return f"{total / 1e6:.0f} MB"


def espaco_livre(pasta: Path) -> int | None:
    """Espaço livre no disco de `pasta` — `None` quando não dá para saber.

    `None` não bloqueia nada: um sistema de arquivos que não responde ao
    `statvfs` não pode virar recusa de um APK que caberia.
    """
    try:
        return shutil.disk_usage(pasta).free
    except OSError:
        return None


class JogoError(ValueError):
    """Erro esperado, em português, seguro para mostrar na tela."""


# ---------------------------------------------------------------------------
# Onde ficam os APKs
# ---------------------------------------------------------------------------

def raiz(files_root: Path) -> Path:
    """A pasta dos jogos, dentro da área isolada do JARVIS."""
    destino = files_root.resolve() / "jogos"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def _slug(nome: str) -> str:
    """O nome de uma pasta a partir do nome do APK: sem espaço, acento ou “.”."""
    limpo = []
    for letra in nome:
        if letra.isalnum() and letra.isascii():
            limpo.append(letra.lower())
        elif letra in {"-", "_", " ", "."}:
            limpo.append("-")
    texto = "".join(limpo)
    while "--" in texto:
        texto = texto.replace("--", "-")
    texto = texto.strip("-._")
    return texto[:60] or "jogo"


def partes(files_root: Path) -> list[dict[str, Any]]:
    """As pastas de jogo que existem (cada uma com um ou mais APKs dentro)."""
    base = raiz(files_root)
    itens: list[dict[str, Any]] = []
    for caminho in sorted(base.iterdir()):
        if not caminho.is_dir() or caminho.is_symlink() or caminho.name.startswith("."):
            continue
        apks = _apks_em(caminho)
        obbs = _obbs_em(caminho)
        if not apks and not obbs:
            continue
        itens.append(
            {
                "nome": caminho.name,
                "pasta": str(caminho),
                "bytes": sum(item.stat().st_size for item in apks + obbs),
                "apks": [item.name for item in apks],
                # 0.91.45 — o OBB é parte do jogo, não um intruso na pasta.
                "obbs": [item.name for item in obbs],
                "analisado": (caminho / "analise.txt").is_file(),
            }
        )
    return itens


def _apks_em(pasta: Path) -> list[Path]:
    try:
        itens = sorted(pasta.iterdir())
    except OSError:
        return []
    return [
        item
        for item in itens
        if item.is_file() and not item.is_symlink() and item.suffix.lower() in EXTENSOES
    ]


def _obbs_em(pasta: Path) -> list[Path]:
    """Os OBBs dentro de uma pasta de jogo (main e patch, quando houver)."""
    try:
        itens = sorted(pasta.iterdir())
    except OSError:
        return []
    return [
        item
        for item in itens
        if item.is_file() and not item.is_symlink() and item.suffix.lower() in EXTENSOES_OBB
    ]


def pacote_do_zip(arquivo: Any) -> str:
    """O pacote de um ZIP/APK **aberto** (caminho ou arquivo do upload).

    Só o manifesto, e para. Não é `analisar()`: aqui a pergunta é uma só, e um
    OBB na pasta não pode custar a leitura de assinatura e entropia do APK.
    """
    try:
        with zipfile.ZipFile(arquivo) as zip_aberto:
            info = zip_aberto.getinfo("AndroidManifest.xml")
            if info.file_size > MAX_MANIFESTO:
                return ""
            dados = zip_aberto.read("AndroidManifest.xml")
    except (KeyError, OSError, zipfile.BadZipFile, ValueError):
        return ""
    try:
        return str(fatos_do_manifest(ler_manifest(dados))["pacote"] or "")
    except (struct.error, ValueError, IndexError):
        return ""


def pacote_do_apk(caminho: Path) -> str:
    """Só o pacote do APK — o suficiente para achar a pasta do OBB dele."""
    return pacote_do_zip(caminho)


def parte_do_obb_orfao(files_root: Path, pacote: str) -> tuple[Path, str] | None:
    """A pasta que só tem OBB deste pacote (o APK ainda não chegou).

    Quando o OBB é enviado antes do APK, a pasta nasce com o nome do pacote.
    Este é o caminho para o APK entrar **nela** em vez de criar uma pasta nova
    e deixar o OBB sozinho do outro lado.
    """
    if not pacote:
        return None
    for parte in partes(files_root):
        pasta = Path(parte["pasta"])
        if _apks_em(pasta):
            continue
        for item in _obbs_em(pasta):
            dados = obb_mod.do_nome(item.name)
            if dados and dados.get("pacote") == pacote:
                return pasta, parte["nome"]
    return None


def parte_do_obb(files_root: Path, nome: str) -> tuple[Path, str]:
    """Onde guardar o OBB: na pasta do APK **do mesmo jogo**, quando ele existe.

    Se o APK ainda não chegou, a pasta é criada com o nome do pacote — e quando
    o APK chegar (mesmo depois), ele entra na pasta que já existe. Assim o OBB
    nunca fica longe do APK que ele completa.
    """
    base = raiz(files_root)
    dados = obb_mod.do_nome(nome) or {}
    pacote = str(dados.get("pacote") or "")
    if pacote:
        for parte in partes(files_root):
            pasta = Path(parte["pasta"])
            for apk in _apks_em(pasta):
                if pacote_do_apk(apk) == pacote:
                    return pasta, parte["nome"]
    semente = pacote or Path(nome).stem
    candidato = _slug(semente)
    contador = 1
    while True:
        pasta = base / candidato
        if not pasta.exists():
            return pasta, candidato
        # Pasta existe: usa se estiver vazia de APK (só OBBs) ou se for do mesmo
        # pacote; senão, procura um nome livre.
        if not _apks_em(pasta) or (
            pacote and any(pacote_do_apk(apk) == pacote for apk in _apks_em(pasta))
        ):
            return pasta, candidato
        candidato = f"{_slug(semente)}-{contador}"
        contador += 1


def _unico_apk(pasta: Path, referencia: str) -> Path:
    """O único arquivo analisável da pasta — APK ou, na falta dele, o OBB."""
    apks = _apks_em(pasta)
    if len(apks) == 1:
        return apks[0]
    if not apks:
        obbs = _obbs_em(pasta)
        if len(obbs) == 1:
            return obbs[0]
        if obbs:
            nomes = ", ".join(item.name for item in obbs)
            raise JogoError(
                f"A pasta “{referencia}” só tem OBBs ({nomes}). Diga qual: "
                f"analisar jogo {referencia}/{obbs[0].name}"
            )
        raise JogoError(f"A pasta “{referencia}” não tem nenhum APK nem OBB dentro.")
    nomes = ", ".join(item.name for item in apks)
    raise JogoError(
        f"A pasta “{referencia}” tem {len(apks)} APKs ({nomes}). Diga qual: "
        f"analisar jogo {referencia}/{apks[0].name}"
    )


def arquivo(files_root: Path, nome: str) -> Path:
    """Um APK pelo nome — solto na raiz, dentro da parte, ou pela pasta (“jogo/”).

    O que chega do dono é sempre um nome curto: `meu-jogo.apk`, `meu-jogo-beta/`
    ou `meu-jogo-beta/meu-jogo.apk`. Caminho com `..` continua recusado.
    """
    base = raiz(files_root)
    bruto = (nome or "").strip()
    if not bruto:
        raise JogoError("Diga qual APK analisar (ou arraste o arquivo no analisar-jogo.bat).")

    caminho: Path | None = None
    if "/" in bruto or "\\" in bruto:
        try:
            caminho = safe_path(base, bruto)
        except ValueError as exc:
            raise JogoError(str(exc)) from exc
    else:
        try:
            direto = safe_path(base, bruto)
        except ValueError as exc:
            raise JogoError(str(exc)) from exc
        if direto.is_file():
            caminho = direto
        elif direto.is_dir():
            caminho = _unico_apk(direto, bruto)
        else:
            achados = [
                pasta / bruto
                for pasta in (base.iterdir() if base.exists() else [])
                if pasta.is_dir()
                and not pasta.is_symlink()
                and (pasta / bruto).is_file()
                and not (pasta / bruto).is_symlink()
            ]
            if len(achados) == 1:
                caminho = achados[0]
            elif len(achados) > 1:
                onde = " e ".join(f"{item.parent.name}/" for item in achados)
                raise JogoError(
                    f"“{bruto}” existe em {len(achados)} pastas ({onde}). Diga qual: "
                    f"analisar jogo {achados[0].parent.name}/{bruto}"
                )
            else:
                raise JogoError(
                    f"Não achei “{bruto}” na pasta de jogos. Envie o APK primeiro "
                    "(Engenharia reversa → enviar arquivo, ou arraste o arquivo em cima "
                    "do analisar-jogo.bat — ele copia para storage/user-files/jogos)."
                )

    if caminho.suffix.lower() not in EXTENSOES_ACEITAS:
        raise JogoError("A análise aceita APK, AAB, APKS, XAPK — e o OBB do jogo (.obb).")
    if not caminho.is_file() or caminho.is_symlink():
        raise JogoError(f"Não achei “{bruto}” na pasta de jogos.")
    tamanho = caminho.stat().st_size
    if tamanho <= 0:
        raise JogoError("O arquivo está vazio.")
    if tamanho > MAXIMO_BYTES:
        raise JogoError(
            f"O arquivo tem {rotulo_bytes(tamanho)}; o limite é {rotulo_bytes(MAXIMO_BYTES)}. "
            "Acima disso, divida os dados em main + patch (até 2 GB cada) ou use Play Asset Delivery."
        )
    return caminho


def listar(files_root: Path) -> dict[str, Any]:
    """Os jogos já enviados, por parte (pasta) e por arquivo."""
    base = raiz(files_root)
    itens: list[dict[str, Any]] = []
    for caminho in sorted(base.iterdir()):
        if caminho.is_file() and not caminho.is_symlink() and caminho.suffix.lower() in EXTENSOES:
            # Formato antigo (0.91.38–0.91.40): APK solto na raiz de jogos/.
            itens.append(
                {
                    "nome": caminho.name,
                    "bytes": caminho.stat().st_size,
                    "parte": "",
                    "pasta": str(base),
                    "analisado": False,
                }
            )
        elif caminho.is_dir() and not caminho.is_symlink() and not caminho.name.startswith("."):
            for apk in _apks_em(caminho):
                itens.append(
                    {
                        "nome": apk.name,
                        "bytes": apk.stat().st_size,
                        "parte": caminho.name,
                        "pasta": str(caminho),
                        "analisado": (caminho / "analise.txt").is_file(),
                    }
                )
    return {
        "pasta": str(base),
        "quantidade": len(itens),
        "partes": partes(files_root),
        "jogos": itens,
    }


def _gravar_analise(pasta: Path, relatorio: dict[str, Any]) -> None:
    """Grava a análise ao lado do APK: `analise.txt` e `analise.json`."""
    (pasta / "analise.txt").write_text(relatorio.get("texto", ""), encoding="utf-8")
    dados = {chave: valor for chave, valor in relatorio.items() if chave != "texto"}
    (pasta / "analise.json").write_text(
        json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _guardar_obb(origem: Path, files_root: Path, tamanho: int | None = None) -> dict[str, Any]:
    """Guarda o OBB ao lado do APK dele e devolve o relatório já conferido."""
    tamanho = tamanho if tamanho is not None else origem.stat().st_size
    pasta, candidato = parte_do_obb(files_root, origem.name)
    livre = espaco_livre(pasta.parent)
    if livre is not None and livre < tamanho + MARGEM_DISCO:
        raise JogoError(
            f"Não há espaço no disco para guardar este OBB: ele tem {rotulo_bytes(tamanho)} "
            f"e o disco tem {rotulo_bytes(livre)} livres (preciso de mais "
            f"{rotulo_bytes(MARGEM_DISCO)} de folga). Libere espaço e arraste de novo."
        )
    pasta.mkdir(parents=True, exist_ok=True)
    destino = safe_path(pasta, origem.name)
    novo = True
    if destino.is_file() and not destino.is_symlink() and destino.stat().st_size == tamanho:
        # Mesmo OBB de novo: não copia por cima, só analisa o que já está lá.
        novo = False
    else:
        shutil.copy2(origem, destino)
    relatorio = relatar_parte(pasta, parte=candidato)
    _gravar_analise(pasta, relatorio)
    return {
        "parte": candidato,
        "pasta": str(pasta),
        "apk": origem.name,
        "bytes": tamanho,
        "novo": novo,
        "relatorio": relatorio,
    }


def guardar(origem: Path, files_root: Path) -> dict[str, Any]:
    """Guarda o APK na pasta DELE e analisa ali dentro.

    Duas coisas não se misturam: cada pacote fica na própria parte, e a análise
    fica ao lado do pacote a que pertence. Arrastar o mesmo arquivo de novo
    reaproveita a parte (não cria cópia nem pasta nova).
    """
    origem = Path(origem).expanduser()
    if not origem.exists():
        raise JogoError(f"Não achei “{origem}”.")
    if origem.is_symlink() or not origem.is_file():
        raise JogoError("Arraste o arquivo do APK, não uma pasta nem um atalho.")
    if origem.suffix.lower() not in EXTENSOES_ACEITAS:
        raise JogoError("A análise aceita APK, AAB, APKS, XAPK — e o OBB do jogo (.obb).")
    tamanho = origem.stat().st_size
    if tamanho <= 0:
        raise JogoError("O arquivo está vazio.")
    if tamanho > MAXIMO_BYTES:
        raise JogoError(
            f"O arquivo tem {rotulo_bytes(tamanho)}; o limite é {rotulo_bytes(MAXIMO_BYTES)}. "
            "Acima disso, divida os dados em main + patch (até 2 GB cada) ou use Play Asset Delivery."
        )

    base = raiz(files_root)

    # 0.91.45 — o OBB não escolhe pasta pelo próprio nome: ele vai para a pasta
    # do APK do mesmo pacote, para o relatório poder conferir um contra o outro.
    if origem.suffix.lower() in EXTENSOES_OBB:
        return _guardar_obb(origem, files_root, tamanho=tamanho)
    # 0.91.44 — a cópia para `jogos/` precisa caber no disco. Sem esta
    # conferência, um APK grande enchia o disco e o erro que aparecia era
    # “No space left on device”, em inglês, no meio de uma pasta pela metade.
    livre = espaco_livre(base)
    if livre is not None and livre < tamanho + MARGEM_DISCO:
        raise JogoError(
            f"Não há espaço no disco para guardar este APK: ele tem {rotulo_bytes(tamanho)} "
            f"e o disco tem {rotulo_bytes(livre)} livres (preciso de mais "
            f"{rotulo_bytes(MARGEM_DISCO)} de folga). Libere espaço e arraste de novo."
        )

    # Mesmo arquivo (nome e tamanho) já guardado? Reaproveita a parte.
    for pasta in sorted(item["pasta"] for item in partes(files_root)):
        alvo = Path(pasta) / origem.name
        if alvo.is_file() and not alvo.is_symlink() and alvo.stat().st_size == tamanho:
            relatorio = relatar(alvo, parte=Path(pasta).name, pasta=str(pasta))
            _gravar_analise(Path(pasta), relatorio)
            return {
                "parte": Path(pasta).name,
                "pasta": str(pasta),
                "apk": alvo.name,
                "bytes": tamanho,
                "novo": False,
                "relatorio": relatorio,
            }

    nome = _slug(origem.stem)
    candidato = nome
    contador = 1
    while (base / candidato).exists():
        candidato = f"{nome}-{contador}"
        contador += 1
    pasta = base / candidato
    pasta.mkdir(parents=True, exist_ok=False)
    destino = pasta / origem.name
    shutil.copy2(origem, destino)
    relatorio = relatar(destino, parte=candidato, pasta=str(pasta))
    _gravar_analise(pasta, relatorio)
    return {
        "parte": candidato,
        "pasta": str(pasta),
        "apk": destino.name,
        "bytes": tamanho,
        "novo": True,
        "relatorio": relatorio,
    }


# ---------------------------------------------------------------------------
# AndroidManifest.xml binário (AXML)
#
# O manifesto de um APK não é texto: é uma árvore binária com um pool de
# strings e atributos identificados por **resource id**, não por nome. Um leitor
# de XML comum devolve lixo — e foi por isso que este pedaço existe.
# ---------------------------------------------------------------------------

_CHUNK_XML = 0x0003
_CHUNK_STRINGS = 0x0001
_CHUNK_RESMAP = 0x0180
_CHUNK_START_ELEMENT = 0x0102
_CHUNK_END_ELEMENT = 0x0103

# Tipo de valor no atributo. Só os que aparecem no manifesto.
_TIPO_STRING = 0x03
_TIPO_INT_DEC = 0x10
_TIPO_INT_HEX = 0x11
_TIPO_BOOL = 0x12

# Atributos do manifesto que o Android identifica por resource id. Quando o
# arquivo é compilado com `aapt2`, o **nome** do atributo vem vazio e só o id
# sobra — sem esta tabela, `versionName` e `debuggable` sumiriam.
ATRIBUTOS_ANDROID: dict[int, str] = {
    0x01010001: "label",
    0x01010003: "name",
    0x0101000F: "debuggable",
    0x0101020C: "minSdkVersion",
    0x0101021B: "versionCode",
    0x0101021C: "versionName",
    0x01010270: "targetSdkVersion",
    0x01010280: "allowBackup",
    0x010104EA: "extractNativeLibs",
    0x010104EC: "usesCleartextTraffic",
    0x01010572: "compileSdkVersion",
    0x01010603: "requestLegacyExternalStorage",
}


def _pool_de_strings(dados: bytes, inicio: int, tamanho_chunk: int) -> list[str]:
    """O pool UTF-8/UTF-16 do AXML. Índice fora da faixa vira string vazia."""
    # ResStringPool_header: stringCount, styleCount, flags, stringsStart.
    total, estilos, flags, strings_inicio = struct.unpack_from("<IIII", dados, inicio + 8)
    base = inicio + strings_inicio
    fim = inicio + tamanho_chunk
    utf8 = bool(flags & 0x100)
    itens: list[str] = []
    deslocamentos = struct.unpack_from(f"<{total}I", dados, inicio + 28) if total else ()
    for deslocamento in deslocamentos:
        posicao = base + deslocamento
        if posicao < inicio or posicao >= fim:
            itens.append("")
            continue
        try:
            if utf8:
                # UTF-8: dois comprimentos (curto e longo), depois os bytes.
                passos = 1 if dados[posicao] < 0x80 else 2
                posicao += passos
                tamanho = dados[posicao] if dados[posicao] < 0x80 else struct.unpack_from(">H", dados, posicao + 1)[0]
                posicao += 1 if dados[posicao] < 0x80 else 2
                itens.append(dados[posicao:posicao + tamanho].decode("utf-8", "replace"))
            else:
                tamanho = struct.unpack_from("<H", dados, posicao)[0]
                if tamanho & 0x8000:  # comprimento longo (dois u16)
                    tamanho = ((tamanho & 0x7FFF) << 16) | struct.unpack_from("<H", dados, posicao + 2)[0]
                    posicao += 4
                else:
                    posicao += 2
                itens.append(dados[posicao:posicao + tamanho * 2].decode("utf-16-le", "replace"))
        except (struct.error, IndexError):
            itens.append("")
    del estilos
    return itens


def _valor_do_atributo(
    tipo: int, dado: int, bruto: int, strings: list[str]
) -> Any:
    """O valor legível de um atributo AXML (string, número ou booleano)."""
    if tipo == _TIPO_STRING and 0 <= bruto < len(strings):
        return strings[bruto]
    if tipo == _TIPO_BOOL:
        return bool(dado)
    if tipo in (_TIPO_INT_DEC, _TIPO_INT_HEX):
        return dado
    if 0 <= bruto < len(strings) and strings[bruto]:
        return strings[bruto]
    return dado


def ler_axml(dados: bytes) -> list[dict[str, Any]]:
    """Os elementos do manifesto, na ordem, com nome e atributos resolvidos.

    Devolve `[{"nome": "manifest", "atributos": {"package": "com.x", ...}}]`.
    Elemento que não deu para ler é pulado — nunca inventado.
    """
    if len(dados) < 8:
        raise JogoError("O AndroidManifest.xml está curto demais para ser lido.")
    tipo, cabecalho, _tamanho = struct.unpack_from("<HHI", dados, 0)
    if tipo != _CHUNK_XML:
        raise JogoError("O AndroidManifest.xml não está no formato binário esperado.")
    strings: list[str] = []
    resmap: list[int] = []
    elementos: list[dict[str, Any]] = []
    posicao = cabecalho
    while posicao + 8 <= len(dados):
        tipo, cab, tamanho = struct.unpack_from("<HHI", dados, posicao)
        if tamanho < 8 or posicao + tamanho > len(dados):
            break
        if tipo == _CHUNK_STRINGS:
            strings = _pool_de_strings(dados, posicao, tamanho)
        elif tipo == _CHUNK_RESMAP:
            quantidade = (tamanho - cab) // 4
            if quantidade > 0:
                resmap = list(struct.unpack_from(f"<{quantidade}I", dados, posicao + cab))
        elif tipo == _CHUNK_START_ELEMENT:
            if cab < 16 or posicao + cab + 20 > len(dados):
                break
            # ResXMLTree_attrExt começa em +16: ns, name, attributeStart, …
            nome_indice = struct.unpack_from("<I", dados, posicao + 20)[0]
            inicio_atributos, tamanho_atributo, quantidade = struct.unpack_from(
                "<HHH", dados, posicao + 24
            )
            if not tamanho_atributo:
                tamanho_atributo = 20
            atributos: dict[str, Any] = {}
            for indice in range(quantidade):
                # `attributeStart` é relativo ao attrExt (+16), não ao início do bloco.
                base = posicao + 16 + inicio_atributos + indice * tamanho_atributo
                if base + 20 > posicao + tamanho:
                    break
                _ns, nome_attr, bruto, _tam, _res0, tipo_valor, dado = struct.unpack_from(
                    "<IIIHBBI", dados, base
                )
                nome = ""
                if nome_attr < len(strings):
                    nome = strings[nome_attr]
                recurso = resmap[nome_attr] if nome_attr < len(resmap) else 0
                if not nome and recurso in ATRIBUTOS_ANDROID:
                    nome = ATRIBUTOS_ANDROID[recurso]
                if not nome:
                    nome = f"attr_{recurso:08x}" if recurso else ""
                if not nome:
                    continue
                atributos[nome] = _valor_do_atributo(tipo_valor, dado, bruto, strings)
            elementos.append(
                {
                    "nome": strings[nome_indice] if nome_indice < len(strings) else "",
                    "atributos": atributos,
                }
            )
        posicao += tamanho
    return elementos


def ler_manifest_texto(dados: bytes) -> list[dict[str, Any]]:
    """Alguns pacotes trazem o manifesto em XML comum (AAB, ferramentas de build)."""
    import xml.etree.ElementTree as ET  # noqa: PLC0415 - só quando é XML de texto

    try:
        raiz_xml = ET.fromstring(dados.decode("utf-8", "replace"))
    except ET.ParseError as exc:
        raise JogoError("O AndroidManifest.xml não é binário nem XML legível.") from exc
    elementos: list[dict[str, Any]] = []

    def visitar(elemento: Any) -> None:
        atributos = {}
        for chave, valor in elemento.attrib.items():
            atributos[chave.split("}")[-1]] = valor
        elementos.append({"nome": elemento.tag.split("}")[-1], "atributos": atributos})
        for filho in elemento:
            visitar(filho)

    visitar(raiz_xml)
    return elementos


def ler_manifest(dados: bytes) -> list[dict[str, Any]]:
    """Binário ou texto: o que vier, sem inventar. Nada de adivinhar o formato."""
    if dados[:4] == b"PK\x03\x04" or dados[:2] == b"\x1f\x8b":
        raise JogoError("O manifesto veio compactado; não é um APK montado por ferramenta conhecida.")
    if len(dados) >= 4 and struct.unpack_from("<H", dados, 0)[0] == _CHUNK_XML:
        return ler_axml(dados)
    return ler_manifest_texto(dados)


def fatos_do_manifest(elementos: list[dict[str, Any]]) -> dict[str, Any]:
    """Do que interessa no manifesto: pacote, versão, SDKs, permissões, flags."""
    fatos: dict[str, Any] = {
        "pacote": "",
        "versaoNome": "",
        "versaoCodigo": None,
        "minSdk": None,
        "targetSdk": None,
        "compileSdk": None,
        "debuggable": None,
        "allowBackup": None,
        "trafegoEmClaro": None,
        "extrairNativas": None,
        "permissoes": [],
        "atividades": [],
    }
    for elemento in elementos:
        nome = (elemento.get("nome") or "").lower()
        atributos = elemento.get("atributos") or {}
        if nome == "manifest":
            fatos["pacote"] = str(atributos.get("package") or "")
            fatos["versaoNome"] = str(atributos.get("versionName") or "")
            codigo = atributos.get("versionCode")
            fatos["versaoCodigo"] = codigo if isinstance(codigo, int) else None
            compilar = atributos.get("compileSdkVersion")
            if isinstance(compilar, int):
                fatos["compileSdk"] = compilar
        elif nome == "uses-sdk":
            for chave in ("minSdkVersion", "targetSdkVersion"):
                valor = atributos.get(chave)
                if isinstance(valor, int):
                    fatos["minSdk" if chave == "minSdkVersion" else "targetSdk"] = valor
                elif isinstance(valor, str) and valor.isdigit():
                    fatos["minSdk" if chave == "minSdkVersion" else "targetSdk"] = int(valor)
        elif nome == "uses-permission" or nome == "uses-permission-sdk-23":
            permissao = atributos.get("name")
            if isinstance(permissao, str) and permissao:
                fatos["permissoes"].append(permissao)
        elif nome == "application":
            for chave, destino in (
                ("debuggable", "debuggable"),
                ("allowBackup", "allowBackup"),
                ("usesCleartextTraffic", "trafegoEmClaro"),
                ("extractNativeLibs", "extrairNativas"),
            ):
                valor = atributos.get(chave)
                if isinstance(valor, bool):
                    fatos[destino] = valor
                elif isinstance(valor, str) and valor.lower() in {"true", "false"}:
                    fatos[destino] = valor.lower() == "true"
        elif nome in {"activity", "activity-alias"} and len(fatos["atividades"]) < 40:
            atividade = atributos.get("name")
            if isinstance(atividade, str) and atividade:
                fatos["atividades"].append(atividade)
    fatos["permissoes"] = sorted(set(fatos["permissoes"]))
    return fatos


# ---------------------------------------------------------------------------
# Motor do jogo
# ---------------------------------------------------------------------------

# Cada motor: (nome, arquivos que denunciam, dica de onde ajustar).
MOTORES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("Unity", ("libunity.so", "assets/bin/Data/", "unity default resources"), "Unity Editor"),
    ("Godot", ("libgodot", "assets/_godot", "godot_android"), "Godot Editor"),
    ("Unreal", ("libUE4.so", "libUnreal.so", "assets/UE4Game"), "Unreal Editor"),
    ("GameMaker", ("libyoyo.so",), "GameMaker"),
    ("Cocos2d-x", ("libcocos2d", "libcocos.so"), "Cocos Creator"),
    ("Defold", ("libdefold.so",), "Defold Editor"),
    # `classes.dex` existe em QUALQUER APK: como marca, ele “detectava” LibGDX
    # em tudo. O teste pegou — marca genérica não identifica motor nenhum.
    ("LibGDX", ("libgdx.so", "libgdx-box2d.so"), "LibGDX/Gradle"),
    ("Flutter", ("libflutter.so", "assets/flutter_assets/"), "Flutter"),
    ("React Native", ("libhermes.so", "assets/index.android.bundle"), "React Native"),
    # Cordova antes de Construct: os dois usam `assets/www/`, mas só um tem o
    # `cordova.js` — marca específica ganha da genérica.
    ("Cordova/PhoneGap", ("assets/www/cordova.js", "assets/www/cordova_plugins.js"), "Cordova"),
    ("Construct", ("assets/www/", "assets/c3runtime/"), "Construct"),
    ("Unreal (UE5)", ("libUnreal5.so",), "Unreal Editor"),
)


def detectar_motor(nomes: list[str]) -> tuple[str, str]:
    """Motor, pela assinatura mais específica. Desconhecido não vira chute."""
    minusculos = [nome.lower() for nome in nomes]
    for motor, marcas, editor in MOTORES:
        if any(any(marca.lower() in nome for nome in minusculos) for marca in marcas):
            return motor, editor
    return "", ""


def versao_do_unity(zip_aberto: zipfile.ZipFile, nomes: list[str]) -> str:
    """A versão do Unity, lida de `libunity.so` — só os primeiros MB."""
    alvo = next((n for n in nomes if n.lower().endswith("libunity.so")), "")
    if not alvo:
        return ""
    try:
        with zip_aberto.open(alvo) as handle:
            dados = handle.read(MAX_BIBLIOTECA)
    except (KeyError, zipfile.BadZipFile, OSError, RuntimeError):
        return ""
    achado = re.search(rb"(\d{4}\.\d+\.\d+[abfp]\d+)", dados)
    return achado.group(1).decode("ascii", "replace") if achado else ""


# ---------------------------------------------------------------------------
# Assinatura
# ---------------------------------------------------------------------------

def assinaturas(zip_aberto: zipfile.ZipFile, caminho: Path) -> dict[str, Any]:
    """v1 (META-INF) e v2/v3 (bloco APK Sig) — o que está de fato no arquivo."""
    nomes = zip_aberto.namelist()
    v1 = any(
        nome.startswith("META-INF/") and nome.upper().endswith((".RSA", ".DSA", ".EC"))
        for nome in nomes
    )
    tem_manifesto_mf = any(nome.upper() == "META-INF/MANIFEST.MF" for nome in nomes)
    v2 = False
    try:
        with caminho.open("rb") as handle:
            handle.seek(max(0, caminho.stat().st_size - 200_000))
            v2 = b"APK Sig Block 42" in handle.read()
    except OSError:
        v2 = False
    return {"v1": v1, "v2v3": v2, "manifestoMf": tem_manifesto_mf}


# ---------------------------------------------------------------------------
# Análise
# ---------------------------------------------------------------------------

PERIGOSAS = {
    "android.permission.READ_EXTERNAL_STORAGE": "ler arquivos do aparelho",
    "android.permission.WRITE_EXTERNAL_STORAGE": "escrever arquivos do aparelho",
    "android.permission.READ_PHONE_STATE": "ler identificadores do telefone",
    "android.permission.ACCESS_FINE_LOCATION": "localização precisa",
    "android.permission.ACCESS_COARSE_LOCATION": "localização aproximada",
    "android.permission.RECORD_AUDIO": "gravar áudio",
    "android.permission.CAMERA": "usar a câmera",
    "android.permission.READ_CONTACTS": "ler contatos",
    "android.permission.READ_SMS": "ler SMS",
    "android.permission.SEND_SMS": "enviar SMS",
    "android.permission.CALL_PHONE": "fazer ligações",
    "android.permission.GET_ACCOUNTS": "ver contas do aparelho",
    "android.permission.QUERY_ALL_PACKAGES": "ver todos os apps instalados",
}


def _tamanho_por_area(entradas: list[dict[str, Any]]) -> dict[str, int]:
    areas: dict[str, int] = {}
    for entrada in entradas:
        nome = entrada["nome"]
        if "/" in nome:
            area = nome.split("/", 1)[0]
        else:
            area = nome
        areas[area] = areas.get(area, 0) + int(entrada["bytes"])
    return dict(sorted(areas.items(), key=lambda item: item[1], reverse=True))


def _mb(valor: float) -> str:
    return f"{valor / 1e6:.1f} MB".replace(".", ",")


def _achado(
    severidade: str, titulo: str, oque: str, porque: str, como: str, onde: str = ""
) -> dict[str, Any]:
    return {
        "severidade": severidade,  # critico | atencao | info
        "titulo": titulo,
        "o_que_e": oque,
        "por_que_importa": porque,
        "como_melhorar": como,
        "onde": onde,
    }


def ler_entradas(zip_aberto: zipfile.ZipFile) -> list[dict[str, Any]]:
    """O inventário do ZIP, sem inflar nada (só o diretório central)."""
    entradas = []
    for info in zip_aberto.infolist()[:MAX_ENTRADAS]:
        entradas.append(
            {
                "nome": info.filename,
                "bytes": info.file_size,
                "comprimido": info.compress_size,
                "metodo": info.compress_type,
            }
        )
    return entradas


def analisar(caminho: Path) -> dict[str, Any]:
    """O relatório completo do APK: fatos, tamanho, motor, assinatura e achados."""
    try:
        zip_aberto = zipfile.ZipFile(caminho)
    except zipfile.BadZipFile as exc:
        raise JogoError(
            "O arquivo não é um APK válido (não abre como ZIP). APK é um ZIP com "
            "AndroidManifest.xml e classes.dex dentro — confira se o envio terminou."
        ) from exc

    with zip_aberto:
        entradas = ler_entradas(zip_aberto)
        nomes = [entrada["nome"] for entrada in entradas]
        manifesto_bytes = b""
        try:
            info = zip_aberto.getinfo("AndroidManifest.xml")
            if info.file_size > MAX_MANIFESTO:
                raise JogoError("O AndroidManifest.xml é grande demais para esta análise.")
            manifesto_bytes = zip_aberto.read("AndroidManifest.xml")
        except KeyError:
            manifesto_bytes = b""
        except zipfile.BadZipFile as exc:
            raise JogoError("O AndroidManifest.xml está corrompido dentro do ZIP.") from exc

        elementos = ler_manifest(manifesto_bytes) if manifesto_bytes else []
        fatos = fatos_do_manifest(elementos)
        motor, editor = detectar_motor(nomes)
        assinatura = assinaturas(zip_aberto, caminho)
        versao_unity = versao_do_unity(zip_aberto, nomes) if motor == "Unity" else ""

    abis = sorted(
        {
            nome.split("/")[1]
            for nome in nomes
            if nome.startswith("lib/") and nome.count("/") >= 2
        }
    )
    dexes = sorted(nome for nome in nomes if re.fullmatch(r"classes\d*\.dex", nome.lower()))
    areas = _tamanho_por_area(entradas)
    maiores = sorted(entradas, key=lambda item: item["bytes"], reverse=True)[:10]
    total = sum(entrada["bytes"] for entrada in entradas)

    achados: list[dict[str, Any]] = []

    if not manifesto_bytes:
        achados.append(
            _achado(
                "atencao",
                "Sem AndroidManifest.xml legível",
                "O pacote não trouxe o manifesto que o Android usa para instalar o app.",
                "Sem ele o app não instala — e nenhuma outra análise do manifesto vale.",
                "Gere o APK de novo pelo Build do motor (Unity: Build Settings → Build).",
            )
        )

    if fatos["debuggable"]:
        achados.append(
            _achado(
                "critico",
                "APK de depuração (debuggable=true)",
                "Este pacote permite depurador e é mais lento: o código não foi otimizado.",
                "É o build de teste. Publicar assim expõe o app a inspeção e é recusado pela Play.",
                "No motor, troque de Development Build / Debug para **Release**, e gere de novo.",
                "Unity: File → Build Settings → desmarque Development Build · Godot: Export → Release",
            )
        )

    if fatos["allowBackup"] is True:
        achados.append(
            _achado(
                "atencao",
                "Backup do app ligado (allowBackup=true)",
                "O Android pode copiar os dados do jogo para outro aparelho.",
                "Se o jogo guarda progresso ou compras locais, isso vira cópia fora do seu controle.",
                "Desligue, ou limite o que entra no backup com regras próprias.",
                "AndroidManifest: android:allowBackup=\"false\" (ou android:fullBackupContent)",
            )
        )

    if fatos["trafegoEmClaro"] is True:
        achados.append(
            _achado(
                "atencao",
                "Tráfego HTTP liberado (usesCleartextTraffic=true)",
                "O jogo pode falar com servidores por HTTP sem criptografia.",
                "Em rede pública, placar, login ou compra podem ser lidos e alterados no caminho.",
                "Use HTTPS em tudo e deixe o padrão do Android (bloqueado) valendo.",
                "AndroidManifest: remova android:usesCleartextTraffic, ou use network_security_config",
            )
        )

    alvo = fatos["targetSdk"]
    if isinstance(alvo, int) and alvo < 34:
        achados.append(
            _achado(
                "atencao",
                f"targetSdk antigo ({alvo})",
                "O app declara compatibilidade com uma versão antiga do Android.",
                "A Play sobe o mínimo exigido todo ano; abaixo disso o envio é recusado e o "
                "sistema aplica modos de compatibilidade que custam desempenho.",
                "Suba o targetSdk para o valor exigido hoje (34 ou mais) e teste nas versões novas.",
                "Unity: Player Settings → Other Settings → Target API Level · Godot: Export → Target SDK",
            )
        )

    if isinstance(fatos["minSdk"], int) and fatos["minSdk"] < 21:
        achados.append(
            _achado(
                "info",
                f"minSdk muito baixo ({fatos['minSdk']})",
                "O app promete rodar em Androids de 2014 ou antes.",
                "Isso obriga bibliotecas antigas e aparelhos que não rodam o jogo direito — "
                "e quem instala e trava dá nota ruim.",
                "Suba o minSdk para 24 (Android 7) ou mais; quase todo aparelho em uso está acima.",
                "Unity/Godot: Minimum API Level nas configurações de build",
            )
        )

    if len(abis) >= 3:
        achados.append(
            _achado(
                "atencao",
                f"{len(abis)} arquiteturas no mesmo pacote",
                "O APK carrega código nativo para " + ", ".join(abis) + ".",
                "O aparelho usa uma só: as outras só engordam o download (~"
                + _mb(sum(e["bytes"] for e in entradas if e["nome"].startswith("lib/")))
                + " em lib/).",
                "Publique um **AAB** (App Bundle) em vez de APK universal: a Play entrega só a "
                "arquitetura e a densidade do aparelho. Para testar, gere APKs separados por ABI.",
                "Unity: Build App Bundle (Google Play) · Godot: Export → AAB · Gradle: bundleRelease",
            )
        )

    if motor and "arm64-v8a" not in abis and abis:
        achados.append(
            _achado(
                "atencao",
                "Sem arm64-v8a",
                "Não há código nativo de 64 bits no pacote.",
                "Aparelhos de 64 bits sem a biblioteca de 32 bits (e a Play, que exige 64 bits) "
                "não instalam ou rodam pior.",
                "Marque ARM64 nas arquiteturas do build.",
                "Unity: Player Settings → Scripting Backend IL2CPP + ARM64",
            )
        )

    if not assinatura["v2v3"]:
        achados.append(
            _achado(
                "critico" if not assinatura["v1"] else "atencao",
                "Assinatura antiga (só v1)" if assinatura["v1"] else "APK sem assinatura",
                "O pacote não tem o bloco de assinatura v2/v3.",
                "Sem v2/v3 o Android não confere a integridade do arquivo inteiro; a Play exige.",
                "Assine com o `apksigner` do build-tools (ele grava v1+v2+v3) ou deixe o motor/Play assinar.",
                "Android Studio: Build → Generate Signed Bundle / APK",
            )
        )

    perigosas = [p for p in fatos["permissoes"] if p in PERIGOSAS]
    if perigosas:
        achados.append(
            _achado(
                "atencao",
                "Permissões sensíveis pedidas",
                "; ".join(f"{p.rsplit('.', 1)[-1]} ({PERIGOSAS[p]})" for p in perigosas),
                "Cada permissão sensível aparece na ficha da loja e no aviso do Android — "
                "e é motivo de desinstalação quando o jogo não precisa dela.",
                "Remova do manifesto a que o jogo não usa. Rede não precisa de permissão; "
                "salvar o progresso pode ir para a pasta do próprio app.",
                "Unity: Player Settings → Publishing Settings · Godot: Export → Permissions",
            )
        )

    if len(dexes) > 1:
        achados.append(
            _achado(
                "info",
                f"{len(dexes)} arquivos DEX (multidex)",
                "O jogo passou do limite de métodos de um DEX.",
                "Com IL2CPP (Unity) isso normalmente não acontece; se apareceu, há biblioteca demais.",
                "Ative R8/ProGuard e remova bibliotecas que o jogo não usa.",
                "Gradle: minifyEnabled true + shrinkResources true",
            )
        )

    areas_grandes = [item for item in list(areas.items())[:3] if item[1] > 5_000_000]
    if areas_grandes and total:
        achados.append(
            _achado(
                "info",
                "Onde está o tamanho",
                " · ".join(f"{nome}: {_mb(tamanho)}" for nome, tamanho in areas_grandes)
                + f" — total {_mb(total)}.",
                "Tamanho de download é a primeira coisa que o jogador vê na loja; "
                "acima de 100 MB ele desiste antes de jogar.",
                _dica_de_tamanho(motor),
                editor or "Build do motor",
            )
        )

    obbs_internos = [item["nome"] for item in entradas if item["nome"].lower().endswith(".obb")]
    if obbs_internos:
        achados.append(
            _achado(
                "info",
                "Este pacote traz OBB dentro dele",
                f"O arquivo contém {len(obbs_internos)} OBB: "
                + ", ".join(obbs_internos[:3])
                + ("…" if len(obbs_internos) > 3 else "")
                + ".",
                "O OBB é onde costuma estar quase todo o peso do jogo — e, dentro do "
                "pacote, ele aparece como mais uma entrada, sem a análise que merece.",
                "Envie o .obb separado na mesma área (é só arrastar junto com o APK): aí eu "
                "leio o nome, o tamanho, o conteúdo e confiro pacote e versão com o APK.",
                "Pasta do jogo",
            )
        )

    if fatos["extrairNativas"] is True:
        achados.append(
            _achado(
                "info",
                "Bibliotecas nativas descompactadas na instalação",
                "android:extractNativeLibs=true faz o Android copiar as .so para o disco.",
                "Ocupa mais espaço no aparelho do que o download.",
                "Deixe `false` e alinhe as bibliotecas (zipalign -p 4) para elas rodarem do próprio APK.",
                "Gradle: packagingOptions { jniLibs { useLegacyPackaging false } }",
            )
        )

    return {
        "arquivo": caminho.name,
        "bytes": caminho.stat().st_size,
        "pacote": fatos["pacote"],
        "versao": fatos["versaoNome"],
        "versaoCodigo": fatos["versaoCodigo"],
        "minSdk": fatos["minSdk"],
        "targetSdk": fatos["targetSdk"],
        "compileSdk": fatos["compileSdk"],
        "motor": motor,
        "editor": editor,
        "versaoDoMotor": versao_unity,
        "abis": abis,
        "dexes": len(dexes),
        "permissoes": fatos["permissoes"],
        "assinatura": assinatura,
        "entradas": len(entradas),
        "tamanhoDescompactado": total,
        "areas": areas,
        "maiores": [
            {"nome": item["nome"], "mb": round(item["bytes"] / 1e6, 2)} for item in maiores
        ],
        "achados": achados,
    }


def _dica_de_tamanho(motor: str) -> str:
    if motor == "Unity":
        return (
            "No Unity: compressão de textura ASTC, marque “Compress Assets on Build”, "
            "Managed Stripping Level Medium/Alto, e tire do build as cenas e os idiomas que não usa."
        )
    if motor == "Godot":
        return "No Godot: importe áudio em Ogg e textura em VRAM Compressed; exporte só as arquiteturas necessárias."
    if motor in {"Unreal"}:
        return "No Unreal: empacote com ASTC/Oodle e remova assets que não estão em nenhuma cena (Reference Viewer)."
    return (
        "Veja os maiores arquivos abaixo: normalmente são texturas, áudio e vídeo. "
        "Reduza a resolução das texturas e converta áudio para Ogg."
    )


# ---------------------------------------------------------------------------
# O texto do chat
# ---------------------------------------------------------------------------

_SEVERIDADE = {"critico": "CRÍTICO", "atencao": "ATENÇÃO", "info": "INFO"}


_CONFERENCIA_TEXTO = {
    "igual": "igual",
    "diferente": "DIFERENTE",
    "desconhecido": "não deu para conferir",
}


def _linhas_do_obb(item: dict[str, Any]) -> list[str]:
    """As linhas de um OBB — usadas no texto do APK e no texto só do OBB."""
    linhas = [
        f"OBB “{item['arquivo']}” — {_mb(item['bytes'])}:",
        f"  formato: {item['formato']} · {item['entradas']} arquivos · "
        f"{_mb(item['tamanhoDescompactado'])} descompactado · entropia {item['entropia']:.2f}",
    ]
    if item.get("pacote"):
        linhas.append(f"  diz ser: {item['pacote']} · versão {item.get('versaoCodigo')}")
    conferencia = item.get("conferencia") or {}
    if conferencia.get("pacoteDoApk"):
        linhas.append(
            "  conferência com o APK: pacote "
            f"{_CONFERENCIA_TEXTO.get(conferencia.get('pacote', ''), '?')} · versionCode "
            f"{_CONFERENCIA_TEXTO.get(conferencia.get('versaoCodigo', ''), '?')}"
        )
    if item["achados"]:
        linhas.append("")
        for indice, achado in enumerate(item["achados"], start=1):
            linhas.append(f"  {indice}. [{_SEVERIDADE[achado['severidade']]}] {achado['titulo']}")
            linhas.append(f"     O que é: {achado['o_que_e']}")
            linhas.append(f"     Por que importa: {achado['por_que_importa']}")
            linhas.append(f"     Como melhorar: {achado['como_melhorar']}")
            if achado["onde"]:
                linhas.append(f"     Onde: {achado['onde']}")
    if item["maiores"]:
        linhas.append("  Maiores arquivos do OBB:")
        for maior in item["maiores"][:5]:
            linhas.append(f"    {maior['mb']:>7.1f} MB  {maior['nome']}")
    return linhas


def texto_obb(relatorio: dict[str, Any]) -> str:
    """O texto de um relatório que só tem OBB (o APK ainda não foi enviado)."""
    linhas = [f"Análise do OBB “{relatorio['arquivo']}”:"]
    if relatorio.get("pacote"):
        linhas.append(
            f"{relatorio['pacote']} · versão {relatorio.get('versaoCodigo')} "
            "(lido do nome do arquivo)"
        )
    linhas.append("")
    for item in relatorio.get("obbs", []):
        linhas.extend(_linhas_do_obb(item))
        linhas.append("")
    linhas.append(
        "OBB não tem manifesto nem assinatura: o que dá para afirmar dele é o nome, o "
        "tamanho, o conteúdo (quando abre como ZIP) e a conferência com o APK da mesma pasta."
    )
    linhas.append("(Análise feita no seu PC, sem enviar o OBB para lugar nenhum.)")
    if relatorio.get("parte"):
        linhas.append(f"(Guardado em jogos/{relatorio['parte']}/.)")
    return "\n".join(linhas)


def texto(relatorio: dict[str, Any]) -> str:
    """O relatório em português, com o que fazer em cada achado."""
    if relatorio.get("somenteObb"):
        return texto_obb(relatorio)
    linhas = [f"Análise do jogo “{relatorio['arquivo']}”:"]
    identidade = []
    if relatorio["pacote"]:
        identidade.append(relatorio["pacote"])
    if relatorio["versao"]:
        identidade.append(f"versão {relatorio['versao']}")
    if relatorio["motor"]:
        motor = relatorio["motor"]
        if relatorio["versaoDoMotor"]:
            motor += f" {relatorio['versaoDoMotor']}"
        identidade.append(motor)
    if identidade:
        linhas.append(" · ".join(identidade))
    linhas.append(
        f"{_mb(relatorio['tamanhoDescompactado'])} descompactado em {relatorio['entradas']} arquivos · "
        f"ABIs: {', '.join(relatorio['abis']) or 'nenhuma'} · DEX: {relatorio['dexes']}"
    )
    if relatorio["minSdk"] or relatorio["targetSdk"]:
        linhas.append(
            f"Android: minSdk {relatorio['minSdk'] or '?'} · targetSdk {relatorio['targetSdk'] or '?'}"
        )

    if not relatorio["achados"]:
        linhas += ["", "Não achei nada errado no pacote — e isso é o que eu consigo ver daqui."]
    else:
        linhas.append("")
        for indice, achado in enumerate(relatorio["achados"], start=1):
            linhas.append(f"{indice}. [{_SEVERIDADE[achado['severidade']]}] {achado['titulo']}")
            linhas.append(f"   O que é: {achado['o_que_e']}")
            linhas.append(f"   Por que importa: {achado['por_que_importa']}")
            linhas.append(f"   Como melhorar: {achado['como_melhorar']}")
            if achado["onde"]:
                linhas.append(f"   Onde: {achado['onde']}")
        linhas.append("")

    maiores = relatorio["maiores"][:5]
    if maiores:
        linhas.append("Maiores arquivos (é aqui que o peso está):")
        for item in maiores:
            linhas.append(f"  {item['mb']:>6.1f} MB  {item['nome']}")
        linhas.append("")

    if relatorio.get("obbs"):
        linhas.append("")
        linhas.append("O OBB do jogo (os dados que ficam fora do APK):")
        for item in relatorio["obbs"]:
            linhas.extend(_linhas_do_obb(item))
            linhas.append("")

    iphone = relatorio.get("iphone")
    if iphone:
        linhas.append("")
        linhas.append("iPhone (de graça?):")
        linhas.append(f"  {iphone['veredito']}")
        linhas.append(f"  {iphone['porque']}")
        for passo in iphone["passos"][:6]:
            linhas.append(f"  - {passo}")
        linhas.append(f"  Custo: {iphone['custo']}")
        linhas.append(f"  Limite: {iphone['limite']}")
        linhas.append("")

    if (relatorio.get("iphone") or {}).get("e_jogo", True):
        linhas.append(
            "Isto é o que se vê do **pacote pronto**. Não descompilei o jogo nem recompilei: "
            "o que muda o jogo de verdade — equilíbrio, controles, ritmo — só você decide, "
            "e o ajuste é feito no motor e no build de novo."
        )
    else:
        # App que não é jogo (ReVanced, microG): falar de “equilíbrio e controles”
        # aqui seria a frase de outro relatório.
        linhas.append(
            "Isto é o que se vê do **pacote pronto**. Não descompilei, não executei e não "
            "modifiquei o app: o que ele faz em execução não é medido daqui."
        )
    linhas.append("(Análise feita no seu PC, sem enviar o APK para lugar nenhum.)")
    # 0.91.41 — cada APK mora na própria pasta; dizer qual é fecha o ciclo
    # (“guardei ali, e o relatório está do lado do APK”).
    if relatorio.get("parte"):
        linhas.append(
            f"(Guardado em jogos/{relatorio['parte']}/ — o APK, o analise.txt e o "
            "analise.json ficam juntos, um jogo por pasta.)"
        )
    return "\n".join(linhas)


def relatar(caminho: Path, parte: str = "", pasta: str = "") -> dict[str, Any]:
    """O relatório completo, já com o texto — e com a pasta onde ele vive.

    0.91.45 — se há OBB ao lado do APK, ele entra no relatório **conferido
    contra o APK**: pacote e versionCode. É a diferença que quebra o jogo em
    silêncio (OBB da versão 20 com APK da 14), e ela não aparecia em lugar
    nenhum porque o OBB não era lido.
    """
    caminho = Path(caminho)
    if caminho.suffix.lower() in EXTENSOES_OBB:
        return relatar_obb(caminho, parte=parte, pasta=pasta)
    relatorio = analisar(caminho)
    if parte:
        relatorio["parte"] = parte
    if pasta:
        relatorio["pasta"] = pasta
    obbs = _obbs_em(caminho.parent)
    if obbs:
        relatorio["obbs"] = [obb_mod.analisar(item) for item in obbs[:2]]
        for item in relatorio["obbs"]:
            obb_mod.conferir(item, relatorio)
    # 0.92.1 — "quero passar esse app para o iPhone de graça" tem resposta
    # diferente para jogo, para app alternativo e para microG. A resposta sai
    # junto com a análise, em vez de ficar só na documentação.
    relatorio["iphone"] = caminho_para_iphone(relatorio)
    relatorio["texto"] = texto(relatorio)
    return relatorio


def relatar_obb(caminho: Path, parte: str = "", pasta: str = "") -> dict[str, Any]:
    """Relatório de um OBB — sozinho, ou conferido com o APK da mesma pasta."""
    caminho = Path(caminho)
    item = obb_mod.analisar(caminho)
    apk: dict[str, Any] | None = None
    irmaos = _apks_em(caminho.parent)
    if irmaos:
        try:
            apk = analisar(irmaos[0])
        except (JogoError, OSError):
            apk = None
    obb_mod.conferir(item, apk)
    relatorio: dict[str, Any] = {
        "arquivo": caminho.name,
        "bytes": item["bytes"],
        "somenteObb": True,
        "pacote": item.get("pacote") or (apk or {}).get("pacote", ""),
        "versao": (apk or {}).get("versao", ""),
        "versaoCodigo": item.get("versaoCodigo"),
        "minSdk": (apk or {}).get("minSdk"),
        "targetSdk": (apk or {}).get("targetSdk"),
        "compileSdk": (apk or {}).get("compileSdk"),
        "motor": (apk or {}).get("motor", ""),
        "editor": (apk or {}).get("editor", ""),
        "versaoDoMotor": (apk or {}).get("versaoDoMotor", ""),
        "abis": (apk or {}).get("abis", []),
        "dexes": (apk or {}).get("dexes", 0),
        "permissoes": (apk or {}).get("permissoes", []),
        "assinatura": (apk or {}).get("assinatura", {"v1": False, "v2v3": False, "manifestoMf": False}),
        "entradas": 0,
        "tamanhoDescompactado": 0,
        "areas": {},
        "maiores": [],
        "achados": [],
        "obbs": [item],
    }
    if parte:
        relatorio["parte"] = parte
    if pasta:
        relatorio["pasta"] = pasta
    relatorio["iphone"] = caminho_para_iphone(relatorio)
    relatorio["texto"] = texto(relatorio)
    return relatorio


def relatar_parte(pasta: Path, parte: str = "") -> dict[str, Any]:
    """O relatório do que está na pasta: o APK (preferido) ou só o OBB."""
    pasta = Path(pasta)
    apks = _apks_em(pasta)
    if apks:
        return relatar(apks[0], parte=parte or pasta.name, pasta=str(pasta))
    obbs = _obbs_em(pasta)
    if obbs:
        return relatar_obb(obbs[0], parte=parte or pasta.name, pasta=str(pasta))
    raise JogoError("Essa pasta não tem APK nem OBB para analisar.")


# ---------------------------------------------------------------------------
# Dois APKs: “antes” e “depois” do mesmo jogo (0.91.41)
#
# O pedido (18/11): *“ta vou testar com dois apks meus”*. Com dois pacotes na
# pasta, a pergunta natural é o que mudou de um para o outro — e essa é uma
# comparação de **fatos**: tamanho, versão, SDKs, ABIs, permissões, assinatura
# e achados. Nada de “qual é mais divertido”: isso não se lê de um ZIP.
# ---------------------------------------------------------------------------

def _resumo(relatorio: dict[str, Any]) -> dict[str, Any]:
    """Só o que a comparação usa — o relatório inteiro é grande demais."""
    return {
        "arquivo": relatorio["arquivo"],
        "pacote": relatorio["pacote"],
        "versao": relatorio["versao"],
        "motor": relatorio["motor"],
        "versaoDoMotor": relatorio["versaoDoMotor"],
        "bytes": relatorio["bytes"],
        "tamanhoDescompactado": relatorio["tamanhoDescompactado"],
        "entradas": relatorio["entradas"],
        "abis": list(relatorio["abis"]),
        "permissoes": list(relatorio["permissoes"]),
        "assinatura": dict(relatorio["assinatura"]),
        "minSdk": relatorio["minSdk"],
        "targetSdk": relatorio["targetSdk"],
        "achados": [
            {"severidade": item["severidade"], "titulo": item["titulo"]}
            for item in relatorio["achados"]
        ],
    }


def _assinatura_texto(assinatura: dict[str, Any]) -> str:
    partes = []
    if assinatura.get("v1"):
        partes.append("v1")
    if assinatura.get("v2v3"):
        partes.append("v2/v3")
    return " + ".join(partes) if partes else "sem assinatura"


def _variacao(antes: float, depois: float) -> str:
    """“+15,4 MB (+17%)” ou “−15,4 MB (−17%)”, com sinal e vírgula."""
    if antes == depois:
        return "sem mudança"
    delta = depois - antes
    sinal = "+" if delta > 0 else "−"
    texto_delta = f"{sinal}{_mb(abs(delta))}"
    if antes > 0:
        porcento = abs(delta) / antes * 100
        texto_delta += f" ({sinal}{porcento:.0f}%)"
    return texto_delta


def comparar(caminho_a: Path, caminho_b: Path) -> dict[str, Any]:
    """Compara dois APKs já guardados (opcional: antes/depois do mesmo jogo)."""
    a = _resumo(relatar(Path(caminho_a)))
    b = _resumo(relatar(Path(caminho_b)))

    permissoes_a, permissoes_b = set(a["permissoes"]), set(b["permissoes"])
    titulos_a = {item["titulo"] for item in a["achados"]}
    titulos_b = {item["titulo"] for item in b["achados"]}

    return {
        "a": a,
        "b": b,
        "mesmoJogo": bool(a["pacote"]) and a["pacote"] == b["pacote"],
        "variacaoBytes": b["bytes"] - a["bytes"],
        "variacaoDescompactado": b["tamanhoDescompactado"] - a["tamanhoDescompactado"],
        "permissoesNovas": sorted(permissoes_b - permissoes_a),
        "permissoesRemovidas": sorted(permissoes_a - permissoes_b),
        "achadosResolvidos": [item for item in a["achados"] if item["titulo"] not in titulos_b],
        "achadosNovos": [item for item in b["achados"] if item["titulo"] not in titulos_a],
        "texto": "",
    }


def guardar_comparacao(files_root: Path, comparacao: dict[str, Any]) -> str:
    """Grava a comparação numa pasta própria, para não se misturar com os jogos."""
    pasta = raiz(files_root) / "comparacoes"
    pasta.mkdir(parents=True, exist_ok=True)
    nome = f"{_slug(comparacao['a']['arquivo'])}-vs-{_slug(comparacao['b']['arquivo'])}"
    destino = pasta / f"{nome}.txt"
    contador = 1
    while destino.exists():
        destino = pasta / f"{nome}-{contador}.txt"
        contador += 1
    destino.write_text(comparacao.get("texto", ""), encoding="utf-8")
    return str(destino)


def texto_comparacao(comparacao: dict[str, Any]) -> str:
    """A comparação em português — só fatos, com o que fazer no fim."""
    a, b = comparacao["a"], comparacao["b"]
    linhas = ["Comparação dos dois pacotes:", ""]

    for rotulo, item in (("A", a), ("B", b)):
        identidade = [item["arquivo"]]
        detalhe = [item["pacote"] or "pacote não lido"]
        if item["versao"]:
            detalhe.append(f"versão {item['versao']}")
        if item["motor"]:
            motor = item["motor"] + (f" {item['versaoDoMotor']}" if item["versaoDoMotor"] else "")
            detalhe.append(motor)
        linhas.append(f"{rotulo}) {' — '.join(identidade)}")
        linhas.append(f"   {' · '.join(detalhe)}")
        linhas.append(
            f"   {_mb(item['tamanhoDescompactado'])} descompactado · "
            f"{_mb(item['bytes'])} de arquivo · {item['entradas']} arquivos"
        )
        linhas.append("")

    if comparacao["mesmoJogo"]:
        linhas.append(f"É o mesmo jogo (pacote {a['pacote']}) — então dá para comparar antes e depois.")
    elif a["pacote"] and b["pacote"]:
        linhas.append(
            f"São jogos diferentes ({a['pacote']} e {b['pacote']}) — a comparação vale como "
            "retrato de cada um, não como “antes e depois”."
        )
    else:
        linhas.append("Um dos dois está sem manifesto legível — comparei só o que deu para ver.")
    linhas.append("")

    linhas.append("O que mudou de A para B:")
    mudancas = []
    if a["versao"] != b["versao"]:
        mudancas.append(f"  versão: {a['versao'] or '?'} → {b['versao'] or '?'}")
    if a["motor"] != b["motor"]:
        mudancas.append(f"  motor: {a['motor'] or 'não identificado'} → {b['motor'] or 'não identificado'}")
    mudancas.append(
        f"  tamanho descompactado: {_mb(a['tamanhoDescompactado'])} → "
        f"{_mb(b['tamanhoDescompactado'])} ({_variacao(a['tamanhoDescompactado'], b['tamanhoDescompactado'])})"
    )
    mudancas.append(
        f"  tamanho do arquivo: {_mb(a['bytes'])} → {_mb(b['bytes'])} "
        f"({_variacao(a['bytes'], b['bytes'])})"
    )
    if a["abis"] != b["abis"]:
        saiu = [abi for abi in a["abis"] if abi not in b["abis"]]
        entrou = [abi for abi in b["abis"] if abi not in a["abis"]]
        pedacos = []
        if entrou:
            pedacos.append("entrou " + ", ".join(entrou))
        if saiu:
            pedacos.append("saiu " + ", ".join(saiu))
        mudancas.append(
            f"  arquiteturas: {', '.join(a['abis']) or 'nenhuma'} → {', '.join(b['abis']) or 'nenhuma'}"
            + (f" ({'; '.join(pedacos)})" if pedacos else "")
        )
    if (a["minSdk"], a["targetSdk"]) != (b["minSdk"], b["targetSdk"]):
        mudancas.append(
            f"  Android: minSdk {a['minSdk'] or '?'} → {b['minSdk'] or '?'} · "
            f"targetSdk {a['targetSdk'] or '?'} → {b['targetSdk'] or '?'}"
        )
    if a["assinatura"] != b["assinatura"]:
        mudancas.append(
            f"  assinatura: {_assinatura_texto(a['assinatura'])} → {_assinatura_texto(b['assinatura'])}"
        )
    if comparacao["permissoesRemovidas"]:
        mudancas.append("  permissões que saíram: " + ", ".join(comparacao["permissoesRemovidas"]))
    if comparacao["permissoesNovas"]:
        mudancas.append("  permissões que entraram: " + ", ".join(comparacao["permissoesNovas"]))
    linhas += mudancas
    linhas.append("")

    resolvidos = comparacao["achadosResolvidos"]
    novos = comparacao["achadosNovos"]
    linhas.append(f"Achados: A tinha {len(a['achados'])} · B tem {len(b['achados'])}.")
    if resolvidos:
        linhas.append("  Saíram em B (bom sinal — confira se foi de propósito):")
        for item in resolvidos:
            linhas.append(f"    - {item['titulo']}")
    if novos:
        linhas.append("  Apareceram em B:")
        for item in novos:
            linhas.append(f"    - [{_SEVERIDADE[item['severidade']]}] {item['titulo']}")
    if not resolvidos and not novos:
        linhas.append("  Os mesmos achados nos dois pacotes.")
    linhas.append("")

    if b["achados"]:
        linhas.append("O que ainda está em B (por ordem de gravidade):")
        for item in b["achados"]:
            linhas.append(f"  - [{_SEVERIDADE[item['severidade']]}] {item['titulo']}")
        linhas.append("")

    linhas.append(
        "Isto compara os dois **pacotes**. Não mede quadros por segundo nem se o jogo ficou "
        "mais divertido — isso só roda no aparelho."
    )
    linhas.append("(Comparação feita no seu PC, sem enviar os APKs para lugar nenhum.)")
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# “Dá para levar este pacote ao iPhone de graça?” (0.92.1)
# ---------------------------------------------------------------------------
# O dono arrastou dois APKs e pediu:
#
#     to testando e quero passar esses dois apps/jogo para o iphone de graca
#
# A resposta honesta depende do que **aquele** pacote é. Um jogo com projeto no
# Unity sai em WebGL hoje, de graça. Um cliente alternativo do YouTube não tem
# caminho nenhum — o iOS não executa APK, e não existe ReVanced para iOS. Um
# microG é pior: nem faz sentido no iPhone. Dizer “exporte em WebGL” para os
# três seria a mesma frase vazia que o projeto já se corrigiu por escrever.
#
# Por isso o veredito é **por pacote**, fechado, com o motivo e o passo a passo.

# Motores cujo projeto exporta HTML5/WebGL (o APK não vira export: o projeto sai).
MOTORES_COM_WEB = {
    "Unity": (
        "No Unity: `File → Build Settings…`, escolha **WebGL**, `Switch Platform`.",
        "Em `Player Settings → Publishing Settings`, use **Compression Format: Gzip** e ligue "
        "**Decompression Fallback** (sem ele o jogo abre preto em servidor simples).",
        "Clique **Build** e escolha uma pasta — a boa é a que tem `index.html` dentro.",
    ),
    "Godot": (
        "No Godot 4: `Projeto → Exportar…` e adicione um preset **Web**.",
        "Se o jogo não usa threads, prefira a variante **sem threads**: o iPhone só liga "
        "`SharedArrayBuffer` em HTTPS, e `http://192.168.x.x` não é contexto seguro.",
        "**Exportar Projeto** para uma pasta com `index.html`.",
    ),
    "GameMaker": (
        "No GameMaker: `File → Build → Target: HTML5`, e depois `Create Executable`.",
        "A saída é uma pasta com `index.html`.",
    ),
    "Construct": (
        "No Construct 3: `Menu → Project → Export → Web (HTML5)`.",
        "Escolha a opção que gera a pasta com `index.html` (não o `.zip` de loja).",
    ),
    "Cocos2d-x": (
        "No Cocos Creator: `Project → Build`, plataforma **Web Mobile**.",
        "A saída é a pasta de build web, com `index.html`.",
    ),
    "Defold": (
        "No Defold: `Project → Bundle → HTML5`.",
        "Marque para gerar os arquivos descompactados, não só o `.zip`.",
    ),
    "LibGDX": (
        "No projeto LibGDX: `gradlew html:dist` (módulo `html`).",
        "A saída fica em `html/build/dist`, com `index.html`.",
    ),
}

# Pacotes que são app de outra coisa — e o que existe de verdade no iPhone.
APPS_SEM_CAMINHO = (
    (
        ("com.google.android.youtube", "com.vanced.android.youtube", "com.google.android.apps.youtube.music"),
        "cliente alternativo do YouTube (ReVanced/Vanced)",
        "É um app Android modificado do YouTube. O APK não roda no iPhone — nem com conta paga — "
        "e não existe ReVanced para iOS. O equivalente de lá é outro pacote, já pronto.",
        (
            "Sem mexer em nada e sem pagar: app oficial do YouTube (grátis, App Store) — com "
            "anúncio. Para assistir sem anúncio pelo Safari, instale um bloqueador de conteúdo "
            "grátis e ligue em Ajustes → Safari → Extensões; depois abra m.youtube.com.",
            "O equivalente iOS do ReVanced é um **.ipa já modificado** (YTLite/uYou+) instalado "
            "por sideload com AltStore ou Sideloadly e um Apple ID comum. É grátis e você não "
            "compila nada — mas o app expira em 7 dias e precisa ser reinstalado pelo PC.",
            "Com conta Apple Developer (US$ 99/ano) a mesma instalação vale 1 ano, sem renovar "
            "toda semana.",
            "O JARVIS não instala nada no iPhone e não gera .ipa: assinar app de iOS exige a "
            "Apple e um Mac (ou AltServer no PC com iTunes).",
        ),
        "grátis no oficial ou no sideload de 7 dias; US$ 99/ano para 1 ano",
    ),
    (
        ("app.revanced.android.gms", "com.microg", "app.microg", "org.microg", "com.google.android.gms"),
        "microG (os serviços do Google reimplementados)",
        "microG é uma reimplementação dos serviços do Google para **Android**. No iOS não "
        "existe equivalente, e ele nem seria necessário: o iPhone já tem as contas do sistema.",
        (
            "No iPhone não há o que instalar: este pacote só serve para dar login aos apps "
            "modificados no Android.",
            "No iPhone você entra direto com a conta Google do sistema — não precisa de "
            "intermediário para o YouTube oficial.",
            "Se o objetivo era o YouTube alternativo, o caminho é o da linha acima — e ele "
            "existe no iOS como outro pacote, não como este.",
        ),
        "— (não há o que instalar no iPhone)",
    ),
)


def caminho_para_iphone(relatorio: dict[str, Any]) -> dict[str, Any]:
    """O veredito do iPhone para **este** pacote, com o porquê.

    Nunca promete `.ipa` de graça: o único caminho gratuito é WebGL no Safari com
    ícone na tela de início. Tudo o que foge disso é dito como não dá.
    """
    if relatorio.get("somenteObb"):
        return {
            "e_jogo": False,
            "possivel": False,
            "gratis": False,
            "tipo": "dados",
            "veredito": "Isto é o OBB — os dados do jogo, não o jogo.",
            "porque": "OBB é conteúdo que o app Android lê; sozinho ele não abre em lugar nenhum.",
            "passos": ["Envie o APK do mesmo jogo nesta área e eu digo o caminho do iPhone para ele."],
            "custo": "—",
            "limite": "OBB não tem manifesto, assinatura nem ponto de entrada.",
            "fonte": "extensão do arquivo",
        }

    pacote = (relatorio.get("pacote") or "").lower()
    motor = relatorio.get("motor") or ""
    for prefixos, tipo, porque, passos, custo in APPS_SEM_CAMINHO:
        if any(pacote.startswith(prefixo) for prefixo in prefixos):
            return {
                "e_jogo": False,
                "possivel": False,
                "gratis": False,
                "tipo": "app-android",
                "veredito": f"Não dá para levar este pacote ao iPhone: é {tipo}.",
                "porque": porque,
                "passos": list(passos),
                "custo": custo,
                "limite": (
                    "APK não roda no iOS. Isto não é limitação do JARVIS: o iOS só executa "
                    "aplicativo assinado pela Apple."
                ),
                "fonte": f"pacote “{relatorio.get('pacote')}”",
            }

    if motor in MOTORES_COM_WEB:
        passos = [
            "O APK em si **não** vai para o iPhone. Quem vai é o export web do projeto.",
            *MOTORES_COM_WEB[motor],
            "Arraste essa pasta (ou o `.zip` dela) na área “Testar no iPhone”, aqui embaixo.",
            "No iPhone, na mesma rede Wi-Fi: abra o endereço no Safari → Compartilhar → "
            "“Adicionar à Tela de Início”.",
        ]
        return {
            "e_jogo": True,
            "possivel": True,
            "gratis": True,
            "tipo": "jogo-android",
            "veredito": f"Sim, de graça — pelo export WebGL do projeto ({motor}), não pelo APK.",
            "porque": (
                "O iOS não executa APK. O mesmo jogo, exportado em WebGL/HTML5, roda no Safari "
                "do iPhone e vira ícone na tela de início, sem App Store e sem conta paga."
            ),
            "passos": passos,
            "custo": "grátis",
            "limite": (
                "Não é app assinado: não passa pela App Store, não notifica e depende do PC "
                "ligado servindo o arquivo enquanto você joga."
            ),
            "fonte": f"motor {motor}" + (f" {relatorio.get('versaoDoMotor')}" if relatorio.get("versaoDoMotor") else ""),
        }

    if motor in {"Unreal", "Unreal (UE5)"}:
        return {
            "e_jogo": True,
            "possivel": False,
            "gratis": False,
            "tipo": "jogo-android",
            "veredito": "Este jogo é Unreal — e a Epic descontinuou o export HTML5 na 4.24.",
            "porque": (
                "Não há caminho gratuito para o iPhone a partir deste APK: o iOS não executa "
                "APK e o Unreal Engine removeu o export HTML5 na 4.24 — não há site para servir "
                "no Safari."
            ),
            "passos": [
                "As opções reais são build iOS assinado (conta Apple Developer, US$ 99/ano, "
                "com Mac) ou publicar na App Store.",
                "Não há atalho gratuito aqui — e eu prefiro dizer isso a inventar um.",
            ],
            "custo": "US$ 99/ano (conta Apple Developer) + Mac",
            "limite": "Nada disto é “de graça”: o que é grátis é o ícone na tela de início de um export web.",
            "fonte": f"motor {motor}",
        }

    if motor in {"Flutter", "React Native"}:
        return {
            "e_jogo": False,
            "possivel": False,
            "gratis": False,
            "tipo": "app-android",
            "veredito": f"Este pacote é um app feito em {motor}, não um jogo com export web.",
            "porque": (
                "O APK compilado não vira site. Só o **projeto** poderia gerar uma build web "
                "(Flutter Web / React Native Web) — e isso é trabalho no código, não no JARVIS."
            ),
            "passos": [
                "Se você tem o projeto, gere a build web nele e arraste a saída nesta área.",
                "Sem o projeto, não há caminho gratuito: o iOS não executa APK.",
            ],
            "custo": "—",
            "limite": "O JARVIS não recompila app: ele lê o pacote, não reconstrói o projeto.",
            "fonte": f"motor {motor}",
        }

    if motor == "Cordova/PhoneGap":
        return {
            "e_jogo": False,
            "possivel": True,
            "gratis": True,
            "tipo": "app-hibrido",
            "veredito": "Este pacote é Cordova/PhoneGap: o conteúdo já é web.",
            "porque": (
                "O app é uma página dentro do APK (`assets/www`). Servir essa página no Safari "
                "é o caminho — mas o JARVIS não extrai conteúdo de APK (decisão da Reversa), "
                "então o export tem de vir da pasta do projeto."
            ),
            "passos": [
                "No projeto Cordova, a pasta `www/` é a página do app.",
                "Arraste essa pasta (ou o `.zip` dela) na área “Testar no iPhone”.",
                "Abra o endereço no Safari do iPhone e adicione à Tela de Início.",
            ],
            "custo": "grátis",
            "limite": "Recursos nativos do Cordova (câmera, arquivos) não funcionam fora do app.",
            "fonte": f"motor {motor}",
        }

    return {
        "e_jogo": False,
        "possivel": False,
        "gratis": False,
        "tipo": "desconhecido",
        "veredito": "Pelo pacote, não reconheci um motor com export web — então não prometo caminho.",
        "porque": (
            "O iOS não executa APK. Sem saber o motor, dizer “exporte em WebGL” seria chute: "
            "cada motor tem um menu diferente, e alguns não têm export web."
        ),
        "passos": [
            "Abra o projeto no motor e veja se existe export “Web”/“HTML5”.",
            "Se existir, gere e arraste a pasta com `index.html` na área “Testar no iPhone”.",
        ],
        "custo": "—",
        "limite": "Sem motor reconhecido, o único caminho garantido é build iOS assinado (pago).",
        "fonte": "sem marca de motor no pacote",
    }
