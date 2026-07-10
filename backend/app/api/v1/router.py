import structlog
from fastapi import APIRouter
from app.api.v1 import (
    users,
    auth, approvals, processes, clients, documents,
    financial, ws, audit, rag, notifications, tenant, system, lgpd, push, portal,
    petition_templates, integrity, google_integration,
)

log = structlog.get_logger()

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(approvals.router)
api_router.include_router(processes.router)
api_router.include_router(clients.router)
api_router.include_router(documents.router)
api_router.include_router(financial.router)
api_router.include_router(ws.router)
api_router.include_router(audit.router)
api_router.include_router(rag.router)
api_router.include_router(notifications.router)
api_router.include_router(tenant.router)
api_router.include_router(system.router)
api_router.include_router(lgpd.router)
api_router.include_router(push.router)
api_router.include_router(users.router)
api_router.include_router(portal.router)
api_router.include_router(petition_templates.router)
api_router.include_router(integrity.router)
api_router.include_router(google_integration.router)

# Agents router depends on LangGraph — load with guard so a build failure
# degrades only /agents/* without bringing down the entire app
try:
    from app.api.v1 import agents as _agents_mod
    api_router.include_router(_agents_mod.router)
except Exception as _exc:
    log.error("agents_router_failed", error=str(_exc))
