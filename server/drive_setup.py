r"""Configurar o Google Drive como espaço de fora — feito pelo próprio JARVIS.

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

**Limite de banda é exceção e é real**: o app do Drive lê
`BandwidthRxKBPS`/`BandwidthTxKBPS` de `HKCU\Software\Google\DriveFS` (é o que
a própria Google documenta). `aplicar_banda()` grava esses dois valores DWORD e
`banda()` lê de volta — sem admin, sem reiniciar o PC. As outras duas coisas do
app (disponibilizar pasta off-line e pausar a sincronização) não têm chave nem
linha de comando pública no Windows; o JARVIS avisa e explica, não finge.
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


# Chave que o app do Drive lê ao iniciar (Google Workspace Help, "Advanced
# Drive for desktop configuration"). Nível de usuário: não precisa de admin.
CHAVE_DRIVE = r"Software\Google\DriveFS"
BANDA_PADRAO = (1000, 500)  # KB/s: 1 MB/s de download, 0,5 MB/s de upload
BANDA_MAXIMA = 100_000_000  # teto que a própria Google aceita


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


def estado(
    drive: Path | None = None,
    *,
    processos: list[str] | None = None,
    simulado_registro: Any = None,
) -> dict[str, Any]:
    r"""Retrato sem efeito: o que está onde, o que o `.env` diz, quanto cabe.

    Também responde a pergunta que importa depois de configurar: **o Drive ainda
    está no ar?** Se a biblioteca mora em `G:\Meu Drive` e o app do Drive não
    subiu com o Windows, a pasta some e o JARVIS fica sem os livros.
    """
    detectado = Path(drive) if drive is not None else dados.detectar_drive()
    texto_env = _ler_env()
    areas: list[dict[str, Any]] = []
    for nome in AREAS:
        origem = dados.caminho(nome)
        alvo = destino(detectado) / nome if detectado is not None else None
        arquivos, total = _medir(origem)
        copiados, bytes_copiados = _medir(alvo) if alvo is not None else (0, 0)
        local_padrao = dados.raiz() / nome
        sobrou_arquivos, sobrou_bytes = (
            _medir(local_padrao) if not _mesmo(local_padrao, origem) else (0, 0)
        )
        areas.append(
            {
                "nome": nome,
                "rotulo": ROTULOS[nome],
                "variavel": VARIAVEIS[nome],
                "origem": str(origem),
                "destino": str(alvo) if alvo is not None else "",
                "existe": origem.is_dir(),
                "arquivos": arquivos,
                "mb": round(total / 1e6, 1),
                "ja_no_drive": copiados,
                "mb_no_drive": round(bytes_copiados / 1e6, 1),
                "no_drive": dados.no_drive(origem),
                "sobrou_no_pc": sobrou_arquivos,
                "sobrou_no_pc_mb": round(sobrou_bytes / 1e6, 1),
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
        "drive_aberto": drive_aberto(processos),
        "banda": banda(simulado_registro),
        "avisos": _avisos(areas),
    }


def _avisos(areas: list[dict[str, Any]]) -> list[str]:
    """Problemas que o usuário precisa ver — em linguagem de quem usa, não de log."""
    avisos: list[str] = []
    no_drive = [item for item in areas if item["no_drive"]]
    for item in no_drive:
        if not item["existe"]:
            avisos.append(
                f"A pasta do Drive de {item['nome']} não está lá agora: abra o app do "
                "Google Drive (ou confira se a unidade ainda é G:). Enquanto isso, o "
                "JARVIS não acha os livros."
            )
        if item["sobrou_no_pc"]:
            tamanho = _mb(int(item["sobrou_no_pc_mb"] * 1e6))
            avisos.append(
                f"Sobraram {item['sobrou_no_pc']} arquivo(s) ({tamanho}) na pasta "
                f"antiga de {item['nome']}; eles não aparecem na biblioteca."
            )
        if item["existe"] and item["arquivos"] == 0:
            avisos.append(
                f"A pasta de {item['nome']} está no Drive, mas ainda vazia: importe um "
                "livro para ver a sincronização acontecer."
            )
    return avisos


# ------------------------------------------------------- limite de banda (Windows)

class _RegistroWindows:
    """Adaptador fino do `winreg` — só usuário atual, nunca HKLM."""

    def __init__(self) -> None:
        import winreg  # noqa: PLC0415 - só existe no Windows

        self._winreg = winreg

    def ler(self, nome: str) -> int | None:
        try:
            with self._winreg.OpenKey(self._winreg.HKEY_CURRENT_USER, CHAVE_DRIVE) as chave:
                valor, _tipo = self._winreg.QueryValueEx(chave, nome)
                return int(valor)
        except (OSError, ValueError):
            return None

    def gravar(self, nome: str, valor: int) -> None:
        with self._winreg.CreateKey(self._winreg.HKEY_CURRENT_USER, CHAVE_DRIVE) as chave:
            self._winreg.SetValueEx(chave, nome, 0, self._winreg.REG_DWORD, int(valor))

    def apagar(self, nome: str) -> None:
        try:
            with self._winreg.OpenKey(
                self._winreg.HKEY_CURRENT_USER, CHAVE_DRIVE, 0, self._winreg.KEY_SET_VALUE
            ) as chave:
                self._winreg.DeleteValue(chave, nome)
        except OSError:
            pass


def _registro(simulado: Any = None) -> Any:
    if simulado is not None:
        return simulado
    if os.name != "nt":
        raise DriveError(
            "O limite de banda é ajuste de registro do Windows; esta máquina não tem "
            "esse registro para mexer."
        )
    return _RegistroWindows()


def banda(simulado: Any = None) -> dict[str, Any]:
    """Limite atual do app do Drive, em KB/s. `0` significa sem limite."""
    try:
        reg = _registro(simulado)
    except DriveError as exc:
        return {"suportado": False, "motivo": str(exc), "download_kbps": 0, "upload_kbps": 0}
    download = reg.ler("BandwidthRxKBPS")
    upload = reg.ler("BandwidthTxKBPS")
    return {
        "suportado": True,
        "download_kbps": int(download or 0),
        "upload_kbps": int(upload or 0),
        "limitado": bool(download or upload),
        "padrao": {"download_kbps": BANDA_PADRAO[0], "upload_kbps": BANDA_PADRAO[1]},
    }


def aplicar_banda(
    download_kbps: int = BANDA_PADRAO[0],
    upload_kbps: int = BANDA_PADRAO[1],
    *,
    simulado: Any = None,
) -> dict[str, Any]:
    """Grava o limite em `HKCU\\Software\\Google\\DriveFS`. `0` remove o limite."""
    antes = banda(simulado)
    for rotulo, valor in (("download", download_kbps), ("upload", upload_kbps)):
        if not isinstance(valor, int) or isinstance(valor, bool):
            raise DriveError(f"O limite de {rotulo} precisa ser número inteiro de KB/s.")
        if valor < 0 or valor > BANDA_MAXIMA:
            raise DriveError(
                f"O limite de {rotulo} precisa ficar entre 0 e {BANDA_MAXIMA} KB/s "
                "(0 = sem limite)."
            )
    reg = _registro(simulado)
    for nome, valor in (("BandwidthRxKBPS", download_kbps), ("BandwidthTxKBPS", upload_kbps)):
        if valor:
            reg.gravar(nome, valor)
        else:
            reg.apagar(nome)
    depois = banda(simulado)
    return {
        "banda": True,
        "antes": {"download_kbps": antes["download_kbps"], "upload_kbps": antes["upload_kbps"]},
        "depois": {"download_kbps": depois["download_kbps"], "upload_kbps": depois["upload_kbps"]},
        "chave": f"HKEY_CURRENT_USER\\{CHAVE_DRIVE}",
        "mensagem": (
            "Limite gravado. Ele vale quando o app do Google Drive reiniciar — "
            "feche o Drive pelo ícone da bandeja e abra de novo (ou reinicie o PC)."
            if (download_kbps or upload_kbps)
            else "Limite removido: o Drive volta a usar a banda inteira quando reiniciar."
        ),
    }


def planejar_banda(
    download_kbps: int = BANDA_PADRAO[0],
    upload_kbps: int = BANDA_PADRAO[1],
    *,
    simulado: Any = None,
) -> dict[str, Any]:
    """O que `aplicar_banda` faria, sem gravar nada."""
    atual = banda(simulado)
    return {
        "banda": True,
        "planejado": True,
        "antes": {"download_kbps": atual["download_kbps"], "upload_kbps": atual["upload_kbps"]},
        "depois": {"download_kbps": download_kbps, "upload_kbps": upload_kbps},
        "chave": f"HKEY_CURRENT_USER\\{CHAVE_DRIVE}",
        "suportado": atual["suportado"],
    }


def _processos_windows() -> list[str]:
    """Nomes dos processos em execução (minúsculos). Fora do Windows, vazio."""
    if os.name != "nt":
        return []
    import subprocess  # noqa: PLC0415

    try:
        saida = subprocess.run(
            ["tasklist", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    nomes: list[str] = []
    for linha in saida.splitlines():
        pedaco = linha.split('","')
        if pedaco:
            nomes.append(pedaco[0].strip('"').strip().lower())
    return nomes


def drive_aberto(processos: list[str] | None = None) -> bool | None:
    """O app do Drive está rodando? `None` quando não dá para saber."""
    lista = _processos_windows() if processos is None else processos
    if not lista and os.name != "nt":
        return None
    return any("googledrive" in nome for nome in lista)


# ------------------------------------------------- abrir e fechar o app do Drive
#
# No Windows o app **não** aceita `--pause_syncing` (esse parâmetro é do macOS).
# O que dá para fazer sem clicar em janela é fechar o processo e abrir de novo.
# O efeito colateral é grande e precisa aparecer na tela antes: fechado o app, a
# unidade `G:` some e a biblioteca fica inalcançável até reabrir. Por isso
# `fechar()` exige `confirmar=True` e devolve o aviso junto.

PROCESSO_DRIVE = "GoogleDriveFS.exe"
_PASTAS_DRIVE = (
    Path(r"C:\Program Files\Google\Drive File Stream"),
    Path(r"C:\Program Files (x86)\Google\Drive File Stream"),
)


def _versao(texto: str) -> tuple:
    partes = []
    for pedaco in texto.replace("-", ".").split("."):
        partes.append(int(pedaco) if pedaco.isdigit() else 0)
    return tuple(partes)


def achar_executavel(raizes: list[Path] | None = None) -> Path | None:
    r"""Onde está o `GoogleDriveFS.exe`, se estiver no lugar de sempre.

    O Drive atualiza trocando a pasta da versão (`...\Drive File Stream\110.0.3.0`),
    então a busca pega a pasta mais nova em vez de decorar um caminho.
    """
    candidatas = list(raizes) if raizes is not None else list(_PASTAS_DRIVE)
    achados: list[Path] = []
    for raiz in candidatas:
        if not raiz.is_dir():
            continue
        for subpasta in raiz.iterdir():
            exe = subpasta / PROCESSO_DRIVE
            if subpasta.is_dir() and exe.is_file():
                achados.append(exe)
    if not achados:
        return None
    achados.sort(key=lambda item: _versao(item.parent.name), reverse=True)
    return achados[0]


def _rodar(comando: list[str], escondido: bool = False) -> tuple[int, str]:
    """Roda um comando já montado aqui dentro — nunca veio de texto livre."""
    import subprocess  # noqa: PLC0415

    opcoes: dict[str, Any] = {"capture_output": True, "text": True, "timeout": 30, "check": False}
    if escondido:
        opcoes["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
        opcoes.pop("capture_output", None)
        opcoes.pop("text", None)
    try:
        feito = subprocess.run(comando, **opcoes)
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)
    saida = ""
    if not escondido:
        saida = ((feito.stdout or "") + (feito.stderr or "")).strip()
    return feito.returncode, saida


def fechar(
    *,
    processos: list[str] | None = None,
    correr: Any = None,
    confirmar: bool = False,
) -> dict[str, Any]:
    """Fecha o app do Drive. Sem `confirmar`, só devolve o aviso do que acontece."""
    rodar = correr or _rodar
    if os.name != "nt":
        raise DriveError("Fechar o app do Google Drive é ação de Windows; aqui não há app para fechar.")
    aberto = drive_aberto(processos)
    aviso = (
        "Fechar o Google Drive para a sincronização, mas também derruba a unidade "
        "`G:` — e a biblioteca do JARVIS mora nela. Enquanto estiver fechado, o "
        "JARVIS não acha livro nenhum. Para só parar de transferir e continuar "
        "lendo, use o menu do app (Pausar sincronização), que mantém a unidade."
    )
    if not aberto:
        return {
            "app": "drive",
            "acao": "fechar",
            "ja_estava": True,
            "fechado": True,
            "mensagem": "O app do Google Drive já estava fechado.",
            "aviso": aviso,
        }
    if not confirmar:
        return {"app": "drive", "acao": "fechar", "vai_fechar": True, "aviso": aviso, "confirma": True}

    codigo, saida = rodar(["taskkill", "/IM", PROCESSO_DRIVE, "/F"])
    restantes = drive_aberto(processos) if processos is not None else drive_aberto()
    return {
        "app": "drive",
        "acao": "fechar",
        "fechado": restantes is False,
        "codigo": codigo,
        "saida": saida[:300],
        "mensagem": (
            "Fechei o app do Google Drive: a sincronização parou e a unidade `G:` saiu."
            if restantes is False
            else "Pedi para fechar, mas o app ainda aparece rodando. Confira na bandeja."
        ),
        "aviso": aviso,
    }


def abrir(*, correr: Any = None, raizes: list[Path] | None = None) -> dict[str, Any]:
    """Abre o app do Drive de novo (e a unidade `G:` volta com ele)."""
    rodar = correr or _rodar
    if os.name != "nt":
        raise DriveError("Abrir o app do Google Drive é ação de Windows.")
    if drive_aberto() is True:
        return {"app": "drive", "acao": "abrir", "ja_estava": True, "aberto": True,
                "mensagem": "O app do Google Drive já estava aberto."}
    exe = achar_executavel(raizes)
    if exe is None:
        raise DriveError(
            "Não achei o `GoogleDriveFS.exe`. Abra o Google Drive pelo menu Iniciar — "
            "o JARVIS só consegue abrir sozinho quando o app está na pasta padrão."
        )
    codigo, saida = rodar([str(exe)], escondido=True)
    return {
        "app": "drive",
        "acao": "abrir",
        "aberto": codigo == 0,
        "executavel": str(exe),
        "codigo": codigo,
        "saida": saida[:300],
        "mensagem": (
            "Abrindo o Google Drive. A unidade `G:` volta em alguns segundos."
            if codigo == 0
            else "Não consegui abrir o app; abra pelo menu Iniciar."
        ),
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
