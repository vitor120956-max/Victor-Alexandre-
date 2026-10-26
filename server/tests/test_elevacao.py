"""Testes da elevação controlada (0.33.0): plano, travas e execução como root.

A camada chama `sudo`, então nenhum teste executa processo de verdade: `_rodar`
e `shutil.which` são substituídos, e o diretório de estado — token, quarentena e
auditoria — é isolado em `tmp_path`. O `sudo` real só aparece num teste de
integração marcado como `skip`, para não depender da máquina.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import elevacao as E
from server.app import create_app


@pytest.fixture(autouse=True)
def estado(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "STORAGE", tmp_path)
    monkeypatch.setattr(E, "TOKEN_ARQUIVO", tmp_path / "host-token.txt")
    monkeypatch.setattr(E, "QUARENTENA", tmp_path / "host-downloads")
    monkeypatch.setattr(E, "AUDITORIA", tmp_path / "host-audit.jsonl")
    monkeypatch.delenv(E.AMBIENTE_ROOT, raising=False)
    monkeypatch.delenv(E.AMBIENTE_SERVICOS, raising=False)
    E._TOKEN_CONFIRMACAO.clear()
    (tmp_path / "host-downloads").mkdir(exist_ok=True)
    yield tmp_path
    E._TOKEN_CONFIRMACAO.clear()


@pytest.fixture
def token(estado):
    caminho = estado / "host-token.txt"
    caminho.write_text("token-de-teste-elevacao\n", encoding="utf-8")
    return "token-de-teste-elevacao"


@pytest.fixture
def root_ligado(monkeypatch):
    monkeypatch.setenv(E.AMBIENTE_ROOT, "1")


@pytest.fixture
def binarios(monkeypatch):
    """Todo binário da tabela existe, e o sudo também."""
    caminhos = {
        "sudo": "/usr/bin/sudo",
        "dpkg": "/usr/bin/dpkg",
        "rpm": "/usr/bin/rpm",
        "systemctl": "/usr/bin/systemctl",
    }
    monkeypatch.setattr(E.shutil, "which", lambda nome: caminhos.get(nome))


@pytest.fixture
def sem_senha(monkeypatch):
    def rodar(comando, timeout=30):
        if comando[0] == "/usr/bin/sudo" and "-l" in comando:
            return 0, "User user may run the following commands:\n    (root) NOPASSWD: /usr/bin/dpkg\n", ""
        return 0, "", ""

    monkeypatch.setattr(E, "_rodar", rodar)


@pytest.fixture
def pacote(estado, binarios, sem_senha):
    alvo = estado / "host-downloads" / "exemplo.deb"
    alvo.write_bytes(b"deb de teste")
    return alvo


def _textos(resultado):
    return " ".join(item["title"] + " " + item["problem"] for item in resultado["findings"])


# ---------------------------------------------------------------------------
# Token de host
# ---------------------------------------------------------------------------


def test_sem_token_recusa(estado):
    with pytest.raises(E.ElevacaoError, match="Token de host ausente"):
        E.privilegio(autorizacao="")


def test_token_errado_recusa(token):
    with pytest.raises(E.ElevacaoError, match="inválido"):
        E.privilegio(autorizacao="outro-valor")


def test_token_gera_arquivo_e_le_de_volta(estado):
    assert E._token_host() == ""
    with pytest.raises(E.ElevacaoError, match="ausente"):
        E.privilegio(autorizacao="qualquer")
    (estado / "host-token.txt").write_text("abc\n", encoding="utf-8")
    assert E._token_host() == "abc"
    assert E.privilegio(autorizacao="abc")["metrics"]["acoes"] == len(E.ACOES)


# ---------------------------------------------------------------------------
# Privilégio
# ---------------------------------------------------------------------------


def test_privilegio_descreve_o_processo(token, binarios, sem_senha):
    dados = E.privilegio(autorizacao=token)
    campos = {linha["chave"]: linha["valor"] for linha in dados["rows"]}
    assert "uid / euid" in campos
    assert campos["sudo instalado"] == "/usr/bin/sudo"
    assert campos["sudo sem senha"] == "sim"
    assert campos["trava de elevação"] == "JARVIS_HOST_ROOT=0"
    assert dados["metrics"]["semSenha"] is True


def test_privilegio_avisa_quando_roda_como_root(token, binarios, sem_senha, monkeypatch):
    monkeypatch.setattr(E.os, "geteuid", lambda: 0)
    dados = E.privilegio(autorizacao=token)
    assert dados["metrics"]["root"] is True
    assert any("roda como root" in item["title"].lower() for item in dados["findings"])


def test_privilegio_avisa_sudo_sem_nopasswd(token, binarios, monkeypatch):
    def rodar(comando, timeout=30):
        return 1, "", "sudo: a password is required"

    monkeypatch.setattr(E, "_rodar", rodar)
    dados = E.privilegio(autorizacao=token)
    assert dados["metrics"]["semSenha"] is False
    assert any("senha" in item["title"].lower() for item in dados["findings"])


def test_privilegio_avisa_sudo_ausente(token, monkeypatch):
    monkeypatch.setattr(E.shutil, "which", lambda nome: None)
    dados = E.privilegio(autorizacao=token)
    assert dados["metrics"]["sudo"] is False
    assert any("sem sudo" in item["title"].lower() for item in dados["findings"])


def test_sudoers_sugerido_cita_os_binarios(token, binarios):
    linhas = E.sudoers_sugerido()
    texto = " ".join(linhas)
    assert "NOPASSWD" in texto
    assert "/usr/bin/dpkg" in texto and "/usr/bin/rpm" in texto
    assert linhas[0].startswith("#")


def test_sudoers_sugerido_sem_binarios(token, monkeypatch):
    monkeypatch.setattr(E.shutil, "which", lambda nome: None)
    assert "nenhum binário" in E.sudoers_sugerido()[0]


# ---------------------------------------------------------------------------
# Plano
# ---------------------------------------------------------------------------


def test_plano_de_instalacao_deb(token, pacote):
    dados = E.elevar(acao="instalar_deb", alvo=str(pacote), autorizacao=token)
    campos = {linha["campo"]: linha["valor"] for linha in dados["rows"]}
    assert campos["comando"] == f"/usr/bin/sudo -n /usr/bin/dpkg -i -- {pacote}"
    assert campos["risco"] == "alto"
    assert len(campos["confirmação"]) == 8
    assert dados["confirmacao"] == campos["confirmação"]
    assert dados["executed"] is False


def test_plano_nao_executa_nada(token, pacote, monkeypatch):
    """O plano só consulta `sudo -n -l`; nunca roda o binário da ação."""
    chamadas = []
    monkeypatch.setattr(E, "_rodar", lambda comando, timeout=30: chamadas.append(comando) or (0, "", ""))
    E.elevar(acao="instalar_deb", alvo=str(pacote), autorizacao=token)
    assert all(comando[-1] == "-l" for comando in chamadas)
    assert not any("-i" in comando for comando in chamadas)


def test_plano_recusa_acao_desconhecida(token, pacote):
    with pytest.raises(E.ElevacaoError, match="Ação desconhecida"):
        E.elevar(acao="rm_rf", alvo=str(pacote), autorizacao=token)


def test_plano_recusa_arquivo_fora_da_quarentena(token, estado, binarios, sem_senha):
    alvo = estado / "fora.deb"
    alvo.write_bytes(b"x")
    with pytest.raises(E.ElevacaoError, match="quarentena"):
        E.elevar(acao="instalar_deb", alvo=str(alvo), autorizacao=token)


def test_plano_recusa_extensao_trocada(token, estado, binarios, sem_senha):
    alvo = estado / "host-downloads" / "isca.deb"
    alvo.write_bytes(b"x")
    with pytest.raises(E.ElevacaoError, match="aceita só"):
        E.elevar(acao="instalar_rpm", alvo=str(alvo), autorizacao=token)


def test_plano_recusa_pacote_com_espaco(token, binarios, sem_senha):
    with pytest.raises(E.ElevacaoError, match="Nome de pacote inválido"):
        E.elevar(acao="remover_deb", alvo="curl; rm -rf /", autorizacao=token)


def test_plano_recusa_pacote_com_maiuscula(token, binarios, sem_senha):
    with pytest.raises(E.ElevacaoError, match="Nome de pacote inválido"):
        E.elevar(acao="remover_rpm", alvo="Curl", autorizacao=token)


def test_plano_recusa_servico_sem_lista(token, binarios, sem_senha):
    with pytest.raises(E.ElevacaoError, match="Nenhum serviço autorizado"):
        E.elevar(acao="reiniciar_servico", alvo="nginx.service", autorizacao=token)


def test_plano_recusa_servico_fora_da_lista(token, binarios, sem_senha, monkeypatch):
    monkeypatch.setenv(E.AMBIENTE_SERVICOS, "meuapp.service")
    with pytest.raises(E.ElevacaoError, match="não está na lista"):
        E.elevar(acao="reiniciar_servico", alvo="nginx.service", autorizacao=token)


def test_plano_aceita_servico_listado(token, binarios, sem_senha, monkeypatch):
    monkeypatch.setenv(E.AMBIENTE_SERVICOS, "meuapp.service, outro.service")
    dados = E.elevar(acao="reiniciar_servico", alvo="meuapp.service", autorizacao=token)
    campos = {linha["campo"]: linha["valor"] for linha in dados["rows"]}
    assert campos["comando"].endswith("systemctl restart -- meuapp.service")


def test_plano_recusa_binario_ausente(token, pacote, monkeypatch):
    monkeypatch.setattr(E.shutil, "which", lambda nome: "/usr/bin/sudo" if nome == "sudo" else None)
    with pytest.raises(E.ElevacaoError, match="não está instalado"):
        E.elevar(acao="instalar_deb", alvo=str(pacote), autorizacao=token)


def test_plano_recusa_sem_sudo(token, pacote, monkeypatch):
    monkeypatch.setattr(E.shutil, "which", lambda nome: None if nome == "sudo" else f"/usr/bin/{nome}")
    with pytest.raises(E.ElevacaoError, match="sudo` não existe"):
        E.elevar(acao="instalar_deb", alvo=str(pacote), autorizacao=token)


def test_plano_avisa_sudo_com_senha(token, pacote, monkeypatch):
    def rodar(comando, timeout=30):
        return 1, "", "sudo: a password is required"

    monkeypatch.setattr(E, "_rodar", rodar)
    dados = E.elevar(acao="instalar_deb", alvo=str(pacote), autorizacao=token)
    assert dados["metrics"]["sudoSemSenha"] is False
    assert any("senha" in item["title"].lower() for item in dados["findings"])


def test_plano_de_remocao_sugere_anotar_versao(token, binarios, sem_senha):
    dados = E.elevar(acao="remover_deb", alvo="curl", autorizacao=token)
    assert any("backup" in item["title"].lower() for item in dados["findings"])


def test_plano_sempre_avisa_que_roda_como_root(token, pacote):
    dados = E.elevar(acao="instalar_deb", alvo=str(pacote), autorizacao=token)
    assert any("roda como root" in item["title"].lower() for item in dados["findings"])


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------


def _plano_e_token(token, pacote):
    dados = E.elevar(acao="instalar_deb", alvo=str(pacote), autorizacao=token)
    return dados["confirmacao"]


def test_execucao_exige_trava(token, pacote):
    confirmacao = _plano_e_token(token, pacote)
    with pytest.raises(E.ElevacaoError, match="Elevação desligada"):
        E.elevar_executar(confirmacao=confirmacao, autorizacao=token)


def test_execucao_exige_token_de_host(pacote, root_ligado):
    with pytest.raises(E.ElevacaoError, match="Token de host ausente"):
        E.elevar_executar(confirmacao="deadbeef", autorizacao="")


def test_execucao_recusa_confirmacao_desconhecida(token, root_ligado):
    with pytest.raises(E.ElevacaoError, match="Confirmação ausente"):
        E.elevar_executar(confirmacao="deadbeef", autorizacao=token)


def test_execucao_roda_o_argv_do_plano(token, pacote, root_ligado, monkeypatch):
    chamadas = []

    def rodar(comando, timeout=30):
        chamadas.append((comando, timeout))
        return 0, "Selecting previously unselected package exemplo.", ""

    confirmacao = _plano_e_token(token, pacote)
    monkeypatch.setattr(E, "_rodar", rodar)
    dados = E.elevar_executar(confirmacao=confirmacao, autorizacao=token)
    assert dados["executed"] is True
    assert dados["readOnly"] is False
    assert dados["metrics"]["codigo"] == 0
    comando, timeout = chamadas[0]
    assert comando[:3] == ["/usr/bin/sudo", "-n", "/usr/bin/dpkg"]
    assert comando[-1] == str(pacote)
    assert timeout == 600


def test_execucao_consome_o_token(token, pacote, root_ligado, monkeypatch):
    monkeypatch.setattr(E, "_rodar", lambda comando, timeout=30: (0, "", ""))
    confirmacao = _plano_e_token(token, pacote)
    E.elevar_executar(confirmacao=confirmacao, autorizacao=token)
    with pytest.raises(E.ElevacaoError, match="Confirmação ausente"):
        E.elevar_executar(confirmacao=confirmacao, autorizacao=token)


def test_execucao_recusa_token_expirado(token, pacote, root_ligado):
    confirmacao = _plano_e_token(token, pacote)
    E._TOKEN_CONFIRMACAO[confirmacao]["expira"] = time.time() - 1
    with pytest.raises(E.ElevacaoError, match="expirada"):
        E.elevar_executar(confirmacao=confirmacao, autorizacao=token)


def test_execucao_recusa_arquivo_alterado(token, pacote, root_ligado, monkeypatch):
    confirmacao = _plano_e_token(token, pacote)
    pacote.write_bytes(b"outro conteudo")
    with pytest.raises(E.ElevacaoError, match="mudou depois do plano"):
        E.elevar_executar(confirmacao=confirmacao, autorizacao=token)


def test_execucao_recusa_arquivo_que_saiu_da_quarentena(token, pacote, root_ligado, monkeypatch):
    confirmacao = _plano_e_token(token, pacote)
    destino = pacote.parent.parent / "movido.deb"
    pacote.rename(destino)
    with pytest.raises(E.ElevacaoError, match="quarentena"):
        E.elevar_executar(confirmacao=confirmacao, autorizacao=token)


def test_execucao_recusa_argv_diferente(token, pacote, root_ligado, monkeypatch):
    confirmacao = _plano_e_token(token, pacote)
    E._TOKEN_CONFIRMACAO[confirmacao]["argv"] = ["/usr/bin/sudo", "-n", "/bin/sh"]
    with pytest.raises(E.ElevacaoError, match="não é o mesmo do plano"):
        E.elevar_executar(confirmacao=confirmacao, autorizacao=token)


def test_execucao_relata_erro_de_senha(token, pacote, root_ligado, monkeypatch):
    monkeypatch.setattr(E, "_rodar", lambda comando, timeout=30: (1, "", "sudo: a password is required"))
    confirmacao = _plano_e_token(token, pacote)
    dados = E.elevar_executar(confirmacao=confirmacao, autorizacao=token)
    assert dados["metrics"]["codigo"] == 1
    assert any("senha" in item["fix"].lower() for item in dados["findings"])


def test_execucao_grava_auditoria(token, pacote, root_ligado, monkeypatch, estado):
    monkeypatch.setattr(E, "_rodar", lambda comando, timeout=30: (0, "", ""))
    confirmacao = _plano_e_token(token, pacote)
    E.elevar_executar(confirmacao=confirmacao, autorizacao=token)
    linhas = (estado / "host-audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    evento = json.loads(linhas[-1])
    assert evento["acao"] == "elevar:instalar_deb"
    assert evento["codigo"] == 0


def test_execucao_de_servico_monta_systemctl(token, root_ligado, binarios, sem_senha, monkeypatch):
    monkeypatch.setenv(E.AMBIENTE_SERVICOS, "meuapp.service")
    chamadas = []
    monkeypatch.setattr(E, "_rodar", lambda comando, timeout=30: chamadas.append(comando) or (0, "", ""))
    plano = E.elevar(acao="parar_servico", alvo="meuapp.service", autorizacao=token)
    E.elevar_executar(confirmacao=plano["confirmacao"], autorizacao=token)
    execucao = [comando for comando in chamadas if comando[-1] != "-l"][0]
    assert execucao[2:] == ["/usr/bin/systemctl", "stop", "--", "meuapp.service"]


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


@pytest.fixture
def client(token):
    return TestClient(create_app(registry=None))


def test_api_exige_confirmacao(client, token, pacote):
    resposta = client.post(
        "/api/skills/sistema.elevar_executar/execute",
        json={"parameters": {"autorizacao": token, "confirmacao": "deadbeef"}},
    )
    assert resposta.status_code == 200
    assert resposta.json()["ok"] is False
    assert resposta.json()["error"]["code"] == "CONFIRMATION_REQUIRED"


def test_api_devolve_erro_de_skill(client, token):
    resposta = client.post(
        "/api/skills/sistema.elevar/execute",
        json={"parameters": {"autorizacao": token, "acao": "instalar_deb", "alvo": "/etc/passwd"}},
    )
    corpo = resposta.json()
    assert corpo["ok"] is False
    assert "quarentena" in corpo["error"]["message"]


def test_api_privilegio_responde(client, token, binarios, sem_senha):
    resposta = client.post(
        "/api/skills/sistema.privilegio/execute",
        json={"parameters": {"autorizacao": token}},
    )
    corpo = resposta.json()
    assert corpo["ok"] is True
    assert corpo["result"]["metrics"]["acoes"] == len(E.ACOES)


def test_api_lista_as_tres_skills_novas(client):
    resposta = client.get("/api/skills")
    ids = {item["id"] for item in resposta.json()["skills"]}
    assert {"sistema.privilegio", "sistema.elevar", "sistema.elevar_executar"} <= ids


def test_registro_conta_as_duzentas_e_oito_skills(client):
    resposta = client.get("/api/skills")
    assert len(resposta.json()["skills"]) == 281


@pytest.mark.skipif(not E._sudo(), reason="sudo não instalado nesta máquina")
def test_sudo_real_so_consulta(token):
    """O único contato com o sudo de verdade: listar permissões, nunca executar."""
    dados = E.privilegio(autorizacao=token)
    assert dados["metrics"]["acoes"] == len(E.ACOES)
    assert isinstance(dados["metrics"]["semSenha"], bool)
