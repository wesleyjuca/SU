"""Parsing de data URL (`data:<content-type>;base64,<dados>`) — usado pelo
caminho legado de armazenamento de Document.arquivo_url (Fase 141: bytes
inline em base64 no Postgres, pré-migração pra object storage) tanto pelo
OCR (app/workers/tasks/ocr_tasks.py) quanto pelo endpoint de download do
arquivo original (app/api/v1/documents.py)."""


def parse_data_url(value: str) -> tuple[str | None, str | None]:
    """Devolve (base64_puro, content_type) a partir de um data URL
    `data:<ct>;base64,<dados>`. Retorna (None, None) se não reconhecer."""
    if not value or not value.startswith("data:"):
        return None, None
    try:
        header, b64 = value.split(",", 1)
    except ValueError:
        return None, None
    # header = "data:application/pdf;base64"
    ct = header[len("data:"):].split(";", 1)[0] or None
    return b64, ct
