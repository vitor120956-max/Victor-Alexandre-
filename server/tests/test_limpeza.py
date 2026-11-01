"""Debloat: tirar o que não se usa, sem quebrar o que se usa.

A pergunta veio com cinco fotos do Gerenciador de Tarefas: *“tem processos que
sempre estão rodando sem funcionalidade ... fazer um debloat do que não usamos e
não é necessário, que só ocupa espaço”*.

O erro clássico de “debloat” é tratar as três origens como uma só. Nas fotos há:

- **Windows de fábrica** (Solitaire, Tempo, Notícias, Xbox overlay, telemetria) —
  sai sem perda;
- **programa que o usuário instalou** (Google Drive, Chrome, Office Click-to-Run,
  WebView2) — não é bloat, é uso;
- **peça de driver** (NVIDIA Container, NVIDIA Web Helper) — já explicado em
  `processos.py`.

Os testes travam o que impede estrago: nada é executado, nada fora do catálogo
recebe palpite, o que é essencial nunca entra como comando ativo no `.bat`, o
plano tem volta, e o texto do script é CRLF com uma linha por comando.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from server import limpeza

RAIZ = Path(__file__).resolve().parents[2]


# ------------------------------------------------------------------ catálogo


def test_o_catalogo_tem_os_tres_vereditos_e_nome_em_todo_item():
    for item in limpeza.APPS:
        assert item["veredito"] in {"sobra", "cuidado", "essencial"}, item
        assert item["nome"] and item["o_que_e"] and item["se_remover"], item


def test_o_que_o_windows_nao_pode_perder_esta_marcado_como_essencial():
    essenciais = {item["chave"] for item in limpeza.APPS if item["veredito"] == "essencial"}
    for chave in ("windowsstore", "vclibs", "sechealthui", "desktopappinstaller"):
        assert chave in essenciais, chave


def test_driver_da_nvidia_aparece_como_cuidado_e_nao_como_sobra():
    servico = next(s for s in limpeza.SERVICOS if s["servico"] == "NvContainerLocalSystem")
    assert servico["veredito"] == "cuidado"
    assert "não desenha nada" in servico["o_que_e"]


def test_nunca_recomenda_apagar_pasta_do_sistema_na_mao():
    """Prefetch e C:\\Windows\\Installer são as duas armadilhas clássicas."""
    armadilhas = {item["id"]: item for item in limpeza.ESPACO
                  if item["id"] in {"prefetch", "winsxs-manual"}}
    assert set(armadilhas) == {"prefetch", "winsxs-manual"}
    for item in armadilhas.values():
        assert item["veredito"] == "essencial"
        assert item["comando"] == ""


# ----------------------------------------------------------------- análise


def test_app_instalado_vira_ficha_e_desconhecido_nao_recebe_palpite():
    dados = limpeza.analisar_apps([
        {"Name": "Microsoft.BingWeather_8wekyb3d8bbwe"},
        {"Name": "Empresa.SistemaDaEmpresa_abc"},
    ])
    nomes = [item["nome"] for item in dados["apps"]]
    assert "MSN Tempo" in nomes
    assert dados["nao_classificados"] == ["Empresa.SistemaDaEmpresa_abc"]
    assert dados["nao_classificados_total"] == 1


def test_a_sobra_soma_so_o_que_e_sobra():
    dados = limpeza.analisar_apps([
        {"Name": "Microsoft.BingWeather_8wekyb3d8bbwe"},          # 60, sobra
        {"Name": "Microsoft.MicrosoftSolitaireCollection_8wekyb3d8bbwe"},  # 220, sobra
        {"Name": "Microsoft.XboxGamingOverlay_8wekyb3d8bbwe"},    # 260, cuidado
    ])
    assert dados["sobras"] == 2
    assert dados["estimado_sobra_mb"] == 280


def test_o_app_que_nao_esta_instalado_nao_aparece():
    dados = limpeza.analisar_apps([{"Name": "Microsoft.WindowsStore_8wekyb3d8bbwe"}])
    assert [item["nome"] for item in dados["apps"]] == ["Microsoft Store"]


def test_servicos_e_tarefas_so_listam_o_que_existe_na_maquina():
    servicos = limpeza.analisar_servicos({"DiagTrack": {"estado": "Running", "inicio": "Auto"}})
    assert [item["servico"] for item in servicos] == ["DiagTrack"]
    tarefas = limpeza.analisar_tarefas({r"\Microsoft\Windows\Autochk\Proxy": "Ready"})
    assert [item["nome"] for item in tarefas] == ["Autochk Proxy"]


def test_servico_de_volta_tem_o_tipo_original():
    """Desfazer com `auto` num serviço que era `manual` muda o boot dele."""
    for item in limpeza.SERVICOS:
        assert item["tipo_volta"] in {"auto", "manual", "disabled"}, item["servico"]
    diag = next(i for i in limpeza.SERVICOS if i["servico"] == "DiagTrack")
    assert diag["tipo_volta"] == "auto"


def test_espaco_mede_so_o_que_existe_e_nunca_inventa_numero():
    medidos = {"lixeira": {"existe": True, "tamanho_mb": 1200.0}}
    fichas = limpeza.analisar_espaco(medidos)
    assert [item["id"] for item in fichas] == ["lixeira"]
    assert fichas[0]["tamanho_mb"] == 1200.0


# --------------------------------------------------------------------- plano


def _plano_com_tudo() -> dict:
    apps = limpeza.analisar_apps([
        {"Name": "Microsoft.BingWeather_8wekyb3d8bbwe"},
        {"Name": "Microsoft.XboxGamingOverlay_8wekyb3d8bbwe"},
        {"Name": "Microsoft.WindowsStore_8wekyb3d8bbwe"},
    ])
    servicos = limpeza.analisar_servicos({
        "DiagTrack": {"estado": "Running", "inicio": "Auto"},
        "NvContainerLocalSystem": {"estado": "Running", "inicio": "Auto"},
    })
    tarefas = limpeza.analisar_tarefas({
        r"\Microsoft\Windows\Application Experience\ProgramDataUpdater": "Ready",
    })
    espaco = limpeza.analisar_espaco({
        "lixeira": {"existe": True, "tamanho_mb": 900.0},
        "win-sxs": {"existe": True, "tamanho_mb": 5000.0},
    })
    return limpeza.plano(apps, servicos, tarefas, espaco)


def test_o_script_comeca_com_seguranca_e_avisa_do_administrador():
    script = _plano_com_tudo()["script"]
    assert script.startswith("@echo off\r\n")
    assert "administrador" in script
    assert script.count("\r\n") >= 10


def test_so_o_que_e_sobra_vira_comando_ativo():
    script = _plano_com_tudo()["script"]
    ativos = "\n".join(
        linha for linha in script.split("\r\n")
        if linha and not linha.startswith(("rem", "echo", "@echo", "title", "pause", "net session", "if %errorlevel%"))
    )
    assert "BingWeather" in ativos          # sobra: comando ativo
    assert "DiagTrack" in ativos            # sobra: comando ativo
    assert "XboxGamingOverlay" not in ativos   # cuidado: só comentado
    assert "NvContainerLocalSystem" not in ativos
    assert "WindowsStore" not in ativos     # essencial: nunca


def test_o_que_e_cuidado_entra_comentado():
    script = _plano_com_tudo()["script"]
    comentadas = [linha for linha in script.split("\r\n") if linha.startswith("rem ")]
    juntas = "\n".join(comentadas)
    assert "XboxGamingOverlay" in juntas
    assert "sc config NvContainerLocalSystem" in juntas
    assert "Dism.exe /Online /Cleanup-Image /StartComponentCleanup /ResetBase" in juntas


def test_o_espaco_essencial_nunca_aparece_no_script():
    apps = limpeza.analisar_apps([])
    espaco = limpeza.analisar_espaco({
        "prefetch": {"existe": True, "tamanho_mb": 10.0},
        "winsxs-manual": {"existe": True, "tamanho_mb": 3000.0},
    })
    script = limpeza.plano(apps, [], [], espaco)["script"]
    assert "Prefetch" not in script
    assert "Windows\\Installer" not in script.replace(r"\\", "\\")


def test_o_plano_tem_volta_para_servico_e_tarefa():
    plano = _plano_com_tudo()
    restaurar = plano["restaurar"]
    assert "sc config DiagTrack start= auto" in restaurar
    assert "schtasks /Change /TN" in restaurar and "/ENABLE" in restaurar
    assert restaurar.startswith("@echo off\r\n")


def test_o_resumo_conta_o_que_da_para_tirar():
    plano = _plano_com_tudo()
    assert "app de loja" in plano["resumo"]
    assert "tarefa" in plano["resumo"] or "serviço" in plano["resumo"]


def test_sem_nada_instalado_o_resumo_diz_que_nao_ha_o_que_tirar():
    plano = limpeza.plano(limpeza.analisar_apps([]), [], [], [])
    assert "Nada para tirar" in plano["resumo"]
    assert "Nada a restaurar" in plano["restaurar"]


def test_o_aviso_diz_que_nada_foi_executado():
    assert "Nada foi executado" in _plano_com_tudo()["aviso"]


# ----------------------------------------------------------------- travas


def test_o_modulo_nao_executa_remove_appxpackage():
    """O comando aparece no texto do plano; nunca é passado para o PowerShell."""
    codigo = RAIZ.joinpath("server/limpeza.py").read_text(encoding="utf-8")
    assert codigo.count("subprocess.run") == 1, "só a função _ps pode chamar subprocess"
    for linha in codigo.splitlines():
        if "Remove-AppxPackage" in linha or "sc config " in linha or "schtasks /Change" in linha:
            assert "subprocess" not in linha, linha
    assert "shell=True" not in codigo
    assert "os.system" not in codigo


def test_fora_do_windows_explica_em_vez_de_fingir(monkeypatch):
    monkeypatch.setattr(limpeza.platform, "system", lambda: "Linux")
    dados = limpeza.relatorio()
    assert dados["lido"] is False
    assert "Windows" in dados["motivo"]
    assert "plano" not in dados


def test_a_medicao_de_pasta_e_opt_in(monkeypatch):
    """Medir WinSxS leva minutos: o padrão confere existência, não soma bytes."""
    chamadas: list[str] = []

    def falso_existe(caminho, timeout=20):
        chamadas.append(caminho)
        return "WinSxS" in caminho

    monkeypatch.setattr(limpeza, "pasta_existe", falso_existe)
    monkeypatch.setattr(limpeza, "medir_pasta", lambda *a, **k: pytest.fail("não devia medir"))
    medido = limpeza.medir_pastas(medir=False)
    assert medido["win-sxs"] == {"existe": True, "tamanho_mb": None}
    assert len(chamadas) == len([i for i in limpeza.ESPACO if i["caminho"]])


def test_a_variavel_de_ambiente_e_traduzida_para_powershell():
    assert limpeza._ps_caminho(r"%LOCALAPPDATA%\Temp") == r"$env:LOCALAPPDATA\Temp"


# ----------------------------------------------------------------- registro


def test_as_skills_de_leitura_da_maquina_nao_tem_efeito():
    """As de leitura nunca mexem; quem executa é `arrumar`/`desfazer` (0.72.0)."""
    from server.skill_registry import build_registry

    registro = build_registry(RAIZ)
    leitura = {"maquina.processos", "maquina.portatil", "maquina.plano",
               "maquina.debloat", "maquina.limpar"}
    ids = {s["id"] for s in registro.list() if s["category"] == "Máquina"}
    assert leitura <= ids
    for identificador in leitura:
        assert registro.get(identificador).side_effects is False, identificador
    for identificador in ("maquina.arrumar", "maquina.desfazer"):
        assert registro.get(identificador).side_effects is True, identificador
