"""Análise estática de artefatos inspirada em morluto/rea (MIT).

Este módulo lê bytes e texto de arquivos confinados e devolve fatos com
identidade SHA-256, cobertura e limitações. Ele nunca importa, executa,
descompacta em disco ou abre um artefato como biblioteca; nenhum processo,
socket ou shell é criado. Formatos não reconhecidos são tratados apenas como
bytes: identidade, entropia e strings continuam disponíveis.

Implementação própria baseada nos contratos públicos do REA (evidência,
autoridade e limite declarados), sem copiar código do upstream.
"""
from __future__ import annotations

import bisect
import hashlib
import os
import json
import math
import re
import struct
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

from .workspace import safe_path

ARTIFACT_EXTENSIONS = {
    ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".json", ".map", ".html", ".htm",
    ".css", ".wasm", ".elf", ".macho", ".o", ".obj", ".bin", ".so", ".dylib", ".dll", ".exe",
    ".apk", ".aar", ".jar", ".zip", ".asar", ".ipa", ".dmg", ".msix", ".har", ".pcap",
    ".py", ".pyc", ".beam", ".gguf", ".safetensors", ".onnx",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".txt", ".md", ".log", ".hbc",
    ".dex", ".class", ".pack", ".dat", ".img", ".rom",
}
JAVASCRIPT_EXTENSIONS = {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx"}
TEXT_ARTIFACT_EXTENSIONS = {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".py", ".json", ".map", ".html", ".htm", ".css", ".txt", ".md", ".log"}
MAX_ARTIFACT_BYTES = 25_000_000
MAX_JS_FILES = 2000
MAX_JS_TOTAL_BYTES = 8_000_000
MAX_JS_FILE_BYTES = 1_500_000
MAX_ARCHIVE_ENTRIES = 2000
MAX_STRINGS = 1000
MAX_LAYOUT_ROWS = 512
ENTROPY_HIGH = 7.2
ENTROPY_LOW = 1.0

_ELF_MACHINES = {
    3: "x86", 8: "MIPS", 20: "PowerPC", 21: "PowerPC64", 40: "ARM", 62: "x86-64",
    183: "AArch64", 243: "RISC-V", 247: "BPF",
}
_PE_MACHINES = {
    0x014C: "x86", 0x8664: "x86-64", 0x01C0: "ARM", 0xAA64: "ARM64",
    0x0200: "IA-64", 0x01C4: "ARMv7",
}
_MACHO_CPUS = {
    7: "x86", 0x01000007: "x86-64", 12: "ARM", 0x0100000C: "ARM64",
    18: "PowerPC", 0x01000012: "PowerPC64",
}
_PYC_VERSIONS = {3394: "3.7", 3413: "3.8", 3425: "3.9", 3439: "3.10", 3495: "3.11", 3531: "3.12", 3571: "3.13"}
_WASM_SECTIONS = {
    0: "custom", 1: "type", 2: "import", 3: "function", 4: "table", 5: "memory",
    6: "global", 7: "export", 8: "start", 9: "element", 10: "code", 11: "data",
    12: "data-count", 13: "tag",
}
_NODE_BUILTINS = {
    "assert", "buffer", "child_process", "cluster", "console", "constants", "crypto",
    "dgram", "diagnostics_channel", "dns", "domain", "events", "fs", "http", "http2",
    "https", "inspector", "module", "net", "os", "path", "perf_hooks", "process",
    "punycode", "querystring", "readline", "repl", "stream", "string_decoder", "sys",
    "timers", "tls", "trace_events", "tty", "url", "util", "v8", "vm", "wasi",
    "worker_threads", "zlib",
}

_FACT_PATTERNS: tuple[tuple[str, str, re.Pattern[str], str], ...] = (
    ("electron.window", "BrowserWindow", re.compile(r"\bBrowserWindow\b"), "info"),
    ("electron.preload", "preload declarado", re.compile(r"\bpreload\s*:\s*(['\"])(?P<value>[^'\"\n]+)\1"), "info"),
    ("electron.context-bridge", "contextBridge.exposeInMainWorld", re.compile(r"\bcontextBridge\s*\.\s*exposeInMainWorld\b"), "info"),
    ("electron.ipc-main", "ipcMain", re.compile(r"\bipcMain\s*\.\s*(?:on|handle|once|removeHandler)\b"), "info"),
    ("electron.ipc-renderer", "ipcRenderer", re.compile(r"\bipcRenderer\s*\.\s*(?:send|invoke|on|postMessage)\b"), "info"),
    ("electron.node-integration", "nodeIntegration habilitado", re.compile(r"\bnodeIntegration\s*:\s*true\b"), "attention"),
    ("electron.context-isolation", "contextIsolation desabilitado", re.compile(r"\bcontextIsolation\s*:\s*false\b"), "attention"),
    ("electron.sandbox", "sandbox desabilitado", re.compile(r"\bsandbox\s*:\s*false\b"), "attention"),
    ("node.child-process", "child_process", re.compile(r"\brequire\s*\(\s*['\"](?:node:)?child_process['\"]\s*\)"), "attention"),
    ("javascript.eval", "eval", re.compile(r"\beval\s*\("), "attention"),
    ("javascript.new-function", "new Function", re.compile(r"\bnew\s+Function\s*\("), "attention"),
    ("native.addon-reference", "referência a .node", re.compile(r"['\"][^'\"\n]+\.node['\"]"), "info"),
    ("native.dlopen", "process.dlopen", re.compile(r"\bprocess\s*\.\s*dlopen\s*\("), "info"),
    ("electron.open-external", "shell.openExternal", re.compile(r"\bshell\s*\.\s*openExternal\b"), "info"),
)
_IMPORT_RE = re.compile(r"\bimport\b(?!\s*[.(])(?P<body>[^;'\"`]{0,500}?)(?:\bfrom\s*)?(['\"])(?P<spec>[^'\"\n]+)\2", re.S)
_EXPORT_FROM_RE = re.compile(r"\bexport\b[^;'\"`]{0,500}?\bfrom\s*(['\"])(?P<spec>[^'\"\n]+)\1", re.S)
_REQUIRE_RE = re.compile(r"\brequire\s*\(\s*(['\"])(?P<spec>[^'\"\n]+)\1\s*\)")
_DYNAMIC_IMPORT_LITERAL_RE = re.compile(r"\bimport\s*\(\s*(['\"])(?P<spec>[^'\"\n]+)\1\s*\)")
_DYNAMIC_IMPORT_RE = re.compile(r"\bimport\s*\(\s*(?!['\"])")
_DYNAMIC_REQUIRE_RE = re.compile(r"\brequire\s*\(\s*(?!['\"])")
_ROUTE_RE = re.compile(r"\b(?:app|router|server)\s*\.\s*(get|post|put|patch|delete|use)\s*\(\s*(['\"])(?P<path>/[^'\"\n]*)\2")
_FETCH_RE = re.compile(r"\bfetch\s*\(\s*(['\"])(?P<url>https?://[^'\"\n]+)\1")
_SOURCE_MAP_RE = re.compile(r"[#@]\s*sourceMappingURL=([^\s*]+)")
_HTML_SCRIPT_RE = re.compile(r"<script\b[^>]*\bsrc\s*=\s*(['\"])(?P<src>[^'\"\n]+)\1", re.I)
_HTML_LINK_RE = re.compile(r"<link\b[^>]*\bhref\s*=\s*(['\"])(?P<href>[^'\"\n]+)\1", re.I)

_LIMITATIONS = (
    "Somente análise estática: nenhum byte do artefato é executado, importado ou carregado como biblioteca.",
    "O SHA-256 identifica o snapshot lido; ele não prova autoria, assinatura ou confiança.",
    "Fatos ausentes não provam ausência: a cobertura é limitada ao arquivo ou à árvore selecionada.",
)
_JAVASCRIPT_LIMITATIONS = (
    "Importações e fatos são extraídos por expressões regulares, sem AST, resolução de bundler ou execução.",
    "Pacotes de node_modules e especificadores remotos não são seguidos nem baixados.",
    "Source maps não são expandidos; caminhos e rotas são candidatos estáticos, não comportamento observado.",
    "Análise JavaScript não examina binários nativos referenciados, mesmo quando o arquivo .node foi enviado.",
)


class ReverseError(ValueError):
    """Erro esperado de análise, seguro para apresentar ao usuário."""


def reverse_root(files_root: Path) -> Path:
    root = files_root.resolve() / "reverse"
    root.mkdir(parents=True, exist_ok=True)
    return root


def artifact_file(files_root: Path, relative: str) -> Path:
    root = reverse_root(files_root)
    try:
        path = safe_path(root, relative)
    except ValueError as exc:
        raise ReverseError(str(exc)) from exc
    if path.suffix.lower() not in ARTIFACT_EXTENSIONS:
        raise ReverseError("Formato de artefato não permitido. Use a área de engenharia reversa com um arquivo suportado.")
    if not path.is_file() or path.is_symlink():
        raise ReverseError("Artefato não encontrado na área de engenharia reversa.")
    size = path.stat().st_size
    if size <= 0:
        raise ReverseError("O artefato está vazio.")
    if size > MAX_ARTIFACT_BYTES:
        raise ReverseError("O artefato excede o limite de 25 MB.")
    return path


def artifact_directory(files_root: Path, relative: str) -> Path:
    root = reverse_root(files_root)
    if not relative.strip():
        raise ReverseError("Informe uma pasta de artefatos.")
    try:
        path = safe_path(root, relative)
    except ValueError as exc:
        raise ReverseError(str(exc)) from exc
    if not path.is_dir() or path.is_symlink():
        raise ReverseError("A árvore informada não existe na área de engenharia reversa.")
    return path


def list_artifacts(files_root: Path) -> dict[str, Any]:
    root = reverse_root(files_root)
    items: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if len(items) >= 500:
            break
        if path.is_symlink() or not path.is_file() or path.suffix.lower() not in ARTIFACT_EXTENSIONS:
            continue
        relative = path.relative_to(root)
        if any(part.startswith(".") for part in relative.parts):
            continue
        stat = path.stat()
        if stat.st_size <= 0 or stat.st_size > MAX_ARTIFACT_BYTES:
            continue
        with path.open("rb") as handle:
            head = handle.read(64)
        kind, label = detect_format(head, path.suffix.lower())
        items.append({
            "path": relative.as_posix(),
            "bytes": stat.st_size,
            "kind": kind,
            "format": label,
            "downloadUrl": f"/api/reverse/download?path={quote(relative.as_posix(), safe='')}",
        })
    return {"root": "Área de engenharia reversa", "artifacts": items, "count": len(items), "limit": 500}


def _read(path: Path) -> bytes:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ReverseError("Não foi possível ler o artefato solicitado.") from exc
    if len(data) == 0:
        raise ReverseError("O artefato está vazio.")
    return data


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _unpack(data: bytes, fmt: str, offset: int, label: str) -> tuple[Any, ...]:
    size = struct.calcsize(fmt)
    if offset < 0 or offset + size > len(data):
        raise ReverseError(f"Registro {label} fora dos limites do arquivo; o artefato pode estar truncado ou malformado.")
    return struct.unpack_from(fmt, data, offset)


def _cstring(data: bytes, offset: int, limit: int = 4096) -> str:
    if offset < 0 or offset >= len(data):
        raise ReverseError("Ponteiro de texto fora dos limites do arquivo.")
    end = data.find(b"\x00", offset, min(len(data), offset + limit))
    if end < 0:
        end = min(len(data), offset + limit)
    return data[offset:end].decode("utf-8", "replace")


def _entropy(counts: Any, total: int) -> float:
    if total <= 0:
        return 0.0
    value = 0.0
    for count in counts:
        if count:
            probability = count / total
            value -= probability * math.log2(probability)
    return round(value, 4)


def _byte_entropy(chunk: bytes) -> float:
    return _entropy(Counter(chunk).values(), len(chunk))


def _is_probably_text(head: bytes) -> bool:
    if not head:
        return False
    if b"\x00" in head:
        return False
    controls = sum(1 for byte in head if byte < 9 or 13 < byte < 32)
    return controls <= max(1, len(head) // 100)


def detect_format(head: bytes, suffix: str = "") -> tuple[str, str]:
    """Identifica o contêiner pelos bytes; a extensão é apenas uma dica secundária."""
    if head[:4] == b"\x7fELF" and len(head) >= 20:
        bits = "64" if head[4] == 2 else "32" if head[4] == 1 else "?"
        endian = "little-endian" if head[5] == 1 else "big-endian" if head[5] == 2 else "?"
        return "elf", f"ELF{bits} {endian}"
    if head[:2] == b"MZ":
        return "pe", "PE / DOS"
    if head[:4] in {b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe"}:
        return "mach-o", "Mach-O"
    if head[:4] in {b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca", b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca"}:
        order = "big" if head[:4] in {b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"} else "little"
        architectures = int.from_bytes(head[4:8], order)
        if 1 <= architectures <= 16:
            return "mach-o", "Mach-O universal"
        return "java-class", "Java class"
    if head[:4] == b"PK\x03\x04" or head[:4] == b"PK\x05\x06":
        return "zip", "ZIP / arquivo compactado"
    if head[:4] == b"\x00asm":
        return "wasm", "WebAssembly"
    if head[:5] == b"%PDF-":
        return "pdf", "PDF"
    if head[:4] == b"\x1f\x8b":
        return "gzip", "GZip"
    if head[:4] == b"GGUF":
        return "gguf", "GGUF (modelo)"
    if head[:8] == b"\x93NUMPY":
        return "numpy", "NumPy .npy"
    if head[:4] == b"FOR1" and head[8:12] == b"BEAM":
        return "beam", "Erlang BEAM"
    if head[:4] == b"dex\n":
        return "dex", "Android DEX"
    if len(head) >= 16 and head[:4] == b"\x04\x00\x00\x00":
        for start in (8, 16):
            length = int.from_bytes(head[start - 4:start], "little")
            if 0 < length <= 64 * 1024 * 1024 and head[start:start + 1] == b"{":
                return "asar", "Electron ASAR"
    if len(head) >= 8 and _is_probably_text(head):
        try:
            head.decode("utf-8")
        except UnicodeDecodeError:
            pass
        else:
            if suffix in {".js", ".mjs", ".cjs", ".jsx"}:
                return "javascript-source", "JavaScript (texto)"
            if suffix in {".ts", ".tsx"}:
                return "typescript-source", "TypeScript (texto)"
            if suffix == ".json":
                return "json", "JSON"
            if suffix == ".map":
                return "source-map", "Source map (JSON)"
            if suffix in {".html", ".htm"}:
                return "html", "HTML"
            if suffix == ".css":
                return "css", "CSS"
            return "text", "Texto"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "png", "PNG"
    if head[:3] == b"\xff\xd8\xff":
        return "jpeg", "JPEG"
    if head[:6] in {b"GIF87a", b"GIF89a"}:
        return "gif", "GIF"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp", "WebP"
    return "binary", "Binário não reconhecido"


def _identity(path: Path, relative: str, data: bytes) -> dict[str, Any]:
    kind, label = detect_format(data[:64], path.suffix.lower())
    return {
        "path": relative,
        "bytes": len(data),
        "sha256": _hash(data),
        "kind": kind,
        "format": label,
        "extension": path.suffix.lower(),
    }


def _entropy_profile(data: bytes, block_size: int = 4096, limit: int = 32768) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    for offset in range(0, len(data), block_size):
        if len(blocks) >= limit:
            break
        chunk = data[offset:offset + block_size]
        blocks.append({"offset": offset, "length": len(chunk), "entropy": _byte_entropy(chunk)})
    runs: list[dict[str, Any]] = []
    for block in blocks:
        if block["entropy"] >= ENTROPY_HIGH:
            classification = "high"
        elif block["entropy"] <= ENTROPY_LOW:
            classification = "low"
        else:
            classification = "mixed"
        if runs and runs[-1]["classification"] == classification:
            runs[-1]["length"] += block["length"]
        else:
            runs.append({"offset": block["offset"], "length": block["length"], "classification": classification})
    return {
        "fileEntropy": _byte_entropy(data),
        "blockSize": block_size,
        "blockCount": len(blocks),
        "blocks": blocks,
        "runs": runs,
        "thresholds": {"high": ENTROPY_HIGH, "low": ENTROPY_LOW},
        "truncated": len(data) > block_size * limit,
    }


# ---------------------------------------------------------------- ELF


def _parse_elf(data: bytes) -> dict[str, Any]:
    if len(data) < 52 or data[:4] != b"\x7fELF":
        raise ReverseError("Cabeçalho ELF incompleto.")
    bits = data[4]
    if bits not in {1, 2} or data[5] not in {1, 2}:
        raise ReverseError("ELF com classe ou byte order desconhecidos.")
    little = data[5] == 1
    endian = "<" if little else ">"
    if bits == 2:
        header = _unpack(data, endian + "HHIQQQIHHHHHH", 16, "ELF header")
        (e_type, e_machine, _version, entry, phoff, shoff, _flags, ehsize,
         phentsize, phnum, shentsize, shnum, shstrndx) = header
    else:
        header = _unpack(data, endian + "HHIIIIIHHHHHH", 16, "ELF header")
        (e_type, e_machine, _version, entry, phoff, shoff, _flags, ehsize,
         phentsize, phnum, shentsize, shnum, shstrndx) = header
    if shnum > 4096 or phnum > 512:
        raise ReverseError("ELF declara uma quantidade de seções ou segmentos acima do limite de análise.")
    if shnum and (shentsize < 40 or shoff + shnum * shentsize > len(data)):
        raise ReverseError("Tabela de seções ELF fora dos limites do arquivo.")
    if phnum and (phentsize < 32 or phoff + phnum * phentsize > len(data)):
        raise ReverseError("Tabela de segmentos ELF fora dos limites do arquivo.")

    sections: list[dict[str, Any]] = []
    section_headers: list[dict[str, Any]] = []
    for index in range(shnum):
        offset = shoff + index * shentsize
        if bits == 2:
            name, sh_type, flags, addr, file_offset, size, link, info, align, entsize = _unpack(data, endian + "IIQQQQIIQQ", offset, "seção ELF")
        else:
            name, sh_type, flags, addr, file_offset, size, link, info, align, entsize = _unpack(data, endian + "IIIIIIIIII", offset, "seção ELF")
        if size and file_offset + size > len(data) and sh_type != 8:  # SHT_NOBITS
            raise ReverseError("Seção ELF aponta para bytes fora do arquivo.")
        section_headers.append({
            "index": index, "nameOffset": name, "type": sh_type, "flags": flags,
            "addr": addr, "offset": file_offset, "size": size, "link": link,
            "info": info, "align": align, "entsize": entsize,
        })

    names = b""
    if shstrndx < len(section_headers):
        candidate = section_headers[shstrndx]
        if candidate["type"] != 8 and candidate["offset"] + candidate["size"] <= len(data):
            names = data[candidate["offset"]:candidate["offset"] + candidate["size"]]
    for section in section_headers:
        name = ""
        if names and section["nameOffset"] < len(names):
            end = names.find(b"\x00", section["nameOffset"])
            name = names[section["nameOffset"]:end if end >= 0 else len(names)].decode("utf-8", "replace")
        sections.append({
            "index": section["index"], "name": name, "type": section["type"],
            "flags": section["flags"], "addr": section["addr"], "offset": section["offset"],
            "size": section["size"],
        })

    segments: list[dict[str, Any]] = []
    for index in range(phnum):
        offset = phoff + index * phentsize
        if bits == 2:
            p_type, flags, file_offset, vaddr, paddr, filesz, memsz, align = _unpack(data, endian + "IIQQQQQQ", offset, "segmento ELF")
        else:
            p_type, flags, file_offset, vaddr, paddr, filesz, memsz, align = _unpack(data, endian + "IIIIIIII", offset, "segmento ELF")
        if filesz and file_offset + filesz > len(data):
            raise ReverseError("Segmento ELF aponta para bytes fora do arquivo.")
        segments.append({"index": index, "type": p_type, "flags": flags, "offset": file_offset, "vaddr": vaddr, "paddr": paddr, "filesz": filesz, "memsz": memsz, "align": align})

    needed: list[str] = []
    soname = ""
    runpath: list[str] = []
    limitations: list[str] = []
    dynamic = next((section for section in section_headers if section["type"] == 6), None)
    if dynamic is not None:
        entry_size = dynamic["entsize"] or (16 if bits == 2 else 8)
        fmt = endian + ("qQ" if bits == 2 else "iI")
        strtab = b""
        if dynamic["link"] < len(section_headers):
            linked = section_headers[dynamic["link"]]
            if linked["offset"] + linked["size"] <= len(data):
                strtab = data[linked["offset"]:linked["offset"] + linked["size"]]
        count = min(dynamic["size"] // entry_size, 4096) if entry_size >= 8 else 0
        for index in range(count):
            tag, value = _unpack(data, fmt, dynamic["offset"] + index * entry_size, "entrada dinâmica")
            if tag == 0:
                break
            if tag in {1, 14, 15, 29}:
                text = ""
                if strtab and value < len(strtab):
                    end = strtab.find(b"\x00", value)
                    text = strtab[value:end if end >= 0 else len(strtab)].decode("utf-8", "replace")
                if not text:
                    limitations.append("Uma entrada dinâmica não pôde ser resolvida na string table.")
                    continue
                if tag == 1:
                    needed.append(text)
                elif tag == 14:
                    soname = text
                else:
                    runpath.append(text)
    elif not sections:
        limitations.append("ELF sem tabela de seções: dependências dinâmicas não foram inventariadas.")

    type_name = {1: "relocatable", 2: "executable", 3: "shared-object", 4: "core"}.get(e_type, f"type-{e_type}")
    facts = {
        "class": 64 if bits == 2 else 32,
        "endianness": "little" if little else "big",
        "type": type_name,
        "machine": _ELF_MACHINES.get(e_machine, f"machine-{e_machine}"),
        "entryPoint": hex(entry),
        "headerSize": ehsize,
        "sectionCount": len(sections),
        "segmentCount": len(segments),
        "needed": needed[:64],
        "soname": soname,
        "runpath": runpath[:8],
        "hasInterpreter": any(segment["type"] == 3 for segment in segments),
    }
    findings: list[dict[str, Any]] = []
    if type_name == "executable" and any(segment["type"] == 3 and segment["flags"] & 0x1 for segment in segments):
        findings.append({"severity": "info", "message": "Segmento carregável possui permissão de execução; é esperado em código, não prova proteção ausente."})
    if any(section["name"] == ".symtab" for section in sections):
        findings.append({"severity": "info", "message": "Tabela de símbolos presente; binários distribuídos costumam omiti-la."})
    return {
        "facts": facts,
        "sections": sections[:MAX_LAYOUT_ROWS],
        "segments": segments[:128],
        "entries": [],
        "imports": [{"library": name} for name in needed[:64]],
        "findings": findings,
        "limitations": limitations,
        "truncated": len(sections) > MAX_LAYOUT_ROWS,
    }


# ---------------------------------------------------------------- PE


def _parse_pe(data: bytes) -> dict[str, Any]:
    if len(data) < 0x40 or data[:2] != b"MZ":
        raise ReverseError("Cabeçalho MZ incompleto.")
    pe_offset = _unpack(data, "<I", 0x3C, "offset PE")[0]
    if pe_offset + 24 > len(data) or data[pe_offset:pe_offset + 4] != b"PE\x00\x00":
        raise ReverseError("Assinatura PE ausente ou fora dos limites do arquivo.")
    machine, section_count, _stamp, _symtab, _nsyms, optional_size, characteristics = _unpack(data, "<HHIIIHH", pe_offset + 4, "COFF header")
    if section_count > 512:
        raise ReverseError("PE declara seções acima do limite de análise.")
    optional_offset = pe_offset + 24
    if optional_offset + optional_size > len(data) or optional_size < 2:
        raise ReverseError("Cabeçalho opcional PE fora dos limites do arquivo.")
    magic = _unpack(data, "<H", optional_offset, "optional magic")[0]
    if magic not in {0x10B, 0x20B}:
        raise ReverseError("PE com formato opcional desconhecido.")
    plus = magic == 0x20B
    entry = _unpack(data, "<I", optional_offset + 16, "entry point")[0]
    image_base = _unpack(data, "<Q" if plus else "<I", optional_offset + (24 if plus else 28), "image base")[0]
    subsystem = _unpack(data, "<H", optional_offset + 68, "subsystem")[0]
    dll_flags = _unpack(data, "<H", optional_offset + 70, "DLL characteristics")[0]
    directory_count_offset = optional_offset + (108 if plus else 92)
    directory_count = _unpack(data, "<I", directory_count_offset, "data directory count")[0]
    directory_offset = optional_offset + (112 if plus else 96)
    directory_count = min(directory_count, 16)
    directories: list[dict[str, Any]] = []
    for index in range(directory_count):
        rva, size = _unpack(data, "<II", directory_offset + index * 8, "data directory")
        if rva or size:
            directories.append({"index": index, "rva": hex(rva), "size": size})

    sections: list[dict[str, Any]] = []
    for index in range(section_count):
        offset = optional_offset + optional_size + index * 40
        raw_name, vsize, vaddr, raw_size, raw_ptr, _relocs, _lines, _nreloc, _nlines, flags = _unpack(data, "<8sIIIIIIHHI", offset, "seção PE")
        if raw_size and raw_ptr + raw_size > len(data):
            raise ReverseError("Seção PE aponta para bytes fora do arquivo.")
        sections.append({
            "index": index,
            "name": raw_name.rstrip(b"\x00").decode("utf-8", "replace"),
            "virtualSize": vsize,
            "virtualAddress": hex(vaddr),
            "rawSize": raw_size,
            "rawOffset": raw_ptr,
            "flags": hex(flags),
            "readable": bool(flags & 0x40000000),
            "writable": bool(flags & 0x80000000),
            "executable": bool(flags & 0x20000000),
        })

    def rva_to_offset(rva: int) -> int | None:
        for section in sections:
            start = int(section["virtualAddress"], 16)
            if start <= rva < start + max(section["virtualSize"], section["rawSize"]):
                delta = rva - start
                if delta < section["rawSize"]:
                    return section["rawOffset"] + delta
        return None

    imports: list[dict[str, Any]] = []
    limitations: list[str] = []
    import_directory = next((item for item in directories if item["index"] == 1), None)
    if import_directory:
        offset = rva_to_offset(int(import_directory["rva"], 16))
        if offset is None:
            limitations.append("Diretório de importações não pôde ser mapeado para um offset de arquivo.")
        else:
            for _ in range(64):
                if offset + 20 > len(data):
                    limitations.append("Tabela de importações termina fora dos limites do arquivo.")
                    break
                original, _stamp, _forward, name_rva, first_thunk = _unpack(data, "<IIIII", offset, "import descriptor")
                if not (original or name_rva or first_thunk):
                    break
                name_offset = rva_to_offset(name_rva)
                library = _cstring(data, name_offset) if name_offset is not None else ""
                count = 0
                thunk_rva = original or first_thunk
                thunk_offset = rva_to_offset(thunk_rva) if thunk_rva else None
                while thunk_offset is not None and count < 4096 and thunk_offset + (8 if plus else 4) <= len(data):
                    value = _unpack(data, "<Q" if plus else "<I", thunk_offset, "import thunk")[0]
                    if value == 0:
                        break
                    count += 1
                    thunk_offset += 8 if plus else 4
                imports.append({"library": library or "(nome indisponível)", "functions": count})
                offset += 20

    managed = any(item["index"] == 14 for item in directories)
    facts = {
        "machine": _PE_MACHINES.get(machine, f"machine-{machine}"),
        "bits": 64 if plus else 32,
        "subsystem": subsystem,
        "entryPoint": hex(entry),
        "imageBase": hex(image_base),
        "sectionCount": len(sections),
        "importedLibraries": len(imports),
        "managed": managed,
        "characteristics": hex(characteristics),
        "dllCharacteristics": hex(dll_flags),
        "aslr": bool(dll_flags & 0x40),
        "nxCompat": bool(dll_flags & 0x100),
        "guardCf": bool(dll_flags & 0x4000),
        "directories": directories,
    }
    findings: list[dict[str, Any]] = []
    if any(section["writable"] and section["executable"] for section in sections):
        findings.append({"severity": "attention", "message": "Há seção simultaneamente gravável e executável; verifique se é intencional."})
    if not facts["aslr"]:
        findings.append({"severity": "info", "message": "DYNAMIC_BASE ausente: o cabeçalho não declara ASLR; isso não prova ausência de proteção em todas as versões do Windows."})
    return {
        "facts": facts,
        "sections": sections[:MAX_LAYOUT_ROWS],
        "segments": [],
        "entries": [],
        "imports": imports[:64],
        "findings": findings,
        "limitations": limitations,
        "truncated": False,
    }


# ---------------------------------------------------------------- Mach-O


def _parse_macho(data: bytes) -> dict[str, Any]:
    magic = data[:4]
    little_endian = magic in {b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe", b"\xbe\xba\xfe\xca", b"\xbf\xba\xfe\xca"}
    endian = "<" if little_endian else ">"
    if magic in {b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca", b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca"}:
        count = _unpack(data, endian + "I", 4, "fat header")[0]
        if count > 16:
            raise ReverseError("Mach-O universal declara arquiteturas acima do limite de análise.")
        fat64 = magic in {b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca"}
        entry_size = 32 if fat64 else 20
        architectures: list[dict[str, Any]] = []
        for index in range(count):
            offset = 8 + index * entry_size
            if fat64:
                cpu, _sub, file_offset, size, _align, _reserved = _unpack(data, endian + "IIQQII", offset, "fat arch")
            else:
                cpu, _sub, file_offset, size, _align = _unpack(data, endian + "IIIII", offset, "fat arch")
            if file_offset + size > len(data):
                raise ReverseError("Arquitetura Mach-O universal aponta para bytes fora do arquivo.")
            architectures.append({"cpu": _MACHO_CPUS.get(cpu, hex(cpu)), "offset": file_offset, "size": size})
        first = architectures[0] if architectures else None
        facts: dict[str, Any] = {"fat": True, "architectures": architectures, "count": len(architectures)}
        if first:
            try:
                inner = _parse_macho(data[first["offset"]:first["offset"] + first["size"]])
                facts["firstArchitecture"] = inner["facts"]
            except ReverseError as exc:
                facts["firstArchitectureError"] = str(exc)
        return {"facts": facts, "sections": [], "segments": [], "entries": [], "imports": [], "findings": [], "limitations": ["Apenas o cabeçalho de cada arquitetura foi resumido; comandos de carga completos exigem análise por slice."], "truncated": True}

    if magic not in {b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe"}:
        raise ReverseError("Mach-O com magic desconhecido.")
    plus = magic in {b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe"}
    cputype, _subtype, filetype, ncmds, sizeofcmds, flags = _unpack(data, endian + "IIIIII", 4, "Mach-O header")
    header_size = 32 if plus else 28
    if ncmds > 256 or header_size + sizeofcmds > len(data):
        raise ReverseError("Comandos de carga Mach-O fora dos limites do arquivo.")
    segments: list[dict[str, Any]] = []
    imports: list[dict[str, Any]] = []
    limitations: list[str] = []
    command_offset = header_size
    for _ in range(ncmds):
        cmd, size = _unpack(data, endian + "II", command_offset, "load command")
        if size < 8 or command_offset + size > len(data):
            raise ReverseError("Comando de carga Mach-O malformado.")
        if cmd in {0x1, 0x19}:
            if cmd == 0x19:
                name_raw, vmaddr, vmsize, fileoff, filesize, _maxprot, _initprot, nsects, _flags = _unpack(data, endian + "16sQQQQIIII", command_offset + 8, "segment 64")
            else:
                name_raw, vmaddr, vmsize, fileoff, filesize, _maxprot, _initprot, nsects, _flags = _unpack(data, endian + "16sIIIIIIII", command_offset + 8, "segment 32")
            segments.append({
                "name": name_raw.rstrip(b"\x00").decode("utf-8", "replace"),
                "vmaddr": hex(vmaddr), "vmsize": vmsize, "fileOffset": fileoff,
                "fileSize": filesize, "sections": nsects,
            })
        elif cmd in {0xC, 0xD}:
            name_offset = _unpack(data, endian + "I", command_offset + 8, "dylib name")[0]
            if 8 < name_offset < size:
                name = _cstring(data, command_offset + name_offset, size - name_offset)
                imports.append({"library": name, "kind": "id" if cmd == 0xD else "load"})
        elif cmd == 0x1B:
            uuid = data[command_offset + 8:command_offset + 24].hex()
            imports.append({"library": f"uuid:{uuid}", "kind": "uuid"})
        elif cmd == 0x21:
            limitations.append("LC_ENCRYPTION_INFO presente; o conteúdo pode estar cifrado e não é decifrado por esta análise.")
        elif cmd == 0x2C:
            limitations.append("LC_ENCRYPTION_INFO_64 presente; o conteúdo pode estar cifrado e não é decifrado por esta análise.")
        command_offset += size
    sections: list[dict[str, Any]] = []
    if segments:
        first = segments[0]
        facts: dict[str, Any] = {
            "cpu": _MACHO_CPUS.get(cputype, hex(cputype)),
            "fileType": filetype,
            "bits": 64 if plus else 32,
            "loadCommands": ncmds,
            "flags": hex(flags),
            "segmentCount": len(segments),
            "fat": False,
        }
        return {"facts": facts, "sections": sections, "segments": segments[:128], "entries": [], "imports": imports[:64], "findings": [], "limitations": limitations, "truncated": False}
    raise ReverseError("Mach-O sem segmentos legíveis.")


# ---------------------------------------------------------------- ZIP


def _parse_zip(data: bytes) -> dict[str, Any]:
    eocd = data.rfind(b"PK\x05\x06", max(0, len(data) - 65_557))
    if eocd < 0 or eocd + 22 > len(data):
        raise ReverseError("Diretório central ZIP não encontrado; o arquivo pode estar truncado.")
    _disk, _cd_disk, _disk_entries, total_entries, cd_size, cd_offset, _comment = _unpack(data, "<HHHHIIH", eocd + 4, "EOCD")
    limitations: list[str] = []
    if total_entries == 0xFFFF or cd_offset == 0xFFFFFFFF or cd_size == 0xFFFFFFFF:
        locator = data.rfind(b"PK\x06\x07", max(0, eocd - 64), eocd)
        if locator >= 0 and locator + 20 <= len(data):
            _sig, _disk, zip64_offset, _disks = _unpack(data, "<IIQI", locator, "ZIP64 locator")
            if zip64_offset + 56 <= len(data):
                (_sig64, _size, _made, _needed, _disk_no, _cd_disk_no, _here, total64,
                 cd_size64, cd_offset64) = _unpack(data, "<IQHHIIQQQQ", zip64_offset, "ZIP64 EOCD")
                total_entries, cd_size, cd_offset = total64, cd_size64, cd_offset64
            else:
                limitations.append("ZIP64 EOCD fora dos limites; o inventário pode estar incompleto.")
        else:
            limitations.append("ZIP64 sem localizador legível; o inventário pode estar incompleto.")
    if cd_offset + cd_size > len(data):
        raise ReverseError("Diretório central ZIP aponta para fora do arquivo.")
    entries: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    position = cd_offset
    unsafe = 0
    duplicates: Counter[str] = Counter()
    while position + 46 <= len(data) and len(entries) < min(total_entries or MAX_ARCHIVE_ENTRIES, MAX_ARCHIVE_ENTRIES):
        if data[position:position + 4] != b"PK\x01\x02":
            limitations.append("Entrada do diretório central com assinatura inesperada; inventário interrompido.")
            break
        (_sig, _made, _needed, flags, method, _time, _date, crc, comp_size, uncomp_size,
         name_len, extra_len, comment_len, _disk_start, _internal, external, local_offset) = _unpack(data, "<IHHHHHHIIIHHHHHII", position, "central directory")
        name_offset = position + 46
        if name_offset + name_len + extra_len + comment_len > len(data):
            raise ReverseError("Entrada ZIP com nome ou metadados fora do arquivo.")
        raw_name = data[name_offset:name_offset + name_len]
        name = raw_name.decode("utf-8" if flags & 0x800 else "cp437", "replace")
        stripped = name.replace("\\", "/")
        pure = PurePosixPath(stripped)
        unsafe_entry = pure.is_absolute() or ".." in pure.parts or "\x00" in name
        if unsafe_entry:
            unsafe += 1
        duplicates[name] += 1
        entries.append({
            "name": name,
            "bytes": uncomp_size,
            "compressedBytes": comp_size,
            "method": method,
            "crc32": f"{crc:08x}",
            "encrypted": bool(flags & 0x1),
            "directory": stripped.endswith("/"),
            "uncompressedRatio": round(uncomp_size / comp_size, 2) if comp_size else None,
            "unsafeName": unsafe_entry,
            "localHeaderOffset": local_offset,
        })
        position += 46 + name_len + extra_len + comment_len
    if len(entries) >= MAX_ARCHIVE_ENTRIES and total_entries > MAX_ARCHIVE_ENTRIES:
        limitations.append(f"Inventário limitado a {MAX_ARCHIVE_ENTRIES} entradas de {total_entries}.")
    if unsafe:
        findings.append({"severity": "attention", "message": f"{unsafe} entrada(s) com caminho absoluto ou '..' no nome; o JARVIS nunca extrai este arquivo automaticamente."})
    if any(count > 1 for count in duplicates.values()):
        findings.append({"severity": "attention", "message": "Há nomes duplicados no diretório central; a resolução depende do consumidor."})
    if any(entry["uncompressedRatio"] and entry["uncompressedRatio"] > 100 and entry["bytes"] > 10_000_000 for entry in entries):
        findings.append({"severity": "attention", "message": "Razão de compressão muito alta em uma entrada grande; possível zip bomb. Nada é descompactado."})
    if any(entry["encrypted"] for entry in entries):
        findings.append({"severity": "info", "message": "Há entradas cifradas; o conteúdo não pode ser interpretado sem a chave."})
    names = {entry["name"] for entry in entries}
    lowered = {name.lower() for name in names}
    if "androidmanifest.xml" in lowered and any(name.startswith("classes") and name.endswith(".dex") for name in lowered):
        archive_kind = "apk"
    elif "meta-inf/manifest.mf" in lowered:
        archive_kind = "jar"
    elif "androidmanifest.xml" in lowered and "classes.jar" in lowered:
        archive_kind = "aar"
    else:
        archive_kind = "zip"
    facts = {
        "archiveKind": archive_kind,
        "entryCount": len(entries),
        "declaredEntryCount": total_entries,
        "compressedBytes": sum(entry["compressedBytes"] for entry in entries),
        "uncompressedBytes": sum(entry["bytes"] for entry in entries),
        "centralDirectorySize": cd_size,
        "hasEncryptedEntries": any(entry["encrypted"] for entry in entries),
        "unsafeEntryCount": unsafe,
    }
    return {"facts": facts, "sections": [], "segments": [], "entries": entries, "imports": [], "findings": findings, "limitations": limitations, "truncated": len(entries) >= MAX_ARCHIVE_ENTRIES}


# ---------------------------------------------------------------- ASAR


def _parse_asar(data: bytes) -> dict[str, Any]:
    tree = None
    data_start = 0
    header_length = 0
    for start in (8, 16):
        if len(data) <= start:
            continue
        length = int.from_bytes(data[start - 4:start], "little")
        if 0 < length <= 16 * 1024 * 1024 and start + length <= len(data) and data[start:start + 1] == b"{":
            try:
                tree = json.loads(data[start:start + length].decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            header_length = length
            data_start = start + length
            break
    if tree is None or not isinstance(tree, dict):
        raise ReverseError("Cabeçalho JSON do ASAR inválido ou fora dos limites do arquivo.")
    entries: list[dict[str, Any]] = []
    limitations: list[str] = []

    def walk(node: Any, prefix: str, depth: int) -> None:
        if len(entries) >= MAX_ARCHIVE_ENTRIES or depth > 16 or not isinstance(node, dict):
            return
        for name, child in node.items():
            if len(entries) >= MAX_ARCHIVE_ENTRIES:
                return
            path = f"{prefix}/{name}" if prefix else str(name)
            if not isinstance(child, dict):
                continue
            if isinstance(child.get("files"), dict):
                walk(child["files"], path, depth + 1)
                continue
            size = child.get("size")
            offset = child.get("offset")
            entries.append({
                "name": path,
                "bytes": size if isinstance(size, int) else None,
                "offset": data_start + offset if isinstance(offset, int) else None,
                "unpacked": bool(child.get("unpacked")),
                "executable": bool(child.get("executable")),
            })

    walk(tree.get("files"), "", 0)
    if len(entries) >= MAX_ARCHIVE_ENTRIES:
        limitations.append(f"Inventário limitado a {MAX_ARCHIVE_ENTRIES} entradas.")
    if any(entry["unpacked"] for entry in entries):
        limitations.append("Há arquivos marcados como 'unpacked'; eles não estão contidos neste ASAR.")
    facts = {
        "headerBytes": header_length,
        "dataStart": data_start,
        "entryCount": len(entries),
        "hasUnpackedEntries": any(entry["unpacked"] for entry in entries),
        "executableEntries": sum(1 for entry in entries if entry["executable"]),
    }
    return {"facts": facts, "sections": [], "segments": [], "entries": entries, "imports": [], "findings": [], "limitations": limitations, "truncated": len(entries) >= MAX_ARCHIVE_ENTRIES}


# ---------------------------------------------------------------- WASM


def _leb(data: bytes, position: int) -> tuple[int, int]:
    result = 0
    shift = 0
    for _ in range(5):
        if position >= len(data):
            raise ReverseError("LEB128 truncado no WASM.")
        byte = data[position]
        position += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, position
        shift += 7
    raise ReverseError("LEB128 inválido no WASM.")


def _wasm_string(data: bytes, position: int, end: int) -> tuple[str, int]:
    length, position = _leb(data, position)
    if length > 4096 or position + length > end:
        raise ReverseError("Nome de importação/exportação WASM fora dos limites da seção.")
    return data[position:position + length].decode("utf-8", "replace"), position + length


def _parse_wasm(data: bytes) -> dict[str, Any]:
    if len(data) < 8 or data[:4] != b"\x00asm":
        raise ReverseError("Cabeçalho WASM incompleto.")
    version = int.from_bytes(data[4:8], "little")
    position = 8
    sections: list[dict[str, Any]] = []
    imports: list[dict[str, Any]] = []
    exports: list[str] = []
    limitations: list[str] = []
    while position < len(data) and len(sections) < 64:
        section_id = data[position]
        position += 1
        size, position = _leb(data, position)
        if size > len(data) - position:
            raise ReverseError("Seção WASM aponta para fora do arquivo.")
        end = position + size
        label = _WASM_SECTIONS.get(section_id, f"section-{section_id}")
        if section_id == 0:
            try:
                label, _ = _wasm_string(data, position, end)
            except ReverseError:
                label = "custom (nome ilegível)"
        count = 0
        if section_id == 2:
            count, cursor = _leb(data, position)
            for _ in range(min(count, 64)):
                module, cursor = _wasm_string(data, cursor, end)
                field, cursor = _wasm_string(data, cursor, end)
                kind = data[cursor]
                cursor += 1
                imports.append({"module": module, "field": field, "kind": {0: "function", 1: "table", 2: "memory", 3: "global"}.get(kind, str(kind))})
                if kind == 0:
                    _type, cursor = _leb(data, cursor) if cursor < end else (0, cursor)
                elif kind == 1:
                    cursor += 1
                    _limits, cursor = _leb(data, cursor)
                elif kind == 2:
                    _flags, cursor = _leb(data, cursor)
                    _min, cursor = _leb(data, cursor)
                    if _flags & 1:
                        _max, cursor = _leb(data, cursor)
                elif kind == 3:
                    cursor += 2
                if cursor > end:
                    raise ReverseError("Importação WASM fora dos limites da seção.")
        elif section_id == 7:
            count, cursor = _leb(data, position)
            for _ in range(min(count, 256)):
                name, cursor = _wasm_string(data, cursor, end)
                if cursor >= end:
                    raise ReverseError("Exportação WASM truncada.")
                cursor += 1
                _index, cursor = _leb(data, cursor)
                exports.append(name)
        sections.append({"id": section_id, "name": label, "bytes": size, "declaredEntries": count})
        position = end
    if position < len(data):
        limitations.append("Há bytes após as seções interpretadas; a leitura foi limitada.")
    if len(sections) >= 64:
        limitations.append("Inventário de seções limitado a 64.")
    return {
        "facts": {"version": version, "sectionCount": len(sections), "importCount": len(imports), "exportCount": len(exports), "exports": exports[:64]},
        "sections": sections,
        "segments": [],
        "entries": [],
        "imports": imports[:64],
        "findings": [],
        "limitations": limitations + ["Os corpos das funções não são decodificados nem executados."],
        "truncated": len(sections) >= 64,
    }


# ---------------------------------------------------------------- modelos e outros contêineres


def _parse_safetensors(data: bytes) -> dict[str, Any]:
    if len(data) < 9:
        raise ReverseError("Cabeçalho safetensors incompleto.")
    header_length = int.from_bytes(data[:8], "little")
    if header_length <= 0 or 8 + header_length > len(data):
        raise ReverseError("Cabeçalho safetensors aponta para fora do arquivo.")
    if header_length > 8 * 1024 * 1024:
        raise ReverseError("Cabeçalho safetensors excede o limite de 8 MB.")
    try:
        header = json.loads(data[8:8 + header_length].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReverseError("Cabeçalho JSON do safetensors inválido.") from exc
    metadata = header.pop("__metadata__", {}) if isinstance(header, dict) else {}
    dtypes: Counter[str] = Counter()
    tensor_bytes = 0
    max_end = 0
    for _name, tensor in list(header.items())[:5000]:
        if not isinstance(tensor, dict):
            continue
        dtype = str(tensor.get("dtype", "unknown"))
        dtypes[dtype] += 1
        shape = tensor.get("shape") if isinstance(tensor.get("shape"), list) else []
        offsets = tensor.get("data_offsets") if isinstance(tensor.get("data_offsets"), list) else []
        if len(offsets) == 2 and all(isinstance(value, int) for value in offsets):
            tensor_bytes += max(0, offsets[1] - offsets[0])
            max_end = max(max_end, offsets[1])
        else:
            shape = shape if isinstance(shape, list) else []
    available = len(data) - 8 - header_length
    limitations = ["Somente o cabeçalho é interpretado; pesos e semântica do modelo não são analisados."]
    if tensor_bytes != available:
        limitations.append(f"Bytes declarados ({tensor_bytes}) diferem dos bytes disponíveis ({available}); o arquivo pode estar truncado ou usar offsets não triviais.")
    facts = {
        "headerBytes": header_length,
        "tensorCount": sum(dtypes.values()),
        "dtypes": dict(dtypes),
        "declaredTensorBytes": tensor_bytes,
        "availableTensorBytes": available,
        "metadataKeys": sorted(str(key) for key in metadata)[:32] if isinstance(metadata, dict) else [],
        "maxDataEnd": max_end,
    }
    return {"facts": facts, "sections": [], "segments": [], "entries": [], "imports": [], "findings": [], "limitations": limitations, "truncated": False}


def _parse_gguf(data: bytes) -> dict[str, Any]:
    if len(data) < 24:
        raise ReverseError("Cabeçalho GGUF incompleto.")
    version, tensor_count, kv_count = _unpack(data, "<IQQ", 4, "GGUF header")
    return {
        "facts": {"version": version, "tensorCount": tensor_count, "metadataCount": kv_count},
        "sections": [],
        "segments": [],
        "entries": [],
        "imports": [],
        "findings": [],
        "limitations": ["Apenas o cabeçalho GGUF é lido; metadados e tensores não são decodificados."],
        "truncated": True,
    }


def _parse_pyc(data: bytes) -> dict[str, Any]:
    if len(data) < 16:
        raise ReverseError("Cabeçalho PYC incompleto.")
    magic = int.from_bytes(data[0:2], "little")
    flags = int.from_bytes(data[4:8], "little")
    return {
        "facts": {"magic": magic, "python": _PYC_VERSIONS.get(magic, "desconhecida"), "flags": flags, "timestampBased": not bool(flags & 0x1)},
        "sections": [],
        "segments": [],
        "entries": [],
        "imports": [],
        "findings": [],
        "limitations": ["Bytecode não é descompilado nem executado."],
        "truncated": False,
    }


def _parse_beam(data: bytes) -> dict[str, Any]:
    if len(data) < 12 or data[:4] != b"FOR1" or data[8:12] != b"BEAM":
        raise ReverseError("Contêiner BEAM incompleto.")
    position = 12
    chunks: list[dict[str, Any]] = []
    while position + 8 <= len(data) and len(chunks) < 64:
        name = data[position:position + 4].decode("latin-1")
        size = int.from_bytes(data[position + 4:position + 8], "big")
        position += 8
        if position + size > len(data):
            raise ReverseError("Chunk BEAM aponta para fora do arquivo.")
        chunks.append({"name": name, "bytes": size})
        position += size
    atoms = next((chunk["bytes"] for chunk in chunks if chunk["name"] in {"AtU8", "Atom"}), 0)
    return {
        "facts": {"chunkCount": len(chunks), "chunks": chunks, "atomChunkBytes": atoms},
        "sections": [],
        "segments": [],
        "entries": [],
        "imports": [],
        "findings": [],
        "limitations": ["Chunks detectados sem decodificar bytecode BEAM."],
        "truncated": False,
    }


def _parse_pdf(data: bytes) -> dict[str, Any]:
    if len(data) < 8:
        raise ReverseError("Cabeçalho PDF incompleto.")
    header = data[:16].decode("latin-1").strip()
    version = header.split("%PDF-", 1)[1].split()[0] if "%PDF-" in header else "unknown"
    objects = len(re.findall(rb"\d+\s+\d+\s+obj\b", data))
    has_javascript = bool(re.search(rb"/JavaScript|/JS\b", data))
    encrypted = bool(re.search(rb"/Encrypt\b", data))
    findings: list[dict[str, Any]] = []
    if has_javascript:
        findings.append({"severity": "attention", "message": "O PDF declara JavaScript embutido; o JARVIS não o executa nem o renderiza."})
    if encrypted:
        findings.append({"severity": "info", "message": "O PDF declara criptografia; o conteúdo não é decifrado."})
    return {
        "facts": {"version": version, "objectCount": objects, "hasJavaScript": has_javascript, "encrypted": encrypted, "linearized": b"/Linearized" in data[:2048]},
        "sections": [],
        "segments": [],
        "entries": [],
        "imports": [],
        "findings": findings,
        "limitations": ["O PDF não é renderizado; apenas marcadores estruturais são contados."],
        "truncated": False,
    }


# ---------------------------------------------------------------- dispatch


def _parse(data: bytes, path: Path) -> dict[str, Any]:
    kind, label = detect_format(data[:64], path.suffix.lower())
    parsers = {
        "elf": _parse_elf,
        "pe": _parse_pe,
        "mach-o": _parse_macho,
        "zip": _parse_zip,
        "asar": _parse_asar,
        "wasm": _parse_wasm,
        "safetensors": _parse_safetensors,
        "gguf": _parse_gguf,
        "pyc": _parse_pyc,
        "beam": _parse_beam,
        "pdf": _parse_pdf,
    }
    if kind in parsers:
        try:
            parsed = parsers[kind](data)
        except (struct.error, IndexError, KeyError, OverflowError) as exc:
            raise ReverseError("O artefato está malformado para o formato declarado.") from exc
        parsed["kind"] = kind
        parsed["format"] = label
        return parsed
    if kind.endswith("-source") or kind in {"json", "source-map", "html", "css", "text"}:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ReverseError("O arquivo de texto não é UTF-8 válido.") from exc
        return {
            "kind": kind,
            "format": label,
            "facts": {"lines": text.count("\n") + 1, "characters": len(text), "encoding": "utf-8"},
            "sections": [],
            "segments": [],
            "entries": [],
            "imports": [],
            "findings": [],
            "limitations": ["Arquivo de texto: nenhuma interpretação de código é feita nesta inspeção."],
            "truncated": False,
        }
    return {
        "kind": kind,
        "format": label,
        "facts": {},
        "sections": [],
        "segments": [],
        "entries": [],
        "imports": [],
        "findings": [],
        "limitations": ["Formato sem parser estrutural nesta versão: apenas identidade, entropia e strings são fatos disponíveis."],
        "truncated": False,
    }


def _base(identity: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": identity["path"],
        "identity": identity,
        "kind": parsed["kind"],
        "format": parsed["format"],
        "executed": False,
        "readOnly": True,
        "facts": parsed["facts"],
        "findings": parsed["findings"],
        "limitations": [*_LIMITATIONS, *parsed["limitations"]],
    }


def inspect_artifact(files_root: Path, relative: str) -> dict[str, Any]:
    path = artifact_file(files_root, relative)
    data = _read(path)
    parsed = _parse(data, path)
    identity = _identity(path, relative, data)
    entropy = _entropy_profile(data)
    result = _base(identity, parsed)
    result.update({
        "analysis": "inspect",
        "entropy": {
            "fileEntropy": entropy["fileEntropy"],
            "blockCount": entropy["blockCount"],
            "highEntropyRuns": sum(1 for run in entropy["runs"] if run["classification"] == "high"),
            "lowEntropyRuns": sum(1 for run in entropy["runs"] if run["classification"] == "low"),
        },
        "counts": {
            "sections": len(parsed["sections"]),
            "segments": len(parsed["segments"]),
            "entries": len(parsed["entries"]),
            "imports": len(parsed["imports"]),
            "findings": len(parsed["findings"]),
        },
        "topFindings": parsed["findings"][:8],
    })
    return result


def inspect_layout(files_root: Path, relative: str) -> dict[str, Any]:
    path = artifact_file(files_root, relative)
    data = _read(path)
    parsed = _parse(data, path)
    identity = _identity(path, relative, data)
    result = _base(identity, parsed)
    result.update({
        "analysis": "layout",
        "sections": parsed["sections"],
        "segments": parsed["segments"],
        "entries": parsed["entries"],
        "imports": parsed["imports"],
        "truncated": parsed["truncated"]
        or len(parsed["sections"]) < int(parsed["facts"].get("sectionCount", len(parsed["sections"])))
        or len(parsed["entries"]) < int(parsed["facts"].get("entryCount", len(parsed["entries"]))),
    })
    return result


# ---------------------------------------------------------------- strings


def extract_strings(files_root: Path, relative: str, min_length: int = 6, encoding: str = "both",
                    limit: int = 200, offset: int = 0, length: int = 0, contains: str = "") -> dict[str, Any]:
    path = artifact_file(files_root, relative)
    size = path.stat().st_size
    if offset < 0 or offset >= size:
        raise ReverseError("O deslocamento inicial está fora do arquivo.")
    window_length = length or (size - offset)
    if window_length <= 0 or offset + window_length > size:
        raise ReverseError("A janela solicitada ultrapassa os limites do arquivo.")
    with path.open("rb") as handle:
        handle.seek(offset)
        window = handle.read(window_length)
    needle = contains.casefold()
    items: list[dict[str, Any]] = []
    truncated = False
    encodings = ["ascii", "utf16le"] if encoding == "both" else [encoding]
    for current in encodings:
        if current == "ascii":
            pattern = re.compile(rb"[\x20-\x7e]{%d,}" % min_length)
            for match in pattern.finditer(window):
                value = match.group().decode("ascii")
                if needle and needle not in value.casefold():
                    continue
                if len(items) >= limit:
                    truncated = True
                    break
                items.append({"offset": offset + match.start(), "bytes": len(match.group()), "encoding": "ascii", "value": value})
        else:
            pattern = re.compile(rb"(?:[\x20-\x7e]\x00){%d,}" % min_length)
            for match in pattern.finditer(window):
                value = match.group().decode("utf-16le")
                if needle and needle not in value.casefold():
                    continue
                if len(items) >= limit:
                    truncated = True
                    break
                items.append({"offset": offset + match.start(), "bytes": len(match.group()), "encoding": "utf-16le", "value": value})
        if truncated:
            break
    items.sort(key=lambda item: (item["offset"], item["encoding"]))
    return {
        "analysis": "strings",
        "path": relative,
        "identity": {"bytes": size, "sha256": _hash_file(path)},
        "window": {"offset": offset, "length": window_length},
        "minLength": min_length,
        "encodings": encodings,
        "contains": contains,
        "items": items[:limit],
        "count": len(items),
        "truncated": truncated,
        "executed": False,
        "limitations": [
            "Strings são bytes imprimíveis no intervalo ASCII e UTF-16LE; outros encodings não são interpretados.",
            "Uma string encontrada não prova que o valor seja usado em tempo de execução.",
            "Os valores pertencem ao artefato e podem conter dados sensíveis; nada é enviado a provedores externos.",
        ],
    }


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1_000_000):
            digest.update(chunk)
    return digest.hexdigest()





# ---------------------------------------------------------------- entropy


def byte_entropy(files_root: Path, relative: str, block_size: int = 4096, offset: int = 0, length: int = 0) -> dict[str, Any]:
    if block_size < 256 or block_size > 65536 or block_size & (block_size - 1):
        raise ReverseError("O tamanho do bloco deve ser uma potência de dois entre 256 e 65536.")
    path = artifact_file(files_root, relative)
    size = path.stat().st_size
    if offset < 0 or offset >= size:
        raise ReverseError("O deslocamento inicial está fora do arquivo.")
    window_length = length or (size - offset)
    if offset + window_length > size:
        raise ReverseError("A janela solicitada ultrapassa os limites do arquivo.")
    if window_length // block_size > 32768:
        raise ReverseError("A janela produziria mais de 32.768 blocos; aumente o tamanho do bloco ou reduza a janela.")
    with path.open("rb") as handle:
        handle.seek(offset)
        window = handle.read(window_length)
    profile = _entropy_profile(window, block_size)
    return {
        "analysis": "entropy",
        "path": relative,
        "identity": {"bytes": size, "sha256": _hash_file(path)},
        "window": {"offset": offset, "length": window_length},
        "blockSize": profile["blockSize"],
        "fileEntropy": profile["fileEntropy"],
        "blockCount": profile["blockCount"],
        "runs": profile["runs"],
        "blocks": profile["blocks"][:512],
        "blocksTruncated": profile["blockCount"] > 512,
        "thresholds": profile["thresholds"],
        "executed": False,
        "limitations": [
            "A entropia cobre a janela selecionada, não o arquivo inteiro; o SHA-256 cobre todo o arquivo.",
            "Entropia alta sugere compressão ou cifra; não identifica o algoritmo nem prova empacotamento.",
        ],
    }


# ---------------------------------------------------------------- JavaScript


class _LineIndex:
    def __init__(self, text: str) -> None:
        self.starts = [0, *(match.end() for match in re.finditer(r"\n", text))]

    def line(self, position: int) -> int:
        return bisect.bisect_right(self.starts, position)


def _node_builtin(specifier: str) -> bool:
    return specifier.startswith("node:") or specifier.split("/", 1)[0] in _NODE_BUILTINS


def _classify_specifier(specifier: str) -> str:
    if specifier.startswith(("http://", "https://", "//")):
        return "remote"
    if specifier.startswith((".", "/")):
        return "relative"
    if _node_builtin(specifier):
        return "builtin"
    return "package"


def _resolve_relative(root: Path, importer: Path, specifier: str) -> Path | None:
    base = (importer.parent / specifier).resolve() if specifier.startswith(".") else (root / specifier.lstrip("/")).resolve()
    try:
        base.relative_to(root)
    except ValueError:
        return None
    candidates = [base, *(base.with_name(f"{base.name}{suffix}") for suffix in (".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".json")), base / "index.js", base / "index.ts"]
    for candidate in candidates:
        if candidate.is_file() and not candidate.is_symlink() and candidate.suffix.lower() in ARTIFACT_EXTENSIONS:
            return candidate
    return None


def _module_facts(text: str, lines: _LineIndex) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for category, label, pattern, severity in _FACT_PATTERNS:
        for match in pattern.finditer(text):
            if len(facts) >= 200:
                return facts
            evidence_start = max(0, match.start() - 60)
            evidence = text[evidence_start:match.end() + 60].replace("\n", " ").strip()
            fact = {
                "category": category,
                "label": label,
                "line": lines.line(match.start()),
                "severity": severity,
                "evidence": evidence[:180],
            }
            try:
                captured = match.group("value")
            except IndexError:
                captured = None
            if captured:
                fact["value"] = captured[:160]
            facts.append(fact)
    return facts


def _analyze_source(relative: str, text: str, lines: _LineIndex, root: Path, importer: Path, resolve_imports: bool = True) -> dict[str, Any]:
    imports: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for pattern, kind in ((_IMPORT_RE, "esm-import"), (_EXPORT_FROM_RE, "esm-export"), (_REQUIRE_RE, "commonjs-require")):
        for match in pattern.finditer(text):
            specifier = match.group("spec").strip()
            if not specifier or (specifier, kind) in seen:
                continue
            seen.add((specifier, kind))
            resolution = _classify_specifier(specifier)
            target = None
            if resolve_imports and resolution == "relative" and root.is_dir():
                candidate = _resolve_relative(root, importer, specifier)
                target = candidate.relative_to(root).as_posix() if candidate else None
            imports.append({
                "specifier": specifier,
                "kind": kind,
                "resolution": resolution,
                "target": target,
                "line": lines.line(match.start()),
            })
            if len(imports) >= 80:
                break
    unresolved: list[dict[str, Any]] = []
    for item in imports:
        if item["resolution"] == "relative" and item["target"] is None:
            reason = "relative-outside-tree-or-missing" if resolve_imports else "inline-no-resolution"
            unresolved.append({"file": relative, "specifier": item["specifier"], "reason": reason, "line": item["line"]})
    for match in _DYNAMIC_IMPORT_LITERAL_RE.finditer(text):
        if len(unresolved) >= 120:
            break
        unresolved.append({
            "file": relative,
            "specifier": match.group("spec"),
            "reason": "dynamic-import",
            "line": lines.line(match.start()),
        })
    for pattern, label in ((_DYNAMIC_IMPORT_RE, "dynamic-import-expression"), (_DYNAMIC_REQUIRE_RE, "dynamic-require")):
        for match in pattern.finditer(text):
            if len(unresolved) >= 120:
                break
            unresolved.append({"file": relative, "specifier": "(expressão dinâmica)", "reason": label, "line": lines.line(match.start())})
    routes: list[dict[str, Any]] = []
    for match in _ROUTE_RE.finditer(text):
        if len(routes) >= 120:
            break
        routes.append({"method": match.group(1).upper(), "path": match.group("path"), "file": relative, "line": lines.line(match.start()), "authority": "static-candidate"})
    endpoints: list[dict[str, Any]] = []
    for match in _FETCH_RE.finditer(text):
        if len(endpoints) >= 60:
            break
        endpoints.append({"url": match.group("url"), "file": relative, "line": lines.line(match.start())})
    maps = [{"file": relative, "line": lines.line(match.start()), "url": match.group(1)} for match in _SOURCE_MAP_RE.finditer(text)][:8]
    return {
        "imports": imports,
        "unresolved": unresolved,
        "routes": routes,
        "endpoints": endpoints,
        "sourceMaps": maps,
        "facts": _module_facts(text, lines),
        "lines": text.count("\n") + 1,
        "characters": len(text),
    }


def _walk_tree(root: Path, include_node_modules: bool, max_files: int) -> tuple[list[Path], list[dict[str, str]], bool]:
    selected: list[Path] = []
    skipped: list[dict[str, str]] = []
    limited = False
    resolved_root = root.resolve()
    for directory, directories, files in os.walk(resolved_root, followlinks=False):
        kept_directories: list[str] = []
        for name in sorted(directories):
            if name.startswith(".") or (Path(directory) / name).is_symlink():
                continue
            if name == "node_modules" and not include_node_modules:
                if len(skipped) < 200:
                    skipped.append({"path": (Path(directory) / name).relative_to(resolved_root).as_posix(), "reason": "node_modules-excluded"})
                continue
            kept_directories.append(name)
        directories[:] = kept_directories
        for name in sorted(files):
            if len(selected) >= max_files:
                limited = True
                break
            if name.startswith("."):
                continue
            candidate = Path(directory) / name
            if candidate.is_symlink() or candidate.suffix.lower() not in ARTIFACT_EXTENSIONS:
                continue
            try:
                relative = candidate.relative_to(resolved_root)
            except ValueError:
                continue
            if candidate.stat().st_size > MAX_JS_FILE_BYTES:
                skipped.append({"path": relative.as_posix(), "reason": "file-too-large"})
                if len(skipped) >= 200:
                    break
                continue
            selected.append(candidate)
        if limited or len(skipped) >= 200:
            break
    return selected, skipped, limited


def analyze_javascript(files_root: Path, path_value: str, source: str = "", include_node_modules: bool = False, max_files: int = 500) -> dict[str, Any]:
    if bool(path_value) == bool(source):
        raise ReverseError("Informe exatamente um alvo: um caminho na área reversa ou um código-fonte colado.")
    if source:
        if len(source.encode("utf-8")) > MAX_JS_FILE_BYTES:
            raise ReverseError("O código colado excede o limite de 1,5 MB.")
        relative = "inline-source.js"
        lines = _LineIndex(source)
        module = _analyze_source(relative, source, lines, Path(), Path(relative), resolve_imports=False)
        return {
            "analysis": "javascript",
            "mode": "inline",
            "target": {"path": relative, "bytes": len(source.encode("utf-8")), "sha256": _hash(source.encode("utf-8")), "files": 1, "digestScope": "inline-source"},
            "modules": [{
                "path": relative, "language": "javascript", "bytes": len(source.encode("utf-8")),
                "lines": module["lines"], "imports": module["imports"], "unresolved": module["unresolved"],
                "facts": module["facts"], "routes": module["routes"], "endpoints": module["endpoints"],
                "sourceMaps": module["sourceMaps"],
            }],
            "relationships": [],
            "unresolved": module["unresolved"],
            "routes": module["routes"],
            "endpoints": module["endpoints"],
            "facts": module["facts"],
            "entryCandidates": [],
            "package": None,
            "coverage": {"analyzedFiles": 1, "skipped": [], "bytesRead": len(source.encode("utf-8")), "limitReached": False},
            "executed": False,
            "limitations": [*_JAVASCRIPT_LIMITATIONS, "No modo inline não há resolução de caminhos relativos."],
        }

    target = artifact_directory(files_root, path_value) if safe_path(reverse_root(files_root), path_value, allow_root=False).is_dir() else artifact_file(files_root, path_value)
    root = target if target.is_dir() else target.parent
    if target.is_dir():
        selected, skipped, limited = _walk_tree(root, include_node_modules, max_files)
    else:
        selected, skipped, limited = [target], [], False
    modules: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    all_unresolved: list[dict[str, Any]] = []
    all_routes: list[dict[str, Any]] = []
    all_endpoints: list[dict[str, Any]] = []
    all_facts: list[dict[str, Any]] = []
    total_bytes = 0
    package: dict[str, Any] | None = None
    html_references: list[dict[str, str]] = []
    coverage_limit = limited
    tree_digest = hashlib.sha256()

    for file_path in selected:
        if total_bytes >= MAX_JS_TOTAL_BYTES:
            coverage_limit = True
            skipped.append({"path": file_path.relative_to(root.resolve()).as_posix(), "reason": "total-byte-limit"})
            break
        suffix = file_path.suffix.lower()
        relative = file_path.relative_to(root.resolve()).as_posix()
        if suffix != ".json" and suffix not in JAVASCRIPT_EXTENSIONS | {".html", ".htm"}:
            continue
        data = file_path.read_bytes()
        if total_bytes + len(data) > MAX_JS_TOTAL_BYTES:
            coverage_limit = True
            skipped.append({"path": relative, "reason": "total-byte-limit"})
            continue
        tree_digest.update(relative.encode("utf-8"))
        tree_digest.update(hashlib.sha256(data).digest())
        if suffix == ".json":
            total_bytes += len(data)
            if file_path.name == "package.json":
                try:
                    manifest = json.loads(data.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    all_unresolved.append({"file": relative, "specifier": "package.json", "reason": "invalid-json", "line": 1})
                    continue
                if isinstance(manifest, dict):
                    dependencies = manifest.get("dependencies")
                    dev_dependencies = manifest.get("devDependencies")
                    package = {
                        "name": manifest.get("name"),
                        "version": manifest.get("version"),
                        "main": manifest.get("main"),
                        "type": manifest.get("type"),
                        "dependencies": sorted(dependencies)[:100] if isinstance(dependencies, dict) else [],
                        "devDependencies": sorted(dev_dependencies)[:100] if isinstance(dev_dependencies, dict) else [],
                        "scriptNames": sorted(manifest.get("scripts", {}))[:50] if isinstance(manifest.get("scripts"), dict) else [],
                    }
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            skipped.append({"path": relative, "reason": "invalid-utf8"})
            continue
        total_bytes += len(data)
        lines = _LineIndex(text)
        if suffix in {".html", ".htm"}:
            for match in _HTML_SCRIPT_RE.finditer(text):
                html_references.append({"file": relative, "reference": match.group("src"), "kind": "script"})
            for match in _HTML_LINK_RE.finditer(text):
                html_references.append({"file": relative, "reference": match.group("href"), "kind": "link"})
            continue
        module = _analyze_source(relative, text, lines, root.resolve(), file_path)
        modules.append({
            "path": relative,
            "language": "typescript" if suffix in {".ts", ".tsx"} else "javascript",
            "bytes": len(data),
            "lines": module["lines"],
            "imports": module["imports"],
            "facts": module["facts"][:24],
            "routes": module["routes"][:24],
            "endpoints": module["endpoints"][:12],
            "sourceMaps": module["sourceMaps"],
        })
        if len(relationships) < 600:
            for item in module["imports"]:
                if item["target"] and len(relationships) < 600:
                    relationships.append({"from": relative, "to": item["target"], "specifier": item["specifier"], "kind": item["kind"]})
        if len(all_unresolved) < 300:
            all_unresolved.extend(module["unresolved"][: 300 - len(all_unresolved)])
        if len(all_routes) < 300:
            all_routes.extend(module["routes"][: 300 - len(all_routes)])
        if len(all_endpoints) < 200:
            all_endpoints.extend(module["endpoints"][: 200 - len(all_endpoints)])
        if len(all_facts) < 600:
            all_facts.extend({**fact, "file": relative} for fact in module["facts"][: 600 - len(all_facts)])

    entry_candidates: list[dict[str, str]] = []
    if package and isinstance(package.get("main"), str):
        entry_candidates.append({"path": package["main"], "reason": "package.json main"})
    analyzed_paths = {module["path"] for module in modules}
    for candidate in ("main.js", "index.js", "electron.js", "preload.js", "main.cjs", "main.mjs"):
        if candidate in analyzed_paths:
            entry_candidates.append({"path": candidate, "reason": "nome convencional"})
    for reference in html_references:
        candidate = reference["reference"].lstrip("./")
        if candidate in analyzed_paths:
            entry_candidates.append({"path": candidate, "reason": f"referência HTML ({reference['kind']})"})
    deduplicated: dict[str, dict[str, str]] = {}
    for item in entry_candidates:
        deduplicated.setdefault(item["path"], item)
    entry_candidates = list(deduplicated.values())

    language_counts = Counter(module["language"] for module in modules)
    identity_target = {
        "path": path_value,
        "files": len(modules),
        "bytesRead": total_bytes,
        "sha256": tree_digest.hexdigest() if target.is_dir() else _hash_file(target),
        "digestScope": "analyzed-content" if target.is_dir() else "file-content",
    }
    return {
        "analysis": "javascript",
        "mode": "tree" if target.is_dir() else "file",
        "target": identity_target,
        "modules": modules[:max_files],
        "relationships": relationships[:600],
        "unresolved": all_unresolved[:200],
        "routes": all_routes[:200],
        "endpoints": all_endpoints[:120],
        "facts": all_facts[:300],
        "entryCandidates": entry_candidates[:20],
        "package": package,
        "htmlReferences": html_references[:100],
        "languages": dict(language_counts),
        "coverage": {
            "analyzedFiles": len(modules),
            "skipped": skipped[:200],
            "bytesRead": total_bytes,
            "limitReached": coverage_limit,
            "maxFiles": max_files,
        },
        "executed": False,
        "limitations": _JAVASCRIPT_LIMITATIONS,
    }


# ---------------------------------------------------------------- comparação


def compare_artifacts(files_root: Path, left_path: str, right_path: str) -> dict[str, Any]:
    left_file = artifact_file(files_root, left_path)
    right_file = artifact_file(files_root, right_path)
    left_data = _read(left_file)
    right_data = _read(right_file)
    left_identity = _identity(left_file, left_path, left_data)
    right_identity = _identity(right_file, right_path, right_data)
    left_parsed = _parse(left_data, left_file)
    right_parsed = _parse(right_data, right_file)
    limitations = [
        "A comparação é estática: diferenças não são prova de mudança de comportamento nem de causalidade.",
        "Somente estruturas e strings amostradas são comparadas; ausência em uma lista limitada não prova ausência no artefato.",
    ]
    result: dict[str, Any] = {
        "analysis": "compare",
        "left": left_identity,
        "right": right_identity,
        "identical": left_identity["sha256"] == right_identity["sha256"],
        "sizeDelta": right_identity["bytes"] - left_identity["bytes"],
        "comparable": left_parsed["kind"] == right_parsed["kind"],
        "leftKind": left_parsed["kind"],
        "rightKind": right_parsed["kind"],
        "sections": None,
        "entries": None,
        "imports": None,
        "strings": None,
        "entropy": {
            "left": _byte_entropy(left_data),
            "right": _byte_entropy(right_data),
        },
        "executed": False,
        "limitations": limitations,
    }
    if left_parsed["kind"] == right_parsed["kind"] and left_parsed["sections"]:
        left_sections = {section["name"]: section for section in left_parsed["sections"] if section.get("name")}
        right_sections = {section["name"]: section for section in right_parsed["sections"] if section.get("name")}
        added = sorted(set(right_sections) - set(left_sections))[:40]
        removed = sorted(set(left_sections) - set(right_sections))[:40]
        changed = sorted(
            name for name in set(left_sections) & set(right_sections)
            if (left_sections[name].get("size"), left_sections[name].get("offset")) != (right_sections[name].get("size"), right_sections[name].get("offset"))
        )[:40]
        result["sections"] = {"added": added, "removed": removed, "changed": changed}
    if left_parsed["kind"] == right_parsed["kind"] and left_parsed["entries"]:
        left_names = {entry["name"] for entry in left_parsed["entries"]}
        right_names = {entry["name"] for entry in right_parsed["entries"]}
        result["entries"] = {
            "added": sorted(right_names - left_names)[:40],
            "removed": sorted(left_names - right_names)[:40],
            "leftCount": len(left_names),
            "rightCount": len(right_names),
        }
    if left_parsed["imports"] or right_parsed["imports"]:
        left_imports = {item["library"] for item in left_parsed["imports"]}
        right_imports = {item["library"] for item in right_parsed["imports"]}
        result["imports"] = {
            "added": sorted(right_imports - left_imports)[:40],
            "removed": sorted(left_imports - right_imports)[:40],
        }
    left_strings = _sample_strings(left_data)
    right_strings = _sample_strings(right_data)
    added_strings = sorted(right_strings - left_strings)
    removed_strings = sorted(left_strings - right_strings)
    result["strings"] = {
        "added": added_strings[:20],
        "removed": removed_strings[:20],
        "addedCount": len(added_strings),
        "removedCount": len(removed_strings),
        "sampled": True,
    }
    if left_identity["sha256"] == right_identity["sha256"]:
        result["limitations"] = ["Os arquivos têm o mesmo SHA-256 e são idênticos byte a byte; caminhos diferentes não mudam a identidade.", *limitations]
    return result


def _sample_strings(data: bytes, limit: int = 400) -> set[str]:
    values: set[str] = set()
    for match in re.finditer(rb"[\x20-\x7e]{8,}", data):
        values.add(match.group().decode("ascii"))
        if len(values) >= limit:
            break
    return values
