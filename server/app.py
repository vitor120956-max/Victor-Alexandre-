"""Aplicação FastAPI do núcleo JARVIS."""
from __future__ import annotations

import mimetypes
import os
import tempfile
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .ai import AIProvider, AIRequest, AIUnavailable, OpenAICompatibleProvider
from .reverse import ARTIFACT_EXTENSIONS, MAX_ARTIFACT_BYTES, artifact_file, list_artifacts, reverse_root
from .skill_registry import SkillError, SkillRegistry, build_registry
from .workspace import MAX_DOCUMENT_BYTES, VISIBLE_EXTENSIONS, download_url, regular_file, safe_path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAX_BODY_BYTES = 2_000_000
MAX_UPLOAD_BODY_BYTES = MAX_DOCUMENT_BYTES + 1_000_000


class ExecuteRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    parameters: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = Field(default=False, alias="dryRun")
    confirmed: bool = False


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


def create_app(*, ai_provider: AIProvider | None = None, registry: SkillRegistry | None = None) -> FastAPI:
    load_dotenv(PROJECT_ROOT / ".env")
    provider = ai_provider or OpenAICompatibleProvider()
    files_root_value = os.getenv("JARVIS_FILES_ROOT", "").strip()
    files_root = Path(files_root_value).expanduser() if files_root_value else PROJECT_ROOT / "storage" / "user-files"
    skill_registry = registry or build_registry(files_root)

    application = FastAPI(
        title="JARVIS Skills API",
        description="Skills Python validadas e camada opcional de IA externa.",
        version="0.16.0",
    )
    application.state.rate_limiter = RateLimiter()

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
            "version": "0.16.0",
            "time": datetime.now(timezone.utc).isoformat(),
            "skills": len(skill_registry.list()),
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

    dist = PROJECT_ROOT / "dist"

    @application.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str):  # type: ignore[no-untyped-def]
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Rota de API não encontrada.")
        if not dist.exists():
            return {"service": "JARVIS API", "status": "online", "docs": "/docs"}
        candidate = (dist / full_path).resolve()
        try:
            candidate.relative_to(dist.resolve())
        except ValueError as exc:
            raise HTTPException(status_code=403, detail="Caminho inválido.") from exc
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")

    return application


app = create_app()
