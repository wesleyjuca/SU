"""Fase pós-262 — `JuditFonte.descobrir_por_oab` (nova). Judit suporta busca
por OAB oficialmente (`docs.judit.io`, `search_type: "oab"`), mas é
ASSÍNCRONA: `POST /requests` cria a busca e devolve `request_id`; os
resultados aparecem via `GET /responses?request_id=...`, sem prazo fixo pra
"completar". Testa o poll curto e limitado com um fake `httpx.AsyncClient`."""
from datetime import date

import pytest

import app.integrations.fontes.judit_fonte as judit_mod
from app.integrations.fontes.judit_fonte import JuditFonte


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}

    def json(self):
        return self._json_data


class _FakeAsyncClient:
    """Fake httpx.AsyncClient roteirizado: `post_response` pro POST
    /requests, `get_responses` (lista, uma por chamada de poll) pro GET
    /responses — permite simular "resultado só aparece na 2ª tentativa"."""

    def __init__(self, *, post_response, get_responses, captured, **kwargs):
        self._post_response = post_response
        self._get_responses = list(get_responses)
        self._captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, headers=None, json=None):
        self._captured.setdefault("posts", []).append({"url": url, "json": json})
        return self._post_response

    async def get(self, url, headers=None, params=None):
        self._captured.setdefault("gets", []).append({"url": url, "params": params})
        if self._get_responses:
            return self._get_responses.pop(0)
        return _FakeResponse(200, json_data={})


def _patch_client(monkeypatch, *, post_response, get_responses):
    captured: dict = {}

    def _factory(*a, **kwargs):
        return _FakeAsyncClient(post_response=post_response, get_responses=get_responses,
                                captured=captured, **kwargs)

    monkeypatch.setattr(judit_mod.httpx, "AsyncClient", _factory)
    return captured


@pytest.fixture(autouse=True)
def _sem_intervalo_real(monkeypatch):
    """Poll usa `asyncio.sleep(_OAB_POLL_INTERVALO_S)` entre tentativas —
    sem isso o teste levaria ~6s de verdade. Zera o intervalo (não a
    função `asyncio.sleep` em si, pra não afetar o resto do processo de
    teste), sem mudar o número de tentativas/lógica de poll."""
    monkeypatch.setattr(judit_mod, "_OAB_POLL_INTERVALO_S", 0)


@pytest.mark.asyncio
async def test_descobrir_por_oab_search_key_formato_uf_numero(monkeypatch):
    captured = _patch_client(
        monkeypatch,
        post_response=_FakeResponse(200, json_data={"request_id": "req-1"}),
        get_responses=[_FakeResponse(200, json_data={"page_data": [{"code": "00012345620268060001"}]})],
    )

    fonte = JuditFonte(token="tok")
    resultado = await fonte.descobrir_por_oab("123456", "sp", date(2026, 1, 1), date(2026, 7, 1))

    assert captured["posts"][0]["json"] == {"search": {"search_type": "oab", "search_key": "SP123456"}}
    assert len(resultado) == 1
    assert resultado[0].numero_cnj == "00012345620268060001"
    assert resultado[0].fonte == "judit"


@pytest.mark.asyncio
async def test_descobrir_por_oab_resultado_so_aparece_apos_poll(monkeypatch):
    """Prova nos 2 sentidos: se o código não fizer poll (só 1 tentativa),
    este teste falharia (o 1º GET vem vazio)."""
    _patch_client(
        monkeypatch,
        post_response=_FakeResponse(200, json_data={"request_id": "req-2"}),
        get_responses=[
            _FakeResponse(200, json_data={"page_data": []}),  # ainda processando
            _FakeResponse(200, json_data={"page_data": [{"lawsuit": {"numero_cnj": "9999999-99.2026.8.06.0001"}}]}),
        ],
    )

    fonte = JuditFonte(token="tok")
    resultado = await fonte.descobrir_por_oab("123456", "CE", date(2026, 1, 1), date(2026, 7, 1))

    assert len(resultado) == 1
    assert resultado[0].numero_cnj == "99999999920268060001"


@pytest.mark.asyncio
async def test_descobrir_por_oab_sem_request_id_devolve_vazio(monkeypatch):
    _patch_client(monkeypatch, post_response=_FakeResponse(200, json_data={}), get_responses=[])

    fonte = JuditFonte(token="tok")
    resultado = await fonte.descobrir_por_oab("123456", "CE", date(2026, 1, 1), date(2026, 7, 1))
    assert resultado == []


@pytest.mark.asyncio
async def test_descobrir_por_oab_falha_http_no_post_devolve_vazio_fail_soft(monkeypatch):
    _patch_client(monkeypatch, post_response=_FakeResponse(500), get_responses=[])

    fonte = JuditFonte(token="tok")
    resultado = await fonte.descobrir_por_oab("123456", "CE", date(2026, 1, 1), date(2026, 7, 1))
    assert resultado == []


@pytest.mark.asyncio
async def test_descobrir_por_oab_nenhuma_tentativa_de_poll_traz_resultado(monkeypatch):
    """Poll esgota as tentativas sem achar nada → [] (fail-soft, não trava
    esperando indefinidamente)."""
    _patch_client(
        monkeypatch,
        post_response=_FakeResponse(200, json_data={"request_id": "req-3"}),
        get_responses=[_FakeResponse(200, json_data={"page_data": []})] * 10,
    )

    fonte = JuditFonte(token="tok")
    resultado = await fonte.descobrir_por_oab("123456", "CE", date(2026, 1, 1), date(2026, 7, 1))
    assert resultado == []


@pytest.mark.asyncio
async def test_descobrir_por_oab_dedup_por_cnj(monkeypatch):
    _patch_client(
        monkeypatch,
        post_response=_FakeResponse(200, json_data={"request_id": "req-4"}),
        get_responses=[_FakeResponse(200, json_data={"page_data": [
            {"code": "00012345620268060001"},
            {"response_data": {"cnj": "0001234-56.2026.8.06.0001"}},  # mesmo CNJ, mascarado
        ]})],
    )

    fonte = JuditFonte(token="tok")
    resultado = await fonte.descobrir_por_oab("123456", "CE", date(2026, 1, 1), date(2026, 7, 1))
    assert len(resultado) == 1
