"""Constrói um AndroidManifest.xml **binário** de verdade, para os testes.

O manifesto de um APK não é texto: é uma árvore de blocos com um pool de
strings, e os atributos do Android são identificados por **resource id** — não
pelo nome. Um teste que só usasse XML comum nunca exercitaria o leitor de
verdade, e foi justamente o leitor de verdade que errou primeiro (no APK
compilado, o nome do atributo chega vazio e só o id sobra).

Este arquivo não é um teste: é o molde usado por `test_jogo.py`, escrito à mão a
partir da estrutura pública do AXML (blocos com cabeçalho de 8 bytes).
"""
from __future__ import annotations

import struct
from typing import Any

# Resource ids do Android que o leitor traduz de volta para o nome.
IDS = {
    "label": 0x01010001,
    "name": 0x01010003,
    "debuggable": 0x0101000F,
    "minSdkVersion": 0x0101020C,
    "versionCode": 0x0101021B,
    "versionName": 0x0101021C,
    "targetSdkVersion": 0x01010270,
    "allowBackup": 0x01010280,
    "extractNativeLibs": 0x010104EA,
    "usesCleartextTraffic": 0x010104EC,
}

TIPO_STRING = 0x03
TIPO_INT = 0x10
TIPO_BOOL = 0x12


class Construtor:
    """Monta o arquivo byte a byte, guardando o pool e o mapa de recursos."""

    def __init__(self) -> None:
        self.strings: list[str] = []
        self.resmap: dict[int, int] = {}
        self.chunks: list[bytes] = []

    def _str(self, valor: str) -> int:
        self.strings.append(valor)
        return len(self.strings) - 1

    def _attr_android(self, nome: str) -> int:
        """Um índice de string **vazio** por atributo, com o id no resource map.

        É o que o `aapt2` faz: o nome do atributo chega vazio e só o id sobra.
        """
        indice = self._str("")
        self.resmap[indice] = IDS[nome]
        return indice

    def elemento(
        self,
        nome: str,
        atributos: list[tuple[str, Any, str]],
        *,
        sem_id: tuple[str, ...] = (),
    ) -> None:
        """`atributos`: (nome, valor, tipo) — tipo é `string`, `int` ou `bool`.

        Nomes em `sem_id` são gravados como texto (é o caso de `package`); os
        demais, quando são do Android, usam resource id como o `aapt2` faz.
        """
        indice_nome = self._str(nome)
        pacote: list[bytes] = []
        for nome_attr, valor, tipo in atributos:
            usa_id = nome_attr in IDS and nome_attr not in sem_id
            indice_attr = self._attr_android(nome_attr) if usa_id else self._str(nome_attr)
            bruto = 0xFFFFFFFF
            dado = 0
            if tipo == "string":
                bruto = self._str(str(valor))
                tipo_valor = TIPO_STRING
                dado = bruto
            elif tipo == "bool":
                tipo_valor = TIPO_BOOL
                dado = 1 if valor else 0
            else:
                tipo_valor = TIPO_INT
                dado = int(valor)
            pacote.append(
                struct.pack("<IIIHBBI", 0xFFFFFFFF, indice_attr, bruto, 8, 0, tipo_valor, dado)
            )
        corpo = b"".join(pacote)
        # Cabeçalho do nó (16) + attrExt (20) + atributos. `headerSize` é 36: é
        # até onde começa o primeiro atributo.
        tamanho = 36 + len(corpo)
        cabecalho = struct.pack("<HHIII", 0x0102, 36, tamanho, 0, 0xFFFFFFFF)
        metadados = struct.pack("<IIHHHHHH", 0xFFFFFFFF, indice_nome, 20, 20, len(atributos), 0, 0, 0)
        self.chunks.append(cabecalho + metadados + corpo)

    def namespace(self, prefixo: str, uri: str) -> None:
        cabecalho = struct.pack("<HHIII", 0x0100, 16, 24, 0, 0xFFFFFFFF)
        self.chunks.append(cabecalho + struct.pack("<II", self._str(prefixo), self._str(uri)))

    def montar(self) -> bytes:
        # Pool UTF-16: cabeçalho, deslocamentos, depois os textos.
        textos = b""
        deslocamentos: list[int] = []
        for valor in self.strings:
            deslocamentos.append(len(textos))
            textos += struct.pack("<H", len(valor)) + valor.encode("utf-16-le") + b"\x00\x00"
            if len(textos) % 4:
                textos += b"\x00" * (4 - len(textos) % 4)
        cabecalho_pool = 28
        inicio_textos = cabecalho_pool + 4 * len(self.strings)
        corpo_pool = struct.pack(f"<{len(self.strings)}I", *deslocamentos) + textos
        pool = (
            struct.pack(
                "<HHIIIIII",
                0x0001,
                28,
                cabecalho_pool + len(corpo_pool),
                len(self.strings),
                0,
                0,  # UTF-16
                inicio_textos,
                0,
            )
            + corpo_pool
        )

        mapa = b""
        if self.resmap:
            limite = max(self.resmap) + 1
            tabela = [self.resmap.get(indice, 0) for indice in range(limite)]
            mapa = struct.pack("<HHI", 0x0180, 8, 8 + 4 * limite) + struct.pack(
                f"<{limite}I", *tabela
            )

        corpo = pool + mapa + b"".join(self.chunks)
        return struct.pack("<HHI", 0x0003, 8, 8 + len(corpo)) + corpo


def manifesto(
    *,
    pacote: str = "com.exemplo.jogo",
    versao_nome: str = "1.0.0",
    versao_codigo: int = 1,
    min_sdk: int = 23,
    target_sdk: int = 34,
    debuggable: bool = False,
    allow_backup: bool = True,
    trafego_em_claro: bool | None = None,
    extrair_nativas: bool | None = None,
    permissoes: tuple[str, ...] = ("android.permission.INTERNET",),
    atividades: tuple[str, ...] = ("com.exemplo.jogo.MainActivity",),
) -> bytes:
    """Um manifesto binário com a mesma forma do que sai de um build real."""
    construtor = Construtor()
    construtor.namespace("android", "http://schemas.android.com/apk/res/android")
    # `package` não é atributo do Android: sai como texto, sem resource id.
    construtor.elemento(
        "manifest",
        [
            ("package", pacote, "string"),
            ("versionCode", versao_codigo, "int"),
            ("versionName", versao_nome, "string"),
        ],
        sem_id=("package",),
    )
    construtor.elemento(
        "uses-sdk",
        [("minSdkVersion", min_sdk, "int"), ("targetSdkVersion", target_sdk, "int")],
    )
    for permissao in permissoes:
        construtor.elemento("uses-permission", [("name", permissao, "string")])
    atributos_app: list[tuple[str, Any, str]] = [("allowBackup", allow_backup, "bool")]
    if debuggable:
        atributos_app.append(("debuggable", True, "bool"))
    if trafego_em_claro is not None:
        atributos_app.append(("usesCleartextTraffic", trafego_em_claro, "bool"))
    if extrair_nativas is not None:
        atributos_app.append(("extractNativeLibs", extrair_nativas, "bool"))
    construtor.elemento("application", atributos_app)
    for atividade in atividades:
        construtor.elemento("activity", [("name", atividade, "string")])
    return construtor.montar()
