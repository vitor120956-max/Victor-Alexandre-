from __future__ import annotations

from pathlib import Path

import pytest

from server.legal_corpus import LegalCorpus, article_number, parse_front_matter


@pytest.fixture(scope="module")
def corpus() -> LegalCorpus:
    return LegalCorpus(Path(__file__).resolve().parents[1] / "legal_data")


def test_corpus_loads_eight_documents_and_thousands_of_articles(corpus: LegalCorpus):
    sources = corpus.sources()
    assert sources["documentCount"] == 8
    assert sources["articleCount"] == 4_427
    assert {document["id"] for document in sources["documents"]} == {
        "constituicao", "codigo-civil", "codigo-penal", "clt", "eca", "cdc", "lgpd", "marco-civil",
    }


def test_exact_article_accepts_thousands_and_suffixes(corpus: LegalCorpus):
    assert article_number("art. 1.046") == "1046"
    assert article_number("6º-A") == "6-A"
    civil = corpus.article("codigo-civil", "1.046")
    assert civil["articleNumber"] == "1046"
    assert "sociedade em comandita simples" in civil["text"]
    suffixed = corpus.article("cdc", "54-F")
    assert suffixed["articleNumber"] == "54-F"


def test_search_is_accent_insensitive_and_returns_real_text(corpus: LegalCorpus):
    result = corpus.search("protecao de dados pessoais", "lgpd", limit=4)
    assert result["resultCount"] > 0
    assert result["returned"] <= 4
    assert all(item["documentId"] == "lgpd" for item in result["results"])
    assert all(item["text"].startswith("Art.") for item in result["results"])
    assert all(item["source"].startswith(("https://www.planalto.gov.br/", "https://normas.leg.br/")) for item in result["results"])
    assert all("informativo" in item["notice"].lower() for item in result["results"])


def test_search_can_find_consumer_right_of_withdrawal(corpus: LegalCorpus):
    result = corpus.search("arrependimento do consumidor", "cdc", limit=3)
    assert result["results"][0]["article"] == "Art. 49."
    assert "desistir do contrato" in result["results"][0]["text"]


def test_invalid_or_empty_legal_queries_fail_explicitly(corpus: LegalCorpus):
    with pytest.raises(ValueError, match="Documento não encontrado"):
        corpus.search("privacidade", "inexistente")
    with pytest.raises(ValueError, match="tema jurídico"):
        corpus.search("de da do")
    with pytest.raises(ValueError, match="não possui o artigo"):
        corpus.article("constituicao", "9999")


def test_front_matter_parser_preserves_body_and_quoted_metadata():
    metadata, body = parse_front_matter('---\ntitulo: "Lei: exemplo"\nrevogada: false\n---\n\n# Texto\nArt. 1º Teste.')
    assert metadata == {"titulo": "Lei: exemplo", "revogada": False}
    assert body.startswith("# Texto")
