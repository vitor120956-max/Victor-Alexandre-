"""Aplicação FastAPI do núcleo JARVIS."""
from __future__ import annotations

import mimetypes
import os
import threading
import tempfile
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .agente_local import RECEITAS, AgenteError, atender as agente_atender, carregar_locais
from .ai import AIProvider, AIRequest, AIUnavailable, OpenAICompatibleProvider
from .estacao_runtime import EstacaoRuntime, EstacaoRuntimeError
from .pesquisa import responder as pesquisa_responder
from .reverse import ARTIFACT_EXTENSIONS, MAX_ARTIFACT_BYTES, artifact_file, list_artifacts, reverse_root
from .sistema import SistemaError, token_host as sistema_token_host
from .skill_registry import SkillError, SkillRegistry, build_registry
from .workspace import MAX_DOCUMENT_BYTES, VISIBLE_EXTENSIONS, download_url, regular_file, safe_path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAX_BODY_BYTES = 2_000_000
MAX_UPLOAD_BODY_BYTES = MAX_DOCUMENT_BYTES + 1_000_000


class PesquisaRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    pergunta: str = Field(min_length=3, max_length=400)
    autorizacao: str = Field(default="")
    limite: int = Field(default=6, ge=1, le=10)
    paginas: int = Field(default=2, ge=0, le=3)


class AgenteRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    pedido: str = Field(min_length=3, max_length=2_000)
    autorizacao: str = Field(default="")
    criar: bool = True
    consultar_web: bool = Field(default=True, alias="consultarWeb")


class ExecuteRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    parameters: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = Field(default=False, alias="dryRun")
    confirmed: bool = False


class EstacaoExecutarRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ferramenta: str = Field(min_length=2, max_length=40)
    argumentos: dict[str, Any] = Field(default_factory=dict)
    tarefa: str = Field(default="", max_length=200)


class EstacaoDecidirRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aprovado: bool
    nota: str = Field(default="", max_length=400)


class EstacaoPoliticaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    permissao: str = Field(min_length=3, max_length=40)
    decisao: str = Field(min_length=3, max_length=8)


class EstacaoAutomacaoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: str = Field(min_length=1, max_length=40)
    cron: str = Field(min_length=9, max_length=80)
    comando: str = Field(min_length=1, max_length=8_000)
    minutos: int = Field(default=10, ge=1, le=60)


def _estacao_lifespan(runtime: EstacaoRuntime):
    @asynccontextmanager
    async def lifespan(_app: FastAPI):  # type: ignore[no-untyped-def]
        runtime.recuperar()
        parar = threading.Event()

        def laco() -> None:
            while not parar.wait(30):
                try:
                    runtime.tick()
                except Exception:  # noqa: BLE001 - o agendador não pode derrubar a API
                    continue

        thread = threading.Thread(target=laco, daemon=True, name="estacao-agenda")
        thread.start()
        try:
            yield
        finally:
            parar.set()

    return lifespan


def _estacao_erro(mensagem: str) -> dict[str, Any]:
    return {"ok": False, "error": {"code": "ESTACAO_ERROR", "message": mensagem}}


class RateLimiter:
    def __init__(self) -> None:
        self.buckets: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, limit: int, window_seconds: int = 60) -> bool:
        now = time.monotonic()
        bucket = self.buckets[key]
        while bucket and bucket[0] <= now - window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True


def pasta_da_interface(base: Path | None = None) -> Path | None:
    """Onde está a interface já compilada: `dist` (build local) ou `web-dist` (embutida no Git).

    O `web-dist` existe para quem não quer (ou não consegue) rodar `npm install`:
    a API serve a mesma interface sem Node instalado.
    """
    raiz = base or PROJECT_ROOT
    for nome in ("dist", "web-dist"):
        candidata = raiz / nome
        if (candidata / "index.html").is_file():
            return candidata
    return None


def create_app(
    *,
    ai_provider: AIProvider | None = None,
    registry: SkillRegistry | None = None,
    estacao: EstacaoRuntime | None = None,
    agente_root: Path | None = None,
) -> FastAPI:
    load_dotenv(PROJECT_ROOT / ".env")
    provider = ai_provider or OpenAICompatibleProvider()
    files_root_value = os.getenv("JARVIS_FILES_ROOT", "").strip()
    files_root = Path(files_root_value).expanduser() if files_root_value else PROJECT_ROOT / "storage" / "user-files"
    skill_registry = registry or build_registry(files_root, ai_provider=provider)
    estacao_runtime = estacao or EstacaoRuntime(root=skill_registry.files_root)
    pasta_agente = Path(agente_root) if agente_root else PROJECT_ROOT / "storage"
    # A camada de host exige prova de acesso: o token aparece aqui, no terminal de
    # quem subiu a API, e nunca numa resposta HTTP.
    if os.getenv("JARVIS_HOST_TOKEN_SILENCIOSO", "0") != "1":
        _token_host = sistema_token_host()
        if _token_host:
            print(
                "JARVIS modo host: token em storage/host-token.txt -> "
                f"{_token_host[:4]}…{_token_host[-4:]} "
                f"(rede={'ligada' if os.getenv('JARVIS_HOST_REDE') == '1' else 'desligada'}, "
                f"instalar={'ligado' if os.getenv('JARVIS_HOST_INSTALAR') == '1' else 'desligado'}, "
                f"root={'ligado' if os.getenv('JARVIS_HOST_ROOT') == '1' else 'desligado'})"
            )

    application = FastAPI(
        title="JARVIS Skills API",
        description="Skills Python validadas, executor da Estação e camada opcional de IA externa.",
        version="0.39.0",
        lifespan=_estacao_lifespan(estacao_runtime),
    )
    application.state.estacao = estacao_runtime
    application.state.rate_limiter = RateLimiter()
    interface = pasta_da_interface()

    @application.middleware("http")
    async def protect_api(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.url.path.startswith("/api/"):
            content_length = request.headers.get("content-length")
            body_limit = MAX_UPLOAD_BODY_BYTES if request.url.path in {"/api/files/upload", "/api/reverse/upload"} else MAX_BODY_BYTES
            try:
                too_large = bool(content_length and int(content_length) > body_limit)
            except ValueError:
                too_large = True
            if too_large:
                return JSONResponse(status_code=413, content={"ok": False, "error": {"code": "BODY_TOO_LARGE", "message": "A requisição excede o limite de tamanho."}})
            if request.method == "POST":
                is_ai = request.url.path == "/api/ai/chat"
                key = f"{request.client.host if request.client else 'unknown'}:{'ai' if is_ai else 'skill'}"
                if not application.state.rate_limiter.allow(key, 12 if is_ai else 40):
                    return JSONResponse(status_code=429, content={"ok": False, "error": {"code": "RATE_LIMIT", "message": "Muitas execuções em pouco tempo. Aguarde um minuto."}})
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @application.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "service": "jarvis-python-api",
            "version": "0.39.0",
            "time": datetime.now(timezone.utc).isoformat(),
            "skills": len(skill_registry.list()),
            "interface": interface.name if interface else "ausente",
        }

    @application.get("/api/skills")
    def list_skills() -> dict[str, Any]:
        return {"ok": True, "skills": skill_registry.list()}

    @application.post("/api/skills/{skill_id}/execute")
    async def execute_skill(skill_id: str, payload: ExecuteRequest) -> dict[str, Any]:
        try:
            definition = skill_registry.get(skill_id)
        except SkillError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if definition.requires_confirmation and not payload.dry_run and not payload.confirmed:
            return {
                "ok": False,
                "error": {"code": "CONFIRMATION_REQUIRED", "message": "Confirme a gravação antes de executar esta skill."},
            }
        started = time.perf_counter()
        try:
            result = await skill_registry.execute(skill_id, payload.parameters, payload.dry_run)
        except SkillError as exc:
            return {"ok": False, "error": {"code": "SKILL_ERROR", "message": str(exc)}}
        except Exception as exc:
            # Detalhes de infraestrutura e entradas do usuário não vazam na resposta.
            print(f"Skill {skill_id} falhou com {type(exc).__name__}")
            return {"ok": False, "error": {"code": "INTERNAL_ERROR", "message": "A skill falhou. Nenhum detalhe interno foi exposto."}}
        return {
            "ok": True,
            "skill": skill_id,
            "dryRun": payload.dry_run,
            "result": result,
            "durationMs": round((time.perf_counter() - started) * 1000, 2),
            "executedAt": datetime.now(timezone.utc).isoformat(),
        }

    @application.post("/api/files/upload")
    async def upload_user_file(
        upload: UploadFile = File(...),
        directory: str = Form(default=""),
        overwrite: bool = Form(default=False),
        confirmed: bool = Form(default=False),
    ) -> Any:
        if not confirmed:
            return JSONResponse(status_code=400, content={"ok": False, "error": {"code": "CONFIRMATION_REQUIRED", "message": "Confirme a gravação do upload na área isolada."}})
        filename = (upload.filename or "").strip().replace("\\", "/")
        if not filename or filename != PurePosixPath(filename).name or filename.startswith("."):
            return JSONResponse(status_code=400, content={"ok": False, "error": {"code": "INVALID_FILENAME", "message": "Use um nome de arquivo visível, sem pastas."}})
        if Path(filename).suffix.lower() not in VISIBLE_EXTENSIONS:
            return JSONResponse(status_code=400, content={"ok": False, "error": {"code": "INVALID_FORMAT", "message": "Formato não permitido. Use TXT, MD, JSON, CSV, LOG, DOCX, XLSX, PPTX ou PDF."}})
        temporary_name = ""
        try:
            clean_directory = directory.strip().rstrip("/")
            relative = f"{clean_directory}/{filename}" if clean_directory else filename
            target = safe_path(skill_registry.files_root, relative)
            if target.exists() and (not target.is_file() or target.is_symlink()):
                raise ValueError("O destino existe, mas não é um arquivo regular.")
            if target.exists() and not overwrite:
                return JSONResponse(status_code=409, content={"ok": False, "error": {"code": "FILE_EXISTS", "message": "O arquivo já existe. Ative a sobrescrita somente se quiser substituí-lo."}})
            target.parent.mkdir(parents=True, exist_ok=True)
            total = 0
            with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".upload", delete=False) as temporary:
                temporary_name = temporary.name
                while chunk := await upload.read(1_000_000):
                    total += len(chunk)
                    if total > MAX_DOCUMENT_BYTES:
                        raise ValueError("SIZE_LIMIT")
                    temporary.write(chunk)
            if total == 0:
                raise ValueError("O arquivo enviado está vazio.")
            if target.exists() and not overwrite:
                raise ValueError("O destino apareceu durante o upload. Repita a validação antes de sobrescrever.")
            Path(temporary_name).replace(target)
            relative = target.relative_to(skill_registry.files_root).as_posix()
            return {"ok": True, "path": relative, "bytes": total, "downloadUrl": download_url(relative)}
        except ValueError as exc:
            if str(exc) == "SIZE_LIMIT":
                return JSONResponse(status_code=413, content={"ok": False, "error": {"code": "FILE_TOO_LARGE", "message": "O arquivo excede o limite de 25 MB."}})
            return JSONResponse(status_code=400, content={"ok": False, "error": {"code": "UPLOAD_ERROR", "message": str(exc)}})
        finally:
            await upload.close()
            if temporary_name:
                Path(temporary_name).unlink(missing_ok=True)

    @application.get("/api/files/download")
    def download_user_file(path: str = Query(min_length=1, max_length=160)) -> FileResponse:
        try:
            source = regular_file(skill_registry.files_root, path, VISIBLE_EXTENSIONS, MAX_DOCUMENT_BYTES)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        media_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        return FileResponse(source, media_type=media_type, filename=source.name)


    @application.get("/api/reverse/files")
    def list_reverse_files() -> dict[str, Any]:
        return {"ok": True, **list_artifacts(skill_registry.files_root)}

    @application.post("/api/reverse/upload")
    async def upload_reverse_file(
        upload: UploadFile = File(...),
        directory: str = Form(default=""),
        overwrite: bool = Form(default=False),
        confirmed: bool = Form(default=False),
    ) -> Any:
        if not confirmed:
            return JSONResponse(status_code=400, content={"ok": False, "error": {"code": "CONFIRMATION_REQUIRED", "message": "Confirme a gravação do artefato na área de engenharia reversa."}})
        filename = (upload.filename or "").strip().replace("\\", "/")
        if not filename or filename != PurePosixPath(filename).name or filename.startswith("."):
            return JSONResponse(status_code=400, content={"ok": False, "error": {"code": "INVALID_FILENAME", "message": "Use um nome de artefato visível, sem pastas."}})
        if Path(filename).suffix.lower() not in ARTIFACT_EXTENSIONS:
            return JSONResponse(status_code=400, content={"ok": False, "error": {"code": "INVALID_FORMAT", "message": "Formato não permitido na área de engenharia reversa."}})
        temporary_name = ""
        try:
            root = reverse_root(skill_registry.files_root)
            clean_directory = directory.strip().rstrip("/")
            relative = f"{clean_directory}/{filename}" if clean_directory else filename
            target = safe_path(root, relative)
            if target.exists() and (not target.is_file() or target.is_symlink()):
                raise ValueError("O destino existe, mas não é um arquivo regular.")
            if target.exists() and not overwrite:
                return JSONResponse(status_code=409, content={"ok": False, "error": {"code": "FILE_EXISTS", "message": "O artefato já existe. Ative a sobrescrita somente se quiser substituí-lo."}})
            target.parent.mkdir(parents=True, exist_ok=True)
            total = 0
            with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".upload", delete=False) as temporary:
                temporary_name = temporary.name
                while chunk := await upload.read(1_000_000):
                    total += len(chunk)
                    if total > MAX_ARTIFACT_BYTES:
                        raise ValueError("SIZE_LIMIT")
                    temporary.write(chunk)
            if total == 0:
                raise ValueError("O artefato enviado está vazio.")
            if target.exists() and not overwrite:
                raise ValueError("O destino apareceu durante o upload. Repita a validação antes de sobrescrever.")
            Path(temporary_name).replace(target)
            relative = target.relative_to(root).as_posix()
            return {"ok": True, "path": relative, "bytes": total, "downloadUrl": f"/api/reverse/download?path={quote(relative, safe='')}"}
        except ValueError as exc:
            if str(exc) == "SIZE_LIMIT":
                return JSONResponse(status_code=413, content={"ok": False, "error": {"code": "FILE_TOO_LARGE", "message": "O artefato excede o limite de 25 MB."}})
            return JSONResponse(status_code=400, content={"ok": False, "error": {"code": "UPLOAD_ERROR", "message": str(exc)}})
        finally:
            await upload.close()
            if temporary_name:
                Path(temporary_name).unlink(missing_ok=True)

    @application.get("/api/reverse/download")
    def download_reverse_file(path: str = Query(min_length=1, max_length=200)) -> FileResponse:
        try:
            source = artifact_file(skill_registry.files_root, path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return FileResponse(source, media_type="application/octet-stream", filename=source.name)

    @application.get("/api/ai/status")
    def ai_status() -> dict[str, Any]:
        return {"ok": True, **provider.status()}

    @application.post("/api/ai/chat")
    async def ai_chat(payload: AIRequest) -> dict[str, Any]:
        if not provider.configured:
            return JSONResponse(
                status_code=503,
                content={"ok": False, "error": {"code": "AI_NOT_CONFIGURED", "message": "Configure o provedor de IA no arquivo .env do servidor."}},
            )
        try:
            content = await provider.generate(payload)
        except AIUnavailable as exc:
            return JSONResponse(status_code=502, content={"ok": False, "error": {"code": "AI_UNAVAILABLE", "message": str(exc)}})
        except Exception:
            return JSONResponse(status_code=502, content={"ok": False, "error": {"code": "AI_UNAVAILABLE", "message": "A camada de IA não conseguiu concluir a resposta."}})
        return {"ok": True, "content": content, "provider": provider.status()["provider"], "external": True}

    @application.post("/api/pesquisa/responder")
    async def pesquisa_responder_rota(payload: PesquisaRequest) -> dict[str, Any]:
        try:
            resultado = await pesquisa_responder(
                payload.pergunta,
                autorizacao=payload.autorizacao,
                provedor=provider,
                limite=payload.limite,
                paginas=payload.paginas,
            )
        except SistemaError as exc:
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": {"code": "PESQUISA_RECUSADA", "message": str(exc)}},
            )
        return {"ok": True, "result": resultado}

    # ------------------------------------------------------------ agente local

    @application.post("/api/agente/executar")
    async def agente_executar(payload: AgenteRequest) -> dict[str, Any]:
        try:
            resultado = await agente_atender(
                payload.pedido,
                registry=skill_registry,
                raiz=pasta_agente,
                autorizacao=payload.autorizacao,
                criar=payload.criar,
                consultar_web=payload.consultar_web,
            )
        except AgenteError as exc:
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": {"code": "AGENTE_RECUSADO", "message": str(exc)}},
            )
        return {"ok": True, "result": resultado}

    @application.get("/api/agente/skills")
    def agente_skills() -> dict[str, Any]:
        locais = [local.publica() for local in carregar_locais(pasta_agente)]
        return {
            "ok": True,
            "result": {
                "locais": locais,
                "receitas": [receita.publica() for receita in RECEITAS],
            },
        }

    # ------------------------------------------------------------ estação real

    @application.get("/api/estacao/estado")
    def estacao_estado() -> dict[str, Any]:
        return {"ok": True, "result": estacao_runtime.estado()}

    @application.post("/api/estacao/executar")
    def estacao_executar(payload: EstacaoExecutarRequest) -> dict[str, Any]:
        try:
            chamada = estacao_runtime.solicitar(payload.ferramenta, payload.argumentos, payload.tarefa)
        except EstacaoRuntimeError as exc:
            return _estacao_erro(str(exc))
        return {"ok": True, "result": chamada}

    @application.get("/api/estacao/aprovacoes")
    def estacao_aprovacoes() -> dict[str, Any]:
        return {"ok": True, "result": {"pendentes": estacao_runtime.pendentes()}}

    @application.post("/api/estacao/aprovacoes/{chamada_id}/decidir")
    def estacao_decidir(chamada_id: str, payload: EstacaoDecidirRequest) -> dict[str, Any]:
        try:
            chamada = estacao_runtime.aprovar(chamada_id, payload.aprovado, payload.nota)
        except EstacaoRuntimeError as exc:
            return _estacao_erro(str(exc))
        return {"ok": True, "result": chamada}

    @application.get("/api/estacao/chamadas")
    def estacao_chamadas(limite: int = Query(default=30, ge=1, le=500)) -> dict[str, Any]:
        return {"ok": True, "result": {"chamadas": estacao_runtime.chamadas(limite)}}

    @application.get("/api/estacao/recibos")
    def estacao_recibos(
        chamada: str = Query(default="", max_length=40),
        limite: int = Query(default=200, ge=1, le=1_000),
    ) -> dict[str, Any]:
        return {"ok": True, "result": {"recibos": estacao_runtime.recibos(chamada, limite)}}

    @application.put("/api/estacao/politica")
    def estacao_politica(payload: EstacaoPoliticaRequest) -> dict[str, Any]:
        try:
            politica = estacao_runtime.definir_politica(payload.permissao, payload.decisao)
        except EstacaoRuntimeError as exc:
            return _estacao_erro(str(exc))
        return {"ok": True, "result": {"politica": politica}}

    @application.get("/api/estacao/agenda")
    def estacao_agenda() -> dict[str, Any]:
        return {"ok": True, "result": {"automacoes": estacao_runtime.automacoes()}}

    @application.post("/api/estacao/agenda")
    def estacao_criar_agenda(payload: EstacaoAutomacaoRequest) -> dict[str, Any]:
        try:
            chamada = estacao_runtime.solicitar(
                "cron",
                {"nome": payload.nome, "cron": payload.cron, "comando": payload.comando,
                 "minutos": payload.minutos},
                tarefa="agenda",
            )
        except EstacaoRuntimeError as exc:
            return _estacao_erro(str(exc))
        return {"ok": True, "result": chamada}

    @application.post("/api/estacao/agenda/{nome}/alternar")
    def estacao_alternar_agenda(nome: str, ativa: bool = Query(default=True)) -> dict[str, Any]:
        try:
            automacao = estacao_runtime.alternar_automacao(nome, ativa)
        except EstacaoRuntimeError as exc:
            return _estacao_erro(str(exc))
        return {"ok": True, "result": automacao}

    @application.delete("/api/estacao/agenda/{nome}")
    def estacao_remover_agenda(nome: str) -> dict[str, Any]:
        try:
            removida = estacao_runtime.remover_automacao(nome)
        except EstacaoRuntimeError as exc:
            return _estacao_erro(str(exc))
        return {"ok": True, "result": removida}

    @application.post("/api/estacao/agenda/tick")
    def estacao_tick() -> dict[str, Any]:
        return {"ok": True, "result": estacao_runtime.tick()}

    @application.post("/api/estacao/recuperar")
    def estacao_recuperar() -> dict[str, Any]:
        return {"ok": True, "result": estacao_runtime.recuperar()}

    @application.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str):  # type: ignore[no-untyped-def]
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Rota de API não encontrada.")
        if interface is None:
            return {
                "service": "JARVIS API",
                "status": "online",
                "docs": "/docs",
                "interface": "ausente",
                "como_ligar": "Rode `npm run build` (grava em dist/) ou use a interface embutida em web-dist/.",
            }
        raiz = interface.resolve()
        candidate = (raiz / full_path).resolve()
        try:
            candidate.relative_to(raiz)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail="Caminho inválido.") from exc
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(raiz / "index.html")

    return application


app = create_app()
