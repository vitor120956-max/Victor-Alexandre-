"""O APK do jogo: manifesto binário lido de verdade e plano de melhoria (0.91.38).

O pedido (18/11):

    ta ok eu to criando um jogo q ele e apk quero q o jarvis possa analisar meu
    jogo e melhorar ele

O que dava para fazer **sem inventar**: abrir o pacote como ZIP, ler o
`AndroidManifest.xml` **binário** (não é texto: os atributos do Android são
identificados por resource id), descobrir o motor, medir onde o peso está e
apontar o ajuste certo em cada achado.

O que estes testes prendem:

1. o leitor de AXML acerta pacote, versão, SDKs, permissões e flags — inclusive
   quando o nome do atributo vem vazio, que é o caso do APK real;
2. um APK de depuração, com 3 arquiteturas, sem assinatura v2 e com permissão
   sensível **não passa** como “está tudo bem”;
3. motor, tamanho e assinatura são medidos, não adivinhados;
4. arquivo que não é APK, caminho que sai da pasta e arquivo vazio dão erro
   explicado — nunca relatório pela metade.
"""
from __future__ import annotations

import struct
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import jogo
from server.app import create_app
from server.skill_registry import build_registry

# O molde do manifesto binário mora ao lado, sem o prefixo `test_` (não é teste).
import importlib.util as _importlib

_spec = _importlib.spec_from_file_location("axml_de_teste", Path(__file__).with_name("_axml.py"))
_axml = _importlib.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_axml)
manifesto = _axml.manifesto

PEDACO_UNITY = b"\x00" * 4096 + b"2021.3.16f1" + b"\x00" * 4096


def _apk(
    destino: Path,
    *,
    manifest: bytes | None = None,
    abis: tuple[str, ...] = ("armeabi-v7a", "arm64-v8a"),
    motor: str = "unity",
    dexes: int = 1,
    assinatura_v1: bool = True,
    assinatura_v2: bool = False,
    extras: dict[str, bytes] | None = None,
) -> Path:
    """Um APK sintético, montado como um build de verdade monta."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as pacote:
        if manifest is not None:
            pacote.writestr("AndroidManifest.xml", manifest)
        for indice in range(dexes):
            pacote.writestr(f"classes{indice or ''}.dex", b"dex\n035\x00" + b"\x00" * 200)
        for abi in abis:
            if motor == "unity":
                pacote.writestr(f"lib/{abi}/libunity.so", PEDACO_UNITY)
            elif motor == "godot":
                pacote.writestr(f"lib/{abi}/libgodot_android.so", b"\x00" * 2048)
            else:
                pacote.writestr(f"lib/{abi}/libprincipal.so", b"\x00" * 1024)
        if motor == "unity":
            pacote.writestr("assets/bin/Data/globalgamemanagers", b"\x00" * 1024)
            pacote.writestr("assets/bin/Data/sharedassets0.assets", b"\x00" * 900_000)
        if assinatura_v1:
            pacote.writestr("META-INF/MANIFEST.MF", b"Manifest-Version: 1.0\r\n")
            pacote.writestr("META-INF/CERT.RSA", b"\x30\x82" + b"\x00" * 64)
        for nome, conteudo in (extras or {}).items():
            pacote.writestr(nome, conteudo)
    if assinatura_v2:
        # O bloco APK Sig fica no fim; aqui basta o marcador, que é o que o
        # leitor procura para dizer “tem v2/v3”.
        with destino.open("ab") as arquivo:
            arquivo.write(b"APK Sig Block 42")
    return destino


@pytest.fixture()
def pasta(tmp_path) -> Path:
    root = tmp_path / "user-files"
    (root / "jogos").mkdir(parents=True)
    return root


# ---------------------------------------------------------------------------
# O manifesto binário
# ---------------------------------------------------------------------------

def test_le_o_manifesto_binario_como_um_apk_de_verdade():
    elementos = jogo.ler_manifest(manifesto(debuggable=True, target_sdk=30))
    fatos = jogo.fatos_do_manifest(elementos)

    assert fatos["pacote"] == "com.exemplo.jogo"
    assert fatos["versaoNome"] == "1.0.0"
    assert fatos["versaoCodigo"] == 1
    assert fatos["minSdk"] == 23
    assert fatos["targetSdk"] == 30
    assert fatos["debuggable"] is True
    assert fatos["allowBackup"] is True
    assert fatos["atividades"] == ["com.exemplo.jogo.MainActivity"]


def test_atributo_sem_nome_e_resolvido_pelo_resource_id():
    """No APK compilado o nome do atributo chega **vazio**; sem o id, some tudo."""
    dados = manifesto()
    assert b"versionName" not in dados[:400], "o molde tem de imitar o aapt2 (nome vazio)"
    fatos = jogo.fatos_do_manifest(jogo.ler_manifest(dados))
    assert fatos["versaoNome"] == "1.0.0"


def test_permissoes_em_ordem_e_sem_repeticao():
    fatos = jogo.fatos_do_manifest(
        jogo.ler_manifest(
            manifesto(
                permissoes=(
                    "android.permission.CAMERA",
                    "android.permission.INTERNET",
                    "android.permission.CAMERA",
                )
            )
        )
    )
    assert fatos["permissoes"] == ["android.permission.CAMERA", "android.permission.INTERNET"]


def test_manifesto_de_texto_tambem_e_lido():
    """AAB e algumas ferramentas trazem o manifesto em XML comum."""
    texto = b"""<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.texto.jogo">
  <uses-sdk android:minSdkVersion="24" android:targetSdkVersion="34" />
  <uses-permission android:name="android.permission.INTERNET" />
  <application android:debuggable="true" />
</manifest>"""
    fatos = jogo.fatos_do_manifest(jogo.ler_manifest(texto))
    assert fatos["pacote"] == "com.texto.jogo"
    assert fatos["minSdk"] == 24
    assert fatos["debuggable"] is True


def test_manifesto_truncado_nao_derruba_a_analise():
    """Arquivo cortado devolve o que deu para ler — e não uma exceção no meio."""
    dados = manifesto()[:220]
    elementos = jogo.ler_manifest(dados)
    assert isinstance(elementos, list)


def test_manifesto_que_nao_e_nem_binario_nem_texto_explica():
    with pytest.raises(jogo.JogoError) as erro:
        jogo.ler_manifest(b"\x00\x01\x02\x03 nada de conhecido")
    assert "não é binário nem XML legível" in str(erro.value)


# ---------------------------------------------------------------------------
# O motor
# ---------------------------------------------------------------------------

def test_reconhece_unity_por_libunity_e_assets():
    assert jogo.detectar_motor(["lib/arm64-v8a/libunity.so"])[0] == "Unity"
    assert jogo.detectar_motor(["assets/bin/Data/globalgamemanagers"])[0] == "Unity"


def test_reconhece_godot_unreal_e_game_maker():
    assert jogo.detectar_motor(["lib/arm64-v8a/libgodot_android.so"])[0] == "Godot"
    assert jogo.detectar_motor(["lib/arm64-v8a/libUE4.so"])[0] == "Unreal"
    assert jogo.detectar_motor(["lib/armeabi-v7a/libyoyo.so"])[0] == "GameMaker"


def test_motor_desconhecido_nao_vira_chute():
    # Nenhuma marca de motor: dizer “é Unity” aqui seria chute.
    assert jogo.detectar_motor(["classes.dex", "res/layout/main.xml"]) == ("", "")


def test_versao_do_unity_e_lida_da_biblioteca(tmp_path):
    caminho = _apk(tmp_path / "jogo.apk", manifest=manifesto())
    relatorio = jogo.analisar(caminho)
    assert relatorio["motor"] == "Unity"
    assert relatorio["versaoDoMotor"] == "2021.3.16f1"


# ---------------------------------------------------------------------------
# O diagnóstico
# ---------------------------------------------------------------------------

def test_apk_de_depuracao_e_reprovado_com_o_onde_corrigir(tmp_path):
    caminho = _apk(tmp_path / "debug.apk", manifest=manifesto(debuggable=True))
    relatorio = jogo.analisar(caminho)
    critico = next(a for a in relatorio["achados"] if a["titulo"].startswith("APK de depuração"))
    assert critico["severidade"] == "critico"
    assert "Build Settings" in critico["onde"]
    assert "Release" in critico["como_melhorar"]


def test_tres_arquiteturas_viram_achado_de_tamanho(tmp_path):
    caminho = _apk(
        tmp_path / "tres.apk",
        manifest=manifesto(),
        abis=("armeabi-v7a", "arm64-v8a", "x86"),
    )
    relatorio = jogo.analisar(caminho)
    assert relatorio["abis"] == ["arm64-v8a", "armeabi-v7a", "x86"]
    achado = next(a for a in relatorio["achados"] if "arquiteturas" in a["titulo"])
    assert "AAB" in achado["como_melhorar"]


def test_sem_arm64_ele_avisa(tmp_path):
    caminho = _apk(tmp_path / "32.apk", manifest=manifesto(), abis=("armeabi-v7a",))
    relatorio = jogo.analisar(caminho)
    assert any(a["titulo"] == "Sem arm64-v8a" for a in relatorio["achados"])


def test_assinatura_v1_sem_v2_avisa_e_v2_nao(tmp_path):
    antigo = jogo.analisar(_apk(tmp_path / "v1.apk", manifest=manifesto(), assinatura_v2=False))
    novo = jogo.analisar(_apk(tmp_path / "v2.apk", manifest=manifesto(), assinatura_v2=True))

    assert antigo["assinatura"] == {"v1": True, "v2v3": False, "manifestoMf": True}
    assert any("Assinatura antiga" in a["titulo"] for a in antigo["achados"])
    assert not any("Assinatura" in a["titulo"] for a in novo["achados"])


def test_apk_sem_assinatura_nenhuma_e_critico(tmp_path):
    relatorio = jogo.analisar(
        _apk(tmp_path / "sem.apk", manifest=manifesto(), assinatura_v1=False)
    )
    achado = next(a for a in relatorio["achados"] if "sem assinatura" in a["titulo"])
    assert achado["severidade"] == "critico"


def test_target_sdk_antigo_avisa_com_a_conta_do_ano(tmp_path):
    caminho = _apk(tmp_path / "velho.apk", manifest=manifesto(target_sdk=29))
    relatorio = jogo.analisar(caminho)
    achado = next(a for a in relatorio["achados"] if a["titulo"].startswith("targetSdk antigo"))
    assert "29" in achado["titulo"]
    assert "34" in achado["como_melhorar"]


def test_permissoes_sensiveis_aparecem_com_o_que_fazem(tmp_path):
    caminho = _apk(
        tmp_path / "perm.apk",
        manifest=manifesto(
            permissoes=(
                "android.permission.INTERNET",
                "android.permission.READ_CONTACTS",
                "android.permission.CAMERA",
            )
        ),
    )
    relatorio = jogo.analisar(caminho)
    achado = next(a for a in relatorio["achados"] if "Permissões sensíveis" in a["titulo"])
    assert "READ_CONTACTS (ler contatos)" in achado["o_que_e"]
    assert "CAMERA (usar a câmera)" in achado["o_que_e"]
    assert "INTERNET" not in achado["o_que_e"]


def test_apk_limpo_nao_inventa_problema(tmp_path):
    """Sem defeito, o relatório diz que não achou nada — não “acha” por achar."""
    caminho = _apk(
        tmp_path / "limpo.apk",
        manifest=manifesto(target_sdk=35, allow_backup=False, min_sdk=24),
        abis=("arm64-v8a", "armeabi-v7a"),
        assinatura_v2=True,
    )
    relatorio = jogo.analisar(caminho)
    titulos = [a["titulo"] for a in relatorio["achados"]]
    assert not any("depuração" in t or "Assinatura" in t or "targetSdk" in t for t in titulos)
    assert not any("arquiteturas" in t for t in titulos)


def test_apk_sem_manifesto_explica_em_vez_de_fingir(tmp_path):
    caminho = _apk(tmp_path / "sem-manifesto.apk", manifest=None)
    relatorio = jogo.analisar(caminho)
    achado = next(a for a in relatorio["achados"] if "Sem AndroidManifest.xml" in a["titulo"])
    assert "não instala" in achado["por_que_importa"]


def test_tamanho_por_area_e_maiores(tmp_path):
    caminho = _apk(
        tmp_path / "grande.apk",
        manifest=manifesto(),
        extras={"assets/video/intro.mp4": b"\x00" * 2_000_000},
    )
    relatorio = jogo.analisar(caminho)
    assert relatorio["areas"]["assets"] > 2_000_000
    assert relatorio["maiores"][0]["nome"] == "assets/video/intro.mp4"
    assert relatorio["tamanhoDescompactado"] > 2_000_000


# ---------------------------------------------------------------------------
# O texto do chat
# ---------------------------------------------------------------------------

def test_o_texto_ensina_o_que_fazer_em_cada_achado(tmp_path):
    caminho = _apk(tmp_path / "relatorio.apk", manifest=manifesto(debuggable=True))
    texto = jogo.relatar(caminho)["texto"]

    assert "Análise do jogo “relatorio.apk”" in texto
    assert "com.exemplo.jogo" in texto
    assert "Unity 2021.3.16f1" in texto
    assert "[CRÍTICO] APK de depuração" in texto
    assert "O que é:" in texto and "Por que importa:" in texto
    assert "Como melhorar:" in texto and "Onde:" in texto
    assert "Maiores arquivos" in texto


def test_o_texto_diz_o_que_ele_nao_faz():
    """Sem isso, “melhorar o jogo” vira promessa que ele não cumpre."""
    texto = jogo.texto(
        {
            "arquivo": "x.apk",
            "pacote": "com.x",
            "versao": "1",
            "motor": "",
            "versaoDoMotor": "",
            "tamanhoDescompactado": 1000,
            "entradas": 3,
            "abis": [],
            "dexes": 1,
            "minSdk": None,
            "targetSdk": None,
            "achados": [],
            "maiores": [],
        }
    )
    assert "Não descompilei o jogo nem recompilei" in texto
    assert "sem enviar o APK para lugar nenhum" in texto
    assert "Não achei nada errado no pacote" in texto


# ---------------------------------------------------------------------------
# Erros e limites
# ---------------------------------------------------------------------------

def test_arquivo_que_nao_e_zip_explica_com_o_proximo_passo(tmp_path):
    caminho = tmp_path / "falso.apk"
    caminho.write_bytes(b"isto nao e um zip")
    with pytest.raises(jogo.JogoError) as erro:
        jogo.analisar(caminho)
    assert "não é um APK válido" in str(erro.value)
    assert "confira se o envio terminou" in str(erro.value)


def test_extensao_errada_e_recusada(pasta):
    (pasta / "jogos" / "jogo.txt").write_text("nao e apk")
    with pytest.raises(jogo.JogoError) as erro:
        jogo.arquivo(pasta, "jogo.txt")
    assert "aceita APK" in str(erro.value)


def test_caminho_que_sai_da_pasta_e_recusado(pasta):
    with pytest.raises(jogo.JogoError):
        jogo.arquivo(pasta, "../fora.apk")


def test_arquivo_ausente_ensina_onde_colocar(pasta):
    with pytest.raises(jogo.JogoError) as erro:
        jogo.arquivo(pasta, "nao-existe.apk")
    assert "Engenharia reversa" in str(erro.value)


def test_arquivo_vazio_e_recusado(pasta):
    (pasta / "jogos" / "vazio.apk").write_bytes(b"")
    with pytest.raises(jogo.JogoError) as erro:
        jogo.arquivo(pasta, "vazio.apk")
    assert "vazio" in str(erro.value)


def test_listar_mostra_so_apk(pasta):
    (pasta / "jogos" / "a.apk").write_bytes(b"x")
    (pasta / "jogos" / "b.txt").write_text("nao")
    lista = jogo.listar(pasta)
    assert [item["nome"] for item in lista["jogos"]] == ["a.apk"]


# ---------------------------------------------------------------------------
# A rota
# ---------------------------------------------------------------------------

@pytest.fixture()
def cliente(tmp_path):
    root = tmp_path / "user-files"
    (root / "jogos").mkdir(parents=True)
    app = create_app(registry=build_registry(root))
    return TestClient(app), root


def test_a_rota_analisa_e_devolve_texto(cliente):
    base, root = cliente
    _apk(root / "jogos" / "meu.apk", manifest=manifesto(debuggable=True))

    resposta = base.get("/api/jogo/analisar", params={"arquivo": "meu.apk"})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["ok"] is True
    assert corpo["result"]["motor"] == "Unity"
    assert "Análise do jogo" in corpo["result"]["texto"]


def test_a_rota_lista_os_jogos(cliente):
    base, root = cliente
    _apk(root / "jogos" / "meu.apk", manifest=manifesto())
    corpo = base.get("/api/jogo/arquivos").json()
    assert corpo["result"]["jogos"][0]["nome"] == "meu.apk"


def test_a_rota_explica_arquivo_inexistente(cliente):
    base, _ = cliente
    resposta = base.get("/api/jogo/analisar", params={"arquivo": "nada.apk"})
    assert resposta.status_code == 400
    assert resposta.json()["error"]["code"] == "JOGO_INVALIDO"


def test_a_rota_envia_o_apk_com_confirmacao(cliente):
    base, root = cliente
    dados = _apk(Path("/tmp") / "envio.apk", manifest=manifesto())

    sem_confirmar = base.post("/api/jogo/upload", files={"upload": ("envio.apk", dados.read_bytes())})
    assert sem_confirmar.status_code == 400
    assert sem_confirmar.json()["error"]["code"] == "CONFIRMATION_REQUIRED"

    confirmado = base.post(
        "/api/jogo/upload",
        files={"upload": ("envio.apk", dados.read_bytes())},
        data={"confirmed": "true"},
    )
    assert confirmado.status_code == 200, confirmado.text
    # 0.91.41 — o APK não fica solto: entra em jogos/<parte>/envio.apk
    corpo = confirmado.json()["result"]
    assert corpo["parte"] == "envio"
    assert (root / "jogos" / "envio" / "envio.apk").is_file()
    assert (root / "jogos" / "envio" / "analise.txt").is_file()


def test_a_rota_recusa_extensao_errada(cliente):
    base, _ = cliente
    resposta = base.post(
        "/api/jogo/upload",
        files={"upload": ("jogo.exe", b"MZ")},
        data={"confirmed": "true"},
    )
    assert resposta.status_code == 400
    assert resposta.json()["error"]["code"] == "INVALID_FORMAT"


def test_analisar_nao_descompacta_nada_em_disco(cliente, tmp_path):
    """O APK é lido em memória: a pasta de jogos continua com um arquivo só."""
    base, root = cliente
    _apk(root / "jogos" / "meu.apk", manifest=manifesto())
    antes = sorted(p.name for p in (root / "jogos").iterdir())
    base.get("/api/jogo/analisar", params={"arquivo": "meu.apk"})
    depois = sorted(p.name for p in (root / "jogos").iterdir())
    assert antes == depois


def test_o_manifesto_do_teste_e_um_axml_de_verdade():
    """Se o molde virar XML comum, os testes param de exercitar o leitor real."""
    dados = manifesto()
    tipo, cabecalho, tamanho = struct.unpack_from("<HHI", dados, 0)
    assert tipo == 0x0003
    assert cabecalho == 8
    assert tamanho == len(dados)
    # O pool é UTF-16: o nome do elemento aparece com um byte nulo entre letras.
    assert "uses-permission".encode("utf-16-le") in dados


# ---------------------------------------------------------------------------
# 0.91.41 — dois APKs, duas pastas: separar, analisar e guardar cada um no seu
# ---------------------------------------------------------------------------
#
# Pedido do dono: *“faça e ele separar e analisar e guardar em pastas/partes
# diferentes”*. As duas armadilhas que os testes prendem:
#
# 1. o `.bat` entregava só o primeiro APK (`%~1`) e o segundo sumia calado;
# 2. os dois pacotes eram gravados lado a lado em `jogos/`, com as análises
#    sem dono — impossível saber qual relatório era de qual build.

def _projeto(tmp_path, nome="files"):
    base = tmp_path / nome
    (base / "jogos").mkdir(parents=True)
    return base, base / "jogos"


def _apk_de(nome: str, destino_dir: Path, *, pacote="com.exemplo.jogo", motor="unity") -> Path:
    caminho = destino_dir / nome
    return _apk(caminho, manifest=manifesto(pacote=pacote), motor=motor)


def test_dois_apks_viram_duas_partes_e_nao_se_misturam(tmp_path):
    files, jogos = _projeto(tmp_path)
    fora = tmp_path / "entrada"
    um = _apk_de("teste-1.apk", fora)
    dois = _apk_de("teste-2.apk", fora, pacote="com.exemplo.jogo.beta", motor="godot")

    primeiro = jogo.guardar(um, files)
    segundo = jogo.guardar(dois, files)

    assert primeiro["parte"] == "teste-1"
    assert segundo["parte"] == "teste-2"
    assert primeiro["pasta"] != segundo["pasta"]

    # cada pasta tem o SEU apk e a SUA análise, e nada do outro
    for guardado, nome in ((primeiro, "teste-1"), (segundo, "teste-2")):
        pasta = Path(guardado["pasta"])
        assert pasta.name == nome
        assert (pasta / f"{nome}.apk").is_file()
        assert (pasta / "analise.txt").is_file()
        assert (pasta / "analise.json").is_file()
        assert sorted(item.name for item in pasta.iterdir()) == [
            "analise.json",
            "analise.txt",
            f"{nome}.apk",
        ]

    # e a análise de cada um fala do pacote certo
    texto_um = (Path(primeiro["pasta"]) / "analise.txt").read_text(encoding="utf-8")
    texto_dois = (Path(segundo["pasta"]) / "analise.txt").read_text(encoding="utf-8")
    assert "teste-1.apk" in texto_um and "teste-2.apk" not in texto_um
    assert "teste-2.apk" in texto_dois and "teste-1.apk" not in texto_dois
    assert "Godot" in texto_dois


def test_a_analise_gravada_ao_lado_do_apk_abre_como_json(tmp_path):
    import json

    files, _ = _projeto(tmp_path)
    guardado = jogo.guardar(_apk_de("meu-jogo.apk", tmp_path / "entrada"), files)
    dados = json.loads((Path(guardado["pasta"]) / "analise.json").read_text(encoding="utf-8"))
    assert dados["pacote"] == "com.exemplo.jogo"
    assert dados["motor"] == "Unity"
    assert "achados" in dados
    assert "texto" not in dados  # o texto é o .txt; o json é para a tela


def test_o_mesmo_arquivo_de_novo_reaproveita_a_parte(tmp_path):
    files, _ = _projeto(tmp_path)
    origem = _apk_de("igual.apk", tmp_path / "entrada")
    primeiro = jogo.guardar(origem, files)
    segundo = jogo.guardar(origem, files)

    assert primeiro["pasta"] == segundo["pasta"]
    assert segundo["novo"] is False
    # não criou “igual-1/” nem uma segunda cópia
    assert [item.name for item in (files / "jogos").iterdir()] == ["igual"]


def test_dois_arquivos_com_o_mesmo_nome_viram_partes_diferentes(tmp_path):
    files, _ = _projeto(tmp_path)
    a = _apk_de("jogo.apk", tmp_path / "build-a", pacote="com.a")
    b = _apk_de("jogo.apk", tmp_path / "build-b", pacote="com.b")
    b.write_bytes(b.read_bytes() + b"x")  # tamanho diferente: não é o mesmo arquivo

    primeiro = jogo.guardar(a, files)
    segundo = jogo.guardar(b, files)
    assert primeiro["parte"] == "jogo"
    assert segundo["parte"] == "jogo-1"
    assert primeiro["pasta"] != segundo["pasta"]


def test_o_nome_da_parte_nao_leva_espaco_acento_nem_ponto(tmp_path):
    files, _ = _projeto(tmp_path)
    curto = _apk_de("Meu Jogo Épico!.apk", tmp_path / "entrada")
    guardado = jogo.guardar(curto, files)
    assert guardado["parte"] == "meu-jogo-pico"
    assert Path(guardado["pasta"]).name == "meu-jogo-pico"


def test_arquivo_acha_pela_parte_e_pelo_caminho_dentro_dela(tmp_path):
    files, _ = _projeto(tmp_path)
    guardado = jogo.guardar(_apk_de("meu-jogo.apk", tmp_path / "entrada"), files)
    parte = guardado["parte"]

    pela_parte = jogo.arquivo(files, parte)
    pelo_caminho = jogo.arquivo(files, f"{parte}/meu-jogo.apk")
    pelo_nome_solto = jogo.arquivo(files, "meu-jogo.apk")
    assert pela_parte == pelo_caminho == pelo_nome_solto
    assert pela_parte.name == "meu-jogo.apk"


def test_nome_igual_em_duas_partes_pede_qual_em_vez_de_escolher(tmp_path):
    files, _ = _projeto(tmp_path)
    a = _apk_de("jogo.apk", tmp_path / "build-a", pacote="com.a")
    b = _apk_de("jogo.apk", tmp_path / "build-b", pacote="com.b")
    b.write_bytes(b.read_bytes() + b"x")
    jogo.guardar(a, files)
    jogo.guardar(b, files)

    with pytest.raises(jogo.JogoError) as erro:
        jogo.arquivo(files, "jogo.apk")
    assert "existe em 2 pastas" in str(erro.value)
    assert "jogo/" in str(erro.value) and "jogo-1/" in str(erro.value)


def test_pasta_com_dois_apks_pede_o_nome(tmp_path):
    files, jogos = _projeto(tmp_path)
    pasta = jogos / "misturada"
    pasta.mkdir()
    _apk_de("um.apk", pasta)
    _apk_de("dois.apk", pasta)
    with pytest.raises(jogo.JogoError) as erro:
        jogo.arquivo(files, "misturada")
    assert "tem 2 APKs" in str(erro.value)


def test_listar_mostra_as_partes_e_quem_ja_tem_analise(tmp_path):
    files, jogos = _projeto(tmp_path)
    jogo.guardar(_apk_de("um.apk", tmp_path / "entrada"), files)
    jogo.guardar(_apk_de("dois.apk", tmp_path / "entrada"), files)
    # APK antigo, solto na raiz (formato da 0.91.38)
    _apk_de("antigo.apk", jogos)

    lista = jogo.listar(files)
    assert lista["quantidade"] == 3
    assert len(lista["partes"]) == 2
    assert {item["nome"] for item in lista["partes"]} == {"um", "dois"}
    assert all(item["analisado"] for item in lista["partes"])
    antigo = [item for item in lista["jogos"] if item["nome"] == "antigo.apk"][0]
    assert antigo["parte"] == ""
    assert antigo["analisado"] is False


def test_o_apk_solto_da_versao_anterior_continua_sendo_analisado(tmp_path):
    files, jogos = _projeto(tmp_path)
    solto = _apk_de("antigo.apk", jogos)
    caminho = jogo.arquivo(files, "antigo.apk")
    assert caminho == solto
    relatorio = jogo.relatar(caminho)
    assert relatorio["pacote"] == "com.exemplo.jogo"


def test_o_texto_diz_em_qual_pasta_a_analise_ficou(tmp_path):
    files, _ = _projeto(tmp_path)
    guardado = jogo.guardar(_apk_de("meu-jogo.apk", tmp_path / "entrada"), files)
    texto = guardado["relatorio"]["texto"]
    assert "Guardado em jogos/meu-jogo/" in texto
    assert "analise.txt" in texto and "analise.json" in texto


def test_a_rota_de_upload_guarda_cada_apk_na_parte_dele(cliente):
    base, root = cliente
    dados_um = _apk(Path("/tmp") / "teste-1.apk", manifest=manifesto(pacote="com.um"))
    dados_dois = _apk(Path("/tmp") / "teste-2.apk", manifest=manifesto(pacote="com.dois"))

    resposta_um = base.post(
        "/api/jogo/upload",
        files={"upload": ("teste-1.apk", dados_um.read_bytes())},
        data={"confirmed": "true"},
    )
    resposta_dois = base.post(
        "/api/jogo/upload",
        files={"upload": ("teste-2.apk", dados_dois.read_bytes())},
        data={"confirmed": "true"},
    )
    assert resposta_um.status_code == 200, resposta_um.text
    assert resposta_dois.status_code == 200, resposta_dois.text

    assert (root / "jogos" / "teste-1" / "teste-1.apk").is_file()
    assert (root / "jogos" / "teste-2" / "teste-2.apk").is_file()
    assert (root / "jogos" / "teste-1" / "analise.txt").is_file()
    assert (root / "jogos" / "teste-2" / "analise.txt").is_file()

    lista = base.get("/api/jogo/arquivos").json()["result"]
    assert {item["parte"] for item in lista["jogos"]} == {"teste-1", "teste-2"}
    assert len(lista["partes"]) == 2


def test_a_lista_do_console_nao_troca_o_ponto_do_nome_por_virgula(monkeypatch, capsys, tmp_path):
    """Defeito visto rodando de verdade: o `--lista` imprimia
    “build-teste-1,apk”, porque a vírgula de decimal era aplicada à linha toda."""
    import importlib.util as importlib_util

    raiz = Path(__file__).resolve().parents[2]
    spec = importlib_util.spec_from_file_location("analisar_jogo_cli", raiz / "analisar-jogo.py")
    cli = importlib_util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(cli)

    files, _ = _projeto(tmp_path)
    jogo.guardar(_apk_de("build-teste-1.apk", tmp_path / "entrada"), files)
    monkeypatch.setattr(cli, "_pasta_de_jogos", lambda: files / "jogos")

    assert cli.main(["--lista"]) == 0
    saida = capsys.readouterr().out
    assert "build-teste-1.apk" in saida
    assert "build-teste-1,apk" not in saida
    assert "build-teste-1/" in saida
    assert "analisado" in saida


def test_o_relatorio_tem_o_formato_que_a_tela_consome(tmp_path):
    """Contrato da aba “Meu jogo” (0.91.42).

    O `tsc` pegou três campos que o tipo do front dizia errado: `maiores`
    vinha com `mb` (não `bytes`), `areas` era objeto nome→bytes (não lista) e
    `permissoes` era lista de strings (não de objetos). O teste prende o
    formato, para o front não quebrar calado numa mudança do servidor.
    """
    arquivo = _apk_de("tela.apk", tmp_path / "entrada")
    relatorio = jogo.relatar(arquivo)

    assert isinstance(relatorio["permissoes"], list)
    assert all(isinstance(item, str) for item in relatorio["permissoes"])

    assert isinstance(relatorio["areas"], dict)
    assert all(isinstance(item, int) for item in relatorio["areas"].values())

    assert relatorio["maiores"], "o relatório precisa dos maiores arquivos"
    for item in relatorio["maiores"]:
        assert set(item) == {"nome", "mb"}, item
        assert isinstance(item["mb"], (int, float))

    assert set(relatorio["assinatura"]) == {"v1", "v2v3", "manifestoMf"}
    for achado in relatorio["achados"]:
        assert set(achado) >= {"severidade", "titulo", "o_que_e", "por_que_importa", "como_melhorar", "onde"}
        assert achado["severidade"] in {"critico", "atencao", "info"}


def test_o_upload_de_apk_nao_e_cortado_pelo_limite_de_corpo(cliente):
    """Defeito real da 0.91.41, achado ao subir a aba “Meu jogo”.

    A rota dizia aceitar 600 MB, mas o middleware de corpo só liberava
    `MAX_UPLOAD_BODY_BYTES` (~26 MB) para `/api/files` e `/api/reverse` — e
    `MAX_BODY_BYTES` (2 MB) para todo o resto, incluindo `/api/jogo/upload`.
    Na prática, **qualquer APK de verdade** voltava `413` antes de chegar na
    rota: o `.bat` funcionava (não passa por HTTP) e a tela não.
    """
    base, root = cliente
    # 3 MB passa do limite global de 2 MB e é bem menor que um APK real
    grande = _apk(Path("/tmp") / "grande.apk", manifest=manifesto())
    with zipfile.ZipFile(grande, "a") as pacote:
        pacote.writestr("assets/peso.bin", b"\0" * (3 * 1024 * 1024))
    assert grande.stat().st_size > 2_000_000

    resposta = base.post(
        "/api/jogo/upload",
        files={"upload": ("grande.apk", grande.read_bytes())},
        data={"confirmed": "true"},
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["result"]["parte"] == "grande"
    assert (root / "jogos" / "grande" / "grande.apk").is_file()


def test_o_limite_da_rota_de_jogo_e_o_do_jogo_e_nao_o_documento(cliente):
    """O teto do APK é 600 MB; o de documento, outro. O middleware tem de usar o
    do jogo — e continuar recusando o que passa dele."""
    assert jogo.MAXIMO_BYTES > 25_000_000
    assert jogo.MAXIMO_BYTES == 600_000_000
