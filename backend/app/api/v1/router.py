from fastapi import APIRouter
from app.api.v1 import (
    auth, agents, approvals, processes, clients, documents,
    financial, ws, audit, rag, notifications, tenant, system, lgpd, push,
)

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(agents.router)
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
