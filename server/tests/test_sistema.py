"""Testes da camada de host (0.30.0): disco, pastas, drivers, Bluetooth, rede e instalador.

A camada lê a máquina de verdade, então cada teste isola o diretório de estado
(token, quarentena e auditoria) num tmp_path e substitui as fontes voláteis —
`/proc`, PowerShell e rede — por fixtures. Nenhum teste abre socket de verdade.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import sistema as S
from server.app import create_app


@pytest.fixture(autouse=True)
def estado(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "STORAGE", tmp_path)
    monkeypatch.setattr(S, "TOKEN_ARQUIVO", tmp_path / "host-token.txt")
    monkeypatch.setattr(S, "QUARENTENA", tmp_path / "host-downloads")
    monkeypatch.setattr(S, "AUDITORIA", tmp_path / "host-audit.jsonl")
    monkeypatch.delenv(S.AMBIENTE_REDE, raising=False)
    monkeypatch.delenv(S.AMBIENTE_INSTALAR, raising=False)
    S._CONFIRMACAO.clear()
    yield tmp_path
    S._CONFIRMACAO.clear()


@pytest.fixture
def token(estado):
    return S.token_host()


@pytest.fixture
def rede_ligada(monkeypatch):
    monkeypatch.setenv(S.AMBIENTE_REDE, "1")


@pytest.fixture
def instalacao_ligada(monkeypatch):
    monkeypatch.setenv(S.AMBIENTE_REDE, "1")
    monkeypatch.setenv(S.AMBIENTE_INSTALAR, "1")


def _textos(resultado):
    return " ".join(item["title"] + " " + item["problem"] for item in resultado["findings"])


# ---------------------------------------------------------------------------
# Token de host
# ---------------------------------------------------------------------------


def test_token_e_criado_no_primeiro_uso(estado):
    token = S.token_host()
    assert len(token) >= 20
    assert (estado / "host-token.txt").read_text(encoding="utf-8").strip() == token


def test_token_e_estavel_entre_chamadas(estado):
    assert S.token_host() == S.token_host()


def test_token_existente_e_reaproveitado(estado):
    (estado / "host-token.txt").write_text("token-fixo-de-teste\n", encoding="utf-8")
    assert S.token_host() == "token-fixo-de-teste"


def test_token_vazio_no_arquivo_e_refeito(estado):
    (estado / "host-token.txt").write_text("   \n", encoding="utf-8")
    assert S.token_host() != ""


def test_sem_token_a_leitura_e_recusada():
    with pytest.raises(S.SistemaError, match="token"):
        S.disco(autorizacao="")


def test_token_errado_e_recusado(token):
    with pytest.raises(S.SistemaError, match="inválido"):
        S.disco(autorizacao="outro-valor")


def test_token_aceita_espaco_em_volta(token):
    assert S.disco(autorizacao=f"  {token}  ")["readOnly"] is True


def test_capacidades_esconde_o_token(monkeypatch):
    dados = S.capacidades()
    assert "token_configurado" in dados
    assert "shell_livre" in dados
    assert S.capacidades()["rede"] is False


def test_capacidades_reflete_as_variaveis(monkeypatch):
    monkeypatch.setenv(S.AMBIENTE_REDE, "1")
    monkeypatch.setenv(S.AMBIENTE_INSTALAR, "1")
    dados = S.capacidades()
    assert dados["rede"] is True and dados["instalar"] is True


# ---------------------------------------------------------------------------
# Ambiente
# ---------------------------------------------------------------------------


def test_ambiente_devolve_linhas_do_sistema(token):
    dados = S.ambiente(autorizacao=token)
    chaves = [linha["chave"] for linha in dados["rows"]]
    assert "Sistema" in chaves and "Núcleos" in chaves and "Python" in chaves
    assert dados["executed"] is False and dados["readOnly"] is True


def test_ambiente_detecta_container(monkeypatch, token):
    monkeypatch.setattr(S, "_container", lambda: {"provavel": True, "evidencias": ["/.dockerenv presente"]})
    dados = S.ambiente(autorizacao=token)
    assert dados["metrics"]["container"] is True
    assert "contêiner" in _textos(dados)


def test_ambiente_sem_container_nao_alerta(monkeypatch, token):
    monkeypatch.setattr(S, "_container", lambda: {"provavel": False, "evidencias": []})
    dados = S.ambiente(autorizacao=token)
    assert dados["metrics"]["container"] is False


def test_ambiente_avisa_rede_desligada(token):
    dados = S.ambiente(autorizacao=token)
    assert any(item["location"] == S.AMBIENTE_REDE for item in dados["findings"])


def test_ambiente_avisa_instalacao_desligada(token):
    dados = S.ambiente(autorizacao=token)
    assert any(item["location"] == S.AMBIENTE_INSTALAR for item in dados["findings"])


def test_ambiente_modo_lite_so_traz_must(monkeypatch, token):
    monkeypatch.setattr(S, "_container", lambda: {"provavel": True, "evidencias": []})
    dados = S.ambiente(autorizacao=token, modo="lite")
    assert all(item["group"] == "must" for item in dados["findings"])


def test_ambiente_modo_invalido(token):
    with pytest.raises(S.SistemaError, match="Modo"):
        S.ambiente(autorizacao=token, modo="turbo")


def test_ambiente_ultra_devolve_perguntas(token):
    dados = S.ambiente(autorizacao=token, modo="ultra")
    assert dados["questions"]


# ---------------------------------------------------------------------------
# Disco
# ---------------------------------------------------------------------------


def _montagem(monkeypatch, itens):
    monkeypatch.setattr(S, "_montagens_posix", lambda: itens)


def test_disco_mede_montagem_real(monkeypatch, token, tmp_path):
    _montagem(monkeypatch, [{"dispositivo": "/dev/sda1", "ponto": str(tmp_path), "tipo": "ext4", "volatil": False}])
    dados = S.disco(autorizacao=token)
    assert dados["metrics"]["unidades"] == 1
    linha = dados["rows"][0]
    assert linha["total"] > 0 and 0 <= linha["livrePct"] <= 100


def test_disco_soma_total_e_livre(monkeypatch, token, tmp_path):
    _montagem(monkeypatch, [{"dispositivo": "/dev/sda1", "ponto": str(tmp_path), "tipo": "ext4", "volatil": False}])
    dados = S.disco(autorizacao=token)
    assert dados["metrics"]["usado"] + dados["metrics"]["livre"] == dados["metrics"]["total"]


def test_disco_alerta_em_disco_quase_cheio(monkeypatch, token, tmp_path):
    class Uso:
        total = 1000
        used = 980
        free = 20

    _montagem(monkeypatch, [{"dispositivo": "x", "ponto": str(tmp_path), "tipo": "ext4", "volatil": False}])
    monkeypatch.setattr(S.shutil, "disk_usage", lambda _ponto: Uso())
    dados = S.disco(autorizacao=token)
    assert any("cheio" in item["title"].lower() for item in dados["findings"])
    assert dados["metrics"]["menorLivrePct"] == 2


def test_disco_alerta_em_pouco_espaco(monkeypatch, token, tmp_path):
    class Uso:
        total = 1000
        used = 880
        free = 120

    _montagem(monkeypatch, [{"dispositivo": "x", "ponto": str(tmp_path), "tipo": "ext4", "volatil": False}])
    monkeypatch.setattr(S.shutil, "disk_usage", lambda _ponto: Uso())
    dados = S.disco(autorizacao=token)
    assert any(item["group"] == "should" for item in dados["findings"])


def test_disco_ignora_volatil_no_alerta(monkeypatch, token, tmp_path):
    class Uso:
        total = 1000
        used = 990
        free = 10

    _montagem(monkeypatch, [{"dispositivo": "tmpfs", "ponto": str(tmp_path), "tipo": "tmpfs", "volatil": True}])
    monkeypatch.setattr(S.shutil, "disk_usage", lambda _ponto: Uso())
    dados = S.disco(autorizacao=token)
    assert dados["findings"] == []
    assert dados["rows"][0]["volatil"] is True


def test_disco_nao_lista_filesystem_pseudo(monkeypatch, token, tmp_path):
    texto = "\n".join(
        [
            f"proc /proc proc rw 0 0",
            f"selinuxfs /sys/fs/selinux selinuxfs rw 0 0",
            f"ramfs /run/credentials/x ramfs rw 0 0",
        ]
    )
    monkeypatch.setattr(S, "_ler_arquivo", lambda *_a, **_k: texto)
    assert S._montagens_posix() == []


def test_disco_deduplica_bind_do_mesmo_dispositivo(monkeypatch, token, tmp_path):
    texto = f"/dev/sda {tmp_path} ext4 rw 0 0\n/dev/sda {tmp_path} ext4 rw 0 0\n"
    monkeypatch.setattr(S, "_ler_arquivo", lambda *_a, **_k: texto)
    assert len(S._montagens_posix()) == 1


def test_disco_ignora_total_zero(monkeypatch, token, tmp_path):
    class Uso:
        total = 0
        used = 0
        free = 0

    _montagem(monkeypatch, [{"dispositivo": "x", "ponto": str(tmp_path), "tipo": "ext4", "volatil": False}])
    monkeypatch.setattr(S.shutil, "disk_usage", lambda _ponto: Uso())
    dados = S.disco(autorizacao=token)
    assert dados["metrics"]["unidades"] == 0


def test_disco_caminho_informado_sem_leitura(monkeypatch, token):
    def falhar(_ponto):
        raise PermissionError

    monkeypatch.setattr(S.shutil, "disk_usage", falhar)
    dados = S.disco(caminhos="/inexistente", autorizacao=token)
    assert any("sem leitura" in item["title"].lower() for item in dados["findings"])


def test_disco_filtra_por_minimo(monkeypatch, token, tmp_path):
    class Uso:
        total = 1000
        used = 100
        free = 900

    _montagem(monkeypatch, [{"dispositivo": "x", "ponto": str(tmp_path), "tipo": "ext4", "volatil": False}])
    monkeypatch.setattr(S.shutil, "disk_usage", lambda _ponto: Uso())
    assert S.disco(autorizacao=token, minimo=95)["rows"] == []


def test_disco_sem_unidade_alerta(monkeypatch, token):
    _montagem(monkeypatch, [])
    dados = S.disco(autorizacao=token)
    assert any("nenhuma unidade" in item["title"].lower() for item in dados["findings"])


# ---------------------------------------------------------------------------
# Pastas
# ---------------------------------------------------------------------------


@pytest.fixture
def arvore(tmp_path):
    raiz = tmp_path / "raiz"
    (raiz / "sub" / "fundo").mkdir(parents=True)
    (raiz / "a.txt").write_text("aaa", encoding="utf-8")
    (raiz / "sub" / "b.md").write_text("bbbb", encoding="utf-8")
    (raiz / "sub" / "fundo" / "c.log").write_text("c", encoding="utf-8")
    (raiz / ".oculto").write_text("x", encoding="utf-8")
    return raiz


def test_pastas_lista_nome_tipo_e_tamanho(arvore, token):
    dados = S.pastas(raiz=str(arvore), profundidade=0, autorizacao=token)
    por_nome = {linha["nome"]: linha for linha in dados["rows"]}
    assert por_nome["a.txt"]["tipo"] == "arquivo" and por_nome["a.txt"]["bytes"] == 3
    assert por_nome["sub"]["tipo"] == "pasta"


def test_pastas_nao_le_conteudo(arvore, token):
    dados = S.pastas(raiz=str(arvore), profundidade=2, autorizacao=token)
    texto = json.dumps(dados, ensure_ascii=False)
    assert "aaa" not in texto and "bbbb" not in texto


def test_pastas_respeita_profundidade(arvore, token):
    dados = S.pastas(raiz=str(arvore), profundidade=0, autorizacao=token)
    nomes = {linha["nome"] for linha in dados["rows"]}
    assert "b.md" not in nomes and "sub" in nomes


def test_pastas_desce_ate_a_profundidade(arvore, token):
    dados = S.pastas(raiz=str(arvore), profundidade=3, autorizacao=token)
    assert "c.log" in {linha["nome"] for linha in dados["rows"]}


def test_pastas_oculta_por_padrao(arvore, token):
    dados = S.pastas(raiz=str(arvore), profundidade=1, autorizacao=token)
    assert ".oculto" not in {linha["nome"] for linha in dados["rows"]}


def test_pastas_inclui_ocultos_quando_pedido(arvore, token):
    dados = S.pastas(raiz=str(arvore), profundidade=1, incluir_ocultos=True, autorizacao=token)
    assert ".oculto" in {linha["nome"] for linha in dados["rows"]}


def test_pastas_trunca_no_limite(arvore, token):
    dados = S.pastas(raiz=str(arvore), profundidade=4, limite=2, autorizacao=token)
    assert len(dados["rows"]) == 2
    assert dados["metrics"]["truncado"] is True


def test_pastas_alerta_truncamento(arvore, token):
    dados = S.pastas(raiz=str(arvore), profundidade=4, limite=1, autorizacao=token)
    assert any("truncada" in item["title"].lower() for item in dados["findings"])


def test_pastas_profundidade_limitada(arvore, token):
    dados = S.pastas(raiz=str(arvore), profundidade=99, autorizacao=token)
    assert dados["metrics"]["profundidade"] == S.MAX_PROFUNDIDADE


def test_pastas_caminho_inexistente(token):
    with pytest.raises(S.SistemaError, match="não existe"):
        S.pastas(raiz="/caminho/que/nao/existe", autorizacao=token)


def test_pastas_arquivo_como_raiz(arvore, token):
    with pytest.raises(S.SistemaError, match="Não é uma pasta"):
        S.pastas(raiz=str(arvore / "a.txt"), autorizacao=token)


def test_pastas_reconhece_cofre_pelo_nome(tmp_path, token):
    raiz = tmp_path / "home"
    (raiz / ".ssh").mkdir(parents=True)
    (raiz / ".ssh" / "id_rsa").write_text("segredo", encoding="utf-8")
    dados = S.pastas(raiz=str(raiz), profundidade=2, incluir_ocultos=True, autorizacao=token)
    protegidos = [linha for linha in dados["rows"] if linha["protegido"]]
    assert protegidos
    assert all(linha["bytes"] == 0 for linha in protegidos if linha["tipo"] == "arquivo")
    assert "segredo" not in json.dumps(dados)


def test_pastas_chave_e_reconhecida(tmp_path, token):
    assert S._protegido(tmp_path / "chave.pem") is True
    assert S._protegido(tmp_path / "arquivo.txt") is False


def test_pastas_link_simbolico_nao_e_seguido(tmp_path, token):
    raiz = tmp_path / "raiz"
    raiz.mkdir()
    (raiz / "real").mkdir()
    (raiz / "atalho").symlink_to(raiz / "real")
    dados = S.pastas(raiz=str(raiz), profundidade=2, autorizacao=token)
    atalho = next(linha for linha in dados["rows"] if linha["nome"] == "atalho")
    assert atalho["tipo"] == "link"


def test_pastas_vazia_avisa(tmp_path, token):
    raiz = tmp_path / "vazia"
    raiz.mkdir()
    dados = S.pastas(raiz=str(raiz), autorizacao=token)
    assert any("vazia" in item["title"].lower() for item in dados["findings"])


def test_pastas_sem_permissao_conta_negado(tmp_path, token, monkeypatch):
    raiz = tmp_path / "raiz"
    raiz.mkdir()
    (raiz / "x.txt").write_text("x", encoding="utf-8")
    original = os.scandir

    def negar(caminho):
        if str(caminho).endswith("raiz"):
            raise PermissionError
        return original(caminho)

    monkeypatch.setattr(S.os, "scandir", negar)
    dados = S.pastas(raiz=str(raiz), autorizacao=token)
    assert dados["metrics"]["negados"] == 1


# ---------------------------------------------------------------------------
# Drivers
# ---------------------------------------------------------------------------


def test_drivers_le_modulos_do_kernel(monkeypatch, token):
    texto = "snd_hda_intel 573440 3 - Live 0x0000000000000000\nbtusb 61440 0 - Live 0x0\n"
    monkeypatch.setattr(S.platform, "system", lambda: "Linux")
    monkeypatch.setattr(S, "_ler_arquivo", lambda caminho, *_a, **_k: texto if "modules" in str(caminho) else "")
    dados = S.drivers(autorizacao=token)
    assert dados["metrics"]["itens"] == 2
    assert dados["rows"][0]["nome"] == "snd_hda_intel"
    assert dados["rows"][0]["bytes"] == 573440


def test_drivers_filtra_por_nome(monkeypatch, token):
    texto = "snd_hda_intel 573440 3 - Live 0x0\nbtusb 61440 0 - Live 0x0\n"
    monkeypatch.setattr(S.platform, "system", lambda: "Linux")
    monkeypatch.setattr(S, "_ler_arquivo", lambda caminho, *_a, **_k: texto if "modules" in str(caminho) else "")
    dados = S.drivers(filtro="bt", autorizacao=token)
    assert [linha["nome"] for linha in dados["rows"]] == ["btusb"]


def test_drivers_windows_parseia_json(monkeypatch, token):
    saida = json.dumps(
        [
            {"DeviceName": "Intel Bluetooth", "DriverVersion": "22.1", "DriverProviderName": "Intel", "IsSigned": True},
            {"DeviceName": "Adaptador RTL", "DriverVersion": "", "DriverProviderName": "Realtek", "IsSigned": False},
        ]
    )
    monkeypatch.setattr(S.platform, "system", lambda: "Windows")
    monkeypatch.setattr(S, "_rodar", lambda *_a, **_k: (0, saida, ""))
    dados = S.drivers(autorizacao=token)
    assert dados["metrics"]["itens"] == 2
    assert dados["metrics"]["naoAssinados"] == 1


def test_drivers_windows_sem_powershell(monkeypatch, token):
    monkeypatch.setattr(S.platform, "system", lambda: "Windows")
    monkeypatch.setattr(S, "_rodar", lambda *_a, **_k: (127, "", "comando não encontrado"))
    dados = S.drivers(autorizacao=token)
    assert any("indisponível" in item["title"].lower() for item in dados["findings"])


def test_drivers_windows_json_invalido(monkeypatch, token):
    monkeypatch.setattr(S.platform, "system", lambda: "Windows")
    monkeypatch.setattr(S, "_rodar", lambda *_a, **_k: (0, "não é json", ""))
    assert S._drivers_windows()[0] == []


def test_drivers_plataforma_sem_fonte(monkeypatch, token):
    monkeypatch.setattr(S.platform, "system", lambda: "Darwin")
    dados = S.drivers(autorizacao=token)
    assert dados["metrics"]["itens"] == 0
    assert any("nenhum driver" in item["title"].lower() for item in dados["findings"])


def test_drivers_sem_versao_gera_achado(monkeypatch, token):
    texto = "modulo_sem_versao 1024 0 - Live 0x0\n"
    monkeypatch.setattr(S.platform, "system", lambda: "Linux")
    monkeypatch.setattr(S, "_ler_arquivo", lambda caminho, *_a, **_k: texto if "modules" in str(caminho) else "")
    dados = S.drivers(autorizacao=token)
    assert dados["metrics"]["semVersao"] == 1


def test_drivers_nao_executa_shell(monkeypatch, token):
    chamadas = []
    monkeypatch.setattr(S.platform, "system", lambda: "Linux")
    monkeypatch.setattr(S, "_ler_arquivo", lambda *_a, **_k: "")
    monkeypatch.setattr(S.subprocess, "run", lambda *a, **k: chamadas.append(a) or (_ for _ in ()).throw(AssertionError("shell")))
    S.drivers(autorizacao=token)
    assert chamadas == []


# ---------------------------------------------------------------------------
# Bluetooth
# ---------------------------------------------------------------------------


def test_bluetooth_linux_le_adaptadores(monkeypatch, token, tmp_path):
    base = tmp_path / "bluetooth"
    adaptador = base / "hci0"
    adaptador.mkdir(parents=True)
    (adaptador / "address").write_text("AA:BB:CC:DD:EE:FF", encoding="utf-8")
    monkeypatch.setattr(S.platform, "system", lambda: "Linux")
    monkeypatch.setattr(S, "_adaptadores_linux", lambda: S._adaptadores_linux.__wrapped__(base) if hasattr(S._adaptadores_linux, "__wrapped__") else [{"nome": "hci0", "tipo": "adaptador", "endereco": "AA:BB:CC:DD:EE:FF"}])
    dados = S.bluetooth(autorizacao=token)
    assert dados["metrics"]["adaptadores"] == 1


def test_bluetooth_sem_adaptador_alerta(monkeypatch, token):
    monkeypatch.setattr(S.platform, "system", lambda: "Linux")
    monkeypatch.setattr(S, "_adaptadores_linux", lambda: [])
    monkeypatch.setattr(S, "_emparelhados_linux", lambda: [])
    dados = S.bluetooth(autorizacao=token)
    assert any("nenhum adaptador" in item["title"].lower() for item in dados["findings"])
    assert dados["counts"]["must"] == 1


def test_bluetooth_adaptador_sem_pareamento(monkeypatch, token):
    monkeypatch.setattr(S.platform, "system", lambda: "Linux")
    monkeypatch.setattr(S, "_adaptadores_linux", lambda: [{"nome": "hci0", "tipo": "adaptador", "endereco": "AA"}])
    monkeypatch.setattr(S, "_emparelhados_linux", lambda: [])
    dados = S.bluetooth(autorizacao=token)
    assert any("pareado" in item["title"].lower() for item in dados["findings"])


def test_bluetooth_adaptador_desligado(monkeypatch, token):
    monkeypatch.setattr(S.platform, "system", lambda: "Linux")
    monkeypatch.setattr(S, "_adaptadores_linux", lambda: [{"nome": "hci0", "tipo": "adaptador", "estado": "disabled"}])
    monkeypatch.setattr(S, "_emparelhados_linux", lambda: [{"nome": "fone", "mac": "11"}])
    dados = S.bluetooth(autorizacao=token)
    assert any("desligado" in item["title"].lower() for item in dados["findings"])


def test_bluetooth_windows_parseia(monkeypatch, token):
    saida = json.dumps(
        [
            {"FriendlyName": "Intel Bluetooth", "Status": "OK", "InstanceId": "USB\\VID_8087"},
            {"FriendlyName": "Fone BT", "Status": "OK", "InstanceId": "BTHENUM\\XX"},
        ]
    )
    monkeypatch.setattr(S.platform, "system", lambda: "Windows")
    monkeypatch.setattr(S, "_rodar", lambda *_a, **_k: (0, saida, ""))
    dados = S.bluetooth(autorizacao=token)
    assert dados["metrics"]["adaptadores"] == 1
    assert dados["metrics"]["emparelhados"] == 1


def test_bluetooth_filtro(monkeypatch, token):
    monkeypatch.setattr(S.platform, "system", lambda: "Linux")
    monkeypatch.setattr(S, "_adaptadores_linux", lambda: [{"nome": "hci0", "tipo": "adaptador"}])
    monkeypatch.setattr(S, "_emparelhados_linux", lambda: [{"nome": "Galaxy Buds", "mac": "11"}])
    dados = S.bluetooth(filtro="galaxy", autorizacao=token)
    assert len(dados["rows"]) == 1


def test_bluetooth_nao_pareia(monkeypatch, token):
    monkeypatch.setattr(S.platform, "system", lambda: "Linux")
    monkeypatch.setattr(S, "_adaptadores_linux", lambda: [])
    monkeypatch.setattr(S, "_emparelhados_linux", lambda: [])
    texto = " ".join(S.bluetooth(autorizacao=token)["limitations"]).lower()
    assert "não pareia" in texto or "não inicia varredura" in texto


# ---------------------------------------------------------------------------
# Rede: guardas de URL
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://127.0.0.1:8000/api/health",
        "http://10.0.0.1/",
        "http://192.168.0.1/",
        "http://172.16.0.1/",
        "http://169.254.1.1/",
        "http://0.0.0.0/",
        "http://printer.local/",
    ],
)
def test_rede_bloqueia_endereco_privado(url):
    with pytest.raises(S.SistemaError):
        S._url_segura(url)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/x", "javascript:alert(1)", ""])
def test_rede_so_aceita_http(url):
    with pytest.raises(S.SistemaError):
        S._url_segura(url)


def test_rede_host_que_nao_resolve():
    with pytest.raises(S.SistemaError, match="resolve"):
        S._url_segura("https://dominio-que-nao-existe-zzz.invalid/")


def test_rede_host_publico_passa():
    assert S._url_segura("https://example.com/") == "https://example.com/"


def test_rede_desligada_recusa(monkeypatch, token):
    with pytest.raises(S.SistemaError, match="Rede desligada"):
        S.rede(acao="buscar", consulta="x", autorizacao=token)


def test_rede_busca_nao_pede_token(monkeypatch, rede_ligada):
    """Pesquisar é leitura: a trava que vale é a rede ligada, não o token."""
    monkeypatch.setattr(
        S.busca_web,
        "buscar",
        lambda *_a, **_k: {"consulta": "x", "fonte": "auto", "resultados": [], "responderam": [], "falhas": []},
    )
    dados = S.rede(acao="buscar", consulta="x", autorizacao="")
    assert dados["readOnly"] is True


def test_baixar_continua_exigindo_token(rede_ligada):
    with pytest.raises(S.SistemaError, match="token"):
        S.baixar(url="https://example.com/a.msi", autorizacao="")


def test_rede_acao_invalida(rede_ligada, token):
    with pytest.raises(S.SistemaError, match="Ação inválida"):
        S.rede(acao="baixar", url="https://example.com/a.msi", autorizacao=token)


def test_rede_busca_sem_consulta(rede_ligada, token):
    with pytest.raises(S.SistemaError, match="consulta"):
        S.rede(acao="buscar", consulta="  ", autorizacao=token)


def test_rede_busca_devolve_linhas(monkeypatch, rede_ligada):
    monkeypatch.setattr(
        S.busca_web,
        "buscar",
        lambda *_a, **_k: {
            "consulta": "driver bluetooth",
            "fonte": "auto",
            "resultados": [
                {"titulo": "Driver Bluetooth", "url": "https://exemplo.com/driver", "fonte": "duckduckgo", "tipo": "site"}
            ],
            "responderam": ["duckduckgo"],
            "falhas": [],
        },
    )
    dados = S.rede(acao="buscar", consulta="driver bluetooth")
    assert dados["rows"][0]["titulo"] == "Driver Bluetooth"
    assert dados["rows"][0]["fonte"] == "duckduckgo"
    assert dados["executed"] is False and dados["readOnly"] is True


def test_rede_busca_vazia_alerta(monkeypatch, rede_ligada):
    monkeypatch.setattr(
        S.busca_web,
        "buscar",
        lambda *_a, **_k: {"consulta": "nada", "fonte": "auto", "resultados": [], "responderam": [], "falhas": []},
    )
    dados = S.rede(acao="buscar", consulta="nada")
    assert any("sem resultado" in item["title"].lower() for item in dados["findings"])


def test_rede_olhar_extrai_texto(monkeypatch, rede_ligada, token):
    monkeypatch.setattr(
        S,
        "_baixar_texto",
        lambda *_a, **_k: ("<html><body><p>Olá <b>mundo</b></p><script>x()</script></body></html>", "text/html", 200),
    )
    dados = S.rede(acao="olhar", url="https://example.com/", autorizacao=token)
    assert "Olá mundo" in dados["markdown"]
    assert "x()" not in dados["markdown"]


def test_texto_de_html_remove_tag_e_entidade():
    assert S._texto_de_html("<p>a&nbsp;&amp;&nbsp;b</p>") == "a & b"


def test_rede_olhar_pagina_grande_recusa(monkeypatch, rede_ligada, token):
    monkeypatch.setattr(S, "MAX_PAGINA", 10)
    monkeypatch.setattr(S, "urlopen", lambda *_a, **_k: _Resposta(b"x" * 100, "text/html", 200))
    with pytest.raises(S.SistemaError, match="maior"):
        S.rede(acao="olhar", url="https://example.com/", autorizacao=token)


class _Resposta:
    """Resposta HTTP falsa que consome o buffer como um socket de verdade."""

    def __init__(self, dados, tipo, status):
        self._dados = dados
        self._posicao = 0
        self.status = status
        self.headers = {"content-type": tipo}

    def read(self, limite=-1):
        if limite < 0:
            bloco = self._dados[self._posicao :]
        else:
            bloco = self._dados[self._posicao : self._posicao + limite]
        self._posicao += len(bloco)
        return bloco

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


def test_baixar_exige_rede(monkeypatch, token):
    with pytest.raises(S.SistemaError, match="Rede desligada"):
        S.baixar(url="https://example.com/a.msi", autorizacao=token)


def test_baixar_grava_na_quarentena(monkeypatch, rede_ligada, token, estado):
    monkeypatch.setattr(S, "urlopen", lambda *_a, **_k: _Resposta(b"conteudo", "application/octet-stream", 200))
    dados = S.baixar(url="https://example.com/fone.msi", autorizacao=token)
    arquivo = Path(dados["download"]["arquivo"])
    assert arquivo.exists() and arquivo.read_bytes() == b"conteudo"
    assert arquivo.parent == estado / "host-downloads"
    assert len(dados["download"]["sha256"]) == 64


def test_baixar_marca_executado(monkeypatch, rede_ligada, token):
    monkeypatch.setattr(S, "urlopen", lambda *_a, **_k: _Resposta(b"x", "application/octet-stream", 200))
    dados = S.baixar(url="https://example.com/a.msi", autorizacao=token)
    assert dados["executed"] is True and dados["readOnly"] is False


def test_baixar_registra_auditoria(monkeypatch, rede_ligada, token, estado):
    monkeypatch.setattr(S, "urlopen", lambda *_a, **_k: _Resposta(b"x", "application/octet-stream", 200))
    S.baixar(url="https://example.com/a.msi", autorizacao=token)
    linhas = (estado / "host-audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(linhas[0])["acao"] == "baixar"


def test_baixar_recusa_acima_do_limite(monkeypatch, rede_ligada, token):
    monkeypatch.setattr(S, "MAX_DOWNLOAD", 4)
    monkeypatch.setattr(S, "urlopen", lambda *_a, **_k: _Resposta(b"123456789", "application/octet-stream", 200))
    with pytest.raises(S.SistemaError, match="maior"):
        S.baixar(url="https://example.com/a.msi", autorizacao=token)


def test_baixar_vazio_alerta(monkeypatch, rede_ligada, token):
    monkeypatch.setattr(S, "urlopen", lambda *_a, **_k: _Resposta(b"", "application/octet-stream", 200))
    dados = S.baixar(url="https://example.com/a.msi", autorizacao=token)
    assert any("vazio" in item["title"].lower() for item in dados["findings"])


def test_baixar_extensao_desconhecida_alerta(monkeypatch, rede_ligada, token):
    monkeypatch.setattr(S, "urlopen", lambda *_a, **_k: _Resposta(b"x", "text/plain", 200))
    dados = S.baixar(url="https://example.com/leiame.txt", autorizacao=token)
    assert any("não é instalador" in item["title"].lower() for item in dados["findings"])


def test_baixar_nome_perigoso_e_sanitizado(monkeypatch, rede_ligada, token, estado):
    monkeypatch.setattr(S, "urlopen", lambda *_a, **_k: _Resposta(b"x", "application/octet-stream", 200))
    dados = S.baixar(url="https://example.com/..%2F..%2Fetc%2Fpasswd.msi", autorizacao=token)
    arquivo = Path(dados["download"]["arquivo"])
    assert arquivo.parent == estado / "host-downloads"
    assert "/" not in arquivo.name.replace(str(arquivo.parent), "")


# ---------------------------------------------------------------------------
# Instalação
# ---------------------------------------------------------------------------


def _baixar_fake(estado, nome="fone.msi", dados=b"abc"):
    pasta = estado / "host-downloads"
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"0000-{nome}"
    arquivo.write_bytes(dados)
    return arquivo


def test_instalar_planeja_pip(token):
    dados = S.instalar(pacote="pip:rich", autorizacao=token)
    assert dados["rows"][2]["valor"].endswith("-m pip install rich")
    assert dados["executed"] is False and dados["readOnly"] is True
    assert len(dados["confirmacao"]) == 8


def test_instalar_planeja_npm(token):
    dados = S.instalar(pacote="npm:typescript", autorizacao=token)
    assert dados["rows"][2]["valor"] == "npm install typescript"


@pytest.mark.parametrize("nome", ["foo; rm -rf /", "a b", "$(whoami)", "a|b", "a&&b", "a`b`"])
def test_instalar_recusa_metacaractere(token, nome):
    with pytest.raises(S.SistemaError, match="inválido"):
        S.instalar(pacote=f"pip:{nome}", autorizacao=token)


def test_instalar_exige_arquivo_ou_pacote(token):
    with pytest.raises(S.SistemaError, match="Informe"):
        S.instalar(autorizacao=token)


def test_instalar_recusa_arquivo_fora_da_quarentena(token):
    with pytest.raises(S.SistemaError, match="quarentena"):
        S.instalar(arquivo="/etc/passwd", autorizacao=token)


def test_instalar_aceita_arquivo_da_quarentena(estado, token):
    arquivo = _baixar_fake(estado)
    dados = S.instalar(arquivo=str(arquivo), autorizacao=token)
    assert dados["metrics"]["tipo"] == "msi"
    assert dados["metrics"]["risco"] == "médio"


def test_instalar_recusa_extensao_nao_suportada(estado, token):
    arquivo = _baixar_fake(estado, nome="pacote.zip")
    with pytest.raises(S.SistemaError, match="Extensão"):
        S.instalar(arquivo=str(arquivo), autorizacao=token)


def test_instalar_exe_tem_risco_alto(estado, token):
    arquivo = _baixar_fake(estado, nome="setup.exe")
    dados = S.instalar(arquivo=str(arquivo), autorizacao=token)
    assert dados["metrics"]["risco"] == "alto"
    assert dados["counts"]["must"] >= 1


def test_instalar_appimage_nao_tem_comando(estado, token):
    arquivo = _baixar_fake(estado, nome="app.AppImage")
    dados = S.instalar(arquivo=str(arquivo), autorizacao=token)
    assert dados["rows"][2]["valor"] == "(somente chmod +x)"


def test_instalar_avisa_trava_desligada(estado, token):
    arquivo = _baixar_fake(estado)
    dados = S.instalar(arquivo=str(arquivo), autorizacao=token)
    assert any(item["location"] == S.AMBIENTE_INSTALAR for item in dados["findings"])


def test_instalar_token_e_unico_por_plano(estado, token):
    a = S.instalar(pacote="pip:a", autorizacao=token)["confirmacao"]
    b = S.instalar(pacote="pip:a", autorizacao=token)["confirmacao"]
    assert a != b


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------


def test_executar_exige_trava(estado, rede_ligada, token):
    token_plano = S.instalar(pacote="pip:rich", autorizacao=token)["confirmacao"]
    with pytest.raises(S.SistemaError, match="Instalação desligada"):
        S.executar(confirmacao=token_plano, autorizacao=token)


def test_executar_confirmacao_desconhecida(instalacao_ligada, token):
    with pytest.raises(S.SistemaError, match="desconhecida"):
        S.executar(confirmacao="deadbeef", autorizacao=token)


def test_executar_confirma_e_roda(monkeypatch, instalacao_ligada, token):
    chamadas = []

    def falso(comando, timeout=20):
        chamadas.append(comando)
        return 0, "ok", ""

    monkeypatch.setattr(S, "_rodar", falso)
    token_plano = S.instalar(pacote="pip:rich", autorizacao=token)["confirmacao"]
    dados = S.executar(confirmacao=token_plano, autorizacao=token)
    assert dados["executed"] is True and dados["readOnly"] is False
    assert dados["metrics"]["codigo"] == 0
    assert chamadas and chamadas[0][-2:] == ["install", "rich"]


def test_executar_token_serve_uma_vez(monkeypatch, instalacao_ligada, token):
    monkeypatch.setattr(S, "_rodar", lambda *_a, **_k: (0, "", ""))
    token_plano = S.instalar(pacote="pip:rich", autorizacao=token)["confirmacao"]
    S.executar(confirmacao=token_plano, autorizacao=token)
    with pytest.raises(S.SistemaError, match="desconhecida"):
        S.executar(confirmacao=token_plano, autorizacao=token)


def test_executar_token_expirado(monkeypatch, instalacao_ligada, token):
    token_plano = S.instalar(pacote="pip:rich", autorizacao=token)["confirmacao"]
    S._CONFIRMACAO[token_plano]["expira"] = time.time() - 1
    with pytest.raises(S.SistemaError, match="expirada"):
        S.executar(confirmacao=token_plano, autorizacao=token)


def test_executar_codigo_diferente_de_zero_alerta(monkeypatch, instalacao_ligada, token):
    monkeypatch.setattr(S, "_rodar", lambda *_a, **_k: (1, "", "falhou"))
    token_plano = S.instalar(pacote="pip:rich", autorizacao=token)["confirmacao"]
    dados = S.executar(confirmacao=token_plano, autorizacao=token)
    assert any("erro" in item["title"].lower() for item in dados["findings"])


def test_executar_registra_auditoria(monkeypatch, instalacao_ligada, token, estado):
    monkeypatch.setattr(S, "_rodar", lambda *_a, **_k: (0, "", ""))
    token_plano = S.instalar(pacote="pip:rich", autorizacao=token)["confirmacao"]
    S.executar(confirmacao=token_plano, autorizacao=token)
    linhas = (estado / "host-audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(linhas[-1])["acao"] == "instalar"


def test_executar_appimage_so_marca_executavel(estado, instalacao_ligada, token):
    arquivo = _baixar_fake(estado, nome="app.AppImage")
    token_plano = S.instalar(arquivo=str(arquivo), autorizacao=token)["confirmacao"]
    dados = S.executar(confirmacao=token_plano, autorizacao=token)
    assert dados["execucao"]["acao"] == "chmod"
    assert os.access(arquivo, os.X_OK)


def test_e_rodar_comando_inexistente_devolve_127():
    assert S._rodar(["binario-que-nao-existe-zzz"])[0] == 127


def test_e_rodar_respeita_timeout(monkeypatch):
    import subprocess

    def estourar(*_a, **_k):
        raise subprocess.TimeoutExpired("x", 1)

    monkeypatch.setattr(S.subprocess, "run", estourar)
    assert S._rodar(["x"], timeout=1)[0] == 124


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------


def test_catalogo_lista_doze_operacoes():
    dados = S.catalogo()
    assert len(dados["operacoes"]) == 12


def test_catalogo_lista_cinco_guardas():
    assert len(S.catalogo()["guardas"]) == 5


def test_catalogo_declara_o_que_nao_faz():
    texto = " ".join(S.catalogo()["nao_faz"]).lower()
    assert "shell livre" in texto and "reputação" in texto and "bluetooth" in texto


def test_catalogo_aponta_a_elevacao_em_vez_de_negala():
    texto = " ".join(S.catalogo()["nao_faz"]).lower()
    assert "não eleva privilégio nesta camada" in texto
    assert "sistema.elevar" in texto and "host-audit.jsonl" in texto


def test_catalogo_publica_as_cinco_fontes_de_verificacao():
    dados = S.catalogo()["verificacao_de_assinatura"]
    assert set(dados) == {"windows", "linux_rpm", "linux_deb", "destacada", "hash", "revalidacao"}


def test_catalogo_nao_expoe_token():
    assert S.token_host() not in json.dumps(S.catalogo())


def test_catalogo_e_somente_leitura():
    dados = S.catalogo()
    assert dados["executed"] is False and dados["readOnly"] is True


# ---------------------------------------------------------------------------
# Assinatura e integridade
# ---------------------------------------------------------------------------


def _arquivo(estado, nome="fone.msi", dados=b"conteudo"):
    return _baixar_fake(estado, nome=nome, dados=dados)


def test_assinatura_calcula_sha256(estado, token):
    alvo = _arquivo(estado)
    dados = S.assinatura(arquivo=str(alvo), autorizacao=token)
    assert dados["metrics"]["sha256"] == hashlib.sha256(b"conteudo").hexdigest()
    assert dados["metrics"]["bytes"] == 8


def test_assinatura_hash_confere(estado, token):
    alvo = _arquivo(estado)
    certo = hashlib.sha256(b"conteudo").hexdigest()
    dados = S.assinatura(arquivo=str(alvo), hash_esperado=certo, autorizacao=token)
    assert dados["metrics"]["hashConfere"] is True
    assert dados["counts"]["must"] == 0


def test_assinatura_hash_divergente_bloqueia(estado, token):
    alvo = _arquivo(estado)
    dados = S.assinatura(arquivo=str(alvo), hash_esperado="0" * 64, autorizacao=token)
    assert dados["metrics"]["hashConfere"] is False
    assert dados["counts"]["must"] == 1
    assert any("hash" in item["title"].lower() for item in dados["findings"])


def test_assinatura_hash_aceita_maiuscula(estado, token):
    alvo = _arquivo(estado)
    certo = hashlib.sha256(b"conteudo").hexdigest().upper()
    assert S.assinatura(arquivo=str(alvo), hash_esperado=certo, autorizacao=token)["metrics"]["hashConfere"] is True


def test_assinatura_hash_malformado(estado, token):
    alvo = _arquivo(estado)
    with pytest.raises(S.SistemaError, match="64"):
        S.assinatura(arquivo=str(alvo), hash_esperado="abc", autorizacao=token)


def test_assinatura_sem_hash_avisa(estado, token):
    alvo = _arquivo(estado)
    dados = S.assinatura(arquivo=str(alvo), autorizacao=token)
    assert dados["metrics"]["hashConfere"] is None
    assert any("não comparado" in item["title"].lower() for item in dados["findings"])


def test_assinatura_fora_da_quarentena(token):
    with pytest.raises(S.SistemaError, match="quarentena"):
        S.assinatura(arquivo="/etc/passwd", autorizacao=token)


def test_assinatura_exige_token(estado):
    with pytest.raises(S.SistemaError, match="token"):
        S.assinatura(arquivo=str(_arquivo(estado)), autorizacao="")


def test_assinatura_authenticode_valida(monkeypatch, estado, token):
    alvo = _arquivo(estado)
    monkeypatch.setattr(S.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        S,
        "_authenticode",
        lambda _p: {"estado": "válida", "fonte": "Get-AuthenticodeSignature", "detalhe": "Valid: ok", "assinante": "CN=Fabricante"},
    )
    dados = S.assinatura(arquivo=str(alvo), autorizacao=token)
    assert dados["metrics"]["assinatura"] == "válida"
    assert dados["counts"]["must"] == 0


def test_assinatura_authenticode_invalida_bloqueia(monkeypatch, estado, token):
    alvo = _arquivo(estado)
    monkeypatch.setattr(S.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        S,
        "_authenticode",
        lambda _p: {"estado": "inválida", "fonte": "Get-AuthenticodeSignature", "detalhe": "HashMismatch", "assinante": ""},
    )
    dados = S.assinatura(arquivo=str(alvo), autorizacao=token)
    assert dados["counts"]["must"] >= 1


def test_authenticode_mapeia_status(monkeypatch):
    monkeypatch.setattr(S, "_rodar_env", lambda *_a, **_k: (0, json.dumps({"Status": "Valid", "Mensagem": "ok"}), ""))
    assert S._authenticode(Path("/x.msi"))["estado"] == "válida"
    monkeypatch.setattr(S, "_rodar_env", lambda *_a, **_k: (0, json.dumps({"Status": "HashMismatch"}), ""))
    assert S._authenticode(Path("/x.msi"))["estado"] == "inválida"
    monkeypatch.setattr(S, "_rodar_env", lambda *_a, **_k: (0, json.dumps({"Status": "NotSigned"}), ""))
    assert S._authenticode(Path("/x.msi"))["estado"] == "ausente"


def test_authenticode_sem_powershell(monkeypatch):
    monkeypatch.setattr(S, "_rodar_env", lambda *_a, **_k: (127, "", "comando não encontrado"))
    assert S._authenticode(Path("/x.msi"))["estado"] == "não verificável"


def test_authenticode_passa_caminho_por_ambiente(monkeypatch):
    visto = {}

    def espiao(comando, extra, timeout=30):
        visto["comando"] = comando
        visto["extra"] = extra
        return 0, json.dumps({"Status": "Valid"}), ""

    monkeypatch.setattr(S, "_rodar_env", espiao)
    S._authenticode(Path("/tmp/quarentena/driver.msi"))
    assert visto["extra"]["JARVIS_ALVO"] == "/tmp/quarentena/driver.msi"
    assert "driver.msi" not in " ".join(visto["comando"])


def test_gpg_assinatura_valida(monkeypatch, estado, token):
    alvo = _arquivo(estado)
    sig = estado / "host-downloads" / "0000-fone.asc"
    sig.write_text("assinatura", encoding="utf-8")
    monkeypatch.setattr(S, "_rodar", lambda *_a, **_k: (0, 'Good signature from "Ahmad"', ""))
    dados = S.assinatura(arquivo=str(alvo), assinatura_arquivo=str(sig), autorizacao=token)
    assert dados["metrics"]["assinatura"] == "válida"
    assert dados["metrics"]["fonte"] == "gpg --verify"


def test_gpg_assinatura_invalida(monkeypatch, estado, token):
    alvo = _arquivo(estado)
    sig = estado / "host-downloads" / "0000-fone.asc"
    sig.write_text("assinatura", encoding="utf-8")
    monkeypatch.setattr(S, "_rodar", lambda *_a, **_k: (1, "", "BAD signature"))
    dados = S.assinatura(arquivo=str(alvo), assinatura_arquivo=str(sig), autorizacao=token)
    assert dados["metrics"]["assinatura"] == "inválida"
    assert dados["counts"]["must"] >= 1


def test_gpg_ausente_nao_verifica(monkeypatch):
    monkeypatch.setattr(S, "_rodar", lambda *_a, **_k: (127, "", "não encontrado"))
    assert S._gpg(Path("/x"), Path("/y"))["estado"] == "não verificável"


def test_rpm_checksig_ok(monkeypatch):
    monkeypatch.setattr(S, "_rodar", lambda *_a, **_k: (0, "digests signatures OK", ""))
    assert S._rpm_checksig(Path("/x.rpm"))["estado"] == "válida"


def test_rpm_checksig_so_digest(monkeypatch):
    monkeypatch.setattr(S, "_rodar", lambda *_a, **_k: (0, "digests OK", ""))
    assert S._rpm_checksig(Path("/x.rpm"))["estado"] == "ausente"


def test_rpm_checksig_quebrado(monkeypatch):
    monkeypatch.setattr(S, "_rodar", lambda *_a, **_k: (1, "digests NOT OK", ""))
    assert S._rpm_checksig(Path("/x.rpm"))["estado"] == "inválida"


def test_dpkg_sig_sem_ferramenta(monkeypatch):
    monkeypatch.setattr(S, "_rodar", lambda *_a, **_k: (127, "", "não encontrado"))
    assert S._dpkg_sig(Path("/x.deb"))["estado"] == "não verificável"


def test_verificacao_escolhe_fonte_por_plataforma(monkeypatch, tmp_path):
    monkeypatch.setattr(S.platform, "system", lambda: "Windows")
    monkeypatch.setattr(S, "_authenticode", lambda _p: {"estado": "válida", "fonte": "Authenticode", "detalhe": "", "assinante": ""})
    assert S._verificar_assinatura(tmp_path / "x.msi")["fonte"] == "Authenticode"
    monkeypatch.setattr(S.platform, "system", lambda: "Linux")
    assert S._verificar_assinatura(tmp_path / "x.appimage")["estado"] == "não verificável"


# ---------------------------------------------------------------------------
# Instalação com assinatura
# ---------------------------------------------------------------------------


def test_instalar_expoe_sha256_do_arquivo(estado, token):
    alvo = _arquivo(estado)
    dados = S.instalar(arquivo=str(alvo), autorizacao=token)
    linha = next(item for item in dados["rows"] if item["campo"] == "sha256")
    assert linha["valor"] == hashlib.sha256(b"conteudo").hexdigest()


def test_instalar_sem_arquivo_local_nao_tem_hash(token):
    dados = S.instalar(pacote="pip:rich", autorizacao=token)
    linha = next(item for item in dados["rows"] if item["campo"] == "sha256")
    assert linha["valor"] == "(sem arquivo local)"


def test_plano_de_instalacao_aponta_a_skill_de_elevacao(token):
    dados = S.instalar(pacote="pip:rich", autorizacao=token)
    texto = " ".join(dados["limitations"]).lower()
    assert "sistema.elevar" in texto
    assert "elevação de privilégio não é feita" not in texto


def test_instalar_exigindo_assinatura_bloqueia_quando_nao_verificavel(estado, token):
    alvo = _arquivo(estado)
    dados = S.instalar(arquivo=str(alvo), exigir_assinatura=True, autorizacao=token)
    assert dados["metrics"]["exigirAssinatura"] is True
    assert dados["counts"]["must"] >= 1


def test_instalar_exigindo_assinatura_aprovada(monkeypatch, estado, token):
    alvo = _arquivo(estado)
    monkeypatch.setattr(
        S,
        "_verificar_assinatura",
        lambda *_a, **_k: {"estado": "válida", "fonte": "Authenticode", "detalhe": "Valid", "assinante": "CN=X"},
    )
    dados = S.instalar(arquivo=str(alvo), exigir_assinatura=True, autorizacao=token)
    assert dados["metrics"]["assinatura"] == "válida"
    assert dados["counts"]["must"] == 0


# ---------------------------------------------------------------------------
# Desinstalação
# ---------------------------------------------------------------------------


def test_desinstalar_dpkg(token):
    dados = S.desinstalar(pacote="dpkg:curl", autorizacao=token)
    assert dados["rows"][2]["valor"] == "dpkg -r curl"
    assert dados["metrics"]["risco"] == "alto"


def test_desinstalar_rpm(token):
    assert S.desinstalar(pacote="rpm:htop", autorizacao=token)["rows"][2]["valor"] == "rpm -e htop"


def test_desinstalar_pip(token):
    assert S.desinstalar(pacote="pip:rich", autorizacao=token)["rows"][2]["valor"].endswith("-m pip uninstall -y rich")


def test_desinstalar_npm(token):
    assert S.desinstalar(pacote="npm:typescript", autorizacao=token)["rows"][2]["valor"] == "npm uninstall typescript"


def test_desinstalar_msi_por_guid(token):
    guid = "{12345678-1234-1234-1234-123456789012}"
    assert S.desinstalar(pacote=f"msi:{guid}", autorizacao=token)["rows"][2]["valor"] == f"msiexec /x {guid} /qb /norestart"


def test_desinstalar_msi_por_arquivo(estado, token):
    alvo = _arquivo(estado)
    dados = S.desinstalar(arquivo=str(alvo), autorizacao=token)
    assert dados["rows"][2]["valor"].startswith("msiexec /x ")
    assert dados["rows"][2]["valor"].endswith("/qb /norestart")


def test_desinstalar_recusa_metacaractere(token):
    with pytest.raises(S.SistemaError, match="inválido"):
        S.desinstalar(pacote="dpkg:curl;rm -rf /", autorizacao=token)


def test_desinstalar_recusa_prefixo_desconhecido(token):
    with pytest.raises(S.SistemaError, match="Prefixo"):
        S.desinstalar(pacote="snap:curl", autorizacao=token)


def test_desinstalar_exige_prefixo_ou_arquivo(token):
    with pytest.raises(S.SistemaError, match="Informe"):
        S.desinstalar(autorizacao=token)


def test_desinstalar_msi_sem_guid(token):
    with pytest.raises(S.SistemaError, match="GUID"):
        S.desinstalar(pacote="msi:1234", autorizacao=token)


def test_desinstalar_arquivo_nao_msi(estado, token):
    alvo = _arquivo(estado, nome="pacote.AppImage")
    with pytest.raises(S.SistemaError, match="msi"):
        S.desinstalar(arquivo=str(alvo), autorizacao=token)


def test_plano_de_desinstalacao_aponta_a_skill_de_elevacao(token):
    dados = S.desinstalar(pacote="dpkg:curl", autorizacao=token)
    texto = " ".join(dados["limitations"]).lower()
    assert "sistema.elevar" in texto and "remover_deb" in texto
    assert "elevação de privilégio não é feita" not in texto


def test_desinstalar_nao_executa(estado, token):
    dados = S.desinstalar(arquivo=str(_arquivo(estado)), autorizacao=token)
    assert dados["executed"] is False and dados["readOnly"] is True
    assert len(dados["confirmacao"]) == 8


def test_desinstalar_avisa_trava(token):
    dados = S.desinstalar(pacote="pip:rich", autorizacao=token)
    assert any(item["location"] == S.AMBIENTE_INSTALAR for item in dados["findings"])


def test_desinstalar_avisa_residuo(token):
    dados = S.desinstalar(pacote="dpkg:curl", autorizacao=token)
    assert any("resíduo" in item["title"].lower() for item in dados["findings"])


def test_executar_desinstala(monkeypatch, instalacao_ligada, token, estado):
    chamadas = []
    monkeypatch.setattr(S, "_rodar", lambda cmd, timeout=20: chamadas.append(cmd) or (0, "Removing", ""))
    plano = S.desinstalar(pacote="dpkg:curl", autorizacao=token)
    dados = S.executar(confirmacao=plano["confirmacao"], autorizacao=token)
    assert dados["executed"] is True
    assert dados["metrics"]["acao"] == "desinstalar"
    assert chamadas[0] == ["dpkg", "-r", "curl"]


def test_executar_audita_desinstalacao(monkeypatch, instalacao_ligada, token, estado):
    monkeypatch.setattr(S, "_rodar", lambda *_a, **_k: (0, "", ""))
    plano = S.desinstalar(pacote="pip:rich", autorizacao=token)
    S.executar(confirmacao=plano["confirmacao"], autorizacao=token)
    linha = json.loads((estado / "host-audit.jsonl").read_text(encoding="utf-8").strip().splitlines()[-1])
    assert linha["acao"] == "desinstalar"


def test_executar_com_erro_de_permissao_aponta_a_elevacao(monkeypatch, instalacao_ligada, token):
    monkeypatch.setattr(S, "_rodar", lambda *_a, **_k: (1, "", "permission denied"))
    plano = S.desinstalar(pacote="dpkg:curl", autorizacao=token)
    dados = S.executar(confirmacao=plano["confirmacao"], autorizacao=token)
    texto = " ".join(item["fix"] for item in dados["findings"]).lower()
    assert "sistema.elevar" in texto


# ---------------------------------------------------------------------------
# Revalidação na execução
# ---------------------------------------------------------------------------


def test_executar_recusa_arquivo_alterado(monkeypatch, instalacao_ligada, token, estado):
    alvo = _arquivo(estado)
    monkeypatch.setattr(S, "_rodar", lambda *_a, **_k: (0, "", ""))
    plano = S.instalar(arquivo=str(alvo), autorizacao=token)
    alvo.write_bytes(b"outra coisa")
    with pytest.raises(S.SistemaError, match="mudou"):
        S.executar(confirmacao=plano["confirmacao"], autorizacao=token)


def test_executar_recusa_assinatura_exigida_nao_confirmada(monkeypatch, instalacao_ligada, token, estado):
    alvo = _arquivo(estado)
    monkeypatch.setattr(S, "_rodar", lambda *_a, **_k: (0, "", ""))
    plano = S.instalar(arquivo=str(alvo), exigir_assinatura=True, autorizacao=token)
    with pytest.raises(S.SistemaError, match="Assinatura exigida"):
        S.executar(confirmacao=plano["confirmacao"], autorizacao=token)


def test_executar_aceita_assinatura_confirmada(monkeypatch, instalacao_ligada, token, estado):
    alvo = _arquivo(estado)
    monkeypatch.setattr(S, "_rodar", lambda *_a, **_k: (0, "", ""))
    monkeypatch.setattr(
        S,
        "_verificar_assinatura",
        lambda *_a, **_k: {"estado": "válida", "fonte": "Authenticator", "detalhe": "", "assinante": "CN=X"},
    )
    plano = S.instalar(arquivo=str(alvo), exigir_assinatura=True, autorizacao=token)
    dados = S.executar(confirmacao=plano["confirmacao"], autorizacao=token)
    assert dados["executed"] is True


def test_executar_mostra_sha256(monkeypatch, instalacao_ligada, token, estado):
    alvo = _arquivo(estado)
    monkeypatch.setattr(S, "_rodar", lambda *_a, **_k: (0, "", ""))
    plano = S.instalar(arquivo=str(alvo), autorizacao=token)
    dados = S.executar(confirmacao=plano["confirmacao"], autorizacao=token)
    linha = next(item for item in dados["rows"] if item["campo"] == "sha256")
    assert linha["valor"] == hashlib.sha256(b"conteudo").hexdigest()


# ---------------------------------------------------------------------------
# API das novas rotas
# ---------------------------------------------------------------------------


def test_api_assinatura_exige_token_com_trava_local(client, monkeypatch):
    """Com JARVIS_HOST_EXIGIR_TOKEN_LOCAL=1 o token voltava a ser pedido até aqui."""
    monkeypatch.setenv("JARVIS_HOST_EXIGIR_TOKEN_LOCAL", "1")
    corpo = client.post("/api/skills/sistema.assinatura/execute", json={"parameters": {"arquivo": "/tmp/x.msi"}}).json()
    assert corpo["error"]["code"] == "SKILL_ERROR"
    assert "token" in corpo["error"]["message"]


def test_api_assinatura_na_propria_maquina_passa_do_token(client, monkeypatch):
    """0.60.9: sem a trava, 127.0.0.1 não digita token e o erro é do arquivo."""
    monkeypatch.delenv("JARVIS_HOST_EXIGIR_TOKEN_LOCAL", raising=False)
    corpo = client.post("/api/skills/sistema.assinatura/execute", json={"parameters": {"arquivo": "/tmp/x.msi"}}).json()
    assert "token" not in corpo["error"]["message"].lower()


def test_api_desinstalar_responde(client, token):
    corpo = client.post(
        "/api/skills/sistema.desinstalar/execute",
        json={"parameters": {"pacote": "pip:rich", "autorizacao": token}},
    ).json()
    assert corpo["ok"] is True
    assert corpo["result"]["metrics"]["tipo"] == "pip"


def test_api_desinstalar_recusa_sem_prefixo(client, token):
    corpo = client.post(
        "/api/skills/sistema.desinstalar/execute",
        json={"parameters": {"pacote": "curl", "autorizacao": token}},
    ).json()
    assert corpo["ok"] is False
    assert "Prefixo" in corpo["error"]["message"]


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path):
    app = create_app(registry=None)
    return TestClient(app)


def test_api_health_na_versao_nova(client):
    dados = client.get("/api/health").json()
    assert dados["version"] == "0.60.9"
    assert dados["skills"] == 288


def test_api_lista_as_dezesseis_skills_de_sistema(client):
    ids = [item["id"] for item in client.get("/api/skills").json()["skills"]]
    assert len([item for item in ids if item.startswith("sistema.")]) == 16


def test_api_sistema_disco_exige_token_com_trava_local(client, monkeypatch):
    monkeypatch.setenv("JARVIS_HOST_EXIGIR_TOKEN_LOCAL", "1")
    resposta = client.post("/api/skills/sistema.disco/execute", json={"parameters": {}}).json()
    assert resposta["ok"] is False
    assert resposta["error"]["code"] == "SKILL_ERROR"
    assert "token" in resposta["error"]["message"]


def test_api_sistema_disco_responde_na_propria_maquina(client, monkeypatch):
    monkeypatch.delenv("JARVIS_HOST_EXIGIR_TOKEN_LOCAL", raising=False)
    resposta = client.post("/api/skills/sistema.disco/execute", json={"parameters": {}}).json()
    assert resposta["ok"] is True
    assert resposta["result"]["metrics"]["unidades"] >= 1


def test_api_sistema_regras_responde(client):
    resposta = client.post("/api/skills/sistema.regras/execute", json={"parameters": {}}).json()
    assert resposta["ok"] is True
    assert resposta["result"]["versao"] == "0.60.9"


def test_api_baixar_exige_confirmacao(client):
    resposta = client.post(
        "/api/skills/sistema.baixar/execute",
        json={"parameters": {"url": "https://example.com/a.msi"}, "autorizacao": ""},
    ).json()
    assert resposta["ok"] is False
    assert resposta["error"]["code"] == "CONFIRMATION_REQUIRED"


def test_api_executar_exige_confirmacao(client):
    resposta = client.post(
        "/api/skills/sistema.executar/execute",
        json={"parameters": {"confirmacao": "abcd1234"}},
    ).json()
    assert resposta["error"]["code"] == "CONFIRMATION_REQUIRED"


def test_api_instalar_monta_o_plano_na_propria_maquina(client, monkeypatch):
    """`sistema.instalar` monta o plano (não executa) e não pede confirmação.

    Antes da 0.60.9 este teste parava na recusa do token; com o dono automático
    em 127.0.0.1 ele chega na skill de verdade.
    """
    monkeypatch.delenv("JARVIS_HOST_EXIGIR_TOKEN_LOCAL", raising=False)
    resposta = client.post("/api/skills/sistema.instalar/execute", json={"parameters": {"pacote": "pip:rich"}}).json()
    assert resposta["ok"] is True
    assert resposta["result"]["metrics"]["executado"] is False
    linhas = {linha["campo"]: linha["valor"] for linha in resposta["result"]["rows"]}
    assert linhas["confirmação"]  # o token de uso único que libera o sistema.executar


def test_api_skill_inexistente(client):
    assert client.post("/api/skills/sistema.nada/execute", json={"parameters": {}}).status_code == 404


def test_api_parametro_extra_recusado(client):
    corpo = client.post("/api/skills/sistema.regras/execute", json={"parameters": {"x": 1}, "dryRun": True}).json()
    assert corpo["ok"] is False


# ---------------------------------------------------------------------------
# Registro do que ele instalou e sugestão de remoção (0.60.3)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tipo,nome,pacote",
    [
        ("deb", "app_2.0_amd64.deb", "dpkg:app"),
        ("deb", "meu-programa.deb", "dpkg:meu-programa"),
        ("rpm", "nano-7.2-1.fc38.x86_64.rpm", "rpm:nano"),
        ("rpm", "meu-programa-1.2.3-1.x86_64.rpm", "rpm:meu-programa"),
        ("msi", "setup.msi", ""),
        ("msix", "pacote.msix", ""),
        ("exe", "instalador.exe", ""),
        ("appimage", "app.AppImage", ""),
    ],
)
def test_remocao_sugerida(tipo, nome, pacote):
    sugestao = S.remocao_sugerida(tipo, nome)
    assert sugestao["pacote"] == pacote
    if not pacote:
        assert sugestao["nota"]


def test_remocao_sugerida_explica_o_que_nao_da_para_saber():
    assert "GUID" in S.remocao_sugerida("msi", "a.msi")["nota"]
    assert "fabricante" in S.remocao_sugerida("exe", "a.exe")["nota"].lower()


def test_instalados_sem_registro(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "AUDITORIA", tmp_path / "host-audit.jsonl")
    dados = S.instalados()
    assert dados["total"] == 0
    assert "nunca" in dados["resposta"] or "ainda" in dados["resposta"]


def test_instalados_le_so_o_que_terminou_com_codigo_zero(tmp_path, monkeypatch):
    registro = tmp_path / "host-audit.jsonl"
    linhas = [
        {"ts": "2026-10-26T10:00:00+00:00", "acao": "instalar", "alvo": "app_2.0_amd64.deb", "comando": "dpkg -i app.deb", "codigo": 0},
        {"ts": "2026-10-26T10:05:00+00:00", "acao": "instalar", "alvo": "quebrado.deb", "comando": "dpkg -i quebrado.deb", "codigo": 1},
        {"ts": "2026-10-26T10:10:00+00:00", "acao": "baixar", "alvo": "arquivo.zip", "codigo": 0},
        {"ts": "2026-10-26T10:15:00+00:00", "acao": "desinstalar", "alvo": "velho.deb", "comando": "dpkg -r velho", "codigo": 0},
        "linha quebrada",
    ]
    registro.write_text("\n".join(json.dumps(linha) if isinstance(linha, dict) else linha for linha in linhas), encoding="utf-8")
    monkeypatch.setattr(S, "AUDITORIA", registro)
    dados = S.instalados()
    assert dados["total"] == 2
    assert [item["alvo"] for item in dados["itens"]] == ["velho.deb", "app_2.0_amd64.deb"]
    assert dados["itens"][1]["remocao"]["pacote"] == "dpkg:app"
    assert dados["itens"][0]["remocao"]["pacote"] == ""


def test_instalados_respeita_o_limite(tmp_path, monkeypatch):
    registro = tmp_path / "host-audit.jsonl"
    conteudo = "\n".join(
        json.dumps({"ts": f"2026-10-26T10:0{n}:00+00:00", "acao": "instalar", "alvo": f"p{n}.deb", "codigo": 0})
        for n in range(5)
    )
    registro.write_text(conteudo, encoding="utf-8")
    monkeypatch.setattr(S, "AUDITORIA", registro)
    assert S.instalados(limite=2)["total"] == 2


def test_planos_pendentes_trazem_a_remocao_sugerida(monkeypatch):
    monkeypatch.setattr(S, "_CONFIRMACAO", {})
    monkeypatch.setattr(
        S,
        "_CONFIRMACAO",
        {
            "abcd1234": {
                "expira": 9_999_999_999,
                "acao": "instalar",
                "tipo": "deb",
                "rotulo": "app_2.0_amd64.deb",
                "comando": ["dpkg", "-i", "app.deb"],
            }
        },
    )
    plano = S.planos_pendentes()[0]
    assert plano["remocao"]["pacote"] == "dpkg:app"


def test_plano_de_desinstalar_nao_sugere_remocao(monkeypatch):
    monkeypatch.setattr(S, "_CONFIRMACAO", {})
    monkeypatch.setattr(
        S,
        "_CONFIRMACAO",
        {"abcd1234": {"expira": 9_999_999_999, "acao": "desinstalar", "tipo": "deb", "rotulo": "app"}},
    )
    plano = S.planos_pendentes()[0]
    assert plano["remocao"]["pacote"] == ""
