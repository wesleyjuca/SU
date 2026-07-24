"""Métricas por tenant — visão de PLATAFORMA (Bloco F / Fase 82).

Agregador reutilizável: consumido pelo endpoint `GET /system/brain/metrics`
(painel Plataforma do Cérebro) e pelos Insights proativos (Fase 85), que
precisam do mesmo retrato para diagnosticar o sistema. Best-effort: cada
agregado é isolado — falha em um não derruba os demais nem o chamador.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import structlog

log = structlog.get_logger()


async def coletar_metricas() -> dict:
    """`{"ok": bool, "tenants": [...], "totais": {...}}`. Nunca levanta."""
    try:
        from sqlalchemy import select, func
        from app.db.base import AsyncSessionLocal
        from app.models.tenant import Tenant
        from app.models.user import User as UserModel
        from app.models.process import LegalProcess
        from app.models.agent_run import AgentRun
        from app.models.sync_run import SyncRun

        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

        async def _dict(db, coluna_tenant, coluna_id, filtro=None):
            try:
                q = select(coluna_tenant, func.count(coluna_id)).group_by(coluna_tenant)
                if filtro is not None:
                    q = q.where(filtro)
                return {t: n for t, n in (await db.execute(q)).all() if t is not None}
            except Exception:
                return {}

        async with AsyncSessionLocal() as db:
            tenants = (await db.execute(select(Tenant.id, Tenant.name, Tenant.plan, Tenant.is_active))).all()
            usuarios = await _dict(db, UserModel.tenant_id, UserModel.id, UserModel.is_active == True)  # noqa: E712
            processos = await _dict(db, LegalProcess.tenant_id, LegalProcess.id)
            agent_runs = await _dict(db, AgentRun.tenant_id, AgentRun.id, AgentRun.started_at >= cutoff)
            syncs = await _dict(db, SyncRun.tenant_id, SyncRun.id)
            try:
                ult = {t: (d.isoformat() if d else None) for t, d in (await db.execute(
                    select(LegalProcess.tenant_id, func.max(LegalProcess.ultimo_andamento_at))
                    .group_by(LegalProcess.tenant_id)
                )).all() if t is not None}
            except Exception:
                ult = {}

        linhas = []
        for tid, nome, plano, ativo in tenants:
            linhas.append({
                "tenant_id": str(tid), "nome": nome, "plano": plano, "ativo": bool(ativo),
                "usuarios_ativos": usuarios.get(tid, 0),
                "processos": processos.get(tid, 0),
                "agent_runs_24h": agent_runs.get(tid, 0),
                "sync_runs": syncs.get(tid, 0),
                "ultima_atividade": ult.get(tid),
            })
        linhas.sort(key=lambda x: x["processos"], reverse=True)
        totais = {
            "tenants": len(linhas),
            "usuarios_ativos": sum(l["usuarios_ativos"] for l in linhas),
            "processos": sum(l["processos"] for l in linhas),
            "agent_runs_24h": sum(l["agent_runs_24h"] for l in linhas),
        }
        return {"ok": True, "tenants": linhas, "totais": totais}
    except Exception as exc:
        log.warning("brain_metrics_failed", error=str(exc))
        return {"ok": False, "tenants": [], "totais": {}, "detail": str(exc)[:200]}
