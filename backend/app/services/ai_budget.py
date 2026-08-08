"""Limites de orçamento de IA por usuário — checagem, bloqueio suave e alerta.

Regras:
- Sem limite cadastrado → nada acontece (uso livre).
- Gasto do mês >= limite → novas execuções de agentes são BLOQUEADAS (429)
  com mensagem acionável. Bloqueio suave: o admin pode elevar/remover o teto.
- Gasto >= alert_pct% do limite → cria UMA notificação de alerta por mês.
"""
from datetime import datetime, timezone
import uuid

import structlog
from fastapi import HTTPException
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()

# Fase 145 — corrida de TOCTOU: AgentRun nasce com status=RUNNING e
# cost_usd=NULL no momento do disparo (agents.py, documents.py etc.) e só
# ganha o custo real depois que o agente termina (podendo levar segundos) —
# a soma de cost_usd sozinha conta ZERO pras chamadas em andamento, então 2
# requisições concorrentes do mesmo usuário podem ambas ler "dentro do
# orçamento" e ambas prosseguir. Reserva-se conservadoramente este valor por
# execução em andamento (mesma ordem de grandeza do teto padrão por run de
# BaseAgent.max_cost_usd_per_run) só pra decidir over_limit/over_threshold —
# o spent_usd exibido na UI continua refletindo só o gasto confirmado.
RESERVA_ESTIMADA_USD_POR_RUN = 1.0


async def get_budget_status(db: AsyncSession, user_id, tenant_id) -> dict | None:
    """Retorna {limit_usd, spent_usd, pct, over_limit, over_threshold} ou None sem limite."""
    from app.models.user import AIBudgetLimit
    from app.models.agent_run import AgentRun

    limit_row = (await db.execute(
        select(AIBudgetLimit).where(AIBudgetLimit.user_id == user_id)
    )).scalar_one_or_none()
    if not limit_row or not limit_row.monthly_limit_usd:
        return None

    # Lock advisory leve — não fecha a corrida sozinho (a reserva abaixo que
    # fecha), mas reduz o resíduo: sem ele, o intervalo de risco é "duração
    # da chamada de IA" (segundos); com ele, cai pra "duração destas 2
    # queries" (milissegundos), já que checagens concorrentes do MESMO
    # usuário serializam aqui.
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:chave))"), {"chave": f"ai_budget:{user_id}"})

    inicio_mes = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    spent = (await db.execute(
        select(func.coalesce(func.sum(AgentRun.cost_usd), 0)).where(
            AgentRun.triggered_by == user_id,
            AgentRun.tenant_id == tenant_id,  # isolamento multi-tenant
            AgentRun.started_at >= inicio_mes,
        )
    )).scalar_one() or 0

    em_andamento = (await db.execute(
        select(func.count(AgentRun.id)).where(
            AgentRun.triggered_by == user_id,
            AgentRun.tenant_id == tenant_id,
            AgentRun.started_at >= inicio_mes,
            AgentRun.status == "RUNNING",
            AgentRun.cost_usd.is_(None),
        )
    )).scalar_one() or 0

    limit_usd = float(limit_row.monthly_limit_usd)
    spent_usd = float(spent)
    spent_com_reserva = spent_usd + (em_andamento * RESERVA_ESTIMADA_USD_POR_RUN)
    pct = (spent_usd / limit_usd * 100) if limit_usd > 0 else 0.0
    return {
        "limit_usd": limit_usd,
        "spent_usd": round(spent_usd, 4),
        "pct": round(pct, 1),
        "alert_pct": limit_row.alert_pct or 80,
        "over_limit": spent_com_reserva >= limit_usd,
        "over_threshold": pct >= (limit_row.alert_pct or 80),
    }


async def enforce_budget(db: AsyncSession, user_id, tenant_id) -> None:
    """Bloqueia (429) execuções quando o teto mensal foi atingido; alerta ao
    cruzar o threshold. Chamar ANTES de disparar um agente. Falhas internas da
    checagem nunca derrubam a requisição (fail-open, com log)."""
    try:
        status = await get_budget_status(db, user_id, tenant_id)
    except Exception as exc:
        log.warning("ai_budget_check_failed", error=str(exc))
        return
    if not status:
        return

    if status["over_limit"]:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Limite mensal de IA atingido (US$ {status['spent_usd']:.2f} de "
                f"US$ {status['limit_usd']:.2f}). Solicite ao administrador um ajuste "
                "do teto em Custos de IA, ou aguarde o próximo mês."
            ),
        )

    if status["over_threshold"]:
        await _alert_once_per_month(db, user_id, status)


async def _alert_once_per_month(db: AsyncSession, user_id, status: dict) -> None:
    """Cria a notificação de alerta no máximo uma vez por mês por usuário."""
    try:
        from app.models.notification import Notification
        month_key = datetime.now(timezone.utc).strftime("%Y-%m")
        existing = (await db.execute(
            select(Notification.id).where(
                Notification.user_id == user_id,
                Notification.tipo == "SISTEMA",
                Notification.extra_data["budget_month"].astext == month_key,
            ).limit(1)
        )).scalar_one_or_none()
        if existing:
            return
        from app.services.notification import create_notification
        await create_notification(
            db,
            user_id=user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id)),
            titulo=f"Orçamento de IA em {status['pct']:.0f}% do limite mensal",
            tipo="SISTEMA",
            corpo=(
                f"Você já usou US$ {status['spent_usd']:.2f} de US$ {status['limit_usd']:.2f} "
                "neste mês. Ao atingir 100%, novas execuções de agentes serão bloqueadas."
            ),
            priority="HIGH",
            link="/custos-ia",
            metadata={"budget_month": month_key},
        )
    except Exception as exc:
        log.warning("ai_budget_alert_failed", error=str(exc))
