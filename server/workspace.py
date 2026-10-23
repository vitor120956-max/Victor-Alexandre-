"""Regras compartilhadas da área de arquivos confinada do JARVIS."""
from __future__ import annotations

from pathlib import Path, PurePosixPath
from urllib.parse import quote

TEXT_EXTENSIONS = {".txt", ".md", ".json", ".csv", ".log"}
DOCUMENT_EXTENSIONS = {".docx", ".xlsx", ".pptx", ".pdf"}
VISIBLE_EXTENSIONS = TEXT_EXTENSIONS | DOCUMENT_EXTENSIONS
MAX_DOCUMENT_BYTES = 25_000_000
MAX_DOCUMENT_TEXT = 100_000


def safe_path(root: Path, relative: str, *, allow_root: bool = False) -> Path:
    value = relative.strip().replace("\\", "/")
    pure = PurePosixPath(value)
    if pure.is_absolute() or "\x00" in value or any(part in {"..", ""} or part.startswith(".") for part in pure.parts):
        raise ValueError("Caminho inválido: use somente arquivos e subpastas visíveis dentro da área do JARVIS.")
    if not value and not allow_root:
        raise ValueError("Informe um arquivo.")
    root = root.resolve()
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("O caminho sai da área autorizada.") from exc
    return candidate


def regular_file(root: Path, relative: str, extensions: set[str], max_bytes: int) -> Path:
    path = safe_path(root, relative)
    if path.suffix.lower() not in extensions:
        raise ValueError("Formato não permitido nesta área.")
    if not path.is_file() or path.is_symlink():
        raise ValueError("Arquivo não encontrado na área do JARVIS.")
    if path.stat().st_size > max_bytes:
        raise ValueError(f"O arquivo excede o limite de {max_bytes // 1_000_000} MB.")
    return path


def download_url(relative: str) -> str:
    return f"/api/files/download?path={quote(relative, safe='')}"
