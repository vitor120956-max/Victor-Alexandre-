"""Testes do `diagnostico.py` (0.47.0) — lentidão medida, não adivinhada.

O script roda no PC do usuário e não pode falhar por falta de permissão: aqui os
parsers são exercitados com a saída real do Windows (tasklist e wmic) e o
veredito com números montados na mão.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
CAMINHO = RAIZ / "diagnostico.py"
BAT = RAIZ / "diagnostico-lento.bat"


def carregar():
    spec = importlib.util.spec_from_file_location("diagnostico", CAMINHO)
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # dataclass precisa do módulo registrado antes de executar (from __future__).
    sys.modules["diagnostico"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


DIAG = carregar()


# ------------------------------------------------------------------- parsing

TASKLIST = (
    '"System Idle Process","0","Services","0","24 K"\r\n'
    '"chrome.exe","12044","Console","1","412.340 K"\r\n'
    '"chrome.exe","12050","Console","1","288.100 K"\r\n'
    '"GoogleDriveFS.exe","9012","Console","1","98.456 K"\r\n'
    '"steam.exe","4411","Console","1","210.000 K"\r\n'
    '"explorer.exe","7011","Console","1","45.780 K"\r\n'
)


def test_parse_tasklist_le_memoria_em_mb():
    processos = DIAG.parse_tasklist(TASKLIST)
    nomes = [item.nome for item in processos]
    assert nomes == ["System Idle Process", "chrome.exe", "chrome.exe", "GoogleDriveFS.exe", "steam.exe", "explorer.exe"]
    chrome = processos[1]
    assert chrome.memoria_mb == pytest.approx(402.7, abs=0.2)


def test_parse_tasklist_ignora_linha_quebrada():
    assert DIAG.parse_tasklist("nome,pid\n") == []


CPU = """Name                          PercentProcessorTime
chrome                        12
chrome#1                      4
GoogleDriveFS.exe             3
_Total                        37
Name                          PercentProcessorTime
"""


def test_parse_cpu_soma_processos_do_mesmo_nome():
    cpu = DIAG.parse_cpu(CPU)
    assert cpu["chrome"] == 16.0
    assert cpu["GoogleDriveFS.exe"] == 3.0
    assert "_Total" not in cpu


def test_juntar_agrupa_e_ordena_por_memoria():
    processos = DIAG.parse_tasklist(TASKLIST)
    lista, por_nome = DIAG.juntar(processos, {"chrome": 16.0})
    assert lista[0].nome == "chrome.exe"
    assert lista[0].memoria_mb > 600
    assert por_nome["chrome"].cpu_pct == 16.0


# ------------------------------------------------------------------ veredito

def _dados(**campos):
    base = DIAG.Dados()
    for chave, valor in campos.items():
        setattr(base, chave, valor)
    return base


def test_veredito_aponta_ram_quando_esta_cheia():
    dados = _dados(ram_total_gb=4.0, ram_livre_gb=0.3, ram_uso_pct=92.5)
    frases = " ".join(DIAG.veredito(dados))
    assert "92%" in frases
    assert "gargalo é RAM" in frases


def test_veredito_aponta_google_drive_pesado():
    dados = _dados(ram_total_gb=4.0, ram_uso_pct=40, por_nome={"googledrivefs": DIAG.Processo("GoogleDriveFS.exe", 320.0)})
    frases = " ".join(DIAG.veredito(dados))
    assert "Google Drive" in frases
    assert "pausar a sincronização" in frases


def test_veredito_aponta_steam_aberta():
    dados = _dados(ram_uso_pct=30, por_nome={"steam": DIAG.Processo("steam.exe", 480.0)})
    frases = " ".join(DIAG.veredito(dados))
    assert "Steam" in frases


def test_veredito_aponta_hdd():
    dados = _dados(ram_uso_pct=20, discos_fisicos=[{"modelo": "ST500DM002", "parece_ssd": False}])
    frases = " ".join(DIAG.veredito(dados))
    assert "mecânico" in frases
    assert "SSD" in frases


def test_veredito_aponta_disco_quase_cheio():
    dados = _dados(
        ram_uso_pct=20,
        discos=[{"unidade": "D:\\", "total_gb": 7.2, "livre_gb": 0.4, "livre_pct": 5.5}],
    )
    frases = " ".join(DIAG.veredito(dados))
    assert "5.5%" in frases
    assert "10%" in frases


def test_veredito_nao_culpa_o_jarvis_quando_ele_e_pequeno():
    dados = _dados(ram_uso_pct=30, por_nome={"python": DIAG.Processo("python.exe", 40.0)})
    assert "python.exe" in DIAG.formatar(dados)
    frases = " ".join(DIAG.veredito(dados))
    assert "não é ele" in frases


def test_veredito_sem_medicao_avisa():
    assert "Não medi nada" in DIAG.veredito(DIAG.Dados())[0]


# ----------------------------------------------------------------- relatório

def test_formatar_traz_as_secoes_principais():
    dados = _dados(
        sistema="Windows-10-10.0.14393-SP0",
        ram_total_gb=4.0,
        ram_livre_gb=0.4,
        ram_uso_pct=90.0,
        discos=[{"unidade": "C:\\", "total_gb": 218.0, "livre_gb": 120.0, "livre_pct": 55.0}],
        processos=[DIAG.Processo("chrome.exe", 900.0, 20.0)],
        por_nome={"chrome": DIAG.Processo("chrome.exe", 900.0, 20.0)},
    )
    texto = DIAG.formatar(dados)
    assert "por que o PC está lento" in texto
    assert "Quem mais ocupa memória agora" in texto
    assert "Os suspeitos de sempre" in texto
    assert "Veredito" in texto
    assert "chrome.exe" in texto


def test_memoria_devolve_tres_numeros_coerentes():
    total, livre, uso = DIAG.memoria()
    assert total >= 0 and livre >= 0
    assert 0 <= uso <= 100


# ---------------------------------------------------------------------- arquivos

def test_bat_existe_e_usa_crlf():
    bruto = BAT.read_bytes()
    assert b"\r\n" in bruto
    assert b"\n" not in bruto.replace(b"\r\n", b"")
    assert "diagnostico.py" in bruto.decode("utf-8")


def test_relatorio_nao_entra_no_git():
    ignorados = (RAIZ / ".gitignore").read_text(encoding="utf-8")
    assert "relatorio-lentidao.txt" in ignorados
