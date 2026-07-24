"""Fase 91 — sincronização best-effort de prazos com o Google Agenda (Google mockado)."""
import pytest
from datetime import date

from app.services.deadline_calendar import sincronizar_prazo_no_google


class _FakeDeadline:
    id = "d1"
    tipo = "CONTESTACAO"
    descricao = "Contestação: processo X"
    data_prazo = date(2026, 8, 1)


@pytest.mark.asyncio
async def test_sincroniza_com_sucesso(monkeypatch):
    import app.services.google_workspace as gw

    chamada = {}

    async def _fake_get_valid_token(db, user_id):
        return "TOKEN"

    async def _fake_create(token, titulo, descricao, data):
        chamada["token"] = token
        chamada["titulo"] = titulo
        chamada["data"] = data
        return {"id": "evt1", "link": "https://calendar.google.com/evt1"}

    monkeypatch.setattr(gw, "get_valid_token", _fake_get_valid_token)
    monkeypatch.setattr(gw, "calendar_create_allday_event", _fake_create)

    await sincronizar_prazo_no_google(db=None, deadline=_FakeDeadline(), user_id="u1")

    assert chamada["token"] == "TOKEN"
    assert "CONTESTACAO" in chamada["titulo"]
    assert chamada["data"] == date(2026, 8, 1)


@pytest.mark.asyncio
async def test_sem_google_conectado_nao_propaga(monkeypatch):
    import app.services.google_workspace as gw

    async def _sem_conexao(db, user_id):
        raise gw.GoogleNotConnected("sem conta conectada")

    monkeypatch.setattr(gw, "get_valid_token", _sem_conexao)

    # Não deve levantar — comportamento idêntico ao atual (sem Google, sem evento).
    await sincronizar_prazo_no_google(db=None, deadline=_FakeDeadline(), user_id="u1")


@pytest.mark.asyncio
async def test_erro_generico_nao_propaga(monkeypatch):
    import app.services.google_workspace as gw

    async def _erro(db, user_id):
        raise RuntimeError("timeout de rede")

    monkeypatch.setattr(gw, "get_valid_token", _erro)

    await sincronizar_prazo_no_google(db=None, deadline=_FakeDeadline(), user_id="u1")
