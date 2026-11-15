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

# 0.80.1 — o mesmo catálogo da tela, em versão mínima. Este script roda sozinho
# (sem importar o servidor) e é o caminho de quem prefere não abrir a interface.
# Cada linha: nome exibido, base, modelo padrão, preço honesto.
CATALOGO = {
    "groq": ("Groq", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", "grátis, sem cartão"),
    "google": (
        "Google Gemini",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "gemini-2.5-flash",
        "grátis nos Flash (o conteúdo pode treinar os produtos do Google)",
    ),
    "openrouter": ("OpenRouter", "https://openrouter.ai/api/v1", "deepseek/deepseek-chat-v3-0324:free", "grátis só nos modelos :free"),
    "mistral": ("Mistral", "https://api.mistral.ai/v1", "mistral-small-latest", "grátis no modo Experiment"),
    "deepseek": ("DeepSeek", "https://api.deepseek.com/v1", "deepseek-chat", "pago, por token (barato)"),
    "anthropic": ("Claude (Anthropic)", "https://api.anthropic.com/v1", "claude-sonnet-4-5", "pago"),
    "openai": ("OpenAI", "https://api.openai.com/v1", "gpt-4o-mini", "pago"),
    "cerebras": ("Cerebras", "https://api.cerebras.ai/v1", "gpt-oss-120b", "teste de US$ 5 com cartão"),
}

# A cara da chave diz de quem ela é. `sk-` sozinho fica fora: DeepSeek, OpenAI e
# outros usam o mesmo prefixo — chutar mandaria a chave para o endereço errado.
POR_PREFIXO = (
    ("sk-ant-", "anthropic"),
    ("sk-or-v1-", "openrouter"),
    ("gsk_", "groq"),
    ("csk-", "cerebras"),
    ("AIza", "google"),  # formato antigo
    ("AQ.", "google"),   # formato novo do AI Studio (AQ.Ab8...)
)


def provedor_da_chave(chave: str) -> str | None:
    """Qual id do catálogo a chave denuncia. `None` quando é ambígua."""
    limpa = (chave or "").strip()
    for prefixo, identificador in POR_PREFIXO:
        if limpa.startswith(prefixo):
            return identificador
    return None


def preencher_do_catalogo(args: argparse.Namespace) -> None:
    """`--provedor openrouter` passa a valer endereço e modelo, como na tela."""
    achado = CATALOGO.get((args.provedor or "").strip().lower())
    if not achado:
        return
    nome, base, modelo, _preco = achado
    args.provedor = nome
    args.base = args.base or base
    args.modelo = args.modelo or modelo
    args.preco = _preco


def preencher_pela_chave(args: argparse.Namespace) -> None:
    """Chave colada/arquivo define o provedor quando ele não foi escolhido."""
    identificador = provedor_da_chave(args.chave or "")
    achado = CATALOGO.get(identificador or "")
    if not achado:
        return
    if args.provedor and args.provedor.strip().lower() not in CATALOGO:
        return  # escolha explícita na linha de comando vence a dedução
    nome, base, modelo, _preco = achado
    args.provedor = nome
    args.base = args.base or base
    args.modelo = args.modelo or modelo
    args.preco = _preco


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
    r"AIza[A-Za-z0-9_-]{30,}",        # Google AI Studio (formato antigo)
    r"AQ\.[A-Za-z0-9_-]{20,}",        # Google AI Studio (formato novo, AQ.Ab8...)
)


def sem_controle(texto: str) -> str:
    """Fora os caracteres de controle (0x00–0x1F e 0x7F).

    0.91.7 — no PC do dono a chave gravada era `\x16abc\x16`. O `\x16` é o
    **Ctrl+V**: no console do Windows 10 antigo ele não cola, escreve esse
    caractere. Se a pessoa digitar assim de novo, o lixo sai aqui antes de ir
    para o `.env`.
    """
    # `\t`, `\n` e `\r` ficam: é neles que as chaves estão separadas. Tirar a
    # quebra de linha colaria duas linhas e a extração pegaria chave a mais.
    return "".join(c for c in (texto or "") if c in "\t\n\r" or (c >= " " and c != "\x7f"))


def chaves_do_texto(texto: str) -> list[str]:
    """Acha chaves dentro de um arquivo de anotações — sem repetir.

    Serve para o caso mais comum: a pessoa anotou as três chaves num `.txt`
    ("api groq 1 gsk_…"), e digitar 56 caracteres três vezes sem errar é
    exatamente onde se perde uma letra. Aqui o arquivo é lido inteiro e só o
    que tem cara de chave é aproveitado.
    """
    achadas: list[str] = []
    for padrao in _PADROES_CHAVE:
        for achado in re.findall(padrao, sem_controle(texto)):
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


def guia_do_provedor(provedor: str, base: str) -> dict[str, str]:
    """Onde pegar a chave e o que digitar — do mesmo catálogo que a tela usa.

    0.91.8 — medido no PC do dono: o script abria com
    `Provedor [OpenRouter]:` e nenhuma palavra sobre **onde** criar a chave.
    Quem nunca fez isso fica parado no prompt. O dado já existia em
    `server/provedores.py` (`onde`, `nota`, `modelo`); faltava mostrar.
    """
    try:
        from server import provedores  # noqa: PLC0415 - só quem roda com o venv paga

        achado = provedores.por_id(provedor.strip().lower()) or provedores.por_base(base)
        if achado:
            return {
                "nome": str(achado.get("nome") or provedor),
                "onde": str(achado.get("onde") or ""),
                "modelo": str(achado.get("modelo") or ""),
                "nota": str(achado.get("nota") or ""),
                "gratis": str(achado.get("gratis") or ""),
            }
    except Exception:  # noqa: BLE001 - sem o pacote do servidor, o guia é opcional
        pass
    if "openrouter" in (provedor + base).lower():
        return {
            "nome": "OpenRouter",
            "onde": "openrouter.ai/keys",
            "modelo": "deepseek/deepseek-chat-v3-0324:free",
            "nota": "os gratuitos terminam em :free; o catálogo muda toda semana",
            "gratis": "sim, só o que termina em :free",
        }
    return {"nome": provedor, "onde": "", "modelo": "", "nota": "", "gratis": ""}


def mostrar_guia(guia: dict[str, str], *, colar: bool = False) -> None:
    """As três informações que faltavam no topo do script.

    `colar=True` muda o passo 3: com `--colar` a chave **não** é digitada nem
    colada no console — ela fica na área de transferência e o JARVIS lê de lá.
    Dizer "cole com o botão direito" nesse caminho seria ensinar o jeito antigo.
    """
    if not guia.get("onde"):
        return
    print(f"  Provedor: {guia['nome']}")
    print(f"  Onde pegar a chave:  {guia['onde']}")
    print("  1. abra esse endereço no navegador e entre (no OpenRouter dá para entrar com o Google)")
    print("  2. crie uma chave nova e clique no botão COPIAR (não selecione o texto com o mouse)")
    if colar:
        print("  3. volte para esta janela e rode de novo: o JARVIS lê a chave copiada sozinho")
        print("     (nada é digitado no console — é aí que as chaves se estragam)")
    else:
        print("  3. volte para esta janela e cole com o BOTÃO DIREITO do mouse")
        print("     (no console antigo do Windows o Ctrl+V não cola: ele escreve um símbolo)")
    if guia.get("nota"):
        print(f"  Modelo grátis: {guia['nota']}")
    if guia.get("modelo"):
        print(f"  Sugestão de modelo: {guia['modelo']}")
    print()


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


def abrir_no_navegador(endereco: str) -> bool:
    """Abre a página do provedor no navegador padrão. Não retorna nada de segredo."""
    if not endereco:
        return False
    url = endereco if endereco.startswith("http") else f"https://{endereco}"
    try:
        if sys.platform == "win32":
            os.startfile(url)  # type: ignore[attr-defined]
        else:
            import webbrowser  # noqa: PLC0415 - só quem pede paga

            webbrowser.open(url)
        return True
    except Exception:  # noqa: BLE001 - abrir navegador é conveniência, não requisito
        return False


def chave_da_area_de_transferencia() -> tuple[str, str]:
    """Lê a área de transferência e devolve (texto_limpo, chave_achada).

    A chave é procurada com os mesmos padrões do resto do programa: copiar a
    linha toda do site, ou um JSON com a chave dentro, funciona igual. O que não
    tem cara de chave é recusado — gravar lixo no `.env` foi o defeito da 0.91.7.
    """
    try:
        from server import area_transferencia  # noqa: PLC0415 - import tardio: só no Windows
    except Exception as exc:  # noqa: BLE001 - sem o pacote, a mensagem tem de ser clara
        raise RuntimeError(
            f"não consegui carregar o leitor da área de transferência ({type(exc).__name__}). "
            "Rode este script da pasta do JARVIS, com o .venv."
        ) from exc

    try:
        texto = area_transferencia.ler()
    except area_transferencia.AreaTransferenciaError as exc:
        raise RuntimeError(str(exc)) from exc

    limpo = sem_controle(texto).strip()
    if not limpo:
        raise RuntimeError(
            "a área de transferência está vazia. No site, clique no botão de COPIAR "
            "(não selecione o texto com o mouse) e rode este comando de novo."
        )
    achadas = chaves_do_texto(limpo)
    if not achadas:
        raise RuntimeError(
            "o que está copiado não tem cara de chave. O esperado começa com "
            "sk-or-v1- (OpenRouter), gsk_ (Groq), sk- (OpenAI) ou AIza/AQ. (Google)."
        )
    return limpo, achadas[0]


def descrever_area(limpo: str, chave: str) -> str:
    """Uma linha do que foi encontrado — sem a chave inteira."""
    return (
        f"  Copiado: {len(limpo)} caractere(s); chave reconhecida {mascarar(chave)}"
    )


def principal(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Grava a chave de IA no .env sem abrir editor de texto."
    )
    parser.add_argument("--ver", action="store_true", help="Mostra a configuração atual (chave mascarada) e sai.")
    parser.add_argument("--limpar", action="store_true", help="Apaga só a chave, mantendo as outras variáveis.")
    parser.add_argument(
        "--colar",
        action="store_true",
        help=(
            "Pega a chave da ÁREA DE TRANSFERÊNCIA (o que você copiou no site) em vez de "
            "pedir para digitar. É o caminho recomendado: digitar 73 caracteres num console "
            "antigo é onde as chaves se estragam."
        ),
    )
    parser.add_argument(
        "--abrir",
        action="store_true",
        help="Abre a página do provedor no navegador antes de colar (a chave é copiada lá).",
    )
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
    args.preco = ""  # preenchido pelo catálogo, quando o provedor é reconhecido

    # 0.80.1 — `--provedor openrouter` (id do catálogo) preenche endereço e
    # modelo. Quem usa a linha de comando não precisa mais decorar a URL.
    preencher_do_catalogo(args)
    if args.chave:
        preencher_pela_chave(args)

    if args.arquivo:
        try:
            do_arquivo = ler_arquivo_de_chaves(args.arquivo)
        except FileNotFoundError as exc:
            print(f"{exc}. Confira o caminho (pode arrastar o arquivo para a janela).")
            return 1
        if not do_arquivo:
            print("O arquivo não tem nenhuma chave reconhecível (gsk_…, sk-…, AIza…, AQ.…, sk-or-v1-…).")
            return 1
        print(f"Achei {len(do_arquivo)} chave(s) em {Path(args.arquivo).name}.")
        if args.so_mostrar:
            return 0
        # Entram na frente das que já estão no .env; duplicata é descartada.
        anteriores = separar_chaves(args.chave or "")
        args.chave = ",".join(separar_chaves(",".join(do_arquivo + anteriores)))
        # 0.80.1 — a primeira chave do arquivo diz o provedor, seja `gsk_`
        # (Groq), `sk-or-v1-` (OpenRouter) ou `AIza` (Google).
        sem_provedor = argparse.Namespace(
            provedor=args.provedor if not args.base and not args.modelo else None,
            base=args.base,
            modelo=args.modelo,
            chave=do_arquivo[0],
            preco="",
        )
        preencher_pela_chave(sem_provedor)
        args.provedor = args.provedor or sem_provedor.provedor
        args.base = sem_provedor.base
        args.modelo = sem_provedor.modelo
        if sem_provedor.preco:
            args.preco = sem_provedor.preco

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
    if getattr(args, "colar", False):
        print("A chave vem da ÁREA DE TRANSFERÊNCIA — você copia no site e nada é digitado aqui.")
    else:
        print("A chave é digitada sem aparecer na tela e não é gravada em histórico.")
    print("Deixe em branco para manter o valor atual.\n")

    _atual_provedor = args.provedor or ler_valor(texto, "JARVIS_AI_PROVIDER") or CAMPOS["JARVIS_AI_PROVIDER"]
    _atual_base = args.base or ler_valor(texto, "JARVIS_AI_BASE_URL") or CAMPOS["JARVIS_AI_BASE_URL"]
    if not local:
        mostrar_guia(guia_do_provedor(_atual_provedor, _atual_base), colar=bool(getattr(args, "colar", False)))

    provedor = args.provedor or perguntar("Provedor", ler_valor(texto, "JARVIS_AI_PROVIDER") or CAMPOS["JARVIS_AI_PROVIDER"])
    base = args.base or perguntar("Base da API", ler_valor(texto, "JARVIS_AI_BASE_URL") or CAMPOS["JARVIS_AI_BASE_URL"])
    modelo = args.modelo or perguntar("Modelo", ler_valor(texto, "JARVIS_AI_MODEL") or CAMPOS["JARVIS_AI_MODEL"])

    if base.rstrip("/").endswith("/chat/completions"):
        print("\nA base não deve terminar em /chat/completions — o servidor acrescenta esse caminho.")
        base = base.rstrip("/")[: -len("/chat/completions")]
    # O servidor monta f"{base}/chat/completions"; barra sobrando viraria "//".
    base = base.rstrip("/") or base

    # ---- caminho novo: copiar no navegador e deixar o JARVIS ler ----
    if args.colar:
        guia = guia_do_provedor(_atual_provedor, _atual_base)
        if args.abrir and guia.get("onde"):
            if abrir_no_navegador(guia["onde"]):
                print(f"  Abri {guia['onde']} no navegador.")
                print("  Se você já está logado: Create Key → dê um nome → botão COPIAR.")
                print("  Depois volte para esta janela.")
                return 0
            print(f"  Não consegui abrir o navegador. Abra na mão: {guia['onde']}")
            return 1
        print("  Lendo a área de transferência...")
        try:
            limpo, chave = chave_da_area_de_transferencia()
        except RuntimeError as exc:
            print(f"\n  NÃO DEU: {exc}")
            if guia.get("onde"):
                print(f"\n  A chave é criada em {guia['onde']}: Create Key → botão COPIAR.")
            print("  Não digite a chave no console: copie no navegador e rode --colar de novo.")
            return 1
        print(descrever_area(limpo, chave))
        args.chave = chave
    elif args.abrir:
        guia = guia_do_provedor(_atual_provedor, _atual_base)
        if guia.get("onde") and abrir_no_navegador(guia["onde"]):
            print(f"  Abri {guia['onde']} no navegador.")
            return 0
        print("  Não consegui abrir o navegador.")
        return 1

    chave = args.chave
    if chave is None and not local:
        if interativo():
            _guia = guia_do_provedor(_atual_provedor, _atual_base)
            if _guia.get("onde"):
                print(f"\n  Chave de: {_guia['onde']}  —  cole com o botão direito do mouse.")
            try:
                digitada = getpass.getpass("Chave(s), uma ou separadas por vírgula (não aparece ao digitar): ")
                chave = sem_controle(digitada).strip()
                if chave != digitada.strip():
                    print("\nHavia caractere invisível na colagem (Ctrl+V no console antigo). Removi.")
                    print("Se a chave continuar inválida, cole de novo com o botão direito do mouse.")
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
    if getattr(args, "preco", ""):
        print(f"  preço:    {args.preco}")
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
