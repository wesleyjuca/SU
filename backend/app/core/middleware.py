import time
import uuid
from typing import Callable
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import structlog

log = structlog.get_logger()

AUDIT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
SKIP_AUDIT_PATHS = {"/api/v1/auth/login", "/api/v1/auth/refresh", "/health", "/docs", "/openapi.json"}

# Rate limit config: (limit, window_seconds)
RATE_LIMIT_RULES: dict[str, tuple[int, int]] = {
    "auth": (10, 60),          # 10 req/min por IP (brute-force protection)
    "agents_trigger": (20, 60), # 20 req/min por user
    "default": (200, 60),       # 200 req/min por IP
}

AUTH_PATHS = {"/api/v1/auth/login", "/api/v1/auth/refresh"}
AGENT_TRIGGER_PATH = "/api/v1/agents/trigger"


class AuditMiddleware(BaseHTTPMiddleware):
    """
    Intercepta todas as requisições que modificam estado e registra no audit_log.
    Usa sessão DB separada que comita independentemente — mesmo se a requisição
    principal falhar, o log de tentativa é preservado (conformidade LGPD).
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        request.state.start_time = time.time()

        response = await call_next(request)

        duration_ms = int((time.time() - request.state.start_time) * 1000)

        if request.method in AUDIT_METHODS and request.url.path not in SKIP_AUDIT_PATHS:
            await self._write_audit(request, response, duration_ms)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Duration-Ms"] = str(duration_ms)
        return response

    async def _write_audit(self, request: Request, response: Response, duration_ms: int):
        try:
            from app.db.base import AsyncSessionLocal
            from app.models.audit_log import AuditLog

            user_id = getattr(request.state, "user_id", None)
            action = f"{request.method}:{request.url.path}"

            async with AsyncSessionLocal() as audit_session:
                entry = AuditLog(
                    user_id=user_id,
                    action=action,
                    ip_address=request.client.host if request.client else None,
                    user_agent=request.headers.get("user-agent"),
                    session_id=getattr(request.state, "session_id", None),
                    success=response.status_code < 400,
                    error_detail=None if response.status_code < 400 else f"HTTP {response.status_code}",
                )
                audit_session.add(entry)
                await audit_session.commit()
        except Exception as exc:
            log.error("audit_write_failed", error=str(exc))


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting via Redis sliding window (fixed window por simplicidade).
    Protege endpoints sensíveis de abuso e brute-force.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"

        if path in AUTH_PATHS:
            rule_key = "auth"
            identifier = client_ip
        elif path == AGENT_TRIGGER_PATH:
            rule_key = "agents_trigger"
            auth_header = request.headers.get("authorization", "")
            identifier = auth_header[-16:] if auth_header else client_ip
        else:
            rule_key = "default"
            identifier = client_ip

        limit, window = RATE_LIMIT_RULES[rule_key]
        redis_key = f"ratelimit:{rule_key}:{identifier}"

        try:
            redis = await self._get_redis()
            if redis:
                count = await redis.incr(redis_key)
                if count == 1:
                    await redis.expire(redis_key, window)
                remaining = max(0, limit - count)

                if count > limit:
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Muitas requisições. Aguarde e tente novamente."},
                        headers={
                            "Retry-After": str(window),
                            "X-RateLimit-Limit": str(limit),
                            "X-RateLimit-Remaining": "0",
                        },
                    )
        except Exception:
            pass

        response = await call_next(request)

        try:
            response.headers["X-RateLimit-Limit"] = str(limit)
        except Exception:
            pass

        return response

    async def _get_redis(self):
        try:
            from app.db.redis import get_redis
            return await get_redis()
        except Exception:
            return None


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        log.info(
            "request_start",
            method=request.method,
            path=request.url.path,
            request_id=getattr(request.state, "request_id", None),
        )
        response = await call_next(request)
        log.info(
            "request_end",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
        )
        return response

