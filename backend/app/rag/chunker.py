"""Chunking jurídico-aware para documentos legais brasileiros."""
import re
from typing import Any


_SECTION_PATTERNS = [
    r"^(?:CAPÍTULO|SEÇÃO|SUBSEÇÃO|TÍTULO)\s+[IVXLCDM\d]+",
    r"^\d+\.\s+[A-ZÁÉÍÓÚÂÊÎÔÛÀÃÕÇ]",
    r"^(?:Art\.|Artigo)\s+\d+",
    r"^(?:CONCLUSÃO|DISPOSITIVO|DO PEDIDO|DA FUNDAMENTAÇÃO|DOS FATOS|DO DIREITO)",
]
_SECTION_RE = re.compile("|".join(_SECTION_PATTERNS), re.MULTILINE | re.IGNORECASE)

CHUNK_SIZE = 800
CHUNK_OVERLAP = 100


def chunk_document(text: str, metadata: dict[str, Any]) -> list[dict]:
    """Divide texto em chunks preservando seções jurídicas."""
    text = text.strip()
    if not text:
        return []

    sections = _split_by_sections(text)
    chunks: list[dict] = []

    for section in sections:
        section = section.strip()
        if not section:
            continue
        if len(section) <= CHUNK_SIZE:
            chunks.append(section)
        else:
            chunks.extend(_sliding_window(section))

    total = len(chunks)
    return [
        {"text": c, "index": i, "total": total}
        for i, c in enumerate(chunks)
        if c.strip()
    ]


def _split_by_sections(text: str) -> list[str]:
    boundaries = [m.start() for m in _SECTION_RE.finditer(text)]
    if not boundaries:
        return [text]

    sections = []
    prev = 0
    for b in boundaries:
        if b > prev:
            sections.append(text[prev:b])
        prev = b
    sections.append(text[prev:])
    return [s for s in sections if s.strip()]


def _sliding_window(text: str) -> list[str]:
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + CHUNK_SIZE, len(words))
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        if end >= len(words):
            break
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks
