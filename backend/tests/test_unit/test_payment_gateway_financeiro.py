"""Fase 129 — conecta pagamento confirmado ao financeiro (FinancialEntry) e
evita perder o rastro de dinheiro real quando a fatura não está mais EMITIDA."""
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.financial import BillingInvoice
from app.services.payment_gateway import _criar_entrada_financeira, _marcar_paga


def _fake_invoice(status="EMITIDA", valor_total=Decimal("500.00")):
    inv = BillingInvoice(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        client_id=uuid.uuid4(),
        process_id=None,
        numero="FAT-202607-ABC123",
        valor_total=valor_total,
        status=status,
    )
    return inv


def test_criar_entrada_financeira_campos_basicos():
    inv = _fake_invoice()
    entry = _criar_entrada_financeira(inv, "stripe")
    assert entry.tipo == "RECEITA"
    assert entry.categoria == "HONORARIOS"
    assert entry.valor == Decimal("500.00")
    assert entry.status == "PAGO"
    assert entry.client_id == inv.client_id
    assert entry.tenant_id == inv.tenant_id
    assert "stripe" in entry.descricao


def test_criar_entrada_financeira_com_nota_de_reconciliacao():
    inv = _fake_invoice(status="CANCELADA")
    entry = _criar_entrada_financeira(inv, "mercadopago", nota="fatura estava CANCELADA")
    assert "fatura estava CANCELADA" in entry.descricao


class _FakeResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        m = MagicMock()
        m.all.return_value = self._items
        return m


@pytest.mark.asyncio
async def test_marcar_paga_ja_paga_e_idempotente(monkeypatch):
    db = AsyncMock()
    inv = _fake_invoice(status="PAGA")
    resultado = await _marcar_paga(db, inv, "stripe")
    assert resultado == {"processed": True, "reason": "já estava paga (idempotente)"}
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_marcar_paga_emitida_cria_financial_entry_e_flipa_status():
    db = AsyncMock()
    inv = _fake_invoice(status="EMITIDA")
    resultado = await _marcar_paga(db, inv, "stripe")
    assert resultado["processed"] is True
    assert inv.status == "PAGA"
    assert inv.pago_em is not None
    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.tipo == "RECEITA"
    assert added.valor == inv.valor_total
    db.flush.assert_awaited()


@pytest.mark.asyncio
async def test_marcar_paga_fatura_cancelada_nao_perde_o_pagamento(monkeypatch):
    """Fase 129 — antes desta fase, esse caminho só logava e descartava o
    pagamento confirmado pelo gateway, sem deixar nenhum rastro no sistema."""
    db = AsyncMock()
    db.execute.return_value = _FakeResult([])  # nenhum ADMIN/SOCIO pra notificar
    inv = _fake_invoice(status="CANCELADA")

    resultado = await _marcar_paga(db, inv, "mercadopago")

    assert resultado["processed"] is False
    assert "reconciliação" in resultado["reason"]
    # fatura NÃO é reaberta automaticamente — só o dinheiro fica registrado
    assert inv.status == "CANCELADA"
    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.tipo == "RECEITA"
    assert "CANCELADA" in added.descricao
    db.flush.assert_awaited()


@pytest.mark.asyncio
async def test_marcar_paga_cancelada_notifica_admin_socio(monkeypatch):
    db = AsyncMock()
    admin_id = uuid.uuid4()
    socio_id = uuid.uuid4()
    db.execute.return_value = _FakeResult([admin_id, socio_id])

    publicados = []

    async def _fake_publish(notif):
        publicados.append(notif.user_id)

    import app.services.payment_gateway as pg_mod
    monkeypatch.setattr(
        "app.services.notification.publish_notification_ws", _fake_publish,
    )

    inv = _fake_invoice(status="CANCELADA")
    await pg_mod._marcar_paga(db, inv, "stripe")

    assert set(publicados) == {admin_id, socio_id}
    # 2 usuários notificados + 1 FinancialEntry = 3 db.add
    assert db.add.call_count == 3
