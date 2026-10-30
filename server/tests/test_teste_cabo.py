"""`teste-cabo.bat` + `teste-cabo.ps1`: o teste que separa cabo, porta e conector.

O caso que gerou isto: a `sonda-otg.bat` mostrou que o Windows tem 11 nos USB
(leitor de cartao, teclado, mouse) e **nenhum** com `VID_04E8`. O "dispositivo
portatil" da lista era o pen drive da pessoa, nao o celular. Ou seja: o J7 nao
esta enumerando, e o Zadig — que so lista aparelho enumerado — nao tem o que
instalar. Antes de qualquer driver, a pergunta e: *o Windows muda quando o
celular entra?* Estes testes travam o contrato disso.
"""
from __future__ import annotations

from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
BAT = RAIZ / "teste-cabo.bat"
PS1 = RAIZ / "teste-cabo.ps1"


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


def test_o_teste_pausa_entre_tentativas_para_a_pessoa_trocar_de_cabo():
    texto = PS1.read_text(encoding="utf-8")
    assert "Read-Host" in texto
    assert "TENTATIVA" in texto
    assert "porta DIFERENTE" in texto


def test_a_espera_mostra_contagem_em_vez_de_ficar_parada():
    texto = PS1.read_text(encoding="utf-8")
    assert "o Windows ainda nao mudou nada" in texto
    assert "Start-Sleep" in texto


def test_veredito_aponta_driver_so_quando_aparece_04e8():
    texto = PS1.read_text(encoding="utf-8")
    # o cabeçalho cita os dois arquivos: a ordem tem de ser aferida no CÓDIGO
    codigo = "\n".join(l for l in texto.splitlines() if not l.strip().startswith("#"))
    assert "if ($Samsung.Count -gt 0)" in codigo
    assert "VID_04E8" in codigo
    # o caminho do driver só aparece dentro do ramo "apareceu"
    assert codigo.index("sonda-otg.bat") > codigo.index("if ($Samsung.Count -gt 0)")


def test_veredito_sem_aparelho_manda_a_lista_fisica_na_ordem_certa():
    """Conector primeiro: é o caso clássico de "carrega mas o PC não vê"."""
    texto = PS1.read_text(encoding="utf-8")
    assert "carrega mas o PC nao ve" in texto
    assert "palito de dente" in texto
    assert "Nunca metal, nunca liquido" in texto
    assert "OUTRA PORTA do PC" in texto
    assert "OUTRO CABO micro-USB" in texto
    assert "CONFIRME QUE O CELULAR ESTA LIGADO" in texto
    # ordem: conector antes de porta, porta antes de cabo
    assert texto.index("LIMPE O CONECTOR") < texto.index("OUTRA PORTA do PC")
    assert texto.index("OUTRA PORTA do PC") < texto.index("OUTRO CABO micro-USB")


def test_o_teste_nao_promete_conserto_por_software_quando_e_pino():
    texto = PS1.read_text(encoding="utf-8")
    assert "solda ou" in texto
    assert "nao tem como consertar isso por software" in texto


def test_falha_de_leitura_nao_vira_aparelho_ausente():
    """Custo alto de errar: mandar a pessoa comprar cabo por falha de WMI."""
    texto = PS1.read_text(encoding="utf-8")
    assert "exit 3" in texto
    assert "nao consegui ler a lista" in texto.lower()
    assert "FalhaLeitura" in texto


def test_a_sonda_manda_para_o_teste_quando_nao_ha_samsung():
    sonda = (RAIZ / "sonda-otg.ps1").read_text(encoding="utf-8")
    assert "teste-cabo.bat" in sonda
    assert "nao e driver (o Zadig so lista o" in sonda

    bat = (RAIZ / "sonda-otg.bat").read_text(encoding="utf-8")
    assert "teste-cabo.bat" in bat
