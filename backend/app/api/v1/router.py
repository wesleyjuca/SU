import structlog
from fastapi import APIRouter, Depends
from app.api.v1 import (
    users,
    auth, approvals, processes, clients, documents,
    financial, ws, audit, rag, notifications, tenant, system, lgpd, push, portal,
    petition_templates, integrity, google_integration, tenants_admin, billing,
    reports_admin, invoices,
)
from app.dependencies import require_active_tenant

log = structlog.get_logger()

api_router = APIRouter()

# Bloqueio suave por inadimplência: escritório SUSPENSO não escreve nos módulos
# de negócio (leitura liberada, SUPERADMIN isento). Ver require_active_tenant.
_BLOCK = [Depends(require_active_tenant)]

api_router.include_router(auth.router)
api_router.include_router(approvals.router, dependencies=_BLOCK)
api_router.include_router(processes.router, dependencies=_BLOCK)
api_router.include_router(clients.router, dependencies=_BLOCK)
api_router.include_router(documents.router, dependencies=_BLOCK)
api_router.include_router(financial.router, dependencies=_BLOCK)
api_router.include_router(invoices.router, dependencies=_BLOCK)
api_router.include_router(ws.router)
api_router.include_router(audit.router)
api_router.include_router(rag.router, dependencies=_BLOCK)
api_router.include_router(notifications.router, dependencies=_BLOCK)
api_router.include_router(tenant.router)
api_router.include_router(system.router)
api_router.include_router(lgpd.router)
api_router.include_router(push.router, dependencies=_BLOCK)
api_router.include_router(users.router)
api_router.include_router(portal.router, dependencies=_BLOCK)
api_router.include_router(petition_templates.router, dependencies=_BLOCK)
api_router.include_router(integrity.router, dependencies=_BLOCK)
api_router.include_router(google_integration.router, dependencies=_BLOCK)
api_router.include_router(tenants_admin.router)
api_router.include_router(billing.router)
api_router.include_router(reports_admin.router)

# Agents router depends on LangGraph — load with guard so a build failure
# degrades only /agents/* without bringing down the entire app
try:
    from app.api.v1 import agents as _agents_mod
    api_router.include_router(_agents_mod.router)
except Exception as _exc:
    log.error("agents_router_failed", error=str(_exc))
