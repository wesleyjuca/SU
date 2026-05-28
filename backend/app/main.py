"""
AFJ CORE SYSTEM — Backend Principal
Almeida, Freire & Jucá Advogados
"""
import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.core.events import lifespan
from app.core.middleware import AuditMiddleware, RequestLoggingMiddleware, RateLimitMiddleware, SecurityHeadersMiddleware
from app.api.v1.router import api_router

log = structlog.get_logger()

# ─── Sentry (opcional — só inicializa se SENTRY_DSN estiver configurado) ─────
if settings.SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.ENVIRONMENT,
            release=f"afj-core@{settings.VERSION}",
            traces_sample_rate=0.1,
            integrations=[FastApiIntegration(), SqlalchemyIntegration()],
            send_default_pii=False,
        )
        log.info("sentry_initialized", environment=settings.ENVIRONMENT)
    except ImportError:
        log.warning("sentry_sdk_not_installed", hint="pip install sentry-sdk[fastapi]")

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer() if settings.DEBUG else structlog.processors.JSONRenderer(),
    ]
)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Sistema Jurídico Inteligente — Almeida, Freire & Jucá Advogados",
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json" if settings.DEBUG else None,
    docs_url=f"{settings.API_V1_STR}/docs" if settings.DEBUG else None,
    lifespan=lifespan,
)

# ─── Middlewares (ordem importa) ─────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=r"https://.*\.(vercel\.app|railway\.app)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(AuditMiddleware)

# ─── Rotas ───────────────────────────────────────────────────────────────────
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error("unhandled_exception", path=request.url.path, error=str(exc), exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
async def health_check():
    from sqlalchemy import text
    from app.db.base import AsyncSessionLocal

    checks: dict[str, bool] = {"postgresql": False, "redis": False, "qdrant": False}

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["postgresql"] = True
    except Exception:
        pass

    try:
        from app.db.redis import get_redis
        redis = await get_redis()
        if redis:
            await redis.ping()
            checks["redis"] = True
    except Exception:
        pass

    try:
        from app.db.qdrant import get_qdrant
        qdrant = await get_qdrant()
        if qdrant:
            checks["qdrant"] = True
    except Exception:
        pass

    all_ok = all(checks.values())
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={
            "status": "operational" if all_ok else "degraded",
            "system": "AFJ CORE SYSTEM",
            "version": settings.VERSION,
            "environment": settings.ENVIRONMENT,
            "checks": checks,
        },
    )
