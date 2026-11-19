"""O OBB do jogo: ler o que dá para ler (0.91.45).

O pedido que abriu esta versão:

    pq o obb mao e analisado? pode fazer o javis analisar pfv

A resposta anterior — “o OBB não é analisado” — estava na tela, no
`docs/ENGENHARIA-REVERSA.md` e no texto de recusa. Era verdade pela metade: o
OBB não é APK (sem manifesto, sem DEX, sem assinatura), mas **nome, tamanho,
conteúdo e conferência com o APK** dizem muita coisa — e são justamente as
perguntas que quebram o jogo em silêncio:

- o OBB é da versão **20** e o APK é a **14**? O Android procura
  `main.14.<pacote>.obb`, não acha, e o jogo abre sem os dados;
- o OBB é de **outro pacote**? Nunca vai ser encontrado;
- o nome está fora do padrão? O arquivo existe e não serve.

Estes testes prendem cada um desses casos, mais o caminho do envio (o OBB
entra na pasta do APK do mesmo jogo, não numa pasta inventada) e o OBB que
não abre como ZIP (aí a resposta honesta é “não dá para listar”, nunca uma
lista inventada).
"""
from __future__ import annotations

import os
import random
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import jogo, obb
from server.app import create_app
from server.skill_registry import build_registry
from server.tests.test_jogo import _apk, manifesto


# ---------------------------------------------------------------------------
# Ajudantes
# ---------------------------------------------------------------------------

def _obb_zip(destino: Path, *, main: bool = True, pacote: str = "com.exemplo.jogo",
             versao: int = 1, extras: dict[str, bytes] | None = None,
             compressao: int = zipfile.ZIP_DEFLATED) -> Path:
    """Um OBB como o build gera: ZIP com `assets/`, `Audio/` e o nome certo."""
    destino.mkdir(parents=True, exist_ok=True)
    nome = f"{'main' if main else 'patch'}.{versao}.{pacote}.obb"
    caminho = destino / nome
    with zipfile.ZipFile(caminho, "w", compressao) as pacote_zip:
        pacote_zip.writestr("assets/bin/Data/level1.dat", os.urandom(8_000))
        pacote_zip.writestr("assets/bin/Data/level2.dat", os.urandom(4_000))
        pacote_zip.writestr("Audio/tema.ogg", b"OggS" + b"\x00" * 6_000)
        pacote_zip.writestr("Textures/hero.png", b"\x89PNG" + b"\x01" * 3_000)
        for nome_extra, conteudo in (extras or {}).items():
            pacote_zip.writestr(nome_extra, conteudo)
    return caminho


def _obb_opaco(destino: Path, nome: str = "main.1.com.exemplo.jogo.obb", bytes_: int = 64_000) -> Path:
    destino.mkdir(parents=True, exist_ok=True)
    caminho = destino / nome
    sorteio = random.Random(42)
    caminho.write_bytes(bytes(sorteio.randrange(256) for _ in range(bytes_)))
    return caminho


def _projeto(tmp_path: Path) -> tuple[Path, Path]:
    base = tmp_path / "files"
    (base / "jogos").mkdir(parents=True)
    return base, base / "jogos"


def _cliente(tmp_path: Path) -> tuple[TestClient, Path]:
    root = tmp_path / "user-files"
    (root / "jogos").mkdir(parents=True)
    return TestClient(create_app(registry=build_registry(root))), root


# ---------------------------------------------------------------------------
# O nome: a primeira metade da análise
# ---------------------------------------------------------------------------

def test_o_nome_do_obb_diz_tipo_versao_e_pacote():
    dados = obb.do_nome("main.20.com.exemplo.jogo.obb")
    assert dados == {"tipo": "main", "versaoCodigo": 20, "pacote": "com.exemplo.jogo"}

    patch = obb.do_nome("patch.21.com.exemplo.jogo.obb")
    assert patch == {"tipo": "patch", "versaoCodigo": 21, "pacote": "com.exemplo.jogo"}

    # Maiúscula e caminho completo não mudam a leitura.
    assert obb.do_nome("C:/build/MAIN.7.com.a.b.obb")["versaoCodigo"] == 7


@pytest.mark.parametrize(
    "nome",
    [
        "dados.obb",
        "main.com.exemplo.jogo.obb",       # sem versão
        "main.1.obb",                       # sem pacote
        "main.1.com.exemplo.jogo.zip",      # outra extensão
        "beta.1.com.exemplo.jogo.obb",      # tipo desconhecido
        "main.1.com exemplo.obb",           # espaço no pacote
    ],
)
def test_nome_fora_do_padrao_nao_vira_palpite(nome: str):
    assert obb.do_nome(nome) is None


# ---------------------------------------------------------------------------
# O conteúdo
# ---------------------------------------------------------------------------

def test_obb_que_e_zip_lista_arquivos_areas_e_maiores(tmp_path: Path):
    caminho = _obb_zip(tmp_path, versao=3)
    relatorio = obb.analisar(caminho)

    assert relatorio["formato"] == "ZIP"
    assert relatorio["zip"] is True
    assert relatorio["entradas"] == 4
    assert relatorio["tamanhoDescompactado"] > 0
    assert relatorio["pacote"] == "com.exemplo.jogo"
    assert relatorio["versaoCodigo"] == 3
    assert set(relatorio["areas"]) == {"assets", "Audio", "Textures"}
    assert relatorio["areas"]["assets"] == relatorio["areas"]["assets"]
    # O maior é o primeiro, e é o arquivo maior de verdade.
    assert relatorio["maiores"][0]["nome"] == "assets/bin/Data/level1.dat"
    assert relatorio["maiores"][0]["mb"] > 0
    # Nome certo não gera achado de nome.
    assert "Nome fora do padrão do Android" not in [item["titulo"] for item in relatorio["achados"]]
    # O texto do peso aponta a pasta que pesa.
    peso = next(item for item in relatorio["achados"] if item["titulo"] == "Onde está o peso do OBB")
    assert peso["o_que_e"].startswith("assets:")


def test_obb_cifrado_nao_inventa_lista_de_arquivos(tmp_path: Path):
    """O caso que antes era um “não” seco: agora é um “não, e por quê”."""
    caminho = _obb_opaco(tmp_path)
    relatorio = obb.analisar(caminho)

    assert relatorio["zip"] is False
    assert relatorio["entradas"] == 0
    assert relatorio["maiores"] == []
    assert relatorio["formato"].startswith("opaco")
    assert relatorio["entropia"] > 7.0  # bytes aleatórios não comprimem
    titulos = [item["titulo"] for item in relatorio["achados"]]
    assert "Conteúdo não listável (OBB opaco ou cifrado)" in titulos
    # E diz o que **continua** valendo, em vez de só recusar.
    achado = next(item for item in relatorio["achados"] if item["titulo"].startswith("Conteúdo não"))
    assert "Tamanho, nome e conferência com o APK continuam valendo" in achado["como_melhorar"]


def test_obb_vazio_e_extensao_errada_sao_recusados_com_frase(tmp_path: Path):
    vazio = tmp_path / "main.1.com.exemplo.jogo.obb"
    vazio.write_bytes(b"")
    with pytest.raises(obb.ObbError, match="vazio"):
        obb.analisar(vazio)

    outro = tmp_path / "jogo.apk"
    outro.write_bytes(b"PK\x03\x04")
    with pytest.raises(obb.ObbError, match=r"\.obb"):
        obb.analisar(outro)


def test_arquivos_que_comprimem_bem_sem_compressao_viram_achado(tmp_path: Path):
    """30 MB de JSON guardados sem compressão: o download engorda à toa."""
    caminho = _obb_zip(
        tmp_path,
        extras={"Textos/dialogos.json": b'{"linha": "texto"} ' * 2_000_000},
        compressao=zipfile.ZIP_STORED,
    )
    relatorio = obb.analisar(caminho)
    titulos = [item["titulo"] for item in relatorio["achados"]]
    assert "Arquivos que comprimem bem estão sem compressão" in titulos


# ---------------------------------------------------------------------------
# A conferência com o APK: o que quebra o jogo em silêncio
# ---------------------------------------------------------------------------

def _apk_relatorio(tmp_path: Path, *, pacote="com.exemplo.jogo", versao=14) -> dict:
    caminho = _apk(tmp_path / "apk" / "meu.apk", manifest=manifesto(pacote=pacote, versao_codigo=versao))
    return jogo.analisar(caminho)


def test_obb_da_mesma_versao_e_pacote_confere(tmp_path: Path):
    relatorio = obb.analisar(_obb_zip(tmp_path, versao=14))
    conferencia = obb.conferir(relatorio, _apk_relatorio(tmp_path))

    assert conferencia["pacote"] == "igual"
    assert conferencia["versaoCodigo"] == "igual"
    assert conferencia["pacoteDoApk"] == "com.exemplo.jogo"
    assert [item["severidade"] for item in relatorio["achados"]].count("critico") == 0


def test_obb_de_outro_jogo_e_critico(tmp_path: Path):
    relatorio = obb.analisar(_obb_zip(tmp_path, versao=14, pacote="com.outro.jogo"))
    obb.conferir(relatorio, _apk_relatorio(tmp_path))

    critico = [item for item in relatorio["achados"] if item["severidade"] == "critico"]
    assert [item["titulo"] for item in critico] == ["O OBB é de outro jogo"]
    assert "com.outro.jogo" in critico[0]["o_que_e"]
    assert "com.exemplo.jogo" in critico[0]["o_que_e"]


def test_obb_com_versao_diferente_do_apk_e_critico_e_diz_o_nome_certo(tmp_path: Path):
    """O achado que só existe porque o OBB é lido junto com o APK."""
    relatorio = obb.analisar(_obb_zip(tmp_path, versao=20))
    obb.conferir(relatorio, _apk_relatorio(tmp_path, versao=14))

    assert relatorio["conferencia"]["versaoCodigo"] == "diferente"
    critico = next(item for item in relatorio["achados"] if item["severidade"] == "critico")
    assert critico["titulo"] == "O número do OBB não bate com a versão do APK"
    # A frase ensina o nome que o jogo procura — não só “está errado”.
    assert "main.14.com.exemplo.jogo.obb" in critico["como_melhorar"]


def test_obb_sozinho_nao_inventa_conferencia(tmp_path: Path):
    relatorio = obb.analisar(_obb_zip(tmp_path, versao=14))
    conferencia = obb.conferir(relatorio, None)
    assert conferencia["pacote"] == "desconhecido"
    assert conferencia["versaoCodigo"] == "desconhecido"
    assert not [item for item in relatorio["achados"] if item["severidade"] == "critico"]


# ---------------------------------------------------------------------------
# Guardar: o OBB entra na pasta do APK, não numa pasta própria
# ---------------------------------------------------------------------------

def test_o_obb_entra_na_pasta_do_apk_do_mesmo_pacote(tmp_path: Path):
    files, jogos = _projeto(tmp_path)
    apk = _apk(tmp_path / "entrada" / "meu-jogo.apk", manifest=manifesto(pacote="com.exemplo.jogo", versao_codigo=14))
    jogo.guardar(apk, files)

    relatorio = jogo.guardar(_obb_zip(tmp_path / "entrada", versao=14), files)

    assert relatorio["parte"] == "meu-jogo"
    assert (jogos / "meu-jogo" / "main.14.com.exemplo.jogo.obb").is_file()
    # A pasta já tem APK: o que volta é o relatório do APK **com** o OBB
    # conferido — é o par que o dono quer ver, não dois relatórios soltos.
    assert relatorio["relatorio"].get("somenteObb") is not True
    assert len(relatorio["relatorio"]["obbs"]) == 1
    assert relatorio["relatorio"]["obbs"][0]["conferencia"]["versaoCodigo"] == "igual"

    completo = jogo.relatar_parte(jogos / "meu-jogo")
    assert completo.get("somenteObb") is not True
    assert len(completo["obbs"]) == 1
    assert completo["obbs"][0]["conferencia"]["pacote"] == "igual"


def test_apk_enviado_depois_entra_na_pasta_do_obb(tmp_path: Path):
    """A ordem do envio não pode separar o par.

    Sem isso, quem arrastasse o OBB primeiro ficava com o OBB em
    `jogos/com-exemplo-jogo/` e o APK em `jogos/meu-jogo/` — dois relatórios
    soltos, e a conferência (a parte que importa) nunca acontecia.
    """
    base, root = _cliente(tmp_path)
    dados_obb = _obb_zip(tmp_path / "entrada", versao=14).read_bytes()

    envio_obb = base.post(
        "/api/jogo/upload",
        files={"upload": ("main.14.com.exemplo.jogo.obb", dados_obb)},
        data={"confirmed": "true"},
    )
    assert envio_obb.status_code == 200, envio_obb.text
    pasta = root / "jogos" / "com-exemplo-jogo"
    assert (pasta / "main.14.com.exemplo.jogo.obb").is_file()

    apk = _apk(tmp_path / "entrada" / "meu-jogo.apk", manifest=manifesto(pacote="com.exemplo.jogo", versao_codigo=14))
    envio_apk = base.post(
        "/api/jogo/upload",
        files={"upload": ("meu-jogo.apk", apk.read_bytes())},
        data={"confirmed": "true"},
    )
    assert envio_apk.status_code == 200, envio_apk.text
    assert envio_apk.json()["result"]["parte"] == "com-exemplo-jogo"
    assert (pasta / "meu-jogo.apk").is_file()

    # Uma pasta só, com o par dentro — e o relatório já conferido.
    partes = base.get("/api/jogo/arquivos").json()["result"]["partes"]
    assert [item["nome"] for item in partes] == ["com-exemplo-jogo"]
    assert partes[0]["apks"] == ["meu-jogo.apk"]
    assert partes[0]["obbs"] == ["main.14.com.exemplo.jogo.obb"]
    relatorio = envio_apk.json()["result"]["relatorio"]
    assert relatorio["obbs"][0]["conferencia"]["pacote"] == "igual"


# ---------------------------------------------------------------------------
# Pela tela: a rota de upload e a de análise
# ---------------------------------------------------------------------------

def test_a_rota_aceita_o_obb_e_guarda_junto_do_apk(tmp_path: Path):
    base, root = _cliente(tmp_path)
    apk = _apk(tmp_path / "entrada" / "meu-jogo.apk", manifest=manifesto(pacote="com.exemplo.jogo", versao_codigo=14))
    envio_apk = base.post(
        "/api/jogo/upload", files={"upload": ("meu-jogo.apk", apk.read_bytes())}, data={"confirmed": "true"}
    )
    assert envio_apk.status_code == 200, envio_apk.text

    dados_obb = _obb_zip(tmp_path / "entrada", versao=14).read_bytes()
    envio = base.post(
        "/api/jogo/upload",
        files={"upload": ("main.14.com.exemplo.jogo.obb", dados_obb)},
        data={"confirmed": "true"},
    )
    assert envio.status_code == 200, envio.text
    corpo = envio.json()["result"]
    assert corpo["parte"] == "meu-jogo"
    assert (root / "jogos" / "meu-jogo" / "main.14.com.exemplo.jogo.obb").is_file()

    # A listagem mostra o OBB dentro da parte (não como um jogo solto).
    lista = base.get("/api/jogo/arquivos").json()["result"]
    parte = next(item for item in lista["partes"] if item["nome"] == "meu-jogo")
    assert parte["obbs"] == ["main.14.com.exemplo.jogo.obb"]
    assert lista["quantidade"] == 1

    # O relatório do APK traz o OBB, conferido.
    analise = base.get("/api/jogo/analisar", params={"arquivo": "meu-jogo/meu-jogo.apk"}).json()["result"]
    assert len(analise["obbs"]) == 1
    assert analise["obbs"][0]["conferencia"]["versaoCodigo"] == "igual"
    assert "OBB" in analise["texto"]
    assert (root / "jogos" / "meu-jogo" / "analise.txt").is_file()


def test_analisar_o_obb_sozinho_devolve_somente_obb(tmp_path: Path):
    base, root = _cliente(tmp_path)
    dados = _obb_zip(tmp_path / "entrada", versao=9).read_bytes()
    base.post(
        "/api/jogo/upload",
        files={"upload": ("main.9.com.exemplo.jogo.obb", dados)},
        data={"confirmed": "true"},
    )
    analise = base.get("/api/jogo/analisar", params={"arquivo": "main.9.com.exemplo.jogo.obb"}).json()["result"]

    assert analise["somenteObb"] is True
    assert analise["obbs"][0]["entradas"] == 4
    assert "Análise do OBB" in analise["texto"]
    assert analise["achados"] == []  # os achados do OBB ficam no bloco dele


def test_a_rota_recusa_extensao_que_nao_e_apk_nem_obb(tmp_path: Path):
    base, _ = _cliente(tmp_path)
    resposta = base.post(
        "/api/jogo/upload", files={"upload": ("jogo.exe", b"MZ")}, data={"confirmed": "true"}
    )
    assert resposta.status_code == 400
    assert resposta.json()["error"]["code"] == "INVALID_FORMAT"
    assert ".obb" in resposta.json()["error"]["message"]


def test_o_obb_que_ja_esta_la_pede_substituicao(tmp_path: Path):
    base, _ = _cliente(tmp_path)
    dados = _obb_zip(tmp_path / "entrada", versao=1).read_bytes()
    primeira = base.post(
        "/api/jogo/upload",
        files={"upload": ("main.1.com.exemplo.jogo.obb", dados)},
        data={"confirmed": "true"},
    )
    assert primeira.status_code == 200
    repetida = base.post(
        "/api/jogo/upload",
        files={"upload": ("main.1.com.exemplo.jogo.obb", dados)},
        data={"confirmed": "true"},
    )
    assert repetida.status_code == 409
    assert repetida.json()["error"]["code"] == "FILE_EXISTS"


# ---------------------------------------------------------------------------
# O pacote que traz OBB dentro (XAPK/APKS)
# ---------------------------------------------------------------------------

def test_apk_que_traz_obb_dentro_aponta_para_o_envio_separado(tmp_path: Path):
    caminho = tmp_path / "pacote.xapk"
    with zipfile.ZipFile(caminho, "w") as pacote:
        pacote.writestr("AndroidManifest.xml", manifesto(pacote="com.exemplo.jogo"))
        pacote.writestr("classes.dex", b"dex\n035\x00")
        pacote.writestr("main.1.com.exemplo.jogo.obb", b"PK\x03\x04" + b"\x00" * 100)

    relatorio = jogo.analisar(caminho)
    achado = next(item for item in relatorio["achados"] if item["titulo"] == "Este pacote traz OBB dentro dele")
    assert "main.1.com.exemplo.jogo.obb" in achado["o_que_e"]
    assert "Envie o .obb separado" in achado["como_melhorar"]
