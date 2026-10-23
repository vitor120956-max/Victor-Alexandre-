#!/usr/bin/env python3
"""Sincroniza somente o recorte legal declarado, usando a API oficial do GitHub."""
from __future__ import annotations

import argparse
import json
import os
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "server" / "legal_data"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", help="Novo commit de ctresb/leis; atualiza index.json após o sucesso.")
    parser.add_argument("--check", action="store_true", help="Compara os arquivos sem gravar alterações.")
    args = parser.parse_args()
    index_path = ROOT / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    upstream = index["upstream"]
    commit = args.commit or upstream["commit"]
    token = os.getenv("JARVIS_GITHUB_TOKEN", "").strip()
    headers = {"Accept": "application/vnd.github.raw+json", "User-Agent": "jarvis-legal-sync"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    for document in index["documents"]:
        url = f"https://api.github.com/repos/{upstream['repository']}/contents/{document['upstreamPath']}?ref={commit}"
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=45) as response:
            content = response.read()
        if not 20 < len(content) <= 2_000_000:
            raise RuntimeError(f"Tamanho inesperado em {document['id']}")
        target = ROOT / document["file"]
        if args.check:
            status = "atualizado" if target.read_bytes() == content else "diferente"
            print(f"{document['id']}: {status}")
        else:
            temporary = target.with_suffix(".tmp")
            temporary.write_bytes(content)
            temporary.replace(target)
            print(f"{document['id']}: {len(content)} bytes")

    if args.commit and not args.check:
        upstream["commit"] = args.commit
        index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Referência atualizada para {args.commit}")


if __name__ == "__main__":
    main()
