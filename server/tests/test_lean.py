"""Testes da engenharia enxuta inspirada em DietrichGebert/ponytail (MIT).

Toda a análise é estática: nenhum trecho avaliado é executado e nenhuma pasta
fora da área isolada do JARVIS é lida.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server.app import create_app
from server.lean import LeanError, audit_tree, evaluate_ladder, harvest_debt, review_change
from server.skill_registry import build_registry


@pytest.fixture()
def client(tmp_path):
    registry = build_registry(tmp_path / "files")
    app = create_app(registry=registry)
    with TestClient(app) as test_client:
        test_client.files_root = tmp_path / "files"  # type: ignore[attr-defined]
        yield test_client


def test_ladder_uses_the_platform_instead_of_installing_a_dependency() -> None:
    result = evaluate_ladder(
        task="adicionar seletor de data",
        stdlib_fit="full",
        stdlib_evidence="input type=date",
        estimated_lines=4,
    )

    assert result["executed"] is False
    assert result["readOnly"] is True
    assert result["decision"]["rung"] == 3
    assert result["decision"]["key"] == "platform"
    assert [rung["status"] for rung in result["rungs"]][:3] == ["clear", "skipped", "holds"]
    assert result["testObligation"]["required"] is False
    assert result["executed"] is False


def test_ladder_stops_at_reuse_and_counts_lines_and_scope() -> None:
    result = evaluate_ladder(
        task="formatar data de entrega",
        reuse_fit="full",
        reuse_evidence="src/lib/date.ts",
        estimated_lines=30,
        unrequested="opção de tema escuro\natalhos de teclado",
        reach="pedidos.ts\nnotaFiscal.ts",
    )

    assert result["decision"]["rung"] == 2
    assert result["outOfScope"][0] == "opção de tema escuro"
    assert result["reach"][0] == "pedidos.ts"
    assert result["rungs"][0]["status"] == "cut"
    assert result["warnings"] == []


def test_ladder_requires_a_task_and_a_test_for_risky_logic() -> None:
    with pytest.raises(LeanError, match="Descreva"):
        evaluate_ladder(task="   ", estimated_lines=3)

    risky = evaluate_ladder(
        task="calcular desconto",
        reuse_fit="full",
        reuse_evidence="src/money.ts",
        estimated_lines=3,
        proposal="if (total > 0) return total * rate;",
    )
    assert risky["testObligation"]["required"] is True
    assert "if" in risky["testObligation"]["riskySignals"]


def test_ladder_ultra_questions_scope_and_one_liner_is_legitimate() -> None:
    ultra = evaluate_ladder(task="adicionar tela de relatórios", mode="ultra", estimated_lines=40)
    assert ultra["questions"]
    assert ultra["testObligation"]["required"] is False

    one_liner = evaluate_ladder(task="ordenar lista", one_liner=True, estimated_lines=1)
    assert one_liner["decision"]["key"] == "one_liner"


def test_review_detects_new_risk() -> None:
    diff = (
        "--- a/src/app.js\n"
        "+++ b/src/app.js\n"
        "@@ -1,2 +1,2 @@\n"
        "-const ok = validate(x);\n"
        "+const ok = eval(x);\n"
    )
    result = review_change(diff=diff)

    kinds = [finding["kind"] for finding in result["findings"]]
    assert "risk:eval" in kinds
    assert result["findings"][0]["group"] == "must"
    assert "produção" in result["findings"][0]["ifSkipped"].lower()
    assert result["addedLines"] == 1


def test_review_requires_a_test_only_for_risky_logic() -> None:
    diff = (
        "--- a/src/clamp.js\n"
        "+++ b/src/clamp.js\n"
        "@@ -0,0 +1,2 @@\n"
        "+export const clamp = (value, max) => {\n"
        "+  if (value > max) return max;\n"
        "+  return Math.min(Math.max(value, 0), max);\n"
        "+};\n"
    )
    result = review_change(diff=diff)
    kinds = [finding["kind"] for finding in result["findings"]]
    assert "missing-test" in kinds
    assert "manual:clamp" in kinds


def test_review_detects_removed_guardrail_and_platform_reimplementation() -> None:
    diff = (
        "--- a/src/session.js\n"
        "+++ b/src/session.js\n"
        "@@ -4,2 +4,2 @@\n"
        "-const ok = await validate(token);\n"
        "+const ok = true;\n"
    )
    result = review_change(diff=diff)
    kinds = [finding["kind"] for finding in result["findings"]]
    assert "removed-guardrail" in kinds

    manual = review_change(diff="+export const clamp = (value, max) => Math.min(Math.max(value, 0), max);")
    assert "manual:clamp" in [finding["kind"] for finding in manual["findings"]]


def test_review_detects_new_dependency_and_duplication() -> None:
    dependency = (
        "--- a/package.json\n"
        "+++ b/package.json\n"
        "@@ -10,0 +11,1 @@\n"
        '+    "left-pad": "^1.3.0",\n'
    )
    assert "new-dependency" in [finding["kind"] for finding in review_change(diff=dependency)["findings"]]

    block = [f"  const item{i} = collection[{i}];" for i in range(6)]
    clone = (
        "--- a/src/one.js\n"
        "+++ b/src/one.js\n"
        "@@ -0,0 +1,6 @@\n"
        + "".join(f"+{line}\n" for line in block)
        + "--- a/src/two.js\n"
        "+++ b/src/two.js\n"
        "@@ -0,0 +1,6 @@\n"
        + "".join(f"+{line}\n" for line in block)
    )
    assert "duplication" in [finding["kind"] for finding in review_change(diff=clone)["findings"]]


def test_review_detects_single_use_wrapper_and_unused_config() -> None:
    wrapper = (
        "--- a/src/service.ts\n"
        "+++ b/src/service.ts\n"
        "@@ -0,0 +1,1 @@\n"
        "+export function load(id: string) { return repository.find(id); }\n"
    )
    assert "single-use-wrapper" in [finding["kind"] for finding in review_change(diff=wrapper)["findings"]]

    config = (
        "--- a/src/config.ts\n"
        "+++ b/src/config.ts\n"
        "@@ -0,0 +1,2 @@\n"
        "+export const endpoint = process.env.LEGACY_ENDPOINT;\n"
        "+interface Store { save(): void; }\n"
    )
    result = review_change(diff=config)
    kinds = [finding["kind"] for finding in result["findings"]]
    assert "unused-config" in kinds
    assert "yagni" in kinds


def test_review_supports_pasted_snippets_and_limits() -> None:
    snippet = review_change(diff="function run(input) {\n  return eval(input);\n}", mode="ultra")
    assert snippet["input"] == "snippet"
    assert {finding["kind"] for finding in snippet["findings"]} >= {"risk:eval"}

    with pytest.raises(LeanError, match="linhas"):
        review_change(diff="   \n\n")

    with pytest.raises(LeanError, match="200.000"):
        review_change(diff="+x\n" * 70_000)


def test_review_lite_hides_should_and_nice_findings() -> None:
    diff = (
        "--- a/src/a.js\n"
        "+++ b/src/a.js\n"
        "@@ -0,0 +1,3 @@\n"
        "+const clone = JSON.parse(JSON.stringify(source));\n"
        "+export const limit = Math.min(Math.max(value, 0), max);\n"
        "+export function load(id) { return repository.find(id); }\n"
    )
    full = review_change(diff=diff)
    lite = review_change(diff=diff, mode="lite")
    assert full["counts"]["must"] == 0
    assert full["counts"]["should"] >= 3
    assert lite["counts"]["must"] == 0
    assert lite["findings"] == []


def test_debt_reads_markers_from_comments_only() -> None:
    code = (
        "### src/cache.js\n"
        "// shortcut: cache em memória, revisar com 100 usuários\n"
        "// shortcut: sem paginação, quando a tabela passar de 10k linhas\n"
        "// ponytail: sem retry, depois\n"
        "// a keyboard shortcut: Ctrl+K\n"
        "// shortcut: sem validação, revisar depois\n"
        "function load() { return keyboardShortcut; }\n"
    )
    result = harvest_debt(files_root=None, code=code)

    assert result["executed"] is False
    assert result["totals"] == {"markers": 4, "noTrigger": 2, "files": 1}
    assert [row["file"] for row in result["rows"]] == ["src/cache.js"] * 4
    assert result["rows"][2]["legacy"] is True
    assert result["rows"][2]["noTrigger"] is True
    assert result["rows"][3]["upgrade"] == "revisar depois"

    without_legacy = harvest_debt(files_root=None, code=code, include_legacy=False)
    assert without_legacy["totals"]["markers"] == 3


def test_debt_walks_a_tree_and_skips_machinery(tmp_path) -> None:
    files_root = tmp_path / "files"
    (files_root / "reverse" / "app" / "src").mkdir(parents=True)
    (files_root / "reverse" / "app" / "node_modules" / "lib").mkdir(parents=True)
    (files_root / "reverse" / "app" / "src" / "a.js").write_text(
        "// shortcut: sem cache, revisar com 50 usuários\n", encoding="utf-8"
    )
    (files_root / "reverse" / "app" / "node_modules" / "lib" / "index.js").write_text(
        "// shortcut: dívida de terceiros\n", encoding="utf-8"
    )

    result = harvest_debt(files_root=files_root, code="", path="app")

    assert result["source"] == "tree"
    assert result["totals"]["markers"] == 1
    assert [row["file"] for row in result["rows"]] == ["src/a.js"]
    assert result["coverage"]["filesScanned"] == 1


def test_debt_requires_exactly_one_source_and_a_simple_marker(tmp_path) -> None:
    files_root = tmp_path / "files"
    (files_root / "reverse" / "app").mkdir(parents=True)

    with pytest.raises(LeanError, match="exatamente uma"):
        harvest_debt(files_root=files_root, code="// shortcut: x, y", path="app")
    with pytest.raises(LeanError, match="marcador"):
        harvest_debt(files_root=None, code="// shortcut: x, y", marker="../etc")
    empty = harvest_debt(files_root=files_root, code="", path="app")
    assert empty["totals"] == {"markers": 0, "noTrigger": 0, "files": 0}


def test_audit_inventories_and_flags_risky_untested_code(tmp_path) -> None:
    files_root = tmp_path / "files"
    (files_root / "reverse" / "app" / "src").mkdir(parents=True)
    (files_root / "reverse" / "app" / "src" / "main.py").write_text(
        "from flask import Flask\napp = Flask(__name__)\n\n@app.get('/x')\ndef run(value):\n    return eval(value)\n",
        encoding="utf-8",
    )
    (files_root / "reverse" / "app" / "src" / "main_test.py").write_text(
        "from main import run\n\ndef test_run():\n    assert run('1') == 1\n", encoding="utf-8"
    )
    (files_root / "reverse" / "app" / "src" / "helper.py").write_text(
        "# shortcut: sem tratamento, revisar depois\ndef helper(v):\n    if v:\n        return 1\n    return 0\n",
        encoding="utf-8",
    )

    result = audit_tree(files_root=files_root, path="app")

    assert result["inventory"]["files"] == 3
    assert result["inventory"]["testFiles"] == 1
    assert result["counts"]["must"] >= 1
    kinds = [finding["kind"] for finding in result["findings"]]
    assert kinds[0] == "risk:eval"
    assert "missing-test" in kinds
    assert result["debt"]["markers"] == 1
    assert result["executed"] is False
    assert result["readOnly"] is True


def test_audit_respects_the_file_limit_and_ignores_symlinks(tmp_path) -> None:
    files_root = tmp_path / "files"
    root = files_root / "reverse" / "many"
    root.mkdir(parents=True)
    for index in range(5):
        (root / f"f{index}.py").write_text("def run():\n    return 1\n", encoding="utf-8")

    limited = audit_tree(files_root=files_root, path="many", max_files=10)
    assert limited["inventory"]["files"] == 5
    assert limited["coverage"]["limitReached"] is False

    (root / "link.py").symlink_to(root / "f0.py")
    linked = audit_tree(files_root=files_root, path="many", max_files=10)
    assert linked["inventory"]["files"] == 5


def test_audit_confines_paths_to_the_code_area(tmp_path) -> None:
    files_root = tmp_path / "files"
    (files_root / "reverse" / "vazia").mkdir(parents=True)

    with pytest.raises(LeanError, match="inválido"):
        audit_tree(files_root=files_root, path="../../etc")
    with pytest.raises(LeanError, match="pasta de código"):
        audit_tree(files_root=files_root, path="   ")
    with pytest.raises(LeanError, match="Nenhum arquivo"):
        audit_tree(files_root=files_root, path="vazia")


def test_api_lists_and_executes_lean_skills(client: TestClient) -> None:
    catalog = client.get("/api/skills").json()["skills"]
    lean_skills = {skill["id"]: skill for skill in catalog if skill["id"].startswith("lean.")}
    assert set(lean_skills) == {"lean.ladder", "lean.review", "lean.audit", "lean.debt"}
    assert all(skill["runtime"] == "python" for skill in lean_skills.values())
    assert all(skill["sideEffects"] is False for skill in lean_skills.values())

    ladder = client.post(
        "/api/skills/lean.ladder/execute",
        json={"parameters": {"task": "adicionar seletor de data", "stdlibFit": "full", "stdlibEvidence": "input type=date", "estimatedLines": 4}},
    )
    assert ladder.status_code == 200
    body = ladder.json()
    assert body["ok"] is True
    assert body["result"]["decision"]["key"] == "platform"
    assert body["result"]["executed"] is False


def test_api_rejects_invalid_lean_parameters(client: TestClient) -> None:
    invalid_mode = client.post("/api/skills/lean.ladder/execute", json={"parameters": {"task": "tarefa", "mode": "turbo"}})
    assert invalid_mode.status_code == 200
    assert invalid_mode.json()["ok"] is False
    assert "mode" in invalid_mode.json()["error"]["message"]

    traversal = client.post("/api/skills/lean.audit/execute", json={"parameters": {"path": "../fora"}})
    assert traversal.json()["ok"] is False
    assert "inválido" in traversal.json()["error"]["message"]

    missing_task = client.post("/api/skills/lean.ladder/execute", json={"parameters": {}})
    assert missing_task.json()["ok"] is False
    assert "task" in missing_task.json()["error"]["message"]


def test_api_audit_reads_the_code_area_without_writing(client: TestClient) -> None:
    root = client.files_root / "reverse" / "api"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.js").write_text(
        "// shortcut: sem cache, revisar com 100 usuários\nconst total = eval(input);\n", encoding="utf-8"
    )

    response = client.post("/api/skills/lean.audit/execute", json={"parameters": {"path": "api", "maxFiles": 50}})
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["inventory"]["files"] == 1
    assert result["debt"]["markers"] == 1
    assert result["counts"]["must"] >= 1
    assert {finding["kind"] for finding in result["findings"]} >= {"risk:eval"}
    assert result["inventory"]["codeFiles"] == 1


def test_api_debt_uses_the_shared_isolated_area(client: TestClient) -> None:
    root = client.files_root / "reverse" / "debt"
    root.mkdir(parents=True)
    (root / "a.js").write_text("// shortcut: sem retry, revisar depois\n", encoding="utf-8")

    response = client.post("/api/skills/lean.debt/execute", json={"parameters": {"path": "debt", "marker": "shortcut"}})
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["totals"] == {"markers": 1, "noTrigger": 1, "files": 1}
    assert result["rows"][0]["legacy"] is False
