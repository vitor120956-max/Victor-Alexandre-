"""Os braços: o JARVIS arruma a máquina em vez de mandar você apertar.

O pedido foi literal: *“eu não quero ter que fazer nada, por isso fiz o JARVIS
com braços”*. Até a 0.73.0 ele diagnosticava e entregava um `.bat` — relatório.
Agora `maquina.arrumar` executa.

O que estes testes travam, e por quê:

- **só `sobra` executa.** Driver (NVIDIA Container), `essencial` (Store, VCLibs,
  Segurança) e `cuidado` (Xbox, WinSxS, hibernação) nunca viram comando. Se alguém
  afrouxar isso no futuro, o teste quebra antes do usuário;
- **identidade antes do PID.** O plano guarda o PID, mas na hora de matar ele
  confere se aquele PID ainda é o mesmo processo e continua sendo sobra — PID é
  reciclado pelo Windows e matar por número antigo é o erro que fecha programa
  alheio;
- **travas**: `JARVIS_HOST_ARRUMAR=1`, token de host e confirmação. Faltando
  qualquer uma, nada roda (e o teste falha se o executor for chamado);
- **diário com volta.** Cada ação bem-sucedida grava comando, saída e desfazer em
  `storage/limpezas/`; `desfazer()` relê o último e reverte o que tem volta;
- **cache só do lixo.** Temp, lixeira, cache de atualização e de entrega. WinSxS,
  `hiberfil.sys` e `Windows.old` ficam de fora, mesmo sendo "sobra" no catálogo.

Nada aqui toca o Windows: o executor é injetado e o sandbox é Linux.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from server import arrumar

RAIZ = Path(__file__).resolve().parents[2]


# ------------------------------------------------------------------ o plano


def test_fora_do_windows_explica_em_vez_de_fingir():
    plano = arrumar.planejar()
    assert plano["lido"] is False
    assert "Windows" in plano["motivo"]
    assert plano["itens"] == []


def test_o_plano_so_tem_sobras(monkeypatch):
    """O catálogo tem 35 apps; só os de veredito 'sobra' podem virar comando."""
    monkeypatch.setattr(arrumar.platform, "system", lambda: "Windows")
    monkeypatch.setattr(arrumar, "_de_processos", lambda: [])
    monkeypatch.setattr(arrumar, "_de_tarefas", lambda ousado=False: [])
    monkeypatch.setattr(arrumar, "_de_servicos", lambda ousado=False: [])
    monkeypatch.setattr(arrumar, "_de_espaco", lambda ousado=False: [])
    monkeypatch.setattr(
        arrumar.limpeza_local,
        "analisar_apps",
        lambda _pacotes: {
            "apps": [
                {"id": "xbox", "nome": "Xbox", "veredito": "cuidado", "pacote": "Microsoft.Xbox", "comando": "cmd-xbox", "desfazer": "volta-xbox", "tamanho_estimado_mb": 260},
                {"id": "bingweather", "nome": "MSN Tempo", "veredito": "sobra", "pacote": "Microsoft.BingWeather", "comando": "cmd-tempo", "desfazer": "volta-tempo", "tamanho_estimado_mb": 60},
                {"id": "windowsstore", "nome": "Microsoft Store", "veredito": "essencial", "pacote": "Microsoft.WindowsStore", "comando": "cmd-store", "desfazer": "", "tamanho_estimado_mb": 90},
            ]
        },
    )
    monkeypatch.setattr(arrumar.limpeza_local, "medir_apps", lambda: [])

    plano = arrumar.planejar()
    assert plano["lido"] is True
    assert [item["nome"] for item in plano["itens"]] == ["MSN Tempo"]
    assert "sobra" in plano["regra"]


def test_o_espaco_automatico_nao_inclui_winsxs_hibernacao_nem_windows_old():
    assert "prefetch" not in arrumar.ESPACO_SEGURO
    assert "winsxs-manual" not in arrumar.ESPACO_SEGURO
    for cuidado in ("win-sxs", "hiberfil", "windows-old"):
        assert cuidado not in arrumar.ESPACO_SEGURO, cuidado
    # e o que é lixo de verdade está lá
    assert {"temp-usuario", "temp-windows", "lixeira", "update-cache"} <= arrumar.ESPACO_SEGURO


def test_o_resumo_do_plano_conta_por_tipo(monkeypatch):
    monkeypatch.setattr(arrumar.platform, "system", lambda: "Windows")
    monkeypatch.setattr(arrumar, "_de_processos", lambda: [arrumar._item("processo", "1:9", "Steam Web Helper", "taskkill /PID 9 /F", "", "320 MB")])
    monkeypatch.setattr(arrumar, "_de_apps", lambda ousado=False: [])
    monkeypatch.setattr(arrumar, "_de_tarefas", lambda ousado=False: [])
    monkeypatch.setattr(arrumar, "_de_servicos", lambda ousado=False: [])
    monkeypatch.setattr(arrumar, "_de_espaco", lambda ousado=False: [])
    plano = arrumar.planejar()
    assert "processo" in plano["resumo"]


# ----------------------------------------------------------------- travas


def _executor_falso(ok=True):
    chamadas: list[str] = []

    def rodar(comando: str):
        chamadas.append(comando)
        return (0 if ok else 1), "ok"

    rodar.chamadas = chamadas  # type: ignore[attr-defined]
    return rodar


def test_sem_a_trava_nao_executa_nada(monkeypatch):
    monkeypatch.delenv(arrumar.AMBIENTE, raising=False)
    rodar = _executor_falso()
    with pytest.raises(arrumar.ArrumarError) as erro:
        arrumar.executar(autorizacao="x", confirmado=True, rodar=rodar)
    assert "JARVIS_HOST_ARRUMAR" in str(erro.value)
    assert rodar.chamadas == []  # type: ignore[attr-defined]


def test_sem_confirmacao_nao_executa(monkeypatch):
    monkeypatch.setenv(arrumar.AMBIENTE, "1")
    from server import sistema

    monkeypatch.setattr(sistema, "autorizado", lambda _texto: (True, ""))
    rodar = _executor_falso()
    with pytest.raises(arrumar.ArrumarError) as erro:
        arrumar.executar(autorizacao="x", confirmado=False, rodar=rodar)
    assert "confirmação" in str(erro.value).lower()
    assert rodar.chamadas == []  # type: ignore[attr-defined]


def test_token_errado_nao_executa(monkeypatch):
    monkeypatch.setenv(arrumar.AMBIENTE, "1")
    from server import sistema

    monkeypatch.setattr(sistema, "autorizado", lambda _texto: (False, "Token errado."))
    rodar = _executor_falso()
    with pytest.raises(arrumar.ArrumarError) as erro:
        arrumar.executar(autorizacao="errado", confirmado=True, rodar=rodar)
    assert "Token errado" in str(erro.value)
    assert rodar.chamadas == []  # type: ignore[attr-defined]


# --------------------------------------------------------------- execução


def _plano_falso(itens):
    return {"lido": True, "itens": itens, "total": len(itens), "resumo": "plano de teste"}


@pytest.fixture
def ambiente_ligado(monkeypatch):
    monkeypatch.setenv(arrumar.AMBIENTE, "1")
    from server import sistema

    monkeypatch.setattr(sistema, "autorizado", lambda texto: (bool(texto), "" if texto else "sem token"))
    monkeypatch.setattr(arrumar.platform, "system", lambda: "Windows")
    return monkeypatch


def test_executa_o_que_esta_no_plano_e_grava_o_diario(ambiente_ligado, tmp_path):
    rodar = _executor_falso(ok=True)
    plano = _plano_falso([
        arrumar._item("app", "bingweather", "MSN Tempo", "cmd-tempo", "volta-tempo", "~60 MB"),
        arrumar._item("tarefa", "Proxy", "Autochk Proxy", "schtasks /Change /TN x /DISABLE", "schtasks /Change /TN x /ENABLE"),
    ])
    resultado = arrumar.executar(autorizacao="token", plano=plano, confirmado=True,
                                 rodar=rodar, raiz_diario=tmp_path, agora=datetime(2026, 11, 1, 10, 0, 0))
    assert resultado["executado"] is True
    assert resultado["feitas"] == 2 and resultado["falhas"] == 0
    assert rodar.chamadas == ["cmd-tempo", "schtasks /Change /TN x /DISABLE"]  # type: ignore[attr-defined]
    diario = Path(resultado["diario"])
    assert diario.is_file()
    salvo = json.loads(diario.read_text(encoding="utf-8"))
    assert salvo["quando"] == "2026-11-01T10:00:00"
    assert [a["nome"] for a in salvo["acoes"]] == ["MSN Tempo", "Autochk Proxy"]
    assert salvo["acoes"][0]["desfazer"] == "volta-tempo"


def test_falha_em_uma_acao_nao_impede_as_outras(ambiente_ligado, tmp_path):
    def rodar(comando: str):
        return (1, "acesso negado") if "app" in comando else (0, "ok")

    plano = _plano_falso([
        arrumar._item("app", "a", "App", "cmd-app", "volta"),
        arrumar._item("tarefa", "b", "Tarefa", "cmd-tarefa", "volta2"),
    ])
    resultado = arrumar.executar(autorizacao="token", plano=plano, confirmado=True,
                                 rodar=rodar, raiz_diario=tmp_path)
    assert resultado["feitas"] == 1 and resultado["falhas"] == 1
    assert "administrador" in resultado["resumo"]


def test_processo_com_pid_que_mudou_e_pulado(ambiente_ligado, tmp_path, monkeypatch):
    """PID reciclado: matar por número antigo fecharia outro programa."""
    from server import processos

    # O processo sumiu: a lista agora tem outro PID com o mesmo número ocupado.
    monkeypatch.setattr(processos, "coletar", lambda limite=600: [{"nome": "outro", "pid": 9, "memoria_mb": 10}])
    rodar = _executor_falso()
    item = arrumar._item("processo", "Steam Web Helper:9", "Steam Web Helper",
                         "taskkill /PID 9 /F", "", "300 MB", {"pid": 9, "processo": "steamwebhelper"})
    resultado = arrumar.executar(autorizacao="token", plano=_plano_falso([item]), confirmado=True,
                                 rodar=rodar, raiz_diario=tmp_path)
    assert rodar.chamadas == []  # type: ignore[attr-defined]
    assert resultado["acoes"][0]["ok"] is False
    assert "PID mudou" in resultado["acoes"][0]["saida"] or "já saiu" in resultado["acoes"][0]["saida"]


def test_processo_que_continua_sendo_sobra_e_encerrado(ambiente_ligado, tmp_path, monkeypatch):
    from server import processos

    monkeypatch.setattr(
        processos, "coletar",
        lambda limite=600: [{"nome": "steamwebhelper", "pid": 9, "memoria_mb": 300}],
    )
    rodar = _executor_falso()
    item = arrumar._item("processo", "Steam Web Helper:9", "Steam Web Helper",
                         "taskkill /PID 9 /F", "", "300 MB", {"pid": 9, "processo": "steamwebhelper"})
    resultado = arrumar.executar(autorizacao="token", plano=_plano_falso([item]), confirmado=True,
                                 rodar=rodar, raiz_diario=tmp_path)
    assert rodar.chamadas == ["taskkill /PID 9 /F"]  # type: ignore[attr-defined]
    assert resultado["feitas"] == 1
    assert "MB de RAM" in resultado["resumo"]


def test_plano_vazio_nao_grava_diario_mentiroso(ambiente_ligado, tmp_path):
    resultado = arrumar.executar(autorizacao="token", plano=_plano_falso([]), confirmado=True,
                                 rodar=_executor_falso(), raiz_diario=tmp_path)
    assert resultado["resumo"] == "Não havia nada para arrumar."
    assert list(tmp_path.glob("*.json")) == []


# ------------------------------------------------ foto de antes + ponto


def test_o_instantaneo_guarda_apps_servicos_e_tarefas(monkeypatch, tmp_path):
    monkeypatch.setattr(arrumar.platform, "system", lambda: "Windows")
    monkeypatch.setattr(arrumar.limpeza_local, "medir_apps",
                        lambda: [{"Name": "Microsoft.BingWeather_8wekyb3d8bbwe", "PackageFullName": "full"}])
    monkeypatch.setattr(arrumar.limpeza_local, "medir_servicos",
                        lambda: {"DiagTrack": {"estado": "Running", "inicio": "Auto"}})
    monkeypatch.setattr(arrumar.limpeza_local, "medir_tarefas",
                        lambda: {r"\Microsoft\Windows\Autochk\Proxy": "Ready"})
    foto = arrumar.instantaneo()
    assert foto["lido"] is True
    assert foto["apps"][0]["nome"].startswith("Microsoft.BingWeather")
    assert foto["servicos"]["DiagTrack"]["inicio"] == "Auto"
    assert "app" in foto["resumo"]

    caminho = arrumar.gravar_instantaneo(foto, raiz=tmp_path)
    assert caminho and Path(caminho).is_file()
    salvo = json.loads(Path(caminho).read_text(encoding="utf-8"))
    assert salvo["tarefas"][r"\Microsoft\Windows\Autochk\Proxy"] == "Ready"


def test_o_instantaneo_e_pequeno_nao_e_backup_do_windows(monkeypatch, tmp_path):
    """O ponto é ser KB: lista de estado, não cópia de 20 GB."""
    monkeypatch.setattr(arrumar.platform, "system", lambda: "Windows")
    monkeypatch.setattr(arrumar.limpeza_local, "medir_apps", lambda: [])
    monkeypatch.setattr(arrumar.limpeza_local, "medir_servicos", lambda: {})
    monkeypatch.setattr(arrumar.limpeza_local, "medir_tarefas", lambda: {})
    caminho = arrumar.gravar_instantaneo(raiz=tmp_path)
    assert Path(caminho).stat().st_size < 4096


def test_fora_do_windows_o_instantaneo_e_o_ponto_dizem_por_que():
    assert arrumar.instantaneo()["lido"] is False
    assert arrumar.ponto_de_restauracao()["criado"] is False
    assert "Windows" in arrumar.ponto_de_restauracao()["motivo"]


def test_ponto_de_restauracao_relata_falha_sem_derrubar(monkeypatch):
    monkeypatch.setattr(arrumar.platform, "system", lambda: "Windows")
    resultado = arrumar.ponto_de_restauracao(lambda script: (1, "Proteção do Sistema desligada"))
    assert resultado["criado"] is False
    assert "Proteção do Sistema" in resultado["motivo"]
    assert "instantâneo" in resultado["motivo"]


def test_ponto_de_restauracao_confirma_quando_o_windows_diz_criado(monkeypatch):
    monkeypatch.setattr(arrumar.platform, "system", lambda: "Windows")
    resultado = arrumar.ponto_de_restauracao(lambda script: (0, "criado"))
    assert resultado["criado"] is True


def test_executar_grava_instantaneo_e_ponto_no_diario(ambiente_ligado, tmp_path):
    plano = _plano_falso([arrumar._item("app", "bing", "MSN Tempo", "cmd-app", "volta")])
    resultado = arrumar.executar(
        autorizacao="token", plano=plano, confirmado=True,
        rodar=_executor_falso(), raiz_diario=tmp_path,
        ponto=lambda: {"criado": True, "motivo": ""},
        foto={"lido": True, "apps": [{"nome": "X"}], "servicos": {}, "tarefas": {}, "resumo": "1 app"},
    )
    assert Path(resultado["instantaneo"]).is_file()
    assert resultado["ponto_de_restauracao"]["criado"] is True
    assert "rstrui" in resultado["como_voltar_tudo"]
    diario = json.loads(Path(resultado["diario"]).read_text(encoding="utf-8"))
    assert diario["ponto_de_restauracao"]["criado"] is True
    assert diario["instantaneo"] == resultado["instantaneo"]


def test_sem_ponto_o_relatorio_aponta_o_instantaneo(ambiente_ligado, tmp_path):
    plano = _plano_falso([arrumar._item("app", "x", "App", "cmd", "volta")])
    resultado = arrumar.executar(
        autorizacao="token", plano=plano, confirmado=True, rodar=_executor_falso(),
        raiz_diario=tmp_path, ponto=False, foto={"lido": True, "apps": [], "servicos": {}, "tarefas": []},
    )
    assert resultado["ponto_de_restauracao"]["criado"] is False
    assert "maquina.desfazer" in resultado["como_voltar_tudo"]


# ---------------------------------------------------------------- modo ousado


def test_modo_ousado_traz_o_cuidado_que_tem_volta(monkeypatch):
    monkeypatch.setattr(arrumar.platform, "system", lambda: "Windows")
    monkeypatch.setattr(arrumar, "_de_processos", lambda: [])
    monkeypatch.setattr(arrumar, "_de_tarefas", lambda ousado=False: [])
    monkeypatch.setattr(arrumar, "_de_servicos", lambda ousado=False: [])
    monkeypatch.setattr(arrumar, "_de_espaco", lambda ousado=False: [])
    monkeypatch.setattr(arrumar.limpeza_local, "medir_apps", lambda: [])
    monkeypatch.setattr(
        arrumar.limpeza_local, "analisar_apps",
        lambda _p: {"apps": [
            {"id": "xbox", "nome": "Xbox", "veredito": "cuidado", "pacote": "P", "comando": "c", "desfazer": "d", "tamanho_estimado_mb": 260},
            {"id": "store", "nome": "Store", "veredito": "essencial", "pacote": "S", "comando": "c2", "desfazer": "", "tamanho_estimado_mb": 90},
        ]},
    )
    assert [i["nome"] for i in arrumar.planejar(ousado=False)["itens"]] == []
    assert [i["nome"] for i in arrumar.planejar(ousado=True)["itens"]] == ["Xbox"]


def test_hibernacao_entra_so_no_ousado_e_winsxs_nunca():
    assert "hiberfil" in arrumar.ESPACO_OUSADO
    assert "hiberfil" not in arrumar.ESPACO_SEGURO
    para_nunca = {"win-sxs", "windows-old", "winsxs-manual", "prefetch"}
    assert para_nunca.isdisjoint(arrumar.ESPACO_SEGURO | arrumar.ESPACO_OUSADO)


def test_o_plano_marca_quando_e_ousado():
    from server import arrumar as mod

    plano = mod.planejar(ousado=True)
    if plano.get("lido"):
        assert plano["ousado"] is True


# --------------------------------------------------------------- desfazer


def test_desfazer_reverte_servico_e_tarefa_do_ultimo_diario(ambiente_ligado, tmp_path):
    plano = _plano_falso([
        arrumar._item("servico", "DiagTrack", "Telemetria", "sc config DiagTrack start= disabled", "sc config DiagTrack start= auto && net start DiagTrack"),
        arrumar._item("espaco", "lixeira", "Lixeira", "Clear-RecycleBin", ""),
    ])
    arrumar.executar(autorizacao="token", plano=plano, confirmado=True,
                     rodar=_executor_falso(), raiz_diario=tmp_path)
    rodar = _executor_falso()
    resultado = arrumar.desfazer(autorizacao="token", confirmado=True, rodar=rodar, raiz_diario=tmp_path)
    assert resultado["desfeito"] is True
    assert rodar.chamadas == ["sc config DiagTrack start= auto && net start DiagTrack"]  # type: ignore[attr-defined]
    assert resultado["sem_volta"] == ["Lixeira"]
    assert "Lixeira" not in resultado["resumo"]


def test_desfazer_sem_diario_avisa_sem_quebrar(ambiente_ligado, tmp_path):
    resultado = arrumar.desfazer(autorizacao="token", confirmado=True, rodar=_executor_falso(), raiz_diario=tmp_path)
    assert resultado["desfeito"] is False
    assert "não há diário" in resultado["motivo"].lower()


def test_desfazer_exige_confirmacao(ambiente_ligado, tmp_path):
    with pytest.raises(arrumar.ArrumarError):
        arrumar.desfazer(autorizacao="token", confirmado=False, rodar=_executor_falso(), raiz_diario=tmp_path)


def test_desfazer_pega_o_diario_mais_novo(ambiente_ligado, tmp_path):
    for dia, comando in ((1, "desfazer-dia-1"), (2, "desfazer-dia-2")):
        plano = _plano_falso([arrumar._item("tarefa", f"t{dia}", f"Tarefa {dia}", f"fazer-{dia}", comando)])
        arrumar.executar(autorizacao="token", plano=plano, confirmado=True, rodar=_executor_falso(),
                         raiz_diario=tmp_path, agora=datetime(2026, 11, dia, 9, 0, 0))
    rodar = _executor_falso()
    arrumar.desfazer(autorizacao="token", confirmado=True, rodar=rodar, raiz_diario=tmp_path)
    assert rodar.chamadas == ["desfazer-dia-2"]  # type: ignore[attr-defined]


# ------------------------------------------------------------- registro


def test_as_duas_skills_de_braco_estao_no_registro_com_efeito_e_confirmacao():
    from server.skill_registry import build_registry

    registro = build_registry(RAIZ)
    for identificador in ("maquina.arrumar", "maquina.desfazer"):
        definicao = registro.get(identificador)
        assert definicao.side_effects is True, identificador
        assert definicao.requires_confirmation is True, identificador


# --------------------------------------------------------- os dois .bat


def test_arrumar_pc_bat_e_ascii_crlf_com_goto_consistente():
    import re

    bruto = (RAIZ / "arrumar-pc.bat").read_bytes()
    assert [b for b in bruto if b > 127] == []
    assert bruto.count(b"\n") == bruto.count(b"\r\n")
    texto = bruto.decode("ascii")
    rotulos = set(re.findall(r"^:([A-Za-z_]\w*)", texto, flags=re.MULTILINE))
    destinos = set(re.findall(r"goto\s+([A-Za-z_]\w*)", texto, flags=re.IGNORECASE))
    assert destinos - rotulos == set()


def test_arrumar_pc_bat_liga_a_trava_so_para_ele():
    texto = (RAIZ / "arrumar-pc.bat").read_text(encoding="ascii")
    assert "set JARVIS_HOST_ARRUMAR=1" in texto
    assert "permite" not in texto.lower()


def test_arrumar_pc_bat_pede_confirmacao_antes_de_aplicar():
    texto = (RAIZ / "arrumar-pc.bat").read_bytes().decode("ascii")
    i_plano = texto.index("%PYEXE% -m server.arrumar ")
    i_pausa = texto.index("pause", i_plano)
    i_aplicar = texto.index("--aplicar --sim")
    assert i_plano < i_pausa < i_aplicar, "o plano tem que vir antes do sim"


def test_arrumar_pc_bat_diz_o_que_nao_toca():
    texto = (RAIZ / "arrumar-pc.bat").read_text(encoding="ascii")
    for proibido in ("NVIDIA Container", "Microsoft Store", "WinSxS", "Installer"):
        assert proibido in texto, proibido


def test_desfazer_limpeza_bat_existe_e_chama_o_modulo():
    bruto = (RAIZ / "desfazer-limpeza.bat").read_bytes()
    assert [b for b in bruto if b > 127] == []
    texto = bruto.decode("ascii")
    assert "-m server.arrumar --desfazer" in texto


def test_iniciar_jarvis_liga_os_bracos_sem_depender_do_env():
    texto = (RAIZ / "iniciar-jarvis.bat").read_text(encoding="ascii")
    assert "if not defined JARVIS_HOST_ARRUMAR set JARVIS_HOST_ARRUMAR=1" in texto


def test_o_modulo_nunca_executa_comando_fora_da_windows():
    """Fora do Windows a função recusa — em vez de rodar `cmd /c` num Linux."""
    with pytest.raises(arrumar.ArrumarError):
        arrumar.rodar_comando("del /q *")


# ------------------------------------------- por que falhou (o caso de 01/11)

def test_causa_traduz_a_saida_do_windows():
    """O usuário recebeu “13 falharam — o diário diz qual”. O motivo era um só."""
    assert arrumar._causa_da_falha("ERRO: Acesso negado.") == "admin"
    assert arrumar._causa_da_falha("Access is denied.") == "admin"
    assert arrumar._causa_da_falha("O sistema não pôde encontrar o caminho especificado.") == "sumiu"
    assert arrumar._causa_da_falha("The system cannot find the file specified.") == "sumiu"
    assert arrumar._causa_da_falha("timeout ao rodar") == "tempo"
    assert arrumar._causa_da_falha("O serviço não está em execução.") == "parado"
    assert arrumar._causa_da_falha("algo estranho") == "outro"
    assert arrumar._causa_da_falha("") == "outro"


def test_falha_de_admin_vem_nomeada_no_relatorio(ambiente_ligado, tmp_path):
    """13 falhas por acesso negado saem contadas, com o que fazer em seguida."""
    plano = _plano_falso([
        arrumar._item("tarefa", "a", "Tarefa A", "schtasks /Change /TN a /DISABLE", "volta"),
        arrumar._item("servico", "b", "Serviço B", "sc config b start= disabled", "volta"),
        arrumar._item("espaco", "temp", "Temp", "cmd /c del /q x", ""),
    ])
    resultado = arrumar.executar(
        autorizacao="token", plano=plano, confirmado=True, raiz_diario=tmp_path,
        rodar=lambda comando: (0, "ok") if comando.startswith("cmd /c") else (1, "ERRO: Acesso negado."),
    )
    assert resultado["feitas"] == 1 and resultado["falhas"] == 2
    assert resultado["falhas_por_causa"] == {"admin": 2}
    assert [item["tipo"] for item in resultado["nao_feitas"]] == ["tarefa", "servico"]
    assert all(item["causa"] == "admin" for item in resultado["nao_feitas"])
    assert "Executar como administrador" in resultado["como_resolver"]
    assert "2 por falta de administrador" in resultado["resumo"]
    # Nada de "veja o diário": a resposta já diz o motivo e o próximo passo.
    assert "o diário diz qual" not in resultado["resumo"]


def test_o_diario_guarda_a_causa_de_cada_falha(ambiente_ligado, tmp_path):
    plano = _plano_falso([
        arrumar._item("tarefa", "a", "Tarefa A", "schtasks /Change /TN a /DISABLE", "volta"),
    ])
    resultado = arrumar.executar(
        autorizacao="token", plano=plano, confirmado=True, raiz_diario=tmp_path,
        rodar=lambda _comando: (1, "Acesso negado"),
    )
    salvo = json.loads(Path(resultado["diario"]).read_text(encoding="utf-8"))
    assert salvo["acoes"][0]["causa"] == "admin"
    assert "administrador" in salvo["acoes"][0]["motivo"]
    assert salvo["resumo"] == resultado["resumo"]


def test_tudo_falhou_diz_que_nada_funcionou_e_por_que(ambiente_ligado, tmp_path):
    plano = _plano_falso([
        arrumar._item("servico", "a", "A", "sc config a start= disabled", "volta"),
        arrumar._item("tarefa", "b", "B", "schtasks /Change /TN b /DISABLE", "volta"),
    ])
    resultado = arrumar.executar(
        autorizacao="token", plano=plano, confirmado=True, raiz_diario=tmp_path,
        rodar=lambda _comando: (5, "Acesso negado"),
    )
    assert resultado["feitas"] == 0
    assert resultado["resumo"].startswith("Nenhuma das 2 ações funcionou.")
    assert "2 por falta de administrador" in resultado["resumo"]
    assert resultado["nao_feitas"] and resultado["nao_feitas"][0]["motivo"]


def test_o_plano_avisa_antes_que_sem_admin_nao_vai_dar(monkeypatch):
    """O aviso chegou tarde da outra vez: agora vem no plano, antes de executar."""
    monkeypatch.setattr(arrumar.platform, "system", lambda: "Windows")
    monkeypatch.setattr(arrumar, "elevado", lambda: False)
    monkeypatch.setattr(arrumar, "_de_processos", lambda: [])
    monkeypatch.setattr(arrumar, "_de_apps", lambda ousado=False: [])
    monkeypatch.setattr(arrumar, "_de_espaco", lambda ousado=False: [])
    monkeypatch.setattr(arrumar, "_de_tarefas", lambda ousado=False: [
        arrumar._item("tarefa", "a", "A", "schtasks /Change /TN a /DISABLE", "volta"),
    ])
    monkeypatch.setattr(arrumar, "_de_servicos", lambda ousado=False: [
        arrumar._item("servico", "b", "B", "sc config b start= disabled", "volta"),
    ])
    plano = arrumar.planejar()
    assert plano["elevado"] is False
    assert plano["precisam_admin"] == 2
    assert "não está como administrador" in plano["aviso_admin"]
    assert "arrumar-pc.bat" in plano["aviso_admin"]

    # Elevado, o aviso some — não é texto fixo.
    monkeypatch.setattr(arrumar, "elevado", lambda: True)
    elevado = arrumar.planejar()
    assert elevado["elevado"] is True
    assert elevado["aviso_admin"] == ""

    # Fora do Windows não há o que avisar (e `elevado()` devolve None).
    monkeypatch.setattr(arrumar, "elevado", lambda: None)
    assert arrumar.planejar()["aviso_admin"] == ""


def test_plano_vazio_nao_inventa_aviso_de_admin(monkeypatch):
    monkeypatch.setattr(arrumar.platform, "system", lambda: "Windows")
    monkeypatch.setattr(arrumar, "elevado", lambda: False)
    monkeypatch.setattr(arrumar, "_de_processos", lambda: [])
    monkeypatch.setattr(arrumar, "_de_apps", lambda ousado=False: [])
    monkeypatch.setattr(arrumar, "_de_tarefas", lambda ousado=False: [])
    monkeypatch.setattr(arrumar, "_de_servicos", lambda ousado=False: [])
    monkeypatch.setattr(arrumar, "_de_espaco", lambda ousado=False: [])
    plano = arrumar.planejar()
    assert plano["precisam_admin"] == 0
    assert plano["aviso_admin"] == ""


# ------------------------------------------------------------------- elevação
# O JARVIS não pode virar administrador sozinho: o UAC é do usuário. Ele pode
# PEDIR — e é isso que passa a existir aqui.

def test_pedir_administrador_fora_do_windows_nao_pede_nada():
    pedido = arrumar.pedir_administrador(executar=lambda _alvo: (_ for _ in ()).throw(AssertionError("não devia chamar")))
    assert pedido["pedido"] is False
    assert pedido["ja_elevado"] is None
    assert pedido["aceito"] is False
    assert "Windows" in pedido["motivo"]


def test_quem_ja_e_administrador_nao_reabre(monkeypatch, tmp_path):
    monkeypatch.setattr(arrumar.platform, "system", lambda: "Windows")
    monkeypatch.setattr(arrumar, "elevado", lambda: True)
    pedido = arrumar.pedir_administrador(
        projeto=tmp_path,
        executar=lambda _alvo: (_ for _ in ()).throw(AssertionError("não devia pedir")),
    )
    assert pedido["ja_elevado"] is True and pedido["pedido"] is False
    assert not (tmp_path / "storage" / arrumar.NOME_BAT_ELEVAR).exists()


def test_pedir_administrador_escreve_o_auxiliar_ascii_e_espera_a_api_morrer(monkeypatch, tmp_path):
    monkeypatch.setattr(arrumar.platform, "system", lambda: "Windows")
    monkeypatch.setattr(arrumar, "elevado", lambda: False)
    pedido = arrumar.pedir_administrador(projeto=tmp_path, executar=lambda _alvo: 42)
    assert pedido["pedido"] is True and pedido["aceito"] is True
    bruto = (tmp_path / "storage" / arrumar.NOME_BAT_ELEVAR).read_bytes()
    assert [b for b in bruto if b > 127] == []          # ASCII: o console antigo embaralha acento
    assert bruto.count(b"\n") == bruto.count(b"\r\n")   # CRLF: .bat com LF quebra no cmd
    texto = bruto.decode("ascii")
    # Para a instância antiga (senão a porta 8000 fica presa) e só então sobe.
    assert "-m server.instancia --parar --sim" in texto
    assert texto.index("--parar") < texto.index('start "" "iniciar-jarvis.bat"')
    # E espera: quem está respondendo o pedido é a API que vai morrer.
    assert texto.index("timeout /t 4") < texto.index("--parar")
    assert 'cd /d "%~dp0.."' in texto  # o auxiliar mora em storage/


def test_recusa_no_uac_nao_vira_sucesso(monkeypatch, tmp_path):
    """Clicar “Não” no Windows tem que aparecer como recusa, não como feito."""
    monkeypatch.setattr(arrumar.platform, "system", lambda: "Windows")
    monkeypatch.setattr(arrumar, "elevado", lambda: False)
    pedido = arrumar.pedir_administrador(projeto=tmp_path, executar=lambda _alvo: 5)
    assert pedido["aceito"] is False
    assert "Não" in pedido["motivo"]
    assert "Nada foi reiniciado" in pedido["motivo"]


def test_codigo_estranho_explica_o_plano_b(monkeypatch, tmp_path):
    monkeypatch.setattr(arrumar.platform, "system", lambda: "Windows")
    monkeypatch.setattr(arrumar, "elevado", lambda: False)
    pedido = arrumar.pedir_administrador(projeto=tmp_path, executar=lambda _alvo: 31)
    assert pedido["aceito"] is False
    assert "arrumar-pc.bat" in pedido["motivo"]
    assert "31" in pedido["motivo"]


def test_a_skill_de_administrador_existe_com_confirmacao():
    from pathlib import Path as _Path

    from server.skill_registry import build_registry

    reg = build_registry(_Path("."))
    skill = reg.get("maquina.administrador")
    assert skill.side_effects is True
    assert skill.requires_confirmation is True


def test_os_dois_bats_se_elevam_sozinhos():
    """Duplo clique basta: sem `net session` o usuário teria que achar o menu."""
    for nome in ("arrumar-pc.bat", "desfazer-limpeza.bat"):
        bruto = (RAIZ / nome).read_bytes()
        assert [b for b in bruto if b > 127] == [], nome
        assert bruto.count(b"\n") == bruto.count(b"\r\n"), nome
        texto = bruto.decode("ascii")
        assert "net session" in texto, nome
        assert "-Verb RunAs" in texto, nome
        assert "%errorlevel" not in texto, nome  # errorlevel sem %%, não i
        assert "goto ja_admin" in texto and ":ja_admin" in texto, nome
    # O .bat da limpeza continua pedindo o plano antes de aplicar, agora elevado.
    texto = (RAIZ / "arrumar-pc.bat").read_text(encoding="ascii")
    assert texto.index("net session") < texto.index("%PYEXE% -m server.arrumar ")
