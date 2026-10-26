"""Testes do instalador — nada aqui baixa da internet nem executa instalador."""
from __future__ import annotations

import json
import struct
import zipfile
from pathlib import Path

import pytest

from server import instalador as ins
from server import sistema


@pytest.fixture(autouse=True)
def _quarentena(tmp_path, monkeypatch):
    base = tmp_path / "host-downloads"
    base.mkdir()
    monkeypatch.setattr(ins, "QUARENTENA", base)
    return base


def _pe(
    *,
    maquina: int = 0x8664,
    magic: int = 0x20B,
    os_maior: int = 6,
    os_menor: int = 1,
    subsistema: int = 3,
    clr: bytes = b"",
) -> bytes:
    """Um PE mínimo com os campos que a análise lê."""
    dados = bytearray(1024)
    dados[0:2] = b"MZ"
    struct.pack_into("<I", dados, 0x3C, 0x80)
    dados[0x80:0x84] = b"PE\x00\x00"
    struct.pack_into("<H", dados, 0x84, maquina)
    struct.pack_into("<H", dados, 0x94, 0xE0)
    opt = 0x98
    struct.pack_into("<H", dados, opt, magic)
    struct.pack_into("<H", dados, opt + 40, os_maior)
    struct.pack_into("<H", dados, opt + 42, os_menor)
    struct.pack_into("<H", dados, opt + 48, 6)
    struct.pack_into("<H", dados, opt + 50, 0)
    struct.pack_into("<H", dados, opt + 68, subsistema)
    if clr:
        base = opt + (96 if magic == 0x10B else 112)
        struct.pack_into("<I", dados, base + 14 * 8, 0x2000)
    return bytes(dados) + clr


def _maquina(**troca) -> dict:
    padrao = {
        "windows": {
            "major": 10,
            "minor": 0,
            "build": 14393,
            "release": "1607",
            "nome": "Windows 10",
            "service_pack": "",
        },
        "plataforma": "Windows 10 1607 (build 14393)",
        "arquitetura": "x64",
        "bits": 64,
        "ram_gb": 4.0,
        "nucleos": 4,
        "discos": [{"nome": "C:", "livre_gb": 40.0, "total_gb": 100.0}],
        "dotnet": ["4.8"],
        "resumo": "Windows 10 1607 (build 14393), x64 (64 bits), 4.0 GB de RAM, 4 núcleos.",
    }
    padrao.update(troca)
    return padrao


def _analisar(tmp_path: Path, nome: str, dados: bytes, **kwargs) -> dict:
    alvo = tmp_path / nome
    alvo.write_bytes(dados)
    kwargs.setdefault("maquina_dada", _maquina())
    return ins.analisar(arquivo=str(alvo), conferir_assinatura=False, **kwargs)


# ---------------------------------------------------------------------------
# Máquina
# ---------------------------------------------------------------------------


def test_maquina_mede_o_windows_quando_ha(monkeypatch):
    monkeypatch.setattr(ins, "_versao_windows", lambda: _maquina()["windows"])
    monkeypatch.setattr(ins, "_ram_gb", lambda: 4.0)
    monkeypatch.setattr(ins, "_discos", lambda: [{"nome": "C:", "livre_gb": 12.0, "total_gb": 100.0}])
    monkeypatch.setattr(ins, "_dotnet", lambda: ["4.8"])
    dados = ins.maquina()
    assert "Windows 10 1607" in dados["plataforma"]
    assert dados["ram_gb"] == 4.0
    assert dados["dotnet"] == ["4.8"]
    assert "1607" in dados["resumo"]


def test_maquina_fora_do_windows_diz_que_a_camada_e_do_windows(monkeypatch):
    monkeypatch.setattr(ins, "_versao_windows", lambda: None)
    monkeypatch.setattr(ins, "_ram_gb", lambda: 8.0)
    dados = ins.maquina()
    assert dados["windows"] is None
    assert "Windows" in dados["resumo"] or "camada" in dados["resumo"]


# ---------------------------------------------------------------------------
# Destinos
# ---------------------------------------------------------------------------


def test_destinos_todas_as_opcoes_ficam_na_quarentena():
    dados = ins.destinos()
    base = Path(dados["pasta_base"])
    assert base == ins.QUARENTENA
    for opcao in dados["opcoes"]:
        assert Path(opcao["caminho"]) == base or base in Path(opcao["caminho"]).parents
        assert "livre_gb" in opcao
    assert dados["opcoes"][0]["recomendado"] is True


def test_destinos_mostra_o_que_fica_fora_como_nao_instalavel():
    dados = ins.destinos()
    for item in dados["fora"]:
        assert "instalar não" in item["nota"] or "instalar nao" in item["nota"]


@pytest.mark.parametrize("nome", ["../etc", "a/b", ".oculto", "a\\b"])
def test_destino_com_caminho_recusa(nome):
    with pytest.raises(ins.InstaladorError):
        ins._pasta(nome)


def test_destino_personalizado_aceita_nome_simples():
    assert ins._pasta("meus instaladores") == ins.QUARENTENA / "meus instaladores"
    assert ins._pasta("") == ins.QUARENTENA
    assert ins._pasta("por-data").name.count("-") == 1


# ---------------------------------------------------------------------------
# Análise do arquivo
# ---------------------------------------------------------------------------


def test_analisar_exe_x64_declara_que_roda(tmp_path):
    resultado = _analisar(tmp_path, "setup.exe", _pe())
    assert resultado["veredito"] == "roda"
    assert resultado["arquitetura_do_arquivo"] == "x64"
    assert resultado["os_minimo_do_arquivo"] == "6.1"
    assert resultado["proximos_passos"]


def test_analisar_programa_de_16_bits_recusa(tmp_path):
    dados = bytearray(256)
    dados[0:2] = b"MZ"
    struct.pack_into("<I", dados, 0x3C, 0x40)
    dados[0x40:0x44] = b"NE\x00\x00"
    resultado = _analisar(tmp_path, "velho.exe", bytes(dados))
    assert resultado["veredito"] == "não roda"
    assert any("16 bits" in item for item in resultado["bloqueios"])


def test_analisar_arm64_recusa_em_pc_x64(tmp_path):
    resultado = _analisar(tmp_path, "arm.exe", _pe(maquina=0xAA64))
    assert resultado["veredito"] == "não roda"
    assert any("ARM64" in item for item in resultado["bloqueios"])


def test_analisar_binario_que_pede_windows_maior_recusa(tmp_path):
    _analisar(tmp_path, "novo.exe", _pe(os_maior=10, os_menor=0))
    antigo = _maquina(
        windows={"major": 6, "minor": 1, "build": 7601, "release": "7", "nome": "Windows", "service_pack": ""},
        plataforma="Windows 7 (build 7601)",
    )
    resultado = ins.analisar(
        arquivo=str(tmp_path / "novo.exe"), maquina_dada=antigo, conferir_assinatura=False
    )
    assert resultado["veredito"] == "não roda"
    assert any("exigir Windows 10.0" in item for item in resultado["bloqueios"])


def test_analisar_msix_recusa_no_1607(tmp_path):
    alvo = tmp_path / "app.msix"
    with zipfile.ZipFile(alvo, "w") as pacote:
        pacote.writestr("AppxManifest.xml", "<Package/>")
    resultado = ins.analisar(arquivo=str(alvo), maquina_dada=_maquina(), conferir_assinatura=False)
    assert resultado["veredito"] == "não roda"
    assert any("MSIX" in item for item in resultado["bloqueios"])


def test_analisar_pacote_de_outro_sistema_recusa(tmp_path):
    resultado = _analisar(tmp_path, "programa.dmg", b"\x00" * 500)
    assert resultado["veredito"] == "não roda"
    assert any("macOS" in item for item in resultado["bloqueios"])


def test_analisar_respeita_requisitos_do_fabricante(tmp_path):
    resultado = _analisar(
        tmp_path,
        "jogo.exe",
        _pe(),
        min_os="1809",
        ram_gb=8,
        disco_gb=500,
    )
    assert resultado["veredito"] == "não roda"
    texto = " ".join(resultado["bloqueios"])
    assert "1809" in texto and "8 GB" in texto and "500 GB" in texto


def test_analisar_dotnet_35_sem_35_instalado_vira_ressalva(tmp_path):
    resultado = _analisar(tmp_path, "antigo.exe", _pe(clr=b"v2.0.50727\x00"))
    assert resultado["veredito"] == "roda com ressalva"
    assert any("3.5" in item for item in resultado["ressalvas"])


def test_analisar_zip_com_instalador_dentro(tmp_path):
    alvo = tmp_path / "pacote.zip"
    with zipfile.ZipFile(alvo, "w") as pacote:
        pacote.writestr("setup.exe", b"MZ")
    resultado = ins.analisar(arquivo=str(alvo), maquina_dada=_maquina(), conferir_assinatura=False)
    assert resultado["formato"] == "zip"
    assert any("ZIP" in item for item in resultado["ressalvas"])


def test_analisar_sem_alvo_devolve_a_maquina(tmp_path):
    resultado = ins.analisar(maquina_dada=_maquina())
    assert resultado["veredito"] == "não dá para saber"
    assert "Manda o link" in resultado["resumo"]


def test_analisar_link_nao_baixa_e_diz_o_que_falta(monkeypatch):
    chamadas: list[str] = []

    def falso(url: str) -> dict:
        chamadas.append(url)
        return {"url": url, "nome": "app.msix", "bytes": 123, "tipo": "application/msix"}

    monkeypatch.setattr(ins, "_cabecalho_remoto", falso)
    resultado = ins.analisar(url="https://exemplo.com/app.msix", maquina_dada=_maquina())
    assert chamadas == ["https://exemplo.com/app.msix"]
    assert resultado["veredito"] == "não roda"
    assert any("MSIX" in item for item in resultado["bloqueios"])
    assert resultado["proximos_passos"]


def test_analisar_link_de_exe_diz_que_ainda_nao_leu_o_binario(monkeypatch):
    monkeypatch.setattr(
        ins,
        "_cabecalho_remoto",
        lambda url: {"url": url, "nome": "setup.exe", "bytes": 10_000, "tipo": "x"},
    )
    resultado = ins.analisar(url="https://exemplo.com/setup.exe", maquina_dada=_maquina())
    assert resultado["veredito"] == "não dá para saber"
    assert any("não foi baixado" in item for item in resultado["nao_verificado"])


def test_analisar_arquivo_inexistente_recusa(tmp_path):
    with pytest.raises(ins.InstaladorError):
        ins.analisar(arquivo=str(tmp_path / "nao-existe.exe"))


def test_resultado_da_analise_e_json(tmp_path):
    resultado = _analisar(tmp_path, "setup.exe", _pe())
    assert json.loads(json.dumps(resultado, ensure_ascii=False))["veredito"] == "roda"


# ---------------------------------------------------------------------------
# Assinatura e leitura de build
# ---------------------------------------------------------------------------


def test_assinatura_fora_do_windows_nao_inventa(monkeypatch):
    monkeypatch.setattr(ins.os, "name", "posix")
    estado = ins._assinatura(Path("/tmp/qualquer.exe"))
    assert estado["estado"] == "não verificável"


@pytest.mark.parametrize(
    ("texto", "build"),
    [
        ("1607", 14393),
        ("1809", 17763),
        ("22H2", 19045),
        ("Windows 11", 22000),
        ("Windows 7", 7601),
        ("build 19045", 19045),
        ("", None),
        ("não sei", None),
    ],
)
def test_build_de_entende_o_que_o_site_escreve(texto, build):
    assert ins._build_de(texto) == build


# ---------------------------------------------------------------------------
# Baixar
# ---------------------------------------------------------------------------


def _falso_download(**kwargs) -> dict:
    alvo = ins.QUARENTENA / "ab12-setup.exe"
    alvo.write_bytes(_pe())
    return {"arquivo": str(alvo), "nome": "setup.exe", "bytes": 1024, "sha256": "a" * 64, "tipo": "x"}


def test_baixar_guarda_na_pasta_escolhida(monkeypatch):
    monkeypatch.setattr(ins, "maquina", lambda: _maquina())
    resultado = ins.baixar(
        url="https://exemplo.com/setup.exe",
        destino="programas",
        autorizacao="token",
        baixar_arquivo=_falso_download,
        conferir_assinatura=False,
    )
    final = Path(resultado["arquivo"])
    assert final.parent == ins.QUARENTENA / "programas"
    assert final.exists()
    assert resultado["veredito"] == "roda"
    assert resultado["sha256"] == "a" * 64


def test_baixar_nao_sobrescreve_arquivo_existente(monkeypatch):
    monkeypatch.setattr(ins, "maquina", lambda: _maquina())
    pasta = ins.QUARENTENA / "programas"
    pasta.mkdir(parents=True)
    (pasta / "ab12-setup.exe").write_bytes(b"antigo")
    resultado = ins.baixar(
        url="https://exemplo.com/setup.exe",
        destino="programas",
        autorizacao="token",
        baixar_arquivo=_falso_download,
        conferir_assinatura=False,
    )
    assert Path(resultado["arquivo"]).name != "ab12-setup.exe"
    assert (pasta / "ab12-setup.exe").read_bytes() == b"antigo"


def test_baixar_recusa_destino_que_sai_da_quarentena():
    with pytest.raises(ins.InstaladorError):
        ins.baixar(url="https://exemplo.com/x.exe", destino="../fora", autorizacao="t")


def test_baixar_repassa_o_erro_do_sistema(monkeypatch):
    def falha(**kwargs):
        raise sistema.SistemaError("trava de rede desligada")

    with pytest.raises(ins.InstaladorError) as erro:
        ins.baixar(url="https://exemplo.com/x.exe", autorizacao="t", baixar_arquivo=falha)
    assert "trava de rede" in str(erro.value)


def test_baixar_sem_arquivo_no_fim_recusa(monkeypatch):
    with pytest.raises(ins.InstaladorError):
        ins.baixar(
            url="https://exemplo.com/x.exe",
            autorizacao="t",
            baixar_arquivo=lambda **kwargs: {"arquivo": "/nao/existe.exe"},
        )


def test_quarentena_acompanha_o_modo_dados(monkeypatch, tmp_path):
    """`JARVIS_DADOS` troca `sistema.QUARENTENA` depois do import: não pode ficar preso."""
    destino = tmp_path / "outro-disco" / "host-downloads"
    monkeypatch.setattr(ins, "QUARENTENA", None)
    monkeypatch.setattr(ins.sistema_mod, "QUARENTENA", destino)
    assert ins._pasta("programas") == destino / "programas"
    assert ins._pasta("") == destino
    assert Path(ins.destinos()["pasta_base"]) == destino


def test_baixar_entende_o_retorno_aninhado_do_sistema(monkeypatch):
    """`sistema.baixar` devolve `download` dentro do resultado — e sem extensão no link."""
    monkeypatch.setattr(ins, "maquina", lambda: _maquina())

    def falso(**kwargs):
        alvo = ins.QUARENTENA / "abc-main"
        alvo.write_bytes(b"PK\x03\x04" + b"\x00" * 100)
        return {
            "executed": True,
            "download": {
                "arquivo": str(alvo),
                "bytes": 104,
                "sha256": "b" * 64,
                "tipo": "application/zip",
            },
        }

    resultado = ins.baixar(
        url="https://codeload.github.com/x/y/zip/refs/heads/main",
        destino="programas",
        autorizacao="token",
        baixar_arquivo=falso,
        conferir_assinatura=False,
    )
    assert Path(resultado["arquivo"]).name == "abc-main.zip"
    assert Path(resultado["arquivo"]).is_file()
    assert resultado["bytes"] == 104


def test_nome_com_extensao_respeita_nome_existente():
    assert ins._nome_com_extensao("setup.exe", "application/zip") == "setup.exe"
    assert ins._nome_com_extensao("main", "application/zip") == "main.zip"
    assert ins._nome_com_extensao("main", "application/x-msdownload") == "main.exe"
    assert ins._nome_com_extensao("main", "application/octet-stream") == "main"


def test_analisar_fora_do_windows_nao_promete_que_roda(tmp_path, monkeypatch):
    monkeypatch.setattr(ins, "_versao_windows", lambda: None)
    alvo = tmp_path / "setup.exe"
    alvo.write_bytes(_pe())
    resultado = ins.analisar(arquivo=str(alvo), conferir_assinatura=False)
    assert resultado["veredito"] == "não dá para saber"
    assert any("fora do Windows" in item for item in resultado["nao_verificado"])
    assert "Não estou no Windows" in resultado["resposta"]


def test_analisar_fora_do_windows_ainda_bloqueia_o_que_e_certo(tmp_path, monkeypatch):
    monkeypatch.setattr(ins, "_versao_windows", lambda: None)
    dados = bytearray(256)
    dados[0:2] = b"MZ"
    struct.pack_into("<I", dados, 0x3C, 0x40)
    dados[0x40:0x44] = b"NE\x00\x00"
    alvo = tmp_path / "velho.exe"
    alvo.write_bytes(bytes(dados))
    resultado = ins.analisar(arquivo=str(alvo), conferir_assinatura=False)
    assert resultado["veredito"] == "não roda"
