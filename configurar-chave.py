#!/usr/bin/env python3
"""Grava a chave de IA no `.env` sem passar por editor de texto.

Por que existe: no Windows 10 antigo (1607, 1709, 1803) o Bloco de Notas não
entende quebra de linha Unix e mostra o `.env` inteiro numa linha só. Quem
salva nesse estado amassa o arquivo. Este script lê e grava com a quebra de
linha do Windows, preserva as outras variáveis e **nunca imprime a chave**.

Uso:
    py configurar-chave.py                 # pergunta provedor, base, modelo e chave
    py configurar-chave.py --ver           # mostra o que está gravado (chave mascarada)
    py configurar-chave.py --limpar        # apaga só a chave, mantendo o resto

O arquivo gerado fica em `<projeto>/.env`, que já está no `.gitignore`.
"""
from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
ENV = RAIZ / ".env"
EXEMPLO = RAIZ / ".env.example"

CAMPOS = {
    "JARVIS_AI_PROVIDER": "OpenAI",
    "JARVIS_AI_BASE_URL": "https://api.openai.com/v1",
    "JARVIS_AI_MODEL": "gpt-4o-mini",
}
CHAVE = "JARVIS_AI_API_KEY"


def ler_texto(caminho: Path) -> str:
    """Lê aceitando UTF-8 (com ou sem BOM) e caindo para cp1252.

    O Bloco de Notas antigo salva em ANSI por padrão; sem o fallback o script
    quebraria em arquivo com acento nos comentários.
    """
    bruto = caminho.read_bytes()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return bruto.decode(encoding)
        except UnicodeDecodeError:
            continue
    return bruto.decode("utf-8", errors="replace")


def texto_base() -> str:
    if ENV.is_file():
        return ler_texto(ENV)
    if EXEMPLO.is_file():
        return ler_texto(EXEMPLO)
    return ""


def ler_valor(texto: str, nome: str) -> str | None:
    achado = re.search(rf"(?m)^\s*{re.escape(nome)}\s*=(.*)$", texto)
    if achado is None:
        return None
    return achado.group(1).strip()


def definir(texto: str, nome: str, valor: str) -> str:
    """Troca (ou acrescenta) uma variável, preservando todas as outras linhas."""
    linha = f"{nome}={valor}"
    padrao = rf"(?m)^\s*{re.escape(nome)}\s*=.*$"
    if re.search(padrao, texto):
        return re.sub(padrao, lambda _: linha, texto, count=1)
    separador = "" if texto.endswith(("\n", "\r\n")) or not texto else "\n"
    return f"{texto}{separador}{linha}\n"


def gravar(texto: str, caminho: Path | None = None) -> Path:
    """Grava sempre em CRLF, a quebra de linha que o Bloco de Notas entende."""
    destino = Path(caminho) if caminho is not None else ENV
    normalizado = texto.replace("\r\n", "\n")
    destino.write_bytes(normalizado.replace("\n", "\r\n").encode("utf-8"))
    return destino


def mascarar(chave: str | None) -> str:
    if not chave:
        return "(vazia)"
    if len(chave) <= 10:
        return chave[:2] + "…" + chave[-2:]
    return f"{chave[:5]}…{chave[-4:]} ({len(chave)} caracteres)"


def interativo() -> bool:
    """True só quando há alguém digitando: no cmd do Windows, sim."""
    try:
        return bool(sys.stdin) and sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


def perguntar(rotulo: str, padrao: str) -> str:
    """Pergunta e, se não houver como perguntar, mantém o padrão."""
    if not interativo():
        print(f"{rotulo}: {padrao} (mantido)")
        return padrao
    try:
        resposta = input(f"{rotulo} [{padrao}]: ").strip()
    except EOFError:
        return padrao
    return resposta or padrao


def tester(base: str, modelo: str, chave: str) -> bool:
    """Faz uma chamada mínima de verdade e diz, em português, o que aconteceu.

    Não imprime a chave nem o corpo cru da resposta do provedor.
    """
    if not chave:
        print("Não há chave gravada para testar. Rode sem --testar e informe a chave.")
        return False
    if not base or not modelo:
        print("Faltam JARVIS_AI_BASE_URL ou JARVIS_AI_MODEL no .env.")
        return False

    url = f"{base.rstrip('/')}/chat/completions"
    print(f"Testando {modelo} em {url} ...")
    try:
        import httpx  # noqa: PLC0415 - só é necessário aqui
    except ImportError:
        print("O pacote httpx não está instalado; não dá para testar agora.")
        return False

    try:
        resposta = httpx.post(
            url,
            headers={"Authorization": f"Bearer {chave}", "Content-Type": "application/json"},
            json={
                "model": modelo,
                "messages": [{"role": "user", "content": "responda apenas: ok"}],
                "max_tokens": 8,
            },
            timeout=45.0,
        )
    except httpx.HTTPError as exc:
        print(f"Falhou na conexão: {type(exc).__name__}. Verifique a internet e a base da API.")
        return False

    if resposta.status_code == 200:
        try:
            texto_resposta = resposta.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            print("HTTP 200, mas a resposta não tem o formato esperado. Confira a base: ela precisa ser compatível com OpenAI.")
            return False
        amostra = " ".join(str(texto_resposta).split())[:80]
        print(f"FUNCIONOU. O modelo respondeu: {amostra!r}")
        return True

    mapa = {
        401: "a chave foi recusada (HTTP 401). Confira se copiou a chave inteira.",
        403: "a chave não tem permissão para este modelo (HTTP 403).",
        404: "base ou modelo não encontrado (HTTP 404). Copie o nome exato do modelo no painel do provedor.",
        422: "o provedor recusou o formato do pedido (HTTP 422). Provavelmente é o nome do modelo.",
        429: "cota ou limite de requisições estourado (HTTP 429). Tente mais tarde.",
    }
    print(mapa.get(resposta.status_code, f"o provedor respondeu HTTP {resposta.status_code}."))
    if resposta.status_code in (400, 404, 422):
        print("Dica: o nome do modelo muda com o tempo. Copie o identificador exato que aparece no painel do provedor.")
    return False


def principal(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Grava a chave de IA no .env sem abrir editor de texto."
    )
    parser.add_argument("--ver", action="store_true", help="Mostra a configuração atual (chave mascarada) e sai.")
    parser.add_argument("--limpar", action="store_true", help="Apaga só a chave, mantendo as outras variáveis.")
    parser.add_argument("--provedor", help="Nome exibido na interface. Ex.: OpenAI")
    parser.add_argument("--base", help="Base da API, sem /chat/completions. Ex.: https://api.openai.com/v1")
    parser.add_argument("--modelo", help="Nome exato do modelo na sua conta.")
    parser.add_argument(
        "--chave",
        help="Grava a chave direto. Prefira deixar em branco: o padrão é digitar sem eco, sem deixar rastro no histórico.",
    )
    parser.add_argument(
        "--local",
        nargs="?",
        const="http://127.0.0.1:8080/v1",
        metavar="URL",
        help="Aponta para um servidor de IA rodando na sua maquina (llama.cpp, KoboldCpp, LM Studio, Ollama no Linux). Sem URL usa %(const)s. Grava a chave de mentira 'local', que esses servidores ignoram.",
    )
    parser.add_argument(
        "--testar",
        action="store_true",
        help="Depois de gravar (ou com o que já está no .env), faz uma chamada real e diz se a chave, a base e o modelo funcionam.",
    )
    args = parser.parse_args(argv)

    texto = texto_base()

    if args.ver:
        print(f"Arquivo: {ENV if ENV.is_file() else '(ainda não existe; usaria o .env.example)'}")
        for nome, padrao in CAMPOS.items():
            print(f"  {nome} = {ler_valor(texto, nome) or padrao}")
        print(f"  {CHAVE} = {mascarar(ler_valor(texto, CHAVE))}")
        return 0

    if args.limpar:
        if not ENV.is_file():
            print("Não existe .env para limpar.")
            return 0
        gravar(definir(texto, CHAVE, ""))
        print(f"Chave apagada em {ENV}. As outras variáveis continuam iguais.")
        return 0

    # `--testar` sozinho confere o que já está gravado; junto de um valor a
    # gravar, ele confere depois de gravar.
    escrevendo = args.chave is not None or bool(args.provedor or args.base or args.modelo)
    if args.testar and not escrevendo:
        prova = tester(
            ler_valor(texto, "JARVIS_AI_BASE_URL") or CAMPOS["JARVIS_AI_BASE_URL"],
            ler_valor(texto, "JARVIS_AI_MODEL") or CAMPOS["JARVIS_AI_MODEL"],
            ler_valor(texto, CHAVE) or "",
        )
        return 0 if prova else 1

    if args.local:
        # Servidor local nao usa chave; o JARVIS exige um valor nao vazio para
        # considerar a IA configurada, entao gravamos um marcador.
        args.provedor = args.provedor or "Local (sem internet)"
        args.base = args.base or args.local
        if not args.chave:
            args.chave = "local"

    print("Configurar a IA externa do JARVIS")
    print("A chave é digitada sem aparecer na tela e não é gravada em histórico.")
    print("Deixe em branco para manter o valor atual.\n")

    provedor = args.provedor or perguntar("Provedor", ler_valor(texto, "JARVIS_AI_PROVIDER") or CAMPOS["JARVIS_AI_PROVIDER"])
    base = args.base or perguntar("Base da API", ler_valor(texto, "JARVIS_AI_BASE_URL") or CAMPOS["JARVIS_AI_BASE_URL"])
    modelo = args.modelo or perguntar("Modelo", ler_valor(texto, "JARVIS_AI_MODEL") or CAMPOS["JARVIS_AI_MODEL"])

    if base.rstrip("/").endswith("/chat/completions"):
        print("\nA base não deve terminar em /chat/completions — o servidor acrescenta esse caminho.")
        base = base.rstrip("/")[: -len("/chat/completions")]
    # O servidor monta f"{base}/chat/completions"; barra sobrando viraria "//".
    base = base.rstrip("/") or base

    chave = args.chave
    if chave is None:
        if interativo():
            try:
                chave = getpass.getpass("Chave (não aparece ao digitar): ").strip()
            except (EOFError, KeyboardInterrupt):
                chave = ""
        else:
            # Sem terminal não há como pedir a chave sem ecoar: não inventa.
            chave = ""

    if not chave:
        atual = ler_valor(texto, CHAVE)
        if atual:
            print("\nNenhuma chave digitada; mantendo a que já estava gravada.")
            chave = atual
        else:
            print("\nNenhuma chave digitada e nenhuma gravada. Nada foi alterado.")
            return 1

    texto = definir(texto, "JARVIS_AI_PROVIDER", provedor)
    texto = definir(texto, "JARVIS_AI_BASE_URL", base)
    texto = definir(texto, "JARVIS_AI_MODEL", modelo)
    texto = definir(texto, CHAVE, chave)
    gravar(texto)

    print(f"\nGravado em {ENV}")
    print(f"  provedor: {provedor}")
    print(f"  base:     {base}")
    print(f"  modelo:   {modelo}")
    print(f"  chave:    {mascarar(chave)}")
    if args.testar:
        print()
        tester(base, modelo, chave)
        print()

    print("\nAgora reinicie o servidor para ele ler o arquivo novo:")
    if os.name == "nt":
        print(r"  Ctrl+C na janela atual, depois: .venv\Scripts\python iniciar.py")
    else:
        print("  Ctrl+C na janela atual, depois: .venv/bin/python iniciar.py")
    print("Confira em http://127.0.0.1:8000/api/ai/status")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
