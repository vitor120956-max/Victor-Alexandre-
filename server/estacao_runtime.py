"""Executor real da Estação: gate de permissão, fila de aprovação, recibos e recuperação.

Diferente das skills de `server/estacao.py` — que só leem texto e devolvem plano —
este módulo **executa**: roda `bash -lc` no diretório de trabalho da Estação, lê e
grava arquivos dentro dele, e mantém tudo em SQLite com recibo por chamada.

As garantias são as do upstream:

* **Permissão declarada** decide cada chamada (`allow`, `ask`, `deny`) antes de ela rodar.
* **`ask` para a rodada**: a chamada fica pendente com os argumentos completos, a
  decisão é registrada uma vez e libera aquela chamada uma única vez.
* **No máximo uma vez**: a chamada reivindica a linha com `UPDATE ... WHERE estado='pendente'`,
  então duas aprovações concorrentes não executam duas vezes.
* **Queda**: linha que ficou em `executando` é marcada `interrompido` na recuperação,
  com o aviso de que pode ter surtido efeito.
* **Recibo**: `intent`, `ok`/`erro`, `recusado`, `negado` e `interrompido`, com hora.

O confinamento é o diretório de trabalho e o ambiente do subprocesso (sem `JARVIS_*`,
sem `.env`). Isso não é uma jaula de sistema operacional — para isso o upstream usa uma
VM, que este repositório não tem.
"""
from __future__ import annotations

import json
import os
import re
import signal
import sqlite3
import subprocess
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .estacao import proxima_execucao
from .workspace import safe_path

VERSAO = "0.60.0"
MAX_SAIDA = 20_000
MAX_ARQUIVO = 2_000_000
TIMEOUT_PADRAO = 60
TIMEOUT_MAX = 600
MAX_CHAMADAS = 500

INTERROMPIDA = (
    "Esta chamada foi interrompida antes de o resultado ser registrado. "
    "Pode ter surtido efeito e pode ainda estar rodando. "
    "Confira o estado atual antes de chamar de novo."
)


class EstacaoRuntimeError(ValueError):
    """Erro de entrada do executor; a API devolve 200 com `ok:false`."""


FERRAMENTAS: dict[str, dict[str, Any]] = {
    "exec": {
        "permissao": "computer.exec",
        "descricao": "Roda `bash -lc` no diretório da Estação, com timeout.",
        "argumentos": ("comando", "timeout_s", "diretorio"),
    },
    "read_file": {
        "permissao": "files.read",
        "descricao": "Lê um arquivo de texto dentro da Estação.",
        "argumentos": ("caminho", "limite_linhas"),
    },
    "write_file": {
        "permissao": "files.write",
        "descricao": "Grava um arquivo inteiro dentro da Estação.",
        "argumentos": ("caminho", "conteudo", "simular"),
    },
    "list_dir": {
        "permissao": "files.read",
        "descricao": "Lista um diretório da Estação.",
        "argumentos": ("caminho", "recursivo"),
    },
    "grep": {
        "permissao": "files.read",
        "descricao": "Procura expressão regular no conteúdo dos arquivos.",
        "argumentos": ("padrao", "caminho", "limite"),
    },
    "cron": {
        "permissao": "automations",
        "descricao": "Cria uma automação agendada que roda `exec`.",
        "argumentos": ("nome", "cron", "comando", "minutos"),
    },
}

PERMISSOES: dict[str, dict[str, Any]] = {
    "computer.exec": {"risco": "alto", "padrao": "ask", "rotulo": "Executar comandos"},
    "files.read": {"risco": "baixo", "padrao": "allow", "rotulo": "Ler arquivos"},
    "files.write": {"risco": "médio", "padrao": "ask", "rotulo": "Escrever arquivos"},
    "automations": {"risco": "alto", "padrao": "ask", "rotulo": "Criar automações"},
}

DECISOES = ("allow", "ask", "deny")
ESTADOS = ("pendente", "executando", "ok", "erro", "interrompido", "recusado", "negado")

SCHEMA = """
CREATE TABLE IF NOT EXISTS chamadas (
    id TEXT PRIMARY KEY,
    tarefa TEXT NOT NULL DEFAULT '',
    ferramenta TEXT NOT NULL,
    permissao TEXT NOT NULL,
    decisao TEXT NOT NULL,
    estado TEXT NOT NULL,
    argumentos TEXT NOT NULL,
    resultado TEXT NOT NULL DEFAULT '',
    duracao_ms INTEGER NOT NULL DEFAULT 0,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS chamadas_estado ON chamadas (estado, criado_em);
CREATE TABLE IF NOT EXISTS recibos (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    chamada TEXT NOT NULL,
    evento TEXT NOT NULL,
    em TEXT NOT NULL,
    detalhe TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS recibos_chamada ON recibos (chamada, seq);
CREATE TABLE IF NOT EXISTS politica (
    permissao TEXT PRIMARY KEY,
    decisao TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS automacoes (
    nome TEXT PRIMARY KEY,
    cron TEXT NOT NULL,
    comando TEXT NOT NULL,
    minutos INTEGER NOT NULL DEFAULT 10,
    ativa INTEGER NOT NULL DEFAULT 1,
    proxima TEXT NOT NULL,
    ultima TEXT NOT NULL DEFAULT '',
    falhas INTEGER NOT NULL DEFAULT 0,
    criado_em TEXT NOT NULL
);
"""


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _truncar(texto: str) -> tuple[str, bool]:
    if len(texto) <= MAX_SAIDA:
        return texto, False
    return texto[:MAX_SAIDA] + "\n… corte em 20 000 caracteres.", True


class EstacaoRuntime:
    """Fila durável de chamadas com gate de permissão e execução real."""

    def __init__(self, root: Path, db_path: Path | None = None) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = Path(db_path) if db_path else self.root.parent / "estacao" / "estacao.db"
        self._lock = threading.RLock()
        self._em_curso: set[str] = set()
        self._pronto = False

    # ------------------------------------------------------------- armazenamento

    def _preparar(self) -> None:
        """Cria diretório e esquema na primeira chamada — importar `create_app` não grava nada."""
        if self._pronto:
            return
        with self._lock:
            if self._pronto:
                return
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path) as conn:
                conn.executescript(SCHEMA)
            self._pronto = True

    def _conn(self) -> sqlite3.Connection:
        self._preparar()
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn

    def _recibo(self, chamada: str, evento: str, detalhe: str = "") -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO recibos (chamada, evento, em, detalhe) VALUES (?, ?, ?, ?)",
                (chamada, evento, _agora(), detalhe[:2_000]),
            )

    def _atualizar(self, chamada: str, **campos: Any) -> None:
        if not campos:
            return
        campos["atualizado_em"] = _agora()
        chaves = ", ".join(f"{chave} = ?" for chave in campos)
        valores = list(campos.values()) + [chamada]
        with self._conn() as conn:
            conn.execute(f"UPDATE chamadas SET {chaves} WHERE id = ?", valores)

    # ---------------------------------------------------------------- política

    def politica(self) -> dict[str, str]:
        valores = {nome: dados["padrao"] for nome, dados in PERMISSOES.items()}
        with self._conn() as conn:
            for linha in conn.execute("SELECT permissao, decisao FROM politica"):
                valores[linha["permissao"]] = linha["decisao"]
        return valores

    def definir_politica(self, permissao: str, decisao: str) -> dict[str, str]:
        if permissao not in PERMISSOES:
            raise EstacaoRuntimeError(
                "Permissão desconhecida. Use: " + ", ".join(sorted(PERMISSOES)) + "."
            )
        if decisao not in DECISOES:
            raise EstacaoRuntimeError("Decisão inválida: use allow, ask ou deny.")
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO politica (permissao, decisao) VALUES (?, ?) "
                "ON CONFLICT(permissao) DO UPDATE SET decisao = excluded.decisao",
                (permissao, decisao),
            )
        return self.politica()

    def decisao(self, permissao: str) -> str:
        return self.politica().get(permissao, "deny")

    # ------------------------------------------------------------------ chamada

    def _validar(self, ferramenta: str, argumentos: dict[str, Any]) -> dict[str, Any]:
        if ferramenta not in FERRAMENTAS:
            raise EstacaoRuntimeError(
                f"Ferramenta desconhecida: `{ferramenta}`. Use " + ", ".join(sorted(FERRAMENTAS)) + "."
            )
        if not isinstance(argumentos, dict):
            raise EstacaoRuntimeError("Os argumentos precisam ser um objeto.")
        permitidos = set(FERRAMENTAS[ferramenta]["argumentos"])
        extras = {chave for chave in argumentos if chave not in permitidos}
        if extras:
            raise EstacaoRuntimeError(
                f"Argumento não aceito por `{ferramenta}`: {', '.join(sorted(extras))}."
            )
        for chave, valor in argumentos.items():
            if isinstance(valor, (dict, list)):
                raise EstacaoRuntimeError(f"O argumento `{chave}` precisa ser um valor simples.")
        return argumentos

    def solicitar(
        self, ferramenta: str, argumentos: dict[str, Any] | None = None, tarefa: str = ""
    ) -> dict[str, Any]:
        ferramenta = (ferramenta or "").strip().lower()
        dados = self._validar(ferramenta, dict(argumentos or {}))
        self._validar_argumentos(ferramenta, dados)
        permissao = FERRAMENTAS[ferramenta]["permissao"]
        decisao = self.decisao(permissao)
        chamada_id = uuid.uuid4().hex[:12]
        agora = _agora()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO chamadas (id, tarefa, ferramenta, permissao, decisao, estado, argumentos,"
                " resultado, duracao_ms, criado_em, atualizado_em) VALUES (?, ?, ?, ?, ?, 'pendente', ?, '', 0, ?, ?)",
                (chamada_id, tarefa[:200], ferramenta, permissao, decisao, json.dumps(dados, ensure_ascii=False), agora, agora),
            )
        alvo = self._alvo(ferramenta, dados)
        self._recibo(chamada_id, "intent", f"{ferramenta} {alvo}".strip())
        if decisao == "deny":
            self._atualizar(chamada_id, estado="negado", resultado=json.dumps({"motivo": "política deny"}))
            self._recibo(chamada_id, "negado", f"{permissao}=deny")
            return self.obter(chamada_id)
        if decisao == "allow":
            return self._executar(chamada_id)
        return self.obter(chamada_id)

    def _alvo(self, ferramenta: str, argumentos: dict[str, Any]) -> str:
        if ferramenta == "exec":
            return str(argumentos.get("comando", ""))[:120]
        if ferramenta == "cron":
            return str(argumentos.get("nome", ""))
        return str(argumentos.get("caminho", "") or argumentos.get("padrao", ""))[:120]

    def _validar_argumentos(self, ferramenta: str, argumentos: dict[str, Any]) -> None:
        if ferramenta == "exec":
            comando = str(argumentos.get("comando", "")).strip()
            if not comando:
                raise EstacaoRuntimeError("`exec` precisa de `comando`.")
            if len(comando) > 8_000:
                raise EstacaoRuntimeError("O comando passa de 8 000 caracteres.")
            timeout = argumentos.get("timeout_s", TIMEOUT_PADRAO)
            try:
                timeout = int(timeout)
            except (TypeError, ValueError) as exc:
                raise EstacaoRuntimeError("`timeout_s` precisa ser inteiro.") from exc
            if not 1 <= timeout <= TIMEOUT_MAX:
                raise EstacaoRuntimeError(f"`timeout_s` fica entre 1 e {TIMEOUT_MAX}.")
            argumentos["timeout_s"] = timeout
        elif ferramenta == "read_file":
            if not str(argumentos.get("caminho", "")).strip():
                raise EstacaoRuntimeError("`read_file` precisa de `caminho`.")
        elif ferramenta == "write_file":
            if not str(argumentos.get("caminho", "")).strip():
                raise EstacaoRuntimeError("`write_file` precisa de `caminho`.")
            conteudo = argumentos.get("conteudo", "")
            if not isinstance(conteudo, str):
                raise EstacaoRuntimeError("`conteudo` precisa ser texto.")
            if len(conteudo) > MAX_ARQUIVO:
                raise EstacaoRuntimeError("O conteúdo passa de 2 MB.")
        elif ferramenta == "grep":
            if not str(argumentos.get("padrao", "")).strip():
                raise EstacaoRuntimeError("`grep` precisa de `padrao`.")
            try:
                re.compile(str(argumentos["padrao"]))
            except re.error as exc:
                raise EstacaoRuntimeError(f"Expressão regular inválida: {exc}.") from exc
        elif ferramenta == "cron":
            for campo in ("nome", "cron", "comando"):
                if not str(argumentos.get(campo, "")).strip():
                    raise EstacaoRuntimeError(f"`cron` precisa de `{campo}`.")
            try:
                proxima_execucao(str(argumentos["cron"]), datetime.now(timezone.utc))
            except ValueError as exc:
                raise EstacaoRuntimeError(f"Cron inválido: {exc}") from exc

    def _executar(self, chamada_id: str) -> dict[str, Any]:
        with self._lock:
            if chamada_id in self._em_curso:
                return self.obter(chamada_id)
            with self._conn() as conn:
                cursor = conn.execute(
                    "UPDATE chamadas SET estado = 'executando', atualizado_em = ? "
                    "WHERE id = ? AND estado = 'pendente'",
                    (_agora(), chamada_id),
                )
                reivindicou = cursor.rowcount == 1
            if not reivindicou:
                return self.obter(chamada_id)
            self._em_curso.add(chamada_id)
        linha = self._linha(chamada_id)
        argumentos = json.loads(linha["argumentos"])
        inicio = time.monotonic()
        try:
            resultado, estado = self._rodar(linha["ferramenta"], argumentos)
        except EstacaoRuntimeError as erro:
            resultado, estado = {"erro": str(erro)}, "erro"
        except OSError as erro:
            resultado, estado = {"erro": f"Falha ao executar: {erro}"}, "erro"
        except Exception as erro:  # noqa: BLE001 - a chamada nunca deixa a linha pendurada
            resultado, estado = {"erro": f"Falha inesperada: {erro}"}, "erro"
        finally:
            duracao = int((time.monotonic() - inicio) * 1000)
            with self._lock:
                self._em_curso.discard(chamada_id)
        self._atualizar(
            chamada_id,
            estado=estado,
            resultado=json.dumps(resultado, ensure_ascii=False),
            duracao_ms=duracao,
        )
        self._recibo(chamada_id, estado, f"{duracao} ms")
        return self.obter(chamada_id)

    # --------------------------------------------------------------- ferramentas

    def _ambiente(self) -> dict[str, str]:
        return {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": str(self.root),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "TERM": "dumb",
        }

    def _rodar(self, ferramenta: str, argumentos: dict[str, Any]) -> tuple[dict[str, Any], str]:
        if ferramenta == "exec":
            return self._exec(argumentos)
        if ferramenta == "read_file":
            return self._ler(argumentos)
        if ferramenta == "write_file":
            return self._escrever(argumentos)
        if ferramenta == "list_dir":
            return self._listar(argumentos)
        if ferramenta == "grep":
            return self._grep(argumentos)
        if ferramenta == "cron":
            return self._cron(argumentos)
        raise EstacaoRuntimeError(f"Ferramenta sem executor: {ferramenta}.")

    def _caminho(self, relativo: str) -> Path:
        try:
            return safe_path(self.root, relativo, allow_root=relativo.strip() in {"", "."})
        except ValueError as exc:
            raise EstacaoRuntimeError(str(exc)) from exc

    def _exec(self, argumentos: dict[str, Any]) -> tuple[dict[str, Any], str]:
        comando = str(argumentos["comando"])
        timeout = int(argumentos.get("timeout_s", TIMEOUT_PADRAO))
        diretorio = str(argumentos.get("diretorio", "")).strip()
        cwd = self._caminho(diretorio) if diretorio else self.root
        if not cwd.is_dir():
            raise EstacaoRuntimeError("`diretorio` não é uma pasta da Estação.")
        processo = subprocess.Popen(
            ["bash", "-lc", comando],
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self._ambiente(),
            start_new_session=True,
        )
        estourou = False
        try:
            saida, erro = processo.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            estourou = True
            try:
                os.killpg(os.getpgid(processo.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                processo.kill()
            saida, erro = processo.communicate()
        texto = saida or ""
        if erro:
            texto += ("\n" if texto else "") + "[stderr]\n" + erro
        texto, truncado = _truncar(texto)
        resultado = {
            "codigo": processo.returncode,
            "saida": texto,
            "truncado": truncado,
            "timeout": estourou,
            "diretorio": str(cwd.relative_to(self.root)) or ".",
        }
        if estourou:
            resultado["erro"] = f"Tempo limite de {timeout}s excedido; o grupo de processos foi encerrado."
            return resultado, "erro"
        return resultado, "ok" if processo.returncode == 0 else "erro"

    def _ler(self, argumentos: dict[str, Any]) -> tuple[dict[str, Any], str]:
        caminho = self._caminho(str(argumentos["caminho"]))
        if not caminho.is_file() or caminho.is_symlink():
            raise EstacaoRuntimeError("Arquivo não encontrado na Estação.")
        if caminho.stat().st_size > MAX_ARQUIVO:
            raise EstacaoRuntimeError("O arquivo passa de 2 MB.")
        bruto = caminho.read_bytes()
        if b"\x00" in bruto[:4_000]:
            return {"caminho": str(caminho.relative_to(self.root)), "binario": True, "bytes": len(bruto)}, "ok"
        texto = bruto.decode("utf-8", errors="replace")
        limite = argumentos.get("limite_linhas")
        linhas = texto.splitlines()
        if isinstance(limite, int) and limite > 0:
            linhas = linhas[:limite]
        texto = "\n".join(linhas)
        cortado, truncado = _truncar(texto)
        return {
            "caminho": str(caminho.relative_to(self.root)),
            "bytes": len(bruto),
            "linhas": len(linhas),
            "texto": cortado,
            "truncado": truncado,
        }, "ok"

    def _escrever(self, argumentos: dict[str, Any]) -> tuple[dict[str, Any], str]:
        caminho = self._caminho(str(argumentos["caminho"]))
        conteudo = str(argumentos.get("conteudo", ""))
        simular = bool(argumentos.get("simular", False))
        existia = caminho.exists()
        if existia and not caminho.is_file():
            raise EstacaoRuntimeError("O caminho existe e não é um arquivo.")
        if not simular:
            caminho.parent.mkdir(parents=True, exist_ok=True)
            caminho.write_text(conteudo, encoding="utf-8")
        return {
            "caminho": str(caminho.relative_to(self.root)),
            "bytes": len(conteudo.encode("utf-8")),
            "criado": not existia,
            "simulado": simular,
        }, "ok"

    def _listar(self, argumentos: dict[str, Any]) -> tuple[dict[str, Any], str]:
        relativo = str(argumentos.get("caminho", "")).strip()
        base = self._caminho(relativo) if relativo else self.root
        if not base.is_dir():
            raise EstacaoRuntimeError("O caminho não é uma pasta da Estação.")
        recursivo = bool(argumentos.get("recursivo", False))
        itens: list[dict[str, Any]] = []
        gerador = base.rglob("*") if recursivo else base.iterdir()
        for item in sorted(gerador):
            if item.is_symlink():
                continue
            relativo_item = str(item.relative_to(self.root))
            if any(parte.startswith(".") for parte in item.relative_to(self.root).parts):
                continue
            itens.append({
                "caminho": relativo_item,
                "tipo": "pasta" if item.is_dir() else "arquivo",
                "bytes": item.stat().st_size if item.is_file() else 0,
            })
            if len(itens) >= 300:
                break
        return {"raiz": str(base.relative_to(self.root)) or ".", "itens": itens, "total": len(itens)}, "ok"

    def _grep(self, argumentos: dict[str, Any]) -> tuple[dict[str, Any], str]:
        padrao = re.compile(str(argumentos["padrao"]))
        relativo = str(argumentos.get("caminho", "")).strip()
        base = self._caminho(relativo) if relativo else self.root
        limite = int(argumentos.get("limite", 50) or 50)
        limite = max(1, min(limite, 200))
        achados: list[dict[str, Any]] = []
        arquivos = [base] if base.is_file() else sorted(base.rglob("*"))
        for arquivo in arquivos:
            if len(achados) >= limite:
                break
            if not arquivo.is_file() or arquivo.is_symlink():
                continue
            if arquivo.stat().st_size > MAX_ARQUIVO:
                continue
            try:
                conteudo = arquivo.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for numero, linha in enumerate(conteudo.splitlines(), start=1):
                if padrao.search(linha):
                    achados.append({
                        "caminho": str(arquivo.relative_to(self.root)),
                        "linha": numero,
                        "texto": linha.strip()[:200],
                    })
                    if len(achados) >= limite:
                        break
        return {"achados": achados, "total": len(achados), "limite": limite}, "ok"

    def _cron(self, argumentos: dict[str, Any]) -> tuple[dict[str, Any], str]:
        automacao = self.criar_automacao(
            nome=str(argumentos["nome"]),
            cron=str(argumentos["cron"]),
            comando=str(argumentos["comando"]),
            minutos=int(argumentos.get("minutos", 10) or 10),
        )
        return automacao, "ok"

    # ------------------------------------------------------------- aprovações

    def obter(self, chamada_id: str) -> dict[str, Any]:
        linha = self._linha(chamada_id)
        return self._publico(linha)

    def _linha(self, chamada_id: str) -> sqlite3.Row:
        with self._conn() as conn:
            linha = conn.execute("SELECT * FROM chamadas WHERE id = ?", (chamada_id,)).fetchone()
        if linha is None:
            raise EstacaoRuntimeError("Chamada não encontrada.")
        return linha

    def _publico(self, linha: sqlite3.Row) -> dict[str, Any]:
        resultado: Any = {}
        if linha["resultado"]:
            try:
                resultado = json.loads(linha["resultado"])
            except json.JSONDecodeError:
                resultado = {"texto": linha["resultado"]}
        return {
            "id": linha["id"],
            "tarefa": linha["tarefa"],
            "ferramenta": linha["ferramenta"],
            "permissao": linha["permissao"],
            "decisao": linha["decisao"],
            "estado": linha["estado"],
            "argumentos": json.loads(linha["argumentos"]),
            "resultado": resultado,
            "duracao_ms": linha["duracao_ms"],
            "criado_em": linha["criado_em"],
            "atualizado_em": linha["atualizado_em"],
            "executou": linha["estado"] in {"ok", "erro"},
        }

    def aprovar(self, chamada_id: str, aprovado: bool, nota: str = "") -> dict[str, Any]:
        with self._lock:
            linha = self._linha(chamada_id)
            if linha["estado"] != "pendente":
                return {
                    **self._publico(linha),
                    "ignorada": True,
                    "motivo_ignorada": f"A chamada já está em `{linha['estado']}`; a decisão não é reaplicada.",
                }
            if aprovado:
                self._recibo(chamada_id, "aprovado", nota[:400])
                return self._executar(chamada_id)
            self._atualizar(
                chamada_id,
                estado="recusado",
                resultado=json.dumps({"motivo": "recusada", "nota": nota}, ensure_ascii=False),
            )
            self._recibo(chamada_id, "recusado", nota[:400])
            return self._publico(self._linha(chamada_id))

    def pendentes(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            linhas = conn.execute(
                "SELECT * FROM chamadas WHERE estado = 'pendente' ORDER BY criado_em DESC LIMIT 100"
            ).fetchall()
        return [self._publico(linha) for linha in linhas]

    def chamadas(self, limite: int = 30) -> list[dict[str, Any]]:
        limite = max(1, min(int(limite), MAX_CHAMADAS))
        with self._conn() as conn:
            linhas = conn.execute(
                "SELECT * FROM chamadas ORDER BY criado_em DESC LIMIT ?", (limite,)
            ).fetchall()
        return [self._publico(linha) for linha in linhas]

    def recibos(self, chamada: str = "", limite: int = 200) -> list[dict[str, Any]]:
        limite = max(1, min(int(limite), 1_000))
        with self._conn() as conn:
            if chamada:
                linhas = conn.execute(
                    "SELECT * FROM recibos WHERE chamada = ? ORDER BY seq DESC LIMIT ?",
                    (chamada, limite),
                ).fetchall()
            else:
                linhas = conn.execute(
                    "SELECT * FROM recibos ORDER BY seq DESC LIMIT ?", (limite,)
                ).fetchall()
        return [
            {"seq": linha["seq"], "chamada": linha["chamada"], "evento": linha["evento"],
             "em": linha["em"], "detalhe": linha["detalhe"]}
            for linha in linhas
        ]

    # ------------------------------------------------------------ automações

    def criar_automacao(self, nome: str, cron: str, comando: str, minutos: int = 10) -> dict[str, Any]:
        nome = nome.strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}", nome.lower()):
            raise EstacaoRuntimeError("O nome aceita de 1 a 40 caracteres: letras minúsculas, números e hífen.")
        if not comando.strip():
            raise EstacaoRuntimeError("A automação precisa de `comando`.")
        minutos = max(1, min(int(minutos), 60))
        try:
            proxima = proxima_execucao(cron, datetime.now(timezone.utc))
        except ValueError as exc:
            raise EstacaoRuntimeError(f"Cron inválido: {exc}") from exc
        with self._conn() as conn:
            existente = conn.execute("SELECT nome FROM automacoes WHERE nome = ?", (nome.lower(),)).fetchone()
            if existente:
                raise EstacaoRuntimeError(f"Já existe uma automação chamada `{nome}`.")
            conn.execute(
                "INSERT INTO automacoes (nome, cron, comando, minutos, ativa, proxima, ultima, falhas, criado_em)"
                " VALUES (?, ?, ?, ?, 1, ?, '', 0, ?)",
                (nome.lower(), cron, comando, minutos, proxima.isoformat(timespec="seconds"), _agora()),
            )
        return self.automacao(nome.lower())

    def automacao(self, nome: str) -> dict[str, Any]:
        with self._conn() as conn:
            linha = conn.execute("SELECT * FROM automacoes WHERE nome = ?", (nome,)).fetchone()
        if linha is None:
            raise EstacaoRuntimeError("Automação não encontrada.")
        return {
            "nome": linha["nome"],
            "cron": linha["cron"],
            "comando": linha["comando"],
            "minutos": linha["minutos"],
            "ativa": bool(linha["ativa"]),
            "proxima": linha["proxima"],
            "ultima": linha["ultima"],
            "falhas": linha["falhas"],
            "criado_em": linha["criado_em"],
        }

    def automacoes(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            nomes = [linha["nome"] for linha in conn.execute("SELECT nome FROM automacoes ORDER BY nome")]
        return [self.automacao(nome) for nome in nomes]

    def remover_automacao(self, nome: str) -> dict[str, Any]:
        with self._conn() as conn:
            cursor = conn.execute("DELETE FROM automacoes WHERE nome = ?", (nome.lower(),))
        if cursor.rowcount != 1:
            raise EstacaoRuntimeError("Automação não encontrada.")
        return {"removida": nome.lower()}

    def alternar_automacao(self, nome: str, ativa: bool) -> dict[str, Any]:
        with self._conn() as conn:
            cursor = conn.execute(
                "UPDATE automacoes SET ativa = ? WHERE nome = ?", (1 if ativa else 0, nome.lower())
            )
        if cursor.rowcount != 1:
            raise EstacaoRuntimeError("Automação não encontrada.")
        return self.automacao(nome.lower())

    def tick(self, agora: datetime | None = None) -> dict[str, Any]:
        """Dispara as automações vencidas; cada uma passa pelo mesmo gate."""
        agora = agora or datetime.now(timezone.utc)
        disparadas: list[dict[str, Any]] = []
        with self._conn() as conn:
            linhas = conn.execute("SELECT * FROM automacoes WHERE ativa = 1").fetchall()
        for linha in linhas:
            proxima = datetime.fromisoformat(linha["proxima"])
            if proxima.tzinfo is None:
                proxima = proxima.replace(tzinfo=timezone.utc)
            if proxima > agora:
                continue
            try:
                chamada = self.solicitar(
                    "exec",
                    {"comando": linha["comando"], "timeout_s": min(linha["minutos"] * 60, TIMEOUT_MAX)},
                    tarefa=f"automacao:{linha['nome']}",
                )
            except EstacaoRuntimeError as erro:
                with self._conn() as conn:
                    conn.execute(
                        "UPDATE automacoes SET falhas = falhas + 1 WHERE nome = ?", (linha["nome"],)
                    )
                disparadas.append({"nome": linha["nome"], "erro": str(erro)})
                continue
            falhas = linha["falhas"] + (1 if chamada["estado"] in {"erro", "negado"} else 0)
            ativa = 0 if falhas >= 3 else 1
            try:
                seguinte = proxima_execucao(linha["cron"], agora)
            except EstacaoRuntimeError:
                seguinte = proxima + timedelta(days=1)
            with self._conn() as conn:
                conn.execute(
                    "UPDATE automacoes SET ultima = ?, proxima = ?, falhas = ?, ativa = ? WHERE nome = ?",
                    (chamada["id"], seguinte.isoformat(timespec="seconds"), falhas, ativa, linha["nome"]),
                )
            disparadas.append({
                "nome": linha["nome"], "chamada": chamada["id"], "estado": chamada["estado"],
                "falhas": falhas, "ativa": bool(ativa),
            })
        return {"disparadas": disparadas, "total": len(disparadas)}

    # ------------------------------------------------------------ recuperação

    def recuperar(self) -> dict[str, Any]:
        """Marca como interrompida toda chamada que ficou em `executando`."""
        with self._lock:
            with self._conn() as conn:
                ids = [linha["id"] for linha in conn.execute(
                    "SELECT id FROM chamadas WHERE estado = 'executando'"
                )]
            for chamada_id in ids:
                self._atualizar(
                    chamada_id,
                    estado="interrompido",
                    resultado=json.dumps({"mensagem": INTERROMPIDA, "resultado_desconhecido": True}, ensure_ascii=False),
                )
                self._recibo(chamada_id, "interrompido", "recuperação na entrada da unidade")
        return {"interrompidas": len(ids), "mensagem": INTERROMPIDA if ids else ""}

    def estado(self) -> dict[str, Any]:
        chamadas = self.chamadas(limite=30)
        pendentes = self.pendentes()
        contagem = {estado: 0 for estado in ESTADOS}
        for chamada in chamadas:
            contagem[chamada["estado"]] = contagem.get(chamada["estado"], 0) + 1
        return {
            "raiz": str(self.root),
            "banco": str(self.db_path),
            "politica": self.politica(),
            "permissoes": [
                {"nome": nome, **dados} for nome, dados in sorted(PERMISSOES.items())
            ],
            "ferramentas": [
                {"nome": nome, **dados} for nome, dados in sorted(FERRAMENTAS.items())
            ],
            "chamadas": chamadas,
            "pendentes": pendentes,
            "automacoes": self.automacoes(),
            "contagem": contagem,
            "versao": VERSAO,
            "executado": True,
        }
