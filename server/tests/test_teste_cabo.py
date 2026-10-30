"""`teste-cabo.bat` + `teste-cabo.ps1` + `vigiar-cabo.bat`: separar cabo, porta e conector.

Caso que gerou isto: o Windows tinha 11 nos USB (leitor de cartao, teclado, mouse)
e **nenhum** `VID_04E8`; o "dispositivo portatil" era o pen drive. Depois o usuario
testou todos os cabos — dois deles passam dados em outro aparelho — e o J7 so
carrega. A primeira versao do teste respondeu **codigo 3 (falha de leitura)**, que
era bug meu: uma consulta WMI vazia por soluco virava "nao consegui ler". Estes
testes travam as tres correcoes da 0.62.7.
"""
from __future__ import annotations

from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
BAT = RAIZ / "teste-cabo.bat"
PS1 = RAIZ / "teste-cabo.ps1"
VIGIAR_BAT = RAIZ / "vigiar-cabo.bat"


def _codigo(caminho: Path) -> str:
    """So as linhas de codigo: comentario nao conta como comportamento."""
    return "\n".join(
        linha for linha in caminho.read_text(encoding="utf-8").splitlines()
        if not linha.strip().startswith("#")
    )


def test_os_arquivos_existem_na_raiz():
    for caminho in (BAT, PS1, VIGIAR_BAT):
        assert caminho.is_file(), caminho.name
        assert caminho.parent == (RAIZ / "iniciar.py").parent


def test_sao_ascii_puro_e_crlf():
    for caminho in (BAT, PS1, VIGIAR_BAT):
        bruto = caminho.read_bytes()
        assert not any(b > 127 for b in bruto), caminho.name
        assert bruto.count(b"\r\n") == bruto.count(b"\n"), caminho.name


def test_script_nao_tem_erro_de_sintaxe_powershell():
    sintaxe = pytest.importorskip("tree_sitter_powershell", reason="parser opcional")
    from tree_sitter import Language, Parser

    arvore = Parser(Language(sintaxe.language())).parse(PS1.read_bytes())
    assert arvore.root_node.has_error is False


# ---------------------------------------------------------------- leitura robusta


def test_le_com_tres_tentativas_e_dois_planos_b():
    """O codigo 3 tem de significar falha real, nao soluco de WMI."""
    texto = _codigo(PS1)
    assert "for ($i = 1; $i -le 3; $i++)" in texto
    assert "Get-CimInstance -ClassName Win32_PnPEntity" in texto
    assert "Get-PnpDevice -PresentOnly" in texto
    assert "Start-Sleep -Milliseconds 700" in texto


def test_tem_piso_de_sanidade_para_lista_vazia():
    """Windows sem 5 dispositivos e leitura quebrada, nao maquina vazia."""
    texto = _codigo(PS1)
    assert "$Piso = 5" in texto
    assert texto.count("-ge $Piso") >= 3


def test_leitura_falhada_nunca_vira_aparelho_ausente():
    texto = _codigo(PS1)
    assert "exit 3" in texto
    assert "Nao consegui ler a lista de dispositivos do Windows" in PS1.read_text(encoding="utf-8")
    assert "nem com os planos B" in PS1.read_text(encoding="utf-8")


def test_tentativa_com_leitura_falha_e_repetida_e_nao_aborta_o_teste():
    texto = _codigo(PS1)
    assert "repetindo esta tentativa" in PS1.read_text(encoding="utf-8")
    assert "continue" in texto


# ---------------------------------------------------------------- vigia por evento


def test_a_espera_usa_evento_e_nao_consulta():
    """Conector com solda fria enumera por fracoes de segundo: consulta perde."""
    texto = _codigo(PS1)
    assert "Register-WmiEvent" in texto
    assert "__InstanceCreationEvent" in texto
    assert "Wait-Event" in texto
    assert "Unregister-Event" in texto


def test_o_evento_registra_a_hora_e_marca_samsung():
    texto = _codigo(PS1)
    assert "(Get-Date).ToString('HH:mm:ss')" in texto
    assert "<== SAMSUNG (o celular)" in PS1.read_text(encoding="utf-8")


def test_a_espera_mostra_contagem_em_vez_de_ficar_parada():
    texto = _codigo(PS1)
    assert '"     ... " + $resta + "s"' in texto
    assert texto.count('"     ... " + $resta + "s"') >= 2  # evento e plano B


def test_se_o_windows_recusar_a_assinatura_cai_para_consulta():
    texto = _codigo(PS1)
    assert "recusou a assinatura de eventos" in PS1.read_text(encoding="utf-8")
    assert "if (-not $deuEvento)" in texto


# ---------------------------------------------------------------- modo pressao


def test_o_modo_vigiar_existe_e_ensina_a_pressionar_o_conector():
    texto = PS1.read_text(encoding="utf-8")
    assert "param(" in texto and "$Vigiar = 0" in texto
    assert "teste de pressao do conector" in texto
    assert "pressione o plugue para dentro" in texto
    assert "cunha fina (papel dobrado)" in texto


def test_veredito_de_pressao_distingue_solda_fria_de_pino_quebrado():
    texto = PS1.read_text(encoding="utf-8")
    assert "solda fria" in texto
    assert "pino quebrado" in texto
    assert "da para segurar com calco" in texto


def test_o_vigiar_cabo_chama_o_modo_pressao_por_60_segundos():
    texto = VIGIAR_BAT.read_text(encoding="utf-8")
    assert '-Vigiar 60' in texto
    assert "teste-cabo.ps1" in texto


# ---------------------------------------------------------------- vereditos


def test_o_teste_pausa_entre_tentativas_para_a_pessoa_trocar_de_cabo():
    texto = PS1.read_text(encoding="utf-8")
    assert "Read-Host" in texto
    assert "TENTATIVA" in texto
    assert "porta DIFERENTE" in texto


def test_veredito_aponta_driver_so_quando_aparece_04e8():
    texto = _codigo(PS1)
    assert "if ($Samsung.Count -gt 0)" in texto
    assert "VID_04E8" in PS1.read_text(encoding="utf-8")
    assert texto.index("sonda-otg.bat") > texto.index("if ($Samsung.Count -gt 0)")


def test_veredito_sem_aparelho_manda_o_teste_de_pressao_antes_de_comprar_cabo():
    texto = PS1.read_text(encoding="utf-8")
    assert "vigiar-cabo.bat" in texto
    assert "LIMPE O CONECTOR" in texto
    assert "palito de dente" in texto
    assert "Nunca metal, nunca liquido" in texto
    assert texto.index("LIMPE O CONECTOR") < texto.index("TESTE DE PRESSAO")
    assert texto.index("TESTE DE PRESSAO") < texto.index("CABO: tem de ser micro-USB")
    assert texto.index("CABO: tem de ser micro-USB") < texto.index("OUTRA PORTA do PC")


def test_avisa_que_cabo_usb_c_do_a34_nao_testa_o_j7():
    """O A34 e USB-C; o J7 e micro-USB. Cabo que funciona la nao entra aqui."""
    texto = PS1.read_text(encoding="utf-8")
    assert "Cabo USB-C que passa dados no A34 nao entra no J7" in texto


def test_o_teste_nao_promete_conserto_por_software_quando_e_pino():
    texto = PS1.read_text(encoding="utf-8")
    assert "solda ou assistencia" in texto
    assert "Por software eu nao consigo consertar pino quebrado" in texto


def test_a_sonda_manda_para_o_teste_quando_nao_ha_samsung():
    sonda = (RAIZ / "sonda-otg.ps1").read_text(encoding="utf-8")
    assert "teste-cabo.bat" in sonda
    assert "nao e driver (o Zadig so lista o" in sonda

    bat = (RAIZ / "sonda-otg.bat").read_text(encoding="utf-8")
    assert "teste-cabo.bat" in bat


def test_o_teste_aponta_o_vigiar_cabo_no_fim():
    texto = BAT.read_text(encoding="utf-8")
    assert "vigiar-cabo.bat" in texto
