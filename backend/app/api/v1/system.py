"""Endpoints de sistema — métricas reais, navegação dinâmica."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import datetime, timezone, timedelta

from app.db.base import get_db
from app.dependencies import get_current_user
from app.models.user import User

router = APIRouter(prefix="/system", tags=["system"])

# Mapa de itens de nav por role
NAV_ALL = [
    {"href": "/dashboard", "label": "Dashboard", "icon": "LayoutDashboard"},
    {"href": "/processos", "label": "Processos", "icon": "Scale"},
    {"href": "/peticoes", "label": "Petições", "icon": "FileEdit"},
    {"href": "/clientes", "label": "Clientes", "icon": "Users"},
    {"href": "/documentos", "label": "Documentos", "icon": "FolderOpen"},
    {"href": "/contratos", "label": "Contratos", "icon": "FileText"},
    {"href": "/agentes", "label": "Agentes IA", "icon": "Bot"},
    {"href": "/aprovacoes", "label": "Aprovações", "icon": "CheckSquare"},
    {"href": "/financeiro", "label": "Financeiro", "icon": "DollarSign"},
    {"href": "/visual-law", "label": "Visual Law", "icon": "Shapes"},
    {"href": "/auditoria", "label": "Auditoria", "icon": "Shield"},
    {"href": "/configuracoes", "label": "Configurações", "icon": "Settings"},
]

NAV_BY_ROLE: dict[str, list[str]] = {
    "ADMIN": [item["href"] for item in NAV_ALL],
    "SOCIO": ["/dashboard", "/processos", "/peticoes", "/clientes", "/documentos", "/contratos", "/agentes", "/aprovacoes", "/financeiro", "/visual-law"],
    "ADVOGADO": ["/dashboard", "/processos", "/peticoes", "/clientes", "/documentos", "/agentes", "/aprovacoes", "/visual-law"],
    "PARALEGAL": ["/dashboard", "/processos", "/clientes", "/documentos"],
    "ASSISTENTE": ["/dashboard", "/processos", "/clientes"],
}


@router.get("/nav")
async def get_nav(current_user: User = Depends(get_current_user)):
    """Retorna itens de navegação filtrados pelo role do usuário."""
    allowed_hrefs = set(NAV_BY_ROLE.get(current_user.role, NAV_BY_ROLE["ASSISTENTE"]))
    filtered = [item for item in NAV_ALL if item["href"] in allowed_hrefs]
    return {"nav": filtered, "role": current_user.role}


@router.get("/metrics")
async def get_metrics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """KPIs reais para o dashboard."""
    from app.models.process import LegalProcess, ProcessDeadline
    from app.models.approval import Approval
    from app.models.agent_run import AgentRun

    now = datetime.now(timezone.utc)
    next_7d = now + timedelta(days=7)

    # Processos ativos
    r1 = await db.execute(
        select(func.count(LegalProcess.id)).where(LegalProcess.situacao == "ATIVO")
    )
    processos_ativos = r1.scalar_one() or 0

    # Prazos nos próximos 7 dias
    r2 = await db.execute(
        select(func.count(ProcessDeadline.id)).where(
            and_(
                ProcessDeadline.status == "PENDENTE",
                ProcessDeadline.data_prazo <= next_7d.date(),
                ProcessDeadline.data_prazo >= now.date(),
            )
        )
    )
    prazos_proximos = r2.scalar_one() or 0

    # Aprovações pendentes
    r3 = await db.execute(
        select(func.count(Approval.id)).where(Approval.status == "PENDENTE")
    )
    aprovacoes_pendentes = r3.scalar_one() or 0

    # Custo IA do mês (soma de tokens usados * custo estimado)
    inicio_mes = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    r4 = await db.execute(
        select(func.coalesce(func.sum(AgentRun.tokens_used), 0)).where(
            AgentRun.started_at >= inicio_mes
        )
    )
    tokens_mes = r4.scalar_one() or 0
    custo_ia_mes = round(float(tokens_mes) * 0.000015, 2)  # ~$15/1M tokens

    # Agentes ativos (runs nas últimas 24h)
    r5 = await db.execute(
        select(func.count(AgentRun.id)).where(
            AgentRun.started_at >= now - timedelta(hours=24),
            AgentRun.status.in_(["RUNNING", "AWAITING_APPROVAL"]),
        )
    )
    agentes_ativos = r5.scalar_one() or 0

    return {
        "processos_ativos": processos_ativos,
        "prazos_proximos_7d": prazos_proximos,
        "aprovacoes_pendentes": aprovacoes_pendentes,
        "custo_ia_mes": custo_ia_mes,
        "tokens_ia_mes": int(tokens_mes),
        "agentes_ativos_24h": agentes_ativos,
        "updated_at": now.isoformat(),
    }
