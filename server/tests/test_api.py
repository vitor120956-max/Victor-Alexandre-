from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.ai import AIRequest
from server.app import create_app
from server.skill_registry import build_registry


class FakeProvider:
    def __init__(self, configured: bool = True) -> None:
        self._configured = configured
        self.last_request: AIRequest | None = None

    @property
    def configured(self) -> bool:
        return self._configured

    def status(self):  # type: ignore[no-untyped-def]
        return {"configured": self._configured, "provider": "Provedor de teste", "model": "fake", "external": True}

    async def generate(self, request: AIRequest) -> str:
        self.last_request = request
        return "Resposta externa de teste."


@pytest.fixture()
def client(tmp_path: Path):
    provider = FakeProvider()
    app = create_app(ai_provider=provider, registry=build_registry(tmp_path / "files"))
    with TestClient(app) as test_client:
        test_client.provider = provider  # type: ignore[attr-defined]
        yield test_client


def test_health_and_catalog(client: TestClient):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["version"] == "0.62.6"
    assert health.json()["skills"] == 291
    catalog = client.get("/api/skills").json()["skills"]
    assert {skill["id"] for skill in catalog} >= {
        "text.analyze", "files.write", "system.status", "legal.search", "legal.article", "legal.sources",
        "document.read", "document.create", "pdf.merge", "files.organize", "meeting.analyze", "changelog.generate", "random.pick",
        "engineering.spec", "engineering.plan", "engineering.tests", "engineering.review", "engineering.threat-model", "engineering.webvitals", "engineering.adr", "engineering.release",
        "reverse.inspect", "reverse.layout", "reverse.strings", "reverse.entropy", "reverse.javascript", "reverse.compare",
        "lean.ladder", "lean.review", "lean.audit", "lean.debt",
        "agency.roster", "agency.board", "agency.budget", "agency.watchdog", "agency.permissions", "agency.defaults",
        "studio.contract", "studio.contrast", "studio.critique", "studio.artifact", "studio.defaults",
    }
    write = next(skill for skill in catalog if skill["id"] == "files.write")
    assert write["requiresConfirmation"] is True
    assert write["inputSchema"]["properties"]["content"]["format"] == "textarea"


def test_python_skills_execute_real_work(client: TestClient):
    analysis = client.post("/api/skills/text.analyze/execute", json={"parameters": {"text": "Jarvis organiza tarefas. Jarvis preserva memórias."}}).json()
    assert analysis["ok"] is True
    assert analysis["result"]["words"] == 6
    assert analysis["result"]["sentences"] == 2
    calculation = client.post("/api/skills/data.calculate/execute", json={"parameters": {"expression": "(42 + 8) / 2"}}).json()
    assert calculation["result"]["result"] == 25
    injection = client.post("/api/skills/data.calculate/execute", json={"parameters": {"expression": "__import__('os').system('id')"}}).json()
    assert injection["ok"] is False


def test_file_skill_requires_confirmation_and_stays_in_sandbox(client: TestClient):
    parameters = {"path": "notas/arquitetura.md", "content": "# Núcleo\nSkill Python."}
    refused = client.post("/api/skills/files.write/execute", json={"parameters": parameters}).json()
    assert refused["error"]["code"] == "CONFIRMATION_REQUIRED"
    dry_run = client.post("/api/skills/files.write/execute", json={"parameters": parameters, "dryRun": True}).json()
    assert dry_run["result"]["wouldWrite"] == "notas/arquitetura.md"
    written = client.post("/api/skills/files.write/execute", json={"parameters": parameters, "confirmed": True}).json()
    assert written["ok"] is True
    read = client.post("/api/skills/files.read/execute", json={"parameters": {"path": "notas/arquitetura.md"}}).json()
    assert "Skill Python" in read["result"]["content"]
    traversal = client.post("/api/skills/files.read/execute", json={"parameters": {"path": "../../.env"}}).json()
    assert traversal["ok"] is False


def test_document_creation_requires_confirmation_and_supports_download(client: TestClient):
    parameters = {"format": "pdf", "path": "documentos/relatorio.pdf", "title": "Relatório", "content": "Texto com acentuação."}
    refused = client.post("/api/skills/document.create/execute", json={"parameters": parameters}).json()
    assert refused["error"]["code"] == "CONFIRMATION_REQUIRED"
    dry = client.post("/api/skills/document.create/execute", json={"parameters": parameters, "dryRun": True}).json()
    assert dry["ok"] is True and dry["result"]["dryRun"] is True
    created = client.post("/api/skills/document.create/execute", json={"parameters": parameters, "confirmed": True}).json()
    assert created["ok"] is True
    assert created["result"]["downloadUrl"].startswith("/api/files/download?path=")
    extracted = client.post("/api/skills/document.read/execute", json={"parameters": {"path": "documentos/relatorio.pdf"}}).json()
    assert "Texto com acentuação" in extracted["result"]["text"]
    downloaded = client.get(created["result"]["downloadUrl"])
    assert downloaded.status_code == 200
    assert downloaded.content.startswith(b"%PDF")
    assert "attachment" in downloaded.headers["content-disposition"]


def test_upload_is_confirmed_constrained_and_downloadable(client: TestClient):
    payload = b"%PDF-1.4\nconteudo de teste"
    refused = client.post("/api/files/upload", files={"upload": ("nota.pdf", payload, "application/pdf")}, data={"directory": "uploads"})
    assert refused.status_code == 400
    assert refused.json()["error"]["code"] == "CONFIRMATION_REQUIRED"
    uploaded = client.post("/api/files/upload", files={"upload": ("nota.pdf", payload, "application/pdf")}, data={"directory": "uploads", "confirmed": "true"})
    assert uploaded.status_code == 200
    assert uploaded.json()["path"] == "uploads/nota.pdf"
    downloaded = client.get(uploaded.json()["downloadUrl"])
    assert downloaded.content == payload
    invalid = client.post("/api/files/upload", files={"upload": ("../../.env", b"secret", "text/plain")}, data={"confirmed": "true"})
    assert invalid.status_code == 400
    traversal = client.get("/api/files/download?path=../../.env")
    assert traversal.status_code == 400


def test_engineering_skills_return_local_evidence_without_external_actions(client: TestClient):
    catalog = client.get("/api/skills").json()["skills"]
    engineering = [skill for skill in catalog if skill["id"].startswith("engineering.")]
    assert len(engineering) == 8
    assert all(not skill["sideEffects"] and not skill["requiresConfirmation"] for skill in engineering)
    review = client.post("/api/skills/engineering.review/execute", json={"parameters": {"code": "eval(entrada)", "language": "python"}}).json()
    assert review["ok"] is True
    assert review["result"]["counts"]["critical"] == 1
    assert review["result"]["codeExecuted"] is False
    vitals = client.post("/api/skills/engineering.webvitals/execute", json={"parameters": {"lcpMs": 2600, "inpMs": 180, "cls": 0.05, "source": "lab"}}).json()
    assert vitals["result"]["overall"] == "needs-improvement"
    assert vitals["result"]["measurementTaken"] is False
    invalid = client.post("/api/skills/engineering.plan/execute", json={"parameters": {"title": "   ", "requirements": "A", "testCommand": "npm test", "buildCommand": "npm run build"}}).json()
    assert invalid["ok"] is False
    assert invalid["error"]["code"] == "SKILL_ERROR"


def test_persistent_planning_requires_confirmation_and_recovers_bundle(client: TestClient):
    catalog = client.get("/api/skills").json()["skills"]
    planning = [skill for skill in catalog if skill["id"].startswith("planning.")]
    assert len(planning) == 5
    writes = [skill for skill in planning if skill["id"] in {"planning.create", "planning.update"}]
    assert all(skill["requiresConfirmation"] and skill["dryRunSupported"] for skill in writes)

    parameters = {
        "planId": "plano-api", "title": "Plano pela API", "goal": "Validar recuperação.",
        "phases": "Base | arquivos criados\nEntrega | gate verificado", "requirements": "Sem histórico externo",
    }
    refused = client.post("/api/skills/planning.create/execute", json={"parameters": parameters}).json()
    assert refused["error"]["code"] == "CONFIRMATION_REQUIRED"
    dry = client.post("/api/skills/planning.create/execute", json={"parameters": parameters, "dryRun": True}).json()
    assert dry["ok"] is True and len(dry["result"]["wouldWrite"]) == 3
    created = client.post("/api/skills/planning.create/execute", json={"parameters": parameters, "confirmed": True}).json()
    assert created["ok"] is True

    resumed = client.post("/api/skills/planning.resume/execute", json={"parameters": {"planId": "plano-api"}}).json()
    assert resumed["result"]["historyRead"] is False
    update = {
        "planId": "plano-api", "expectedSha256": resumed["result"]["sha256"],
        "phase": 1, "status": "complete", "nextStep": "", "evidence": "API E2E passou",
        "noteType": "test", "note": "Fluxo confirmado",
    }
    update_refused = client.post("/api/skills/planning.update/execute", json={"parameters": update}).json()
    assert update_refused["error"]["code"] == "CONFIRMATION_REQUIRED"
    update_dry = client.post("/api/skills/planning.update/execute", json={"parameters": update, "dryRun": True}).json()
    assert update_dry["result"]["dryRun"] is True
    updated = client.post("/api/skills/planning.update/execute", json={"parameters": update, "confirmed": True}).json()
    assert updated["ok"] is True and updated["result"]["currentPhase"] == 2
    downloaded = client.get(updated["result"]["downloadUrls"]["task_plan.md"])
    assert downloaded.status_code == 200
    assert "Status:** complete" in downloaded.text
    gate = client.post("/api/skills/planning.gate/execute", json={"parameters": {"planId": "plano-api"}}).json()
    assert gate["result"]["gate"]["complete"] is False
    assert gate["result"]["gate"]["commandsExecuted"] is False


def test_legal_skills_return_corpus_text_and_official_sources(client: TestClient):
    sources = client.post("/api/skills/legal.sources/execute", json={"parameters": {}}).json()
    assert sources["ok"] is True
    assert sources["result"]["documentCount"] == 8
    assert sources["result"]["articleCount"] > 4_000
    assert sources["result"]["upstream"]["commit"] == "15eb09b618ff08a38c4dfee06a91bd139d093f5d"

    article = client.post("/api/skills/legal.article/execute", json={
        "parameters": {"documentId": "cdc", "article": "49"},
    }).json()
    assert article["ok"] is True
    assert article["result"]["article"] == "Art. 49."
    assert "7 dias" in article["result"]["text"]
    assert article["result"]["source"].startswith(("https://www.planalto.gov.br/", "https://normas.leg.br/"))
    assert "informativo" in article["result"]["notice"].lower()

    search = client.post("/api/skills/legal.search/execute", json={
        "parameters": {"query": "arrependimento do consumidor", "documentId": "cdc", "limit": 3},
    }).json()
    assert search["ok"] is True
    assert search["result"]["results"][0]["article"] == "Art. 49."
    assert len(search["result"]["results"]) <= 3


def test_legal_skills_validate_document_article_and_limits(client: TestClient):
    missing = client.post("/api/skills/legal.article/execute", json={
        "parameters": {"documentId": "constituicao", "article": "9999"},
    }).json()
    assert missing["ok"] is False
    assert "não possui o artigo" in missing["error"]["message"]
    invalid_document = client.post("/api/skills/legal.search/execute", json={
        "parameters": {"query": "privacidade", "documentId": "desconhecido"},
    }).json()
    assert invalid_document["ok"] is False
    excessive_limit = client.post("/api/skills/legal.search/execute", json={
        "parameters": {"query": "privacidade", "limit": 99},
    }).json()
    assert excessive_limit["ok"] is False
    assert "Parâmetros inválidos" in excessive_limit["error"]["message"]


def test_ai_route_uses_provider_without_exposing_secrets(client: TestClient):
    status = client.get("/api/ai/status").json()
    assert status["configured"] is True
    response = client.post("/api/ai/chat", json={
        "message": "Explique o próximo passo",
        "history": [{"role": "user", "content": "Olá"}],
        "context": {"tasks": [{"title": "Revisar núcleo"}]},
    })
    assert response.status_code == 200
    assert response.json()["content"] == "Resposta externa de teste."
    assert client.provider.last_request.context["tasks"][0]["title"] == "Revisar núcleo"  # type: ignore[attr-defined]
    assert "api_key" not in response.text.lower()


def test_unconfigured_ai_is_explicit(tmp_path: Path):
    app = create_app(ai_provider=FakeProvider(False), registry=build_registry(tmp_path / "files"))
    with TestClient(app) as client:
        response = client.post("/api/ai/chat", json={"message": "Olá"})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "AI_NOT_CONFIGURED"
