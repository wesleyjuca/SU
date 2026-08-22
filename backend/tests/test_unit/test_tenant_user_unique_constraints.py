"""Fase 202 (achado ALTO da Fase 201) — `Tenant.slug`/`User.email` são
declarados `unique=True` no SQLAlchemy, mas o banco nasceu via
`create_all()` sem `alembic_version`, e essa unicidade nunca virou
constraint real no Postgres. Sem ela, a garantia de segurança de
`POST /auth/demo-login`/`resetar_tenant_demo` ("estruturalmente
impossível" cruzar tenant, porque a query assume no máximo 1 linha) não
tinha nenhum lastro no banco. Prova a garantia diretamente contra
Postgres real, com valores só-de-teste (nunca toca em "demo"/"afj")."""
import uuid

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError

from app.db.base import AsyncSessionLocal
from app.models.tenant import Tenant
from app.models.user import User

pytestmark = pytest.mark.asyncio


async def _indice_existe(db, indexname: str) -> bool:
    return (await db.execute(
        text("SELECT 1 FROM pg_indexes WHERE indexname = :nome"),
        {"nome": indexname},
    )).scalar_one_or_none() is not None


async def test_tenants_slug_tem_constraint_unica_real():
    async with AsyncSessionLocal() as db:
        if not await _indice_existe(db, "tenants_slug_unique_idx"):
            pytest.skip("Migração da Fase 202 (tenants_slug_unique_idx) não aplicada neste ambiente")

    slug_teste = f"teste-unico-{uuid.uuid4().hex[:10]}"
    tenant_id_a = uuid.uuid4()
    try:
        async with AsyncSessionLocal() as db:
            db.add(Tenant(id=tenant_id_a, name="Tenant Teste A", slug=slug_teste, plan="STANDARD", is_active=True))
            await db.commit()

        async with AsyncSessionLocal() as db:
            db.add(Tenant(id=uuid.uuid4(), name="Tenant Teste B", slug=slug_teste, plan="STANDARD", is_active=True))
            with pytest.raises(IntegrityError):
                await db.commit()
            await db.rollback()
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(Tenant).where(Tenant.slug == slug_teste))
            await db.commit()


async def test_users_email_tem_constraint_unica_real():
    async with AsyncSessionLocal() as db:
        if not await _indice_existe(db, "users_email_unique_idx"):
            pytest.skip("Migração da Fase 202 (users_email_unique_idx) não aplicada neste ambiente")
        afj_id = (await db.execute(select(Tenant.id).where(Tenant.slug == "afj"))).scalar_one_or_none()
        if afj_id is None:
            pytest.skip("Seed (tenant afj) não disponível neste ambiente")

    email_teste = f"teste-unico-{uuid.uuid4().hex[:10]}@example.com"
    try:
        async with AsyncSessionLocal() as db:
            db.add(User(
                id=uuid.uuid4(), email=email_teste, hashed_password="x",
                full_name="Usuario Teste A", role="ASSISTENTE", is_active=True, tenant_id=afj_id,
            ))
            await db.commit()

        async with AsyncSessionLocal() as db:
            db.add(User(
                id=uuid.uuid4(), email=email_teste, hashed_password="x",
                full_name="Usuario Teste B", role="ASSISTENTE", is_active=True, tenant_id=afj_id,
            ))
            with pytest.raises(IntegrityError):
                await db.commit()
            await db.rollback()
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(User).where(User.email == email_teste))
            await db.commit()
