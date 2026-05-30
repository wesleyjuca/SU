"""Eventos de startup e shutdown da aplicação FastAPI."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
import structlog

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ─── STARTUP ─────────────────────────────────────────────────────────────
    from datetime import datetime, timezone
    from app.config import settings as _cfg
    _cfg.APP_START_TIME = datetime.now(timezone.utc)
    log.info("afj_core_starting", version="1.0.0")

    # Criar tables (apenas em desenvolvimento — produção usa Alembic)
    try:
        from app.db.base import engine, Base
        import app.models  # noqa: garante que todos os models são importados
        # Em produção, remover este bloco e usar apenas Alembic
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        log.info("database_ready")
    except Exception as exc:
        log.error("database_startup_failed", error=str(exc))

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
