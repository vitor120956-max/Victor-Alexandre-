"""OCR: ler PDF escaneado e foto de página com o motor que a máquina tiver.

O problema real: livro digitalizado é imagem, e sem OCR não sai texto. O
Windows 10 1607 do projeto tem três caminhos possíveis, e nenhum deles é
garantido — então esta camada **detecta** em vez de exigir:

1. **Tesseract** — programa externo (UB Mannheim), roda offline, funciona no
   1607. É o recomendado. O `pytesseract` só faz a ponte; sem o executável não
   adianta.
2. **Windows.Media.Ocr** (pacote `winocr`) — só existe a partir do Windows 10
   build 15063; no 1607 **não** está disponível.
3. **RapidOCR/onnxruntime** — depende de `onnxruntime`, que não publica wheel
   para Python 3.15; fica como terceira opção para quem tiver outra versão.

Sem nenhum dos três, a camada diz exatamente o que instalar e para de prometer.
Rasterizar PDF usa `pypdfium2` (wheel pura, instala com `pip` e não precisa de
compilador).
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

VARIAVEL = "JARVIS_TESSERACT"
MAX_PAGINAS = 40
DPI = 200
MINIMO_TEXTO_POR_PAGINA = 40

CAMINHOS_TESSERACT = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe"),
)

INSTRUCOES = (
    "Para ler PDF escaneado e foto de página, instale o Tesseract OCR "
    "(Windows, UB Mannheim), marque o idioma Portuguese na instalação e reinicie a API. "
    "Depois: .venv\\Scripts\\pip install pytesseract pypdfium2. "
    "Se você instalou em outra pasta, aponte com JARVIS_TESSERACT=C:\\...\\tesseract.exe no .env."
)


class OcrError(ValueError):
    """OCR pedido mas indisponível, ou imagem que não pôde ser lida."""


# ------------------------------------------------------------------- detecção

def caminho_tesseract() -> str | None:
    """Onde está o executável do Tesseract, se estiver nesta máquina."""
    da_variavel = (os.environ.get(VARIAVEL) or "").strip()
    if da_variavel and Path(da_variavel).is_file():
        return da_variavel
    achado = shutil.which("tesseract")
    if achado:
        return achado
    for candidato in CAMINHOS_TESSERACT:
        if candidato and Path(candidato).is_file():
            return candidato
    # cópia portátil ao lado do projeto, para quem não tem admin
    for relativo in ("tesseract/tesseract.exe", "ferramentas/tesseract/tesseract.exe"):
        portatil = Path(__file__).resolve().parent.parent / relativo
        if portatil.is_file():
            return str(portatil)
    return None


@lru_cache(maxsize=1)
def _idiomas_tesseract(executavel: str) -> tuple[str, ...]:
    try:
        saida = subprocess.run(
            [executavel, "--list-langs"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    linhas = [linha.strip() for linha in (saida.stdout or "").splitlines()]
    return tuple(linha for linha in linhas if linha and "available languages" not in linha.lower())


def _idioma_preferido(executavel: str, pedido: str = "por") -> str:
    disponiveis = _idiomas_tesseract(executavel)
    if not disponiveis:
        return pedido
    if pedido in disponiveis:
        return pedido
    if "eng" in disponiveis:
        return "eng"
    return disponiveis[0]


def _motor_tesseract() -> tuple[str, Callable[..., str]] | None:
    executavel = caminho_tesseract()
    if not executavel:
        return None
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return None

    pytesseract.pytesseract.tesseract_cmd = executavel
    idioma = _idioma_preferido(executavel)

    def extrair(dados: bytes, _idioma: str = idioma) -> str:
        imagem = Image.open(io.BytesIO(dados))
        return pytesseract.image_to_string(imagem, lang=_idioma)

    return "tesseract", extrair


def _motor_winocr() -> tuple[str, Callable[..., str]] | None:
    if sys.platform != "win32":
        return None
    try:
        from winocr import recognize_pil_sync  # type: ignore
        from PIL import Image
    except Exception:
        return None

    def extrair(dados: bytes, idioma: str = "pt-BR") -> str:
        imagem = Image.open(io.BytesIO(dados))
        resultado = recognize_pil_sync(imagem, idioma)
        return getattr(resultado, "text", "") or ""

    return "winocr", extrair


def _motor_rapidocr() -> tuple[str, Callable[..., str]] | None:
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore
    except Exception:
        return None
    engine = RapidOCR()

    def extrair(dados: bytes, idioma: str = "por") -> str:
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as arquivo:
            arquivo.write(dados)
            caminho = arquivo.name
        try:
            resultado, _ = engine(caminho)
        finally:
            Path(caminho).unlink(missing_ok=True)
        linhas = [item[1] for item in (resultado or []) if len(item) >= 2]
        return "\n".join(linhas)

    return "rapidocr", extrair


def motor() -> tuple[str, Callable[..., str]] | None:
    """Primeiro motor disponível, na ordem de qualidade/portabilidade."""
    for fabrica in (_motor_tesseract, _motor_winocr, _motor_rapidocr):
        achado = fabrica()
        if achado is not None:
            return achado
    return None


def status() -> dict[str, Any]:
    """O que existe nesta máquina e o que fazer se não houver nada."""
    achado = motor()
    executavel = caminho_tesseract()
    return {
        "disponivel": achado is not None,
        "motor": achado[0] if achado else None,
        "tesseract": executavel,
        "tesseract_em": executavel,
        "idiomas": list(_idiomas_tesseract(executavel)) if executavel else [],
        "pypdfium2": _tem_pdfium(),
        "instrucoes": None if achado else INSTRUCOES,
        "limite_paginas": MAX_PAGINAS,
        "dpi": DPI,
    }


# ----------------------------------------------------------------- rasterizar

def _tem_pdfium() -> bool:
    try:
        import pypdfium2  # noqa: F401
    except Exception:
        return False
    return True


def renderizar_pdf(caminho: str | Path, *, paginas: int = MAX_PAGINAS, dpi: int = DPI) -> list[tuple[int, bytes]]:
    """Converte as páginas do PDF em PNG, para o motor de OCR ler."""
    if not _tem_pdfium():
        raise OcrError(
            "Falta o `pypdfium2` para transformar a página em imagem. "
            "Rode: .venv\\Scripts\\pip install pypdfium2"
        )
    import pypdfium2 as pdfium

    alvo = Path(caminho)
    if not alvo.is_file():
        raise OcrError("PDF não encontrado.")
    try:
        documento = pdfium.PdfDocument(str(alvo))
    except Exception as exc:
        raise OcrError(f"PDF ilegível para rasterizar ({type(exc).__name__}).") from exc

    if len(documento) == 0:
        raise OcrError("O PDF não tem páginas.")
    limite = max(1, min(paginas, len(documento)))
    escalas = dpi / 72
    saida: list[tuple[int, bytes]] = []
    for indice in range(limite):
        pagina = documento[indice]
        imagem = pagina.render(scale=escalas).to_pil()
        buffer = io.BytesIO()
        imagem.save(buffer, format="PNG")
        saida.append((indice + 1, buffer.getvalue()))
    return saida


# ---------------------------------------------------------------------- extrair

def extrair_imagem(dados: bytes, *, idioma: str = "por") -> str:
    """Texto de uma imagem (PNG/JPG), com o motor disponível."""
    achado = motor()
    if achado is None:
        raise OcrError(INSTRUCOES)
    _, extrair = achado
    try:
        texto = extrair(dados, idioma)
    except Exception as exc:
        raise OcrError(f"O OCR falhou nesta imagem ({type(exc).__name__}).") from exc
    return (texto or "").strip()


def extrair_pdf(caminho: str | Path, *, paginas: int = MAX_PAGINAS, dpi: int = DPI) -> list[tuple[int, str]]:
    """OCR página por página. Devolve `(número da página, texto)` só do que saiu."""
    achado = motor()
    if achado is None:
        raise OcrError(INSTRUCOES)
    blocos: list[tuple[int, str]] = []
    for numero, png in renderizar_pdf(caminho, paginas=paginas, dpi=dpi):
        try:
            texto = extrair_imagem(png)
        except OcrError:
            continue
        if texto:
            blocos.append((numero, texto))
    if not blocos:
        raise OcrError("O OCR não encontrou texto legível nas páginas lidas.")
    return blocos


def precisa_ocr(texto: str, paginas: int = 1) -> bool:
    """Quase nenhum texto por página: é digitalização, não livro curto.

    O corte é baixo de propósito (40 caracteres por página): página escaneada
    devolve zero, enquanto PDF de texto — mesmo com capa e folha de rosto —
    passa fácil. Livro digitalizado com uma linha de cabeçalho por página
    continua precisando de OCR, e o usuário pode forçar com `usar_ocr`.
    """
    return len(texto.strip()) < MINIMO_TEXTO_POR_PAGINA * max(1, paginas)
