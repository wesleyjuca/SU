"""Fase 184 — heurística de PII (CPF/CNPJ-like) usada pelo aviso antes do
export financeiro pro Google Sheets: puramente a função de regex, sem DB
(o comportamento fim-a-fim do endpoint é coberto empiricamente em
test_api/test_google_docs_sheets_export.py)."""
from types import SimpleNamespace

from app.api.v1.financial import _CPF_CNPJ_LIKE_RE, _descricoes_com_possivel_pii


def test_cpf_com_pontuacao_e_detectado():
    assert _CPF_CNPJ_LIKE_RE.search("Pagamento a Fulano CPF 123.456.789-01")


def test_cpf_sem_pontuacao_e_detectado():
    assert _CPF_CNPJ_LIKE_RE.search("Pagamento a Fulano CPF 12345678901")


def test_cnpj_com_pontuacao_e_detectado():
    assert _CPF_CNPJ_LIKE_RE.search("Honorários da empresa 12.345.678/0001-95")


def test_cnpj_sem_pontuacao_e_detectado():
    assert _CPF_CNPJ_LIKE_RE.search("Honorários da empresa 12345678000195")


def test_descricao_sem_padrao_nao_e_detectada():
    assert not _CPF_CNPJ_LIKE_RE.search("Pagamento de aluguel do escritório em agosto")


def test_numero_curto_nao_e_falso_positivo():
    # nº de processo, valores, datas — não devem casar com o padrão de 11/14 dígitos
    assert not _CPF_CNPJ_LIKE_RE.search("Processo 12345 - parcela 3 de 12, venc. 15/08/2026")


def test_descricoes_com_possivel_pii_filtra_so_as_que_batem():
    entries = [
        SimpleNamespace(descricao="Aluguel de agosto"),
        SimpleNamespace(descricao="Pagamento CPF 123.456.789-01"),
        SimpleNamespace(descricao=None),
        SimpleNamespace(descricao="Honorários 12.345.678/0001-95"),
    ]
    achou = _descricoes_com_possivel_pii(entries)
    assert achou == ["Pagamento CPF 123.456.789-01", "Honorários 12.345.678/0001-95"]
