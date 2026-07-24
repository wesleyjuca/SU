"""Fase 86 — coluna `fonte` first-class em LegalProcess (lógica, sem DB real)."""
import inspect

from app.models.process import LegalProcess


def test_legal_process_tem_coluna_fonte():
    """SQLAlchemy permite construir o objeto Python sem conexão — confirma que
    o atributo existe e aceita o valor esperado."""
    proc = LegalProcess(tribunal="TJSP", fonte="OAB")
    assert proc.fonte == "OAB"
    proc2 = LegalProcess(tribunal="TJSP", fonte="MANUAL")
    assert proc2.fonte == "MANUAL"
    # default é None (processos antigos, antes do backfill)
    proc3 = LegalProcess(tribunal="TJSP")
    assert proc3.fonte is None


def test_captura_por_oab_seta_fonte_oab():
    """Guarda de regressão: o ponto de criação da captura automática deve
    continuar passando fonte='OAB' (evita reintroduzir o dado morto em
    metadata_json sem promovê-lo à coluna)."""
    from app.services import oab_capture
    src = inspect.getsource(oab_capture.capturar_por_oab)
    assert 'fonte="OAB"' in src
    # a chave redundante não deve voltar para o metadata_json
    assert '"fonte_captura"' not in src


def test_criar_processo_manual_seta_fonte_manual():
    """Guarda de regressão: o endpoint de cadastro manual deve continuar
    passando fonte='MANUAL'."""
    from app.api.v1 import processes
    src = inspect.getsource(processes.create_process)
    assert 'fonte="MANUAL"' in src


def test_process_response_expoe_fonte():
    from app.api.v1.processes import ProcessResponse, _to_response
    assert "fonte" in ProcessResponse.model_fields
    proc = LegalProcess(tribunal="TJCE", fonte="OAB")
    resp = _to_response(proc)
    assert resp.fonte == "OAB"
