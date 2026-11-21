"""Testes da varredura completa do celular (0.92.5).

O pedido: *“ta ja conectei o cll no pc como faço o jarvis rodar por todo o meu
celular”*. Até aqui isso exigia saber que existem três abas. A varredura junta
tudo num comando.

O que estes testes travam:

- **só leitura** — a lista de comandos é conferida palavra por palavra; nenhum
  `rm`, `pull`, `push`, `install`, `reboot` ou `su`;
- **o mapa é honesto** — a seção “o que não dá sem root” existe sempre, com os
  quatro itens, e a varredura **não** promete ler `/data/data`;
- **falha parcial não derruba o resto** — um comando que não responde vira linha
  em “leituras que não responderam”, e o relatório sai;
- **o parser do `ls` do Android** — nome com espaço, atalho, pasta e arquivo;
- **o texto do console** cabe e termina dizendo o que não faz.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import varredura as vd
from server.app import create_app
from server.skill_registry import build_registry


# ---------------------------------------------------------------------------
# Saídas de exemplo
# ---------------------------------------------------------------------------

LS_RAIZ = """total 4096
drwxr-xr-x  20 root   root          4096 2026-10-23 10:00 .
drwxr-xr-x   3 root   root          4096 2026-10-23 10:00 ..
drwxr-xr-x   2 root   root          4096 2026-10-23 10:00 acct
lrw-r--r--   1 root   root            11 2026-10-23 10:00 bin -> /system/bin
drwxrwx--x   2 system system        4096 2026-10-23 10:00 data
drwxr-xr-x  12 root   root          4096 2026-10-23 10:00 system
drwxr-xr-x   4 root   root          4096 2026-10-23 10:00 vendor
"""

LS_SD = """total 128
drwxrwx--x  30 root   sdcard_rw 4096 2026-10-23 10:00 .
drwx--x--x   3 root   sdcard_rw 4096 2026-10-23 10:00 ..
drwxrwx--x   4 u0_a12 ext_data_rw 4096 2026-10-23 10:00 Android
drwxrwx--x   6 u0_a12 ext_data_rw 4096 2026-10-23 10:00 DCIM
drwxrwx--x   3 u0_a12 ext_data_rw 4096 2026-10-23 10:00 Download
-rw-rw----   1 u0_a12 ext_data_rw 123456789 2026-10-23 10:00 video grande.mp4
"""

PARTICOES = """major minor  #blocks  name

 254        0   31131648 mmcblk0
 254        1       8192 mmcblk0p1
 254       32  114257920 mmcblk0p32
 255        0     524288 dm-0
"""

MEMINFO = """Applications Memory Usage (in Kilobytes):
Total RAM: 5,840,000K (status normal)
 Free RAM: 1,200,000K
 Used RAM: 3,900,000K
 Lost RAM: 740,000K
"""

PS = """  PID   RSS NAME
  412 900120 com.instagram.android
  511 480000 com.whatsapp
  900 120000 com.android.systemui
"""

APPS_SISTEMA = """package:android
package:com.android.systemui
package:com.samsung.android.app.camera
"""


def saidas() -> dict[str, str]:
    return {
        "ls -la /": LS_RAIZ,
        "ls -la /storage/emulated/0": LS_SD,
        "ls -la /sdcard": LS_SD,
        "ls -la /system": LS_RAIZ,
        "ls -la /vendor": LS_RAIZ,
        "ls -la /data/app": LS_SD,
        "df -h": "",
        "cat /proc/partitions": PARTICOES,
        "dumpsys meminfo": MEMINFO,
        "dumpsys cpuinfo": "",
        "ps -A -o PID,RSS,NAME": PS,
        "pm list packages -s": APPS_SISTEMA,
    }


def medido(**trocas: str) -> dict:
    base = saidas()
    base.update(trocas)
    return {"serial": "ABC123", "saidas": base, "falhas": []}


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def test_le_o_ls_do_android_com_nome_que_tem_espaco():
    itens = vd.ler_pastas(LS_SD)
    nomes = [i["nome"] for i in itens]
    assert "video grande.mp4" in nomes
    video = next(i for i in itens if i["nome"] == "video grande.mp4")
    assert video["tipo"] == "arquivo"
    assert video["tamanho"] == "123,5 MB"


def test_le_atalho_sem_confundir_com_arquivo():
    itens = vd.ler_pastas(LS_RAIZ)
    binario = next(i for i in itens if i["nome"] == "bin")
    assert binario["tipo"] == "atalho para /system/bin"


def test_pasta_e_pasta_sem_tamanho():
    itens = vd.ler_pastas(LS_RAIZ)
    sistema = next(i for i in itens if i["nome"] == "system")
    assert sistema["tipo"] == "pasta"
    assert sistema["tamanho"] == ""


def test_le_as_particoes_com_tamanho_em_gb():
    partes = {p["nome"]: p["tamanho"] for p in vd.ler_particoes(PARTICOES)}
    assert partes["mmcblk0p32"] == "109 GB"
    assert partes["mmcblk0p1"] == "8 MB"


def test_le_o_resumo_de_memoria_do_dumpsys():
    memoria = vd.ler_memoria_detalhada(MEMINFO)
    assert memoria["Livre"] == "1,200,000K"
    assert memoria["RAM total"].startswith("5,840,000K")


def test_processos_saem_do_maior_para_o_menor():
    processos = vd.ler_processos(PS)
    assert processos[0]["nome"] == "com.instagram.android"
    assert processos[0]["mb"] == "879 MB"


# ---------------------------------------------------------------------------
# A lista é de leitura
# ---------------------------------------------------------------------------

def test_nenhum_comando_altera_o_aparelho():
    for comando in vd.COMANDOS:
        texto = " ".join(comando)
        for proibido in ("install", "uninstall", "push", "pull", "rm ", " mv ", " cp ",
                         "reboot", "wipe", "format", "keyevent", "input", "su"):
            assert proibido not in f" {texto} ", f"comando de efeito: {texto}"


def test_todo_comando_carrega_o_serial(monkeypatch):
    registro: list[list[str]] = []

    def rodar(argumentos: list[str]):
        registro.append(list(argumentos))
        if argumentos[1:3] == ["devices", "-l"]:
            return 0, "List of devices attached\nABC123          device product:a34x model:SM_A346B\n", ""
        corpo = " ".join(argumentos[3:])
        return 0, next((v for k, v in saidas().items() if corpo.startswith(k)), ""), ""

    monkeypatch.setenv(vd.AMBIENTE, "1")
    monkeypatch.setattr("server.celular.ferramentas", lambda: {"ligado": True, "adb": "/fake/adb", "scrcpy": ""})
    dados = vd.coletar(rodar=rodar)
    assert dados["serial"] == "ABC123"
    for comando in registro:
        if "shell" in comando:
            assert comando[:3] == ["/fake/adb", "-s", "ABC123"], comando


# ---------------------------------------------------------------------------
# Junção
# ---------------------------------------------------------------------------

def test_a_varredura_tem_as_secoes_do_aparelho_inteiro():
    relatorio = vd.montar(medido())
    ids = {s["id"] for s in relatorio["secoes"]}
    assert {"pastas", "particoes", "memoria", "processos", "sistema-apps"} <= ids
    texto = " ".join(i["rotulo"] + i["valor"] for s in relatorio["secoes"] for i in s["itens"])
    assert "DCIM" in texto and "Android" in texto


def test_a_varredura_diz_o_que_nao_da_sem_root():
    relatorio = vd.montar(medido())
    texto = " ".join(relatorio["sem_root"])
    assert "/data/data" in texto
    assert "root" in texto.lower()
    assert "bootloader" in texto


def test_a_varredura_nao_promete_copiar_arquivo_nem_abrir_tela():
    relatorio = vd.montar(medido())
    texto = " ".join(relatorio["nao_faz"])
    assert "celular.puxar" in texto
    assert "scrcpy" in texto


def test_cobertura_total_quando_tudo_responde():
    relatorio = vd.montar(medido())
    assert "entregou tudo" in relatorio["veredito"]


def test_falha_parcial_nao_derruba_o_relatorio():
    incompleto = medido()
    incompleto["falhas"] = ["“ls -la /data/app”: Permission denied"]
    relatorio = vd.montar(incompleto)
    assert "Permission denied" in " ".join(relatorio["limitacoes"])
    assert relatorio["secoes"], "o relatório saiu mesmo com uma leitura faltando"
    assert "de 12 leituras" in relatorio["veredito"]


def test_varredura_desligada_explica_a_variavel(monkeypatch):
    monkeypatch.delenv(vd.AMBIENTE, raising=False)
    monkeypatch.setattr("server.celular.ligado", lambda: False)
    with pytest.raises(vd.VarreduraError) as erro:
        vd.varrer()
    assert "JARVIS_HOST_CELULAR=1" in str(erro.value)


def test_o_texto_do_console_termina_dizendo_o_que_nao_faz():
    texto = vd.em_texto(vd.montar(medido()))
    assert "O QUE NÃO DÁ SEM ROOT" in texto
    assert "O QUE ESTA VARREDURA NÃO FAZ" in texto
    assert "PARTIÇÕES" in texto


# ---------------------------------------------------------------------------
# API e skill
# ---------------------------------------------------------------------------

def _cliente(tmp_path: Path) -> TestClient:
    return TestClient(create_app(registry=build_registry(tmp_path / "files")))


def test_api_da_varredura_responde_409_sem_aparelho(tmp_path: Path, monkeypatch):
    monkeypatch.delenv(vd.AMBIENTE, raising=False)
    monkeypatch.setattr("server.celular.ligado", lambda: False)
    resposta = _cliente(tmp_path).get("/api/anatomia/android/varredura")
    assert resposta.status_code == 409
    assert "JARVIS_HOST_CELULAR" in resposta.json()["error"]["message"]


def test_api_da_varredura_devolve_o_relatorio(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(vd.AMBIENTE, "1")
    monkeypatch.setattr("server.celular.ligado", lambda: True)
    monkeypatch.setattr(vd, "coletar", lambda alvo="", rodar=None: medido())
    resposta = _cliente(tmp_path).get("/api/anatomia/android/varredura")
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()["result"]
    assert dados["alvo"] == "android"
    assert any(s["id"] == "particoes" for s in dados["secoes"])


def test_a_skill_da_varredura_existe_e_e_de_leitura():
    registro = build_registry(Path("/tmp/reg-varredura"))
    skill = registro.get("celular.varredura")
    assert skill is not None
    assert skill.side_effects is False


# ---------------------------------------------------------------------------
# 0.92.5 — “quero e preciso que o JARVIS tenha 100% de acesso”
# ---------------------------------------------------------------------------

def test_o_mapa_de_controle_diz_que_100_por_cento_nao_existe():
    relatorio = vd.controle()
    assert relatorio["degrau_maximo_jarvis"] == 2
    assert len(relatorio["degraus"]) == 5
    # O degrau de root e o de flash existem no mapa, mas NÃO são feitos.
    root = next(d for d in relatorio["degraus"] if d["degrau"] == 3)
    flash = next(d for d in relatorio["degraus"] if d["degrau"] == 4)
    falha = next(d for d in relatorio["degraus"] if d["degrau"] == 5)
    assert root["jarvis_faz"] is False
    assert flash["jarvis_faz"] is False
    assert falha["jarvis_faz"] is False
    assert "não faz root" in root["recusa"].lower() or "não** faz root" in root["recusa"].lower() or "não" in root["recusa"]


def test_o_degrau_1_diz_o_que_ganha_e_o_que_custa():
    relatorio = vd.controle()
    um = next(d for d in relatorio["degraus"] if d["degrau"] == 1)
    assert um["jarvis_faz"] is True
    assert "Permitir" in um["falta"]
    assert um["ganha"].strip() and um["custa"].strip()


def test_aparelho_comum_fica_no_degrau_0_sem_autorizacao():
    relatorio = vd.controle(aparelho={})
    assert relatorio["degrau_atual"] == 0
    assert "degrau 0" in relatorio["resumo"]


def test_aparelho_autorizado_com_debuggable_chega_ao_degrau_2(monkeypatch):
    monkeypatch.setattr("server.varredura.celular.ligado", lambda: True)
    monkeypatch.setattr(
        "server.varredura.celular.ferramentas", lambda: {"ligado": True, "adb": "/x/adb", "scrcpy": ""}
    )
    relatorio = vd.controle(aparelho={
        "ro.product.model": "SM-A346B",
        "ro.debuggable": "1",
        "ro.build.tags": "release-keys",
    })
    assert relatorio["degrau_atual"] == 2
    assert relatorio["aparelho"]["root"] is False


def test_o_mapa_avisa_que_root_nao_vem_do_jarvis():
    texto = " ".join(vd.controle()["o_que_nao_faz_e_por_que"])
    assert "root" in texto
    assert "bootloader" in texto
    assert "falha" in texto


def test_api_do_controle_responde(tmp_path: Path):
    resp = _cliente(tmp_path).get("/api/anatomia/android/controle")
    assert resp.status_code == 200
    dados = resp.json()["result"]
    assert dados["degrau_maximo_jarvis"] == 2
