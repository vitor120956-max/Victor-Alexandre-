"""`vigiar-usb.bat` + `vigiar-usb.ps1`: o teste conectar/desconectar ao vivo.

O caso que gerou isto: o celular carrega, o Windows não vê nada, e a pessoa
teria de rodar `celular.status` a cada cabo que tentasse — sem saber o instante
em que algo muda. A janela de vigia resolve isso; estes testes garantem o
contrato que dói quando quebra.
"""
from __future__ import annotations

from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
BAT = RAIZ / "vigiar-usb.bat"
PS1 = RAIZ / "vigiar-usb.ps1"


def _texto(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8", errors="replace")


def test_os_dois_arquivos_existem_ao_lado_do_iniciar_py():
    assert BAT.is_file()
    assert PS1.is_file()
    assert PS1.parent == (RAIZ / "iniciar.py").parent


def test_script_e_ascii_puro():
    """Console do Windows com chcp 65001 embaralha acento vindo do PowerShell."""
    estranhos = [(i, b) for i, b in enumerate(PS1.read_bytes()) if b > 127]
    assert estranhos == [], estranhos[:5]


def test_script_nao_tem_erro_de_sintaxe_powershell():
    sintaxe = pytest.importorskip("tree_sitter_powershell", reason="parser de PowerShell opcional")
    from tree_sitter import Language, Parser

    arvore = Parser(Language(sintaxe.language())).parse(PS1.read_bytes())
    assert arvore.root_node.has_error is False


def test_le_a_usb_e_nao_executa_nada():
    texto = _texto(PS1)
    assert "Get-PnpDevice" in texto
    for proibido in ("Remove-Item", "Start-Process", "Invoke-WebRequest", "Schtasks", "netsh"):
        assert proibido not in texto, proibido


def test_apita_e_avisa_na_hora_em_que_algo_entra():
    texto = _texto(PS1)
    assert "[console]::Beep" in texto
    assert "ENTROU" in texto and "SAIU" in texto
    assert "VID_04E8" in texto or "04E8" in texto


def test_reconhece_o_dispositivo_que_o_windows_nao_identificou():
    texto = _texto(PS1)
    assert "esconhecid|unknown" in texto
    assert "cabo de dados" in texto.lower() or "cabo de" in texto


def test_mostra_sinal_de_vida_a_cada_30_segundos():
    """Janela parada não pode parecer travamento."""
    texto = _texto(PS1)
    assert "ainda vigiando" in texto
    assert "TotalSeconds -ge 30" in texto


def test_para_fechando_a_janela_e_nao_pede_tecla():
    for caminho in (PS1, BAT):
        texto = _texto(caminho)
        assert "Ctrl+C" not in texto
        assert "CTRL+C" not in texto
    assert "no X" in _texto(PS1)


def test_o_bat_chama_o_script_com_a_politica_certa():
    texto = _texto(BAT)
    assert "vigiar-usb.ps1" in texto
    assert "-ExecutionPolicy Bypass" in texto
    assert "chcp 65001" in texto
    # `pause` só no caminho de erro: com o script longo, o pause nunca apareceria
    assert texto.index("vigiar-usb.ps1") < texto.index("pause")


def test_a_camada_do_celular_aponta_para_a_vigia_no_plano():
    """Quem recebe "teste cabo e porta" precisa saber que existe a janela ao vivo."""
    texto = (RAIZ / "server" / "celular.py").read_text(encoding="utf-8")
    assert "vigiar-usb-atento.bat" in texto
