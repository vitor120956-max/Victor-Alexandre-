"""Configurar o Google Drive como espaço de fora — feito pelo próprio JARVIS.

O módulo não tem opinião: ele **copia** `biblioteca/` e `repos/` para
`<Drive>/JARVIS-DADOS/` e grava `JARVIS_BIBLIOTECA` e `JARVIS_REPOS` no `.env`.
O estado do agente (`historico.json`, `fila.json`, `skills.json`, `host-*`)
**não** vai: é regravado a cada resposta e, dentro de uma pasta sincronizada,
cada gravação viraria uma sincronização.

Três garantias:

- **nada é apagado** — a pasta antiga continua onde está;
- **nada é gravado no `.env` antes de a cópia conferir** arquivo por arquivo
  (contagem e bytes);
- **`desfazer` só mexe no `.env`** — os arquivos do Drive ficam lá, para o
  usuário decidir quando apagar.

`planejar()` não toca em disco: devolve o passo a passo com os tamanhos reais.
`aplicar()` é o único que escreve, e só roda com confirmação da interface.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from . import dados

PASTA_NO_DRIVE = "JARVIS-DADOS"
AREAS = ("biblioteca", "repos")
ROTULOS = {
    "biblioteca": "livros, vídeos e pesquisas",
    "repos": "repositórios baixados",
}
VARIAVEIS = {
    "biblioteca": dados.VARIAVEL_BIBLIOTECA,
    "repos": dados.VARIAVEL_REPOS,
}

ENV = dados.PROJETO / ".env"
ENV_EXEMPLO = dados.PROJETO / ".env.example"

# Trava de segurança: acima disso, a cópia pelo chat prenderia a interface por
# minutos num PC fraco. O caminho para biblioteca grande é `mover-dados.py --drive`.
MAX_ARQUIVOS = 10_000
MAX_BYTES = 1_500_000_000


class DriveError(ValueError):
    """Recusa explicada: o que faltou para configurar o Drive."""


# ------------------------------------------------------------------ medição

def _medir(pasta: Path) -> tuple[int, int]:
    arquivos = 0
    total = 0
    if not pasta.exists():
        return 0, 0
    for item in pasta.rglob("*"):
        try:
            if not item.is_file():
                continue
            total += item.stat().st_size
            arquivos += 1
        except OSError:
            continue
    return arquivos, total


def _mb(valor: int) -> str:
    return f"{valor / 1e6:.1f} MB"


def _gb(valor: int) -> str:
    return f"{valor / 1e9:.1f} GB"


# --------------------------------------------------------------------- .env

def _ler_env() -> str:
    base = ENV if ENV.is_file() else ENV_EXEMPLO
    return base.read_text(encoding="utf-8") if base.is_file() else ""


def ler_valor(texto: str, nome: str) -> str | None:
    import re

    achado = re.search(rf"(?m)^\s*{re.escape(nome)}\s*=(.*)$", texto)
    return achado.group(1).strip() if achado else None


def _definir(texto: str, nome: str, valor: str) -> str:
    import re

    linha = f"{nome}={valor}"
    padrao = rf"(?m)^\s*{re.escape(nome)}\s*=.*$"
    if re.search(padrao, texto):
        return re.sub(padrao, lambda _: linha, texto, count=1)
    separador = "" if texto.endswith(("\n", "\r\n")) or not texto else "\n"
    return f"{texto}{separador}{linha}\n"


def _apagar_linha(texto: str, nome: str) -> str:
    import re

    return re.sub(rf"(?m)^\s*{re.escape(nome)}\s*=.*\n?", "", texto)


def gravar_env(texto: str) -> Path:
    """Grava o `.env` em CRLF, que é o que o Windows espera."""
    ENV.write_bytes(texto.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))
    return ENV


# ------------------------------------------------------------------ estado

def destino(drive: Path) -> Path:
    return Path(drive) / PASTA_NO_DRIVE


def _vazio(pasta: Path) -> bool:
    try:
        return not any(pasta.iterdir())
    except OSError:
        return True


def _mesmo(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return False


def estado(drive: Path | None = None) -> dict[str, Any]:
    """Retrato sem efeito: o que está onde, o que o `.env` diz, quanto cabe."""
    detectado = Path(drive) if drive is not None else dados.detectar_drive()
    texto_env = _ler_env()
    areas: list[dict[str, Any]] = []
    for nome in AREAS:
        origem = dados.caminho(nome)
        alvo = destino(detectado) / nome if detectado is not None else None
        arquivos, total = _medir(origem)
        copiados, bytes_copiados = _medir(alvo) if alvo is not None else (0, 0)
        areas.append(
            {
                "nome": nome,
                "rotulo": ROTULOS[nome],
                "variavel": VARIAVEIS[nome],
                "origem": str(origem),
                "destino": str(alvo) if alvo is not None else "",
                "arquivos": arquivos,
                "mb": round(total / 1e6, 1),
                "ja_no_drive": copiados,
                "mb_no_drive": round(bytes_copiados / 1e6, 1),
                "configurada": str(origem).lower() == str(alvo).lower() if alvo is not None else False,
            }
        )
    valor_env = {nome: ler_valor(texto_env, VARIAVEIS[nome]) or "" for nome in AREAS}
    livre = 0
    if detectado is not None:
        try:
            livre = shutil.disk_usage(detectado).free
        except OSError:
            livre = 0
    return {
        "drive": str(detectado) if detectado is not None else "",
        "detectado": detectado is not None,
        "destino": str(destino(detectado)) if detectado is not None else "",
        "espaco_livre_gb": round(livre / 1e9, 1),
        "env": {
            "arquivo": str(ENV),
            "existe": ENV.is_file(),
            "biblioteca": valor_env["biblioteca"],
            "repos": valor_env["repos"],
        },
        "areas": areas,
        "configurado": all(item["configurada"] for item in areas) if detectado is not None else False,
        "total_mb": round(sum(item["mb"] for item in areas), 1),
        "total_arquivos": sum(item["arquivos"] for item in areas),
    }


# ------------------------------------------------------------------ planejar

def planejar(drive: Path | None = None, modo: str = "usar") -> dict[str, Any]:
    """O que `aplicar` faria — sem criar, copiar ou gravar nada."""
    retrato = estado(drive)
    if modo == "desfazer":
        return {
            "modo": "desfazer",
            "env": retrato["env"],
            "vai_acontecer": [
                f"apagar as linhas {dados.VARIAVEL_BIBLIOTECA} e {dados.VARIAVEL_REPOS} de {retrato['env']['arquivo']}",
                "nada é apagado do Drive: os arquivos continuam lá",
                "o JARVIS volta a usar as pastas locais na próxima subida",
            ],
            "precisa_reiniciar": True,
            "confirma": True,
        }

    if not retrato["detectado"]:
        raise DriveError(
            "Não achei a pasta do Google Drive. Abra o app do Drive, confirme que ele "
            "está com sessão iniciada, ou informe o caminho no campo `drive` "
            "(ex.: `C:/Users/Você/Google Drive/Meu Drive`)."
        )

    passos = [
        f"1. criar {retrato['destino']} dentro do Drive;",
    ]
    for item in retrato["areas"]:
        if item["configurada"]:
            passos.append(f"2. {item['nome']}: já está no Drive — nada a copiar;")
        elif item["arquivos"] == 0:
            passos.append(f"2. {item['nome']}: vazia — só apontar a variável;")
        else:
            passos.append(
                f"2. {item['nome']}: copiar {item['arquivos']} arquivos "
                f"({item['mb']} MB) de {item['origem']} para {item['destino']};"
            )
    passos.extend(
        [
            f"3. conferir arquivo por arquivo (contagem e bytes);",
            f"4. gravar {dados.VARIAVEL_BIBLIOTECA} e {dados.VARIAVEL_REPOS} em {retrato['env']['arquivo']};",
            "5. nada é apagado: a pasta antiga continua onde está.",
        ]
    )
    return {
        "modo": "usar",
        "drive": retrato["drive"],
        "destino": retrato["destino"],
        "passos": passos,
        "areas": retrato["areas"],
        "total_mb": retrato["total_mb"],
        "total_arquivos": retrato["total_arquivos"],
        "espaco_livre_gb": retrato["espaco_livre_gb"],
        "precisa_reiniciar": True,
        "confirma": True,
    }


# ------------------------------------------------------------------- aplicar

def _copiar(origem: Path, alvo: Path) -> tuple[int, int]:
    alvo.mkdir(parents=True, exist_ok=True)
    arquivos = 0
    total = 0
    for item in origem.rglob("*"):
        if not item.is_file():
            continue
        relativo = item.relative_to(origem)
        destino_item = alvo / relativo
        destino_item.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, destino_item)
        arquivos += 1
        try:
            total += item.stat().st_size
        except OSError:
            pass
    return arquivos, total


def _ao_vivo(areas: list[dict[str, Any]]) -> None:
    """Aplica nesta sessão também: sem isso só valeria depois de reiniciar."""
    for item in areas:
        os.environ[item["variavel"]] = item["destino"]
    dados.apontar()


def aplicar(
    drive: Path | None = None,
    *,
    modo: str = "usar",
    ao_vivo: bool = True,
) -> dict[str, Any]:
    """Copia e grava o `.env`. Devolve o que fez, sem inventar sucesso."""
    if modo not in ("usar", "desfazer"):
        raise DriveError("Modo inválido: use `usar` ou `desfazer`.")

    if modo == "desfazer":
        texto = _ler_env()
        antes = texto
        for nome in AREAS:
            texto = _apagar_linha(texto, VARIAVEIS[nome])
        mudou = texto != antes
        if mudou:
            gravar_env(texto)
        return {
            "modo": "desfazer",
            "env": str(ENV),
            "alterou_env": mudou,
            "precisa_reiniciar": True,
            "mensagem": (
                "Tirei as linhas do `.env`. Nada do Drive foi apagado."
                if mudou
                else "O `.env` já não apontava para o Drive."
            ),
            "aviso": "Feche e abra o JARVIS para voltar às pastas locais.",
        }

    retrato = estado(drive)
    if not retrato["detectado"]:
        raise DriveError(
            "Não achei a pasta do Google Drive. Informe o caminho no campo `drive`."
        )
    raiz_drive = Path(retrato["drive"])
    if not raiz_drive.is_dir():
        raise DriveError(f"A pasta {raiz_drive} não existe.")

    if retrato["total_arquivos"] > MAX_ARQUIVOS:
        raise DriveError(
            f"São {retrato['total_arquivos']} arquivos — demais para copiar pelo chat. "
            "Rode `mover-dados.py --drive` na janela do JARVIS, que mostra o progresso."
        )
    if retrato["total_mb"] * 1e6 > MAX_BYTES:
        raise DriveError("Mais de 1,5 GB para copiar: use `mover-dados.py --drive`.")

    areas: list[dict[str, Any]] = []
    for item in retrato["areas"]:
        origem = Path(item["origem"])
        alvo = Path(item["destino"])
        ja_esta = item["configurada"] or _mesmo(origem, alvo)
        if ja_esta:
            areas.append({**item, "situacao": "já estava no Drive", "copiados": 0, "mb_copiados": 0.0})
            continue
        if not origem.exists() or _vazio(origem):
            alvo.mkdir(parents=True, exist_ok=True)
            areas.append({**item, "situacao": "vazia: só apontada", "copiados": 0, "mb_copiados": 0.0})
            continue
        try:
            livre = shutil.disk_usage(raiz_drive).free
        except OSError:
            livre = 0
        if livre and livre < item["mb"] * 1e6 * 1.1:
            raise DriveError(
                f"Sem espaço no Drive para {item['nome']}: precisa de {item['mb']} MB, "
                f"há {_gb(livre)} livres."
            )
        copiados, bytes_copiados = _copiar(origem, alvo)
        arquivos_alvo, bytes_alvo = _medir(alvo)
        origem_arquivos, origem_bytes = _medir(origem)
        if arquivos_alvo < origem_arquivos or bytes_alvo < origem_bytes:
            raise DriveError(
                f"A cópia de {item['nome']} ficou incompleta ({arquivos_alvo} de "
                f"{origem_arquivos} arquivos). Nada foi gravado no `.env`."
            )
        areas.append(
            {
                **item,
                "situacao": "copiada",
                "copiados": copiados,
                "mb_copiados": round(bytes_copiados / 1e6, 1),
                "conferido": f"{arquivos_alvo} arquivos / {_mb(bytes_alvo)}",
            }
        )

    texto = _ler_env()
    for item in areas:
        texto = _definir(texto, item["variavel"], item["destino"])
    gravar_env(texto)
    if ao_vivo:
        try:
            _ao_vivo(areas)
        except Exception:  # aplicar ao vivo é conforto, não requisito
            pass

    return {
        "modo": "usar",
        "drive": str(raiz_drive),
        "destino": retrato["destino"],
        "env": str(ENV),
        "areas": areas,
        "copiados": sum(item["copiados"] for item in areas),
        "mb_copiados": round(sum(item["mb_copiados"] for item in areas), 1),
        "precisa_reiniciar": True,
        "mensagem": "Biblioteca e repositórios agora ficam no Drive; o estado do agente continua no PC.",
        "aviso": (
            "Reinicie o JARVIS para o `.env` valer em tudo. No Drive, deixe a pasta "
            "`JARVIS-DADOS` disponível off-line e limite a banda para o PC não travar."
        ),
    }
