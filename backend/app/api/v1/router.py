from fastapi import APIRouter
from app.api.v1 import auth, agents, approvals, processes, clients, documents, financial, ws

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(agents.router)
api_router.include_router(approvals.router)
api_router.include_router(processes.router)
api_router.include_router(clients.router)
api_router.include_router(documents.router)
api_router.include_router(financial.router)
api_router.include_router(ws.router)
