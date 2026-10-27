#!/usr/bin/env python3
"""Liga a camada do celular no `.env` — sem abrir o Bloco de Notas.

O problema real: no Windows, um arquivo chamado `.env` é fácil de errar. O Bloco
de Notas salva como `.env.txt` quando você digita só `.env` no campo de nome, e aí
o JARVIS continua lendo um `.env` que não existe. Este script resolve isso do
jeito certo:

- acha o `.env` na raiz do projeto (o mesmo que `server/app.py` carrega);
- se não existir, cria a partir do `.env.example`;
- ajusta `JARVIS_HOST_REDE=1` e `JARVIS_HOST_CELULAR=1`, **substituindo** a linha
  se ela já existir (nada de duplicar chave);
- grava em UTF-8 sem BOM e com quebra CRLF, que é o que o Python do projeto lê;
- avisa se achar um `.env.txt` perdido no caminho;
- mostra o antes e o depois das duas linhas.

Não sobe servidor, não instala nada e não toca em nenhuma outra variável.

Uso:
    .venv\\Scripts\\python configurar-celular.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ARQUIVO = RAIZ / ".env"
EXEMPLO = RAIZ / ".env.example"

# o que liga a camada do celular; a terceira é o modo dono, que evita digitar o
# token na própria máquina (o pedido explícito do dono do projeto em 0.57.0)
AJUSTES = {
    "JARVIS_HOST_REDE": "1",
    "JARVIS_HOST_CELULAR": "1",
    "JARVIS_HOST_CONFIAR_LOCAL": "1",
}

EXPLICACOES = {
    "JARVIS_HOST_REDE": "libera a rede: baixar adb e scrcpy",
    "JARVIS_HOST_CELULAR": "liga as cinco skills celular.*",
    "JARVIS_HOST_CONFIAR_LOCAL": (
        "modo dono: nesta máquina você não digita o token "
        "(de outra máquina, continua pedindo)"
    ),
}


def _ler(caminho: Path) -> str:
    """Lê aceitando BOM (o Bloco de Notas adora colocar um)."""
    return caminho.read_text(encoding="utf-8-sig")


def _gravar(caminho: Path, texto: str) -> None:
    """Grava UTF-8 sem BOM e com CRLF — como o resto dos arquivos do projeto."""
    normalizado = texto.replace("\r\n", "\n").replace("\n", "\r\n")
    caminho.write_bytes(normalizado.encode("utf-8"))


def _chave_da_linha(linha: str) -> str:
    limpo = linha.strip()
    if not limpo or limpo.startswith("#") or "=" not in limpo:
        return ""
    return limpo.split("=", 1)[0].strip()


def ajustar(texto: str) -> tuple[str, dict[str, str], dict[str, str]]:
    """Troca (ou acrescenta) as chaves e devolve o texto e o antes/depois."""
    linhas = texto.replace("\r\n", "\n").split("\n")
    antes: dict[str, str] = {}
    trocadas: set[str] = set()

    for indice, linha in enumerate(linhas):
        chave = _chave_da_linha(linha)
        if chave in AJUSTES:
            antes[chave] = linha.strip()
            linhas[indice] = f"{chave}={AJUSTES[chave]}"
            trocadas.add(chave)

    faltando = [chave for chave in AJUSTES if chave not in trocadas]
    if faltando:
        while linhas and not linhas[-1].strip():
            linhas.pop()
        linhas.append("")
        linhas.append("# --- Celular pelo PC ------------------------------------------------")
        linhas.append("# Liga adb/scrcpy: celular.status, celular.plano, celular.espelhar,")
        linhas.append("# celular.puxar e celular.preparar. Nao liga a Depuracao USB do aparelho.")
        for chave in faltando:
            linhas.append(f"{chave}={AJUSTES[chave]}")
            antes.setdefault(chave, "(não existia)")

    depois = {chave: f"{chave}={valor}" for chave, valor in AJUSTES.items()}
    return "\n".join(linhas).rstrip("\n") + "\n", antes, depois


def main() -> int:
    print()
    print("  JARVIS - ligar a camada do celular (.env)")
    print()

    perdido = RAIZ / ".env.txt"
    if perdido.exists() and not ARQUIVO.exists():
        print("  Achei um '.env.txt' no lugar do '.env' - era isso que estava errado.")
        shutil.move(str(perdido), str(ARQUIVO))
        print("  Renomeei para '.env'.")
        print()

    criado = False
    if not ARQUIVO.exists():
        if EXEMPLO.exists():
            shutil.copyfile(EXEMPLO, ARQUIVO)
            print("  O '.env' nao existia. Criei a partir do '.env.example'.")
        else:
            ARQUIVO.write_text("", encoding="utf-8")
            print("  O '.env' nao existia e o '.env.example' tambem nao. Criei vazio.")
        criado = True
        print()

    original = _ler(ARQUIVO)
    novo, antes, depois = ajustar(original)

    if novo == _ler(ARQUIVO).replace("\r\n", "\n") and not criado:
        print("  Ja estava tudo certo:")
    else:
        _gravar(ARQUIVO, novo)
        print("  Gravado em:", ARQUIVO)
        print()

    for chave in AJUSTES:
        print(f"  {chave}")
        print(f"     antes:  {antes.get(chave, '(não existia)')}")
        print(f"     agora:  {depois[chave]}")
        print(f"     para:   {EXPLICACOES.get(chave, '')}")
        print()

    print("  Outras variaveis do arquivo nao foram tocadas.")
    print()
    print("  O modo dono vale so para a propria maquina (127.0.0.1). Para desligar,")
    print("  troque JARVIS_HOST_CONFIAR_LOCAL=1 por =0 no .env e reinicie.")
    print()
    print("  Agora faca:")
    print("    1) feche a janela da API no X (nao digite nada nela)")
    print("    2) .venv\\Scripts\\python iniciar.py")
    print("    3) confira a primeira linha do banner:")
    print("       rede=ligada ... celular=ligado")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
