import time
import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import structlog

log = structlog.get_logger()

AUDIT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
SKIP_AUDIT_PATHS = {"/api/v1/auth/login", "/api/v1/auth/refresh", "/health", "/docs", "/openapi.json"}


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
