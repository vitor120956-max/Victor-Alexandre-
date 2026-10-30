"""O que está rodando no PC e o que cabe no pendrive.

Duas perguntas do usuário, e as duas têm resposta melhor que "pode fechar":

1. *"no gerenciador de tarefas tem algumas coisas abertas que não precisam, tipo o
   nvidia container"* — cada processo recebe um veredito (essencial, driver,
   sobra, cuidado), o que se perde ao parar e como desfazer. O NVIDIA Container é
   o caso central: **não desenha nada**, então fechar não melhora imagem nem FPS —
   devolve RAM e tira painel, ShadowPlay e checagem de driver.

2. *"tem mais melhorias, plugins e drivers que dá para deixar no pendrive?"* —
   ferramenta portátil sim; driver **não**. Driver não é arquivo que se carrega:
   instala-se no Windows, vira serviço e pede reinício. O catálogo só lista o que
   roda do pendrive, e o que não pode ser portátil fica listado com o motivo.

O que os testes travam: nenhum processo é fechado (o módulo só lê), processo
desconhecido **não** recebe palpite, e o catálogo não aceita item que exija
instalação.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from server import portatil, processos

RAIZ = Path(__file__).resolve().parents[2]


def _linhas(**memorias: float) -> list[dict]:
    return [{"nome": nome.replace("_", " "), "pid": i, "memoria_mb": mb}
            for i, (nome, mb) in enumerate(memorias.items(), start=100)]


# ------------------------------------------------------------------ processos


def test_nvidia_container_nao_e_essencial_e_tem_explicacao():
    """É a pergunta original: fechar melhora o quê?"""
    ficha = processos.conhecer("nvcontainer")
    assert ficha is not None
    assert ficha["veredito"] == "driver"
    assert "não" in ficha["se_parar"] or "nao" in ficha["se_parar"]
    assert "painel" in ficha["se_parar"]
    assert ficha["como_parar"].startswith("taskkill")
    assert ficha["como_desfazer"]


def test_nvidia_nunca_promete_fps_ou_imagem():
    """Prometer ganho de FPS ao fechar o container seria mentira."""
    dados = processos.nvidia()
    texto = dados["resposta"].lower()
    assert "não aumenta fps" in texto or "nao aumenta fps" in texto
    assert "nenhuma" not in texto
    assert dados["para_nao_voltar"]


def test_essencial_nunca_aparece_como_sobra():
    for nome in ("lsass", "csrss", "winlogon", "svchost", "explorer", "dwm"):
        ficha = processos.conhecer(nome)
        assert ficha and ficha["veredito"] == "essencial", nome
        assert ficha["se_parar"], nome


def test_processo_desconhecido_nao_recebe_palpite():
    dados = processos.analisar(_linhas(coisaminha=33.0))
    assert dados["ganho_sobra_mb"] == 0
    assert [item["nome"] for item in dados["desconhecidos"]] == ["coisaminha"]


def test_analise_soma_memoria_e_separa_grupos():
    dados = processos.analisar(
        _linhas(steamwebhelper=320.0, nvcontainer=96.0, explorer=120.0, python=180.0)
    )
    assert dados["memoria_total_mb"] == pytest.approx(716.0)
    assert dados["ganho_sobra_mb"] == pytest.approx(320.0)
    assert dados["ganho_driver_mb"] == pytest.approx(96.0)
    assert dados["grupos"]["essencial"][0]["nome"] == "Explorer"
    assert dados["grupos"]["proprio"][0]["nome"].startswith("Python")


def test_sobras_vem_ordenadas_da_maior_para_a_menor():
    dados = processos.analisar(_linhas(searchui=88.0, steamwebhelper=320.0, onedrive=200.0))
    tamanhos = [item["memoria_mb"] for item in dados["grupos"]["sobra"]]
    assert tamanhos == sorted(tamanhos, reverse=True)


def test_resumo_diz_o_ganho_e_nomeia_os_maiores():
    dados = processos.analisar(_linhas(steamwebhelper=320.0, searchui=88.0))
    assert "MB" in dados["resumo"]
    assert "Steam Web Helper" in dados["resumo"]


def test_o_relatorio_avisa_que_nada_foi_fechado():
    dados = processos.analisar(_linhas(steamwebhelper=320.0))
    assert "Nada foi fechado" in dados["aviso"]
    assert "comando" in dados["aviso"]


def test_o_modulo_nao_tem_como_matar_processo():
    """Só leitura: sem taskkill/Stop-Process no código, só na explicação do usuário."""
    codigo = RAIZ.joinpath("server/processos.py").read_text(encoding="utf-8")
    codigo_sem_texto = "\n".join(
        linha for linha in codigo.splitlines()
        if "taskkill" not in linha and "Stop-Process" not in linha
    )
    for proibido in ("os.kill", "TerminateProcess", "Stop-Process -Name"):
        assert proibido not in codigo_sem_texto, proibido


def test_fora_do_windows_explica_em_vez_de_fingir(monkeypatch):
    monkeypatch.setattr(processos.platform, "system", lambda: "Linux")
    dados = processos.relatorio()
    assert dados["lido"] is False
    assert "Windows" in dados["motivo"]


def test_nome_com_caminho_e_exe_e_reconhecido():
    assert processos.conhecer(r"C:\Program Files\NVIDIA\NvContainer.exe")["veredito"] == "driver"
    assert processos.conhecer("NVSPHELPER64")["veredito"] == "sobra"
    assert processos.conhecer("python.exe")["veredito"] == "proprio"


# ------------------------------------------------------------------ portátil


def test_catalogo_tem_licenca_url_e_portabilidade_em_todo_item():
    for item in portatil.FERRAMENTAS:
        assert item["licenca"], item["id"]
        assert item["url"].startswith("https://"), item["id"]
        assert item["portatil"] is True, item["id"]
        assert isinstance(item["tamanho_mb"], int) and item["tamanho_mb"] > 0, item["id"]


def test_catalogo_so_tem_o_que_roda_sem_instalar():
    """Item que exige instalador não entra no pendrive."""
    for item in portatil.FERRAMENTAS:
        assert "install" not in item["url"].lower(), item["id"]
        assert "setup" not in item["url"].lower(), item["id"]


def test_o_que_nao_e_portatil_esta_explicado():
    nomes = " ".join(item["nome"] for item in portatil.NAO_PORTATIL)
    assert "NVIDIA" in nomes
    assert ".NET" in nomes
    assert "Npcap" in nomes
    for item in portatil.NAO_PORTATIL:
        assert len(item["por_que"]) > 30, item["nome"]


def test_driver_de_video_explica_por_que_nao_vai_para_o_pendrive():
    ficha = next(i for i in portatil.NAO_PORTATIL if "NVIDIA" in i["nome"])
    assert "serviço" in ficha["por_que"] or "servico" in ficha["por_que"]
    assert "NVIDIA Container" in ficha["por_que"]


def test_adb_scrcpy_esta_primeiro_no_plano(monkeypatch):
    monkeypatch.setattr(portatil, "medir", lambda: {
        "pasta": "x", "existe": True, "arquivos": 0, "tamanho_mb": 0.0,
        "presentes": [], "faltando": [{"id": f["id"], "nome": f["nome"], "tamanho_mb": f["tamanho_mb"]}
                                       for f in portatil.FERRAMENTAS],
        "espaco_para_tudo_mb": 454, "onde": {"caminho": "D:\\JARVIS", "unidade": "D:", "removivel": True},
    })
    dados = portatil.plano()
    assert dados["etapas"][0]["id"] == "adb-scrcpy"
    assert dados["cabe"] is True
    assert "sistema.baixar" in dados["como_baixar"]


def test_plano_nao_baixa_nada(monkeypatch):
    """A skill de catálogo não pode abrir conexão: baixar é outra skill."""
    codigo = RAIZ.joinpath("server/portatil.py").read_text(encoding="utf-8")
    for proibido in ("urlopen", "requests.get", "subprocess.run", "urllib.request"):
        assert proibido not in codigo, proibido


def test_medir_marca_o_que_ja_existe(tmp_path, monkeypatch):
    pasta = tmp_path / "ferramentas"
    pasta.mkdir()
    (pasta / "scrcpy.exe").write_bytes(b"x" * 10)
    monkeypatch.setattr(portatil, "_raiz_ferramentas", lambda: pasta)
    monkeypatch.setattr(portatil, "_projeto", lambda: tmp_path)
    medido = portatil.medir()
    assert "adb-scrcpy" in medido["presentes"]
    assert medido["arquivos"] == 1


def test_catalogo_marca_presente_e_ausente(tmp_path, monkeypatch):
    monkeypatch.setattr(portatil, "_raiz_ferramentas", lambda: tmp_path)
    monkeypatch.setattr(portatil, "_projeto", lambda: tmp_path)
    dados = portatil.catalogo()
    assert dados["presentes"] == 0
    assert all(item["presente"] is False for item in dados["ferramentas"])
    assert dados["total"] == len(portatil.FERRAMENTAS)


# ------------------------------------------------------------------ registro


def test_as_tres_skills_estao_no_registro_e_nao_tem_efeito():
    from server.skill_registry import build_registry

    registro = build_registry(RAIZ)
    ids = {s["id"] for s in registro.list() if s["category"] == "Máquina"}
    assert ids == {"maquina.processos", "maquina.portatil", "maquina.plano"}
    for identificador in ids:
        assert registro.get(identificador).side_effects is False, identificador
