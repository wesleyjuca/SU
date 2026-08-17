"""Fase 199 — ponto único de verdade para "este tenant é o tenant público de
demonstração?", usado pelos serviços que disparam efeito externo real
(assinatura eletrônica, e-mail, link de pagamento) e pelo endpoint de teto de
IA, pra bloquear esses efeitos sem tocar em cada call site."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def tenant_is_demo(db: AsyncSession, tenant_id) -> bool:
    if not tenant_id:
        return False
    from app.models.tenant import Tenant

    return bool((await db.execute(
        select(Tenant.is_demo).where(Tenant.id == tenant_id)
    )).scalar_one_or_none())
