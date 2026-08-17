"""Fase 199 — prova que os 3 guards de efeito externo real (assinatura
eletrônica, e-mail, link de pagamento) cortam ANTES de qualquer I/O de rede
quando o tenant é o de demonstração — não só que capturam a exceção do
provedor real. `demo_guard.tenant_is_demo` é monkeypatchado (não criamos um
Tenant real aqui — isso é coberto empiricamente + em test_demo_reset.py),
o que também prova que os 3 serviços de fato chamam o guard antes de
qualquer outra coisa."""
import uuid

import pytest
from fastapi import HTTPException

import app.services.demo_guard as demo_guard_mod

pytestmark = pytest.mark.asyncio


async def _sempre_demo(db, tenant_id):
    return True


class _RedeNaoDeveriaSerChamada:
    def __init__(self, *a, **k):
        raise AssertionError("chamada de rede não deveria acontecer — guard deveria ter cortado antes")


async def test_enviar_para_assinatura_bloqueia_sem_tocar_clicksign(monkeypatch):
    from app.services import esign

    monkeypatch.setattr(demo_guard_mod, "tenant_is_demo", _sempre_demo)
    monkeypatch.setattr(esign.httpx, "AsyncClient", _RedeNaoDeveriaSerChamada)

    with pytest.raises(HTTPException) as exc_info:
        await esign.enviar_para_assinatura(
            db=None, tenant_id=uuid.uuid4(), doc=None, contract=None,
            signatario_email="cliente@exemplo.com", signatario_nome="Cliente Teste",
        )
    assert exc_info.value.status_code == 422
    assert "demonstração" in exc_info.value.detail.lower()


async def test_criar_link_pagamento_bloqueia_sem_tocar_gateway(monkeypatch):
    from app.services import payment_gateway

    monkeypatch.setattr(demo_guard_mod, "tenant_is_demo", _sempre_demo)
    monkeypatch.setattr(payment_gateway.httpx, "AsyncClient", _RedeNaoDeveriaSerChamada)

    with pytest.raises(HTTPException) as exc_info:
        await payment_gateway.criar_link_pagamento(db=None, tenant_id=uuid.uuid4(), inv=None)
    assert exc_info.value.status_code == 422
    assert "demonstração" in exc_info.value.detail.lower()


async def test_send_email_bloqueia_sem_tocar_gmail_ou_smtp(monkeypatch):
    from app.services import email as email_mod

    monkeypatch.setattr(demo_guard_mod, "tenant_is_demo", _sempre_demo)
    monkeypatch.setattr(email_mod.smtplib, "SMTP", _RedeNaoDeveriaSerChamada)

    async def _gmail_nao_deveria_ser_chamado(*a, **k):
        raise AssertionError("gmail_send não deveria ser chamado — guard deveria ter cortado antes")
    monkeypatch.setattr("app.services.google_workspace.gmail_send", _gmail_nao_deveria_ser_chamado)

    resultado = await email_mod.send_email(
        to="cliente@exemplo.com", subject="Teste", html_body="<p>oi</p>",
        db=object(), tenant_id=uuid.uuid4(),
    )
    assert resultado is False
