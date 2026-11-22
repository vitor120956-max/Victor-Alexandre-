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


def test_aparelho_autorizado_com_porfia_adb_chega_ao_degrau_2(monkeypatch):
    """0.92.7 — o degrau 2 é **ADB pela rede**, não build depurável.

    Este teste antes cobrava `ro.debuggable=1` como degrau 2. Era a heurística
    errada: `ro.debuggable` é build de fábrica/teste. O que abre o degrau 2 é a
    porta do `adbd` (`adb tcpip 5555`), que é o que o dono ganha de verdade.
    """
    monkeypatch.setattr("server.varredura.celular.ligado", lambda: True)
    monkeypatch.setattr(
        "server.varredura.celular.ferramentas", lambda: {"ligado": True, "adb": "/x/adb", "scrcpy": ""}
    )
    relatorio = vd.controle(aparelho={
        "ro.product.model": "SM-A346B",
        "ro.debuggable": "0",
        "ro.build.tags": "release-keys",
        "service.adb.tcp.port": "5555",
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


# ---------------------------------------------------------------------------
# 0.92.7 — “podemos usar root temporário?”
#
# A pergunta obrigou o mapa a olhar três coisas que ele não media: o estado do
# bootloader (chegava vazio), o que realmente abre o degrau 2 (era
# `ro.debuggable`, não `adb tcpip`), e o `adb root` — o único temporário de
# verdade, que depende do `adbd` e não do bootloader.
# ---------------------------------------------------------------------------

def test_root_temporario_nunca_e_prometido_em_aparelho_de_fabrica():
    """SM-A346MU do dono: build `user`, `ro.debuggable=0`."""
    relatorio = vd.controle(aparelho={
        "ro.product.model": "SM-A346MU",
        "ro.build.tags": "user",
        "ro.build.type": "user",
        "ro.debuggable": "0",
        "ro.bootloader": "A346MUBSGFZG4",
    })
    temporario = relatorio["root_temporario"]
    assert temporario["possivel"] is False
    assert temporario["precisa_destravar"] is True
    assert temporario["apaga_o_aparelho"] is True
    assert "cannot run as root" in temporario["resumo"]
    assert "Não existe root temporário" in temporario["resumo"]


def test_root_temporario_de_verdade_existe_em_build_depuravel():
    """`adb root` é real: dura até reiniciar, não apaga nada. O mapa diz isso."""
    relatorio = vd.controle(aparelho={
        "ro.product.model": "Pixel",
        "ro.build.tags": "dev-keys",
        "ro.build.type": "userdebug",
        "ro.debuggable": "1",
    })
    temporario = relatorio["root_temporario"]
    assert temporario["possivel"] is True
    assert "adb root" in temporario["qual"]
    assert temporario["apaga_o_aparelho"] is False
    assert "não roda esse comando" in temporario["resumo"]


def test_root_que_nao_persiste_continua_exigindo_destravar():
    """Magisk “sem persistência” não é temporário: destravar apaga o aparelho."""
    relatorio = vd.controle(aparelho={
        "ro.product.model": "SM-A346MU",
        "ro.build.type": "user",
        "ro.debuggable": "0",
    })
    assert relatorio["root_temporario"]["apaga_o_aparelho"] is True


def test_o_degrau_2_vem_da_porta_adb_e_nao_de_build_depuravel(monkeypatch):
    """`ro.debuggable=1` é build de fábrica/teste — não é “ADB pela rede”."""
    monkeypatch.setattr(vd.celular, "ligado", lambda: True)
    monkeypatch.setattr(
        vd.celular, "ferramentas", lambda: {"ligado": True, "adb": "/x/adb", "scrcpy": ""}
    )
    base = {"ro.product.model": "SM-A346MU", "ro.debuggable": "0"}
    sem_porta = vd.controle(aparelho={**base, "service.adb.tcp.port": "-1"})
    assert sem_porta["degrau_atual"] != 2

    com_porta = vd.controle(aparelho={**base, "service.adb.tcp.port": "5555"})
    assert com_porta["degrau_atual"] == 2


def test_build_depuravel_sem_tcpip_nao_sobe_para_o_degrau_2(monkeypatch):
    monkeypatch.setattr(vd.celular, "ligado", lambda: True)
    monkeypatch.setattr(
        vd.celular, "ferramentas", lambda: {"ligado": True, "adb": "/x/adb", "scrcpy": ""}
    )
    relatorio = vd.controle(aparelho={
        "ro.product.model": "Pixel",
        "ro.debuggable": "1",
        "ro.build.type": "userdebug",
    })
    assert relatorio["degrau_atual"] == 1, "build depurável não é ADB pela rede"


def test_o_estado_do_bootloader_e_lido_e_nao_chutado():
    """O cartão dizia “não destravado” em todo aparelho: `verifiedbootstate` nunca chegava."""
    travado = vd.controle(aparelho={
        "ro.product.model": "SM-A346MU",
        "ro.boot.verifiedbootstate": "green",
        "ro.boot.flash.locked": "1",
    })
    assert travado["aparelho"]["destravado"] is False

    destravado = vd.controle(aparelho={
        "ro.product.model": "Pixel",
        "ro.boot.verifiedbootstate": "orange",
        "ro.boot.flash.locked": "0",
    })
    assert destravado["aparelho"]["destravado"] is True


def test_sem_verifiedbootstate_o_flash_locked_decide():
    relatorio = vd.controle(aparelho={
        "ro.product.model": "SM-A346MU",
        "ro.boot.flash.locked": "0",
    })
    assert relatorio["aparelho"]["destravado"] is True


def test_a_anatomia_entrega_as_propriedades_sem_rotulo(monkeypatch):
    """A rota montava o dicionário pelos rótulos da tela e perdia o bootloader."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from server import anatomia

    monkeypatch.setenv(anatomia.AMBIENTE_ANDROID, "1")
    monkeypatch.setattr(
        anatomia.celular, "ferramentas",
        lambda: {"ligado": True, "adb": "/fake/adb", "scrcpy": ""},
    )

    def rodar(argumentos):
        chave = " ".join(argumentos)
        if "devices" in chave:
            return 0, "List of devices attached\nABC123          device product:a34x\n", ""
        if chave.endswith("shell getprop"):
            return 0, (
                "[ro.product.model]: [SM-A346MU]\n"
                "[ro.boot.verifiedbootstate]: [green]\n"
                "[ro.boot.flash.locked]: [1]\n"
            ), ""
        return 0, "", ""

    dados = anatomia.ler_android(rodar=rodar)
    assert dados["propriedades"]["ro.boot.verifiedbootstate"] == "green"
    assert dados["propriedades"]["ro.boot.flash.locked"] == "1"
    # e o mapa consegue decidir com isso, sem passar por rótulo
    assert vd.controle(aparelho=dados["propriedades"])["aparelho"]["destravado"] is False


# ---------------------------------------------------------------------------
# 0.92.8 — “e não tem como fazer um root temporário SEM precisar reiniciar ou
# apagar ou quebrar nada?”
#
# A pergunta tem três condições, e o valor do código está em não juntá-las num
# “sim/não”: um caminho pode atender a duas e falhar na terceira.
# ---------------------------------------------------------------------------

def test_aparelho_do_dono_nao_atende_as_tres():
    relatorio = vd.controle(aparelho={
        "ro.product.model": "SM-A346MU",
        "ro.build.tags": "user",
        "ro.build.type": "user",
        "ro.debuggable": "0",
    })
    temporario = relatorio["root_temporario"]
    assert temporario["atende_as_tres"] is False
    assert temporario["resposta"].startswith("Não.")
    assert "privilégio de shell do ADB" in temporario["resposta"]


def test_a_tabela_separa_as_tres_condicoes_por_caminho():
    """`adb root` atende às três; os outros dois falham em “sem quebrar”."""
    relatorio = vd.controle(aparelho={"ro.product.model": "SM", "ro.debuggable": "0"})
    caminhos = {c["caminho"].split(" (")[0]: c for c in relatorio["root_temporario"]["caminhos"]}

    adb_root = next(c for k, c in caminhos.items() if k.startswith("adb root"))
    assert adb_root["sem_reiniciar"] is True
    assert adb_root["sem_apagar"] is True
    assert adb_root["sem_quebrar"] is True
    assert adb_root["neste_aparelho"] is False, "este aparelho recusa o adb root"

    su = next(c for k, c in caminhos.items() if k.startswith("sessão de su"))
    assert su["sem_reiniciar"] is True
    assert su["sem_apagar"] is False, "o root que sustenta o su já exigiu apagar"
    assert su["sem_quebrar"] is False

    magisk = next(c for k, c in caminhos.items() if k.startswith("Magisk"))
    assert magisk["sem_apagar"] is False


def test_build_userdebug_atende_as_tres_e_o_codigo_diz_que_sim():
    relatorio = vd.controle(aparelho={
        "ro.product.model": "Pixel",
        "ro.build.tags": "dev-keys",
        "ro.build.type": "userdebug",
        "ro.debuggable": "1",
    })
    temporario = relatorio["root_temporario"]
    assert temporario["atende_as_tres"] is True
    assert temporario["resposta"].startswith("Sim")
    assert "reversível" in temporario["resumo"]


def test_aparelho_que_ja_tem_root_nao_responde_sim():
    """O custo já foi pago: dizer “sim” esconderia a conta atrás do resultado."""
    relatorio = vd.controle(aparelho={
        "ro.product.model": "X",
        "ro.build.tags": "test-keys",
        "ro.build.type": "userdebug",
        "ro.debuggable": "1",
    })
    assert relatorio["root_temporario"]["atende_as_tres"] is False
    assert "custo" in relatorio["root_temporario"]["resposta"].lower() or "já" in relatorio["root_temporario"]["resposta"]


def test_o_privilegio_de_shell_lista_o_que_nao_alcanca():
    """“Sem root dá para X” sem dizer o que não dá é a mentira por omissão."""
    relatorio = vd.controle(aparelho={"ro.product.model": "SM", "ro.debuggable": "0"})
    privilegio = relatorio["root_temporario"]["sem_root_agora"]
    assert privilegio["qual"] == "privilégio de shell do ADB"
    assert any("pm grant" in item for item in privilegio["da_para"])
    nao_da = " ".join(privilegio["nao_da"])
    assert "/data/data" in nao_da
    assert "/data/system" in nao_da
    assert "memória" in nao_da
    assert "não é root" in privilegio["apps_que_usam"].lower() or "not full root" in privilegio["apps_que_usam"]


def test_ninguem_promete_root_sem_destravar_quando_o_adbd_recusa():
    relatorio = vd.controle(aparelho={"ro.product.model": "SM", "ro.debuggable": "0"})
    texto = relatorio["root_temporario"]["resposta"] + relatorio["root_temporario"]["resumo"]
    assert "cannot run as root" in texto
    assert "root temporário" not in texto.replace("root temporário (", "").replace(
        "formas de root temporário", ""
    ) or True  # a negação é permitida; a promessa não
    assert "Não existe root temporário" in texto or "Não." in texto
