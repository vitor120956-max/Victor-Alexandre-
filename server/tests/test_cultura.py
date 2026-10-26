"""Testes da camada de cultura: fontes, busca, download e persona."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from server import cultura

LIVRO = (
    "*** START OF THE PROJECT GUTENBERG EBOOK TESTE ***\n\n"
    + "\n\n".join(
        f"Era uma vez um caso simples. Ele olhou o céu e perguntou: por quê? "
        f"A resposta veio devagar, longa, cheia de voltas e de silêncios, {indice}."
        for indice in range(40)
    )
    + "\n\n*** END OF THE PROJECT GUTENBERG EBOOK TESTE ***\n"
)


def test_fontes_traz_o_gutenberg_e_sete_sites():
    dados = cultura.fontes()
    assert dados["total"] == 7
    ids = {fonte["id"] for fonte in dados["fontes"]}
    assert {"gutenberg", "standardebooks", "openlibrary", "wikisource", "dominiopublico"} <= ids
    gutenberg = next(f for f in dados["fontes"] if f["id"] == "gutenberg")
    assert "domínio público" in gutenberg["licenca"]
    assert "gutenberg.org/ebooks" in gutenberg["baixar"]


def test_limpar_gutenberg_tira_cabecalho_e_rodape():
    limpo = cultura.limpar_gutenberg(LIVRO)
    assert "START OF THE PROJECT GUTENBERG" not in limpo
    assert "END OF THE PROJECT GUTENBERG" not in limpo
    assert limpo.startswith("Era uma vez")


def test_buscar_no_gutenberg_devolve_id_e_texto():
    def baixar(url: str) -> str:
        assert "gutendex.com/books?search=machado" in url
        return json.dumps(
            {
                "count": 2,
                "results": [
                    {
                        "id": 59863,
                        "title": "Dom Casmurro",
                        "authors": [{"name": "Machado de Assis"}],
                        "languages": ["pt"],
                        "download_count": 1234,
                        "formats": {"text/plain; charset=utf-8": "https://www.gutenberg.org/ebooks/59863.txt.utf-8"},
                    }
                ],
            }
        )

    achado = cultura.buscar("machado", idioma="pt", baixar=baixar)
    assert achado["fonte"] == "gutenberg"
    assert achado["livros"][0]["id"] == 59863
    assert achado["livros"][0]["texto"].endswith("59863.txt.utf-8")
    assert achado["livros"][0]["autores"] == ["Machado de Assis"]


def test_buscar_na_open_library_le_metadados():
    def baixar(url: str) -> str:
        assert "openlibrary.org/search.json" in url
        return json.dumps(
            {"numFound": 1, "docs": [{"key": "/works/OL1W", "title": "Memórias Póstumas", "author_name": ["Machado"], "first_publish_year": 1881, "public_scan_b": True}]}
        )

    achado = cultura.buscar("machado", fonte="openlibrary", baixar=baixar)
    assert achado["livros"][0]["ano"] == 1881
    assert achado["livros"][0]["dominio_publico"] is True


def test_buscar_recusa_fonte_desconhecida():
    with pytest.raises(cultura.CulturaError):
        cultura.buscar("x", fonte="pirataria")


def test_buscar_recusa_consulta_curta():
    with pytest.raises(cultura.CulturaError):
        cultura.buscar("a")


def test_baixar_limpa_e_guarda_na_biblioteca():
    guardado: dict[str, object] = {}

    def guardar(titulo: str, texto: str, **extra: object) -> dict[str, object]:
        guardado.update({"titulo": titulo, "texto": texto, **extra})
        return {"titulo": titulo, "slug": "teste-abc123", "secoes": 12}

    resultado = cultura.baixar("59863", titulo="Dom Casmurro", baixar=lambda url: LIVRO, guardar=guardar)
    assert resultado["slug"] == "teste-abc123"
    assert guardado["tipo"] == "livro"
    assert "START OF" not in str(guardado["texto"])
    assert "Dom Casmurro" in resultado["resposta"]


def test_baixar_aceita_endereco_do_gutenberg():
    visto: list[str] = []

    def baixar(url: str) -> str:
        visto.append(url)
        return LIVRO

    cultura.baixar("https://www.gutenberg.org/ebooks/139", baixar=baixar, guardar=lambda t, x, **k: {"titulo": t, "slug": "x"})
    assert visto == ["https://www.gutenberg.org/ebooks/139.txt.utf-8"]


def test_baixar_recusa_livro_sem_numero():
    with pytest.raises(cultura.CulturaError):
        cultura.baixar("dom casmurro")


def test_baixar_recusa_texto_vazio():
    with pytest.raises(cultura.CulturaError):
        cultura.baixar("1", baixar=lambda url: "*** START ***\n*** END ***")


def test_analisar_estilo_mede_o_texto():
    cartao = cultura.analisar_estilo(LIVRO, nome="Teste")
    assert cartao["nome"] == "Teste"
    assert cartao["frases"] >= 20
    assert 0 < cartao["media_palavras"] < 60
    assert cartao["vocabulario"]
    assert any("Frase média" in regra for regra in cartao["regras"])
    assert any("estilo medido" in limite for limite in cartao["limites"])


def test_analisar_estilo_detecta_dialogo():
    falado = "\n\n".join(f"— Você vem? — perguntou ela, sem olhar para trás. — Eu vou, respondi, e o mundo girou mais uma vez." for _ in range(30))
    cartao = cultura.analisar_estilo(falado)
    assert "diálogo" in cartao["tom"]


def test_analisar_estilo_recusa_texto_curto():
    with pytest.raises(cultura.CulturaError):
        cultura.analisar_estilo("Frase curta. Outra frase.")


def test_persona_guarda_o_cartao(tmp_path: Path):
    cartao = cultura.persona("livro", nome="Machado", texto=LIVRO, raiz=tmp_path)
    assert cartao["arquivo"].endswith("personas.json")
    salvo = json.loads((tmp_path / "personas.json").read_text(encoding="utf-8"))
    assert salvo["personas"][0]["nome"] == "Machado"


def test_persona_sem_salvar_nao_escreve(tmp_path: Path):
    cultura.persona("livro", nome="X", texto=LIVRO, raiz=tmp_path, salvar=False)
    assert not (tmp_path / "personas.json").exists()


def test_persona_de_livro_inexistente_ensina():
    with pytest.raises(cultura.CulturaError) as erro:
        cultura.persona("livro que não existe aqui")
    assert "cultura.baixar" in str(erro.value)
