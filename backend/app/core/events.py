"""Eventos de startup e shutdown da aplicação FastAPI."""
import asyncio
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

        # Inclui os e-mails DOCUMENTADOS (CLAUDE.md e /ajuda usam @afj.com.br) —
        # a divergência @afjadvogados.com vs @afj.com.br causava
        # "E-mail ou senha incorretos" no login do admin.
        SEED = [
            ("admin@afj.com.br",          "Admin@123",    "Administrador", "ADMIN"),
            ("advogado@afj.com.br",       "Adv@123",      "Advogado",      "ADVOGADO"),
            ("admin@afjadvogados.com",    "Admin@123",    "Administrador", "ADMIN"),
            ("socio@afjadvogados.com",    "Socio@123",    "Sócio",         "SOCIO"),
            ("advogado@afjadvogados.com", "Advogado@123", "Advogado",      "ADVOGADO"),
            # SUPERADMIN — dono da plataforma SaaS (gerencia todos os escritórios).
            ("super@afj.com.br",          "Super@123",    "Super Admin",   "SUPERADMIN"),
        ]
        import os
        # Resetar senha/reativar conta a cada boot é destrutivo (desfaz trocas
        # de senha e reativa contas desativadas). Só com opt-in explícito.
        reset_passwords = os.environ.get("SEED_RESET_PASSWORDS", "").lower() == "true"
        for email, password, full_name, role in SEED:
            exists = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if not exists:
                session.add(User(
                    id=uuid.uuid4(), email=email,
                    hashed_password=hash_password(password),
                    full_name=full_name, role=role,
                    is_active=True, tenant_id=tenant.id,
                ))
            elif reset_passwords:
                exists.hashed_password = hash_password(password)
                exists.is_active = True
        await session.commit()
    log.info("seed_complete", reset_passwords=reset_passwords)


async def _background_warmup() -> None:
    """Optional warmup that runs after the app is already serving requests."""
    await asyncio.sleep(2)

    try:
        from app.agents.brain.orchestrator import get_orchestrator_graph
        get_orchestrator_graph()
        log.info("orchestrator_ready")
    except Exception as exc:
        log.warning("orchestrator_warmup_failed", error=str(exc))

    from app.config import settings as _cfg
    _qdrant_configured = bool(
        _cfg.QDRANT_API_KEY or
        (_cfg.QDRANT_URL and _cfg.QDRANT_URL not in {"http://qdrant:6333", "http://localhost:6333"})
    )
    if _qdrant_configured:
        try:
            from app.db.qdrant import get_qdrant
            from app.rag.collections import ensure_collections
            qdrant = await get_qdrant()
            await asyncio.wait_for(ensure_collections(qdrant), timeout=15.0)
            log.info("qdrant_collections_ready")
        except Exception as exc:
            log.warning("qdrant_startup_warning", error=str(exc))
    else:
        log.info("qdrant_skipped", reason="QDRANT_URL is default placeholder — skipping init")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ─── STARTUP (fast — must complete before Railway health check) ───────────
    global APP_START_TIME
    from datetime import timezone
    APP_START_TIME = datetime.now(timezone.utc)
    log.info("afj_core_starting", version="1.0.0")

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
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_provider VARCHAR(20)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_api_key_enc TEXT",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_model VARCHAR(80)",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS ai_enabled BOOLEAN DEFAULT FALSE",
            # Fase 27 — unidades da mesma banca (create_all não adiciona colunas novas)
            "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS parent_tenant_id UUID REFERENCES tenants(id) ON DELETE SET NULL",
            "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS unit_label VARCHAR(120)",
            # Fase 34 — desfecho do processo (taxa de êxito nos relatórios de gestão)
            "ALTER TABLE legal_processes ADD COLUMN IF NOT EXISTS desfecho VARCHAR(20)",
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

    log.info("afj_core_ready", message="AFJ CORE SYSTEM iniciado com sucesso")
    asyncio.create_task(_background_warmup())

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
