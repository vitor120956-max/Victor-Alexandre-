"""`formatar-celular.bat` + `.ps1` + `celular.formatar`: zerar pelos botões.

Caso que gerou isto: o toque da tela morreu (fantasma) e a porta micro-USB perdeu
os pinos de dados — o teste de pressão de 60 s não viu nada em nenhum ângulo. Sem
toque e sem dados, `adb`, `scrcpy` e MTP estão fora de alcance; sobra o recovery
de fábrica da Samsung, que se opera com Volume e Power.

O perigo real aqui não é o reset em si: é o **FRP**. Depois de zerar, o Android
exige a mesma conta Google que estava no aparelho. Se a pessoa não sabe a senha,
o aparelho para na tela de conta para sempre — nem com a tela consertada. Estes
testes travam esse freio.
"""
from __future__ import annotations

from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
BAT = RAIZ / "formatar-celular.bat"
PS1 = RAIZ / "formatar-celular.ps1"


def _codigo(caminho: Path) -> str:
    return "\n".join(
        linha for linha in caminho.read_text(encoding="utf-8").splitlines()
        if not linha.strip().startswith("#")
    )


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


# ---------------------------------------------------------------- o freio do FRP


def test_pergunta_a_conta_google_antes_de_zerar():
    texto = PS1.read_text(encoding="utf-8")
    assert "Voce sabe o e-mail E a senha da conta Google" in texto
    assert "FRP" in texto


def test_sem_a_conta_google_o_guia_para_e_nao_zera():
    """Sem essa parada, a pessoa apaga tudo e ganha um tijolo mais limpo."""
    texto = _codigo(PS1)
    assert "if (-not $sabe)" in texto
    assert "Entao NAO zerar agora." in PS1.read_text(encoding="utf-8")
    assert "exit 4" in texto
    # o exit 4 tem de vir ANTES do passo de desligar
    assert texto.index("exit 4") < texto.index("PASSO 1 - DESLIGAR")


def test_explica_como_descobrir_a_conta_depois_do_conserto():
    texto = PS1.read_text(encoding="utf-8")
    assert "Configuracoes -^> Contas -^> Google" in texto
    assert "myaccount.google.com" in texto


# ---------------------------------------------------------------- o roteiro


def test_o_roteiro_usa_os_botoes_certos_do_j7_prime():
    texto = PS1.read_text(encoding="utf-8")
    assert "VOLUME CIMA  +  HOME  +  POWER" in texto
    assert "VOLUME BAIXO  = desce a lista" in texto
    assert "POWER         = confirma o item destacado" in texto


def test_o_roteiro_tem_o_wipe_e_o_reboot():
    texto = PS1.read_text(encoding="utf-8")
    assert "wipe data/factory reset" in texto
    assert "Yes -- delete all user data" in texto
    assert "Reboot system now" in texto


def test_ensina_o_no_command_do_android_7():
    texto = PS1.read_text(encoding="utf-8")
    assert "No command" in texto
    assert "segure o POWER e toque VOLUME CIMA" in texto


def test_tem_plano_b_quando_os_tres_botoes_nao_entram():
    texto = PS1.read_text(encoding="utf-8")
    assert "function TentaRecovery" in texto
    assert "volte a segurar" not in texto.lower()
    assert "segure VOLUME CIMA e HOME primeiro" in texto
    assert "$tentativas -lt 3" in texto


def test_avisa_da_primeira_ligacao_longa():
    texto = PS1.read_text(encoding="utf-8")
    assert "5 a 15 minutos" in texto
    assert "Nao tire a bateria" in texto


def test_tem_modo_roteiro_sem_perguntas():
    texto = _codigo(PS1)
    assert "param(" in texto and "[switch]$Roteiro" in texto
    assert "MostraRoteiro" in texto
    assert BAT.read_text(encoding="utf-8").count("-Roteiro") >= 1


# ---------------------------------------------------------------- a verdade sobre o PC


def test_diz_que_dex_nao_existe_neste_modelo_e_por_que():
    texto = PS1.read_text(encoding="utf-8")
    assert "DeX" in texto
    assert "Galaxy S8" in texto
    assert "USB-C com saida de video" in texto
    assert "micro-USB de 2016" in texto


def test_diz_que_modo_pc_precisa_de_entrada():
    texto = PS1.read_text(encoding="utf-8")
    assert "Termux" in texto
    assert "precisa de entrada" in texto


def test_diz_o_que_o_reset_nao_resolve():
    texto = PS1.read_text(encoding="utf-8")
    assert "o TOQUE na tela (digitalizador) continua morto" in texto
    assert "os DADOS da porta USB continuam mortos" in texto


def test_deixa_claro_que_quem_aperta_os_botoes_e_a_mao():
    texto = PS1.read_text(encoding="utf-8")
    assert "quem apertou os botoes foi voce" in texto
    assert "nao tem como apagar" in texto


def test_o_guia_nao_contem_comando_destrutivo_no_pc():
    texto = _codigo(PS1)
    for proibido in ("Remove-Item", "Format-Volume", "Clear-Disk", "adb ", "fastboot "):
        assert proibido not in texto, proibido


# ---------------------------------------------------------------- a skill


def test_a_skill_existe_e_pede_confirmacao():
    from server.skill_registry import build_registry

    registro = build_registry(RAIZ)
    skill = registro.get("celular.formatar")
    assert skill is not None
    assert skill.requires_confirmation is True
    assert skill.side_effects is True


def test_a_skill_devolve_o_roteiro_e_o_freio():
    from server import celular as C

    dados = C.formatar()   # nao mede o aparelho: so devolve o roteiro
    assert dados["destrutivo"] is True
    assert dados["executado"] is False
    assert "NAO zerar" in dados["a_pergunta_que_decide"] or "NÃO zerar" in dados["a_pergunta_que_decide"]
    assert any("Volume Cima + Home + Power" in p for p in dados["passos"])
    assert "DeX" in dados["virar_pc"]
    assert "consertar o toque primeiro" in dados["ordem_que_funciona"]
