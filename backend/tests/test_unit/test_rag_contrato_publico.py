"""Fase 89 — mapeamento do shape interno de retrieve() pro contrato público do rag_search."""
from app.api.v1.rag import _para_contrato_publico


def test_mapeia_text_para_content_e_payload_para_metadata():
    interno = [
        {"collection": "jurisprudencia", "score": 0.91, "text": "trecho do acórdão",
         "payload": {"tribunal": "STJ", "numero_processo": "123"}, "id": "abc"},
    ]
    out = _para_contrato_publico(interno)
    assert out == [
        {"id": "abc", "score": 0.91, "collection": "jurisprudencia",
         "content": "trecho do acórdão", "metadata": {"tribunal": "STJ", "numero_processo": "123"}},
    ]


def test_payload_ausente_vira_metadata_vazio():
    out = _para_contrato_publico([{"collection": "doutrina", "score": 0.6, "text": "x", "id": "1"}])
    assert out[0]["metadata"] == {}


def test_lista_vazia():
    assert _para_contrato_publico([]) == []
