"""Testes do OCR (0.47.0): motor, imagem e PDF escaneado.

O sandbox não tem Tesseract instalado, então o motor é **falso** e injetado por
monkeypatch. O que fica testado de verdade: detecção, mensagem de instalação,
rasterizar o PDF com `pypdfium2`, o corte de páginas e a ligação com a
biblioteca (imagem e PDF sem texto).
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest

pytest.importorskip("pypdfium2")

from server import biblioteca, ocr
from server.ocr import OcrError


def _motor_falso(chamadas: list[bytes] | None = None):
    def extrair(imagem: bytes, _idioma: str = "por") -> str:
        if chamadas is not None:
            chamadas.append(imagem)
        return "Texto lido do papel: rateio de custo indireto entre produtos."

    return ("tesseract-falso", extrair)


def _pdf_de_texto(texto: str = "") -> bytes:
    reportlab = pytest.importorskip("reportlab")
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pagina = canvas.Canvas(buffer, pagesize=A4)
    if texto:
        pagina.drawString(72, 760, texto)
    pagina.showPage()
    pagina.save()
    return buffer.getvalue()


def test_precisa_ocr_por_pagina():
    assert ocr.precisa_ocr("", 3) is True
    assert ocr.precisa_ocr("x" * 10, 3) is True
    assert ocr.precisa_ocr("a" * 400, 3) is False


def test_sem_motor_o_status_explica_como_instalar(monkeypatch):
    monkeypatch.setattr(ocr, "motor", lambda: None)
    monkeypatch.setattr(ocr, "caminho_tesseract", lambda: None)
    situacao = ocr.status()
    assert situacao["disponivel"] is False
    assert situacao["motor"] is None
    assert situacao["instrucoes"] and "tesseract" in situacao["instrucoes"].lower()
    assert situacao["limite_paginas"] == ocr.MAX_PAGINAS


def test_extrair_imagem_sem_motor_recusa(monkeypatch):
    monkeypatch.setattr(ocr, "motor", lambda: None)
    with pytest.raises(OcrError) as erro:
        ocr.extrair_imagem(b"\x89PNG")
    assert "tesseract" in str(erro.value).lower()


def test_extrair_imagem_com_motor_falso(monkeypatch):
    vistos: list[bytes] = []
    monkeypatch.setattr(ocr, "motor", lambda: _motor_falso(vistos))
    texto = ocr.extrair_imagem(b"\x89PNG-falso")
    assert "rateio" in texto
    assert vistos == [b"\x89PNG-falso"]


def test_renderizar_pdf_devolve_png_por_pagina(tmp_path):
    alvo = tmp_path / "scan.pdf"
    alvo.write_bytes(_pdf_de_texto())
    paginas = ocr.renderizar_pdf(alvo)
    assert len(paginas) == 1
    numero, imagem = paginas[0]
    assert numero == 1
    assert imagem.startswith(b"\x89PNG")


def test_renderizar_pdf_respeita_o_limite(tmp_path):
    reportlab = pytest.importorskip("reportlab")
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pagina = canvas.Canvas(buffer, pagesize=A4)
    for _ in range(3):
        pagina.drawString(72, 760, "pagina sem texto")
        pagina.showPage()
    pagina.save()
    alvo = tmp_path / "tres.pdf"
    alvo.write_bytes(buffer.getvalue())

    assert len(ocr.renderizar_pdf(alvo)) == 3
    assert len(ocr.renderizar_pdf(alvo, paginas=2)) == 2
    assert reportlab is not None


def test_renderizar_pdf_inexistente():
    with pytest.raises(OcrError):
        ocr.renderizar_pdf("/nao/existe.pdf")


def test_extrair_pdf_usa_o_motor_pagina_a_pagina(tmp_path, monkeypatch):
    alvo = tmp_path / "scan.pdf"
    alvo.write_bytes(_pdf_de_texto())
    monkeypatch.setattr(ocr, "motor", lambda: _motor_falso())
    paginas = ocr.extrair_pdf(alvo)
    assert len(paginas) == 1
    assert paginas[0][0] == 1
    assert "rateio" in paginas[0][1]


def test_biblioteca_importa_imagem_com_ocr(tmp_path, monkeypatch):
    monkeypatch.setattr(biblioteca.dados, "raiz", lambda: tmp_path)
    monkeypatch.setattr(ocr, "motor", lambda: _motor_falso())
    foto = tmp_path / "pagina.jpg"
    foto.write_bytes(b"\xff\xd8\xff-foto")
    fonte = biblioteca.importar(foto, titulo="Foto do rateio")
    assert fonte["tipo"] == "imagem"
    assert fonte["secoes"] == 1
    achados = biblioteca.buscar("rateio custo indireto", limite=3)
    assert achados and "rateio" in achados[0]["trecho"].lower()


def test_biblioteca_recusa_imagem_sem_motor(tmp_path, monkeypatch):
    monkeypatch.setattr(biblioteca.dados, "raiz", lambda: tmp_path)
    monkeypatch.setattr(ocr, "motor", lambda: None)
    foto = tmp_path / "pagina.png"
    foto.write_bytes(b"\x89PNG-foto")
    with pytest.raises(biblioteca.BibliotecaError) as erro:
        biblioteca.importar(foto)
    assert "tesseract" in str(erro.value).lower()


def test_biblioteca_manda_pdf_sem_texto_para_o_ocr(tmp_path, monkeypatch):
    monkeypatch.setattr(biblioteca.dados, "raiz", lambda: tmp_path)
    monkeypatch.setattr(ocr, "motor", lambda: _motor_falso())
    alvo = tmp_path / "escaneado.pdf"
    alvo.write_bytes(_pdf_de_texto())
    fonte = biblioteca.importar(alvo, titulo="Escaneado")
    assert fonte["secoes"] == 1
    achados = biblioteca.buscar("rateio", limite=2)
    assert achados and "rateio" in achados[0]["trecho"].lower()


def test_biblioteca_pdf_sem_texto_sem_motor_explica(tmp_path, monkeypatch):
    monkeypatch.setattr(biblioteca.dados, "raiz", lambda: tmp_path)
    monkeypatch.setattr(ocr, "motor", lambda: None)
    alvo = tmp_path / "escaneado.pdf"
    alvo.write_bytes(_pdf_de_texto())
    with pytest.raises(biblioteca.BibliotecaError) as erro:
        biblioteca.importar(alvo)
    mensagem = str(erro.value)
    assert "escane" in mensagem.lower()
    assert "tesseract" in mensagem.lower()


def test_pdf_de_texto_nao_passa_pelo_ocr(tmp_path, monkeypatch):
    monkeypatch.setattr(biblioteca.dados, "raiz", lambda: tmp_path)
    monkeypatch.setattr(ocr, "motor", lambda: (_ for _ in ()).throw(AssertionError("não deveria chamar")))
    alvo = tmp_path / "texto.pdf"
    alvo.write_bytes(
        _pdf_de_texto(
            "Rateio de custo indireto: a despesa comum e distribuida entre os produtos "
            "fabricados conforme o criterio escolhido pela contabilidade da empresa."
        )
    )
    fonte = biblioteca.importar(alvo)
    assert fonte["secoes"] >= 1
