"""Atualização delta: baixar só o que mudou e perceber que há versão nova.

O contrato que estes testes protegem, em uma frase: *o manifesto é a verdade, o
hash é a prova, e o que roda em memória não é tocado até você mandar.*

- `gerar_manifesto` não pode incluir `.env`, `storage/`, `.git/` nem a si mesmo;
- `comparar` não pode marcar como alterado o que é igual (senão o delta vira
  zip de novo, só mais lento);
- `preparar` não pode aceitar arquivo cujo `sha256` não confere;
- `aplicar` não pode rodar sem confirmação, não pode sair da pasta do projeto e
  não pode deixar de guardar o backup do que substituiu;
- nada disso pode acontecer por causa de um teste: a raiz de dados é temporária.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import atualizacao
from server.agente_local import _pedido_direto_de_atualizacao
from server.app import create_app
from server.skill_registry import build_registry


# ------------------------------------------------------------------ auxiliares

def _sha(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


@pytest.fixture()
def projeto(tmp_path: Path) -> Path:
    base = tmp_path / "projeto"
    (base / "server").mkdir(parents=True)
    (base / "src" / "pages").mkdir(parents=True)
    (base / "server" / "app.py").write_text("print('app')\n", encoding="utf-8")
    (base / "src" / "pages" / "Home.tsx").write_text("export const A = 1;\n", encoding="utf-8")
    (base / "package.json").write_text('{"version":"0.74.0"}\n', encoding="utf-8")
    (base / ".env").write_text("SEGREDO=1\n", encoding="utf-8")
    (base / "storage").mkdir()
    (base / "storage" / "dados.json").write_text("{}\n", encoding="utf-8")
    (base / ".git").mkdir()
    (base / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    return base


@pytest.fixture()
def dados(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    raiz = tmp_path / "dados"
    raiz.mkdir()
    monkeypatch.setenv("JARVIS_DADOS", str(raiz))
    return raiz


def _remoto_alterando(projeto: Path, mudancas: dict[str, bytes]) -> tuple[dict, dict[str, bytes]]:
    """Manifesto remoto + conteúdo servido pela rede falsa."""
    manifesto = atualizacao.gerar_manifesto(raiz=projeto)
    manifesto["versao"] = "0.75.0"
    fonte: dict[str, bytes] = {}
    for caminho, conteudo in mudancas.items():
        manifesto["arquivos"][caminho] = {"sha256": _sha(conteudo), "bytes": len(conteudo)}
        fonte[caminho] = conteudo
    fonte[atualizacao.NOME_MANIFESTO] = json.dumps(manifesto).encode("utf-8")
    return manifesto, fonte


def _rede(fonte: dict[str, bytes]):
    base = atualizacao._base()

    def baixar(url: str) -> bytes:
        chave = url[len(base) + 1:]
        return fonte[chave]

    return baixar


# ------------------------------------------------------------------- manifesto

def test_o_manifesto_ignora_dado_do_usuario_e_o_proprio_manifesto(projeto: Path):
    manifesto = atualizacao.gerar_manifesto(raiz=projeto)
    arquivos = set(manifesto["arquivos"])
    assert "server/app.py" in arquivos
    assert manifesto["versao"] == "0.74.0"
    assert not any(nome.startswith(".env") for nome in arquivos)
    assert not [nome for nome in arquivos if nome.startswith(("storage/", ".git/"))]
    assert atualizacao.NOME_MANIFESTO not in arquivos
    assert manifesto["arquivos"]["server/app.py"]["bytes"] == len("print('app')\n")


def test_arquivo_pesado_ou_de_log_nao_entra(projeto: Path):
    (projeto / "server" / "debug.log").write_text("x", encoding="utf-8")
    (projeto / "server" / "antigo.pyc").write_bytes(b"\x00")
    arquivos = set(atualizacao.gerar_manifesto(raiz=projeto)["arquivos"])
    assert "server/debug.log" not in arquivos
    assert "server/antigo.pyc" not in arquivos


def test_gerenciado_recusa_caminho_perigoso():
    assert atualizacao.gerenciado(Path("server/app.py"))
    assert not atualizacao.gerenciado(Path("../fora.py"))
    assert not atualizacao.gerenciado(Path(".venv/Lib/site.py"))
    assert not atualizacao.gerenciado(Path(".env"))
    assert not atualizacao.gerenciado(Path("storage/estado.json"))


def test_comparar_nao_marca_igual_como_alterado(projeto: Path):
    manifesto = atualizacao.gerar_manifesto(raiz=projeto)
    local = atualizacao.hashes_locais(projeto)
    diferenca = atualizacao.comparar(manifesto, local)
    assert diferenca["baixar"] == []
    assert diferenca["iguais"] == len(manifesto["arquivos"])
    assert diferenca["extras"] == []


def test_comparar_acha_o_alterado_o_novo_e_a_sobra(projeto: Path):
    manifesto = atualizacao.gerar_manifesto(raiz=projeto)
    manifesto["arquivos"]["server/app.py"]["sha256"] = "0" * 64
    manifesto["arquivos"]["server/novo.py"] = {"sha256": "1" * 64, "bytes": 10}
    local = atualizacao.hashes_locais(projeto)
    local["server/sobra.py"] = "2" * 64
    diferenca = atualizacao.comparar(manifesto, local)
    caminhos = {item["caminho"]: item["novo"] for item in diferenca["baixar"]}
    assert caminhos == {"server/app.py": False, "server/novo.py": True}
    # bytes é o total a baixar: o alterado (13) + o novo (10)
    assert diferenca["bytes"] == 13 + 10
    assert diferenca["extras"] == ["server/sobra.py"]


def test_comparar_recusa_manifesto_vazio():
    with pytest.raises(ValueError):
        atualizacao.comparar({"arquivos": {}}, {})


# ------------------------------------------------------------------- verificar

def test_sem_a_variavel_a_checagem_automatica_esta_desligada(dados: Path, projeto: Path, monkeypatch):
    monkeypatch.delenv("JARVIS_ATUALIZACAO", raising=False)
    resultado = atualizacao.verificar(projeto=projeto)
    assert resultado["checou"] is False
    assert resultado["ligado"] is False
    assert "desligada" in resultado["motivo"]


def test_checagem_forcada_funciona_com_a_automatica_desligada(dados: Path, projeto: Path, monkeypatch):
    monkeypatch.delenv("JARVIS_ATUALIZACAO", raising=False)
    _, fonte = _remoto_alterando(projeto, {"server/app.py": b"print('novo')\n"})
    resultado = atualizacao.verificar(projeto=projeto, baixar=_rede(fonte), forcar=True)
    assert resultado["checou"] is True
    assert resultado["disponivel"] is True
    assert resultado["a_baixar"] == 1
    assert resultado["remota"] == "0.75.0"
    assert "em vez do zip" in resultado["resumo"]
    # ficou registrado no estado, para a tela não precisar checar de novo
    estado = json.loads((dados / "atualizacao" / "estado.json").read_text(encoding="utf-8"))
    assert estado["disponivel"] is True
    assert estado["remota"] == "0.75.0"
    assert estado["ultima_checagem"]


def test_ja_na_ultima_nao_inventa_atualizacao(dados: Path, projeto: Path):
    manifesto = atualizacao.gerar_manifesto(raiz=projeto)
    fonte = {atualizacao.NOME_MANIFESTO: json.dumps(manifesto).encode("utf-8")}
    resultado = atualizacao.verificar(projeto=projeto, baixar=_rede(fonte), forcar=True)
    assert resultado["disponivel"] is False
    assert resultado["a_baixar"] == 0
    assert "última" in resultado["resumo"]


def test_falha_de_rede_nao_derruba_e_aponta_o_plano_b(dados: Path, projeto: Path):
    def sem_rede(_url: str) -> bytes:
        raise OSError("sem rota para o host")

    resultado = atualizacao.verificar(projeto=projeto, baixar=sem_rede, forcar=True)
    assert resultado["checou"] is False
    assert "OSError" in resultado["motivo"]
    assert "atualizar.bat" in resultado["plano_b"]


# -------------------------------------------------------------------- preparar

def test_preparar_baixa_so_o_que_mudou(dados: Path, projeto: Path):
    _, fonte = _remoto_alterando(projeto, {
        "server/app.py": b"print('novo')\n",
        "src/pages/Nova.tsx": b"export const B = 2;\n",
    })
    resultado = atualizacao.preparar(projeto=projeto, baixar=_rede(fonte))
    assert resultado["preparado"] is True
    assert resultado["baixados"] == 2
    palco = Path(resultado["palco"])
    assert (palco / "files" / "server" / "app.py").read_bytes() == b"print('novo')\n"
    assert (palco / "files" / "src" / "pages" / "Nova.tsx").read_bytes() == b"export const B = 2;\n"
    # o que não mudou não foi baixado nem copiado para o palco
    assert not (palco / "files" / "src" / "pages" / "Home.tsx").exists()
    assert not (palco / "files" / "package.json").exists()
    # e o projeto continua intocado
    assert (projeto / "server" / "app.py").read_text(encoding="utf-8") == "print('app')\n"


def test_preparar_recusa_arquivo_com_hash_errado(dados: Path, projeto: Path):
    _, fonte = _remoto_alterando(projeto, {"server/app.py": b"print('novo')\n"})
    # a rede entrega outra coisa (arquivo corrompido no caminho ou servidor errado)
    fonte["server/app.py"] = b"print('malicioso')\n"
    resultado = atualizacao.preparar(projeto=projeto, baixar=_rede(fonte))
    assert resultado["preparado"] is False
    assert resultado["baixados"] == 0
    assert resultado["falhas"][0]["motivo"] == "sha256 não confere com o manifesto"
    assert "atualizar.bat" in resultado["resumo"]


def test_preparar_sem_nada_novo_nao_cria_palco(dados: Path, projeto: Path):
    manifesto = atualizacao.gerar_manifesto(raiz=projeto)
    fonte = {atualizacao.NOME_MANIFESTO: json.dumps(manifesto).encode("utf-8")}
    resultado = atualizacao.preparar(projeto=projeto, baixar=_rede(fonte))
    assert resultado["preparado"] is False
    assert "Nada mudou" in resultado["motivo"]


# --------------------------------------------------------------------- aplicar

def test_aplicar_exige_confirmacao(dados: Path, projeto: Path):
    with pytest.raises(ValueError):
        atualizacao.aplicar(projeto=projeto, confirmado=False)


def test_aplicar_sem_palco_explica_em_vez_de_quebrar(dados: Path, projeto: Path):
    with pytest.raises(ValueError, match="Não há atualização"):
        atualizacao.aplicar(projeto=projeto, confirmado=True)


def test_aplicar_troca_arquivo_guarda_backup_e_manda_reiniciar(dados: Path, projeto: Path):
    _, fonte = _remoto_alterando(projeto, {
        "server/app.py": b"print('novo')\n",
        "src/pages/Nova.tsx": b"export const B = 2;\n",
    })
    atualizacao.preparar(projeto=projeto, baixar=_rede(fonte))
    resultado = atualizacao.aplicar(versao="0.75.0", projeto=projeto, confirmado=True)
    assert resultado["aplicado"] is True
    assert resultado["versao"] == "0.75.0"
    assert resultado["substituidos"] == ["server/app.py"]
    assert resultado["adicionados"] == ["src/pages/Nova.tsx"]
    assert (projeto / "server" / "app.py").read_bytes() == b"print('novo')\n"
    assert (projeto / "src" / "pages" / "Nova.tsx").exists()
    backup = Path(resultado["backup"])
    assert (backup / "server" / "app.py").read_text(encoding="utf-8") == "print('app')\n"
    assert "iniciar-jarvis.bat" in resultado["reiniciar"]
    assert resultado["como_voltar"].startswith("Copie de volta")
    # `.env` e `storage/` não são tocados nem por engano
    assert (projeto / ".env").read_text(encoding="utf-8") == "SEGREDO=1\n"
    assert (projeto / "storage" / "dados.json").exists()


def test_aplicar_recusa_caminho_que_sai_do_projeto(dados: Path, projeto: Path):
    _, fonte = _remoto_alterando(projeto, {"server/app.py": b"print('novo')\n"})
    atualizacao.preparar(projeto=projeto, baixar=_rede(fonte))
    palco = dados / "atualizacao" / "0.75.0"
    pronto = json.loads((palco / "pronto.json").read_text(encoding="utf-8"))
    pronto["baixados"].append({"caminho": "../../fora.py", "bytes": 3, "novo": True})
    forjado = palco / "files" / "server" / "forjado.py"
    forjado.write_text("print(1)\n", encoding="utf-8")
    (palco / "pronto.json").write_text(json.dumps(pronto), encoding="utf-8")
    resultado = atualizacao.aplicar(versao="0.75.0", projeto=projeto, confirmado=True)
    assert resultado["recusados"] == ["../../fora.py"]
    assert not (projeto.parent.parent / "fora.py").exists()


def test_palco_com_falha_nao_aplica(dados: Path, projeto: Path):
    _, fonte = _remoto_alterando(projeto, {"server/app.py": b"print('novo')\n"})
    fonte["server/app.py"] = b"outro conteudo"
    atualizacao.preparar(projeto=projeto, baixar=_rede(fonte))
    with pytest.raises(ValueError, match="palco tem falhas"):
        atualizacao.aplicar(versao="0.75.0", projeto=projeto, confirmado=True)


# ------------------------------------------------------------------- integração

def test_as_quatro_skills_estao_no_catalogo(tmp_path: Path):
    registro = build_registry(tmp_path / "files")
    ids = {skill["id"] for skill in registro.list()}
    assert {
        "atualizacao.estado",
        "atualizacao.verificar",
        "atualizacao.preparar",
        "atualizacao.aplicar",
    } <= ids
    baixar = registro.get("atualizacao.preparar")
    aplicar = registro.get("atualizacao.aplicar")
    verificar = registro.get("atualizacao.verificar")
    assert baixar.side_effects is True and baixar.requires_confirmation is True
    assert aplicar.side_effects is True and aplicar.requires_confirmation is True
    # checar é barato e não muda nada: não pede confirmação
    assert verificar.side_effects is False and verificar.requires_confirmation is False


def test_a_api_checa_e_para_no_aviso(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Pela API: a checagem devolve o resumo e não aplica nada."""
    monkeypatch.setenv("JARVIS_DADOS", str(tmp_path / "dados"))
    projeto = tmp_path / "projeto"
    (projeto / "server").mkdir(parents=True)
    (projeto / "server" / "app.py").write_text("print('app')\n", encoding="utf-8")
    (projeto / "package.json").write_text('{"version":"0.74.0"}\n', encoding="utf-8")
    _, fonte = _remoto_alterando(projeto, {"server/app.py": b"print('novo')\n"})
    monkeypatch.setattr(atualizacao, "_baixar_url", _rede(fonte))

    cliente = TestClient(create_app(registry=build_registry(tmp_path / "files")))
    with cliente:
        resposta = cliente.post(
            "/api/skills/atualizacao.verificar/execute",
            json={"parameters": {"forcar": True}, "confirmed": False},
        )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["ok"] is True
    assert corpo["result"]["checou"] is True
    # a checagem não aplica nada: o arquivo é do teste e continua igual
    assert (projeto / "server" / "app.py").read_text(encoding="utf-8") == "print('app')\n"


# ------------------------------------------------------------------ no chat

@pytest.mark.parametrize(
    ("frase", "skill"),
    [
        ("tem versão nova?", "atualizacao.verificar"),
        ("saiu atualização?", "atualizacao.verificar"),
        ("atualiza o jarvis", "atualizacao.preparar"),
        ("baixa só o que mudou", "atualizacao.preparar"),
        ("puxa as melhorias", "atualizacao.preparar"),
        ("aplica a atualização", "atualizacao.aplicar"),
        ("como atualizo o windows", None),
        ("atualizar o celular", None),
        ("arruma o pc", None),
    ],
)
def test_o_pedido_de_atualizacao_cai_na_skill_certa(frase: str, skill: str | None):
    pedido = _pedido_direto_de_atualizacao(frase)
    assert (pedido or {}).get("skill_id") == skill
