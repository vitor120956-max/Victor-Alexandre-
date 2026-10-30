"""`resgatar-cartao.bat` + `.ps1`: as fotos saem pelo cartão, sem o conector.

Caso que gerou isto: o teste de pressão do conector (`vigiar-cabo.bat`) ficou 60 s
com o plugue pressionado, inclinado e girado e **nada** apareceu no Windows, com
cabos que passam dados em outro aparelho. Sem dados na USB não existe scrcpy,
adb nem MTP — e não existe driver que conserte pino. O caminho que sobra, de
graça, é o microSD: o leitor de cartão já está ligado no PC (a sonda viu um Alcor
`058F`). Estes testes travam o contrato de segurança desse resgate.
"""
from __future__ import annotations

from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
BAT = RAIZ / "resgatar-cartao.bat"
PS1 = RAIZ / "resgatar-cartao.ps1"


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


# ---------------------------------------------------------------- so leitura


def test_o_cartao_e_so_leitura():
    """Nada de Remove-Item/Move-Item/Format-Volume: o cartão é a única cópia."""
    texto = _codigo(PS1)
    for proibido in ("Remove-Item", "Move-Item", "Rename-Item", "Format-Volume", "Clear-Disk"):
        assert proibido not in texto, proibido
    assert PS1.read_text(encoding="utf-8").count("SOMENTE LEITURA") >= 1


def test_nao_escreve_no_cartao():
    """O destino nunca pode cair dentro da origem."""
    texto = _codigo(PS1)
    assert "$Destino" in texto
    # a cópia sempre sai da origem para o destino (origem é só lida)
    assert "Copy-Item -LiteralPath $arq.FullName -Destination $alvo" in texto


# ---------------------------------------------------------------- honestidade


def test_confere_espaco_antes_de_comecar():
    """Falhar no meio de 8 GB é pior do que falhar agora."""
    texto = _codigo(PS1)
    assert "Win32_LogicalDisk" in texto
    assert "cabe" in PS1.read_text(encoding="utf-8")   # diz quando cabe
    assert "ESPACO INSUFICIENTE" in PS1.read_text(encoding="utf-8")
    assert "exit 3" in texto
    assert texto.index("ESPACO INSUFICIENTE") < texto.index("Copy-Item -LiteralPath $arq.FullName")


def test_mostra_o_plano_e_espera_confirmacao():
    texto = _codigo(PS1)
    assert "O que vou copiar:" in PS1.read_text(encoding="utf-8")
    assert "Read-Host" in texto
    assert "-not $Sim" in texto


def test_o_progresso_tem_contagem_velocidade_e_tempo_restante():
    texto = _codigo(PS1)
    assert "faltam ~" in texto
    assert "$velocidade" in texto
    assert "$feitos + '/' + $plano.Arquivos.Count" in texto


def test_pula_o_que_ja_foi_copiado_para_poder_rodar_de_novo():
    texto = _codigo(PS1)
    assert "$existente.Length -eq $arq.Length" in texto
    assert "$pulados" in texto


def test_diz_que_foto_da_memoria_interna_precisa_do_conector():
    """Sem essa frase o resgate vira promessa falsa de 'todas as fotos'."""
    texto = PS1.read_text(encoding="utf-8")
    assert "estava na memoria interna do celular" in texto
    assert "so sai com o conector funcionando" in texto


def test_pega_a_midia_do_whatsapp_em_android_media():
    texto = _codigo(PS1)
    assert "Android\\media\\com.whatsapp" in texto


def test_ignora_pasta_de_sistema_do_cartao():
    texto = _codigo(PS1)
    for lixo in ("$RECYCLE.BIN", "System Volume Information", "LOST.DIR"):
        assert lixo in texto


# ---------------------------------------------------------------- deteccao


def test_acha_disco_removivel_e_tambem_leitor_que_se_disfarca():
    texto = _codigo(PS1)
    assert "$_.DriveType -eq 2" in texto
    assert "$_.DriveType -eq 3" in texto
    assert "Get-CimInstance -ClassName Win32_LogicalDisk" in texto


def test_reconhece_cartao_pelas_pastas_de_foto():
    texto = _codigo(PS1)
    assert "function TemCara" in texto
    assert "'DCIM', 'Pictures', 'WhatsApp', 'Android'" in texto


def test_o_bat_ensina_a_tirar_o_cartao_do_celular():
    texto = BAT.read_text(encoding="utf-8")
    assert "desligue o celular" in texto
    assert "microSD" in texto
    assert "adaptador SD" in texto
