"""Agregador de observabilidade de infraestrutura (Bloco F / F1).

Consulta em runtime — SEMPRE best-effort, cada sonda com timeout e captura de
exceção — o estado real de: Celery (workers/tasks/beat), Redis (memória/fila),
Qdrant (coleções), Postgres (pool), AgentRun (por status) e SyncRun (captura).

Nada aqui pode derrubar a requisição: qualquer falha vira {"ok": False, ...}.
Consumido pelo painel Cérebro (SUPERADMIN) e pela Saúde do Sistema.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone, timedelta

import structlog

log = structlog.get_logger()

_PROBE_TIMEOUT = 4.0


async def _com_timeout(coro, fallback):
    try:
        return await asyncio.wait_for(coro, timeout=_PROBE_TIMEOUT)
    except Exception as exc:
        log.warning("brain_probe_timeout", error=str(exc))
        return fallback


# ─── Celery ───────────────────────────────────────────────────────────────────
def _inspect_celery_sync() -> dict:
    """celery inspect é síncrono/bloqueante — roda em thread via _celery()."""
    try:
        from app.workers.worker import celery_app
        insp = celery_app.control.inspect(timeout=2.0)
        ping = insp.ping() or {}
        if not ping:
            return {"ok": False, "workers": 0, "detail": "nenhum worker respondeu ao ping"}
        active = insp.active() or {}
        scheduled = insp.scheduled() or {}
        stats = insp.stats() or {}
        workers = []
        for nome in ping:
            st = stats.get(nome, {})
            workers.append({
                "nome": nome,
                "ativas": len(active.get(nome, [])),
                "agendadas": len(scheduled.get(nome, [])),
                "total_processadas": (st.get("total") or {}),
                "concorrencia": (st.get("pool", {}) or {}).get("max-concurrency"),
            })
        # beat schedule declarado (tarefas periódicas configuradas)
        beat = []
        for nome, cfg in (celery_app.conf.beat_schedule or {}).items():
            beat.append({"nome": nome, "task": cfg.get("task"), "schedule": str(cfg.get("schedule"))})
        return {
            "ok": True,
            "workers": len(ping),
            "workers_detail": workers,
            "total_ativas": sum(w["ativas"] for w in workers),
            "beat_schedule": beat,
        }
    except Exception as exc:
        log.warning("celery_inspect_failed", error=str(exc))
        return {"ok": False, "workers": 0, "detail": str(exc)[:200]}


async def _celery() -> dict:
    return await _com_timeout(asyncio.to_thread(_inspect_celery_sync), {"ok": False, "workers": 0, "detail": "timeout"})


# ─── Redis ────────────────────────────────────────────────────────────────────
async def _redis() -> dict:
    async def _run():
        from app.db.redis import get_redis
        r = await get_redis()
        if not r:
            return {"ok": False, "configured": False, "detail": "REDIS_URL não configurado"}
        info = await r.info()
        # profundidade da fila Celery default (lista 'celery' no broker Redis)
        try:
            fila = await r.llen("celery")
        except Exception:
            fila = None
        return {
            "ok": True,
            "configured": True,
            "memoria_usada": info.get("used_memory_human"),
            "clientes_conectados": info.get("connected_clients"),
            "uptime_dias": info.get("uptime_in_days"),
            "total_chaves": (await r.dbsize()),
            "fila_celery": fila,
        }
    return await _com_timeout(_run(), {"ok": False, "detail": "timeout"})


# ─── Qdrant ───────────────────────────────────────────────────────────────────
async def _qdrant() -> dict:
    async def _run():
        from app.config import settings as cfg
        configurado = bool(
            cfg.QDRANT_API_KEY or
            (cfg.QDRANT_URL and cfg.QDRANT_URL not in {"http://qdrant:6333", "http://localhost:6333"})
        )
        if not configurado:
            return {"ok": False, "configured": False, "detail": "Qdrant não configurado (placeholder)"}
        from app.db.qdrant import get_qdrant
        q = await get_qdrant()
        cols = await q.get_collections()
        nomes = [c.name for c in cols.collections]
        colecoes = []
        for nome in nomes:
            try:
                info = await q.count(collection_name=nome, exact=False)
                colecoes.append({"nome": nome, "pontos": info.count})
            except Exception:
                colecoes.append({"nome": nome, "pontos": None})
        return {"ok": True, "configured": True, "colecoes": colecoes, "total_colecoes": len(nomes)}
    return await _com_timeout(_run(), {"ok": False, "detail": "timeout"})


# ─── Postgres (pool) ──────────────────────────────────────────────────────────
def _postgres_pool() -> dict:
    try:
        from app.db.base import engine
        pool = engine.pool
        return {
            "ok": True,
            "tamanho": pool.size(),
            "em_uso": pool.checkedout(),
            "overflow": pool.overflow(),
        }
    except Exception as exc:
        return {"ok": False, "detail": str(exc)[:200]}


# ─── AgentRun por status + SyncRun global ─────────────────────────────────────
async def _jobs() -> dict:
    async def _run():
        from sqlalchemy import select, func
        from app.db.base import AsyncSessionLocal
        from app.models.agent_run import AgentRun
        from app.models.sync_run import SyncRun
        async with AsyncSessionLocal() as db:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            rows = (await db.execute(
                select(AgentRun.status, func.count(AgentRun.id))
                .where(AgentRun.started_at >= cutoff)
                .group_by(AgentRun.status)
            )).all()
            por_status = {status: n for status, n in rows}
            # SyncRun recentes (captura/scan/polling)
            syncs = (await db.execute(
                select(SyncRun.fonte, SyncRun.tipo, SyncRun.status, SyncRun.started_at, SyncRun.stats)
                .order_by(SyncRun.started_at.desc()).limit(10)
            )).all()
            sync_list = [
                {"fonte": s.fonte, "tipo": s.tipo, "status": s.status,
                 "started_at": s.started_at.isoformat() if s.started_at else None,
                 "detalhe": (s.stats or {}).get("fonte_detalhe")}
                for s in syncs
            ]
        return {"ok": True, "agent_runs_24h_por_status": por_status, "sync_runs_recentes": sync_list}
    return await _com_timeout(_run(), {"ok": False, "detail": "timeout"})


# ─── Fontes da Captura (registry + circuit breakers + tabela Tribunal) ────────
async def _fontes() -> dict:
    """Saúde das fontes processuais: estado do circuit breaker de cada fonte do
    registry (comunica/datajud), o conector PDPJ credenciado (por-tenant) e a
    contagem da tabela de referência Tribunal. Best-effort."""
    async def _run():
        resultado: dict = {"ok": True, "fontes": [], "pdpj": None, "tribunais": None}
        # Fontes públicas registradas (comunica, datajud)
        try:
            from app.integrations.fontes.registry import todas_as_fontes
            for f in todas_as_fontes():
                breaker = getattr(f, "_breaker", None)
                resultado["fontes"].append({
                    "nome": getattr(f, "nome", "?"),
                    "capabilities": sorted(c.value for c in getattr(f, "capabilities", set())),
                    "breaker": (breaker.state if breaker is not None else None),
                })
        except Exception as exc:
            resultado["ok"] = False
            resultado["detail"] = str(exc)[:200]
        # PDPJ é credenciado por tenant (fora do registry global) — informativo
        try:
            from app.services.integration_hub import PROVIDERS
            resultado["pdpj"] = {"registrado": "pdpj" in PROVIDERS, "credential_gated": True}
        except Exception:
            pass
        # Tabela de referência de tribunais
        try:
            from sqlalchemy import select, func
            from app.db.base import AsyncSessionLocal
            from app.models.tribunal import Tribunal
            async with AsyncSessionLocal() as db:
                resultado["tribunais"] = (await db.execute(
                    select(func.count(Tribunal.codigo))
                )).scalar_one()
        except Exception:
            pass
        return resultado
    return await _com_timeout(_run(), {"ok": False, "detail": "timeout"})


# ─── Agregação ────────────────────────────────────────────────────────────────
async def coletar_infra() -> dict:
    """Snapshot completo de infra para o painel Cérebro. Best-effort em tudo."""
    t0 = time.monotonic()
    celery, redis, qdrant, jobs, fontes = await asyncio.gather(
        _celery(), _redis(), _qdrant(), _jobs(), _fontes(),
    )
    postgres = _postgres_pool()
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "coleta_ms": int((time.monotonic() - t0) * 1000),
        "celery": celery,
        "redis": redis,
        "qdrant": qdrant,
        "postgres_pool": postgres,
        "jobs": jobs,
        "fontes": fontes,
    }
