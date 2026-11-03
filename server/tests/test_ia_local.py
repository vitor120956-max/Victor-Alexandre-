"""Modelo local: o caminho sem chave, do `.env` ao arquivo baixado.

O que estes testes protegem, em uma frase cada:

- baixar **não** começa sem saber se cabe, e não deixa `.parcial` para trás;
- `ligar` só aceita endereço desta máquina — apontar para outro PC sem chave é
  pedir `401`;
- `desligar` devolve o `.env` como estava, inclusive os comentários;
- nada aqui apaga modelo existente nem inventa chave.
"""
from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import ia_local
from server.skill_registry import build_registry
from server.app import create_app


@pytest.fixture()
def dados(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    raiz = tmp_path / "dados"
    raiz.mkdir()
    monkeypatch.setenv("JARVIS_DADOS", str(raiz))
    return raiz


@pytest.fixture()
def projeto(tmp_path: Path) -> Path:
    raiz = tmp_path / "projeto"
    raiz.mkdir()
    (raiz / ".env").write_text(
        "# comentário que precisa sobreviver\nJARVIS_DONO=1\nJARVIS_AI_MODEL=gpt-4o-mini\n",
        encoding="utf-8",
    )
    return raiz


def _gguf(pasta: Path, nome: str = "modelo.gguf", tamanho: int = 2_048) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / nome
    arquivo.write_bytes(b"\x00" * tamanho)
    return arquivo


# ---------------------------------------------------------------------------
# .env
# ---------------------------------------------------------------------------

def test_ler_env_ignora_comentario_e_espaco(projeto: Path):
    valores = ia_local.ler_env(projeto)
    assert valores["JARVIS_DONO"] == "1"
    assert "#" not in "".join(valores)


def test_escrever_env_preserva_ordem_comentario_e_guarda_copia(projeto: Path):
    ia_local.escrever_env({"JARVIS_AI_MODEL": "local.gguf", "JARVIS_AI_BASE_URL": "http://127.0.0.1:8080/v1"}, projeto)
    texto = (projeto / ".env").read_text(encoding="utf-8")
    assert texto.startswith("# comentário que precisa sobreviver")
    assert "JARVIS_DONO=1" in texto
    assert "JARVIS_AI_MODEL=local.gguf" in texto
    # a linha antiga foi trocada, não duplicada
    assert texto.count("JARVIS_AI_MODEL=") == 1
    copia = projeto / "env.antes-do-modelo-local"
    assert copia.exists()
    assert "gpt-4o-mini" in copia.read_text(encoding="utf-8")


def test_escrever_env_nao_sobrescreve_a_copia_antiga(projeto: Path):
    ia_local.escrever_env({"JARVIS_AI_MODEL": "a.gguf"}, projeto)
    primeira = (projeto / "env.antes-do-modelo-local").read_text(encoding="utf-8")
    ia_local.escrever_env({"JARVIS_AI_MODEL": "b.gguf"}, projeto)
    segunda = (projeto / "env.antes-do-modelo-local").read_text(encoding="utf-8")
    assert primeira == segunda


# ---------------------------------------------------------------------------
# Pasta e nomes
# ---------------------------------------------------------------------------

def test_modelos_lista_so_gguf_do_maior_para_o_menor(dados: Path):
    pasta = ia_local.pasta()
    _gguf(pasta, "pequeno.gguf", 10)
    _gguf(pasta, "grande.gguf", 5_000)
    (pasta / "leiame.txt").write_text("não é modelo", encoding="utf-8")
    nomes = [item["nome"] for item in ia_local.modelos()]
    assert nomes == ["grande.gguf", "pequeno.gguf"]


def test_nome_seguro_recusa_caminho_e_arquivo_que_nao_e_modelo():
    for ruim in ["../../fora.bin", "C:\\Windows\\system32\\x.dll", "modelo.txt", ".."]:
        with pytest.raises(ValueError):
            ia_local._nome_seguro(ruim)


def test_nome_seguro_aceita_gguf():
    assert ia_local._nome_seguro("qwen2.5-1.5b-instruct-q4_k_m.gguf") == "qwen2.5-1.5b-instruct-q4_k_m.gguf"


# ---------------------------------------------------------------------------
# Baixar
# ---------------------------------------------------------------------------

def test_baixar_grava_e_nao_deixa_parcial(dados: Path):
    def obter(_url: str, parcial: Path) -> int:
        parcial.write_bytes(b"x" * 100)
        return 100

    resultado = ia_local.baixar("https://exemplo/modelo.gguf", obter=obter)
    assert resultado["baixado"] is True
    assert resultado["bytes"] == 100
    assert Path(resultado["caminho"]).read_bytes() == b"x" * 100
    assert not list(ia_local.pasta().glob("*.parcial"))


def test_baixar_falhou_apaga_o_parcial(dados: Path):
    def obter(_url: str, parcial: Path) -> int:
        parcial.write_bytes(b"metade")
        raise OSError("caiu a conexão")

    with pytest.raises(OSError):
        ia_local.baixar("https://exemplo/modelo.gguf", obter=obter)
    assert not list(ia_local.pasta().glob("*"))


def test_baixar_nao_baixa_de_novo_o_que_ja_existe(dados: Path):
    _gguf(ia_local.pasta(), "modelo.gguf", 300)

    def obter(_url: str, _parcial: Path) -> int:  # pragma: no cover - não deve rodar
        raise AssertionError("não era para baixar")

    resultado = ia_local.baixar("https://exemplo/modelo.gguf", obter=obter)
    assert resultado["baixado"] is False
    assert "já está na pasta" in resultado["resumo"]


def test_baixar_recusa_endereco_que_nao_e_http(dados: Path):
    with pytest.raises(ValueError, match="http"):
        ia_local.baixar("file:///C:/modelo.gguf")


def test_baixar_recusa_download_vazio(dados: Path):
    def obter(_url: str, parcial: Path) -> int:
        parcial.write_bytes(b"")
        return 0

    with pytest.raises(ValueError, match="vazio"):
        ia_local.baixar("https://exemplo/modelo.gguf", obter=obter)


def test_baixar_recusa_disco_quase_cheio(dados: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ia_local, "_livre", lambda _caminho: 10 * 1024 * 1024)
    with pytest.raises(ValueError, match="disco quase cheio"):
        ia_local.baixar("https://exemplo/modelo.gguf")


# ---------------------------------------------------------------------------
# Ligar e desligar
# ---------------------------------------------------------------------------

def test_ligar_escreve_as_tres_linhas_e_usa_o_maior_modelo(dados: Path, projeto: Path):
    _gguf(ia_local.pasta(), "pequeno.gguf", 10)
    _gguf(ia_local.pasta(), "modelo-bom.gguf", 4_096)
    resultado = ia_local.ligar(raiz=projeto, ensaiar=False)
    assert resultado["modelo"] == "modelo-bom.gguf"
    assert resultado["porta_aberta"] is False
    assert "nada está escutando" in resultado["resumo"]
    texto = (projeto / ".env").read_text(encoding="utf-8")
    assert "JARVIS_AI_BASE_URL=http://127.0.0.1:8080/v1" in texto
    assert "JARVIS_AI_MODEL=modelo-bom.gguf" in texto
    assert "JARVIS_DONO=1" in texto


def test_ligar_sem_modelo_recusa_com_o_proximo_passo(dados: Path, projeto: Path):
    with pytest.raises(ValueError, match="acao=baixar"):
        ia_local.ligar(raiz=projeto, ensaiar=False)


def test_ligar_recusa_endereco_de_outro_pc(dados: Path, projeto: Path):
    _gguf(ia_local.pasta())
    with pytest.raises(ValueError, match="desta máquina"):
        ia_local.ligar(base="http://192.168.0.10:8080/v1", raiz=projeto, ensaiar=False)
    # e não sujou o .env
    assert "MODELO" not in (projeto / ".env").read_text(encoding="utf-8").upper()


def test_ligar_completa_o_gguf_quando_o_nome_vem_sem_extensao(dados: Path, projeto: Path):
    _gguf(ia_local.pasta(), "meu.gguf")
    resultado = ia_local.ligar(modelo="meu", raiz=projeto, ensaiar=False)
    assert resultado["modelo"] == "meu.gguf"


def test_desligar_restaura_o_env_como_era(dados: Path, projeto: Path):
    original = (projeto / ".env").read_text(encoding="utf-8")
    _gguf(ia_local.pasta())
    ia_local.ligar(raiz=projeto, ensaiar=False)
    assert "meu" not in original
    resultado = ia_local.desligar(raiz=projeto)
    assert resultado["restaurado"] is True
    assert (projeto / ".env").read_text(encoding="utf-8") == original
    assert not (projeto / "env.antes-do-modelo-local").exists()


def test_desligar_sem_copia_tira_so_as_chaves_da_ia(tmp_path: Path):
    raiz = tmp_path / "sem-copia"
    raiz.mkdir()
    (raiz / ".env").write_text(
        "JARVIS_DONO=1\nJARVIS_AI_PROVIDER=Modelo local\nJARVIS_AI_MODEL=x.gguf\n",
        encoding="utf-8",
    )
    resultado = ia_local.desligar(raiz)
    assert resultado["desligado"] is True
    assert resultado["restaurado"] is False
    texto = (raiz / ".env").read_text(encoding="utf-8")
    assert "JARVIS_DONO=1" in texto
    assert "JARVIS_AI_MODEL" not in texto


def test_desligar_quando_nada_foi_ligado_nao_mexe(tmp_path: Path):
    raiz = tmp_path / "intacto"
    raiz.mkdir()
    resultado = ia_local.desligar(raiz)
    assert resultado["desligado"] is False
    assert "já não aponta" in resultado["resumo"]


# ---------------------------------------------------------------------------
# Estado e porta
# ---------------------------------------------------------------------------

def test_porta_aberta_enxerga_um_socket_de_verdade(dados: Path):
    with socket.socket() as servidor:
        servidor.bind(("127.0.0.1", 0))
        servidor.listen(1)
        porta = servidor.getsockname()[1]
        assert ia_local.porta_aberta(f"http://127.0.0.1:{porta}/v1") is True


def test_porta_fechada_devolve_falso(dados: Path):
    with socket.socket() as livre:
        livre.bind(("127.0.0.1", 0))
        porta = livre.getsockname()[1]
    # o socket foi fechado: ninguém escuta nesse número agora
    assert ia_local.porta_aberta(f"http://127.0.0.1:{porta}/v1") is False


def test_estado_sem_modelo_diz_o_que_falta(dados: Path):
    resultado = ia_local.estado()
    assert resultado["configurado"] is False
    assert resultado["modelos"] == []
    assert ".gguf" in resultado["resumo"] or "não é esta máquina" in resultado["resumo"]


def test_estado_com_modelo_e_porta_aberta_nao_exige_chave(dados: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JARVIS_AI_BASE_URL", "http://127.0.0.1:8080/v1")
    monkeypatch.setenv("JARVIS_AI_MODEL", "modelo.gguf")
    monkeypatch.delenv("JARVIS_AI_API_KEY", raising=False)
    _gguf(ia_local.pasta(), "modelo.gguf", 3_000)
    monkeypatch.setattr(ia_local, "porta_aberta", lambda *_a, **_k: True)
    resultado = ia_local.estado()
    assert resultado["local"] is True
    assert resultado["com_chave"] is False
    assert resultado["porta_aberta"] is True
    assert resultado["configurado"] is True
    assert "Sem chave" in resultado["resumo"]


def test_estado_com_modelo_e_porta_fechada_manda_subir_o_servidor(dados: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JARVIS_AI_BASE_URL", "http://127.0.0.1:8080/v1")
    monkeypatch.setenv("JARVIS_AI_MODEL", "modelo.gguf")
    _gguf(ia_local.pasta(), "modelo.gguf", 3_000)
    monkeypatch.setattr(ia_local, "porta_aberta", lambda *_a, **_k: False)
    resultado = ia_local.estado()
    assert "llama-server" in resultado["resumo"]


# ---------------------------------------------------------------------------
# Skill e API
# ---------------------------------------------------------------------------

def test_a_skill_esta_no_catalogo(tmp_path: Path):
    catalogo = {item["id"]: item for item in build_registry(tmp_path / "files").list()}
    assert "ia.local" in catalogo
    skill = catalogo["ia.local"]
    assert skill["category"] == "IA"
    assert skill["requiresConfirmation"] is False
    acao = skill["inputSchema"]["properties"]["acao"]
    assert acao["default"] == "estado"
    assert "ligar" in acao["pattern"]


def test_pela_api_confere_o_estado(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JARVIS_DADOS", str(tmp_path / "dados"))
    monkeypatch.delenv("JARVIS_AI_BASE_URL", raising=False)
    cliente = TestClient(create_app(registry=build_registry(tmp_path / "files")))
    with cliente:
        resposta = cliente.post(
            "/api/skills/ia.local/execute",
            json={"parameters": {"acao": "estado"}, "confirmed": False},
        )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["ok"] is True
    assert "modelos" in corpo["result"]
    json.dumps(corpo)  # serializável pela API


def test_pela_api_baixar_sem_url_explica_em_vez_de_estourar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("JARVIS_DADOS", str(tmp_path / "dados"))
    cliente = TestClient(create_app(registry=build_registry(tmp_path / "files")))
    with cliente:
        resposta = cliente.post(
            "/api/skills/ia.local/execute",
            json={"parameters": {"acao": "baixar"}, "confirmed": False},
        )
    # A API devolve 200 com `ok: false` e a explicação em português: erro de
    # uso não é falha do servidor.
    corpo = resposta.json()
    assert corpo["ok"] is False
    # Recusa de uso chega legível (SKILL_ERROR), não como "falha interna".
    assert corpo["error"]["code"] == "SKILL_ERROR"
    assert "url" in corpo["error"]["message"].lower()
