"""Fase pós-265 — 2 achados reais no OCRAgent, confirmados por leitura de
código e reproduzíveis aqui:

1. `except ImportError` não capturava `pytesseract.TesseractNotFoundError`
   (que herda de `EnvironmentError`/`OSError`, não de `ImportError`). Com as
   libs instaladas e o BINÁRIO do tesseract ausente — exatamente o estado
   deste sandbox, `which tesseract` não encontra nada — a exceção subia, o
   agente devolvia FAILED, e o arquivo virava um erro genérico que não dizia
   que faltava o binário no servidor.
2. `_ocr_pdf` não isolava página: uma única página que estourava derrubava o
   PDF inteiro (foi o que aconteceu com o Vade Mecum em produção). Agora cada
   página é isolada, a contagem sobe no `output`, e o chamador indexa o que
   deu reportando o resto.
"""
import base64

import pytest

from app.agents.base.result import AgentStatus
from app.agents.brain.context import AgentContext
from app.agents.ocr.ocr_agent import OCRAgent


class _FakePage:
    """Página que sempre força o caminho de OCR (`extract_text` vazio)."""

    def __init__(self, texto_ocr: str | None = None, explode: Exception | None = None):
        self._texto_ocr = texto_ocr
        self._explode = explode

    def extract_text(self):
        return None  # curto demais → cai no OCR, é o caminho que interessa

    def to_image(self, resolution=300):
        if self._explode is not None:
            raise self._explode

        class _Img:
            original = object()

        return _Img()


class _FakePdf:
    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _ctx() -> AgentContext:
    return AgentContext(
        task_type="ocr_document",
        task_input={
            "file_bytes_b64": base64.b64encode(b"%PDF-fake").decode(),
            "content_type": "application/pdf",
        },
    )


def _patch_pdf(monkeypatch, pages):
    import pdfplumber

    monkeypatch.setattr(pdfplumber, "open", lambda source: _FakePdf(pages))


@pytest.mark.asyncio
async def test_tesseract_ausente_vira_unavailable_nao_excecao(monkeypatch):
    """Prova do achado 1: sem o binário do tesseract, o agente devolve
    SUCCESS + o placeholder UNAVAILABLE (que o chamador sabe traduzir), não
    um FAILED com traceback de `TesseractNotFoundError`."""
    import pytesseract

    def _sem_binario(img, lang=None):
        raise pytesseract.TesseractNotFoundError()

    monkeypatch.setattr(pytesseract, "image_to_string", _sem_binario)
    _patch_pdf(monkeypatch, [_FakePage(), _FakePage()])

    result = await OCRAgent(db=None).execute(_ctx())

    assert result.status == AgentStatus.SUCCESS
    assert result.output["texto_extraido"] == OCRAgent.UNAVAILABLE


@pytest.mark.asyncio
async def test_uma_pagina_ruim_nao_derruba_o_pdf_inteiro(monkeypatch):
    """Prova do achado 2: a 2ª de 3 páginas estoura; as outras 2 são lidas e
    a contagem de falhas chega ao `output`."""
    import pytesseract

    monkeypatch.setattr(pytesseract, "image_to_string", lambda img, lang=None: "texto ok")
    _patch_pdf(monkeypatch, [
        _FakePage(),
        _FakePage(explode=ValueError("página corrompida")),
        _FakePage(),
    ])

    result = await OCRAgent(db=None).execute(_ctx())

    assert result.status == AgentStatus.SUCCESS
    assert result.output["texto_extraido"] == "texto ok\n\ntexto ok"
    assert result.output["paginas_falhas"] == 1
    assert result.output["paginas_total"] == 3


@pytest.mark.asyncio
async def test_todas_as_paginas_falhando_devolve_texto_vazio_com_contagem(monkeypatch):
    """Caso extremo: nada foi extraído, mas a contagem permite ao chamador
    dizer "falhou em todas as N páginas" em vez de "sem texto extraível"."""
    import pytesseract

    monkeypatch.setattr(pytesseract, "image_to_string", lambda img, lang=None: "irrelevante")
    _patch_pdf(monkeypatch, [_FakePage(explode=RuntimeError("boom")) for _ in range(4)])

    result = await OCRAgent(db=None).execute(_ctx())

    assert result.status == AgentStatus.SUCCESS
    assert result.output["texto_extraido"] == ""
    assert result.output["paginas_falhas"] == 4
    assert result.output["paginas_total"] == 4


@pytest.mark.asyncio
async def test_pdf_sem_pagina_ruim_nao_reporta_falha(monkeypatch):
    """Regressão: o caminho normal continua sem nenhum aviso."""
    import pytesseract

    monkeypatch.setattr(pytesseract, "image_to_string", lambda img, lang=None: "conteúdo")
    _patch_pdf(monkeypatch, [_FakePage(), _FakePage()])

    result = await OCRAgent(db=None).execute(_ctx())

    assert result.output["paginas_falhas"] == 0
    assert result.output["paginas_total"] == 2
    assert result.output["caracteres"] > 0
