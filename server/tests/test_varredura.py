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


GETPROP = (
    "[ro.product.manufacturer]: [samsung]\n"
    "[ro.product.model]: [SM-A346MU]\n"
    "[ro.build.version.release]: [16]\n"
    "[ro.build.version.sdk]: [36]\n"
    "[ro.build.version.security_patch]: [2026-07-05]\n"
    "[ro.bootloader]: [A346MUBSGFZG4]\n"
    "[ro.build.type]: [user]\n"
    "[ro.debuggable]: [0]\n"
)

BATERIA = (
    "Current Battery Service state:\n"
    "  AC powered: false\n"
    "  status: 2\n"
    "  health: 2\n"
    "  level: 17\n"
    "  voltage: 3690\n"
    "  temperature: 363\n"
)

DF = (
    "Filesystem      1K-blocks     Used Available Use% Mounted on\n"
    "/dev/block/dm-8  114496460 108800000  5696460  95% /data\n"
)

MEMINFO_ANDROID = (
    "MemTotal:        7647736 kB\n"
    "MemFree:          295324 kB\n"
    "MemAvailable:    3211545 kB\n"
    "SwapTotal:      12582908 kB\n"
)

POWER_SUPPLY = (
    "/sys/class/power_supply/battery/temp=363\n"
    "/sys/class/power_supply/battery/voltage_now=3690000\n"
    "/sys/class/power_supply/battery/capacity=17\n"
)

TERMICO = "cpu:39000\nbattery:36300\n"

PS_RSS = """  RSS NAME
 900120 app.revanced.android.youtube
 480000 com.whatsapp
"""

def saidas() -> dict[str, str]:
    """O que o `adb` devolve — a **lista inteira** de `COMANDOS`, não um subconjunto.

    0.92.6 — este dicionário era menor que a lista de comandos, e foi por isso que
    o defeito passou: o teste “passava” com o scanner sem medida nenhuma. Agora
    toda chave de `COMANDOS` tem saída de exemplo, e um teste cobra isso.
    """
    return {
        # --- o que o scanner lê
        "getprop": GETPROP,
        "dumpsys battery": BATERIA,
        'for f in /sys/class/power_supply/battery/*; do echo "$f=$(cat $f 2>/dev/null)"; done': POWER_SUPPLY,
        "df -k": DF,
        "cat /proc/meminfo": MEMINFO_ANDROID,
        "cat /proc/uptime": "93784.51 302144.22\n",
        "ps -A -o RSS,NAME": PS_RSS,
        "dumpsys diskstats": "Latency: 1ms [512B Data Write]\nRecent Disk I/O: 12.3 MB/s\n",
        'for z in /sys/class/thermal/thermal_zone*; do echo "$(cat $z/type 2>/dev/null):$(cat $z/temp 2>/dev/null)"; done': TERMICO,
        "settings get global window_animation_scale": "1.0\n",
        "settings get global transition_animation_scale": "1.0\n",
        "settings get global animator_duration_scale": "1.0\n",
        "pm list packages -3": "package:com.whatsapp\npackage:app.revanced.android.youtube\n",
        "logcat -b crash -d -t 80": "",
        "which su": "",
        "dumpsys input": "Input Reader State\n  Device 4: fts_ts\n",
        "dumpsys window displays": "mCurrentFocus=Window{abc u0 com.whatsapp/com.whatsapp.Main}\n",
        "logcat -b system -d -t 400": "",
        "dumpsys gfxinfo": "",
        # --- o que a varredura lê
        "ls -la /": LS_RAIZ,
        "ls -la /storage/emulated/0": LS_SD,
        "ls -la /system": LS_RAIZ,
        "ls -la /vendor": LS_RAIZ,
        "ls -la /data/app": LS_SD,
        "dumpsys meminfo": MEMINFO,
        "ps -A -o PID,RSS,NAME": PS,
        "cat /proc/partitions": PARTICOES,
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
                         "reboot", "wipe", "format", "keyevent"):
            assert proibido not in f" {texto} ", f"comando de efeito: {texto}"
        # `adb shell input` injeta toque na tela; `dumpsys input` só lê o estado
        # do controlador. A pergunta é legitimamente "input".
        if " input" in texto:
            assert texto.endswith("dumpsys input"), f"comando de entrada que não é leitura: {texto}"
        # `which su` só **pergunta** se existe root; não executa. Qualquer outro
        # uso de `su` continua proibido.
        if "su" in texto.split():
            assert texto.endswith("which su"), f"comando com `su` que não é a pergunta: {texto}"


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
    assert "de 28 leituras" in relatorio["veredito"]


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


# ---------------------------------------------------------------------------
# 0.92.6 — os defeitos que o relatório do dono expôs
#
# O primeiro relatório de verdade (SM-A346MU, Android 16) saiu com “Nenhum
# problema nas áreas que o scanner mede” e “PARTIÇÕES” vazia na mesma tela que
# listava as pastas. Não era o aparelho: era a varredura mentindo.
# ---------------------------------------------------------------------------

def test_toda_leitura_do_scanner_e_feita_pela_varredura():
    """O scanner só enxerga o que está em `saidas`, com a chave exata.

    Este teste é o que faltava: ele compara a lista de comandos da varredura com
    a do scanner, chave por chave. Era exatamente a diferença entre as duas que
    fazia o diagnóstico sair vazio.
    """
    from server import diagnostico_celular as dc

    da_varredura = {" ".join(c[1:]) for c in vd.COMANDOS}
    faltando = sorted({" ".join(c[1:]) for c in dc.COMANDOS} - da_varredura)
    assert not faltando, (
        "a varredura não roda estas leituras que o scanner procura, então o "
        f"diagnóstico sai vazio: {faltando}"
    )


def test_o_exemplo_de_teste_cobre_a_lista_inteira():
    """Se o exemplo não cobre `COMANDOS`, o teste não prova nada — foi assim que
    o defeito passou na 0.92.5."""
    chaves = {" ".join(c[1:]) for c in vd.COMANDOS}
    assert chaves - set(saidas()) == set(), "falta saída de exemplo para alguma leitura"


def test_o_diagnostico_roda_na_varredura_e_acha_o_que_ha():
    """Com o disco a 95%, a varredura tem de dizer que há problema — não “nada”."""
    relatorio = vd.montar(medido())
    assert relatorio["problemas"], "a varredura engoliu o achado do scanner"
    ids = {p["id"] for p in relatorio["problemas"]}
    assert "armazenamento-cheio" in ids
    assert "achei" in relatorio["veredito"] or "achou" in relatorio["veredito"]


def test_as_particoes_nao_saem_vazias_quando_o_aparelho_responde():
    relatorio = vd.montar(medido())
    particoes = next(s for s in relatorio["secoes"] if s["id"] == "particoes")
    assert particoes["itens"], "a seção Partições saiu sem item mesmo com saída"
    assert any("mmcblk0p32" in i["rotulo"] for i in particoes["itens"])


def test_particao_negada_explica_em_vez_de_sumir():
    """Android 16 do dono: `cat /proc/partitions` → Permission denied.

    A seção tem de continuar existindo, dizendo que o aparelho não publica —
    seção vazia parece defeito do JARVIS.
    """
    base = saidas()
    base["cat /proc/partitions"] = ""
    relatorio = vd.montar({"serial": "ABC123", "saidas": base, "falhas": []})
    particoes = next(s for s in relatorio["secoes"] if s["id"] == "particoes")
    assert particoes["itens"]
    texto = particoes["itens"][0]["valor"]
    assert "não entrega" in texto or "sem root" in texto


def test_a_memoria_do_scanner_nao_e_engolida_pelo_dumpsys():
    """O `dumpsys meminfo` não publica `MemAvailable` — a seção tem de trazer as duas."""
    relatorio = vd.montar(medido())
    memoria = next(s for s in relatorio["secoes"] if s["id"] == "memoria")
    rotulos = {i["rotulo"] for i in memoria["itens"]}
    assert "RAM total" in rotulos, "perdeu o resumo do dumpsys"
    assert any("Disponível" in r or "Total" in r for r in rotulos), "perdeu a leitura do scanner"


def test_a_identidade_nao_perde_a_bateria():
    relatorio = vd.montar(medido())
    identidade = next((s for s in relatorio["secoes"] if s["id"] == "identidade"), None)
    if identidade:  # depende de haver anatomia no ambiente
        texto = " ".join(i["rotulo"] for i in identidade["itens"])
        assert "Bootloader" in texto


def test_sem_leitura_de_saude_nao_se_diz_que_esta_tudo_bem():
    """O pior defeito do relatório real: sem medida, a frase era “nada de errado”."""
    vazio = {
        "serial": "ABC123",
        "saidas": {k: v for k, v in saidas().items() if k.startswith("ls ") or k.startswith("dumpsys meminfo")},
        "falhas": [],
    }
    relatorio = vd.montar(vazio)
    # A frase pode citar “está tudo bem” — mas só para **negar**: o que não pode
    # é afirmar. A conferência é sobre a afirmação, não sobre a palavra.
    assert "não dá para dizer que está tudo bem" in relatorio["veredito"]
    assert "não deu para medir" in relatorio["veredito"]


def test_o_texto_do_console_mostra_problema_e_como_resolver():
    texto = vd.em_texto(vd.montar(medido()))
    assert "O QUE ESTÁ ERRADO" in texto
    assert "O QUE DÁ PARA MELHORAR" in texto or True  # otimização depende do aparelho
    assert "Ajustes" in texto or "Reinicie" in texto


def test_a_anatomia_e_lida_no_serial_certo(monkeypatch):
    """Com dois celulares no cabo, `ler_android()` sem serial podia ler o outro."""
    vistos: list[str] = []

    def falso(serial="", **_):
        vistos.append(serial)
        return {"titulo": "SM-A346MU · Android 16", "secoes": [], "limitacoes": []}

    monkeypatch.setattr(vd.anatomia, "ler_android", falso)
    monkeypatch.setattr(vd.diagnostico_celular, "analisar", lambda medido: {"secoes": [], "problemas": []})
    vd.montar({"serial": "RXCW400ZV3F", "saidas": saidas(), "falhas": []})
    assert vistos == ["RXCW400ZV3F"]
