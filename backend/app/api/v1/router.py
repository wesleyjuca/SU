import structlog
from fastapi import APIRouter, Depends
from app.api.v1 import (
    users,
    auth, approvals, processes, clients, documents,
    financial, ws, audit, rag, notifications, tenant, system, lgpd, push, portal,
    petition_templates, integrity, google_integration, tenants_admin, billing,
    reports_admin, invoices, crm, publications, integrations_hub, ai_oauth,
)
from app.dependencies import require_active_tenant, get_current_staff

log = structlog.get_logger()

api_router = APIRouter()

# Bloqueio suave por inadimplência: escritório SUSPENSO não escreve nos módulos
# de negócio (leitura liberada, SUPERADMIN isento). Ver require_active_tenant.
_BLOCK = [Depends(require_active_tenant)]

# Fronteira de confiança: o papel CLIENT (portal do cliente) só acessa /portal/*
# e /auth/*. Os módulos internos do escritório exigem colaborador (staff) —
# sem isto um CLIENT autenticado listaria documentos/processos e resolveria
# aprovações HITL do escritório inteiro.
_STAFF = [Depends(get_current_staff)]
_BLOCK_STAFF = [*_BLOCK, *_STAFF]

api_router.include_router(auth.router)
api_router.include_router(approvals.router, dependencies=_BLOCK_STAFF)
api_router.include_router(processes.router, dependencies=_BLOCK_STAFF)
api_router.include_router(clients.router, dependencies=_BLOCK_STAFF)
api_router.include_router(documents.router, dependencies=_BLOCK_STAFF)
api_router.include_router(financial.router, dependencies=_BLOCK_STAFF)
api_router.include_router(invoices.router, dependencies=_BLOCK_STAFF)
api_router.include_router(crm.router, dependencies=_BLOCK_STAFF)
api_router.include_router(publications.router, dependencies=_BLOCK_STAFF)
api_router.include_router(ws.router)
api_router.include_router(audit.router, dependencies=_STAFF)
api_router.include_router(rag.router, dependencies=_BLOCK_STAFF)
api_router.include_router(notifications.router, dependencies=_BLOCK)
api_router.include_router(tenant.router)
api_router.include_router(system.router)
api_router.include_router(lgpd.router, dependencies=_STAFF)
api_router.include_router(push.router, dependencies=_BLOCK)
api_router.include_router(users.router, dependencies=_STAFF)
api_router.include_router(portal.router, dependencies=_BLOCK)
api_router.include_router(petition_templates.router, dependencies=_BLOCK_STAFF)
api_router.include_router(integrity.router, dependencies=_BLOCK_STAFF)
api_router.include_router(google_integration.router, dependencies=_BLOCK_STAFF)
api_router.include_router(integrations_hub.router, dependencies=_BLOCK_STAFF)
# Sem dependencies aqui de propósito: /callback é o navegador do usuário sendo
# redirecionado pelo OpenRouter (sem header Authorization), precisa ficar
# público; /connect exige auth no próprio parâmetro do endpoint (ai_oauth.py).
api_router.include_router(ai_oauth.router)
# Webhooks de provedores: público (provedores não têm JWT); validação por
# assinatura específica do provedor nas fases de cada integração.
api_router.include_router(integrations_hub.webhooks_router)
api_router.include_router(tenants_admin.router)
api_router.include_router(billing.router)
api_router.include_router(reports_admin.router)

# Agents router depends on LangGraph — load with guard so a build failure
# degrades only /agents/* without bringing down the entire app
try:
    from app.api.v1 import agents as _agents_mod
    # _BLOCK: tenant suspenso por inadimplência não gasta tokens de IA.
    api_router.include_router(_agents_mod.router, dependencies=_BLOCK_STAFF)
except Exception as _exc:
    log.error("agents_router_failed", error=str(_exc))
