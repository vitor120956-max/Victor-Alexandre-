"""Testes do scanner do celular (0.92.3).

O pedido: *“vou testar com o meu cll, quero ver se consigo melhorar e otimizar e
ver uns problemas que ele está apresentando — talvez passando um scanner nele a
gente consegue resolver”*.

O que estes testes travam:

- **só leitura** — a lista de comandos é conferida palavra por palavra; nenhum
  `install`, `push`, `rm`, `pm uninstall`, `settings put`, `reboot` ou `su`;
- **cada achado tem a medida que o sustenta** — não existe problema sem número e
  origem;
- **armazenamento cheio, bateria gasta, aquecimento, patch antigo, app travando**
  → cada um no seu limiar, com o teste nos dois lados (logo abaixo não é achado);
- **aparelho saudável não inventa problema** — a resposta é “nenhum problema”;
- **o aparelho desligado/autorizado errado explica o que fazer**;
- **o texto do console** cabe numa tela e termina dizendo o que não faz.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import diagnostico_celular as dc
from server.app import create_app
from server.skill_registry import build_registry

AGORA = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Saídas de exemplo — no formato do Android de verdade
# ---------------------------------------------------------------------------

GETPROP = (
    "[ro.product.manufacturer]: [samsung]\n"
    "[ro.product.model]: [SM-A346B]\n"
    "[ro.build.version.release]: [14]\n"
    "[ro.build.version.sdk]: [34]\n"
    "[ro.build.version.security_patch]: [2026-10-01]\n"
    "[ro.build.tags]: [release-keys]\n"
)

BATERIA = (
    "Current Battery Service state:\n"
    "  AC powered: false\n"
    "  USB powered: true\n"
    "  status: 3\n"
    "  health: 2\n"
    "  level: 87\n"
    "  voltage: 4321\n"
    "  temperature: 312\n"
)

POWER_SUPPLY = (
    "/sys/class/power_supply/battery/charge_full=4200000\n"
    "/sys/class/power_supply/battery/charge_full_design=5000000\n"
    "/sys/class/power_supply/battery/cycle_count=512\n"
)

DF = (
    "Filesystem      1K-blocks     Used Available Use% Mounted on\n"
    "/dev/block/dm-8  114496460 44231220  70265240  39% /data\n"
    "tmpfs             3811560      388   3811172   1% /dev\n"
)

DF_CHEIO = (
    "Filesystem      1K-blocks     Used Available Use% Mounted on\n"
    "/dev/block/dm-8  114496460 108000000   6496460  94% /data\n"
)

MEMINFO = (
    "MemTotal:        7643124 kB\n"
    "MemFree:          612004 kB\n"
    "MemAvailable:    2903340 kB\n"
    "SwapTotal:       2097148 kB\n"
)

MEMINFO_BAIXA = (
    "MemTotal:        4000000 kB\n"
    "MemAvailable:     200000 kB\n"
    "SwapTotal:       1000000 kB\n"
)

UPTIME = "1728000.42 12345.00\n"  # 20 dias

PS = (
    "  RSS NAME\n"
    " 812345 com.whatsapp\n"
    " 900000 com.facebook.katana\n"
    " 120000 com.android.systemui\n"
)

TERMICA = "cpu-0:45000\ncpu-1:52000\nbattery:32000\n"

TERMICA_QUENTE = "cpu-0:82000\ncpu-1:91000\n"

ANIMACAO = "1.0\n"

APPS = "package:com.whatsapp\npackage:com.instagram.android\n"

CRASH = (
    "Build fingerprint: 'samsung/a34x/a34x:14'\n"
    "FATAL EXCEPTION: main\n"
    "Process: com.instagram.android, PID: 1234\n"
    "java.lang.NullPointerException\n"
)


def saidas(**trocas: str) -> dict[str, str]:
    base = {
        "getprop": GETPROP,
        "dumpsys battery": BATERIA,
        "for f in /sys/class/power_supply/battery/*": POWER_SUPPLY,
        "df -k": DF,
        "cat /proc/meminfo": MEMINFO,
        "cat /proc/uptime": UPTIME,
        "ps -A -o RSS,NAME": PS,
        "for z in /sys/class/thermal/thermal_zone*": TERMICA,
        "settings get global window_animation_scale": ANIMACAO,
        "pm list packages -3": APPS,
        "logcat -b crash -d -t 80": "",
        "which su": "",
        "dumpsys diskstats": "",
    }
    base.update(trocas)
    return base


def medido(**trocas: str) -> dict:
    return {"serial": "ABC123", "saidas": saidas(**trocas), "falhas": [], "comandos": []}


def _ids(relatorio: dict) -> set[str]:
    return {p["id"] for p in relatorio["problemas"]}


# ---------------------------------------------------------------------------
# Leitura das saídas
# ---------------------------------------------------------------------------

def test_le_o_uso_real_do_disco_e_nao_o_use_porcento_arredondado():
    pontos = dc.ler_df(DF_CHEIO)
    assert pontos["/data"]["pct"] == pytest.approx(94.3, abs=0.2)
    assert pontos["/data"]["livre"] == pytest.approx(6496460 * 1024)


def test_le_a_capacidade_da_bateria_pelo_power_supply():
    energia = dc.ler_power_supply(POWER_SUPPLY)
    assert energia["charge_full"] == "4200000"
    assert energia["charge_full_design"] == "5000000"
    assert energia["cycle_count"] == "512"


def test_le_os_processos_que_mais_ocupam_memoria():
    processos = dc.ler_top_processos(PS)
    assert processos[0]["nome"] == "com.facebook.katana"
    assert processos[0]["kb"] == 900000


def test_le_o_sensor_mais_quente_primeiro():
    sensores = dc.ler_termica(TERMICA_QUENTE)
    assert sensores[0]["nome"] == "cpu-1"
    assert sensores[0]["c"] == 91.0


def test_le_o_app_que_travou():
    assert dc.ler_crash(CRASH) == ["com.instagram.android"]


def test_o_crash_sem_fatal_nao_vira_achado():
    assert dc.ler_crash("I/ActivityManager: nada\n") == []


# ---------------------------------------------------------------------------
# A lista de comandos é de leitura
# ---------------------------------------------------------------------------

def test_a_lista_de_comandos_nao_tem_nada_que_altera():
    permitidos_settings = {
        "window_animation_scale",
        "transition_animation_scale",
        "animator_duration_scale",
    }
    for comando in dc.COMANDOS:
        texto = " ".join(comando)
        assert "uninstall" not in texto
        assert " install" not in texto
        assert " push" not in texto and " pull" not in texto
        assert " rm " not in texto and " reboot" not in texto
        assert "settings put" not in texto and "settings delete" not in texto
        assert " su" not in texto or comando[-1] == "su" and comando[-2] == "which"
        if comando[:2] == ("shell", "settings"):
            assert comando[2] == "get"
            assert comando[3] == "global"
            assert comando[4] in permitidos_settings
        if "pm" in comando:
            assert comando[2:] == ("list", "packages", "-3")


def test_todo_comando_passa_pelo_serial():
    """Nenhum comando pode ser global: com dois aparelhos na USB, isso é o
    que evita medir o aparelho errado."""
    registro: list[list[str]] = []

    def rodar(argumentos: list[str]):
        registro.append(list(argumentos))
        chave = " ".join(argumentos[3:])
        for trecho, saida in saidas().items():
            if chave.startswith(trecho):
                return 0, saida, ""
        if argumentos[1:3] == ["devices", "-l"]:
            return 0, "List of devices attached\nABC123          device product:test model:SM_A346B\n", ""
        return 0, "", ""

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("JARVIS_HOST_CELULAR", "1")
    monkeypatch.setattr("server.celular.ferramentas", lambda: {"ligado": True, "adb": "/fake/adb", "scrcpy": ""})
    try:
        dados = dc.coletar(rodar=rodar)
    finally:
        monkeypatch.undo()
    assert dados["serial"] == "ABC123"
    comandos_de_leitura = [c for c in registro if "shell" in c]
    assert comandos_de_leitura, "nenhum comando rodou"
    for comando in comandos_de_leitura:
        assert comando[:3] == ["/fake/adb", "-s", "ABC123"], comando


# ---------------------------------------------------------------------------
# Julgamento
# ---------------------------------------------------------------------------

def test_aparelho_saudavel_nao_inventa_problema():
    relatorio = dc.analisar(medido(), agora=AGORA)
    assert relatorio["problemas"] == []
    assert "Nenhum problema" in relatorio["veredito"]
    assert relatorio["titulo"] == "SM-A346B · Android 14"


def test_disco_quase_cheio_vira_achado_alto_com_a_medida():
    relatorio = dc.analisar(medido(**{"df -k": DF_CHEIO}), agora=AGORA)
    problema = next(p for p in relatorio["problemas"] if p["id"] == "armazenamento-cheio")
    assert problema["gravidade"] == "alta"
    assert "94%" in problema["medido"]
    assert any("Ajustes → Armazenamento" in passo for passo in problema["o_que_fazer"])
    # E o limite não promete que limpar cache resolve tudo.
    assert "cache" in problema["limite"]


def test_disco_no_limiar_medio_nao_e_o_mesmo_achado():
    # 104.730.000 kB usados de 114.496.460 → ~91,5%... não: 104,73/114,50 = 91,5%.
    # Use 96.000.000 usados de 114.496.460 → 83,8%, dentro da faixa “apertado”.
    apertado = DF.replace("44231220  70265240  39%", "96000000  18496460  84%")
    relatorio = dc.analisar(medido(**{"df -k": apertado}), agora=AGORA)
    assert "armazenamento-cheio" not in _ids(relatorio)
    assert "armazenamento-apertado" in _ids(relatorio)


def test_pouca_memoria_livre_vira_achado():
    relatorio = dc.analisar(medido(**{"cat /proc/meminfo": MEMINFO_BAIXA}), agora=AGORA)
    problema = next(p for p in relatorio["problemas"] if p["id"] == "memoria-baixa")
    assert problema["gravidade"] == "alta"
    # 0,2 GB de 4,0 GB = 5,0% — com uma casa decimal, para o número explicar o achado.
    assert "5,0%" in problema["medido"]
    assert any("Reinicie" in passo for passo in problema["o_que_fazer"])


def test_bateria_gasta_diz_o_porcento_da_capacidade_de_fabrica():
    # 3.600 mAh de 5.000 de fábrica = 72% — abaixo do limiar de 80%.
    gasta = POWER_SUPPLY.replace("charge_full=4200000", "charge_full=3600000")
    relatorio = dc.analisar(
        medido(**{"for f in /sys/class/power_supply/battery/*": gasta}), agora=AGORA
    )
    problema = next(p for p in relatorio["problemas"] if p["id"] == "bateria-gasta")
    assert "72%" in problema["medido"]
    assert "3600 mAh" in problema["medido"] and "5000 mAh" in problema["medido"]
    assert any("assistência" in passo for passo in problema["o_que_fazer"])
    assert "não devolve" in problema["limite"]


def test_bateria_boa_nao_entra_como_gasta():
    nova = POWER_SUPPLY.replace("charge_full=4200000", "charge_full=4900000")
    # 4.900/5.000 = 98%: bateria saudável não é achado.
    relatorio = dc.analisar(medido(**{"for f in /sys/class/power_supply/battery/*": nova}), agora=AGORA)
    assert "bateria-gasta" not in _ids(relatorio)


def test_bateria_quente_carregando_e_achado_e_fria_nao():
    quente = BATERIA.replace("status: 3", "status: 2").replace("temperature: 312", "temperature: 425")
    relatorio = dc.analisar(medido(**{"dumpsys battery": quente}), agora=AGORA)
    assert "bateria-quente-carregando" in _ids(relatorio)
    fria = BATERIA.replace("status: 3", "status: 2").replace("temperature: 312", "temperature: 300")
    assert "bateria-quente-carregando" not in _ids(dc.analisar(medido(**{"dumpsys battery": fria}), agora=AGORA))


def test_sensor_acima_de_70_graus_explica_o_throttling():
    relatorio = dc.analisar(
        medido(**{"for z in /sys/class/thermal/thermal_zone*": TERMICA_QUENTE}), agora=AGORA
    )
    problema = next(p for p in relatorio["problemas"] if p["id"] == "aquecendo")
    assert problema["gravidade"] == "alta"
    assert "91" in problema["medido"]
    assert "throttling" in problema["causa"]


def test_patch_velho_conta_os_dias_a_partir_do_patch():
    antigo = GETPROP.replace("2026-10-01", "2025-01-05")
    relatorio = dc.analisar(medido(getprop=antigo), agora=AGORA)
    problema = next(p for p in relatorio["problemas"] if p["id"] == "patch-antigo")
    assert "2025-01-05" in problema["medido"]
    assert any("Atualização de software" in passo for passo in problema["o_que_fazer"])


def test_app_travando_e_achado_medio_e_diz_qual_app():
    relatorio = dc.analisar(medido(**{"logcat -b crash -d -t 80": CRASH}), agora=AGORA)
    problema = next(p for p in relatorio["problemas"] if p["id"] == "app-travando")
    assert problema["gravidade"] == "media"
    assert "com.instagram.android" in problema["medido"]
    # E não manda “limpar dados” sem avisar o que se perde.
    assert any("não “Limpar dados”" in passo for passo in problema["o_que_fazer"])


def test_root_e_build_de_teste_aparecem_como_informacao():
    relatorio = dc.analisar(
        medido(**{
            "which su": "/system/xbin/su\n",
            "getprop": GETPROP.replace("release-keys", "test-keys"),
        }),
        agora=AGORA,
    )
    ids = _ids(relatorio)
    assert {"root", "build-de-teste"} <= ids
    root = next(p for p in relatorio["problemas"] if p["id"] == "root")
    assert root["gravidade"] == "baixa"
    assert "nunca usa root" in root["limite"]


def test_otimizacoes_dizem_quando_o_ganho_nao_foi_medido():
    relatorio = dc.analisar(medido(), agora=AGORA)
    animacao = next(o for o in relatorio["otimizacoes"] if o["id"] == "animacao")
    assert animacao["medido"] is False
    assert "não muda desempenho medido" in animacao["ganho"]
    reiniciar = next(o for o in relatorio["otimizacoes"] if o["id"] == "reiniciar")
    assert reiniciar["medido"] is True


def test_processo_pesado_vira_otimizacao_com_o_numero():
    relatorio = dc.analisar(medido(), agora=AGORA)
    fechar = next(o for o in relatorio["otimizacoes"] if o["id"].startswith("fechar-"))
    assert "com.facebook.katana" in fechar["id"]
    assert "com.facebook.katana" in fechar["titulo"]
    assert "MB" in fechar["ganho"]


def test_gravidade_ordena_o_resultado():
    relatorio = dc.analisar(
        medido(**{
            "df -k": DF_CHEIO,
            "getprop": GETPROP.replace("2026-10-01", "2024-01-01"),
            "which su": "/system/xbin/su\n",
        }),
        agora=AGORA,
    )
    gravidades = [p["gravidade"] for p in relatorio["problemas"]]
    assert gravidades == sorted(gravidades, key=lambda g: {"alta": 0, "media": 1, "baixa": 2}[g])
    assert "principal" in relatorio["veredito"]


def test_o_relatorio_termina_dizendo_o_que_nao_faz():
    relatorio = dc.analisar(medido(), agora=AGORA)
    assert any("Não desinstala" in frase for frase in relatorio["nao_faz"])
    assert any("não devolve" not in f for f in relatorio["nao_faz"])


# ---------------------------------------------------------------------------
# Texto do console
# ---------------------------------------------------------------------------

def test_o_texto_do_console_mostra_medida_causa_passo_e_limite():
    relatorio = dc.analisar(medido(**{"df -k": DF_CHEIO}), agora=AGORA)
    texto = dc.em_texto(relatorio)
    assert "SM-A346B · Android 14" in texto
    assert "[ALTA]" in texto
    assert "medido:" in texto and "causa:" in texto and "limite:" in texto
    assert "O QUE ESTE SCANNER NÃO FAZ" in texto
    assert "Ajustes → Armazenamento" in texto


# ---------------------------------------------------------------------------
# Erros de acesso
# ---------------------------------------------------------------------------

def test_scanner_desligado_explica_a_variavel(monkeypatch):
    monkeypatch.delenv("JARVIS_HOST_CELULAR", raising=False)
    monkeypatch.setattr("server.celular.ligado", lambda: False)
    with pytest.raises(dc.DiagnosticoError) as erro:
        dc.diagnosticar()
    assert "JARVIS_HOST_CELULAR=1" in str(erro.value)


def test_sem_aparelho_diz_que_o_cabo_pode_ser_de_carga(monkeypatch):
    monkeypatch.setenv("JARVIS_HOST_CELULAR", "1")
    monkeypatch.setattr("server.celular.ferramentas", lambda: {"ligado": True, "adb": "/fake/adb", "scrcpy": ""})
    monkeypatch.setattr("server.anatomia.aparelhos", lambda rodar=None: [])
    with pytest.raises(dc.DiagnosticoError) as erro:
        dc.diagnosticar(rodar=lambda argumentos: (0, "", ""))
    assert "carga" in str(erro.value)


def test_aparelho_nao_autorizado_pede_o_permitir_na_tela(monkeypatch):
    monkeypatch.setenv("JARVIS_HOST_CELULAR", "1")
    monkeypatch.setattr("server.celular.ferramentas", lambda: {"ligado": True, "adb": "/fake/adb", "scrcpy": ""})
    monkeypatch.setattr(
        "server.anatomia.aparelhos",
        lambda rodar=None: [{"serial": "ABC", "estado": "unauthorized"}],
    )
    with pytest.raises(dc.DiagnosticoError) as erro:
        dc.diagnosticar(rodar=lambda argumentos: (0, "", ""))
    assert "Permitir" in str(erro.value)


# ---------------------------------------------------------------------------
# API e skill
# ---------------------------------------------------------------------------

def _cliente(tmp_path: Path) -> TestClient:
    return TestClient(create_app(registry=build_registry(tmp_path / "files")))


def test_api_escaneia_sem_aparelho_e_explica(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("JARVIS_HOST_CELULAR", raising=False)
    monkeypatch.setattr("server.celular.ligado", lambda: False)
    resposta = _cliente(tmp_path).get("/api/anatomia/android/scan")
    assert resposta.status_code == 409, resposta.text
    assert "JARVIS_HOST_CELULAR" in resposta.json()["error"]["message"]


def test_api_devolve_o_diagnostico_com_aparelho_falso(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JARVIS_HOST_CELULAR", "1")
    monkeypatch.setattr("server.celular.ligado", lambda: True)
    saida = medido(**{"df -k": DF_CHEIO})
    monkeypatch.setattr(
        dc, "coletar", lambda alvo="", rodar=None: dict(saida, comandos=[])
    )
    resposta = _cliente(tmp_path).get("/api/anatomia/android/scan")
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()["result"]
    assert dados["problemas"][0]["id"] == "armazenamento-cheio"


def test_a_skill_do_scanner_existe_e_nao_tem_efeito_colateral():
    registro = build_registry(Path("/tmp/reg-scan"))
    skill = registro.get("celular.diagnostico")
    assert skill is not None
    assert skill.side_effects is False
    texto = skill.description.lower()
    assert "só leitura" in texto or "não altera" in texto
    assert "não desinstala" in texto


# ---------------------------------------------------------------------------
# 0.92.4 — “a tela trava, o frame fica lento, se mexe sozinho, e só para quando
# apaga e liga a tela”
# ---------------------------------------------------------------------------

JANELA = (
    "  Display: mDisplayId=0\n"
    "  mCurrentFocus=Window{abc123 u0 com.instagram.android/com.instagram.android.MainActivity}\n"
    "  mFocusedApp=AppWindowToken{def456 token=Token{abc123 ActivityRecord{1 u0 com.instagram.android/.MainActivity}}}\n"
)

INPUT = (
    "  Device 2: touch\n"
    "    Name: 'fts_ts'\n"
    "  Device 5: gpio-keys\n"
    "    Name: 'gpio_keys'\n"
)

ANR = (
    "10-23 12:00:01.123  1234  1234 E ActivityManager: ANR in com.instagram.android\n"
    "10-23 12:00:01.124  1234  1234 E ActivityManager: PID: 4321\n"
    "10-23 12:00:01.125  1234  1234 E ActivityManager: Reason: Input dispatching timed out "
    "(Waiting to send key event because the focused window has not finished rendering)\n"
)

GFXINFO = (
    "Applications Graphics Acceleration Info:\n"
    "** com.instagram.android/4321\n"
    "  Total frames rendered: 1200\n"
    "  Janky frames: 340 (28.33%)\n"
    "** com.whatsapp/1111\n"
    "  Total frames rendered: 800\n"
    "  Janky frames: 8 (1.00%)\n"
)


def medido_com_tela(**trocas: str) -> dict:
    base = {
        "dumpsys window displays": JANELA,
        "dumpsys input": INPUT,
        "logcat -b system -d -t 400": ANR,
        "dumpsys gfxinfo": GFXINFO,
    }
    base.update(trocas)
    return medido(**base)


def test_le_o_dispositivo_de_toque_e_a_janela_em_foco():
    dados = medido_com_tela()
    relatorio = dc.analisar(dados, agora=AGORA)
    secao = next(s for s in relatorio["secoes"] if s["id"] == "toque")
    valores = {i["rotulo"]: i["valor"] for i in secao["itens"]}
    assert "fts_ts" in valores["Dispositivo de entrada"]
    assert valores["Janela em foco"] == "com.instagram.android/com.instagram.android.MainActivity"


def test_anr_vira_achado_com_o_app_e_o_motivo():
    relatorio = dc.analisar(medido_com_tela(), agora=AGORA)
    problema = next(p for p in relatorio["problemas"] if p["id"] == "app-nao-responde")
    assert problema["gravidade"] == "alta"
    assert "com.instagram.android" in problema["medido"]
    assert "Input dispatching timed out" in problema["medido"]
    assert any("Limpar cache" in passo for passo in problema["o_que_fazer"])


def test_quadros_travados_viram_achado_grave_acima_de_25_por_cento():
    relatorio = dc.analisar(medido_com_tela(), agora=AGORA)
    problema = next(p for p in relatorio["problemas"] if p["id"] == "frame-lento")
    assert problema["gravidade"] == "alta"
    assert "28" in problema["medido"]
    # O pacote medido é o pior, não o primeiro da lista.
    assert "com.instagram.android" in problema["medido"]


def test_frame_lento_medio_quando_esta_entre_10_e_25_por_cento():
    meio = GFXINFO.replace("340 (28.33%)", "160 (13.33%)")
    relatorio = dc.analisar(medido_com_tela(**{"dumpsys gfxinfo": meio}), agora=AGORA)
    problema = next(p for p in relatorio["problemas"] if p["id"] == "frame-lento")
    assert problema["gravidade"] == "media"


def test_poucos_quadros_travados_nao_viram_achado():
    bom = GFXINFO.replace("340 (28.33%)", "40 (3.33%)")
    relatorio = dc.analisar(medido_com_tela(**{"dumpsys gfxinfo": bom}), agora=AGORA)
    assert "frame-lento" not in _ids(relatorio)


def test_tela_se_mexendo_vira_suspeita_de_toque_fantasma_com_os_testes():
    relatorio = dc.analisar(medido_com_tela(), agora=AGORA)
    problema = next(p for p in relatorio["problemas"] if p["id"] == "toque-fantasma")
    assert problema["gravidade"] == "media"
    # A frase tem de dizer que é suspeita medida pela consequência, não laudo.
    assert "não um diagnóstico fechado" in problema["limite"]
    # E os três testes que separam causa física de software estão lá.
    texto = " ".join(problema["o_que_fazer"]).lower()
    assert "capa" in texto and "película" in texto
    assert "carregador" in texto
    assert "mostrar toques" in texto


def test_sem_medida_de_tela_nao_aparece_toque_fantasma():
    relatorio = dc.analisar(medido(), agora=AGORA)  # aparelho saudável, sem ANR
    assert "toque-fantasma" not in _ids(relatorio)


def test_aparelho_quente_vira_sugestao_de_esfriar_antes_de_julgar():
    relatorio = dc.analisar(
        medido_com_tela(**{"for z in /sys/class/thermal/thermal_zone*": "cpu-0:82000\n"}), agora=AGORA
    )
    assert any(o["id"] == "esfriar-para-destravar" for o in relatorio["otimizacoes"])


# ---------------------------------------------------------------------------
# Cruzamento com o relato (0.92.4)
# ---------------------------------------------------------------------------

def test_os_sintomas_que_a_api_aceita_tem_pergunta():
    lista = dc.sintomas()
    assert {s["id"] for s in lista} >= {"tela-prende", "frame-lento", "se-mexe-sozinho", "so-para-apagar-tela"}
    assert all(s["pergunta"].strip() for s in lista)


def test_o_relato_do_dono_poe_toque_fantasma_em_primeiro():
    relatorio = dc.analisar(medido_com_tela(), agora=AGORA)
    cruzado = dc.cruzar(relatorio, ["tela-prende", "frame-lento", "se-mexe-sozinho", "so-para-apagar-tela"])
    assert cruzado["fila"][0]["id"] == "toque-fantasma"
    assert "toque fantasma" in cruzado["veredito"].lower()
    # E a fila é decrescente em pontos.
    pontos = [c["pontos"] for c in cruzado["fila"]]
    assert pontos == sorted(pontos, reverse=True)


def test_so_relato_de_lentidao_nao_poe_toque_fantasma_em_primeiro():
    relatorio = dc.analisar(medido_com_tela(), agora=AGORA)
    cruzado = dc.cruzar(relatorio, ["frame-lento"])
    assert cruzado["fila"][0]["id"] != "toque-fantasma"


def test_sem_sintoma_marcado_a_ordem_e_a_do_que_o_aparelho_mediu():
    relatorio = dc.analisar(medido_com_tela(), agora=AGORA)
    cruzado = dc.cruzar(relatorio, [])
    assert cruzado["sintomas_marcados"] == []
    assert "Marque o que você vê" in cruzado["veredito"]
    # A primeira da fila tem de ter medida no aparelho.
    assert cruzado["fila"][0]["medido_no_aparelho"]


def test_causa_sem_medida_no_aparelho_avisa_que_nao_confirmou():
    saudavel = dc.analisar(medido(), agora=AGORA)
    cruzado = dc.cruzar(saudavel, ["se-mexe-sozinho"])
    primeira = cruzado["fila"][0]
    assert primeira["id"] == "toque-fantasma"
    assert "não mostrou medida" in cruzado["veredito"]


def test_sintoma_desconhecido_e_ignorado_sem_quebrar():
    relatorio = dc.analisar(medido(), agora=AGORA)
    cruzado = dc.cruzar(relatorio, ["vibra-sozinho", "se-mexe-sozinho"])
    assert cruzado["sintomas_marcados"] == ["se-mexe-sozinho"]


def test_o_texto_do_console_mostra_a_fila_de_suspeitas():
    relatorio = dc.analisar(medido_com_tela(), agora=AGORA)
    relatorio["sintomas"] = dc.cruzar(relatorio, ["se-mexe-sozinho", "so-para-apagar-tela", "frame-lento"])
    texto = dc.em_texto(relatorio)
    assert "O QUE VOCÊ RELATOU — SUSPEITAS EM ORDEM" in texto
    assert "Toque fantasma" in texto
    assert "teste:" in texto


# ---------------------------------------------------------------------------
# 0.95.4 — “está conectado” e o adb não vê: a mensagem tem de dizer o porquê
# ---------------------------------------------------------------------------


def test_adb_vazio_mas_windows_ve_mtp_diz_que_falta_o_driver(monkeypatch):
    """O caso do dono: a pasta “A34” aparece no Explorer e o `adb` não vê nada.

    O Windows mostrar os arquivos **não** quer dizer que o driver do ADB está
    instalado: são interfaces USB diferentes. A mensagem antiga mandava
    conferir o cabo — e o cabo estava bom.
    """
    from server import celular

    monkeypatch.setattr(
        celular, "windows_ve",
        lambda **_: {
            "consulta": True,
            "telefones": [{"vid": celular.VID_SAMSUNG, "nome": "USB Composite Device", "status": "OK"}],
            "com_problema": False, "desconhecidos": [], "genericos": [],
            "visivel": True, "dispositivos": [],
        },
    )
    frase = dc._por_que_nao_apareceu()
    assert "driver" in frase.lower()
    assert "Samsung USB Driver" in frase
    # e não pode culpar o cabo — foi o que a versão antiga fazia
    assert "cabo (tem de ser de dados" not in frase


def test_adb_vazio_com_windows_vendo_o_aparelho_aponta_a_depuracao(monkeypatch):
    from server import celular

    monkeypatch.setattr(
        celular, "windows_ve",
        lambda **_: {
            "consulta": True,
            "telefones": [{"vid": celular.VID_SAMSUNG, "nome": "SAMSUNG Android Phone", "status": "OK"}],
            "com_problema": False, "desconhecidos": [], "genericos": [],
            "visivel": True, "dispositivos": [],
        },
    )
    frase = dc._por_que_nao_apareceu()
    assert "Depuração USB" in frase
    assert "sem fio" in frase.lower()  # as duas brigam pela porta
    assert "Sempre permitir" in frase


def test_adb_vazio_e_windows_sem_celular_culpa_cabo_porta(monkeypatch):
    from server import celular

    monkeypatch.setattr(
        celular, "windows_ve",
        lambda **_: {
            "consulta": True, "telefones": [], "com_problema": False,
            "desconhecidos": [], "genericos": [{"nome": "USB Root Hub", "status": "OK"}],
            "visivel": False, "dispositivos": [],
        },
    )
    frase = dc._por_que_nao_apareceu()
    assert "não" in frase.lower() and "celular" in frase.lower()
    assert "cabo" in frase.lower()


def test_sonda_de_usb_fora_do_windows_nao_quebra_a_mensagem(monkeypatch):
    """Sem a sonda, a frase diz que NÃO perguntou ao Windows — não chuta driver.

    0.95.4 — antes ela devolvia o mesmo palpite de sempre ("confira o cabo"), e
    o dono recebeu exatamente essa frase duas varreduras seguidas: a primeira
    leu o aparelho inteiro, a segunda não viu nada. A frase agora nomeia a
    diferença em vez de repetir a lista de sempre.
    """
    from server import celular

    monkeypatch.setattr(
        celular, "windows_ve",
        lambda **_: {"consulta": False, "motivo": "A sonda de USB só existe no Windows."},
    )
    frase = dc._por_que_nao_apareceu()
    assert "Nenhum Android apareceu" in frase
    assert "não consegui perguntar ao Windows" in frase
    # o motivo real tem de aparecer, não um "(falhou)" genérico
    assert "só existe no Windows" in frase


def test_sonda_que_explode_nao_derruba_o_diagnostico(monkeypatch):
    """Uma exceção da sonda não pode virar erro diferente do que o dono espera."""
    from server import celular

    def explodir(**_):
        raise RuntimeError("powershell morreu")

    monkeypatch.setattr(celular, "windows_ve", explodir)
    frase = dc._por_que_nao_apareceu()
    assert "Nenhum Android apareceu" in frase


# ---------------------------------------------------------------------------
# 0.95.4 — “vai chover amanhã?” não é pedido para fechar app
# ---------------------------------------------------------------------------


def _modelo_fechar():
    from pathlib import Path

    from server import skill_registry as sr

    registro = sr.build_registry(Path.cwd())
    return registro.get("celular.fechar-app").input_model


def test_frase_inteira_no_campo_pacote_e_recusada_com_explicacao():
    """O dono perguntou “vai chover amanhã?” e recebeu a recusa desta skill.

    A IA escolheu a ferramenta errada e o texto foi como `pacote`. A mensagem
    antiga mandava usar “o nome do app como o Android conhece” — como se quem
    perguntou sobre chuva tivesse errado o nome de um pacote.
    """
    modelo = _modelo_fechar()
    with pytest.raises(Exception) as erro:
        modelo(pacote="vai chover amanha")
    mensagem = str(erro.value)
    assert "frase inteira" in mensagem
    assert "não é para esta skill" in mensagem


def test_pacote_verdadeiro_continua_aceito():
    from server import acoes

    # o mesmo par que `_exigir_pacote` aceita — as duas camadas concordam
    for bom in ("com.dti.telefonica", "app.revanced.android.youtube", "com.whatsapp"):
        assert acoes._exigir_pacote(bom) == bom
        assert _modelo_fechar()(pacote=bom).pacote == bom


def test_nome_de_exibicao_sem_pontos_continua_recusado_com_a_dica_antiga():
    modelo = _modelo_fechar()
    with pytest.raises(Exception) as erro:
        modelo(pacote="whatsapp")
    assert "com.whatsapp" in str(erro.value)


# ---------------------------------------------------------------------------
# 0.95.4 — o JARVIS instala o driver em vez de mandar o dono baixar
# ---------------------------------------------------------------------------


def test_driver_sem_confirmar_devolve_plano_e_nao_baixa(monkeypatch):
    """Sem `confirmado=True` nada é baixado — o dono vê URL e tamanho antes."""
    from server import sistema

    monkeypatch.setattr(sistema.platform, "system", lambda: "Windows")

    def nao_pode_baixar(*a, **k):
        raise AssertionError("baixou sem confirmação")

    monkeypatch.setattr(sistema, "baixar", nao_pode_baixar)
    plano = sistema.driver_do_celular(fabricante="samsung")
    assert plano["url"].startswith("https://developer.samsung.com/")
    assert plano["tamanho_aprox_mb"] > 0
    assert "confirmado=True" in plano["confirmação"]
    # e a mensagem tem de deixar claro que o celular não recebe nada
    assert "nenhum app" in plano["no_celular"].lower()


def test_driver_confirmado_baixa_e_instala_pela_quarentena(monkeypatch):
    """O caminho real: baixa, confere o hash e chama o instalador."""
    from server import sistema

    monkeypatch.setattr(sistema.platform, "system", lambda: "Windows")
    chamadas: list[str] = []

    def baixar(**kwargs):
        chamadas.append(f"baixar:{kwargs['url']}")
        return {"arquivo": "/tmp/quarentena/driver.exe", "bytes": 34_000_000, "sha256": "a" * 64, "tipo": "application/x-msdownload"}

    def instalar(**kwargs):
        chamadas.append(f"instalar-plano:{kwargs['arquivo']}")
        return {"plano": "driver.exe", "confirmação": "abc123"}

    def executar(**kwargs):
        # o token tem de ser o que o plano devolveu — não um qualquer
        chamadas.append(f"executar:{kwargs['confirmacao']}")
        return {"estado": "instalado", "saida": "Samsung USB Driver instalado."}

    monkeypatch.setattr(sistema, "baixar", baixar)
    monkeypatch.setattr(sistema, "instalar", instalar)
    monkeypatch.setattr(sistema, "executar", executar)
    feito = sistema.driver_do_celular(fabricante="samsung", confirmado=True)
    assert chamadas == [
        "baixar:https://developer.samsung.com/sdp/file/de97d0ea-da03-46a4-b35d-346d37a878e0",
        "instalar-plano:/tmp/quarentena/driver.exe",
        "executar:abc123",
    ], chamadas
    assert feito["baixado"]["sha256"] == "a" * 64
    # o próximo passo é dito, não deixado para o dono adivinhar
    assert "reconecte o cabo" in feito["depois"]


def test_driver_recusa_fabricante_desconhecido_sem_inventar_url(monkeypatch):
    from server import sistema

    monkeypatch.setattr(sistema.platform, "system", lambda: "Windows")
    with pytest.raises(sistema.SistemaError) as erro:
        sistema.driver_do_celular(fabricante="xiaomi")
    assert "samsung" in str(erro.value).lower()


def test_driver_nao_existe_fora_do_windows(monkeypatch):
    """No Linux/macOS o driver é do kernel: instalar `.exe` seria enganar."""
    from server import sistema

    monkeypatch.setattr(sistema.platform, "system", lambda: "Linux")
    with pytest.raises(sistema.SistemaError) as erro:
        sistema.driver_do_celular(fabricante="samsung")
    assert "Windows" in str(erro.value)


def test_a_skill_do_driver_esta_no_registro_e_diz_o_que_faz():
    from pathlib import Path

    from server import skill_registry as sr

    registro = sr.build_registry(Path.cwd())
    definicao = registro.get("sistema.driver-celular")
    assert definicao.requires_confirmation is True
    assert definicao.side_effects is True
    # a descrição precisa dizer que instala no PC — é a dúvida número um do dono
    texto = definicao.description.lower()
    assert "no pc" in texto and "não no celular" in texto


def test_driver_nao_diz_instalado_quando_o_plano_nao_devolve_token(monkeypatch):
    """0.95.4 baixava e parava no plano — o dono achava que estava instalado.

    `instalar()` só monta o plano e devolve o token; quem executa é `executar()`.
    Se o token não vier, o certo é falhar alto, não devolver "baixado" e seguir.
    """
    from server import sistema

    monkeypatch.setattr(sistema.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        sistema,
        "baixar",
        lambda **k: {"arquivo": "/tmp/quarentena/driver.exe", "bytes": 1, "sha256": "a" * 64, "tipo": "exe"},
    )
    monkeypatch.setattr(sistema, "instalar", lambda **k: {"plano": "driver.exe"})
    executou: list[str] = []
    monkeypatch.setattr(sistema, "executar", lambda **k: executou.append("x") or {})

    with pytest.raises(sistema.SistemaError) as erro:
        sistema.driver_do_celular(fabricante="samsung", confirmado=True)
    assert "confirmação" in str(erro.value)
    assert executou == []          # e não executou nada às cegas


def test_escanear_driver_instala_de_ponta_a_ponta_com_janela_falsa(monkeypatch, capsys):
    """0.95.4 — o caminho que o dono roda: `escanear-celular.bat --driver`.

    A 0.95.4 devolvia o plano de instalação e parava. Aqui a prova é a ponta:
    `instalar` monta, `executar` executa, e a tela final diz o que fazer depois.
    """
    import importlib.util
    from pathlib import Path

    from server import sistema

    monkeypatch.setattr(sistema.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        sistema,
        "baixar",
        lambda **k: {"arquivo": "/tmp/q/driver.exe", "bytes": 34_000_000, "sha256": "b" * 64, "tipo": "exe"},
    )
    monkeypatch.setattr(sistema, "instalar", lambda **k: {"plano": "x", "confirmação": "tok1"})
    executou: list[dict] = []

    def executar(**k):
        executou.append(k)
        return {"estado": "instalado"}

    monkeypatch.setattr(sistema, "executar", executar)

    alvo = Path(__file__).resolve().parents[2] / "escanear-celular.py"
    spec = importlib.util.spec_from_file_location("escanear_mod", alvo)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)

    codigo = modulo.main(["--driver"])
    saida = capsys.readouterr().out
    assert codigo == 0
    assert executou and executou[0]["confirmacao"] == "tok1"
    assert "instalado no PC" in saida
    assert "celular não recebeu nada" in saida
    # e o passo seguinte tem de estar escrito, não subentendido
    assert "desconecte o cabo" in saida


def test_configurar_celular_liga_as_permissoes_do_driver(tmp_path, monkeypatch):
    """O `.bat` não pode depender de o dono digitar `set VAR=1` no prompt."""
    import importlib.util
    from pathlib import Path

    alvo = Path(__file__).resolve().parents[2] / "configurar-celular.py"
    spec = importlib.util.spec_from_file_location("configurar_mod", alvo)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)

    env = tmp_path / ".env"
    monkeypatch.setattr(modulo, "ARQUIVO", env)
    monkeypatch.setattr(modulo, "EXEMPLO", tmp_path / ".env.example")
    env.write_text("JARVIS_ACOES=1\n", encoding="utf-8")

    modulo.ligar_driver()
    modulo.ligar_driver()          # duas vezes: não pode duplicar a linha
    texto = env.read_text(encoding="utf-8")
    assert texto.count("JARVIS_HOST_REDE=1") == 1
    assert texto.count("JARVIS_HOST_INSTALAR=1") == 1
    assert "JARVIS_ACOES=1" in texto   # e não apaga o que o dono já tinha


def test_script_local_nao_pede_token_de_host(monkeypatch):
    """0.95.4 — o `.bat` roda no PC do dono e pedia token de host.

    A tela dele: *“Sem token e este pedido não veio da própria máquina.”* —
    vindo de um `.bat` na própria máquina. O token existe para barrar site de
    fora; um processo do mesmo usuário já lê `storage/host-token.txt`.
    """
    from server import sistema

    monkeypatch.setattr(sistema.platform, "system", lambda: "Windows")
    monkeypatch.delenv("JARVIS_HOST_EXIGIR_TOKEN_LOCAL", raising=False)
    monkeypatch.setenv("JARVIS_HOST_REDE", "1")
    monkeypatch.setenv("JARVIS_HOST_INSTALAR", "1")
    # O `baixar` de verdade chama `_exigir_rede(autorizacao)` e é ELE que
    # levantava o erro na tela do dono. O falso tem de fazer o mesmo, senão o
    # teste passa por não reproduzir o caminho real (foi o que aconteceu na
    # primeira tentativa deste teste).
    def baixar_de_verdade(**k):
        # repassa o `script_local` como o `baixar` real faz
        sistema._exigir_rede(  # noqa: SLF001
            k.get("autorizacao", ""), script_local=k.get("script_local", False)
        )
        return {"arquivo": "/tmp/q/driver.exe", "bytes": 1, "sha256": "c" * 64, "tipo": "exe"}

    monkeypatch.setattr(sistema, "baixar", baixar_de_verdade)
    monkeypatch.setattr(sistema, "instalar", lambda **k: {"confirmação": "tok"})
    monkeypatch.setattr(sistema, "executar", lambda **k: {"estado": "instalado"})

    # autorizacao vazia e SEM token: tem de passar mesmo assim
    feito = sistema.driver_do_celular(fabricante="samsung", confirmado=True, autorizacao="")
    assert feito["instalacao"]["estado"] == "instalado"


def test_quem_pede_token_local_de_volta_continua_tendo(monkeypatch):
    """A trava de quem quer o token até na própria máquina não foi removida."""
    from server import sistema

    monkeypatch.setenv("JARVIS_HOST_EXIGIR_TOKEN_LOCAL", "1")
    assert sistema.da_propria_maquina() is False
    with pytest.raises(sistema.SistemaError):
        sistema._exigir("", script_local=True)  # noqa: SLF001


def test_rede_desligada_explica_que_e_linha_de_env_e_nao_comando(monkeypatch):
    """O dono digitou `JARVIS_HOST_REDE=1` no prompt e o Windows reclamou."""
    from server import sistema

    monkeypatch.delenv("JARVIS_HOST_REDE", raising=False)
    with pytest.raises(sistema.SistemaError) as erro:
        sistema._exigir_rede_ligada()  # noqa: SLF001
    texto = str(erro.value)
    assert ".env" in texto
    assert "não no prompt" in texto


def test_o_plano_do_driver_avisa_que_o_cabo_tem_de_estar_conectado(monkeypatch):
    """0.95.4 — eu tinha escrito “com o celular desconectado”, e é o contrário.

    O instalador da Samsung é da época do Kies: ele reconhece o aparelho plugado.
    Sem o cabo, termina “com sucesso” e não instala a interface de depuração.
    """
    from server import sistema

    monkeypatch.setattr(sistema.platform, "system", lambda: "Windows")
    plano = sistema.driver_do_celular(fabricante="samsung")
    assert "conectado" in plano["antes_de_instalar"].lower()
    assert "desbloqueado" in plano["antes_de_instalar"].lower()


def test_driver_instalado_nao_baixa_de_novo(monkeypatch):
    """0.95.4 — o dono rodou o `.bat` três vezes; 33 MB em cada uma seria absurdo."""
    import importlib.util
    from pathlib import Path

    from server import sistema

    monkeypatch.setattr(sistema.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        sistema, "driver_instalado",
        lambda f="samsung": {"instalado": True, "como_sei": "O Windows lista a interface ADB da Samsung.",
                             "dispositivos": ["SAMSUNG Android ADB Interface"]},
    )

    def nao_pode(*a, **k):
        raise AssertionError("baixou mesmo com o driver já instalado")

    monkeypatch.setattr(sistema, "baixar", nao_pode)
    monkeypatch.setattr(sistema, "driver_do_celular", nao_pode)

    alvo = Path(__file__).resolve().parents[2] / "escanear-celular.py"
    spec = importlib.util.spec_from_file_location("escanear_mod2", alvo)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)

    import io
    from contextlib import redirect_stdout

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        codigo = modulo.main(["--driver"])
    assert codigo == 0
    assert "já está instalado" in buffer.getvalue()
    assert "não baixei nada" in buffer.getvalue()


def test_driver_instalado_nao_confunde_linux(monkeypatch):
    """Fora do Windows não há o que conferir — e ele não pode dizer "instalado"."""
    from server import sistema

    monkeypatch.setattr(sistema.platform, "system", lambda: "Linux")
    estado = sistema.driver_instalado("samsung")
    assert estado["instalado"] is False
    assert "Windows" in estado["como_sei"]


def test_a_api_continua_exigindo_token(monkeypatch):
    """A isenção é do script local — a API nunca pode passar `script_local`.

    0.95.4 — na primeira tentativa eu tirei o token de `_exigir()` para todo
    mundo e derrubei 8 testes: `disco()`, `baixar()`, `instalar()` e `executar()`
    são chamados pela API. Aqui fica preso que, sem `script_local`, o token
    continua sendo cobrado mesmo na própria máquina.
    """
    from server import sistema

    monkeypatch.delenv("JARVIS_HOST_EXIGIR_TOKEN_LOCAL", raising=False)
    with pytest.raises(sistema.SistemaError, match="token"):
        sistema._exigir("")  # noqa: SLF001
    with pytest.raises(sistema.SistemaError, match="token"):
        sistema._exigir("", script_local=False)  # noqa: SLF001 - explícito, igual à API
