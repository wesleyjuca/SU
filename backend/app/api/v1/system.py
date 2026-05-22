"""Endpoints de sistema — métricas reais, navegação dinâmica, analytics."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, text
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


@router.get("/analytics/financeiro")
async def analytics_financeiro(
    meses: int = Query(default=6, ge=1, le=24),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dados financeiros para gráficos: receitas/despesas por mês e por categoria."""
    from app.models.financial import FinancialEntry

    tid = current_user.tenant_id
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=meses * 31)

    # Receitas e despesas mensais
    q_mensal = await db.execute(
        select(
            func.date_trunc("month", func.coalesce(FinancialEntry.data_pagamento, FinancialEntry.created_at)).label("mes"),
            FinancialEntry.tipo,
            func.sum(FinancialEntry.valor).label("total"),
        ).where(
            and_(
                FinancialEntry.tenant_id == tid,
                FinancialEntry.status != "CANCELADO",
                FinancialEntry.created_at >= cutoff,
            )
        ).group_by("mes", FinancialEntry.tipo).order_by("mes")
    )
    rows_mensal = q_mensal.all()

    receitas_por_mes: dict = {}
    despesas_por_mes: dict = {}
    for row in rows_mensal:
        mes_str = row.mes.strftime("%Y-%m") if row.mes else "?"
        val = float(row.total or 0)
        if row.tipo == "RECEITA":
            receitas_por_mes[mes_str] = receitas_por_mes.get(mes_str, 0) + val
        else:
            despesas_por_mes[mes_str] = despesas_por_mes.get(mes_str, 0) + val

    # Unir meses em lista ordenada
    all_months = sorted(set(list(receitas_por_mes) + list(despesas_por_mes)))
    mensal = [
        {
            "mes": m,
            "receitas": round(receitas_por_mes.get(m, 0), 2),
            "despesas": round(despesas_por_mes.get(m, 0), 2),
        }
        for m in all_months
    ]

    # Saldo acumulado
    saldo = 0.0
    for item in mensal:
        saldo += item["receitas"] - item["despesas"]
        item["saldo"] = round(saldo, 2)

    # Por categoria (pagos)
    q_cat = await db.execute(
        select(
            func.coalesce(FinancialEntry.categoria, "Outros").label("categoria"),
            FinancialEntry.tipo,
            func.sum(FinancialEntry.valor).label("total"),
        ).where(
            and_(FinancialEntry.tenant_id == tid, FinancialEntry.status == "PAGO")
        ).group_by("categoria", FinancialEntry.tipo).order_by(func.sum(FinancialEntry.valor).desc()).limit(10)
    )
    por_categoria = [
        {"categoria": r.categoria, "tipo": r.tipo, "total": float(r.total or 0)}
        for r in q_cat.all()
    ]

    # Totais gerais
    q_tot = await db.execute(
        select(FinancialEntry.tipo, FinancialEntry.status, func.sum(FinancialEntry.valor).label("t"))
        .where(FinancialEntry.tenant_id == tid)
        .group_by(FinancialEntry.tipo, FinancialEntry.status)
    )
    totais: dict = {}
    for r in q_tot.all():
        totais[f"{r.tipo}_{r.status}"] = float(r.t or 0)

    return {
        "mensal": mensal,
        "por_categoria": por_categoria,
        "summary": {
            "receitas_pagas": round(totais.get("RECEITA_PAGO", 0), 2),
            "receitas_pendentes": round(totais.get("RECEITA_PENDENTE", 0), 2),
            "despesas_pagas": round(totais.get("DESPESA_PAGO", 0), 2),
            "despesas_pendentes": round(totais.get("DESPESA_PENDENTE", 0), 2),
        },
    }


@router.get("/analytics/processos")
async def analytics_processos(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Estatísticas de processos para gráficos."""
    from app.models.process import LegalProcess

    tid = current_user.tenant_id
    now = datetime.now(timezone.utc)
    cutoff_6m = now - timedelta(days=183)

    # Por situação
    q_sit = await db.execute(
        select(LegalProcess.situacao, func.count(LegalProcess.id).label("count"))
        .where(LegalProcess.tenant_id == tid)
        .group_by(LegalProcess.situacao)
    )
    por_situacao = [{"situacao": r.situacao or "Indefinido", "count": r.count} for r in q_sit.all()]

    # Por área do direito
    q_area = await db.execute(
        select(
            func.coalesce(LegalProcess.area_direito, "Não definido").label("area"),
            func.count(LegalProcess.id).label("count"),
        )
        .where(LegalProcess.tenant_id == tid)
        .group_by("area")
        .order_by(func.count(LegalProcess.id).desc())
        .limit(8)
    )
    por_area = [{"area": r.area, "count": r.count} for r in q_area.all()]

    # Criados por mês (últimos 6 meses)
    q_mes = await db.execute(
        select(
            func.date_trunc("month", LegalProcess.created_at).label("mes"),
            func.count(LegalProcess.id).label("count"),
        )
        .where(and_(LegalProcess.tenant_id == tid, LegalProcess.created_at >= cutoff_6m))
        .group_by("mes")
        .order_by("mes")
    )
    criados_por_mes = [
        {"mes": r.mes.strftime("%Y-%m") if r.mes else "?", "count": r.count}
        for r in q_mes.all()
    ]

    return {
        "por_situacao": por_situacao,
        "por_area": por_area,
        "criados_por_mes": criados_por_mes,
        "total": sum(r["count"] for r in por_situacao),
    }


@router.get("/analytics/agentes")
async def analytics_agentes(
    dias: int = Query(default=30, ge=1, le=90),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Métricas de performance e custo dos agentes IA."""
    from app.models.agent_run import AgentRun

    tid = current_user.tenant_id
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=dias)

    # Por agente (custo, execuções, taxa sucesso)
    q_ag = await db.execute(
        select(
            AgentRun.agent_name,
            func.sum(AgentRun.cost_usd).label("custo"),
            func.sum(AgentRun.tokens_used).label("tokens"),
            func.count(AgentRun.id).label("execucoes"),
            func.avg(AgentRun.duration_ms).label("avg_ms"),
            func.sum(
                func.cast(AgentRun.status == "SUCCESS", func.Integer if False else text("INTEGER"))
            ).label("sucessos"),
        )
        .where(and_(AgentRun.tenant_id == tid, AgentRun.started_at >= cutoff))
        .group_by(AgentRun.agent_name)
        .order_by(func.sum(AgentRun.cost_usd).desc())
        .limit(12)
    )
    por_agente = [
        {
            "agent": r.agent_name,
            "custo": round(float(r.custo or 0), 4),
            "tokens": int(r.tokens or 0),
            "execucoes": r.execucoes,
            "avg_ms": int(r.avg_ms or 0),
        }
        for r in q_ag.all()
    ]

    # Por dia (execuções + custo)
    q_dia = await db.execute(
        select(
            func.date_trunc("day", AgentRun.started_at).label("dia"),
            func.count(AgentRun.id).label("total"),
            func.sum(AgentRun.cost_usd).label("custo"),
        )
        .where(and_(AgentRun.tenant_id == tid, AgentRun.started_at >= cutoff))
        .group_by("dia")
        .order_by("dia")
    )
    por_dia = [
        {
            "dia": r.dia.strftime("%Y-%m-%d") if r.dia else "?",
            "total": r.total,
            "custo": round(float(r.custo or 0), 4),
        }
        for r in q_dia.all()
    ]

    # Totais
    q_tot = await db.execute(
        select(
            func.count(AgentRun.id).label("total"),
            func.sum(AgentRun.cost_usd).label("custo"),
            func.sum(AgentRun.tokens_used).label("tokens"),
        ).where(and_(AgentRun.tenant_id == tid, AgentRun.started_at >= cutoff))
    )
    tot = q_tot.one()

    return {
        "por_agente": por_agente,
        "por_dia": por_dia,
        "total_execucoes": int(tot.total or 0),
        "total_custo": round(float(tot.custo or 0), 4),
        "total_tokens": int(tot.tokens or 0),
    }
