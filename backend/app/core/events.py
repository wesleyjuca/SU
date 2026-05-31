"""Eventos de startup e shutdown da aplicação FastAPI."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
import structlog

log = structlog.get_logger()


async def _seed_default_data(engine) -> None:
    """Cria tenant padrão e usuários iniciais se o banco estiver vazio."""
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import select
    from app.models.tenant import Tenant, TenantConfig
    from app.models.user import User
    from app.core.security import hash_password
    import uuid

    async with AsyncSession(engine) as session:
        result = await session.execute(select(Tenant).limit(1))
        tenant = result.scalar_one_or_none()
        if not tenant:
            tenant = Tenant(
                id=uuid.uuid4(), name="AFJ Advogados",
                slug="afj", plan="STANDARD", is_active=True,
            )
            session.add(tenant)
            session.add(TenantConfig(id=uuid.uuid4(), tenant_id=tenant.id))
            await session.flush()

        SEED = [
            ("admin@afjadvogados.com",    "Admin@123",    "Administrador", "ADMIN"),
            ("socio@afjadvogados.com",    "Socio@123",    "Sócio",         "SOCIO"),
            ("advogado@afjadvogados.com", "Advogado@123", "Advogado",      "ADVOGADO"),
        ]
        for email, password, full_name, role in SEED:
            exists = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if not exists:
                session.add(User(
                    id=uuid.uuid4(), email=email,
                    hashed_password=hash_password(password),
                    full_name=full_name, role=role,
                    is_active=True, tenant_id=tenant.id,
                ))
            else:
                exists.hashed_password = hash_password(password)
                exists.is_active = True
        await session.commit()
    log.info("seed_complete")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ─── STARTUP ─────────────────────────────────────────────────────────────
    from datetime import datetime, timezone
    from app.config import settings as _cfg
    _cfg.APP_START_TIME = datetime.now(timezone.utc)
    log.info("afj_core_starting", version="1.0.0")

    # Criar tables + garantir colunas adicionadas em migrações posteriores
    from app.db.base import engine, Base
    from sqlalchemy import text
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        log.info("database_ready")
    except Exception as exc:
        log.error("database_startup_failed", error=str(exc))

    # Colunas adicionadas após o deploy inicial — cada statement independente
    for _sql in [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS linked_client_id UUID REFERENCES clients(id)",
    ]:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(_sql))
        except Exception as exc:
            log.warning("migration_warning", sql=_sql[:60], error=str(exc))

    try:
        await _seed_default_data(engine)
    except Exception as exc:
        log.warning("seed_warning", error=str(exc))

    # Inicializar collections do Qdrant
    try:
        from app.db.qdrant import get_qdrant
        from app.rag.collections import ensure_collections
        qdrant = await get_qdrant()
        await ensure_collections(qdrant)
        log.info("qdrant_collections_ready")
    except Exception as exc:
        log.warning("qdrant_startup_warning", error=str(exc))

    log.info("afj_core_ready", message="AFJ CORE SYSTEM iniciado com sucesso")

    yield

    # ─── SHUTDOWN ─────────────────────────────────────────────────────────────
    log.info("afj_core_shutting_down")

    try:
        from app.db.redis import close_redis
        await close_redis()
    except Exception:
        pass

    try:
        from app.db.qdrant import close_qdrant
        await close_qdrant()
    except Exception:
        pass

    log.info("afj_core_stopped")
