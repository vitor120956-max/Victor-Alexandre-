"""Consulta local a um recorte atribuído do acervo ctresb/leis."""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_NOTICE = (
    "Conteúdo informativo. Confirme o texto e a vigência na fonte oficial; "
    "não substitui o Diário Oficial nem orientação jurídica profissional."
)
_ARTICLE_PATTERN = re.compile(
    r"^[ \t]*(?:#{1,6}[ \t]+)?(?:\*\*)?Art\.?[ \t]*(\d{1,3}(?:\.\d{3})+|\d+)(?:º)?(?:-([A-Z]))?\.?(?:\*\*)?(?=[ \t]|$)",
    re.IGNORECASE | re.MULTILINE,
)
_STOPWORDS = {
    "a", "o", "e", "de", "da", "do", "das", "dos", "em", "no", "na", "nos", "nas", "um", "uma",
    "para", "por", "com", "que", "se", "ao", "aos", "as", "os", "sobre", "lei", "leis", "legal",
    "artigo", "art", "qual", "quais", "diz", "dizem", "me", "mostre", "pesquisar", "buscar",
}
# Expansões lexicais pequenas ajudam temas comuns sem criar ou resumir conteúdo jurídico.
_TERM_VARIANTS = {
    "infantil": ("infantil", "crianca", "criancas", "menor", "menores", "adolescente", "adolescentes"),
    "expressao": ("expressao", "manifestacao", "comunicacao"),
    "arrependimento": ("arrependimento", "arrepender", "desistencia", "desistir"),
}


def fold_text(value: str) -> str:
    """Normaliza acentos preservando os índices para recortes no texto original."""
    output: list[str] = []
    for char in value.lower():
        output.append("".join(part for part in unicodedata.normalize("NFD", char) if not unicodedata.combining(part)))
    return "".join(output)


def clean_markdown(value: str) -> str:
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = value.replace("**", "").replace("__", "").replace("~~", "")
    value = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", value)
    value = re.sub(r"(?m)^\s*>\s?", "", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        return {}, text
    metadata: dict[str, Any] = {}
    for line in text[4:end].splitlines():
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, raw = line.split(":", 1)
        value = raw.strip()
        if value.startswith('"'):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                value = value.strip('"')
        elif value in {"true", "false"}:
            value = value == "true"  # type: ignore[assignment]
        metadata[key.strip()] = value
    body = text[end + 4:].lstrip("\r\n")
    return metadata, body


def article_number(value: str) -> str:
    match = re.search(r"(\d{1,3}(?:\.\d{3})+|\d+)(?:\s*º)?(?:\s*-?\s*([a-zA-Z]))?", fold_text(value))
    if not match:
        raise ValueError("Número de artigo inválido.")
    return match.group(1).replace(".", "") + (f"-{match.group(2).upper()}" if match.group(2) else "")


@dataclass(frozen=True)
class LegalArticle:
    reference: str
    number: str
    text: str
    folded: str
    truncated: bool = False


@dataclass(frozen=True)
class LegalDocument:
    id: str
    title: str
    short_title: str
    kind: str
    number: str
    date: str
    ementa: str
    situation: str
    version: str
    source: str
    upstream_path: str
    aliases: tuple[str, ...]
    articles: tuple[LegalArticle, ...]

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "shortTitle": self.short_title,
            "type": self.kind,
            "number": self.number,
            "date": self.date,
            "ementa": self.ementa,
            "situation": self.situation,
            "version": self.version,
            "source": self.source,
            "articleCount": len(self.articles),
            "upstreamPath": self.upstream_path,
        }


class LegalCorpus:
    def __init__(self, root: Path) -> None:
        self.root = root
        index = json.loads((root / "index.json").read_text(encoding="utf-8"))
        self.upstream = index["upstream"]
        self.documents = tuple(self._load_document(item) for item in index["documents"])
        self.by_id = {document.id: document for document in self.documents}

    def _load_document(self, item: dict[str, Any]) -> LegalDocument:
        raw = (self.root / item["file"]).read_text(encoding="utf-8")
        metadata, body = parse_front_matter(raw)
        title_match = re.search(r"(?m)^#\s+(.+)$", body)
        title = str(metadata.get("titulo") or (title_match.group(1) if title_match else item["shortTitle"]))
        source = item.get("source") or metadata.get("fonte") or f"{self.upstream['url']}/blob/{self.upstream['commit']}/{item['upstreamPath']}"
        articles: list[LegalArticle] = []
        matches = list(_ARTICLE_PATTERN.finditer(body))
        for position, match in enumerate(matches):
            end = matches[position + 1].start() if position + 1 < len(matches) else len(body)
            number = match.group(1).replace(".", "") + (f"-{match.group(2).upper()}" if match.group(2) else "")
            reference = clean_markdown(match.group(0)).strip()
            cleaned = clean_markdown(body[match.start():end])
            truncated = len(cleaned) > 16_000
            text = cleaned[:16_000] + ("\n\n[Trecho limitado; consulte a fonte oficial para o artigo completo.]" if truncated else "")
            articles.append(LegalArticle(reference, number, text, fold_text(text), truncated))
        if not articles:
            cleaned = clean_markdown(body)[:16_000]
            articles.append(LegalArticle("Texto integral", "", cleaned, fold_text(cleaned)))
        return LegalDocument(
            id=item["id"],
            title=title,
            short_title=item["shortTitle"],
            kind=str(metadata.get("tipo") or "Constituição Federal"),
            number=str(metadata.get("numero") or ""),
            date=str(metadata.get("data") or "1988-10-05"),
            ementa=str(metadata.get("ementa") or ""),
            situation=str(metadata.get("situacao") or ("Revogada" if metadata.get("revogada") is True else "Consulte a fonte oficial")),
            version=str(metadata.get("versao_texto") or "texto compilado"),
            source=str(source),
            upstream_path=item["upstreamPath"],
            aliases=tuple(item.get("aliases", [])),
            articles=tuple(articles),
        )

    def document(self, document_id: str) -> LegalDocument:
        try:
            return self.by_id[document_id]
        except KeyError as exc:
            raise ValueError(f"Documento não encontrado. Disponíveis: {', '.join(self.by_id)}.") from exc

    def sources(self) -> dict[str, Any]:
        return {
            "documents": [document.public() for document in self.documents],
            "documentCount": len(self.documents),
            "articleCount": sum(len(document.articles) for document in self.documents),
            "upstream": self.upstream,
            "notice": _NOTICE,
        }

    def article(self, document_id: str, article: str) -> dict[str, Any]:
        document = self.document(document_id)
        try:
            number = article_number(article)
        except ValueError as exc:
            raise ValueError("Informe um artigo válido, como 5, 49 ou 6-A.") from exc
        for item in document.articles:
            if item.number == number:
                return {
                    "documentId": document.id,
                    "documentTitle": document.title,
                    "documentShortTitle": document.short_title,
                    "article": item.reference,
                    "articleNumber": item.number,
                    "text": item.text,
                    "snippet": re.sub(r"\s+", " ", item.text[:500]).strip(),
                    "source": document.source,
                    "truncated": item.truncated,
                    "notice": _NOTICE,
                }
        raise ValueError(f"{document.short_title} não possui o artigo {number} neste recorte. Confira o número e o documento.")

    def search(self, query: str, document_id: str = "", limit: int = 6) -> dict[str, Any]:
        folded_query = fold_text(query.strip())
        tokens = [token for token in re.findall(r"[a-z0-9]+", folded_query) if len(token) >= 2 and token not in _STOPWORDS]
        if not tokens:
            raise ValueError("Descreva um tema jurídico com pelo menos uma palavra relevante.")
        documents = (self.document(document_id),) if document_id else self.documents
        results: list[dict[str, Any]] = []
        required_coverage = 1.0 if len(tokens) <= 3 else 0.6
        for document in documents:
            metadata = fold_text(f"{document.title} {document.short_title} {document.ementa}")
            for article in document.articles:
                matched: list[tuple[str, str]] = []
                for token in tokens:
                    variants = _TERM_VARIANTS.get(token, (token,))
                    found = next((variant for variant in variants if variant in article.folded), None)
                    if found:
                        matched.append((token, found))
                coverage = len(matched) / len(tokens)
                if coverage < required_coverage:
                    continue
                score = len(matched) * 5 + coverage * 12
                if folded_query in article.folded:
                    score += 28
                score += sum(4 for _, term in matched if term in metadata)
                positions = [article.folded.find(term) for _, term in matched]
                if len(positions) > 1:
                    span = max(positions) - min(positions)
                    if span <= 240:
                        score += 16
                    elif span <= 600:
                        score += 6
                first = matched[-1][1]
                plain = re.sub(r"\s+", " ", article.text).strip()
                folded_plain = fold_text(plain)
                position = max(0, folded_plain.find(first))
                start = max(0, position - 110)
                end = min(len(plain), position + 300)
                snippet = ("…" if start else "") + plain[start:end].strip() + ("…" if end < len(plain) else "")
                results.append({
                    "documentId": document.id,
                    "documentTitle": document.title,
                    "documentShortTitle": document.short_title,
                    "article": article.reference,
                    "articleNumber": article.number,
                    "snippet": snippet,
                    "text": article.text,
                    "source": document.source,
                    "score": round(score, 2),
                    "truncated": article.truncated,
                    "notice": _NOTICE,
                })
        results.sort(key=lambda item: (-item["score"], item["documentShortTitle"], item["articleNumber"]))
        return {
            "query": query,
            "results": results[:limit],
            "resultCount": len(results),
            "returned": min(limit, len(results)),
            "searchedDocuments": len(documents),
            "notice": _NOTICE,
        }
