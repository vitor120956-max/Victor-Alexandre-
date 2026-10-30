"""`acesso-celular.bat` + `.ps1` + `celular.acesso`: o mapa do acesso.

A pergunta que gerou isto: *"eu zerar ele e você não ter acesso ao celular, é o
que a gente estava tentando; se você não tem acesso, como a gente vai mudar o
sistema operacional dele?"* — e ela está certa, no ponto exato.

A resposta honesta: trocar o sistema operacional **também** passa pela porta USB.
No Samsung não existe instalação por cartão SD (o recovery de fábrica só aceita
pacote assinado pela Samsung) e o download mode (Odin) só existe pela porta. Com
os pinos de dados mortos, nenhuma ROM entra — nem stock, nem LineageOS.

Estes testes travam esse mapa e, principalmente, travam a única coisa otimista e
verdadeira dele: **uma solda no conector reabre tudo**, porque o `scrcpy` devolve
teclado e mouse pelo cabo e o mesmo cabo serve ao Odin.
"""
from __future__ import annotations

from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
BAT = RAIZ / "acesso-celular.bat"
PS1 = RAIZ / "acesso-celular.ps1"


def test_os_dois_arquivos_existem_na_raiz():
    assert BAT.is_file()
    assert PS1.is_file()
    assert PS1.parent == (RAIZ / "iniciar.py").parent


def test_sao_ascii_puro_e_crlf():
    for caminho in (BAT, PS1):
        bruto = caminho.read_bytes()
        assert not any(b > 127 for b in bruto), caminho.name
        assert bruto.count(b"\r\n") == bruto.count(b"\n"), caminho.name


def test_script_nao_tem_erro_de_sintaxe_powershell():
    sintaxe = pytest.importorskip("tree_sitter_powershell", reason="parser opcional")
    from tree_sitter import Language, Parser

    arvore = Parser(Language(sintaxe.language())).parse(PS1.read_bytes())
    assert arvore.root_node.has_error is False


# ---------------------------------------------------------------- a conclusão dura


def test_diz_que_trocar_o_sistema_passa_pela_porta_usb():
    texto = PS1.read_text(encoding="utf-8")
    assert "Trocar o sistema operacional passa pela porta USB" in texto
    assert "nenhuma ROM entra" in texto


def test_diz_que_o_cartao_sd_nao_instala_sistema_e_por_que():
    """Era a esperança natural: 'jogo a ROM no cartão'. Não funciona, e não é opinião."""
    texto = PS1.read_text(encoding="utf-8")
    assert "aceita pacote assinado PELA SAMSUNG" in texto
    assert "nao se fabrica em casa" in texto


def test_diz_que_wifi_nao_serve():
    texto = PS1.read_text(encoding="utf-8")
    assert "adb sem fio exige Depuracao USB JA ligada" in texto


def test_nomeia_odin_heimdall_e_twrp():
    texto = PS1.read_text(encoding="utf-8")
    for ferramenta in ("Odin", "Heimdall", "TWRP", "adb sideload"):
        assert ferramenta in texto, ferramenta


# ---------------------------------------------------------------- a saída verdadeira


def test_uma_solda_reabre_tudo_e_explica_o_porque():
    texto = PS1.read_text(encoding="utf-8")
    assert "UMA SOLDA REABRE TUDO" in texto
    assert "devolve TECLADO E MOUSE pelo cabo" in texto
    assert "o digitalizador vira OPCIONAL" in texto


def test_da_a_ordem_exata_depois_do_conserto():
    texto = PS1.read_text(encoding="utf-8")
    # "Odin" também aparece antes, na lista de entradas: a ordem vale na seção.
    inicio = texto.index("A ORDEM, DEPOIS DO CONSERTO")
    secao = texto[inicio:]
    ordem = ["sonda-otg.bat", "teclado-pelo-pc.bat", "Desbloqueio OEM", "Odin", "adb sideload", "LineageOS 18.1"]
    posicoes = [secao.index(item) for item in ordem]
    assert posicoes == sorted(posicoes), posicoes


def test_avisa_que_se_ainda_nao_enumerar_e_o_controlador_usb():
    texto = PS1.read_text(encoding="utf-8")
    assert "controlador USB na" in texto
    assert "bancada, mais caro que o conector" in texto


# ---------------------------------------------------------------- o que não existe


def test_diz_que_dex_nao_existe_neste_modelo():
    texto = PS1.read_text(encoding="utf-8")
    assert "DeX nao existe neste modelo" in texto
    assert "USB-C com" in texto


def test_diz_que_mhl_nao_funciona_e_que_foi_confirmado_pela_samsung():
    texto = PS1.read_text(encoding="utf-8")
    assert "MHL nao e" in texto
    assert "a Samsung confirma" in texto


# ---------------------------------------------------------------- o técnico


def test_ensina_a_nao_aceitar_teste_so_de_carga():
    """Carga são dois pinos; dados são outros dois. Técnico ruim confunde."""
    texto = PS1.read_text(encoding="utf-8")
    assert "nao aceito teste so com" in texto
    assert "carga e dois pinos; dados sao outros dois" in texto


def test_diz_a_peca_exata_para_nao_ser_trocada_por_outra():
    texto = PS1.read_text(encoding="utf-8")
    assert "SM-G610 / on7xelte" in texto
    assert "com solda em bancada" in texto


# ---------------------------------------------------------------- a skill


def test_a_skill_existe_e_nao_tem_efeito():
    from server.skill_registry import build_registry

    registro = build_registry(RAIZ)
    skill = registro.get("celular.acesso")
    assert skill is not None
    assert skill.side_effects is False


def test_a_funcao_devolve_o_mapa_com_as_quatro_vias():
    from server import celular as C

    dados = C.acesso()
    vias = [e["via"] for e in dados["entradas"]]
    assert len(vias) == 4
    assert any("toque" in v for v in vias)
    assert any("USB" in v for v in vias)
    assert any("microSD" in v for v in vias)
    assert any("Wi-Fi" in v for v in vias)


def test_a_funcao_marca_o_que_esta_quebrado_e_o_que_esta_aberto():
    from server import celular as C

    dados = C.acesso()
    estados = {e["via"]: e["estado"] for e in dados["entradas"]}
    toque = [v for v in estados if "toque" in v][0]
    usb = [v for v in estados if "USB" in v][0]
    cartao = [v for v in estados if "microSD" in v][0]
    assert estados[toque] == "quebrada"
    assert estados[usb] == "quebrada"
    assert "aberta" in estados[cartao]


def test_a_funcao_diz_que_a_solda_reabre_tudo_e_qual_a_ordem():
    from server import celular as C

    dados = C.acesso()
    assert "devolve dados" in dados["uma_solda_reabre_tudo"]
    ordem = " ".join(dados["ordem_depois_do_conserto"])
    assert "sonda-otg.bat" in ordem
    assert "Odin" in ordem
    assert "adb sideload" in ordem
