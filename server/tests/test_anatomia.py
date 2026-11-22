"""Testes da anatomia: ler o aparelho sem mudar nada nele.

O pedido (23/11, conversa colada): *“conectar um aparelho no USB e fazer uma
varredura… não para modificar, mas para entender todos os componentes e
arquivos, igual anatomia humana”* — e a TV TCL Roku pela rede.

O que estes testes fixam, e por quê:

- **a leitura local não inventa** — sem `/proc` sintético a resposta é a mesma
  do sistema; com CPU, memória e térmica de mentira, os números são os do
  arquivo. Quando não há sensor, a resposta é “não exposta” com motivo, nunca um
  valor de enfeite;
- **o Android só recebe leitura** — a lista de comandos do teste é conferida
  linha a linha; `install`, `push`, `pull`, `reboot`, `su` e `pm uninstall` não
  podem aparecer. Se alguém acrescentar um comando de efeito no futuro, este
  teste cai antes do dono;
- **o Android desligado explica o que ligar** — a frase cita a variável e o
  arquivo, em vez de “acesso negado”;
- **a Roku é lida por GET** — nada de `POST /keypress`, que mudaria a TV;
- **IP público, laço local e link-local são recusados** — a mesma linha do
  resto do projeto: a API não vira proxy para a internet.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import anatomia
from server.app import create_app
from server.skill_registry import build_registry


# ---------------------------------------------------------------------------
# Ajuda
# ---------------------------------------------------------------------------

def _proc_sintetico(base: Path) -> Path:
    proc = base / "proc"
    proc.mkdir(parents=True, exist_ok=True)
    (proc / "cpuinfo").write_text(
        "processor\t: 0\nmodel name\t: Snapdragon 8 Gen 2\n\n"
        "processor\t: 1\nmodel name\t: Snapdragon 8 Gen 2\n",
        encoding="utf-8",
    )
    (proc / "meminfo").write_text(
        "MemTotal:       16000000 kB\n"
        "MemFree:         2000000 kB\n"
        "MemAvailable:    8000000 kB\n"
        "SwapTotal:             0 kB\n",
        encoding="utf-8",
    )
    return proc


def _sys_com_termica(base: Path) -> Path:
    sys_ = base / "sys"
    zona = sys_ / "class" / "thermal" / "thermal_zone0"
    zona.mkdir(parents=True)
    (zona / "type").write_text("cpu-thermal\n", encoding="utf-8")
    (zona / "temp").write_text("45000\n", encoding="utf-8")
    return sys_


def _rodar_falso(saidas: dict[str, str], registro: list[list[str]] | None = None):
    """Devolve saída por comando e guarda cada chamada para a auditoria."""

    def rodar(argumentos: list[str]):
        if registro is not None:
            registro.append(list(argumentos))
        chave = " ".join(argumentos)
        for trecho, saida in saidas.items():
            if trecho in chave:
                return 0, saida, ""
        return 0, "", ""

    return rodar


def _aparelho_autorizado(serial: str = "ABC123") -> str:
    return f"List of devices attached\n{serial}          device product:test model:SM_A346B device:a34 transport_id:1\n"


GETPROP = (
    "[ro.product.manufacturer]: [samsung]\n"
    "[ro.product.brand]: [samsung]\n"
    "[ro.product.model]: [SM-A346B]\n"
    "[ro.product.device]: [a34x]\n"
    "[ro.build.version.release]: [14]\n"
    "[ro.build.version.sdk]: [34]\n"
    "[ro.build.version.security_patch]: [2025-09-01]\n"
    "[ro.soc.manufacturer]: [QTI]\n"
    "[ro.soc.model]: [SM6375]\n"
    "[ro.board.platform]: [holi]\n"
    "[ro.hardware]: [qcom]\n"
    "[ro.product.cpu.abi]: [arm64-v8a]\n"
    "[ro.product.cpu.abilist]: [arm64-v8a,armeabi-v7a,armeabi]\n"
    "[ro.bootloader]: [A346BXXS9CXK1]\n"
    "[ro.build.type]: [user]\n"
    "[ro.debuggable]: [0]\n"
    "[ro.secure]: [1]\n"
)

BATERIA = (
    "Current Battery Service state:\n"
    "  AC powered: false\n"
    "  USB powered: true\n"
    "  status: 2\n"
    "  health: 2\n"
    "  level: 87\n"
    "  voltage: 4321\n"
    "  temperature: 312\n"
)

MEMINFO_ANDROID = (
    "MemTotal:        7643124 kB\n"
    "MemFree:          612004 kB\n"
    "MemAvailable:    2903340 kB\n"
    "SwapTotal:       2097148 kB\n"
)

CPUINFO_ANDROID = (
    "processor\t: 0\n"
    "BogoMIPS\t: 38.40\n"
    "Features\t: fp asimd evtstrm aes\n"
    "Hardware\t: Qualcomm Technologies, Inc SM6375\n"
)

DF_ANDROID = (
    "Filesystem      1K-blocks     Used Available Use% Mounted on\n"
    "/dev/block/dm-8  114496460 44231220  70265240  39% /data\n"
    "tmpfs             3811560      388   3811172   1% /dev\n"
)

PARTICOES_ANDROID = (
    "major minor  #blocks  name\n\n"
    " 254        0   31131648 mmcblk0\n"
    " 254        1       8192 mmcblk0p1\n"
    " 254       32  114257920 mmcblk0p32\n"
)

TERMICO_ANDROID = "cpu:39000\nbattery:31000\ngpu:-127000\n"

APPS_TERCEIROS = (
    "package:com.google.android.youtube\n"
    "package:app.revanced.android.gms\n"
    "package:com.whatsapp\n"
)

APPS_TODOS = APPS_TERCEIROS + "package:android\npackage:com.android.systemui\n"


def _rodar_android(registro: list[list[str]] | None = None):
    return _rodar_falso(
        {
            "devices": _aparelho_autorizado(),
            "getprop": GETPROP,
            "dumpsys battery": BATERIA,
            "/proc/meminfo": MEMINFO_ANDROID,
            "/proc/cpuinfo": CPUINFO_ANDROID,
            "df -k": DF_ANDROID,
            "/proc/partitions": PARTICOES_ANDROID,
            "thermal": TERMICO_ANDROID,
            "pm list packages -3": APPS_TERCEIROS,
            "pm list packages": APPS_TODOS,
        },
        registro,
    )


def _ligar_android(monkeypatch, *, adb: str = "/fake/adb") -> None:
    monkeypatch.setenv(anatomia.AMBIENTE_ANDROID, "1")
    monkeypatch.setattr(anatomia.celular, "ferramentas", lambda: {"ligado": True, "adb": adb, "scrcpy": ""})


def _ligar_rede(monkeypatch) -> None:
    monkeypatch.setenv(anatomia.AMBIENTE_REDE, "1")


# ---------------------------------------------------------------------------
# Local
# ---------------------------------------------------------------------------

def test_local_le_cpu_e_memoria_dos_arquivos_do_sistema(tmp_path: Path):
    dados = anatomia.ler_local(
        raiz_proc=_proc_sintetico(tmp_path),
        raiz_sys=tmp_path / "sys_vazio",
        rodar=_rodar_falso({}),
    )
    valores = {item["rotulo"]: item["valor"] for secao in dados["secoes"] for item in secao["itens"]}
    assert valores["Modelo da CPU"] == "Snapdragon 8 Gen 2"
    assert valores["Memória total"].endswith("GB")
    assert "15" in valores["Memória total"].replace(",", ".")  # 16.000.000 kB ≈ 15,3 GB


def test_local_le_temperatura_do_thermal_zone(tmp_path: Path):
    dados = anatomia.ler_local(
        raiz_proc=_proc_sintetico(tmp_path),
        raiz_sys=_sys_com_termica(tmp_path),
        rodar=_rodar_falso({}),
    )
    termica = next(s for s in dados["secoes"] if s["id"] == "temperatura")
    assert termica["itens"] == [{"rotulo": "cpu-thermal", "valor": "45,0 °C"}]
    assert dados["fontes"]["temperatura"] == "/sys/class/thermal"


def test_local_diz_que_a_temperatura_nao_esta_exposta(tmp_path: Path):
    dados = anatomia.ler_local(
        raiz_proc=_proc_sintetico(tmp_path),
        raiz_sys=tmp_path / "vazio",
        rodar=_rodar_falso({}),
    )
    termica = next(s for s in dados["secoes"] if s["id"] == "temperatura")
    assert termica["itens"][0]["rotulo"] == "Situação"
    assert termica["itens"][0]["valor"] == "não exposta"
    assert any("Temperatura" in motivo for motivo in dados["limitacoes"])


def test_local_le_a_gpu_pelo_nvidia_smi(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(anatomia.shutil, "which", lambda nome: "/usr/bin/nvidia-smi" if nome == "nvidia-smi" else None)
    dados = anatomia.ler_local(
        raiz_proc=_proc_sintetico(tmp_path),
        raiz_sys=tmp_path / "vazio",
        rodar=_rodar_falso({"nvidia-smi": "NVIDIA GeForce RTX 3060, 12288 MiB, 41\n"}),
    )
    video = next(s for s in dados["secoes"] if s["id"] == "gpu")
    assert video["itens"][0]["valor"].startswith("NVIDIA GeForce RTX 3060")
    assert dados["fontes"]["gpu"] == "nvidia-smi"


def test_local_nao_promete_o_que_nao_le(tmp_path: Path):
    dados = anatomia.ler_local(
        raiz_proc=_proc_sintetico(tmp_path),
        raiz_sys=tmp_path / "vazio",
        rodar=_rodar_falso({}),
    )
    assert any("Não lê a memória de outros aplicativos" in frase for frase in dados["nao_faz"])
    assert dados["alvo"] == "local"
    assert dados["lido_em"]


# ---------------------------------------------------------------------------
# Android
# ---------------------------------------------------------------------------

def test_android_desligado_explica_o_que_ligar(monkeypatch):
    monkeypatch.delenv(anatomia.AMBIENTE_ANDROID, raising=False)
    monkeypatch.setattr(anatomia.celular, "ligado", lambda: False)
    with pytest.raises(anatomia.AnatomiaError) as erro:
        anatomia.ler_android()
    assert "JARVIS_HOST_CELULAR=1" in str(erro.value)
    assert "iniciar-jarvis.bat" in str(erro.value)


def test_android_le_identidade_bateria_memoria_e_apps(monkeypatch):
    _ligar_android(monkeypatch)
    registro: list[list[str]] = []
    dados = anatomia.ler_android(rodar=_rodar_android(registro))
    valores = {
        (secao["id"], item["rotulo"]): item["valor"] for secao in dados["secoes"] for item in secao["itens"]
    }
    assert valores[("identidade", "Modelo")] == "SM-A346B"
    assert valores[("identidade", "SoC")] == "SM6375"
    assert valores[("identidade", "ABIs")] == "arm64-v8a,armeabi-v7a,armeabi"
    assert valores[("bateria", "Carga")] == "87%"
    assert valores[("bateria", "Temperatura da bateria")] == "31,2 °C"
    assert valores[("bateria", "Saúde")] == "boa"
    assert valores[("memoria", "Memória total")].endswith("GB")
    assert valores[("termico", "cpu")] == "39,0 °C"
    assert valores[("termico", "gpu")] == "-127,0 °C"  # o valor vem do aparelho, sem maquiagem
    assert valores[("discos", "/data")].startswith("67,0 GB livres")
    assert valores[("apps", "Fora da loja (terceiros)")] == "3"
    assert "com.google.android.youtube" in valores[("apps", "Amostra")]
    assert dados["titulo"] == "SM-A346B · Android 14"


def test_android_so_recebe_comandos_de_leitura(monkeypatch):
    _ligar_android(monkeypatch)
    registro: list[list[str]] = []
    anatomia.ler_android(rodar=_rodar_android(registro))
    assert registro, "nenhum comando rodou"
    proibidos = ("install", "uninstall", "push", "pull", "reboot", "root", "su", "rm", "format", "keyevent")
    for comando in registro:
        # O primeiro argumento é o adb e o segundo o serial; o resto é o que importa.
        corpo = " ".join(comando[2:])
        for palavra in proibidos:
            assert palavra not in corpo.split(), f"comando de efeito na lista de leitura: {corpo}"
        if "shell" in comando:
            assert comando[1] == "-s", comando


def test_android_nao_autorizado_diz_o_que_fazer_na_tela(monkeypatch):
    _ligar_android(monkeypatch)
    rodar = _rodar_falso(
        {
            "devices": "List of devices attached\nABC123          unauthorized transport_id:1\n",
        }
    )
    with pytest.raises(anatomia.AnatomiaError) as erro:
        anatomia.ler_android(rodar=rodar)
    assert "Permitir" in str(erro.value)
    assert "depuração usb" in str(erro.value).lower()


def test_android_sem_cabo_diz_que_o_cabo_pode_ser_so_carga(monkeypatch):
    _ligar_android(monkeypatch)
    rodar = _rodar_falso({"devices": "List of devices attached\n"})
    with pytest.raises(anatomia.AnatomiaError) as erro:
        anatomia.ler_android(rodar=rodar)
    assert "cabo" in str(erro.value)
    assert "carga" in str(erro.value)


def test_android_sem_adb_manda_preparar_pela_maquina(monkeypatch):
    monkeypatch.setenv(anatomia.AMBIENTE_ANDROID, "1")
    monkeypatch.setattr(anatomia.celular, "ferramentas", lambda: {"ligado": True, "adb": "", "scrcpy": ""})
    with pytest.raises(anatomia.AnatomiaError) as erro:
        anatomia.ler_android(rodar=_rodar_falso({}))
    assert "adb" in str(erro.value) and "Máquina" in str(erro.value)


def test_android_sem_termica_explica_que_e_o_sistema(monkeypatch):
    _ligar_android(monkeypatch)
    rodar = _rodar_falso(
        {
            "devices": _aparelho_autorizado(),
            "getprop": GETPROP,
            "thermal": "",  # permission denied silencioso, como em muitos aparelhos
        }
    )
    dados = anatomia.ler_android(rodar=rodar)
    assert not any(s["id"] == "termico" for s in dados["secoes"])
    # 0.94.0 — o texto da limitação térmica passou a ser o mesmo do
    # `diagnostico_celular`, para a dedup conseguir juntar as duas.
    assert any("/sys/class/thermal" in lim for lim in dados["limitacoes"])


# ---------------------------------------------------------------------------
# Roku
# ---------------------------------------------------------------------------

def test_roku_desligado_explica_o_que_ligar(monkeypatch):
    monkeypatch.delenv(anatomia.AMBIENTE_REDE, raising=False)
    with pytest.raises(anatomia.AnatomiaError) as erro:
        anatomia.ler_roku("192.168.0.23")
    assert "JARVIS_HOST_REDE=1" in str(erro.value)


def test_roku_recusa_ip_que_nao_e_da_rede(monkeypatch):
    _ligar_rede(monkeypatch)
    for endereco in ("8.8.8.8", "127.0.0.1", "169.254.10.10", "nao-e-ip"):
        with pytest.raises(anatomia.AnatomiaError):
            anatomia.ler_roku(endereco, buscar=lambda url: "")


DEVICE_INFO = """<?xml version="1.0" encoding="UTF-8" ?>
<device-info>
  <friendly-device-name>TCL Roku TV</friendly-device-name>
  <model-name>TCL 32S305</model-name>
  <model-number>32S305</model-number>
  <vendor-name>TCL</vendor-name>
  <software-version>11.5.0</software-version>
  <software-build>4313</software-build>
  <serial-number>X00900ABCDEF</serial-number>
  <wifi-mac>aa:bb:cc:dd:ee:ff</wifi-mac>
  <display-type>1080p</display-type>
  <network-type>wifi</network-type>
  <uptime>93784</uptime>
  <power-mode>PowerOn</power-mode>
</device-info>
"""

APPS_ROKU = """<?xml version="1.0" encoding="UTF-8" ?>
<apps>
  <app id="12" type="appl" version="6.10.0">Netflix</app>
  <app id="13" type="appl" version="9.2">Prime Video</app>
  <app id="tvinput.hdmi1" type="tvin" version="1.0">HDMI 1</app>
</apps>
"""

ATIVO_ROKU = """<?xml version="1.0" encoding="UTF-8" ?>
<active-app><app id="12" type="appl" version="6.10.0">Netflix</app></active-app>
"""


def test_roku_le_o_device_info_e_os_canais(monkeypatch):
    _ligar_rede(monkeypatch)
    urls: list[str] = []

    def buscar(url: str) -> str:
        urls.append(url)
        if url.endswith("/query/device-info"):
            return DEVICE_INFO
        if url.endswith("/query/apps"):
            return APPS_ROKU
        if url.endswith("/query/active-app"):
            return ATIVO_ROKU
        raise AssertionError(f"URL inesperada: {url}")

    dados = anatomia.ler_roku("192.168.0.23", buscar=buscar, portas=lambda ip, porta: porta == 8060)
    valores = {item["rotulo"]: item["valor"] for secao in dados["secoes"] for item in secao["itens"]}
    assert dados["titulo"] == "TCL Roku TV"
    assert valores["Modelo"] == "TCL 32S305"
    assert valores["Roku OS"] == "11.5.0"
    assert valores["Série"] == "X00900ABCDEF"
    assert valores["Ligada há"] == "1d 2h 3min"
    assert valores["Canal ativo"] == "Netflix"
    assert "Netflix" in valores["3 canais"]
    assert todos_get(urls), "a leitura não pode usar nada além de GET"


def todos_get(urls: list[str]) -> bool:
    return all(url.startswith("http://192.168.0.23:8060/query/") for url in urls)


def test_roku_recusa_aparelho_que_nao_e_roku(monkeypatch):
    _ligar_rede(monkeypatch)
    with pytest.raises(anatomia.AnatomiaError) as erro:
        anatomia.ler_roku("192.168.0.23", buscar=lambda url: "<html><body>roteador</body></html>")
    assert "device-info" in str(erro.value)


def test_roku_avisa_que_nao_aperta_botao(monkeypatch):
    _ligar_rede(monkeypatch)

    def buscar(url: str) -> str:
        if url.endswith("device-info"):
            return DEVICE_INFO
        return "<apps></apps>" if url.endswith("/query/apps") else "<active-app></active-app>"

    dados = anatomia.ler_roku("192.168.0.23", buscar=buscar, portas=lambda ip, porta: False)
    assert any("aperta botão" in lim.lower() for lim in dados["limitacoes"])
    assert any("temperatura" in lim for lim in dados["limitacoes"])


# ---------------------------------------------------------------------------
# Fontes e API
# ---------------------------------------------------------------------------

def test_fontes_diz_por_que_cada_alvo_esta_desligado(monkeypatch, tmp_path):
    monkeypatch.delenv(anatomia.AMBIENTE_ANDROID, raising=False)
    monkeypatch.delenv(anatomia.AMBIENTE_REDE, raising=False)
    monkeypatch.setattr(anatomia.celular, "ferramentas", lambda: {"ligado": False, "adb": "", "scrcpy": ""})
    alvos = {alvo["id"]: alvo for alvo in anatomia.fontes(rodar=_rodar_falso({}))["alvos"]}
    assert alvos["local"]["disponivel"] is True
    assert alvos["android"]["disponivel"] is False
    assert "JARVIS_HOST_CELULAR=1" in alvos["android"]["motivo"]
    assert "JARVIS_HOST_REDE=1" in alvos["roku"]["motivo"]


def _cliente(tmp_path: Path) -> TestClient:
    return TestClient(create_app(registry=build_registry(tmp_path / "files")))


def test_api_mostra_os_alvos(tmp_path: Path, monkeypatch):
    monkeypatch.delenv(anatomia.AMBIENTE_REDE, raising=False)
    monkeypatch.setattr(anatomia.celular, "ligado", lambda: False)
    resposta = _cliente(tmp_path).get("/api/anatomia/fontes")
    assert resposta.status_code == 200, resposta.text
    alvos = resposta.json()["result"]["alvos"]
    assert {alvo["id"] for alvo in alvos} == {"local", "android", "roku"}


def test_api_le_o_computador_sem_pedir_nada_alem(tmp_path: Path):
    resposta = _cliente(tmp_path).get("/api/anatomia/local")
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()["result"]
    assert dados["alvo"] == "local"
    assert dados["secoes"]


def test_api_recusa_alvo_desconhecido(tmp_path: Path):
    resposta = _cliente(tmp_path).get("/api/anatomia/maquina-do-vizinho")
    assert resposta.status_code == 404


# ---------------------------------------------------------------------------
# 0.92.6 — o título que saía sem o modelo
#
# No relatório real do dono (SM-A346MU, Android 16) o cabeçalho era só
# “Android 16”: o `getprop` inteiro tem centenas de linhas e a do modelo caía
# depois do corte de 60 KB. O `adb` já sabe pedir uma propriedade só.
# ---------------------------------------------------------------------------

def test_o_titulo_tem_o_modelo_mesmo_com_getprop_cortado(monkeypatch):
    _ligar_android(monkeypatch)
    grande = "\n".join(f"[ro.persist.prop.{i}]: [{'x' * 60}]" for i in range(1200))
    pedidos: list[list[str]] = []

    def rodar(argumentos: list[str]):
        pedidos.append(list(argumentos))
        chave = " ".join(argumentos)
        if "devices" in chave:
            return 0, _aparelho_autorizado(), ""
        if chave.endswith("shell getprop"):
            # O modelo fica no fim de um despejo maior que o corte — some.
            return 0, grande + "\n[ro.product.model]: [SM-A346MU]\n", ""
        if chave.endswith("shell getprop ro.product.model"):
            return 0, "SM-A346MU\n", ""
        if chave.endswith("shell getprop ro.build.version.release"):
            return 0, "16\n", ""
        return 0, "", ""

    dados = anatomia.ler_android(rodar=rodar)
    assert "SM-A346MU" in dados["titulo"], dados["titulo"]
    assert "Android 16" in dados["titulo"]
    assert any("getprop ro.product.model" in " ".join(p) for p in pedidos)


def test_a_propriedade_nao_e_pedida_de_novo_quando_ja_vem_no_getprop(monkeypatch):
    """Um comando a mais só quando falta — com o `getprop` completo, nada extra."""
    _ligar_android(monkeypatch)
    pedidos: list[list[str]] = []
    rodar = _rodar_falso(
        {
            "devices": _aparelho_autorizado(),
            "getprop ro.": "",  # qualquer `getprop <chave>` devolve vazio
            "getprop": GETPROP,
            "dumpsys battery": BATERIA,
            "/proc/meminfo": MEMINFO_ANDROID,
            "df -k": DF_ANDROID,
            "pm list packages": APPS_TODOS,
        },
        pedidos,
    )
    dados = anatomia.ler_android(rodar=rodar)
    assert "SM-A346B" in dados["titulo"]
    # `adb shell getprop` (sem chave) é a leitura normal; o que não pode haver é
    # a pergunta por chave específica quando o valor já estava na leitura.
    extras = [p for p in pedidos if p[-2:] == ["getprop"] and len(p) > 4]
    assert extras == [], f"pediu propriedade que já tinha: {extras}"
