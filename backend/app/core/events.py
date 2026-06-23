"""Eventos de startup e shutdown da aplicação FastAPI."""
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
from fastapi import FastAPI
import structlog

log = structlog.get_logger()

APP_START_TIME: Optional[datetime] = None


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
    global APP_START_TIME
    from datetime import timezone
    APP_START_TIME = datetime.now(timezone.utc)
    log.info("afj_core_starting", version="1.0.0")

    # Criar tables + seed apenas quando DATABASE_URL estiver configurado
    from app.db.base import engine, Base, _has_real_db
    from sqlalchemy import text
    if _has_real_db:
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            log.info("database_ready")
        except Exception as exc:
            log.error("database_startup_failed", error=str(exc))

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
    else:
        log.warning("database_skipped", reason="DATABASE_URL not configured — running in degraded mode")

    # Pré-compilar o grafo LangGraph para evitar latência no primeiro request
    try:
        import asyncio as _asyncio
        from app.agents.brain.orchestrator import get_orchestrator_graph
        await _asyncio.wait_for(
            _asyncio.get_event_loop().run_in_executor(None, get_orchestrator_graph),
            timeout=30.0,
        )
        log.info("orchestrator_ready")
    except Exception as exc:
        log.warning("orchestrator_warmup_failed", error=str(exc))

    # Inicializar collections do Qdrant (apenas se URL configurada explicitamente)
    from app.config import settings as _cfg
    _qdrant_configured = bool(
        _cfg.QDRANT_API_KEY or
        (_cfg.QDRANT_URL and _cfg.QDRANT_URL not in {"http://qdrant:6333", "http://localhost:6333"})
    )
    if _qdrant_configured:
        try:
            import asyncio as _asyncio
            from app.db.qdrant import get_qdrant
            from app.rag.collections import ensure_collections
            qdrant = await get_qdrant()
            await _asyncio.wait_for(ensure_collections(qdrant), timeout=15.0)
            log.info("qdrant_collections_ready")
        except Exception as exc:
            log.warning("qdrant_startup_warning", error=str(exc))
    else:
        log.info("qdrant_skipped", reason="QDRANT_URL is default placeholder — skipping init")

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
