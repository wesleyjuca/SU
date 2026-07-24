"""Fase 90 — send_prazo_alert repassa db/sender_user_id pro send_email (wiring do Gmail)."""
import pytest

from app.services import email as email_mod


@pytest.mark.asyncio
async def test_send_prazo_alert_repassa_credenciais_gmail(monkeypatch):
    capturado = {}

    async def _fake_send_email(to, subject, html_body, text_body=None, db=None, sender_user_id=None):
        capturado["to"] = to
        capturado["db"] = db
        capturado["sender_user_id"] = sender_user_id
        return True

    monkeypatch.setattr(email_mod, "send_email", _fake_send_email)

    ok = await email_mod.send_prazo_alert(
        to_email="advogado@afj.com.br",
        descricao="Contestação",
        dias=3,
        data_prazo="2026-08-01",
        process_id="123",
        db="DB_SESSION",
        sender_user_id="USER_ID",
    )

    assert ok is True
    assert capturado["to"] == "advogado@afj.com.br"
    assert capturado["db"] == "DB_SESSION"
    assert capturado["sender_user_id"] == "USER_ID"


@pytest.mark.asyncio
async def test_send_prazo_alert_sem_credenciais_mantem_compatibilidade(monkeypatch):
    capturado = {}

    async def _fake_send_email(to, subject, html_body, text_body=None, db=None, sender_user_id=None):
        capturado["db"] = db
        capturado["sender_user_id"] = sender_user_id
        return True

    monkeypatch.setattr(email_mod, "send_email", _fake_send_email)

    ok = await email_mod.send_prazo_alert(
        to_email="advogado@afj.com.br",
        descricao="Contestação",
        dias=3,
        data_prazo="2026-08-01",
    )

    assert ok is True
    assert capturado["db"] is None
    assert capturado["sender_user_id"] is None
