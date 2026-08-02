"""Fase 138.4 — validação de `desfecho` em ProcessCreate/ProcessUpdate
(achado incidental: só o endpoint de arquivamento validava a whitelist;
ProcessCreate/ProcessUpdate aceitavam qualquer string sem validação)."""
import pytest
from pydantic import ValidationError

from app.api.v1.processes import ProcessCreate, ProcessUpdate, _DESFECHOS_VALIDOS


def test_desfechos_validos_constante():
    assert _DESFECHOS_VALIDOS == {"EXITO", "PARCIAL", "ACORDO", "DERROTA"}


@pytest.mark.parametrize("desfecho", ["EXITO", "PARCIAL", "ACORDO", "DERROTA", None])
def test_process_create_aceita_desfecho_valido(desfecho):
    p = ProcessCreate(tribunal="TJSP", desfecho=desfecho)
    assert p.desfecho == desfecho


def test_process_create_rejeita_desfecho_invalido():
    with pytest.raises(ValidationError, match="desfecho inválido"):
        ProcessCreate(tribunal="TJSP", desfecho="GANHOU")


@pytest.mark.parametrize("desfecho", ["EXITO", "PARCIAL", "ACORDO", "DERROTA", None])
def test_process_update_aceita_desfecho_valido(desfecho):
    p = ProcessUpdate(desfecho=desfecho)
    assert p.desfecho == desfecho


def test_process_update_rejeita_desfecho_invalido():
    with pytest.raises(ValidationError, match="desfecho inválido"):
        ProcessUpdate(desfecho="PERDEU")


def test_process_create_aceita_tese_id():
    p = ProcessCreate(tribunal="TJSP", tese_id="11111111-1111-1111-1111-111111111111")
    assert p.tese_id == "11111111-1111-1111-1111-111111111111"


def test_process_update_aceita_tese_id_none():
    p = ProcessUpdate(tese_id=None)
    assert p.tese_id is None
