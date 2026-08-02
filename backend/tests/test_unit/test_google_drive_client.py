"""Fase 138.2 — cliente do Google Drive: parsing de URL/ID de pasta (puro,
vários formatos plausíveis), fail-soft de rede, e dispatch de extração de
texto por mimeType."""
import pytest

from app.integrations.google_drive.client import (
    extrair_folder_id, listar_arquivos, extrair_texto, _MIME_DOCX, _MIME_PDF,
)


def test_extrair_folder_id_url_completa():
    url = "https://drive.google.com/drive/folders/1a2B3c4D5e6F7g8H9i0J"
    assert extrair_folder_id(url) == "1a2B3c4D5e6F7g8H9i0J"


def test_extrair_folder_id_url_com_usuario_e_query():
    url = "https://drive.google.com/drive/u/0/folders/1a2B3c4D5e6F7g8H9i0J?usp=sharing"
    assert extrair_folder_id(url) == "1a2B3c4D5e6F7g8H9i0J"


def test_extrair_folder_id_id_cru():
    assert extrair_folder_id("1a2B3c4D5e6F7g8H9i0J") == "1a2B3c4D5e6F7g8H9i0J"


def test_extrair_folder_id_com_espacos_ao_redor():
    assert extrair_folder_id("  1a2B3c4D5e6F7g8H9i0J  ") == "1a2B3c4D5e6F7g8H9i0J"


def test_extrair_folder_id_invalido():
    assert extrair_folder_id("") is None
    assert extrair_folder_id("não é nem url nem id") is None
    assert extrair_folder_id("curto") is None  # menor que o mínimo de um ID real


def test_extrair_folder_id_url_de_arquivo_nao_de_pasta():
    # /file/d/... não é uma pasta — não deve casar com o padrão de pasta
    assert extrair_folder_id("https://drive.google.com/file/d/1a2B3c4D5e6F7g8H9i0J/view") is None


@pytest.mark.asyncio
async def test_listar_arquivos_rede_indisponivel_retorna_none(monkeypatch):
    import httpx

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            raise httpx.ConnectError("sem rede")

    monkeypatch.setattr(httpx, "AsyncClient", lambda **k: _FakeClient())
    assert await listar_arquivos("token-fake", "folder-fake") is None


@pytest.mark.asyncio
async def test_extrair_texto_docx(monkeypatch):
    import app.utils.docx_text as docx_mod
    monkeypatch.setattr(docx_mod, "extract_docx_text", lambda raw: "texto do docx")
    texto = await extrair_texto(_MIME_DOCX, b"conteudo-fake")
    assert texto == "texto do docx"


@pytest.mark.asyncio
async def test_extrair_texto_docx_vazio_vira_none(monkeypatch):
    import app.utils.docx_text as docx_mod
    monkeypatch.setattr(docx_mod, "extract_docx_text", lambda raw: "")
    assert await extrair_texto(_MIME_DOCX, b"conteudo-fake") is None


@pytest.mark.asyncio
async def test_extrair_texto_pdf_via_ocr_agent(monkeypatch):
    from app.agents.base.result import AgentResult, AgentStatus
    import app.agents.ocr.ocr_agent as ocr_mod

    async def _fake_execute(self, ctx):
        return AgentResult(status=AgentStatus.SUCCESS, agent_name="ocr_agent", output={"texto_extraido": "texto do pdf"})

    monkeypatch.setattr(ocr_mod.OCRAgent, "execute", _fake_execute)
    texto = await extrair_texto(_MIME_PDF, b"conteudo-fake")
    assert texto == "texto do pdf"


@pytest.mark.asyncio
async def test_extrair_texto_pdf_ocr_indisponivel_vira_none(monkeypatch):
    from app.agents.base.result import AgentResult, AgentStatus
    import app.agents.ocr.ocr_agent as ocr_mod

    async def _fake_execute(self, ctx):
        return AgentResult(status=AgentStatus.SUCCESS, agent_name="ocr_agent", output={"texto_extraido": ocr_mod.OCRAgent.UNAVAILABLE})

    monkeypatch.setattr(ocr_mod.OCRAgent, "execute", _fake_execute)
    assert await extrair_texto(_MIME_PDF, b"conteudo-fake") is None


@pytest.mark.asyncio
async def test_extrair_texto_tipo_nao_suportado():
    assert await extrair_texto("application/vnd.ms-excel", b"x") is None
    assert await extrair_texto(None, b"x") is None
    assert await extrair_texto(_MIME_DOCX, b"") is None
