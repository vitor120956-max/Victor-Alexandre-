"""Elevação controlada: o único caminho pelo qual o JARVIS pede root.

A camada de sistema roda tudo com o usuário do processo. Isso basta para ler a
máquina, baixar arquivo e instalar no `.venv`. Não basta para `dpkg`, `rpm` ou
`systemctl`, que precisam de root.

Este módulo não entrega root ao processo. Ele monta um argv a partir de uma
tabela fechada, chama `sudo -n` (nunca espera senha) e devolve o que o sistema
operacional respondeu. Quem autoriza de verdade é o `/etc/sudoers`: sem uma
linha `NOPASSWD` para esses binários, a chamada falha e nada acontece.

Três travas separam plano de efeito: token de host, `JARVIS_HOST_ROOT=1` e o
token de 8 hex devolvido pelo plano, com validade de 10 minutos e uso único.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import tokens
from .review import common, finalize, finding

VERSAO = "0.60.8"

PROJETO = Path(__file__).resolve().parents[1]
STORAGE = PROJETO / "storage"
TOKEN_ARQUIVO = STORAGE / "host-token.txt"
QUARENTENA = STORAGE / "host-downloads"
AUDITORIA = STORAGE / "host-audit.jsonl"

AMBIENTE_ROOT = "JARVIS_HOST_ROOT"
AMBIENTE_SERVICOS = "JARVIS_HOST_SERVICOS"

CONFIRMACAO_TTL = 600
MAX_TEXTO = 40_000
MAX_ROWS = 200
MODOS = ("lite", "full", "ultra")

# Tabela fechada. Nenhum texto do usuário entra na linha de comando sem passar
# por `_validar`, e nada fora daqui pode ser executado como root.
ACOES: dict[str, dict[str, Any]] = {
    "instalar_deb": {
        "binario": "dpkg",
        "argumentos": ("-i", "--", "{alvo}"),
        "tipo_alvo": "arquivo",
        "extensoes": (".deb",),
        "descricao": "Instala um .deb que já passou pela quarentena.",
        "risco": "alto",
    },
    "remover_deb": {
        "binario": "dpkg",
        "argumentos": ("-r", "--", "{alvo}"),
        "tipo_alvo": "pacote",
        "descricao": "Remove um pacote .deb instalado pelo sistema.",
        "risco": "médio",
    },
    "instalar_rpm": {
        "binario": "rpm",
        "argumentos": ("-Uvh", "--", "{alvo}"),
        "tipo_alvo": "arquivo",
        "extensoes": (".rpm",),
        "descricao": "Instala um .rpm que já passou pela quarentena.",
        "risco": "alto",
    },
    "remover_rpm": {
        "binario": "rpm",
        "argumentos": ("-e", "--", "{alvo}"),
        "tipo_alvo": "pacote",
        "descricao": "Remove um pacote rpm instalado pelo sistema.",
        "risco": "médio",
    },
    "reiniciar_servico": {
        "binario": "systemctl",
        "argumentos": ("restart", "--", "{alvo}"),
        "tipo_alvo": "servico",
        "descricao": "Reinicia um serviço declarado em JARVIS_HOST_SERVICOS.",
        "risco": "alto",
    },
    "parar_servico": {
        "binario": "systemctl",
        "argumentos": ("stop", "--", "{alvo}"),
        "tipo_alvo": "servico",
        "descricao": "Para um serviço declarado em JARVIS_HOST_SERVICOS.",
        "risco": "alto",
    },
}

PACOTE = re.compile(r"^[a-z0-9][a-z0-9+.-]{0,63}$")
SERVICO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9@._:-]{0,63}$")

_TOKEN_CONFIRMACAO: dict[str, dict[str, Any]] = {}


class ElevacaoError(ValueError):
    """Entrada inválida ou operação recusada por trava."""


# ---------------------------------------------------------------------------
# Guardas
# ---------------------------------------------------------------------------


def _token_host() -> str:
    try:
        if TOKEN_ARQUIVO.exists():
            return TOKEN_ARQUIVO.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return ""


def _autorizado(autorizacao: str) -> tuple[bool, str]:
    esperado = _token_host()
    if not esperado:
        return False, "Token de host ausente: suba a API uma vez para gerar storage/host-token.txt."
    if not (autorizacao or "").strip():
        return False, tokens.explicar(autorizacao)
    if not tokens.iguais(autorizacao, esperado):
        return False, tokens.explicar(autorizacao)
    return True, ""


def _exigir(autorizacao: str) -> None:
    ok, motivo = _autorizado(autorizacao)
    if not ok:
        raise ElevacaoError(motivo)


def _exigir_root(autorizacao: str) -> None:
    _exigir(autorizacao)
    if os.environ.get(AMBIENTE_ROOT, "0") != "1":
        raise ElevacaoError(
            f"Elevação desligada. Suba a API com {AMBIENTE_ROOT}=1 para executar como root. "
            "Sem a variável, esta camada só planeja."
        )


def _servicos() -> list[str]:
    bruto = os.environ.get(AMBIENTE_SERVICOS, "")
    itens = [item.strip() for item in bruto.split(",") if item.strip()]
    return [item for item in itens if SERVICO.match(item)]


def _modo(modo: str) -> str:
    valor = (modo or "full").strip().lower()
    if valor not in MODOS:
        raise ElevacaoError("Modo inválido: use lite, full ou ultra.")
    return valor


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def _rodar(comando: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """Executa apenas argv montado no código, sem shell."""
    try:
        concluido = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            check=False,
        )
        return concluido.returncode, concluido.stdout[:MAX_TEXTO], concluido.stderr[:8000]
    except FileNotFoundError:
        return 127, "", f"comando não encontrado: {comando[0]}"
    except PermissionError:
        return 126, "", "sem permissão para executar"
    except subprocess.TimeoutExpired:
        return 124, "", f"tempo esgotado em {timeout}s"
    except OSError as exc:
        return 1, "", f"falha ao executar: {type(exc).__name__}"


def _sha(caminho: Path) -> str:
    digest = hashlib.sha256()
    try:
        with open(caminho, "rb") as handle:
            for bloco in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(bloco)
    except OSError:
        return ""
    return digest.hexdigest()


def _auditar(evento: dict[str, Any]) -> None:
    try:
        AUDITORIA.parent.mkdir(parents=True, exist_ok=True)
        linha = {"ts": datetime.now(timezone.utc).isoformat(), **evento}
        with open(AUDITORIA, "a", encoding="utf-8") as saida:
            saida.write(json.dumps(linha, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _relativo(caminho: Path) -> str:
    try:
        return caminho.relative_to(PROJETO).as_posix()
    except ValueError:
        return str(caminho)


def _quarentena(caminho: str) -> Path:
    alvo = Path(caminho).expanduser()
    try:
        resolvido = alvo.resolve()
    except OSError as exc:
        raise ElevacaoError("Caminho de arquivo inválido.") from exc
    try:
        base = QUARENTENA.resolve()
    except OSError:
        base = QUARENTENA
    if base not in resolvido.parents:
        raise ElevacaoError(
            "Só elevo arquivo que passou pela quarentena de `sistema.baixar` em storage/host-downloads."
        )
    if not resolvido.is_file():
        raise ElevacaoError(f"Arquivo não encontrado na quarentena: `{_relativo(resolvido)}`.")
    return resolvido


def _sudo() -> str:
    return shutil.which("sudo") or ""


def _sudo_sem_senha() -> tuple[bool, str]:
    """Consulta o que o sudo permite sem pedir senha. Nunca espera prompt."""
    caminho = _sudo()
    if not caminho:
        return False, "sudo ausente"
    codigo, saida, erro = _rodar([caminho, "-n", "-l"], timeout=10)
    texto = (saida + "\n" + erro).strip()
    if codigo == 0:
        return True, texto[:4000]
    if "password is required" in texto or "senha" in texto.lower():
        return False, "sudo pede senha: sem NOPASSWD a elevação falharia"
    return False, texto[-500:] or f"sudo -n -l saiu com código {codigo}"


def _validar(acao: str, alvo: str) -> tuple[dict[str, Any], str]:
    entrada = ACOES.get(acao)
    if entrada is None:
        raise ElevacaoError(
            f"Ação desconhecida: `{acao}`. Use {', '.join(sorted(ACOES))}."
        )
    valor = (alvo or "").strip()
    tipo = entrada["tipo_alvo"]
    if tipo == "arquivo":
        if not valor:
            raise ElevacaoError("Informe o arquivo da quarentena em `alvo`.")
        caminho = _quarentena(valor)
        extensoes = entrada.get("extensoes", ())
        if extensoes and caminho.suffix.lower() not in extensoes:
            raise ElevacaoError(
                f"`{acao}` aceita só {', '.join(extensoes)}; recebi `{caminho.suffix or '(sem extensão)'}`."
            )
        return entrada, str(caminho)
    if tipo == "pacote":
        if not PACOTE.match(valor):
            raise ElevacaoError(
                "Nome de pacote inválido: use letras minúsculas, dígitos, `+`, `.` e `-` (até 64 caracteres)."
            )
        return entrada, valor
    if tipo == "servico":
        if not SERVICO.match(valor):
            raise ElevacaoError("Nome de serviço inválido: use o nome da unidade, como `meuapp.service`.")
        permitidos = _servicos()
        if not permitidos:
            raise ElevacaoError(
                f"Nenhum serviço autorizado. Defina {AMBIENTE_SERVICOS}=meuapp.service (lista separada por vírgula) "
                "e suba a API de novo."
            )
        if valor not in permitidos:
            raise ElevacaoError(
                f"Serviço `{valor}` não está na lista autorizada desta máquina ({', '.join(permitidos)})."
            )
        return entrada, valor
    raise ElevacaoError("Tipo de alvo desconhecido na tabela.")


def _argv(entrada: dict[str, Any], alvo: str) -> list[str]:
    binario = shutil.which(entrada["binario"])
    if not binario:
        raise ElevacaoError(
            f"`{entrada['binario']}` não está instalado nesta máquina; esta ação não pode rodar."
        )
    sudo = _sudo()
    if not sudo:
        raise ElevacaoError("`sudo` não existe nesta máquina. Elevação exige sudo.")
    return [sudo, "-n", binario, *(parte.format(alvo=alvo) for parte in entrada["argumentos"])]


def sudoers_sugerido() -> list[str]:
    """Linha de sudoers que restringe a elevação aos binários da tabela."""
    usuario = os.environ.get("USER") or os.environ.get("LOGNAME") or "seu-usuario"
    binarios: list[str] = []
    for entrada in ACOES.values():
        caminho = shutil.which(entrada["binario"])
        if caminho and caminho not in binarios:
            binarios.append(caminho)
    if not binarios:
        return ["# nenhum binário da tabela foi encontrado nesta máquina"]
    return [
        f"# /etc/sudoers.d/jarvis-elevacao  (root:root, modo 0440)",
        f"{usuario} ALL=(root) NOPASSWD: {', '.join(binarios)}",
    ]


# ---------------------------------------------------------------------------
# 1. Privilégio atual
# ---------------------------------------------------------------------------


def privilegio(*, modo: str = "full", autorizacao: str = "") -> dict[str, Any]:
    """Descreve com que privilégio a API roda e o que o sudo permite hoje."""
    modo = _modo(modo)
    _exigir(autorizacao)

    uid = os.getuid() if hasattr(os, "getuid") else -1
    euid = os.geteuid() if hasattr(os, "geteuid") else -1
    usuario = os.environ.get("USER") or os.environ.get("LOGNAME") or "desconhecido"
    root = euid == 0
    sudo = _sudo()
    sem_senha, detalhe = _sudo_sem_senha()
    servicos = _servicos()
    ligado = os.environ.get(AMBIENTE_ROOT, "0") == "1"

    rows = [
        {"chave": "usuário do processo", "valor": usuario},
        {"chave": "uid / euid", "valor": f"{uid} / {euid}"},
        {"chave": "roda como root", "valor": "sim" if root else "não"},
        {"chave": "sudo instalado", "valor": sudo or "ausente"},
        {"chave": "sudo sem senha", "valor": "sim" if sem_senha else "não"},
        {"chave": "trava de elevação", "valor": f"{AMBIENTE_ROOT}={'1' if ligado else '0'}"},
        {"chave": "serviços autorizados", "valor": ", ".join(servicos) if servicos else "(nenhum)"},
        {"chave": "token de host", "valor": _relativo(TOKEN_ARQUIVO) if _token_host() else "ausente"},
        {"chave": "quarentena", "valor": _relativo(QUARENTENA)},
    ]
    for acao, entrada in sorted(ACOES.items()):
        rows.append(
            {
                "chave": f"ação {acao}",
                "valor": f"{entrada['binario']} {' '.join(entrada['argumentos'])}",
            }
        )

    findings: list[dict[str, Any]] = []
    if root:
        findings.append(
            finding(
                "must",
                "privilegio",
                "A API roda como root",
                f"pid do processo, uid {euid}",
                "O processo inteiro tem privilégio de root, não só os comandos da tabela.",
                "Qualquer falha em qualquer skill passa a ser uma falha com root: leitura, escrita de arquivo e código promovido pela camada de evolução.",
                "Suba a API com o seu usuário normal e use `sistema.elevar` para os comandos que realmente precisam de root.",
                "O raio de dano de um bug deixa de ser a pasta do projeto.",
            )
        )
    if not sudo:
        findings.append(
            finding(
                "should",
                "privilegio",
                "Sem sudo nesta máquina",
                "PATH",
                "`shutil.which('sudo')` não encontrou o binário.",
                "Sem sudo, nenhuma ação da tabela pode rodar: a camada de elevação fica só no plano.",
                "Instale sudo ou use o gerenciador de pacotes da sua plataforma com o usuário certo.",
                "Você continua sem instalar pacote do sistema pelo JARVIS.",
            )
        )
    elif not sem_senha:
        findings.append(
            finding(
                "should",
                "privilegio",
                "sudo pede senha",
                "/etc/sudoers",
                "`sudo -n -l` não completou sem senha.",
                "A execução usa `sudo -n`: se o sudo pedir senha, o comando falha na hora em vez de ficar esperando.",
                "Crie /etc/sudoers.d/jarvis-elevacao com a linha sugerida, restrita aos binários da tabela.",
                "A elevação planeja e nunca executa.",
            )
        )
    if not ligado:
        findings.append(
            finding(
                "nice",
                "trava",
                "Trava de elevação desligada",
                AMBIENTE_ROOT,
                f"{AMBIENTE_ROOT} não está em 1.",
                "O padrão é planejar sem executar — a camada não vira root por acidente.",
                f"Suba a API com {AMBIENTE_ROOT}=1 quando quiser executar o plano confirmado.",
                "Nada acontece: o plano é gerado e o token não é aceito na execução.",
            )
        )
    if not _token_host():
        findings.append(
            finding(
                "must",
                "token",
                "Token de host ausente",
                _relativo(TOKEN_ARQUIVO),
                "O arquivo do token não existe ou está vazio.",
                "Sem token, o modo host está fechado.",
                "Suba a API uma vez para gerar o arquivo e reinicie o que já estava rodando.",
                "Nenhuma skill de host responde.",
            )
        )

    findings, counts, veredito, questions = finalize(
        findings, modo, ["Você vai rodar a API como root de propósito?", "Quem mais usa esta máquina?"]
    )
    resultado = common(
        analysis="privilegio",
        mode=modo,
        title="Privilégio da API",
        summary=[
            f"O processo roda como **{usuario}** (uid {uid}, euid {euid}).",
            "**Root**" if root else "**Usuário comum**" + (" — elevação só pela tabela fechada." if sudo else " — e sem sudo."),
            f"sudo sem senha: {'sim' if sem_senha else 'não'}; trava {AMBIENTE_ROOT}={'1' if ligado else '0'}.",
        ],
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=questions,
        rows=rows[:MAX_ROWS],
        metrics={
            "uid": uid,
            "euid": euid,
            "root": root,
            "sudo": bool(sudo),
            "semSenha": sem_senha,
            "ligado": ligado,
            "acoes": len(ACOES),
            "servicos": len(servicos),
        },
        limitations=[
            "A leitura de privilégio é do processo da API, não do seu terminal.",
            "`sudo -n -l` pode estar bloqueado por política mesmo com NOPASSWD ativo.",
            "Numa sandbox ou contêiner, `root` aqui é root do contêiner.",
        ],
        extra_sections=["", "## sudoers sugerido", "", "```sudoers", *sudoers_sugerido(), "```"],
    )
    resultado["sudoers"] = sudoers_sugerido()
    return resultado


# ---------------------------------------------------------------------------
# 2. Plano de elevação
# ---------------------------------------------------------------------------


def elevar(*, acao: str, alvo: str = "", modo: str = "full", autorizacao: str = "") -> dict[str, Any]:
    """Monta o comando que rodaria como root e devolve o token de confirmação."""
    modo = _modo(modo)
    _exigir(autorizacao)
    entrada, valor = _validar(acao, alvo)
    argv = _argv(entrada, valor)
    comando = " ".join(argv)
    sha = _sha(Path(valor)) if entrada["tipo_alvo"] == "arquivo" else ""
    sem_senha, detalhe_sudo = _sudo_sem_senha()

    token = secrets.token_hex(4)
    expira = time.time() + CONFIRMACAO_TTL
    _TOKEN_CONFIRMACAO[token] = {
        "acao": acao,
        "alvo": valor,
        "argv": argv,
        "sha256": sha,
        "tipo_alvo": entrada["tipo_alvo"],
        "expira": expira,
    }

    rows = [
        {"campo": "ação", "valor": acao},
        {"campo": "alvo", "valor": valor},
        {"campo": "binário", "valor": shutil.which(entrada["binario"]) or entrada["binario"]},
        {"campo": "comando", "valor": comando},
        {"campo": "risco", "valor": entrada["risco"]},
        {"campo": "sha256", "valor": sha or "(não se aplica)"},
        {"campo": "sudo sem senha", "valor": "sim" if sem_senha else "não"},
        {"campo": "confirmação", "valor": token},
        {"campo": "válida até", "valor": datetime.fromtimestamp(expira, tz=timezone.utc).strftime("%H:%M:%S UTC")},
    ]

    findings: list[dict[str, Any]] = [
        finding(
            "should",
            "risco",
            "Este comando roda como root",
            comando,
            "A linha começa com `sudo -n` e o binário está na tabela fechada.",
            "Root não pede confirmação ao sistema operacional: um alvo errado é dano imediato e amplo.",
            "Leia o alvo e o SHA-256 acima antes de confirmar; para remoção, confira se o pacote é o que você pensa.",
            "Você instala ou remove algo com privilégio total.",
        )
    ]
    if not sem_senha:
        findings.append(
            finding(
                "must",
                "sudo",
                "sudo sem senha não confirmado",
                "/etc/sudoers",
                detalhe_sudo[:200],
                "A execução usa `sudo -n` e vai falhar se o sudo pedir senha.",
                "Crie /etc/sudoers.d/jarvis-elevacao com a linha sugerida e rode de novo.",
                "O plano existe, mas a execução devolve erro de permissão.",
            )
        )
    if entrada["tipo_alvo"] == "arquivo" and not sha:
        findings.append(
            finding(
                "must",
                "arquivo",
                "Arquivo ilegível",
                valor,
                "Não foi possível calcular o SHA-256 do arquivo.",
                "Sem hash não há como provar que o arquivo é o mesmo entre o plano e a execução.",
                "Baixe de novo pela quarentena e repita o plano.",
                "A execução recusa por hash ausente.",
            )
        )
    if acao.startswith("remover"):
        findings.append(
            finding(
                "nice",
                "remocao",
                "Remoção sem backup",
                valor,
                "`dpkg -r` e `rpm -e` apagam arquivos do sistema.",
                "Não existe desfazer: reinstalar a mesma versão pode não recuperar configuração local.",
                "Anote a versão instalada antes de remover, para poder voltar.",
                "Você depende do repositório para reinstalar.",
            )
        )

    findings, counts, veredito, questions = finalize(
        findings, modo, ["Você confere o alvo acima?", "Esta remoção tem como voltar?"]
    )
    resultado = common(
        analysis="elevar",
        mode=modo,
        title="Plano de elevação",
        summary=[
            f"Ação **{acao}** sobre `{valor}`.",
            f"Comando: `{comando}`",
            "Nada foi executado: o plano só monta o argv e devolve o token.",
        ],
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=questions,
        rows=rows,
        metrics={
            "acao": acao,
            "risco": entrada["risco"],
            "sudoSemSenha": sem_senha,
            "sha256": sha,
            "confirmação": token,
        },
        limitations=[
            "O plano não prova que o alvo é o que você quer: ele só prova que o caminho é permitido.",
            "Quem autoriza root é o /etc/sudoers, não este módulo.",
            "`NOPASSWD` em dpkg ou rpm equivale a root: o pacote instala o que quiser.",
        ],
    )
    resultado["confirmacao"] = token
    resultado["comando"] = comando
    resultado["sudoers"] = sudoers_sugerido()
    return resultado


# ---------------------------------------------------------------------------
# 3. Execução
# ---------------------------------------------------------------------------


def elevar_executar(
    *, confirmacao: str, modo: str = "full", autorizacao: str = ""
) -> dict[str, Any]:
    """Executa o plano confirmado com `sudo -n`. Exige a trava e o token de uso único."""
    modo = _modo(modo)
    _exigir_root(autorizacao)
    token = (confirmacao or "").strip()
    if not token or token not in _TOKEN_CONFIRMACAO:
        raise ElevacaoError("Confirmação ausente ou desconhecida. Gere o plano em `sistema.elevar` de novo.")
    registro = _TOKEN_CONFIRMACAO.pop(token)
    if registro["expira"] < time.time():
        raise ElevacaoError("Confirmação expirada. Gere o plano de novo.")

    acao = registro["acao"]
    alvo = registro["alvo"]
    entrada, valor = _validar(acao, alvo)
    if valor != alvo:
        raise ElevacaoError("O alvo mudou desde o plano. Gere o plano de novo.")
    if registro["tipo_alvo"] == "arquivo" and registro["sha256"]:
        atual = _sha(Path(alvo))
        if atual != registro["sha256"]:
            raise ElevacaoError(
                "O arquivo mudou depois do plano. Gere o plano de novo para ver o comando atualizado."
            )
    argv = _argv(entrada, alvo)
    if argv != registro["argv"]:
        raise ElevacaoError("O comando montado não é o mesmo do plano. Nada foi executado.")

    inicio = time.time()
    codigo, saida, erro = _rodar(argv, timeout=600)
    duracao = round(time.time() - inicio, 2)
    _auditar(
        {
            "acao": f"elevar:{acao}",
            "alvo": alvo,
            "comando": " ".join(argv),
            "codigo": codigo,
        }
    )

    rows = [
        {"campo": "ação", "valor": acao},
        {"campo": "alvo", "valor": alvo},
        {"campo": "comando", "valor": " ".join(argv)},
        {"campo": "código de saída", "valor": str(codigo)},
        {"campo": "duração", "valor": f"{duracao}s"},
        {"campo": "saída", "valor": (saida or "(vazia)")[-3000:]},
        {"campo": "erro", "valor": (erro or "(vazio)")[-2000:]},
    ]

    findings: list[dict[str, Any]] = []
    if codigo != 0:
        dica = ""
        if "password is required" in (erro or "").lower() or "a terminal is required" in (erro or "").lower():
            dica = " O sudo pediu senha: crie /etc/sudoers.d/jarvis-elevacao com a linha restrita aos binários da tabela."
        findings.append(
            finding(
                "must",
                "execucao",
                "O comando terminou com erro",
                alvo,
                f"Código de saída {codigo}: {(erro or saida)[-300:] or 'sem mensagem'}.",
                "A operação não foi concluída, ou parou no meio.",
                f"Leia a saída acima e corrija antes de repetir.{dica}",
                "O sistema fica no estado anterior ou parcialmente alterado.",
            )
        )
    else:
        findings.append(
            finding(
                "nice",
                "execucao",
                "Comando concluído",
                alvo,
                f"`{acao}` terminou com código 0 em {duracao}s.",
                "Sucesso do comando não é prova de que o resultado é o desejado.",
                "Confira o efeito com uma leitura (`sistema.privilegio` ou o gerenciador de pacotes).",
                "Você acredita no relatório, não no estado.",
            )
        )

    findings, counts, veredito, questions = finalize(
        findings, modo, ["O efeito é o que você esperava?", "Algum serviço depende deste pacote?"]
    )
    resultado = common(
        analysis="elevar_executar",
        mode=modo,
        title="Elevação executada",
        summary=[
            f"`{acao}` sobre `{alvo}` com código **{codigo}** em {duracao}s.",
            "O comando rodou com root via `sudo -n`, sem shell e sem texto livre na linha de comando.",
        ],
        findings=findings,
        counts=counts,
        verdict=veredito,
        questions=questions,
        rows=rows,
        metrics={
            "acao": acao,
            "codigo": codigo,
            "duracao": duracao,
            "executado": True,
        },
        limitations=[
            "O código de saída é do binário; ele não garante que o serviço ficou saudável.",
            "A auditoria grava o comando, não a intenção.",
            "Sem `JARVIS_HOST_ROOT=1` esta skill nem chega ao sudo.",
        ],
        extra_sections=["", "## Saída", "", "```text", ((saida or "") + (("\n" + erro) if erro else ""))[-6000:] or "(vazia)", "```"],
    )
    resultado["executed"] = True
    resultado["readOnly"] = False
    resultado["execucao"] = {
        "comando": " ".join(argv),
        "codigo": codigo,
        "saida": saida[-4000:],
        "erro": erro[-4000:],
    }
    return resultado
