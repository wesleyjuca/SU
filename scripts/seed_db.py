#!/usr/bin/env python3
"""Seed completo do banco — 2 tenants, 4 usuários/tenant, dados fictícios.

Fase 199: reescrito para ser idempotente (get-or-create por slug/e-mail) —
antes rodar de novo duplicava tenants/usuários sem checar existência. Passou
a existir porque o tenant `demo` também é chamado programaticamente pelo
serviço de reset periódico (`app/services/demo_reset.py`), não só uma vez
manualmente."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.db.base import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User
from app.models.tenant import Tenant, TenantConfig
from app.services.demo_fixtures import DEMO_ADMIN_EMAIL, DEMO_ADMIN_SENHA, criar_elenco_demo, gerar_dados_ficticios


async def _get_or_create_tenant(db, slug: str, **kwargs) -> tuple[Tenant, bool]:
    existing = (await db.execute(select(Tenant).where(Tenant.slug == slug))).scalar_one_or_none()
    if existing:
        return existing, False
    tenant = Tenant(slug=slug, **kwargs)
    db.add(tenant)
    await db.flush()
    return tenant, True


async def _get_or_create_user(db, email: str, **kwargs) -> User:
    existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing:
        return existing
    user = User(email=email, **kwargs)
    db.add(user)
    await db.flush()
    return user


async def seed():
    async with AsyncSessionLocal() as db:
        print("Iniciando seed...")

        # ── Tenant AFJ ───────────────────────────────────────────────────────
        tenant_afj, afj_novo = await _get_or_create_tenant(
            db, "afj", name="Almeida, Freire & Jucá Advogados",
            plan="ENTERPRISE", is_active=True,
        )
        if afj_novo:
            db.add(TenantConfig(
                tenant_id=tenant_afj.id, app_name="AFJ CORE",
                primary_color="#C9A84C", secondary_color="#1A1A1A", accent_color="#F5F0E8",
                modules_enabled={
                    "processos": True, "peticoes": True, "clientes": True,
                    "financeiro": True, "agentes": True, "visual_law": True,
                },
            ))

        admin = await _get_or_create_user(
            db, "admin@afjadvogados.com.br", hashed_password=hash_password("Admin@123"),
            full_name="Administrador AFJ", oab_number="123456CE", role="ADMIN",
            is_active=True, tenant_id=tenant_afj.id,
        )
        socio = await _get_or_create_user(
            db, "socio@afjadvogados.com.br", hashed_password=hash_password("Socio@123"),
            full_name="Dr. Almeida Freire", oab_number="111111CE", role="SOCIO",
            is_active=True, tenant_id=tenant_afj.id,
        )
        advogado = await _get_or_create_user(
            db, "advogado@afjadvogados.com.br", hashed_password=hash_password("Advogado@123"),
            full_name="Dr. João Silva", oab_number="654321CE", role="ADVOGADO",
            is_active=True, tenant_id=tenant_afj.id,
        )
        await _get_or_create_user(
            db, "assistente@afjadvogados.com.br", hashed_password=hash_password("Assistente@123"),
            full_name="Ana Secretária", role="ASSISTENTE",
            is_active=True, tenant_id=tenant_afj.id,
        )

        if afj_novo:
            await gerar_dados_ficticios(db, tenant_afj.id, admin.id, socio.id, advogado.id)

        # ── Tenant demo (público, Fase 199) ────────────────────────────────────
        tenant_demo, demo_novo = await _get_or_create_tenant(
            db, "demo", name="Escritório Demo", plan="STANDARD",
            is_active=True, is_demo=True, max_users=4,
        )
        if demo_novo:
            db.add(TenantConfig(
                tenant_id=tenant_demo.id, app_name="Demo Jurídico",
                primary_color="#1A6EAB", secondary_color="#0D1B2A", accent_color="#EBF4FB",
                modules_enabled={
                    "processos": True, "peticoes": True, "clientes": True,
                    "financeiro": True, "agentes": True, "visual_law": True,
                },
            ))

        if demo_novo:
            admin_demo_id, socio_demo_id, advogado_demo_id, _ = await criar_elenco_demo(db, tenant_demo.id)
            await gerar_dados_ficticios(db, tenant_demo.id, admin_demo_id, socio_demo_id, advogado_demo_id)

        await db.commit()
        print("\n✓ Seed concluído!")
        print("  Tenants:")
        print("    afj     — Almeida, Freire & Jucá (ENTERPRISE)" + ("" if afj_novo else " [já existia]"))
        print("    demo    — Escritório Demo, is_demo=true (STANDARD)" + ("" if demo_novo else " [já existia]"))
        print("\n  Usuários AFJ:")
        print("    admin@afjadvogados.com.br       / Admin@123      (ADMIN)")
        print("    socio@afjadvogados.com.br       / Socio@123      (SOCIO)")
        print("    advogado@afjadvogados.com.br    / Advogado@123   (ADVOGADO)")
        print("    assistente@afjadvogados.com.br  / Assistente@123 (ASSISTENTE)")
        print("\n  Usuário público do tenant demo:")
        print(f"    {DEMO_ADMIN_EMAIL}  / {DEMO_ADMIN_SENHA}  (ADMIN — todas as funcionalidades, sem efeito externo real)")


if __name__ == "__main__":
    asyncio.run(seed())
