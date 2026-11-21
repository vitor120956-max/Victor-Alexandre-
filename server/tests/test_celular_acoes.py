"""Testes das ações no celular (0.92.5): abrir, fechar e instalar — com trava.

O dono pediu *“100% de acesso ao meu celular”*. A resposta deste projeto não é
prometer isso: é fazer **o que o degrau 1 permite** (cabo + Depuração USB) com
trava, e dizer em voz alta o que fica de fora.

O que estes testes travam:

- **sem `JARVIS_ACOES=1` nada acontece** — a resposta é o plano;
- **sem `confirmed: true` nada acontece** — mesmo com a variável ligada;
- **nome de pacote é validado** antes de virar argumento — `com.app; rm -rf /`
  não passa;
- **todo comando leva o serial** e sai por lista de argumentos, nunca por shell;
- **só `.apk`** instala (o `.ipa` de iPhone não roda no Android);
- **sem aparelho autorizado**, a resposta é a frase que resolve, não “erro 500”.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from server import acoes, anatomia


def _ligar(monkeypatch, *, adb: str = "/fake/adb") -> None:
    monkeypatch.setenv("JARVIS_ACOES", "1")
    monkeypatch.setenv("JARVIS_HOST_CELULAR", "1")
    monkeypatch.setattr("server.celular.ligado", lambda: True)
    monkeypatch.setattr(
        "server.celular.ferramentas", lambda: {"ligado": True, "adb": adb, "scrcpy": ""}
    )
    monkeypatch.setattr(anatomia, "_adb", lambda: adb)
    monkeypatch.setattr(
        anatomia, "aparelhos", lambda rodar=None: [{"serial": "ABC123", "estado": "device"}]
    )


def _capturar(monkeypatch, devolver: tuple[int, str, str] = (0, "Success", "")) -> list[list[str]]:
    registro: list[list[str]] = []

    def falso(argumentos, timeout=None):
        registro.append(list(argumentos))
        return devolver

    monkeypatch.setattr(anatomia, "_rodar", falso)
    return registro


# ---------------------------------------------------------------------------
# As travas
# ---------------------------------------------------------------------------

def test_sem_jarvis_acoes_so_devolve_o_plano(monkeypatch):
    monkeypatch.delenv("JARVIS_ACOES", raising=False)
    with pytest.raises(acoes.AcoesError) as erro:
        acoes.celular_abrir_app("com.whatsapp", confirmado=True)
    assert "JARVIS_ACOES=1" in str(erro.value)


def test_sem_confirmacao_nada_e_aberto(monkeypatch):
    _ligar(monkeypatch)
    registro = _capturar(monkeypatch)
    plano = acoes.celular_abrir_app("com.whatsapp")
    assert plano["plano"] == "abrir com.whatsapp"
    assert registro == [], "o adb não podia ter rodado"


def test_sem_confirmacao_nada_e_fechado_e_o_aviso_diz_o_que_se_perde(monkeypatch):
    _ligar(monkeypatch)
    registro = _capturar(monkeypatch)
    plano = acoes.celular_fechar_app("com.instagram.android")
    assert "descarta" in plano["aviso"].lower()
    assert registro == []


def test_nome_de_pacote_com_comando_e_recusado(monkeypatch):
    _ligar(monkeypatch)
    _capturar(monkeypatch)
    for ruim in ("com.app; rm -rf /", "com.app && reboot", "../../etc", "com", "a b"):
        with pytest.raises(acoes.AcoesError):
            acoes.celular_abrir_app(ruim, confirmado=True)


def test_instalacao_so_aceita_apk(tmp_path: Path, monkeypatch):
    _ligar(monkeypatch)
    ipa = tmp_path / "app.ipa"
    ipa.write_bytes(b"PK\0\0")
    with pytest.raises(acoes.AcoesError) as erro:
        acoes.celular_instalar_apk(str(ipa), tmp_path, confirmado=True)
    assert "ipa" in str(erro.value).lower()


def test_sem_aparelho_autorizado_a_frase_resolve(monkeypatch):
    _ligar(monkeypatch)
    monkeypatch.setattr(anatomia, "aparelhos", lambda rodar=None: [])
    with pytest.raises(acoes.AcoesError) as erro:
        acoes.celular_abrir_app("com.whatsapp", confirmado=True)
    texto = str(erro.value)
    assert "cabo" in texto and "Permitir" in texto


# ---------------------------------------------------------------------------
# O caminho que funciona
# ---------------------------------------------------------------------------

def test_abrir_app_usa_monkey_com_o_pacote_e_o_serial(monkeypatch):
    _ligar(monkeypatch)
    registro = _capturar(monkeypatch, (0, "Events injected: 1", ""))
    resultado = acoes.celular_abrir_app("com.whatsapp", confirmado=True)
    assert resultado["aberto"] == "com.whatsapp"
    assert registro == [[
        "/fake/adb", "-s", "ABC123",
        "shell", "monkey", "-p", "com.whatsapp",
        "-c", "android.intent.category.LAUNCHER", "1",
    ]]


def test_fechar_app_usa_force_stop(monkeypatch):
    _ligar(monkeypatch)
    registro = _capturar(monkeypatch, (0, "", ""))
    acoes.celular_fechar_app("com.instagram.android", confirmado=True)
    assert registro[0][-3:] == ["am", "force-stop", "com.instagram.android"]


def test_instalar_apk_roda_adb_install_do_arquivo_do_jarvis(tmp_path: Path, monkeypatch):
    _ligar(monkeypatch)
    apk = tmp_path / "meu.apk"
    apk.write_bytes(b"PK\3\4" + b"0" * 100)
    registro = _capturar(monkeypatch, (0, "Success", ""))
    resultado = acoes.celular_instalar_apk(str(apk), tmp_path, confirmado=True)
    assert resultado["instalado"] == "meu.apk"
    assert registro[0][:6] == ["/fake/adb", "-s", "ABC123", "install", "-r", str(apk)]


def test_instalacao_recusada_explica_as_causas(monkeypatch, tmp_path: Path):
    _ligar(monkeypatch)
    apk = tmp_path / "velho.apk"
    apk.write_bytes(b"PK\3\4" + b"0" * 100)
    _capturar(monkeypatch, (1, "Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE]", ""))
    with pytest.raises(acoes.AcoesError) as erro:
        acoes.celular_instalar_apk(str(apk), tmp_path, confirmado=True)
    texto = str(erro.value)
    assert "assinatura" in texto
    assert "INSTALL_FAILED_UPDATE_INCOMPATIBLE" in texto


def test_apk_fora_da_area_do_jarvis_e_recusado(tmp_path: Path, monkeypatch):
    _ligar(monkeypatch)
    externo = tmp_path.parent / "fora.apk"
    externo.write_bytes(b"PK")
    with pytest.raises(acoes.AcoesError):
        acoes.celular_instalar_apk(str(externo), tmp_path / "files", confirmado=True)
