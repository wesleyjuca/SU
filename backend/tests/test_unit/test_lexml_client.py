"""Fase 93 — cliente LexML: parsing tolerante da resposta SRU (XML mockado)."""
import pytest

from app.integrations.lexml.client import _parsear_resposta, buscar_lei


def test_parsear_resposta_encontrada():
    xml = """<?xml version="1.0"?>
    <searchRetrieveResponse xmlns="http://www.loc.gov/zing/srw/">
      <numberOfRecords>1</numberOfRecords>
      <records>
        <record>
          <recordData>
            <title>Código de Defesa do Consumidor</title>
            <urn>urn:lex:br:federal:lei:1990-09-11;8078</urn>
          </recordData>
        </record>
      </records>
    </searchRetrieveResponse>"""
    r = _parsear_resposta(xml)
    assert r == {
        "encontrado": True,
        "titulo": "Código de Defesa do Consumidor",
        "urn": "urn:lex:br:federal:lei:1990-09-11;8078",
    }


def test_parsear_resposta_nao_encontrada():
    xml = '<searchRetrieveResponse><numberOfRecords>0</numberOfRecords></searchRetrieveResponse>'
    r = _parsear_resposta(xml)
    assert r == {"encontrado": False, "titulo": None, "urn": None}


def test_parsear_resposta_xml_quebrado_retorna_none():
    assert _parsear_resposta("isso não é XML <<<") is None
    assert _parsear_resposta("") is None


def test_parsear_resposta_sem_number_of_records_retorna_none():
    assert _parsear_resposta("<root><foo>bar</foo></root>") is None


@pytest.mark.asyncio
async def test_buscar_lei_rede_indisponivel_retorna_none(monkeypatch):
    import httpx

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            raise httpx.ConnectError("sem rede")

    monkeypatch.setattr(httpx, "AsyncClient", lambda **k: _FakeClient())

    resultado = await buscar_lei("8078/1990")
    assert resultado is None
