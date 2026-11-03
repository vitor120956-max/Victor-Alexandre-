"""Modelo local: conferir, baixar e ligar a IA que roda sem chave.

A pergunta que gerou este módulo foi *“podemos colocar a IA local no pen
drive?”*. A resposta curta é **sim para o programa e para o arquivo, não para a
memória** — e a diferença importa:

- o `llama-server.exe` é um programa: roda de onde estiver, inclusive do
  pendrive;
- o `.gguf` é o modelo: pode ficar no pendrive, mas a cada resposta ele é lido
  e carregado **na RAM** do PC. Pendrive não vira memória;
- sem chave nenhuma, o JARVIS aceita um endereço local (`127.0.0.1`) como
  provedor desde a 0.75.0. Antes ele exigia `JARVIS_AI_API_KEY` até para
  `localhost`, e isso travava exatamente quem queria tudo no pendrive.

## O que este módulo faz

| ação | o que acontece | toca em quê |
|---|---|---|
| `estado` | diz se há modelo, quanto ocupa, se a porta responde | nada |
| `baixar` | baixa um arquivo `.gguf` para a pasta do modelo, conferindo espaço antes | cria um `.gguf` |
| `ligar` | escreve as três linhas da IA local no `.env` (com cópia do antigo) | `.env` |
| `desligar` | devolve o `.env` como estava | `.env` |

## O que ele **não** faz

- **não** escolhe modelo por você nem acha que sabe sua RAM: baixar 2 GB num PC
  de 4 GB é pior do que não baixar. O tamanho vem no pedido, e o espaço livre é
  conferido antes de começar;
- **não** instala nada do sistema: nada de `pip`, nada de serviço, nada de
  registro do Windows. Só arquivo dentro da pasta do modelo;
- **não** baixa de qualquer lugar: só `http`/`https`, e um limite de tamanho
  (`JARVIS_MODELO_MAXIMO`, padrão 8 GB) para um link errado não encher o disco;
- **não** apaga o modelo antigo: trocar de modelo é apagar por fora, de
  propósito, para nunca “sumir” 2 GB por acidente;
- **não** sobe um servidor que não existe: se o `llama-server.exe` não estiver
  na pasta, `ligar` diz o que falta em vez de fingir que ligou.

## Por que ele não liga o processo sozinho no Windows

`ligar` escreve a configuração e **testa** a porta; subir o processo é feito pelo
`modelo-local.ps1` (`-Ligar`), chamado por você ou pela skill. Motivo: processo
filho de um servidor Python que reinicia fica órfão e ocupa a porta, e aí a
próxima tentativa falha com “endereço em uso” — erro que parece do modelo e não
é.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from . import dados as dados_locais

PASTA_MODELO = "modelo-local"
AMBIENTE_LIMITE = "JARVIS_MODELO_MAXIMO"
LIMITE_PADRAO = 8 * 1024 * 1024 * 1024  # 8 GB: o maior GGUF que ainda faz sentido
PEDACO = 1024 * 1024  # 1 MB por leitura: 2 GB em 2.000 pedaços, sem encher a RAM
# Abaixo disso nem tenta: o `.parcial` precisa caber junto com o Windows.
MINIMO_LIVRE = 512 * 1024 * 1024
TIMEOUT_PORTA = 0.4

# As três linhas que o `.env` passa a ter quando o modelo local está ligado.
CHAVES_IA = ("JARVIS_AI_PROVIDER", "JARVIS_AI_BASE_URL", "JARVIS_AI_MODEL")
BASE_PADRAO = "http://127.0.0.1:8080/v1"
PROVEDOR_PADRAO = "Modelo local"


def pasta(raiz: Path | None = None) -> Path:
    """Onde os modelos moram: `storage/modelo-local` (ou dentro do pendrive)."""
    return Path(raiz) if raiz is not None else dados_locais.raiz() / PASTA_MODELO


def limite() -> int:
    """Tamanho máximo aceito para um download, em bytes.

    Existe para um link errado (ou um `.gguf` de 70 B) não encher o disco em
    silêncio. Configurável porque há quem queira testar um modelo grande.
    """
    bruto = os.environ.get(AMBIENTE_LIMITE, "").strip()
    if not bruto:
        return LIMITE_PADRAO
    try:
        valor = int(bruto)
    except ValueError:
        return LIMITE_PADRAO
    return valor if valor > 0 else LIMITE_PADRAO


# ---------------------------------------------------------------------------
# Leitura e escrita do `.env`
# ---------------------------------------------------------------------------

def _arquivo_env(raiz: Path | None = None) -> Path:
    if raiz is not None:
        return Path(raiz) / ".env"
    return dados_locais.PROJETO / ".env"


def ler_env(raiz: Path | None = None) -> dict[str, str]:
    """Lê o `.env` como texto, sem interpretar: comentário e ordem ficam."""
    caminho = _arquivo_env(raiz)
    valores: dict[str, str] = {}
    if not caminho.exists():
        return valores
    for linha in caminho.read_text(encoding="utf-8", errors="replace").splitlines():
        limpa = linha.strip()
        if not limpa or limpa.startswith("#") or "=" not in limpa:
            continue
        chave, _, valor = limpa.partition("=")
        valores[chave.strip()] = valor.strip().strip('"').strip("'")
    return valores


def escrever_env(valores: dict[str, str], raiz: Path | None = None) -> Path:
    """Troca só as chaves pedidas, guardando uma cópia do `.env` anterior.

    Preserva comentários, ordem e linhas em branco: o `.env` é do usuário, não
    deste módulo, e reescrevê-lo do zero apagaria configuração que ele editou à
    mão. A cópia `env.antes-do-modelo-local` é o caminho de volta.
    """
    caminho = _arquivo_env(raiz)
    original = caminho.read_text(encoding="utf-8", errors="replace") if caminho.exists() else ""
    if original:
        copia = caminho.with_name("env.antes-do-modelo-local")
        if not copia.exists():
            copia.write_text(original, encoding="utf-8")

    linhas = original.splitlines()
    restantes = dict(valores)
    saida: list[str] = []
    for linha in linhas:
        limpa = linha.strip()
        chave = limpa.partition("=")[0].strip() if "=" in limpa and not limpa.startswith("#") else ""
        if chave in restantes:
            saida.append(f"{chave}={restantes.pop(chave)}")
        else:
            saida.append(linha)
    for chave, valor in restantes.items():
        saida.append(f"{chave}={valor}")
    caminho.write_text("\n".join(saida).rstrip("\n") + "\n", encoding="utf-8")
    return caminho


# ---------------------------------------------------------------------------
# Estado
# ---------------------------------------------------------------------------

def modelos(pasta_: Path | None = None) -> list[dict[str, Any]]:
    """Os `.gguf` que estão na pasta do modelo, do maior para o menor."""
    base = pasta(pasta_)
    if not base.exists():
        return []
    achados = []
    for arquivo in sorted(base.glob("*.gguf")):
        if arquivo.is_file():
            achados.append({"nome": arquivo.name, "caminho": str(arquivo), "bytes": arquivo.stat().st_size})
    achados.sort(key=lambda item: item["bytes"], reverse=True)
    return achados


def _endereco(base: str) -> tuple[str, int] | None:
    try:
        partes = urlsplit(base)
    except ValueError:
        return None
    if not partes.hostname:
        return None
    porta = partes.port or (443 if partes.scheme == "https" else 80)
    return partes.hostname, porta


def porta_aberta(base: str, timeout: float = TIMEOUT_PORTA) -> bool:
    """Alguém está escutando nesse endereço? Não faz requisição, só conecta.

    É um teste de tomada, não de modelo: porta aberta quer dizer “tem um servidor
    ali”, não “o modelo respondeu”. Separar as duas coisas evita dizer que a IA
    funciona quando o servidor subiu e o `.gguf` não carregou.
    """
    alvo = _endereco(base)
    if not alvo:
        return False
    try:
        with socket.create_connection(alvo, timeout=timeout):
            return True
    except OSError:
        return False


def estado(raiz: Path | None = None, base: Path | None = None) -> dict[str, Any]:
    """Retrato do modelo local: o que está configurado, o que existe em disco."""
    from .ai import e_local  # noqa: PLC0415  (import tardio: ai puxa httpx)

    # O ambiente ganha do `.env` — é o que o `load_dotenv` do app faz
    # (ele não sobrescreve variável já definida). Inverter a ordem faria o
    # `.env` do projeto mandar por cima de um teste ou de um `set` no prompt.
    valores = {**ler_env(raiz), **os.environ}
    endereco = valores.get("JARVIS_AI_BASE_URL", "").strip() or "(sem endereço)"
    modelo = valores.get("JARVIS_AI_MODEL", "").strip()
    chave = valores.get("JARVIS_AI_API_KEY", "").strip()
    local = e_local(endereco)
    achados = modelos(base)
    maior = achados[0] if achados else None
    aberta = porta_aberta(endereco) if local else False

    if not local:
        resumo = (
            f"A IA está apontada para {endereco}, que não é esta máquina. "
            "Para usar o modelo local, rode ia.local com acao=ligar."
        )
    elif not achados:
        resumo = (
            f"Modelo local configurado em {endereco}, mas não há arquivo .gguf em "
            f"{pasta(base)}. Baixe um antes: sem pesos não há resposta."
        )
    elif not aberta:
        resumo = (
            f"{maior['nome']} está na pasta ({_mb(maior['bytes'])}), mas nada está "
            f"escutando em {endereco}. Suba o llama-server (modelo-local.ps1 -Ligar)."
        )
    else:
        resumo = (
            f"Modelo local de pé em {endereco}: {modelo or maior['nome']}. "
            "Sem chave e sem internet — mais lento que a nuvem, mas funciona."
        )

    return {
        "configurado": bool(local and modelo and achados),
        "local": local,
        "endereco": endereco,
        "modelo": modelo or None,
        "com_chave": bool(chave),
        "porta_aberta": aberta,
        "pasta": str(pasta(base)),
        "modelos": achados,
        "espaco_livre_bytes": _livre(pasta(base)),
        "limite_bytes": limite(),
        "resumo": resumo,
    }


def _livre(caminho: Path) -> int:
    """Espaço livre no disco que contém a pasta (ou no pai mais próximo)."""
    alvo = caminho
    while not alvo.exists() and alvo != alvo.parent:
        alvo = alvo.parent
    try:
        return shutil.disk_usage(alvo).free
    except OSError:
        return 0


def _mb(bytes_: int) -> str:
    if bytes_ >= 1024 * 1024 * 1024:
        return f"{bytes_ / (1024 ** 3):.1f} GB"
    return f"{max(1, round(bytes_ / (1024 * 1024)))} MB"


# ---------------------------------------------------------------------------
# Baixar
# ---------------------------------------------------------------------------

def _nome_seguro(nome: str) -> str:
    """Só nome de arquivo: nada de `..`, barra ou letra de unidade do Windows."""
    limpo = Path(str(nome).replace("\\", "/")).name.strip()
    if not limpo or limpo in {".", ".."}:
        raise ValueError("nome de arquivo inválido")
    if not limpo.lower().endswith(".gguf"):
        raise ValueError("o arquivo do modelo precisa terminar em .gguf")
    return limpo


def _obter_http(url: str, parcial: Path) -> int:
    """Baixa em pedaços de 1 MB e devolve o total gravado.

    Pedaço pequeno de propósito: 2 GB numa `response.content` seria 2 GB de RAM
    no PC que já vai carregar o modelo na RAM depois.
    """
    import httpx  # noqa: PLC0415

    total = 0
    with httpx.stream("GET", url, timeout=60.0, follow_redirects=True) as resposta:
        resposta.raise_for_status()
        anunciado = int(resposta.headers.get("content-length") or 0)
        if anunciado and anunciado > limite():
            raise ValueError(
                f"o arquivo tem {_mb(anunciado)}, acima do limite de {_mb(limite())}. "
                f"Se é isso mesmo, defina {AMBIENTE_LIMITE}."
            )
        livre = _livre(parcial.parent)
        if anunciado and livre and anunciado > livre * 0.95:
            raise ValueError(
                f"o arquivo tem {_mb(anunciado)} e o disco tem {_mb(livre)} livres. "
                "Escolha um modelo menor ou libere espaço."
            )
        with parcial.open("wb") as saida:
            for pedaco in resposta.iter_bytes(PEDACO):
                total += len(pedaco)
                if total > limite():
                    saida.close()
                    parcial.unlink(missing_ok=True)
                    raise ValueError(f"download passou do limite de {_mb(limite())}; apagado")
                saida.write(pedaco)
    return total


def baixar(
    url: str,
    nome: str = "",
    pasta_: Path | None = None,
    obter: Callable[[str, Path], int] | None = None,
) -> dict[str, Any]:
    """Baixa um `.gguf` para a pasta do modelo, conferindo antes o que cabe.

    Recusa antes de gastar dados: URL que não é http(s), arquivo que não é
    `.gguf`, e download maior do que o disco livre (com 10% de folga, porque o
    `.parcial` e a pasta de sistema convivem).
    """
    partes = urlsplit(url)
    if partes.scheme not in {"http", "https"} or not partes.hostname:
        raise ValueError("o endereço do modelo precisa começar com http:// ou https://")
    arquivo = _nome_seguro(nome or partes.path.rsplit("/", 1)[-1])
    destino_pasta = pasta(pasta_)
    destino_pasta.mkdir(parents=True, exist_ok=True)
    destino = destino_pasta / arquivo
    if destino.exists():
        return {
            "baixado": False,
            "caminho": str(destino),
            "bytes": destino.stat().st_size,
            "resumo": f"{arquivo} já está na pasta ({_mb(destino.stat().st_size)}). Nada baixado.",
        }

    livre = _livre(destino_pasta)
    if livre and livre < MINIMO_LIVRE:
        # Disco quase cheio: nem começa. A mensagem diz o número para não ser
        # preciso adivinhar depois.
        raise ValueError(f"disco quase cheio: {_mb(livre)} livres em {destino_pasta}")

    parcial = destino.with_suffix(destino.suffix + ".parcial")
    leitor = obter or _obter_http
    try:
        total = leitor(url, parcial)
    except BaseException:
        parcial.unlink(missing_ok=True)
        raise
    if not parcial.exists() or parcial.stat().st_size == 0:
        parcial.unlink(missing_ok=True)
        raise ValueError("o download terminou vazio; o endereço pode estar errado")
    os.replace(parcial, destino)
    tamanho = total or destino.stat().st_size
    return {
        "baixado": True,
        "caminho": str(destino),
        "bytes": tamanho,
        "resumo": (
            f"Baixado {arquivo} ({_mb(tamanho)}) em {destino_pasta}. "
            "Agora rode ia.local com acao=ligar para o JARVIS passar a usar."
        ),
    }


# ---------------------------------------------------------------------------
# Ligar e desligar
# ---------------------------------------------------------------------------

def ligar(
    base: str = BASE_PADRAO,
    modelo: str = "",
    raiz: Path | None = None,
    pasta_: Path | None = None,
    ensaiar: bool = True,
) -> dict[str, Any]:
    """Aponta o JARVIS para o modelo local, escrevendo três linhas no `.env`.

    Se `modelo` vier vazio, usa o maior `.gguf` da pasta. O nome do modelo vai
    como está, com `.gguf`: é assim que o `llama-server` o identifica, e um nome
    inventado só daria `404` na primeira pergunta.
    """
    from .ai import e_local  # noqa: PLC0415

    if not e_local(base):
        raise ValueError(
            f"{base} não é um endereço desta máquina. Modelo local mora em "
            "127.0.0.1, localhost ou [::1] — outro PC da rede exige chave."
        )
    achados = modelos(pasta_)
    escolhido = modelo.strip() or (achados[0]["nome"] if achados else "")
    if not escolhido:
        raise ValueError(
            f"não há .gguf em {pasta(pasta_)}. Rode ia.local com acao=baixar primeiro."
        )
    if not escolhido.lower().endswith(".gguf"):
        escolhido = f"{escolhido}.gguf"

    escrever_env(
        {
            "JARVIS_AI_PROVIDER": PROVEDOR_PADRAO,
            "JARVIS_AI_BASE_URL": base.rstrip("/"),
            "JARVIS_AI_MODEL": escolhido,
        },
        raiz,
    )
    aberta = porta_aberta(base) if ensaiar else False
    if aberta:
        resumo = (
            f"Ligado: {escolhido} em {base}. A API já pode responder sem chave. "
            "Reinicie o JARVIS para ele ler o .env novo."
        )
    else:
        resumo = (
            f"Configuração escrita ({escolhido} em {base}), mas nada está escutando "
            "nesse endereço ainda. Suba o llama-server com modelo-local.ps1 -Ligar "
            "e depois reinicie o JARVIS."
        )
    return {
        "ligado": True,
        "base": base.rstrip("/"),
        "modelo": escolhido,
        "porta_aberta": aberta,
        "reiniciar": "Feche a API no X e rode iniciar-jarvis.bat.",
        "resumo": resumo,
    }


def desligar(raiz: Path | None = None) -> dict[str, Any]:
    """Volta o `.env` ao que era antes de `ligar`.

    Se a cópia não existir (`.env` nunca foi tocado por este módulo), não
    inventa: remove só as três chaves da IA local e diz que não havia cópia.
    """
    caminho = _arquivo_env(raiz)
    copia = caminho.with_name("env.antes-do-modelo-local")
    if copia.exists():
        caminho.write_text(copia.read_text(encoding="utf-8"), encoding="utf-8")
        copia.unlink(missing_ok=True)
        return {
            "desligado": True,
            "restaurado": True,
            "resumo": (
                "O .env voltou ao que era antes do modelo local. "
                "Reinicie o JARVIS para valer."
            ),
        }

    valores = ler_env(raiz)
    if not any(chave in valores for chave in CHAVES_IA):
        return {
            "desligado": False,
            "restaurado": False,
            "resumo": "Nada a desfazer: o .env já não aponta para modelo local.",
        }
    # Sem cópia: apaga só as chaves da IA local, mantendo o resto intacto.
    texto = caminho.read_text(encoding="utf-8", errors="replace")
    linhas = [
        linha for linha in texto.splitlines()
        if linha.strip().partition("=")[0].strip() not in CHAVES_IA
    ]
    caminho.write_text("\n".join(linhas).rstrip("\n") + "\n", encoding="utf-8")
    return {
        "desligado": True,
        "restaurado": False,
        "resumo": (
            "Removi as três chaves da IA local do .env (não havia cópia antiga). "
            "Reinicie o JARVIS para valer."
        ),
    }


# ---------------------------------------------------------------------------
# Linha de comando
# ---------------------------------------------------------------------------

def _cli(argv: list[str] | None = None) -> int:
    import argparse  # noqa: PLC0415

    parser = argparse.ArgumentParser(description="Modelo local do JARVIS (sem chave).")
    parser.add_argument("--estado", action="store_true")
    parser.add_argument("--baixar", metavar="URL", default="")
    parser.add_argument("--nome", default="")
    parser.add_argument("--ligar", action="store_true")
    parser.add_argument("--desligar", action="store_true")
    parser.add_argument("--base", default=BASE_PADRAO)
    parser.add_argument("--modelo", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.baixar:
            dados: dict[str, Any] = baixar(args.baixar, nome=args.nome)
        elif args.ligar:
            dados = ligar(base=args.base, modelo=args.modelo)
        elif args.desligar:
            dados = desligar()
        else:
            dados = estado()
    except Exception as exc:
        print(f"  Falhou: {type(exc).__name__}: {exc}")
        return 1

    if args.json:
        print(json.dumps(dados, ensure_ascii=False, indent=2))
        return 0
    print(f"  {dados.get('resumo', '')}")
    if dados.get("reiniciar"):
        print(f"  {dados['reiniciar']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_cli())
