"""
AFJ CORE SYSTEM — Backend Principal
Almeida, Freire & Jucá Advogados
"""
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.events import lifespan
from app.core.middleware import AuditMiddleware, RequestLoggingMiddleware, RateLimitMiddleware
from app.api.v1.router import api_router

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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(AuditMiddleware)

# ─── Rotas ───────────────────────────────────────────────────────────────────
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/health")
async def health_check():
    return {
        "status": "operational",
        "system": "AFJ CORE SYSTEM",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
    }
