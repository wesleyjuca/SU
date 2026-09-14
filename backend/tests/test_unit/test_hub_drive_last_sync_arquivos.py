"""Achado real (validação da pasta Doutrina — Fase pós-258): `GET
.../last-sync` só devolvia o agregado (`processados`/`pulados`/`falhas`) —
o erro real de CADA arquivo já era gravado em `JurisprudenciaIngerida.erro`,
mas nenhum endpoint o expunha. `GET .../last-sync/arquivos` devolve os
arquivos mais recentes deste tenant com o motivo real de cada falha."""
import uuid
from datetime import datetime, timezone

import pytest

from app.api.v1.integrations_hub import hub_drive_doutrina_last_sync_arquivos


class _FakeScalarsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows
        self.last_query = None

    async def execute(self, query):
        self.last_query = query
        return _FakeScalarsResult(self._rows)


class _FakeUser:
    def __init__(self, tenant_id):
        self.tenant_id = tenant_id


class _FakeLinha:
    def __init__(self, fonte_documento_id, metadata_extraida, status, erro, processed_at):
        self.fonte_documento_id = fonte_documento_id
        self.metadata_extraida = metadata_extraida
        self.status = status
        self.erro = erro
        self.processed_at = processed_at


@pytest.mark.asyncio
async def test_sem_arquivos_devolve_lista_vazia():
    db = _FakeDB([])
    result = await hub_drive_doutrina_last_sync_arquivos(current_user=_FakeUser(uuid.uuid4()), db=db)
    assert result == {"arquivos": []}


@pytest.mark.asyncio
async def test_expoe_erro_real_do_arquivo_falhou():
    now = datetime.now(timezone.utc)
    linha = _FakeLinha(
        "file-123",
        {"nome_arquivo": "manual.pdf", "google_file_id": "file-123", "caminho_pasta": "Civil"},
        "FALHOU",
        "Busca vetorial indisponível: OPENAI_API_KEY não configurada.",
        now,
    )
    db = _FakeDB([linha])
    result = await hub_drive_doutrina_last_sync_arquivos(current_user=_FakeUser(uuid.uuid4()), db=db)

    assert len(result["arquivos"]) == 1
    arq = result["arquivos"][0]
    assert arq["google_file_id"] == "file-123"
    assert arq["nome_arquivo"] == "manual.pdf"
    assert arq["caminho_pasta"] == "Civil"
    assert arq["status"] == "FALHOU"
    assert arq["erro"] == "Busca vetorial indisponível: OPENAI_API_KEY não configurada."
    assert arq["processed_at"] is not None


@pytest.mark.asyncio
async def test_arquivo_embedded_sem_erro():
    linha = _FakeLinha(
        "file-456", {"nome_arquivo": "doutrina.docx", "google_file_id": "file-456", "caminho_pasta": ""},
        "EMBEDDED", None, datetime.now(timezone.utc),
    )
    db = _FakeDB([linha])
    result = await hub_drive_doutrina_last_sync_arquivos(current_user=_FakeUser(uuid.uuid4()), db=db)

    assert result["arquivos"][0]["status"] == "EMBEDDED"
    assert result["arquivos"][0]["erro"] is None
    assert result["arquivos"][0]["caminho_pasta"] == ""


@pytest.mark.asyncio
async def test_metadata_ausente_nao_quebra():
    linha = _FakeLinha("file-789", None, "PENDENTE", None, None)
    db = _FakeDB([linha])
    result = await hub_drive_doutrina_last_sync_arquivos(current_user=_FakeUser(uuid.uuid4()), db=db)

    assert result["arquivos"][0]["nome_arquivo"] is None
    assert result["arquivos"][0]["caminho_pasta"] == ""
    assert result["arquivos"][0]["processed_at"] is None


# ─── Fase pós-265 — tradução amigável do erro por arquivo ────────────────────
# O corpo de erro 429 do provedor de embeddings chegava VERBATIM à tela, em
# vermelho, pra um advogado. `friendly_detail` já existia pro card de status,
# mas (a) não tinha padrão pra cota e (b) nunca era aplicada aqui.


@pytest.mark.asyncio
async def test_erro_de_cota_chega_traduzido_e_o_cru_e_preservado():
    cru = (
        '{"error": {"code": 429, "message": "You exceeded your current quota, '
        'please check your plan and billing details.", "status": "RESOURCE_EXHAUSTED"}}'
    )
    linha = _FakeLinha("f1", {"nome_arquivo": "eca-2025.pdf"}, "FALHOU", cru, datetime.now(timezone.utc))
    arq = (await hub_drive_doutrina_last_sync_arquivos(
        current_user=_FakeUser(uuid.uuid4()), db=_FakeDB([linha]),
    ))["arquivos"][0]

    assert arq["erro"] == cru, "o texto técnico continua no payload, pra suporte"
    assert "cota" in arq["erro_amigavel"].lower()
    assert "429" not in arq["erro_amigavel"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status, texto", [
    # Aviso de sucesso parcial, escrito pelo próprio sistema.
    ("EMBEDDED", "3 de 267 página(s) falharam no OCR — o arquivo foi indexado com o texto das demais."),
    # Achado real da verificação desta fase: uma FALHA cuja mensagem também é
    # nossa e já é acionável. O fallback genérico a embrulhava em "Não foi
    # possível identificar a causa exata do erro (...)", piorando o que já
    # estava claro.
    ("FALHOU", "OCR indisponível no servidor (pdfplumber/pytesseract ou o binário "
               "do tesseract não estão instalados) — PDFs escaneados não podem ser lidos."),
])
async def test_mensagem_ja_escrita_pelo_sistema_nao_e_embrulhada(status, texto):
    linha = _FakeLinha("f2", {"nome_arquivo": "vade-mecum.pdf"}, status, texto, datetime.now(timezone.utc))
    arq = (await hub_drive_doutrina_last_sync_arquivos(
        current_user=_FakeUser(uuid.uuid4()), db=_FakeDB([linha]),
    ))["arquivos"][0]

    assert arq["erro"] == texto
    assert arq["erro_amigavel"] is None, "sem padrão casado, não inventa tradução"
