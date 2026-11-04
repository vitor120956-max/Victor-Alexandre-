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

try:
    import httpx  # só é usado no --testar; o resto do script funciona sem ele
except ImportError:  # pragma: no cover - ambiente sem httpx
    httpx = None  # type: ignore[assignment]

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


# Formatos de chave que os provedores usam. A lista existe para não confundir
# "api groq 1" com chave: só o que casa aqui é gravado.
_PADROES_CHAVE = (
    r"gsk_[A-Za-z0-9]{20,}",          # Groq
    r"sk-or-v1-[A-Za-z0-9]{20,}",     # OpenRouter
    r"sk-[A-Za-z0-9_-]{20,}",         # OpenAI e compatíveis
    r"AIza[A-Za-z0-9_-]{30,}",        # Google AI Studio
)


def chaves_do_texto(texto: str) -> list[str]:
    """Acha chaves dentro de um arquivo de anotações — sem repetir.

    Serve para o caso mais comum: a pessoa anotou as três chaves num `.txt`
    ("api groq 1 gsk_…"), e digitar 56 caracteres três vezes sem errar é
    exatamente onde se perde uma letra. Aqui o arquivo é lido inteiro e só o
    que tem cara de chave é aproveitado.
    """
    achadas: list[str] = []
    for padrao in _PADROES_CHAVE:
        for achado in re.findall(padrao, texto or ""):
            if achado not in achadas:
                achadas.append(achado)
    return achadas


def ler_arquivo_de_chaves(caminho: str) -> list[str]:
    """Lê o `.txt` em utf-8 e, se falhar, em latin-1 (Bloco de Notas antigo)."""
    alvo = Path(caminho).expanduser()
    if not alvo.is_file():
        raise FileNotFoundError(f"não achei o arquivo {alvo}")
    bruto = alvo.read_bytes()
    for codificacao in ("utf-8-sig", "latin-1"):
        try:
            return chaves_do_texto(bruto.decode(codificacao))
        except UnicodeDecodeError:
            continue
    return []


def separar_chaves(bruto: str) -> list[str]:
    """Mesma regra do servidor: vírgula, ponto e vírgula, barra ou quebra de linha."""
    vistas: set[str] = set()
    saida: list[str] = []
    for parte in re.split(r"[,;|\s]+", (bruto or "").strip()):
        parte = parte.strip()
        if parte and parte not in vistas:
            vistas.add(parte)
            saida.append(parte)
    return saida


def mascarar(chave: str | None) -> str:
    """Mascara uma ou várias chaves. Nunca imprime a chave inteira."""
    chaves = separar_chaves(chave or "")
    if not chaves:
        return "(vazia)"
    mascaradas = []
    for item in chaves:
        if len(item) <= 10:
            mascaradas.append(item[:2] + "…" + item[-2:])
        else:
            mascaradas.append(f"{item[:5]}…{item[-4:]} ({len(item)} caracteres)")
    if len(mascaradas) == 1:
        return mascaradas[0]
    return f"{len(mascaradas)} chaves: " + ", ".join(mascaradas)


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
    """Testa a chave — ou cada uma delas, se houver várias.

    Com três chaves, saber que "a segunda está no limite" vale mais que um
    "falhou" genérico: é o que decide se dá para trabalhar hoje ou não.
    """
    chaves = separar_chaves(chave)
    if len(chaves) > 1:
        resultados = []
        for indice, item in enumerate(chaves, 1):
            print(f"\nChave {indice} de {len(chaves)}:")
            resultados.append(_testar_uma(base, modelo, item))
        boas = sum(1 for ok in resultados if ok)
        print(f"\nResumo: {boas} de {len(resultados)} chave(s) respondendo.")
        if boas == 0:
            print("Nenhuma serve agora. O JARVIS continua respondendo pelo modelo local, se estiver ligado.")
        return boas > 0
    return _testar_uma(base, modelo, chaves[0] if chaves else "")


def _testar_uma(base: str, modelo: str, chave: str) -> bool:
    """Uma chamada real de 8 tokens, sem imprimir a chave."""
    if not chave:
        print("Não há chave gravada para testar. Rode sem --testar e informe a chave.")
        return False
    if not base or not modelo:
        print("Faltam JARVIS_AI_BASE_URL ou JARVIS_AI_MODEL no .env.")
        return False

    url = f"{base.rstrip('/')}/chat/completions"
    print(f"Testando {modelo} em {url} ...")
    if httpx is None:
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
        help="Grava a chave direto (aceita várias separadas por vírgula). Prefira deixar em branco: o padrão é digitar sem eco, sem deixar rastro no histórico.",
    )
    parser.add_argument(
        "--local",
        nargs="?",
        const="http://127.0.0.1:8080/v1",
        metavar="URL",
        help="Aponta para um servidor de IA rodando na sua maquina (llama.cpp, KoboldCpp, LM Studio, Ollama no Linux). Sem URL usa %(const)s. Grava a chave de mentira 'local', que esses servidores ignoram.",
    )
    parser.add_argument(
        "--arquivo",
        metavar="CAMINHO",
        help="Lê as chaves de um arquivo .txt (uma ou várias, em qualquer linha). "
        "Evita digitar 56 caracteres no escuro. Nada do arquivo é impresso.",
    )
    parser.add_argument(
        "--so-mostrar",
        dest="so_mostrar",
        action="store_true",
        help="Com --arquivo: diz quantas chaves achou e sai, sem gravar no .env.",
    )
    parser.add_argument(
        "--testar",
        action="store_true",
        help="Depois de gravar (ou com o que já está no .env), faz uma chamada real e diz se a chave, a base e o modelo funcionam.",
    )
    args = parser.parse_args(argv)

    if args.arquivo:
        try:
            do_arquivo = ler_arquivo_de_chaves(args.arquivo)
        except FileNotFoundError as exc:
            print(f"{exc}. Confira o caminho (pode arrastar o arquivo para a janela).")
            return 1
        if not do_arquivo:
            print("O arquivo não tem nenhuma chave reconhecível (gsk_…, sk-…, AIza…, sk-or-v1-…).")
            return 1
        print(f"Achei {len(do_arquivo)} chave(s) em {Path(args.arquivo).name}.")
        if args.so_mostrar:
            return 0
        # Entram na frente das que já estão no .env; duplicata é descartada.
        anteriores = separar_chaves(args.chave or "")
        args.chave = ",".join(separar_chaves(",".join(do_arquivo + anteriores)))
        if do_arquivo[0].startswith("gsk_"):
            args.provedor = args.provedor or "Groq"
            args.base = args.base or "https://api.groq.com/openai/v1"
            args.modelo = args.modelo or "llama-3.3-70b-versatile"

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

    # Modelo local desde a 0.75.0: o servidor aceita 127.0.0.1 sem chave. Antes
    # era preciso gravar o marcador `local`, porque a checagem exigia chave para
    # qualquer endereco — inclusive a propria maquina, o que travava o uso no
    # pendrive. O marcador continua aceito (nao atrapalha), mas nao e mais
    # gravado: chave vazia e o estado honesto de quem nao tem chave.
    local = bool(args.local)
    if local:
        args.provedor = args.provedor or "Modelo local (sem chave)"
        args.base = args.base or args.local

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
    if chave is None and not local:
        if interativo():
            try:
                chave = getpass.getpass("Chave(s), uma ou separadas por vírgula (não aparece ao digitar): ").strip()
            except (EOFError, KeyboardInterrupt):
                chave = ""
        else:
            # Sem terminal não há como pedir a chave sem ecoar: não inventa.
            chave = ""

    if not chave:
        atual = ler_valor(texto, CHAVE) if not local else ""
        if atual:
            print("\nNenhuma chave digitada; mantendo a que já estava gravada.")
            chave = atual
        elif local:
            chave = ""  # modelo local nao usa chave: e o caso normal, nao erro
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
    print(f"  chave:    {mascarar(chave) if chave else '(nenhuma - modelo local)'}")
    if args.testar:
        print()
        tester(base, modelo, chave)
        print()

    print("\nAgora reinicie o servidor para ele ler o arquivo novo:")
    if os.name == "nt":
        print(r"  Feche a janela do JARVIS no X e rode iniciar-jarvis.bat")
    else:
        print("  Encerre o processo da API e rode iniciar-jarvis.bat")
    print("Confira em http://127.0.0.1:8000/api/ai/status")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
