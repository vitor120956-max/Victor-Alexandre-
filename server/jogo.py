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
- se a assinatura é v1, v2/v3 (bloco APK Sig) ou nenhuma.

Ele **não** descompila DEX, não recompila, não assina e não promete “deixar o
jogo melhor” no sentido de diversão. O que ele entrega é: **o diagnóstico do
pacote** e um **plano priorizado** com o lugar exato onde cada ajuste é feito —
a maioria no próprio motor, antes de gerar o APK de novo.

## As regras

1. **Nada é extraído.** Só cabeçalhos, diretório central e o manifesto (que é
   lido em memória, com teto). ZIP bomb não ganha nada porque nada infla.
2. **Nada é inventado.** O que não deu para ler aparece como “não deu”, com o
   motivo. Achado sem base não entra no relatório.
3. **O texto diz o que fazer**, não só o que está errado: cada achado traz
   severidade, o que é, por que importa e o caminho do ajuste.
"""
from __future__ import annotations

import re
import struct
import zipfile
from pathlib import Path
from typing import Any

from .workspace import safe_path

EXTENSOES = {".apk", ".aab", ".apks", ".xapk"}
MAXIMO_BYTES = 600_000_000
MAX_ENTRADAS = 60_000
MAX_MANIFESTO = 4 * 1024 * 1024
MAX_BIBLIOTECA = 12 * 1024 * 1024


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


def arquivo(files_root: Path, nome: str) -> Path:
    """Um APK pelo nome, dentro da pasta de jogos — nunca fora dela."""
    try:
        caminho = safe_path(raiz(files_root), nome)
    except ValueError as exc:
        raise JogoError(str(exc)) from exc
    if caminho.suffix.lower() not in EXTENSOES:
        raise JogoError("A análise aceita APK, AAB, APKS ou XAPK do seu jogo.")
    if not caminho.is_file() or caminho.is_symlink():
        raise JogoError(
            f"Não achei “{nome}” na pasta de jogos. Envie o APK primeiro "
            "(Engenharia reversa → enviar arquivo, ou copie para storage/user-files/jogos)."
        )
    tamanho = caminho.stat().st_size
    if tamanho <= 0:
        raise JogoError("O arquivo está vazio.")
    if tamanho > MAXIMO_BYTES:
        raise JogoError(f"O arquivo tem {tamanho / 1e6:.0f} MB; o limite é {MAXIMO_BYTES / 1e6:.0f} MB.")
    return caminho


def listar(files_root: Path) -> dict[str, Any]:
    """Os jogos já enviados, para a tela e para o chat."""
    base = raiz(files_root)
    itens = []
    for caminho in sorted(base.iterdir()):
        if not caminho.is_file() or caminho.is_symlink():
            continue
        if caminho.suffix.lower() not in EXTENSOES:
            continue
        itens.append({"nome": caminho.name, "bytes": caminho.stat().st_size})
    return {"pasta": str(base), "quantidade": len(itens), "jogos": itens}


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


def texto(relatorio: dict[str, Any]) -> str:
    """O relatório em português, com o que fazer em cada achado."""
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

    linhas.append(
        "Isto é o que se vê do **pacote pronto**. Não descompilei o jogo nem recompilei: "
        "o que muda o jogo de verdade — equilíbrio, controles, ritmo — só você decide, "
        "e o ajuste é feito no motor e no build de novo."
    )
    linhas.append("(Análise feita no seu PC, sem enviar o APK para lugar nenhum.)")
    return "\n".join(linhas)


def relatar(caminho: Path) -> dict[str, Any]:
    relatorio = analisar(caminho)
    relatorio["texto"] = texto(relatorio)
    return relatorio
