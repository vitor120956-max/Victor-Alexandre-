"""Compatibilidade: instalar o JARVIS em outras distros — e onde é impossível.

Contrato, em uma frase: **sistema sem caminho não recebe comando**. A tentação
aqui é gerar `apt install` para tudo e deixar o dono descobrir sozinho que não
funciona; o teste que importa é o que cobra a recusa.
"""
from __future__ import annotations

import pytest

from server import compatibilidade as c


def test_os_oito_sistemas_pedidos_estao_na_lista():
    """O pedido do dono nomeou oito. Nenhum pode ficar de fora."""
    ids = {s["id"] for s in c.sistemas()}
    assert ids == {
        "parrot", "astra", "neokylin", "whonix",
        "lindows", "redstar", "templeos", "windows-gaming",
    }


@pytest.mark.parametrize("nome", ["templeos", "lindows", "redstar", "windows gaming"])
def test_quem_nao_roda_nao_recebe_comando(nome):
    """A regra central: impossível é impossível, sem `apt install` inventado."""
    dados = c.plano(nome)
    assert dados["pode_instalar"] is False
    assert dados["comandos"] == []
    # e a recusa precisa oferecer um caminho, não só um "não"
    assert dados["em_vez_disso"].strip()


def test_templeos_explica_o_que_quebraria_em_detalhe():
    """Ele pediu detalhe: sem Python, sem pip, sem TLS, sem subprocesso."""
    dados = c.plano("templeos")
    texto = " ".join(dados["quebra"]).lower()
    assert "python" in texto
    assert "pip" in texto
    assert "tls" in texto
    assert len(dados["quebra"]) >= 4, "detalhe não é uma frase só"


@pytest.mark.parametrize("nome", ["parrot", "astra", "neokylin", "whonix"])
def test_quem_roda_recebe_passo_a_passo_com_gerenciador_certo(nome):
    dados = c.plano(nome)
    assert dados["pode_instalar"] is True
    texto = " ".join(dados["comandos"]).lower()
    if dados["id"] == "neokylin":
        assert "dnf" in texto, "família rpm não pode receber apt"
    else:
        assert "apt" in texto, "família debian não pode receber dnf"
        assert "dnf" not in texto


def test_whonix_avisa_que_a_rede_cai():
    """Whonix roda o JARVIS — menos tudo que fala com a internet."""
    dados = c.plano("whonix")
    texto = " ".join(dados["quebra"]).lower()
    assert "tor" in texto
    assert "rede" in texto or "download" in texto


def test_nome_desconhecido_lista_o_que_existe():
    with pytest.raises(c.SistemaError) as erro:
        c.plano("haiku")
    # a recusa tem de dizer o que EU sei, em vez de só "desconhecido"
    assert "parrot" in str(erro.value).lower()


def test_medir_le_a_maquina_de_verdade(monkeypatch):
    """Medir é o que separa “roda” de “roda aqui”."""
    dados = c.medir()
    assert dados["python"] == "3.11.2" or dados["python"].count(".") == 2
    assert isinstance(dados["ferramentas"], dict)
    assert set(dados["ferramentas"]) == {"python3", "pip", "adb", "git", "ffmpeg"}
    # `pode_rodar_aqui` não pode ser verdade com problema listado
    if dados["problemas"]:
        assert dados["pode_rodar_aqui"] is False


def test_python_velho_impede_o_jarvis(monkeypatch):
    """3.8 não roda: o código usa `dict[str, Any]` em anotação de classe."""
    import platform as p

    monkeypatch.setattr(p, "python_version", lambda: "3.8.10")
    dados = c.medir()
    assert dados["python_ok"] is False
    assert any("3.9" in problema for problema in dados["problemas"])
    assert dados["pode_rodar_aqui"] is False


def test_esta_maquina_so_aparece_para_familia_conhecida():
    """Em TempleOS não faz sentido devolver `esta_maquina` de Linux."""
    dados = c.plano("templeos")
    assert "esta_maquina" not in dados


def test_em_texto_nao_tem_jargao_solto():
    """A saída de terminal tem de ser legível para quem não é programador."""
    texto = c.em_texto("lindows")
    assert "não roda" in texto
    assert "Em vez disso:" in texto


def test_scanner_tem_a_opcao_sistemas(capsys):
    """`escanear-celular.py --sistemas` — o caminho do duplo clique."""
    import importlib.util
    from pathlib import Path

    alvo = Path(__file__).resolve().parents[2] / "escanear-celular.py"
    spec = importlib.util.spec_from_file_location("escanear_sis", alvo)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)

    codigo = modulo.main(["--sistemas"])
    saida = capsys.readouterr().out
    assert codigo == 0
    assert "Esta máquina" in saida
    for nome in ("TempleOS", "Lindows", "Whonix", "NeoKylin", "Parrot"):
        assert nome in saida
    # o veredito tem de estar visível, não só o nome
    assert "não roda" in saida


def test_o_handler_do_driver_executa_de_verdade(monkeypatch):
    """0.95.6 — o handler da 0.95.2 usava `sistema_mod` sem importar.

    Nenhum teste executava o handler: o teste só lia o schema, e o
    `undefined name` passou por três versões. Aqui ele roda de verdade.
    """
    from server import skill_registry as sr
    from server import sistema

    monkeypatch.setattr(sistema.platform, "system", lambda: "Windows")
    definicao = sr.build_registry(__import__("pathlib").Path.cwd()).get("sistema.driver-celular")
    dados = definicao.input_model(fabricante="samsung")
    resultado = definicao.handler(dados, False)
    assert resultado["driver"].startswith("Samsung")


def test_o_handler_de_compatibilidade_executa_de_verdade():
    from pathlib import Path

    from server import skill_registry as sr

    definicao = sr.build_registry(Path.cwd()).get("sistema.compatibilidade")
    dados = definicao.input_model(sistema="whonix")
    resultado = definicao.handler(dados, False)
    assert resultado["pode_instalar"] is True
    assert any("Tor" in item for item in resultado["quebra"])
