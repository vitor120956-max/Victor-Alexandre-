"""Atualização delta: baixar só o que mudou, e saber que há versão nova.

Duas ideias viraram uma camada só:

1. *“em vez de baixar tudo, baixar e alterar só o que foi mexido”*;
2. *“o JARVIS reconhecer sempre que houver atualização e puxar as melhorias”*.

## Por que o zip inteiro era desperdício

A instalação por zip (sem `.git`) baixa ~3,5 MB e passa o `robocopy` por ~460
arquivos a cada versão. Numa versão pequena — um `.py`, duas páginas, um doc —
isso é 99% de bytes e de tempo desperdiçados, e num pendrive é pior, porque cada
arquivo reescrito custa a mais do que o tamanho dele.

Com `.git` isso já era delta de verdade (`fetch` só transfere objeto novo). O que
não existia era o mesmo para quem instalou pelo zip.

## O desenho

`manifest.json`, na raiz do projeto, lista cada arquivo gerenciado com `sha256` e
tamanho. No seu computador o JARVIS:

1. calcula o hash dos arquivos locais;
2. baixa **só o `manifest.json`** (~50 KB) do GitHub;
3. compara e monta a lista do que mudou;
4. baixa **só esses arquivos** (cada um de ~2–60 KB);
5. guarda em `storage/atualizacao/<versão>/` — ainda **sem** tocar no que roda;
6. aplica quando você manda, com backup do que foi substituído em
   `storage/atualizacao/backup-<data>/`.

Numa versão típica isso é ~1% do zip. E o `atualizar.bat` continua existindo como
plano B: se qualquer passo falhar (rede, `raw.githubusercontent.com` bloqueado,
arquivo estranho), ele cai no zip de sempre.

## O que este módulo **não** faz

- não apaga arquivo seu: o que deixou de existir no projeto aparece como
  “sobras”, e apagar continua sendo decisão sua;
- não mexe em `.env`, `storage/`, `.venv/` ou `node_modules/` — por definição,
  eles nem entram no manifesto;
- não aplica sozinho: baixar é silencioso, aplicar exige confirmação (skill) ou o
  `.bat` com `--sim`, e o código novo só vale depois de reiniciar a API. Aplicar
  com o processo velho rodando é o jeito mais fácil de ficar com metade de cada
  versão na memória;
- não confia no GitHub cegamente: cada arquivo baixado é conferido contra o
  `sha256` do manifesto antes de entrar no palco. Arquivo que não confere é
  recusado, não “aplicado assim mesmo”.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from . import dados as dados_locais

VERSAO = "0.79.0"
NOME_MANIFESTO = "manifest.json"

# Onde o manifesto e os arquivos moram. Trocável por `JARVIS_ATUALIZACAO_URL`
# (útil para testar contra um servidor local e para quem fizer fork).
BASE_PADRAO = (
    "https://raw.githubusercontent.com/vitor120956-max/Victor-Alexandre-"
    "/arena/f26cfa7a-victor-alexandre"
)

AMBIENTE = "JARVIS_ATUALIZACAO"
# Modo automático: quem aplica a atualização sozinho, **antes** de a API
# subir. Desligável no `.env` com `JARVIS_AUTO_ATUALIZAR=0`.
AMBIENTE_AUTO = "JARVIS_AUTO_ATUALIZAR"

# O que **nunca** entra no manifesto nem na comparação: dado do usuário,
# ambiente, build local e o próprio manifesto (que não pode se hashear).
PASTAS_IGNORADAS = {
    ".git", ".venv", "storage", "node_modules", "__pycache__", "dist",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", "coverage", ".next", "out",
    "build", ".idea", ".vscode",
}
ARQUIVOS_IGNORADOS = {
    NOME_MANIFESTO, ".env", ".env.local", ".DS_Store", "Thumbs.db",
}
# Cache de build do TypeScript: muda a cada `tsc -b` e não é código. Se entrasse,
# a cópia do usuário apareceria sempre “divergente” por causa de um arquivo que
# ninguém edita à mão.
SUFIXOS_IGNORADOS = (".pyc", ".pyo", ".log", ".tmp", ".swp", ".tsbuildinfo")

MAX_ARQUIVO = 12 * 1024 * 1024  # o maior arquivo do projeto é bem menor
MAX_ARQUIVOS = 5_000
TIMEOUT = 30


def ligado() -> bool:
    """A checagem automática de versão está ligada?

    Ligada por padrão **pelo `iniciar-jarvis.bat`** (mesmo padrão dos braços),
    desligável no `.env` com `JARVIS_ATUALIZACAO=0`. Só a checagem: o download e
    a aplicação sempre pedem a sua decisão.
    """
    return os.environ.get(AMBIENTE, "0").strip() == "1"


def auto_ligado(projeto: Path | None = None) -> bool:
    """O JARVIS pode se atualizar sozinho ao subir?

    Ligado por padrão **pelo `iniciar-jarvis.bat`**, que exporta
    `JARVIS_AUTO_ATUALIZAR=1`. Desligado com `JARVIS_AUTO_ATUALIZAR=0` no `.env`.

    O **`.env` manda mais que a variável de ambiente**, e a ordem é de propósito:
    o `.bat` exporta `1` antes de o Python existir, então se a variável ganhasse,
    escrever `=0` no `.env` não desligaria nada — e o dono ficaria com um
    automático que não consegue parar. Lido por arquivo porque o `.env` só entra
    em `os.environ` depois, dentro do `create_app`.

    O momento importa: isto roda antes de a API existir, então aplicar arquivo
    aqui é seguro — não há processo com a versão antiga na memória. É por isso
    que o automático mora no start e não no meio do expediente.
    """
    raiz = Path(projeto) if projeto is not None else Path(__file__).resolve().parents[1]
    env = raiz / ".env"
    if env.is_file():
        try:
            texto = env.read_bytes().decode("utf-8", errors="replace")
        except OSError:  # pragma: no cover - disco sem permissão
            texto = ""
        for linha in texto.splitlines():
            limpa = linha.strip()
            if limpa.startswith("#") or "=" not in limpa:
                continue
            nome, _, valor = limpa.partition("=")
            if nome.strip() == AMBIENTE_AUTO:
                return valor.strip().strip('"').strip("'").lower() not in {"0", "nao", "não", "false", "off"}
    return os.environ.get(AMBIENTE_AUTO, "0").strip() == "1"


def _base() -> str:
    return (os.environ.get("JARVIS_ATUALIZACAO_URL", "") or BASE_PADRAO).rstrip("/")


# ---------------------------------------------------------------------------
# Manifesto
# ---------------------------------------------------------------------------


def hash_arquivo(caminho: Path) -> str:
    digest = hashlib.sha256()
    with caminho.open("rb") as origem:
        for bloco in iter(lambda: origem.read(1 << 16), b""):
            digest.update(bloco)
    return digest.hexdigest()


def gerenciado(relativo: Path) -> bool:
    """Este caminho entra no manifesto auto-atualizável?"""
    partes = relativo.parts
    if not partes or relativo.is_absolute() or ".." in partes:
        return False
    if any(parte in PASTAS_IGNORADAS for parte in partes):
        return False
    if relativo.name in ARQUIVOS_IGNORADOS:
        return False
    if relativo.suffix.lower() in SUFIXOS_IGNORADOS:
        return False
    if relativo.name.startswith(".env"):
        return False
    return True


def arquivos_gerenciaveis(raiz: Path | None = None) -> list[Path]:
    """Arquivos do projeto que o atualizador controla, em ordem estável."""
    base = Path(raiz) if raiz is not None else Path(__file__).resolve().parents[1]
    encontrados: list[Path] = []
    for caminho in sorted(base.rglob("*")):
        if not caminho.is_file():
            continue
        relativo = caminho.relative_to(base)
        if not gerenciado(relativo):
            continue
        try:
            if caminho.stat().st_size > MAX_ARQUIVO:
                continue
        except OSError:
            continue
        encontrados.append(relativo)
    return encontrados


def gerar_manifesto(*, raiz: Path | None = None, versao: str = "", agora: datetime | None = None) -> dict[str, Any]:
    """Monta o manifesto a partir do que está no disco (o que o release publica)."""
    base = Path(raiz) if raiz is not None else Path(__file__).resolve().parents[1]
    arquivos: dict[str, dict[str, Any]] = {}
    for relativo in arquivos_gerenciaveis(base):
        puro = relativo.as_posix()
        try:
            arquivos[puro] = {
                "sha256": hash_arquivo(base / relativo),
                "bytes": (base / relativo).stat().st_size,
            }
        except OSError:
            continue
    return {
        "versao": versao or _versao_do_pacote(base),
        "gerado": (agora or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        "arquivos": arquivos,
    }


def _versao_do_pacote(base: Path) -> str:
    try:
        return str(json.loads((base / "package.json").read_text(encoding="utf-8")).get("version") or "")
    except (OSError, json.JSONDecodeError):
        return ""


def hashes_locais(raiz: Path | None = None) -> dict[str, str]:
    """`caminho -> sha256` do que está no disco agora (só o gerenciável)."""
    base = Path(raiz) if raiz is not None else Path(__file__).resolve().parents[1]
    saida: dict[str, str] = {}
    for relativo in arquivos_gerenciaveis(base):
        try:
            saida[relativo.as_posix()] = hash_arquivo(base / relativo)
        except OSError:
            continue
    return saida


def comparar(remoto: dict[str, Any], local: dict[str, str]) -> dict[str, Any]:
    """O que baixar, o que já está igual e o que sobrou de versões antigas."""
    arquivos = remoto.get("arquivos") or {}
    if not isinstance(arquivos, dict) or not arquivos:
        raise ValueError("O manifesto remoto está vazio ou em formato desconhecido.")
    baixar: list[dict[str, Any]] = []
    iguais = 0
    bytes_total = 0
    for caminho, dados in sorted(arquivos.items()):
        esperado = str((dados or {}).get("sha256") or "")
        tamanho = int((dados or {}).get("bytes") or 0)
        if not esperado:
            continue
        if local.get(caminho) == esperado:
            iguais += 1
            continue
        baixar.append({"caminho": caminho, "sha256": esperado, "bytes": tamanho,
                       "novo": caminho not in local})
        bytes_total += tamanho
    extras = sorted(caminho for caminho in local if caminho not in arquivos)
    return {
        "baixar": baixar,
        "iguais": iguais,
        "extras": extras,
        "bytes": bytes_total,
        "total_remoto": len(arquivos),
    }


# ---------------------------------------------------------------------------
# Rede — uma função só, trocável em teste
# ---------------------------------------------------------------------------


def _baixar_url(url: str) -> bytes:
    """GET simples com teto de tamanho. Sem token, sem redirecionamento aberto."""
    import httpx  # noqa: PLC0415

    with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as cliente:
        resposta = cliente.get(url, headers={"User-Agent": "JARVIS-atualizacao"})
        resposta.raise_for_status()
        if len(resposta.content) > MAX_ARQUIVO:
            raise ValueError(f"arquivo grande demais para atualização ({len(resposta.content)} bytes)")
        return resposta.content


def _buscar_manifesto(baixar: Callable[[str], bytes] | None = None) -> dict[str, Any]:
    obter = baixar or _baixar_url
    bruto = obter(f"{_base()}/{NOME_MANIFESTO}")
    try:
        return json.loads(bruto.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("O manifesto remoto não é JSON válido.") from exc


# ---------------------------------------------------------------------------
# Palco: baixar para um canto, sem tocar no que roda
# ---------------------------------------------------------------------------


def _projeto(projeto: Path | None = None) -> Path:
    return Path(projeto) if projeto is not None else Path(__file__).resolve().parents[1]


def _pasta_palco(versao: str, raiz: Path | None = None) -> Path:
    base = Path(raiz) if raiz is not None else Path(dados_locais.raiz())
    seguro = re.sub(r"[^0-9A-Za-z._-]+", "-", versao or "sem-versao")[:40]
    return base / "atualizacao" / seguro


def _estado_arquivo(raiz: Path | None = None) -> Path:
    base = Path(raiz) if raiz is not None else Path(dados_locais.raiz())
    return base / "atualizacao" / "estado.json"


def estado(raiz: Path | None = None) -> dict[str, Any]:
    """O que a última checagem e o último palco deixaram registrado."""
    arquivo = _estado_arquivo(raiz)
    try:
        salvo = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        salvo = {}
    pronto: list[str] = []
    base = Path(raiz) if raiz is not None else Path(dados_locais.raiz())
    pasta_raiz = base / "atualizacao"
    if pasta_raiz.is_dir():
        pronto = sorted(
            caminho.name for caminho in pasta_raiz.iterdir()
            if caminho.is_dir() and (caminho / "pronto.json").is_file()
        )
    projeto = Path(__file__).resolve().parents[1]
    return {
        "ligado": ligado(),
        # Duas coisas diferentes: "avisar" (ligado) e "aplicar sozinho" (automático).
        "automatico": auto_ligado(projeto) and not (projeto / ".git").exists(),
        "motivo_auto": (
            "pasta com Git: use o atualizar.bat"
            if (projeto / ".git").exists() and auto_ligado(projeto)
            else ""
        ),
        "base": _base(),
        "local": _versao_local(),
        "ultima_checagem": salvo.get("ultima_checagem", ""),
        "disponivel": salvo.get("disponivel", False),
        "remota": salvo.get("remota", ""),
        "a_baixar": salvo.get("a_baixar", 0),
        "bytes": salvo.get("bytes", 0),
        "palcos_prontos": pronto,
        "como_aplicar": "skill `atualizacao.aplicar` (ou atualizar.bat) e depois reiniciar a API",
    }


def _versao_local(projeto: Path | None = None) -> str:
    return _versao_do_pacote(_projeto(projeto)) or VERSAO


def _gravar_estado(dados: dict[str, Any], raiz: Path | None = None) -> None:
    arquivo = _estado_arquivo(raiz)
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def verificar(
    *,
    raiz: Path | None = None,
    projeto: Path | None = None,
    baixar: Callable[[str], bytes] | None = None,
    forcar: bool = False,
) -> dict[str, Any]:
    """Há versão nova? Baixa **só o manifesto** e compara com os hashes locais.

    `forcar=True` checa mesmo com `JARVIS_ATUALIZACAO=0` — é o que a skill faz
    quando você pede de propósito (“tem versão nova?”).
    """
    if not forcar and not ligado():
        return {
            "ligado": False,
            "checou": False,
            "motivo": (
                "A checagem automática está desligada. Peça de novo com `forcar` "
                "(skill) ou ligue `JARVIS_ATUALIZACAO=1` no `.env`."
            ),
        }
    inicio = time.perf_counter()
    try:
        remoto = _buscar_manifesto(baixar)
        local_hashes = hashes_locais(projeto)
        diferenca = comparar(remoto, local_hashes)
    except Exception as exc:  # rede, json, manifesto vazio
        return {
            "ligado": True,
            "checou": False,
            "motivo": f"Não consegui falar com o GitHub: {type(exc).__name__}: {exc}",
            "plano_b": "O `atualizar.bat` baixa o zip inteiro e funciona sem esta camada.",
        }

    versao_remota = str(remoto.get("versao") or "")
    versao_local = _versao_local(projeto)
    mudou = bool(diferenca["baixar"])
    resultado = {
        "ligado": True,
        "checou": True,
        "local": versao_local,
        "remota": versao_remota,
        "disponivel": mudou,
        "a_baixar": len(diferenca["baixar"]),
        "iguais": diferenca["iguais"],
        "total_remoto": diferenca["total_remoto"],
        "bytes": diferenca["bytes"],
        "extras": diferenca["extras"][:50],
        "ms": round((time.perf_counter() - inicio) * 1000, 1),
        "resumo": _resumo(versao_local, versao_remota, len(diferenca["baixar"]), diferenca["bytes"]) if mudou else f"Já está na última: {versao_local}.",
    }
    salvo = dict(estado(raiz))
    salvo.update({
        "ultima_checagem": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "disponivel": mudou,
        "remota": versao_remota,
        "a_baixar": len(diferenca["baixar"]),
        "bytes": diferenca["bytes"],
    })
    _gravar_estado(salvo, raiz)
    return resultado


def _resumo(versao_local: str, versao_remota: str, quantos: int, bytes_: int) -> str:
    """A frase do aviso — e ela não pode mentir sobre a versão.

    Se o número da versão é o mesmo mas o conteúdo diverge (arquivo editado à
    mão, cópia antiga com um arquivo novo), dizer “versão nova: 0.75.0 (a sua é
    0.75.0)” confunde. Aí a frase é sobre arquivos, não sobre versão.
    """
    if versao_remota and versao_remota != versao_local:
        return (
            f"Versão nova: {versao_remota} (a sua é {versao_local}). "
            f"{quantos} arquivo(s), {_mb(bytes_)} — em vez do zip inteiro."
        )
    if not versao_remota:
        return f"{quantos} arquivo(s) diferente(s) do publicado: {_mb(bytes_)}."
    return (
        f"Mesma versão ({versao_local}), {quantos} arquivo(s) diferente(s) do "
        f"publicado: {_mb(bytes_)}."
    )


def _mb(bytes_: int) -> str:
    if bytes_ >= 1024 * 1024:
        return f"{bytes_ / (1024 * 1024):.1f} MB"
    return f"{max(1, round(bytes_ / 1024))} KB"


def preparar(
    *,
    raiz: Path | None = None,
    projeto: Path | None = None,
    baixar: Callable[[str], bytes] | None = None,
) -> dict[str, Any]:
    """Baixa **só os arquivos que mudaram** para o palco. Nada é aplicado ainda."""
    checagem = verificar(raiz=raiz, projeto=projeto, baixar=baixar, forcar=True)
    if not checagem.get("checou"):
        return checagem
    if not checagem.get("disponivel"):
        return {**checagem, "preparado": False, "motivo": "Nada mudou: não há o que baixar."}

    remoto = _buscar_manifesto(baixar)
    local_hashes = hashes_locais(projeto)
    diferenca = comparar(remoto, local_hashes)
    pasta = _pasta_palco(str(remoto.get("versao") or ""), raiz)
    if pasta.is_dir():
        shutil.rmtree(pasta, ignore_errors=True)
    (pasta / "files").mkdir(parents=True, exist_ok=True)

    obter = baixar or _baixar_url
    baixados: list[dict[str, Any]] = []
    falhas: list[dict[str, str]] = []
    for item in diferenca["baixar"]:
        caminho = item["caminho"]
        url = f"{_base()}/{caminho}"
        try:
            conteudo = obter(url)
        except Exception as exc:
            falhas.append({"caminho": caminho, "motivo": f"{type(exc).__name__}: {exc}"})
            continue
        if hashlib.sha256(conteudo).hexdigest() != item["sha256"]:
            # Não “aplica assim mesmo”: arquivo que não confere é recusado.
            falhas.append({"caminho": caminho, "motivo": "sha256 não confere com o manifesto"})
            continue
        destino = pasta / "files" / caminho
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(conteudo)
        baixados.append({"caminho": caminho, "bytes": len(conteudo), "novo": item["novo"]})

    pronto = not falhas
    registro = {
        "versao": str(remoto.get("versao") or ""),
        "quando": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "baixados": baixados,
        "falhas": falhas,
        "extras": diferenca["extras"],
        "pronto": pronto,
    }
    (pasta / "pronto.json").write_text(json.dumps(registro, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        **checagem,
        "preparado": pronto,
        "palco": str(pasta),
        "baixados": len(baixados),
        "bytes_baixados": sum(item["bytes"] for item in baixados),
        "falhas": falhas,
        "resumo": (
            f"Baixei {len(baixados)} arquivo(s), {_mb(sum(i['bytes'] for i in baixados))}, "
            f"para o palco. Nada foi aplicado ainda."
            if pronto
            else f"Baixei {len(baixados)} e falharam {len(falhas)}: o palco não é confiável. Use o atualizar.bat."
        ),
    }


def aplicar(
    *,
    versao: str = "",
    raiz: Path | None = None,
    confirmado: bool = False,
    projeto: Path | None = None,
    agora: datetime | None = None,
) -> dict[str, Any]:
    """Copia o palco para o projeto, com backup do que for substituído.

    Só roda com `confirmado=True` e só a partir de um palco marcado como pronto —
    isto é, com todos os arquivos baixados e conferidos. Depois de aplicar, a API
    precisa reiniciar: é o processo velho carregado na memória.
    """
    if not confirmado:
        raise ValueError("Falta confirmação explícita para aplicar a atualização.")
    base_dados = Path(raiz) if raiz is not None else Path(dados_locais.raiz())
    raiz_projeto = Path(projeto) if projeto is not None else Path(__file__).resolve().parents[1]
    pasta_raiz = base_dados / "atualizacao"
    if versao:
        pasta = _pasta_palco(versao, raiz)
    else:
        candidatos = sorted(
            (c for c in pasta_raiz.iterdir() if c.is_dir() and (c / "pronto.json").is_file()),
            key=lambda c: (c / "pronto.json").stat().st_mtime,
        ) if pasta_raiz.is_dir() else []
        if not candidatos:
            raise ValueError("Não há atualização baixada e conferida para aplicar.")
        pasta = candidatos[-1]

    registro = json.loads((pasta / "pronto.json").read_text(encoding="utf-8"))
    if not registro.get("pronto"):
        raise ValueError("O palco tem falhas: aplicar agora deixaria a instalação pela metade.")

    carimbo = (agora or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    backup = pasta_raiz / f"backup-{carimbo}"
    aplicados: list[str] = []
    novos: list[str] = []
    recusados: list[str] = []
    for item in registro.get("baixados") or []:
        relativo = str(item.get("caminho") or "")
        alvo_relativo = Path(relativo)
        # O pronto.json veio da rede: caminho com "..", raiz absoluta ou fora do
        # que o manifesto gerencia não se aplica nem com confirmação.
        if (
            not relativo
            or alvo_relativo.is_absolute()
            or ".." in alvo_relativo.parts
            or not gerenciado(alvo_relativo)
        ):
            recusados.append(relativo or "(vazio)")
            continue
        origem = pasta / "files" / relativo
        if not origem.is_file():
            recusados.append(relativo)
            continue
        destino = raiz_projeto / relativo
        if destino.exists():
            alvo = backup / relativo
            alvo.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destino, alvo)
            aplicados.append(relativo)
        else:
            novos.append(relativo)
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origem, destino)

    resultado = {
        "aplicado": True,
        "versao": registro.get("versao", ""),
        "substituidos": aplicados,
        "adicionados": novos,
        "backup": str(backup) if aplicados else "",
        "recusados": recusados,
        "abaixo_de_storage": str(pasta),
        "reiniciar": (
            "Feche a janela da API no X e rode iniciar-jarvis.bat. O código novo está "
            "no disco; o processo em memória continua o antigo até reiniciar."
        ),
        "como_voltar": (
            f"Copie de volta o conteúdo de `{backup}` por cima do projeto."
            if aplicados else "Nada foi substituído: só arquivos novos."
        ),
    }
    salvo = dict(estado(raiz))
    salvo.update({"aplicada": registro.get("versao", ""), "aplicada_em": carimbo, "disponivel": False})
    _gravar_estado(salvo, raiz)
    return resultado


# ---------------------------------------------------------------------------
# Modo automático: atualizar sozinho ao subir (0.78.0)
# ---------------------------------------------------------------------------

# Arquivos que, se mudarem, exigem `pip install` antes de a API subir.
_ARQUIVOS_DE_DEPENDENCIA = ("requirements.txt", "requirements-dev.txt", "requirements-rapido.txt")


def auto_atualizar(
    *,
    raiz: Path | None = None,
    projeto: Path | None = None,
    baixar: Callable[[str], bytes] | None = None,
) -> dict[str, Any]:
    """Verifica, baixa só o que mudou e aplica — **antes** de a API subir.

    O pedido: *“ué, o JARVIS ainda não se auto atualiza?”*. Não se atualizava
    porque aplicar com o processo velho na memória é o jeito mais fácil de ficar
    com metade de cada versão rodando. A solução não é aplicar no meio do
    expediente: é aplicar **no start**, quando ainda não há processo nenhum.

    ## As três travas

    1. **Nunca derruba o start.** Rede fora, GitHub bloqueado, arquivo com hash
       estranho: o JARVIS sobe na versão atual e diz o motivo no terminal.
    2. **Nunca aplica palco com falha.** Se um único arquivo não conferiu, nada é
       copiado.
    3. **Nunca em pasta com `.git`.** Ali quem manda é `git`, e aplicar arquivo
       por cima deixaria a árvore suja — o `evoluir.promover` exige árvore
       limpa, então o automático se recusa em vez de atrapalhar.

    Devolve sempre um dicionário com `resumo` e `motivo`, para o terminal ter o
    que mostrar mesmo quando não havia nada a fazer.
    """
    raiz_projeto = Path(projeto) if projeto is not None else Path(__file__).resolve().parents[1]
    if not auto_ligado(raiz_projeto):
        return {
            "automatico": False,
            "pulou": True,
            "motivo": f"desligado ({AMBIENTE_AUTO}=0 no .env).",
            "resumo": "Atualização automática desligada.",
        }

    if (raiz_projeto / ".git").exists():
        return {
            "automatico": True,
            "pulou": True,
            "motivo": "esta pasta é um repositório Git: use atualizar.bat (git fetch + pull).",
            "resumo": "Pasta com Git: atualização automática não se aplica aqui.",
        }

    checagem = verificar(raiz=raiz, projeto=raiz_projeto, baixar=baixar, forcar=True)
    if not checagem.get("checou"):
        return {
            "automatico": True,
            "pulou": True,
            "motivo": checagem.get("motivo") or "não consegui checar",
            "resumo": "Não deu para checar versão nova — seguindo com a atual.",
        }
    if not checagem.get("disponivel"):
        return {
            "automatico": True,
            "pulou": True,
            "ja_ultima": True,
            "versao": checagem.get("local"),
            "motivo": "já está na última versão",
            "resumo": f"Já é a última versão ({checagem.get('local')}).",
        }

    estagio = preparar(raiz=raiz, projeto=raiz_projeto, baixar=baixar)
    if not estagio.get("preparado"):
        return {
            "automatico": True,
            "pulou": True,
            "falhou": True,
            "motivo": estagio.get("motivo") or "o download não fechou",
            "falhas": estagio.get("falhas") or [],
            "resumo": "A atualização não veio inteira — seguindo com a versão atual.",
        }

    aplicada = aplicar(versao=str(estagio.get("remota") or ""), raiz=raiz, projeto=raiz_projeto, confirmado=True)
    mexidos = list(aplicada.get("substituidos") or []) + list(aplicada.get("adicionados") or [])
    dependencias = any(caminho in _ARQUIVOS_DE_DEPENDENCIA for caminho in mexidos)
    return {
        "automatico": True,
        "pulou": False,
        "atualizou": True,
        "de": checagem.get("local"),
        "para": aplicada.get("versao"),
        "arquivos": mexidos,
        "backup": aplicada.get("backup"),
        "como_voltar": aplicada.get("como_voltar"),
        "instalar_dependencias": dependencias,
        "resumo": (
            f"Atualizado de {checagem.get('local')} para {aplicada.get('versao')} "
            f"({len(mexidos)} arquivo(s))."
            + (" Dependências mudaram: rodando pip install." if dependencias else "")
        ),
    }


# ---------------------------------------------------------------------------
# CLI — o `atualizar.bat` usa este caminho antes de partir para o zip
# ---------------------------------------------------------------------------


def _cli(argv: list[str] | None = None) -> int:
    import argparse  # noqa: PLC0415
    import sys  # noqa: PLC0415

    parser = argparse.ArgumentParser(description="Atualização delta do JARVIS (só o que mudou).")
    parser.add_argument("--verificar", action="store_true")
    parser.add_argument("--preparar", action="store_true")
    parser.add_argument("--aplicar", action="store_true")
    parser.add_argument("--sim", action="store_true", help="Não perguntar (usar só em script).")
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Atualizar sozinho, sem perguntar (usado pelo iniciar-jarvis.bat antes de subir).",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.auto:
            dados_auto: dict[str, Any] = auto_atualizar()
            if args.json:
                print(json.dumps(dados_auto, ensure_ascii=False, indent=2))
            else:
                print(f"  {dados_auto.get('resumo', '')}")
                if dados_auto.get("motivo") and not dados_auto.get("atualizou"):
                    print(f"  ({dados_auto['motivo']})")
                for caminho in (dados_auto.get("arquivos") or [])[:8]:
                    print(f"    - {caminho}")
                if dados_auto.get("backup"):
                    print(f"  backup: {dados_auto['backup']}")
            # 4 = atualizou e as dependências mudaram: o .bat roda pip antes de subir.
            if dados_auto.get("atualizou"):
                return 4 if dados_auto.get("instalar_dependencias") else 0
            return 0
        if args.verificar:
            dados: dict[str, Any] = verificar(forcar=True)
        elif args.preparar:
            dados = preparar()
        elif args.aplicar:
            if not args.sim:
                resposta = input("  Aplicar a atualização baixada? [s/N] ").strip().lower()
                if resposta not in {"s", "sim", "y", "yes"}:
                    print("  Cancelado. Nada foi alterado.")
                    return 0
            dados = aplicar(confirmado=True)
        else:
            dados = estado()
    except Exception as exc:
        print(f"  Falhou: {type(exc).__name__}: {exc}")
        return 1

    if args.json:
        print(json.dumps(dados, ensure_ascii=False, indent=2))
        return 0
    resumo = dados.get("resumo") or dados.get("motivo") or dados.get("reiniciar") or ""
    if resumo:
        print(f"  {resumo}")
    if dados.get("aplicado"):
        print("  Reinicie: feche a API no X e rode iniciar-jarvis.bat.")
    # Códigos que o `atualizar.bat` lê: 0 seguiu, 1 falhou (cai no zip),
    # 2 palco com falha (cai no zip), 3 já está na última (não faz nada).
    if dados.get("falhas"):
        return 2
    if dados.get("checou") is False:
        return 1
    if dados.get("preparado") is False and not dados.get("aplicado"):
        return 3 if not dados.get("disponivel", True) else 2
    if dados.get("checou") and not dados.get("disponivel") and not dados.get("aplicado"):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
