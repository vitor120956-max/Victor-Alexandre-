from __future__ import annotations

import json
import os
import struct
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import reverse
from server.app import create_app
from server.skill_registry import build_registry


def _elf() -> bytes:
    header = b"\x7fELF" + bytes([2, 1, 1, 0]) + b"\x00" * 8
    header += struct.pack("<HHIQQQIHHHHHH", 2, 62, 1, 0x401000, 0, 64, 0, 64, 56, 0, 64, 3, 2)
    strings = b"\x00.text\x00.shstrtab\x00"
    text_offset = 64 + 3 * 64 + len(strings)
    sections = bytearray(3 * 64)
    struct.pack_into("<IIQQQQIIQQ", sections, 64, 1, 1, 6, 0x401000, text_offset, 4, 0, 0, 16, 0)
    struct.pack_into("<IIQQQQIIQQ", sections, 128, 7, 3, 0, 0, 256, len(strings), 0, 0, 1, 0)
    body = bytes(sections) + strings + b"\x90\x90\xc3\x00"
    return header + body


def _pe() -> bytes:
    data = bytearray(0x400)
    data[0:2] = b"MZ"
    struct.pack_into("<I", data, 0x3C, 0x80)
    data[0x80:0x84] = b"PE\x00\x00"
    struct.pack_into("<HHIIIHH", data, 0x84, 0x8664, 1, 0, 0, 0, 0xF0, 0x22)
    optional = 0x98
    struct.pack_into("<H", data, optional, 0x20B)
    struct.pack_into("<I", data, optional + 16, 0x1000)
    struct.pack_into("<Q", data, optional + 24, 0x140000000)
    struct.pack_into("<H", data, optional + 68, 3)
    struct.pack_into("<H", data, optional + 70, 0x140)
    struct.pack_into("<I", data, optional + 108, 16)
    struct.pack_into("<II", data, optional + 112 + 8, 0x1000, 0x28)
    struct.pack_into("<8sIIIIIIHHI", data, optional + 0xF0, b".text", 0x200, 0x1000, 0x200, 0x200, 0, 0, 0, 0, 0x60000020)
    struct.pack_into("<IIIII", data, 0x200, 0, 0, 0, 0x1080, 0x1100)
    struct.pack_into("<IIIII", data, 0x214, 0, 0, 0, 0, 0)
    data[0x280:0x280 + 13] = b"KERNEL32.dll\x00"
    struct.pack_into("<QQQ", data, 0x300, 1, 2, 0)
    return bytes(data)


def _root(tmp_path: Path) -> Path:
    return reverse.reverse_root(tmp_path / "files")


def _write(tmp_path: Path, relative: str, content: bytes) -> Path:
    path = _root(tmp_path) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _app(tmp_path: Path) -> TestClient:
    return TestClient(create_app(ai_provider=None, registry=build_registry(tmp_path / "files")))


def test_inspect_elf_reports_identity_and_sections(tmp_path: Path):
    _write(tmp_path, "amostra.elf", _elf())
    result = reverse.inspect_layout(tmp_path / "files", "amostra.elf")
    assert result["kind"] == "elf"
    assert result["identity"]["sha256"] == reverse.hashlib.sha256(_elf()).hexdigest()
    assert result["facts"]["machine"] == "x86-64"
    assert result["facts"]["sectionCount"] == 3
    assert {section["name"] for section in result["sections"]} >= {".text", ".shstrtab"}
    assert result["executed"] is False and result["readOnly"] is True
    assert any("estática" in limitation for limitation in result["limitations"])


def test_inspect_pe_reads_sections_and_imports(tmp_path: Path):
    _write(tmp_path, "amostra.exe", _pe())
    result = reverse.inspect_layout(tmp_path / "files", "amostra.exe")
    assert result["kind"] == "pe"
    assert result["facts"]["machine"] == "x86-64"
    assert result["facts"]["sectionCount"] == 1
    assert result["facts"]["aslr"] is True
    assert result["sections"][0]["name"] == ".text"
    assert result["imports"] == [{"library": "KERNEL32.dll", "functions": 2}]


def test_zip_inventory_detects_unsafe_names_without_extracting(tmp_path: Path):
    path = _root(tmp_path) / "pacote.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("app/main.js", "console.log('ok')")
        archive.writestr("../fuga.txt", "não extrair")
    result = reverse.inspect_layout(tmp_path / "files", "pacote.zip")
    assert result["kind"] == "zip"
    assert result["facts"]["entryCount"] == 2
    assert result["facts"]["unsafeEntryCount"] == 1
    assert any("nunca extrai" in finding["message"] for finding in result["findings"])
    assert not (path.parent.parent / "fuga.txt").exists()


def test_asar_and_wasm_are_parsed_with_bounded_metadata(tmp_path: Path):
    header = json.dumps({"files": {"main.js": {"size": 10, "offset": 0}}}).encode()
    _write(tmp_path, "app.asar", struct.pack("<I", 4) + struct.pack("<I", len(header)) + header + b"0123456789")
    asar = reverse.inspect_layout(tmp_path / "files", "app.asar")
    assert asar["kind"] == "asar"
    assert asar["entries"][0]["name"] == "main.js"

    payload = b"\x01\x01m\x01\x00\x01"
    _write(tmp_path, "modulo.wasm", b"\x00asm\x01\x00\x00\x00" + bytes([7, len(payload)]) + payload)
    wasm = reverse.inspect_layout(tmp_path / "files", "modulo.wasm")
    assert wasm["kind"] == "wasm"
    assert wasm["facts"]["exports"] == ["m"]
    assert wasm["facts"]["version"] == 1


def test_strings_supports_ascii_utf16_offsets_and_filter(tmp_path: Path):
    content = b"prefixo\x00hello world\x00" + "hello utf16".encode("utf-16le") + b"\x00\x00"
    _write(tmp_path, "bytes.bin", content)
    result = reverse.extract_strings(tmp_path / "files", "bytes.bin", min_length=5, encoding="both", limit=50)
    values = {item["value"]: item for item in result["items"]}
    assert "hello world" in values
    assert values["hello world"]["offset"] == content.index(b"hello world")
    assert any(item["encoding"] == "utf-16le" and "hello utf16" in item["value"] for item in result["items"])
    filtered = reverse.extract_strings(tmp_path / "files", "bytes.bin", min_length=5, encoding="both", limit=50, contains="WORLD")
    assert [item["value"] for item in filtered["items"]] == ["hello world"]
    limited = reverse.extract_strings(tmp_path / "files", "bytes.bin", min_length=5, encoding="both", limit=1)
    assert limited["truncated"] is True
    assert len(limited["items"]) == 1


def test_entropy_is_measured_per_block_and_validated(tmp_path: Path):
    _write(tmp_path, "aleatorio.bin", bytes(range(256)) * 32)
    high = reverse.byte_entropy(tmp_path / "files", "aleatorio.bin", 4096)
    assert high["fileEntropy"] == 8.0
    assert high["blockCount"] == 2
    assert {run["classification"] for run in high["runs"]} == {"high"}
    _write(tmp_path, "zeros.bin", b"\x00" * 8192)
    low = reverse.byte_entropy(tmp_path / "files", "zeros.bin", 4096)
    assert low["fileEntropy"] == 0.0
    assert {run["classification"] for run in low["runs"]} == {"low"}
    window = reverse.byte_entropy(tmp_path / "files", "aleatorio.bin", 512, offset=512, length=1024)
    assert window["window"] == {"offset": 512, "length": 1024}
    assert window["identity"]["bytes"] == 8192
    with pytest.raises(ValueError, match="bloco"):
        reverse.byte_entropy(tmp_path / "files", "aleatorio.bin", 1000)


def test_javascript_tree_maps_relationships_electron_and_unknowns(tmp_path: Path):
    _write(tmp_path, "app/package.json", json.dumps({"name": "demo", "main": "main.js", "dependencies": {"electron": "^30"}}).encode())
    _write(
        tmp_path,
        "app/main.js",
        b"const { BrowserWindow, ipcMain } = require('electron');\n"
        b"const helper = require('./helper');\n"
        b"const win = new BrowserWindow({ webPreferences: { preload: './preload.js', nodeIntegration: true } });\n"
        b"ipcMain.handle('ping', () => 'pong');\n"
        b"const dynamic = require(process.env.ALVO);\n"
        b"fetch('https://example.test/api');\n"
        b"app.get('/health', (req, res) => res.send('ok'));\n",
    )
    _write(tmp_path, "app/helper.js", b"export const help = 1;\n")
    _write(tmp_path, "app/preload.js", b"const { contextBridge, ipcRenderer } = require('electron');\ncontextBridge.exposeInMainWorld('api', { ping: () => ipcRenderer.invoke('ping') });\n")
    _write(tmp_path, "app/index.html", b'<script src="main.js"></script>')

    result = reverse.analyze_javascript(tmp_path / "files", "app")
    assert result["mode"] == "tree"
    assert result["executed"] is False
    assert {module["path"] for module in result["modules"]} == {"main.js", "helper.js", "preload.js"}
    assert {"from": "main.js", "to": "helper.js", "specifier": "./helper", "kind": "commonjs-require"} in result["relationships"]
    assert any(item["reason"] == "dynamic-require" for item in result["unresolved"])
    categories = {fact["category"] for fact in result["facts"]}
    assert {"electron.window", "electron.ipc-main", "electron.node-integration", "electron.preload", "electron.context-bridge"} <= categories
    assert result["package"]["name"] == "demo"
    assert result["routes"][0]["path"] == "/health"
    assert result["routes"][0]["authority"] == "static-candidate"
    assert any(entry["reason"] == "package.json main" for entry in result["entryCandidates"])
    assert result["limitations"]


def test_javascript_excludes_node_modules_and_follows_option(tmp_path: Path):
    _write(tmp_path, "projeto/main.js", b"require('lib');\n")
    _write(tmp_path, "projeto/node_modules/lib/index.js", b"module.exports = 1;\n")
    default = reverse.analyze_javascript(tmp_path / "files", "projeto")
    assert {module["path"] for module in default["modules"]} == {"main.js"}
    assert any(item["reason"] == "node_modules-excluded" for item in default["coverage"]["skipped"])
    included = reverse.analyze_javascript(tmp_path / "files", "projeto", include_node_modules=True)
    assert "node_modules/lib/index.js" in {module["path"] for module in included["modules"]}


def test_javascript_single_file_does_not_walk_siblings_and_inline_is_inert(tmp_path: Path):
    _write(tmp_path, "projeto/alvo.js", b"import './outro';\n")
    _write(tmp_path, "projeto/outro.js", b"export const x = 1;\n")
    _write(tmp_path, "projeto/irmao.js", b"eval('nunca executado');\n")
    single = reverse.analyze_javascript(tmp_path / "files", "projeto/alvo.js")
    assert single["mode"] == "file"
    assert [module["path"] for module in single["modules"]] == ["alvo.js"]
    inline = reverse.analyze_javascript(tmp_path / "files", "", source="import ausente from './x';\nimport('./dinamico');\neval('x');\n")
    assert inline["mode"] == "inline"
    assert {item["reason"] for item in inline["unresolved"]} == {"inline-no-resolution", "dynamic-import"}
    assert "javascript.eval" in {fact["category"] for fact in inline["facts"]}
    with pytest.raises(ValueError, match="exatamente um"):
        reverse.analyze_javascript(tmp_path / "files", "projeto/alvo.js", source="x")
    with pytest.raises(ValueError, match="exatamente um"):
        reverse.analyze_javascript(tmp_path / "files", "")


def test_symlinks_cannot_escape_the_reverse_area(tmp_path: Path):
    outside = tmp_path / "fora"
    outside.mkdir()
    (outside / "segredo.js").write_text("export const segredo = 1;\n")
    tree = _root(tmp_path) / "app"
    tree.mkdir(parents=True)
    (tree / "main.js").write_text("const x = 1;\n")
    try:
        (tree / "link.js").symlink_to(outside / "segredo.js")
        (tree / "pasta").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("o sistema de arquivos não permite symlinks")
    result = reverse.analyze_javascript(tmp_path / "files", "app")
    assert {module["path"] for module in result["modules"]} == {"main.js"}
    with pytest.raises(ValueError):
        reverse.inspect_artifact(tmp_path / "files", "app/link.js")


def test_compare_is_static_and_never_claims_equivalence(tmp_path: Path):
    _write(tmp_path, "antes.bin", b"\x00alpha-beta-gamma\x00comum\x00")
    _write(tmp_path, "depois.bin", b"\x00alpha-delta-gamma\x00comum\x00")
    result = reverse.compare_artifacts(tmp_path / "files", "antes.bin", "depois.bin")
    assert result["identical"] is False
    assert "alpha-delta-gamma" in result["strings"]["added"]
    assert "alpha-beta-gamma" in result["strings"]["removed"]
    assert any("não são prova" in limitation for limitation in result["limitations"])
    _write(tmp_path, "copia.bin", b"\x00alpha-beta-gamma\x00comum\x00")
    identical = reverse.compare_artifacts(tmp_path / "files", "antes.bin", "copia.bin")
    assert identical["identical"] is True
    assert any("idênticos" in limitation for limitation in identical["limitations"])


def test_tree_digest_describes_content_not_its_location(tmp_path: Path):
    for folder in ("copia-a", "copia-b"):
        _write(tmp_path, f"{folder}/main.js", b"import './lib';\n")
        _write(tmp_path, f"{folder}/lib.js", b"export const x = 1;\n")
    first = reverse.analyze_javascript(tmp_path / "files", "copia-a")
    second = reverse.analyze_javascript(tmp_path / "files", "copia-b")
    assert first["target"]["sha256"] == second["target"]["sha256"]
    assert first["target"]["digestScope"] == "analyzed-content"
    _write(tmp_path, "copia-b/lib.js", b"export const x = 2;\n")
    changed = reverse.analyze_javascript(tmp_path / "files", "copia-b")
    assert changed["target"]["sha256"] != first["target"]["sha256"]


def test_paths_are_confined_and_hidden_or_unknown_artifacts_are_refused(tmp_path: Path):
    _write(tmp_path, "ok.bin", b"dados")
    for value in ("../ok.bin", "/etc/passwd", ".oculto", "nao-existe.bin", "script.sh"):
        with pytest.raises(ValueError):
            reverse.inspect_artifact(tmp_path / "files", value)


def test_api_upload_list_download_and_execute(tmp_path: Path):
    with _app(tmp_path) as client:
        refused = client.post("/api/reverse/upload", files={"upload": ("amostra.bin", b"hello")}, data={"directory": "", "confirmed": "false"})
        assert refused.status_code == 400
        assert refused.json()["error"]["code"] == "CONFIRMATION_REQUIRED"
        invalid = client.post("/api/reverse/upload", files={"upload": ("script.sh", b"echo")}, data={"directory": "", "confirmed": "true"})
        assert invalid.status_code == 400
        uploaded = client.post(
            "/api/reverse/upload",
            files={"upload": ("app.js", b"import './x';\nconsole.log('ok');\n")},
            data={"directory": "projeto", "confirmed": "true"},
        )
        assert uploaded.status_code == 200
        assert uploaded.json()["path"] == "projeto/app.js"
        listing = client.get("/api/reverse/files").json()
        assert listing["count"] == 1
        assert listing["artifacts"][0]["kind"] == "javascript-source"
        download = client.get("/api/reverse/download", params={"path": "projeto/app.js"})
        assert download.status_code == 200
        assert download.headers["content-type"] == "application/octet-stream"
        assert "attachment" in download.headers["content-disposition"]
        assert client.get("/api/reverse/download", params={"path": "../app.js"}).status_code == 400
        traversal = client.post(
            "/api/reverse/upload",
            files={"upload": ("app.js", b"x")},
            data={"directory": "../fora", "confirmed": "true"},
        )
        assert traversal.status_code == 400


def test_api_executes_reverse_features_without_side_effects(tmp_path: Path):
    _write(tmp_path, "amostra.elf", _elf())
    with _app(tmp_path) as client:
        health = client.get("/api/health").json()
        assert health["version"] == "0.17.0"
        assert health["skills"] == 93
        catalog = {skill["id"]: skill for skill in client.get("/api/skills").json()["skills"]}
        assert len([skill for skill in catalog if skill.startswith("reverse.")]) == 6
        assert catalog["reverse.javascript"]["requiresConfirmation"] is False
        inspected = client.post("/api/skills/reverse.inspect/execute", json={"parameters": {"path": "amostra.elf"}}).json()
        assert inspected["ok"] is True
        assert inspected["result"]["executed"] is False
        assert inspected["result"]["identity"]["sha256"] == reverse.hashlib.sha256(_elf()).hexdigest()
        invalid_block = client.post(
            "/api/skills/reverse.entropy/execute",
            json={"parameters": {"path": "amostra.elf", "blockSize": 1000}},
        ).json()
        assert invalid_block["ok"] is False
        dry_run = client.post("/api/skills/reverse.strings/execute", json={"parameters": {"path": "amostra.elf"}, "dryRun": True}).json()
        assert dry_run["ok"] is False
        for path in ({"path": "../amostra.elf"}, {"path": ""}):
            refused = client.post("/api/skills/reverse.inspect/execute", json={"parameters": path}).json()
            assert refused["ok"] is False
