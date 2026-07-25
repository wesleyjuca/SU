"""Fase 100 — rate limit dedicado pra geração de petição/contrato (chamam LLM
pago sem gate de papel; antes caíam no "default" genérico por IP)."""
from app.core.middleware import (
    _is_contract_generate_path,
    PETITION_GENERATE_PATH,
    RATE_LIMIT_RULES,
)


def test_petition_generate_path_e_exato():
    assert PETITION_GENERATE_PATH == "/api/v1/documents/petitions/generate"


def test_contract_generate_path_com_segmento_dinamico():
    assert _is_contract_generate_path("/api/v1/documents/contracts/abc-123/generate")
    assert _is_contract_generate_path("/api/v1/documents/contracts/" + "x" * 40 + "/generate")


def test_contract_generate_path_nao_confunde_outras_rotas_de_documents():
    assert not _is_contract_generate_path("/api/v1/documents/contracts/create")
    assert not _is_contract_generate_path("/api/v1/documents/contracts/abc/enviar-assinatura")
    assert not _is_contract_generate_path("/api/v1/documents/petitions/generate")
    assert not _is_contract_generate_path("/api/v1/documents")


def test_regra_documents_generate_existe_e_e_mais_restrita_que_default():
    assert "documents_generate" in RATE_LIMIT_RULES
    limit_generate, _ = RATE_LIMIT_RULES["documents_generate"]
    limit_default, _ = RATE_LIMIT_RULES["default"]
    assert limit_generate < limit_default
