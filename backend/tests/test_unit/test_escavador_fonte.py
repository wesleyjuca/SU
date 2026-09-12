"""Fase pós-262 — `EscavadorFonte.descobrir_por_oab` nunca era chamada por
`oab_capture.py` (só nesta fase passa a ser ligada como fonte alternativa de
descoberta por OAB) — por isso o path/params desatualizados em relação à doc
oficial atual nunca foram exercitados em produção. Confirma o contrato novo:
`GET /api/v2/advogado/processos` (singular) com `numero`/`estado`."""
from datetime import date

import pytest

import app.integrations.fontes.escavador_fonte as escavador_mod
from app.integrations.fontes.escavador_fonte import EscavadorFonte


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}

    def json(self):
        return self._json_data


class _FakeAsyncClient:
    """Fake httpx.AsyncClient — captura url/params/headers do único GET."""

    def __init__(self, *, response, captured, **kwargs):
        self._response = response
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, headers=None, params=None):
        self._captured["url"] = url
        self._captured["headers"] = headers
        self._captured["params"] = params
        return self._response


def _patch_client(monkeypatch, *, response):
    captured: dict = {}

    def _factory(*a, **kwargs):
        return _FakeAsyncClient(response=response, captured=captured, **kwargs)

    monkeypatch.setattr(escavador_mod.httpx, "AsyncClient", _factory)
    return captured


@pytest.mark.asyncio
async def test_descobrir_por_oab_usa_endpoint_e_params_atuais(monkeypatch):
    captured = _patch_client(monkeypatch, response=_FakeResponse(200, json_data={"data": []}))

    fonte = EscavadorFonte(token="tok")
    await fonte.descobrir_por_oab("123456", "sp", date(2026, 1, 1), date(2026, 7, 1))

    assert captured["url"] == "https://api.escavador.com/api/v2/advogado/processos"
    assert captured["params"] == {"numero": "123456", "estado": "SP"}
    # os nomes antigos (plural, oab_numero/oab_estado) não podem mais aparecer.
    assert "advogados" not in captured["url"]


@pytest.mark.asyncio
async def test_descobrir_por_oab_normaliza_e_dedup_por_cnj(monkeypatch):
    _patch_client(monkeypatch, response=_FakeResponse(200, json_data={"data": [
        {"numero_cnj": "0001234-56.2026.8.06.0001", "tribunal": "TJCE"},
        {"numeroProcesso": "0001234-56.2026.8.06.0001"},  # mesmo CNJ, chave alternativa
        {"numero": "0009999-99.2026.8.06.0001"},
    ]}))

    fonte = EscavadorFonte(token="tok")
    resultado = await fonte.descobrir_por_oab("123456", "CE", date(2026, 1, 1), date(2026, 7, 1))

    cnjs = sorted(p.numero_cnj for p in resultado)
    assert cnjs == ["00012345620268060001", "00099999920268060001"]
    assert all(p.fonte == "escavador" for p in resultado)


@pytest.mark.asyncio
async def test_descobrir_por_oab_sem_token_ou_sem_oab_devolve_vazio():
    assert await EscavadorFonte(token="").descobrir_por_oab("123", "SP", None, None) == []
    assert await EscavadorFonte(token="tok").descobrir_por_oab("", "SP", None, None) == []
    assert await EscavadorFonte(token="tok").descobrir_por_oab("123", "", None, None) == []
