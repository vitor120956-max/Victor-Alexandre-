"""Testes do modo sem Node (0.38.0): servir a interface embutida em `web-dist`.

O objetivo é permitir usar o JARVIS sem `npm install` — o caso de quem roda de
um pendrive lento. A API escolhe `dist/` quando existe (build local) e cai para
`web-dist/` (versionado) quando não existe.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.app import create_app, pasta_da_interface

RAIZ = Path(__file__).resolve().parents[2]
EMBUTIDA = RAIZ / "web-dist"


def _montar(tmp_path: Path, *, dist: bool = False, web: bool = True) -> Path:
    base = tmp_path / "projeto"
    base.mkdir()
    if dist:
        (base / "dist" / "assets").mkdir(parents=True)
        (base / "dist" / "index.html").write_text("<html>dist</html>", encoding="utf-8")
        (base / "dist" / "assets" / "app.js").write_text("console.log('dist')", encoding="utf-8")
    if web:
        (base / "web-dist" / "assets").mkdir(parents=True)
        (base / "web-dist" / "index.html").write_text("<html>embutida</html>", encoding="utf-8")
        (base / "web-dist" / "assets" / "app.js").write_text("console.log('embutida')", encoding="utf-8")
    return base


# ---------------------------------------------------------------------------
# Escolha da pasta
# ---------------------------------------------------------------------------


def test_sem_nenhuma_interface_devolve_none(tmp_path):
    base = _montar(tmp_path, dist=False, web=False)
    assert pasta_da_interface(base) is None


def test_prefere_dist_quando_existe(tmp_path):
    base = _montar(tmp_path, dist=True, web=True)
    escolhida = pasta_da_interface(base)
    assert escolhida is not None and escolhida.name == "dist"


def test_cai_para_web_dist_sem_dist(tmp_path):
    base = _montar(tmp_path, dist=False, web=True)
    escolhida = pasta_da_interface(base)
    assert escolhida is not None and escolhida.name == "web-dist"


def test_pasta_sem_index_nao_conta(tmp_path):
    base = _montar(tmp_path, dist=False, web=False)
    (base / "web-dist" / "assets").mkdir(parents=True)
    assert pasta_da_interface(base) is None


def test_repositorio_tem_interface_embutida():
    assert (EMBUTIDA / "index.html").is_file()
    assert list((EMBUTIDA / "assets").glob("*.js")), "web-dist precisa do bundle JavaScript"
    assert list((EMBUTIDA / "assets").glob("*.css")), "web-dist precisa do CSS"
    assert (EMBUTIDA / "LEIA-ME.txt").is_file()


def test_interface_embutida_e_pequena():
    arquivos = [item for item in EMBUTIDA.rglob("*") if item.is_file()]
    total = sum(item.stat().st_size for item in arquivos)
    assert len(arquivos) <= 40, f"{len(arquivos)} arquivos é demais para versionar"
    assert total < 5 * 1024 * 1024, f"{total} bytes é demais para versionar"


# ---------------------------------------------------------------------------
# Serviço HTTP
# ---------------------------------------------------------------------------


@pytest.fixture
def cliente(tmp_path):
    app = create_app(registry=None)
    return TestClient(app)


def test_api_health_declara_a_interface(cliente):
    dados = cliente.get("/api/health").json()
    assert dados["interface"] in {"dist", "web-dist", "ausente"}


def test_raiz_serve_html(cliente, monkeypatch):
    from server import app as modulo_app

    monkeypatch.setattr(modulo_app, "pasta_da_interface", lambda base=None: RAIZ / "web-dist")
    app = create_app(registry=None)
    resposta = TestClient(app).get("/")
    assert resposta.status_code == 200
    assert "text/html" in resposta.headers["content-type"]
    assert "<div id=\"root\"" in resposta.text or "<script" in resposta.text


def test_asset_embutido_e_servido(cliente, monkeypatch):
    from server import app as modulo_app

    monkeypatch.setattr(modulo_app, "pasta_da_interface", lambda base=None: RAIZ / "web-dist")
    app = create_app(registry=None)
    nome = next((RAIZ / "web-dist" / "assets").glob("*.js")).name
    resposta = TestClient(app).get(f"/assets/{nome}")
    assert resposta.status_code == 200
    assert "javascript" in resposta.headers["content-type"]


def test_rota_desconhecida_devolve_index(cliente, monkeypatch):
    from server import app as modulo_app

    monkeypatch.setattr(modulo_app, "pasta_da_interface", lambda base=None: RAIZ / "web-dist")
    app = create_app(registry=None)
    resposta = TestClient(app).get("/memoria")
    assert resposta.status_code == 200
    assert "text/html" in resposta.headers["content-type"]


def test_rota_de_api_desconhecida_da_404(cliente):
    assert cliente.get("/api/nao-existe").status_code == 404


def test_fuga_por_ponto_ponto_e_bloqueada(cliente, monkeypatch):
    from server import app as modulo_app

    monkeypatch.setattr(modulo_app, "pasta_da_interface", lambda base=None: RAIZ / "web-dist")
    app = create_app(registry=None)
    resposta = TestClient(app).get("/../server/app.py")
    assert resposta.status_code in {200, 403, 404}
    if resposta.status_code == 200:
        assert "pasta_da_interface" not in resposta.text


def test_sem_interface_responde_json(cliente, monkeypatch):
    from server import app as modulo_app

    monkeypatch.setattr(modulo_app, "pasta_da_interface", lambda base=None: None)
    app = create_app(registry=None)
    resposta = TestClient(app).get("/")
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["interface"] == "ausente"
    assert "como_ligar" in dados

# ---------------------------------------------------------------------------
# Lançador sem Node
# ---------------------------------------------------------------------------


def test_iniciar_py_responde_ajuda():
    import subprocess
    import sys

    processo = subprocess.run(
        [sys.executable, str(RAIZ / "iniciar.py"), "--help"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert processo.returncode == 0
    assert "Node" in processo.stdout
    assert "--porta" in processo.stdout


def test_iniciar_py_tem_modo_proprio_de_venv():
    texto = (RAIZ / "iniciar.py").read_text(encoding="utf-8")
    assert "JARVIS_SEM_VENV" in texto
    assert "web-dist" not in texto or "pasta_da_interface" in texto
