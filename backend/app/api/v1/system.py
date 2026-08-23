"""Endpoints de sistema — métricas reais, navegação dinâmica, analytics."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, text
from datetime import date, datetime, timezone, timedelta, time as dtime
import json
import uuid
from typing import Any, Callable, Awaitable

from app.db.base import get_db
from app.dependencies import get_current_user, require_role
from app.models.user import User

router = APIRouter(prefix="/system", tags=["system"])


async def _cached(key: str, ttl: int, compute_fn: Callable[[], Awaitable[Any]]) -> Any:
    """Fetch from Redis cache or compute and store result."""
    try:
        from app.db.redis import get_redis
        redis = await get_redis()
        if redis:
            cached = await redis.get(f"analytics:{key}")
            if cached:
                return json.loads(cached)
    except Exception:
        pass

    result = await compute_fn()

    try:
        from app.db.redis import get_redis
        redis = await get_redis()
        if redis:
            await redis.setex(f"analytics:{key}", ttl, json.dumps(result))
    except Exception:
        pass

    return result

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
    {"href": "/admin/health", "label": "Saúde do Sistema", "icon": "Activity"},
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
    force_refresh: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """KPIs reais para o dashboard (cache 60s)."""
    from app.models.process import LegalProcess, ProcessDeadline
    from app.models.agent_run import Approval
    from app.models.agent_run import AgentRun

    cache_key = f"metrics:{current_user.tenant_id}"

    if force_refresh:
        try:
            from app.db.redis import get_redis
            redis = await get_redis()
            if redis:
                await redis.delete(f"analytics:{cache_key}")
        except Exception:
            pass

    async def compute():
        now = datetime.now(timezone.utc)
        next_7d = now + timedelta(days=7)

        r1 = await db.execute(
            select(func.count(LegalProcess.id)).where(
                LegalProcess.situacao == "ATIVO",
                LegalProcess.tenant_id == current_user.tenant_id,
            )
        )
        processos_ativos = r1.scalar_one() or 0

        r2 = await db.execute(
            select(func.count(ProcessDeadline.id))
            .join(LegalProcess, ProcessDeadline.process_id == LegalProcess.id)
            .where(
                and_(
                    ProcessDeadline.status == "PENDENTE",
                    ProcessDeadline.data_prazo <= next_7d.date(),
                    ProcessDeadline.data_prazo >= now.date(),
                    LegalProcess.tenant_id == current_user.tenant_id,
                )
            )
        )
        prazos_proximos = r2.scalar_one() or 0

        r3 = await db.execute(
            select(func.count(Approval.id)).where(
                Approval.status == "PENDENTE",
                Approval.tenant_id == current_user.tenant_id,
            )
        )
        aprovacoes_pendentes = r3.scalar_one() or 0

        inicio_mes = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        r4 = await db.execute(
            select(func.coalesce(func.sum(AgentRun.tokens_used), 0)).where(
                AgentRun.started_at >= inicio_mes,
                AgentRun.tenant_id == current_user.tenant_id,
            )
        )
        tokens_mes = r4.scalar_one() or 0
        custo_ia_mes = round(float(tokens_mes) * 0.000015, 2)

        r5 = await db.execute(
            select(func.count(AgentRun.id)).where(
                AgentRun.started_at >= now - timedelta(hours=24),
                AgentRun.status.in_(["RUNNING", "AWAITING_APPROVAL"]),
                AgentRun.tenant_id == current_user.tenant_id,
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

    return await _cached(cache_key, 60, compute)


@router.get("/analytics/financeiro")
async def analytics_financeiro(
    meses: int = Query(default=6, ge=1, le=24),
    force_refresh: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dados financeiros para gráficos (cache 5 min)."""
    from app.models.financial import FinancialEntry

    tid = current_user.tenant_id
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=meses * 31)
    cache_key = f"fin:{tid}:{meses}"

    if force_refresh:
        try:
            from app.db.redis import get_redis
            r = await get_redis()
            if r:
                await r.delete(f"analytics:{cache_key}")
        except Exception:
            pass

    async def compute():
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

        all_months = sorted(set(list(receitas_por_mes) + list(despesas_por_mes)))
        mensal = [
            {
                "mes": m,
                "receitas": round(receitas_por_mes.get(m, 0), 2),
                "despesas": round(despesas_por_mes.get(m, 0), 2),
            }
            for m in all_months
        ]

        saldo = 0.0
        for item in mensal:
            saldo += item["receitas"] - item["despesas"]
            item["saldo"] = round(saldo, 2)

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

        q_tot = await db.execute(
            select(FinancialEntry.tipo, FinancialEntry.status, func.sum(FinancialEntry.valor).label("total_grupo"))
            .where(FinancialEntry.tenant_id == tid)
            .group_by(FinancialEntry.tipo, FinancialEntry.status)
        )
        totais: dict = {}
        for r in q_tot.all():
            totais[f"{r.tipo}_{r.status}"] = float(r.total_grupo or 0)

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

    return await _cached(cache_key, 300, compute)


@router.get("/analytics/processos")
async def analytics_processos(
    force_refresh: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Estatísticas de processos para gráficos (cache 10 min)."""
    from app.models.process import LegalProcess

    tid = current_user.tenant_id
    now = datetime.now(timezone.utc)
    cutoff_6m = now - timedelta(days=183)
    cache_key = f"proc:{tid}"

    if force_refresh:
        try:
            from app.db.redis import get_redis
            r = await get_redis()
            if r:
                await r.delete(f"analytics:{cache_key}")
        except Exception:
            pass

    async def compute():
        q_sit = await db.execute(
            select(LegalProcess.situacao, func.count(LegalProcess.id).label("count"))
            .where(LegalProcess.tenant_id == tid)
            .group_by(LegalProcess.situacao)
        )
        por_situacao = [{"situacao": r.situacao or "Indefinido", "count": r.count} for r in q_sit.all()]

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

    return await _cached(cache_key, 600, compute)


@router.get("/analytics/agentes")
async def analytics_agentes(
    dias: int = Query(default=30, ge=1, le=90),
    force_refresh: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Métricas de performance e custo dos agentes IA (cache 2 min)."""
    from app.models.agent_run import AgentRun

    tid = current_user.tenant_id
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=dias)
    cache_key = f"agents:{tid}:{dias}"

    if force_refresh:
        try:
            from app.db.redis import get_redis
            r = await get_redis()
            if r:
                await r.delete(f"analytics:{cache_key}")
        except Exception:
            pass

    async def compute():
        q_ag = await db.execute(
            select(
                AgentRun.agent_name,
                func.sum(AgentRun.cost_usd).label("custo"),
                func.sum(AgentRun.tokens_used).label("tokens"),
                func.count(AgentRun.id).label("execucoes"),
                func.avg(AgentRun.duration_ms).label("avg_ms"),
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

    return await _cached(cache_key, 120, compute)


@router.get("/analytics/gestao")
async def analytics_gestao(
    date_from: date | None = Query(default=None, description="Filtra por período (inclusive). Sem filtro = histórico completo."),
    date_to: date | None = Query(default=None, description="Filtra por período (inclusive). Sem filtro = histórico completo."),
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "GESTOR")),
    db: AsyncSession = Depends(get_db),
):
    """Relatórios de gestão do sócio: rentabilidade, produtividade e taxa de êxito
    (cache 5 min, chave varia por período). Fase 206.3 — `date_from`/`date_to`
    opcionais habilitam comparativo de período no frontend (2 chamadas, uma por
    período). Cada bloco de métrica usa o campo de data mais natural pro que
    representa — ver comentários abaixo; `processos_ativos`/`prazos_pendentes`
    (carga ATUAL) e `prazos_cumpridos` (sem timestamp de conclusão no model)
    ficam de fora do filtro em qualquer período, por design."""
    from app.models.financial import FinancialEntry
    from app.models.client import Client
    from app.models.process import LegalProcess, ProcessDeadline
    from app.models.document import Document
    from app.models.tese import Tese

    tid = current_user.tenant_id
    periodo_ini = datetime.combine(date_from, dtime.min, tzinfo=timezone.utc) if date_from else None
    periodo_fim = datetime.combine(date_to, dtime.max, tzinfo=timezone.utc) if date_to else None

    async def compute():
        # ── Rentabilidade por cliente (receita − despesa, pagos) ─────────────
        fin_where = [FinancialEntry.tenant_id == tid, FinancialEntry.status == "PAGO"]
        if date_from:
            fin_where.append(FinancialEntry.data_pagamento >= date_from)
        if date_to:
            fin_where.append(FinancialEntry.data_pagamento <= date_to)
        fin_rows = (await db.execute(
            select(FinancialEntry.client_id, FinancialEntry.tipo, func.coalesce(func.sum(FinancialEntry.valor), 0))
            .where(*fin_where)
            .group_by(FinancialEntry.client_id, FinancialEntry.tipo)
        )).all()
        por_cliente: dict = {}
        for cid, tipo, val in fin_rows:
            key = str(cid) if cid else None
            e = por_cliente.setdefault(key, {"receita": 0.0, "despesa": 0.0})
            e["receita" if tipo == "RECEITA" else "despesa"] += float(val or 0)
        nomes = {}
        cids = [uuid.UUID(k) for k in por_cliente if k]
        if cids:
            for c in (await db.execute(select(Client).where(Client.id.in_(cids)))).scalars().all():
                nomes[str(c.id)] = c.nome_completo
        rentab_clientes = sorted(
            [{"cliente": nomes.get(k, "Sem cliente") if k else "Sem cliente",
              "receita": v["receita"], "despesa": v["despesa"], "resultado": v["receita"] - v["despesa"]}
             for k, v in por_cliente.items()],
            key=lambda x: x["resultado"], reverse=True,
        )[:12]

        # ── Rentabilidade por processo (mesmo filtro de data_pagamento) ────────
        proc_fin_where = [FinancialEntry.tenant_id == tid, FinancialEntry.status == "PAGO", FinancialEntry.process_id.is_not(None)]
        if date_from:
            proc_fin_where.append(FinancialEntry.data_pagamento >= date_from)
        if date_to:
            proc_fin_where.append(FinancialEntry.data_pagamento <= date_to)
        proc_rows = (await db.execute(
            select(FinancialEntry.process_id, FinancialEntry.tipo, func.coalesce(func.sum(FinancialEntry.valor), 0))
            .where(*proc_fin_where)
            .group_by(FinancialEntry.process_id, FinancialEntry.tipo)
        )).all()
        por_proc: dict = {}
        for pid, tipo, val in proc_rows:
            e = por_proc.setdefault(str(pid), {"receita": 0.0, "despesa": 0.0})
            e["receita" if tipo == "RECEITA" else "despesa"] += float(val or 0)
        proc_nomes = {}
        pids = [uuid.UUID(k) for k in por_proc]
        if pids:
            for p in (await db.execute(select(LegalProcess).where(LegalProcess.id.in_(pids)))).scalars().all():
                proc_nomes[str(p.id)] = p.numero_cnj or "Sem CNJ"
        rentab_processos = sorted(
            [{"processo": proc_nomes.get(k, "—"), "resultado": v["receita"] - v["despesa"]}
             for k, v in por_proc.items()],
            key=lambda x: x["resultado"], reverse=True,
        )[:12]

        # ── Produtividade por advogado — "processos"/"documentos" contam só o
        # que foi CRIADO no período (created_at); sem período = histórico
        # completo, igual ao comportamento anterior a esta fase. ─────────────
        proc_por_resp_where = [LegalProcess.tenant_id == tid, LegalProcess.responsavel_id.is_not(None)]
        if periodo_ini:
            proc_por_resp_where.append(LegalProcess.created_at >= periodo_ini)
        if periodo_fim:
            proc_por_resp_where.append(LegalProcess.created_at <= periodo_fim)
        proc_por_resp = dict((await db.execute(
            select(LegalProcess.responsavel_id, func.count(LegalProcess.id))
            .where(*proc_por_resp_where)
            .group_by(LegalProcess.responsavel_id)
        )).all())
        docs_where = [Document.tenant_id == tid, Document.created_by.is_not(None)]
        if periodo_ini:
            docs_where.append(Document.created_at >= periodo_ini)
        if periodo_fim:
            docs_where.append(Document.created_at <= periodo_fim)
        docs_por_autor = dict((await db.execute(
            select(Document.created_by, func.count(Document.id))
            .where(*docs_where)
            .group_by(Document.created_by)
        )).all())
        prazos_cumpridos = dict((await db.execute(
            select(ProcessDeadline.responsavel_id, func.count(ProcessDeadline.id))
            .join(LegalProcess, ProcessDeadline.process_id == LegalProcess.id)
            .where(LegalProcess.tenant_id == tid, ProcessDeadline.status == "CUMPRIDO",
                   ProcessDeadline.responsavel_id.is_not(None))
            .group_by(ProcessDeadline.responsavel_id)
        )).all())
        # Carga atual: processos em andamento e prazos ainda pendentes por responsável
        proc_ativos_por_resp = dict((await db.execute(
            select(LegalProcess.responsavel_id, func.count(LegalProcess.id))
            .where(LegalProcess.tenant_id == tid, LegalProcess.responsavel_id.is_not(None),
                   LegalProcess.situacao.in_(["ATIVO", "SUSPENSO"]))
            .group_by(LegalProcess.responsavel_id)
        )).all())
        prazos_pendentes = dict((await db.execute(
            select(ProcessDeadline.responsavel_id, func.count(ProcessDeadline.id))
            .join(LegalProcess, ProcessDeadline.process_id == LegalProcess.id)
            .where(LegalProcess.tenant_id == tid, ProcessDeadline.status == "PENDENTE",
                   ProcessDeadline.responsavel_id.is_not(None))
            .group_by(ProcessDeadline.responsavel_id)
        )).all())
        usuarios = (await db.execute(
            select(User).where(User.tenant_id == tid, User.is_active == True, User.role != "CLIENT")  # noqa: E712
        )).scalars().all()
        produtividade = sorted(
            [{"id": str(u.id), "advogado": u.full_name,
              "processos": int(proc_por_resp.get(u.id, 0)),
              "processos_ativos": int(proc_ativos_por_resp.get(u.id, 0)),
              "prazos_pendentes": int(prazos_pendentes.get(u.id, 0)),
              "documentos": int(docs_por_autor.get(u.id, 0)),
              "prazos_cumpridos": int(prazos_cumpridos.get(u.id, 0))}
             for u in usuarios],
            key=lambda x: x["processos"], reverse=True,
        )

        # ── Taxa de êxito (processos com desfecho). O model não guarda um
        # timestamp dedicado de "quando o desfecho foi registrado" — usa
        # `updated_at` como proxy (igual aproximação já aceita em
        # `protocolado_em`/`updated_at` na Fase 205.1, documentada lá pelo
        # mesmo motivo: sem campo dedicado, é a melhor data disponível). ─────
        desf_where = [LegalProcess.tenant_id == tid, LegalProcess.desfecho.is_not(None)]
        if periodo_ini:
            desf_where.append(LegalProcess.updated_at >= periodo_ini)
        if periodo_fim:
            desf_where.append(LegalProcess.updated_at <= periodo_fim)
        desf_rows = dict((await db.execute(
            select(LegalProcess.desfecho, func.count(LegalProcess.id))
            .where(*desf_where)
            .group_by(LegalProcess.desfecho)
        )).all())
        total_desf = sum(desf_rows.values())
        ganhos = desf_rows.get("EXITO", 0) + desf_rows.get("ACORDO", 0)
        win_rate = round(100 * ganhos / total_desf, 1) if total_desf else 0.0
        por_area_rows = (await db.execute(
            select(LegalProcess.area_direito, LegalProcess.desfecho, func.count(LegalProcess.id))
            .where(*desf_where)
            .group_by(LegalProcess.area_direito, LegalProcess.desfecho)
        )).all()
        area_map: dict = {}
        for area, desf, n in por_area_rows:
            a = area_map.setdefault(area or "Sem área", {"ganhos": 0, "total": 0})
            a["total"] += int(n)
            if desf in ("EXITO", "ACORDO"):
                a["ganhos"] += int(n)
        exito_por_area = [
            {"area": k, "win_rate": round(100 * v["ganhos"] / v["total"], 1) if v["total"] else 0.0, "total": v["total"]}
            for k, v in sorted(area_map.items(), key=lambda kv: kv[1]["total"], reverse=True)
        ]

        # ── Fase 138.4 — taxa de êxito por tribunal (jurimetria do escritório,
        # texto livre — sem FK real pra Tribunal, GROUP BY funciona igual) ────
        por_tribunal_rows = (await db.execute(
            select(LegalProcess.tribunal, LegalProcess.desfecho, func.count(LegalProcess.id))
            .where(*desf_where)
            .group_by(LegalProcess.tribunal, LegalProcess.desfecho)
        )).all()
        tribunal_map: dict = {}
        for tribunal, desf, n in por_tribunal_rows:
            t = tribunal_map.setdefault(tribunal, {"ganhos": 0, "total": 0})
            t["total"] += int(n)
            if desf in ("EXITO", "ACORDO"):
                t["ganhos"] += int(n)
        exito_por_tribunal = [
            {"tribunal": k, "win_rate": round(100 * v["ganhos"] / v["total"], 1) if v["total"] else 0.0, "total": v["total"]}
            for k, v in sorted(tribunal_map.items(), key=lambda kv: kv[1]["total"], reverse=True)
        ]

        # ── Fase 138.4 — taxa de êxito por tese (só processos com tese_id
        # definida — a maioria hoje não tem, campo é novo) ────────────────────
        por_tese_rows = (await db.execute(
            select(LegalProcess.tese_id, LegalProcess.desfecho, func.count(LegalProcess.id))
            .where(*desf_where, LegalProcess.tese_id.is_not(None))
            .group_by(LegalProcess.tese_id, LegalProcess.desfecho)
        )).all()
        tese_map: dict = {}
        for tese_id, desf, n in por_tese_rows:
            t = tese_map.setdefault(tese_id, {"ganhos": 0, "total": 0})
            t["total"] += int(n)
            if desf in ("EXITO", "ACORDO"):
                t["ganhos"] += int(n)
        tese_nomes = {}
        if tese_map:
            tese_nomes = dict((await db.execute(
                select(Tese.id, Tese.nome).where(Tese.id.in_(tese_map.keys()))
            )).all())
        exito_por_tese = [
            {"tese": tese_nomes.get(k, "—"), "win_rate": round(100 * v["ganhos"] / v["total"], 1) if v["total"] else 0.0, "total": v["total"]}
            for k, v in sorted(tese_map.items(), key=lambda kv: kv[1]["total"], reverse=True)
        ]

        return {
            "rentabilidade_clientes": rentab_clientes,
            "rentabilidade_processos": rentab_processos,
            "produtividade_advogados": produtividade,
            "taxa_exito": {
                "por_desfecho": {k: int(v) for k, v in desf_rows.items()},
                "total_com_desfecho": int(total_desf),
                "win_rate": win_rate,
                "por_area": exito_por_area,
                "por_tribunal": exito_por_tribunal,
                "por_tese": exito_por_tese,
            },
        }

    return await _cached(f"gestao:{tid}:{date_from or ''}:{date_to or ''}", 300, compute)


@router.get("/analytics/lgpd-qualidade")
async def analytics_lgpd_qualidade(
    current_user: User = Depends(require_role("ADMIN", "SOCIO")),
    db: AsyncSession = Depends(get_db),
):
    """Fase 212 (proposta de evolução da Fase 209) — painel de qualidade de
    dado LGPD-aware: não é um relatório de gestão comum, é sensível a PII
    (mostra quais clientes têm lacuna de conformidade), por isso restrito a
    ADMIN/SOCIO — mesmo gate de erase_client_data/export_client_data.
    Sinaliza 3 lacunas concretas de conformidade, cada uma acionável:
    (1) cliente ATIVO sem `lgpd_consent` registrado, (2) `lgpd_consent=True`
    mas sem `lgpd_consent_at` (dado inconsistente — não dá pra provar
    QUANDO o consentimento foi obtido), (3) titular sem CPF/CNPJ cadastrado
    (documento de identificação ausente). Cache 5 min como os outros
    relatórios de /analytics."""
    from app.models.client import Client

    tid = current_user.tenant_id

    async def compute():
        clientes = (await db.execute(
            select(Client.id, Client.nome_completo, Client.tipo, Client.status,
                   Client.cpf, Client.cnpj, Client.lgpd_consent, Client.lgpd_consent_at)
            .where(Client.tenant_id == tid)
        )).all()

        total = len(clientes)
        sem_consentimento_ativo = []
        consentimento_sem_data = []
        sem_documento = []
        for c in clientes:
            if c.status == "ATIVO" and not c.lgpd_consent:
                sem_consentimento_ativo.append({"id": str(c.id), "nome": c.nome_completo})
            if c.lgpd_consent and not c.lgpd_consent_at:
                consentimento_sem_data.append({"id": str(c.id), "nome": c.nome_completo})
            documento_ausente = (c.tipo == "PF" and not c.cpf) or (c.tipo == "PJ" and not c.cnpj)
            if documento_ausente:
                sem_documento.append({"id": str(c.id), "nome": c.nome_completo, "tipo": c.tipo})

        com_consentimento = sum(1 for c in clientes if c.lgpd_consent)
        score = 100 if total == 0 else round(
            100 * (1 - (len(sem_consentimento_ativo) + len(consentimento_sem_data) + len(sem_documento)) / (total * 3))
        )

        return {
            "total_clientes": total,
            "score_conformidade": max(0, score),
            "taxa_consentimento": round(100 * com_consentimento / total, 1) if total else None,
            "lacunas": {
                "sem_consentimento_ativo": {
                    "total": len(sem_consentimento_ativo), "clientes": sem_consentimento_ativo[:50],
                },
                "consentimento_sem_data": {
                    "total": len(consentimento_sem_data), "clientes": consentimento_sem_data[:50],
                },
                "sem_documento_identificacao": {
                    "total": len(sem_documento), "clientes": sem_documento[:50],
                },
            },
        }

    return await _cached(f"lgpd-qualidade:{tid}", 300, compute)


@router.get("/health/detailed")
async def health_detailed(current_user: User = Depends(get_current_user)):
    """Health check detalhado com latências — ADMIN/SOCIO/SUPERADMIN.

    (SUPERADMIN estava sendo rejeitado aqui apesar de ver a página de Saúde no
    frontend — divergência de gate corrigida no Bloco F.)"""
    if current_user.role not in ("ADMIN", "SOCIO", "SUPERADMIN"):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Acesso negado")

    import time
    import asyncio

    async def probe_postgres(db_session) -> tuple[bool, int]:
        t0 = time.monotonic()
        try:
            await db_session.execute(text("SELECT 1"))
            return True, int((time.monotonic() - t0) * 1000)
        except Exception:
            return False, -1

    async def probe_redis() -> tuple[bool, int]:
        t0 = time.monotonic()
        try:
            from app.db.redis import get_redis
            redis = await get_redis()
            if redis:
                await redis.ping()
                return True, int((time.monotonic() - t0) * 1000)
        except Exception:
            pass
        return False, -1

    async def probe_qdrant() -> tuple[bool, int]:
        t0 = time.monotonic()
        try:
            from app.db.qdrant import get_qdrant
            qdrant = await get_qdrant()
            if qdrant:
                return True, int((time.monotonic() - t0) * 1000)
        except Exception:
            pass
        return False, -1

    async def probe_anthropic() -> tuple[bool, int]:
        """Verifica conectividade com o provider de IA de SISTEMA ativo (Anthropic
        ou Gemini), listando modelos (sem gerar tokens).

        Observação: este é o provider CENTRAL do escritório. Como o sistema é
        BYOK-first (cada usuário pode trazer a própria chave em "Minha IA"), a
        ausência de chave central NÃO é um erro — é apenas "não configurado".
        Nesse caso não fazemos a chamada de rede (evita um 401 inútil)."""
        t0 = time.monotonic()
        try:
            from app.config import settings as _cfg
            from app.integrations.llm_client import resolve_provider
            import httpx
            provider = resolve_provider(None)
            key = (_cfg.GEMINI_API_KEY or _cfg.OPENAI_API_KEY) if provider == "gemini" else _cfg.ANTHROPIC_API_KEY
            if not key:
                # Sem chave central: BYOK cobre o uso. Não é falha.
                return False, -1
            async with httpx.AsyncClient(timeout=5) as c:
                if provider == "gemini":
                    r = await c.get(
                        "https://generativelanguage.googleapis.com/v1beta/models",
                        params={"key": key},
                    )
                else:
                    r = await c.get(
                        "https://api.anthropic.com/v1/models",
                        headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                    )
                return r.status_code == 200, int((time.monotonic() - t0) * 1000)
        except Exception:
            return False, -1

    async def probe_datajud() -> tuple[bool, int]:
        """Verifica acesso ao CNJ DataJud (API pública)."""
        t0 = time.monotonic()
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get("https://api-publica.datajud.cnj.jus.br/", timeout=5)
                return r.status_code < 500, int((time.monotonic() - t0) * 1000)
        except Exception:
            return False, -1

    from app.db.base import AsyncSessionLocal
    from app.models.agent_run import AgentRun

    async with AsyncSessionLocal() as db_check:
        pg_ok, pg_ms = await probe_postgres(db_check)

    (redis_ok, redis_ms), (qdrant_ok, qdrant_ms), (anthropic_ok, anthropic_ms), (datajud_ok, datajud_ms) = await asyncio.gather(
        probe_redis(), probe_qdrant(), probe_anthropic(), probe_datajud()
    )

    # Recent agent activity (last 24h)
    async with AsyncSessionLocal() as db2:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        q = await db2.execute(
            select(AgentRun.agent_name, AgentRun.status, AgentRun.started_at)
            .where(AgentRun.started_at >= cutoff)
            .order_by(AgentRun.started_at.desc())
            .limit(20)
        )
        recent_runs = [
            {"agent": r.agent_name, "status": r.status, "started_at": r.started_at.isoformat()}
            for r in q.all()
        ]

    # Celery: workers vivos + tarefas ativas (leve — inspect com timeout curto).
    try:
        from app.services.brain_infra import _celery as _celery_probe
        celery_status = await _celery_probe()
    except Exception:
        celery_status = {"ok": False, "workers": 0}

    from app.config import settings as cfg
    from app.core.events import APP_START_TIME
    from app.integrations.llm_client import resolve_provider as _resolve_provider

    # IA central: qual provider está ativo e se há chave de sistema configurada.
    # BYOK-first: sem chave central não é erro (usuários trazem a própria chave).
    # Resiliente: uma exceção aqui NÃO pode derrubar (500) a página de saúde.
    try:
        _ai_provider = _resolve_provider(None)
    except Exception:
        _ai_provider = "anthropic"
    _ai_configured = bool(
        (cfg.GEMINI_API_KEY or cfg.OPENAI_API_KEY) if _ai_provider == "gemini" else cfg.ANTHROPIC_API_KEY
    )
    services = {
        "postgresql": {"ok": pg_ok, "latency_ms": pg_ms},
        "redis": {"ok": redis_ok, "latency_ms": redis_ms},
        "qdrant": {"ok": qdrant_ok, "latency_ms": qdrant_ms},
        "anthropic": {
            "ok": anthropic_ok,
            "latency_ms": anthropic_ms,
            "configured": _ai_configured,
            "provider": _ai_provider,
        },
        "datajud": {"ok": datajud_ok, "latency_ms": datajud_ms},
    }
    core_ok = all(services[k]["ok"] for k in ("postgresql", "redis"))

    uptime_seconds = int((datetime.now(timezone.utc) - APP_START_TIME).total_seconds()) if APP_START_TIME else None

    return {
        "status": "operational" if core_ok else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": cfg.VERSION,
        "environment": cfg.ENVIRONMENT,
        "uptime_seconds": uptime_seconds,
        "services": services,
        "email_enabled": cfg.EMAIL_ENABLED,
        "sentry_enabled": bool(cfg.SENTRY_DSN),
        "recent_agent_runs": recent_runs,
        "celery": {"ok": celery_status.get("ok"), "workers": celery_status.get("workers", 0),
                   "total_ativas": celery_status.get("total_ativas", 0)},
    }


@router.get("/ai-costs")
async def ai_costs_por_usuario(
    dias: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Custos de IA por usuário do escritório (tenant-scoped).

    Base do Painel de Custos de IA: agrega tokens/custo/execuções dos
    AgentRuns por usuário disparador nos últimos N dias. ADMIN/SOCIO."""
    from app.core.exceptions import ForbiddenError
    from app.models.agent_run import AgentRun

    if current_user.role not in ("ADMIN", "SUPERADMIN", "SOCIO"):
        raise ForbiddenError("Acesso restrito a administradores e sócios")

    cutoff = datetime.now(timezone.utc) - timedelta(days=dias)
    result = await db.execute(
        select(
            User.id,
            User.full_name,
            User.email,
            func.count(AgentRun.id).label("execucoes"),
            func.coalesce(func.sum(AgentRun.tokens_used), 0).label("tokens"),
            func.coalesce(func.sum(AgentRun.cost_usd), 0).label("custo_usd"),
        )
        .join(AgentRun, AgentRun.triggered_by == User.id)
        .where(
            AgentRun.tenant_id == current_user.tenant_id,  # isolamento multi-tenant
            AgentRun.started_at >= cutoff,
        )
        .group_by(User.id, User.full_name, User.email)
        .order_by(func.coalesce(func.sum(AgentRun.cost_usd), 0).desc())
    )
    rows = result.all()

    # Limites de orçamento cadastrados (para exibir teto e % usado por usuário)
    from app.models.user import AIBudgetLimit
    limites = {
        str(b.user_id): float(b.monthly_limit_usd)
        for b in (await db.execute(
            select(AIBudgetLimit).where(AIBudgetLimit.tenant_id == current_user.tenant_id)
        )).scalars().all()
    }

    usuarios = []
    for r in rows:
        uid = str(r.id)
        custo = float(r.custo_usd)
        limite = limites.get(uid)
        usuarios.append({
            "user_id": uid,
            "nome": r.full_name,
            "email": r.email,
            "execucoes": int(r.execucoes),
            "tokens": int(r.tokens),
            "custo_usd": custo,
            "limite_usd": limite,
            "pct_limite": round(custo / limite * 100, 1) if limite else None,
        })
    return {
        "periodo_dias": dias,
        "total_execucoes": sum(u["execucoes"] for u in usuarios),
        "total_tokens": sum(u["tokens"] for u in usuarios),
        "total_custo_usd": round(sum(u["custo_usd"] for u in usuarios), 4),
        "usuarios": usuarios,
    }


@router.get("/health/tenant-infra")
async def health_tenant_infra(
    current_user: User = Depends(require_role("ADMIN", "SOCIO", "SUPERADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Saúde do PRÓPRIO escritório para a tela de Saúde do Sistema (ADMIN/SOCIO).

    Complementa /system/brain/infra (visão de plataforma, SUPERADMIN-only, que
    hoje 403 silenciosamente pra quem acessa a tela de Saúde sem ser
    SUPERADMIN). Best-effort por seção — uma falha isolada não derruba as
    demais."""
    tenant_id = current_user.tenant_id

    integracoes_conectadas: list[dict] = []
    try:
        from app.services import integration_hub
        status_list = await integration_hub.list_status(db, tenant_id)
        integracoes_conectadas = [
            {"provider": i["provider"], "nome": i["nome"], "status": i["status"]}
            for i in status_list if i["status"] == "CONECTADA"
        ]
    except Exception:
        pass

    custo_ia = None
    try:
        from app.models.agent_run import AgentRun
        from app.models.user import AIBudgetLimit
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        custo_total, execucoes = (await db.execute(
            select(
                func.coalesce(func.sum(AgentRun.cost_usd), 0),
                func.count(AgentRun.id),
            ).where(AgentRun.tenant_id == tenant_id, AgentRun.started_at >= cutoff)
        )).one()
        limite_total = (await db.execute(
            select(func.coalesce(func.sum(AIBudgetLimit.monthly_limit_usd), 0))
            .where(AIBudgetLimit.tenant_id == tenant_id)
        )).scalar_one()
        custo_ia = {
            "total_usd": round(float(custo_total), 4),
            "execucoes": int(execucoes),
            "limite_usd": float(limite_total) if limite_total else None,
            "periodo_dias": 30,
        }
    except Exception:
        pass

    captura = None
    try:
        from app.models.process import LegalProcess
        from app.models.sync_run import SyncRun
        monitorados = (await db.execute(
            select(func.count(LegalProcess.id)).where(
                LegalProcess.tenant_id == tenant_id, LegalProcess.monitoring_active.is_(True),
            )
        )).scalar_one()
        ultimo = (await db.execute(
            select(SyncRun.fonte, SyncRun.tipo, SyncRun.status, SyncRun.started_at)
            .where(SyncRun.tenant_id == tenant_id)
            .order_by(SyncRun.started_at.desc()).limit(1)
        )).first()
        captura = {
            "processos_monitorados": monitorados,
            "ultima_sincronizacao": {
                "fonte": ultimo.fonte, "tipo": ultimo.tipo, "status": ultimo.status,
                "started_at": ultimo.started_at.isoformat() if ultimo.started_at else None,
            } if ultimo else None,
        }
    except Exception:
        pass

    return {
        "integracoes_conectadas": integracoes_conectadas,
        "custo_ia": custo_ia,
        "captura": captura,
    }


class AIBudgetUpdate(BaseModel):
    user_id: str
    monthly_limit_usd: float | None = None   # None/0 remove o limite
    alert_pct: int = 80


@router.put("/ai-budgets")
async def set_ai_budget(
    body: AIBudgetUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Define/remove o teto mensal de IA de um usuário do escritório (ADMIN/SÓCIO)."""
    import uuid as _uuid
    from app.core.exceptions import ForbiddenError, NotFoundError
    from app.models.user import AIBudgetLimit

    if current_user.role not in ("ADMIN", "SUPERADMIN", "SOCIO"):
        raise ForbiddenError("Acesso restrito a administradores e sócios")
    if not (0 <= body.alert_pct <= 100):
        body.alert_pct = 80

    # Fase 199: sem isso, o próprio ADMIN do tenant demo poderia remover ou
    # inflar o teto de IA da sua conta via este endpoint (o alvo já é
    # filtrado por tenant, sem excluir a si mesmo).
    from fastapi import HTTPException
    from app.services.demo_guard import tenant_is_demo
    if await tenant_is_demo(db, current_user.tenant_id):
        raise HTTPException(
            status_code=403,
            detail="Teto de IA do ambiente de demonstração não pode ser alterado.",
        )

    target_id = _uuid.UUID(body.user_id)
    # Só permite gerir usuários do MESMO escritório (isolamento multi-tenant)
    target = (await db.execute(
        select(User).where(User.id == target_id, User.tenant_id == current_user.tenant_id)
    )).scalar_one_or_none()
    if not target:
        raise NotFoundError("Usuário", body.user_id)

    existing = (await db.execute(
        select(AIBudgetLimit).where(AIBudgetLimit.user_id == target_id)
    )).scalar_one_or_none()

    if not body.monthly_limit_usd or body.monthly_limit_usd <= 0:
        if existing:
            await db.delete(existing)
            await db.flush()
        return {"user_id": body.user_id, "monthly_limit_usd": None, "message": "Limite removido"}

    if existing:
        existing.monthly_limit_usd = body.monthly_limit_usd
        existing.alert_pct = body.alert_pct
    else:
        db.add(AIBudgetLimit(
            user_id=target_id,
            tenant_id=current_user.tenant_id,
            monthly_limit_usd=body.monthly_limit_usd,
            alert_pct=body.alert_pct,
        ))
    await db.flush()
    return {"user_id": body.user_id, "monthly_limit_usd": body.monthly_limit_usd,
            "alert_pct": body.alert_pct, "message": "Limite salvo"}


@router.post("/ai-budget/request-increase")
async def request_ai_budget_increase(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fase 205.5 — o usuário bloqueado pelo teto mensal de IA (429 de
    enforce_budget) pode pedir um aumento direto pela tela, em vez do fluxo
    manual anterior (falar com o admin fora do sistema). Notifica todo
    ADMIN/SÓCIO/SUPERADMIN do escritório com o gasto atual — não altera o
    teto sozinho, quem decide continua sendo o humano em /custos-ia (mesmo
    invariante de nunca auto-aprovar do resto do sistema)."""
    from fastapi import HTTPException
    from app.services.ai_budget import get_budget_status
    from app.services.notification import create_notification

    status = await get_budget_status(db, current_user.id, current_user.tenant_id)
    if not status:
        raise HTTPException(status_code=422, detail="Você não tem um teto de IA configurado.")

    # No máximo 1 solicitação por dia por usuário — evita virar gerador de
    # notificação em massa se o usuário insistir em disparar agentes bloqueados.
    from datetime import datetime, timezone
    from app.models.notification import Notification
    dia_chave = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ja_pediu_hoje = (await db.execute(
        select(Notification.id).where(
            Notification.tipo == "SISTEMA",
            Notification.extra_data["budget_increase_request_day"].astext == dia_chave,
            Notification.extra_data["requested_by"].astext == str(current_user.id),
        ).limit(1)
    )).scalar_one_or_none()
    if ja_pediu_hoje:
        return {"message": "Você já solicitou um aumento hoje — aguarde a análise do administrador."}

    gestores = (await db.execute(
        select(User.id).where(
            User.tenant_id == current_user.tenant_id,
            User.role.in_(["ADMIN", "SOCIO", "SUPERADMIN"]),
            User.is_active == True,  # noqa: E712
        )
    )).scalars().all()
    for gestor_id in gestores:
        await create_notification(
            db, user_id=gestor_id,
            titulo=f"{current_user.full_name} solicitou aumento do teto de IA",
            tipo="SISTEMA",
            corpo=(
                f"Uso atual: US$ {status['spent_usd']:.2f} de US$ {status['limit_usd']:.2f} "
                f"({status['pct']:.0f}%). Ajuste o teto em Custos de IA se aprovar."
            ),
            priority="HIGH",
            link="/custos-ia",
            metadata={"budget_increase_request_day": dia_chave, "requested_by": str(current_user.id)},
        )
    return {"message": "Solicitação enviada ao(s) administrador(es) do escritório."}


# ─── Painel Cérebro (SUPERADMIN) — observabilidade de infra + mapa ────────────
async def _audit_brain(user_id, action: str) -> None:
    """Registra no audit_log o acesso a dados internos do sistema (trilha)."""
    try:
        from app.db.base import AsyncSessionLocal
        from app.models.audit_log import AuditLog
        async with AsyncSessionLocal() as db:
            db.add(AuditLog(
                user_id=user_id, action=action, resource_type="SYSTEM",
                success=True, legal_basis="legitimate_interest",
            ))
            await db.commit()
    except Exception:
        pass  # auditoria best-effort nunca derruba a consulta


@router.get("/brain/infra")
async def brain_infra(current_user: User = Depends(require_role("SUPERADMIN"))):
    """Snapshot de infraestrutura em tempo real — Celery, Redis, Qdrant,
    Postgres pool, jobs (AgentRun/SyncRun). Exclusivo do SUPERADMIN."""
    from app.services.brain_infra import coletar_infra
    await _audit_brain(current_user.id, "BRAIN_INFRA_VIEW")
    return await coletar_infra()


@router.get("/brain/map")
async def brain_map(current_user: User = Depends(require_role("SUPERADMIN"))):
    """Mapa de módulos do sistema (nós + arestas) para o grafo do Cérebro."""
    from app.services.system_map import construir_mapa
    await _audit_brain(current_user.id, "BRAIN_MAP_VIEW")
    return construir_mapa()


@router.get("/brain/audit")
async def brain_audit(
    limit: int = Query(default=100, ge=1, le=300),
    offset: int = Query(default=0, ge=0),
    tenant_id: str | None = Query(default=None, description="Filtra por um tenant específico"),
    action: str | None = Query(default=None, description="Busca parcial (ilike) na ação"),
    success: bool | None = Query(default=None),
    current_user: User = Depends(require_role("SUPERADMIN")),
):
    """Trilha de auditoria recente — visão de PLATAFORMA (todas as tenants),
    exclusiva do SUPERADMIN. Lê o audit_log imutável. Best-effort: qualquer
    falha retorna lista vazia, nunca derruba o painel.

    Fase 162 — ganhou offset/tenant_id/action/success (antes só tinha limit,
    fixo nos últimos 300 eventos da PLATAFORMA INTEIRA, sem forma de buscar
    um tenant/período específico)."""
    await _audit_brain(current_user.id, "BRAIN_AUDIT_VIEW")
    try:
        from sqlalchemy import select, desc, func
        from app.db.base import AsyncSessionLocal
        from app.models.audit_log import AuditLog
        async with AsyncSessionLocal() as db:
            stmt = select(
                AuditLog.id, AuditLog.timestamp, AuditLog.action, AuditLog.user_id,
                AuditLog.agent_name, AuditLog.resource_type, AuditLog.resource_id,
                AuditLog.success, AuditLog.contains_pii, AuditLog.ip_address,
                AuditLog.legal_basis, AuditLog.tenant_id,
            ).order_by(desc(AuditLog.timestamp))

            if tenant_id:
                stmt = stmt.where(AuditLog.tenant_id == uuid.UUID(tenant_id))
            if action:
                stmt = stmt.where(AuditLog.action.ilike(f"%{action}%"))
            if success is not None:
                stmt = stmt.where(AuditLog.success == success)

            total = (await db.execute(
                select(func.count()).select_from(stmt.subquery())
            )).scalar_one()
            rows = (await db.execute(stmt.offset(offset).limit(limit))).all()
        return {"ok": True, "total": total, "limit": limit, "offset": offset, "eventos": [
            {
                "id": r.id,
                "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                "action": r.action,
                "user_id": str(r.user_id) if r.user_id else None,
                "agent_name": r.agent_name,
                "resource_type": r.resource_type,
                "resource_id": str(r.resource_id) if r.resource_id else None,
                "success": bool(r.success),
                "contains_pii": bool(r.contains_pii),
                "ip_address": r.ip_address,
                "legal_basis": r.legal_basis,
                "tenant_id": str(r.tenant_id) if r.tenant_id else None,
            }
            for r in rows
        ]}
    except Exception as exc:
        return {"ok": False, "total": 0, "limit": limit, "offset": offset, "eventos": [], "detail": str(exc)[:200]}


@router.get("/brain/logs")
async def brain_logs(
    limit: int = Query(default=200, ge=1, le=500),
    level: str | None = Query(default=None),
    current_user: User = Depends(require_role("SUPERADMIN")),
):
    """Logs recentes do processo (ring buffer em memória) — SUPERADMIN.
    `level` filtra por nível mínimo (debug|info|warning|error)."""
    await _audit_brain(current_user.id, "BRAIN_LOGS_VIEW")
    try:
        from app.core.log_buffer import snapshot
        return {"ok": True, "logs": snapshot(limit=limit, level=level)}
    except Exception as exc:
        return {"ok": False, "logs": [], "detail": str(exc)[:200]}


@router.get("/brain/metrics")
async def brain_metrics(current_user: User = Depends(require_role("SUPERADMIN"))):
    """Métricas por tenant — visão de PLATAFORMA (todas as tenants), SUPERADMIN.
    Best-effort: cada agregado é isolado; falha em um não derruba os demais."""
    await _audit_brain(current_user.id, "BRAIN_METRICS_VIEW")
    from app.services.brain_metrics import coletar_metricas
    return await coletar_metricas()


class EmbeddingsCompareRequest(BaseModel):
    queries: list[str]
    documentos: list[str]


@router.post("/brain/embeddings-compare")
async def brain_embeddings_compare(
    body: EmbeddingsCompareRequest,
    current_user: User = Depends(require_role("SUPERADMIN")),
):
    """Fase 4.2 — compara qualidade de busca entre OpenAI (motor real de
    produção, intocado) e BGE-M3 local (candidato). Indexa a amostra numa
    collection Qdrant descartável (`_test_bge_m3`, 1024-dim) — nunca toca
    nas 7 collections reais. Ferramenta de avaliação manual do SUPERADMIN
    antes de decidir avançar para a Fase 4.3 (reindexação real)."""
    from app.services.embeddings_compare import comparar_embeddings

    await _audit_brain(current_user.id, "BRAIN_EMBEDDINGS_COMPARE")
    return await comparar_embeddings(body.queries, body.documentos)


class ReindexTestRequest(BaseModel):
    collection: str
    limite: int = 200


@router.post("/brain/reindex-test-collection")
async def brain_reindex_test_collection(
    body: ReindexTestRequest,
    current_user: User = Depends(require_role("SUPERADMIN")),
):
    """Fase 4.3 Parte 1 — reindexa uma amostra REAL de uma das 7 collections
    de produção (só leitura nela) numa collection de teste BGE-M3 descartável
    (`_test_bge_m3_{collection}`), pra validar qualidade contra conteúdo de
    verdade antes de decidir migrar produção de vez."""
    from app.services.embeddings_compare import reindexar_amostra_teste

    await _audit_brain(current_user.id, "BRAIN_REINDEX_TEST_COLLECTION")
    return await reindexar_amostra_teste(body.collection, body.limite)


class SearchTestRequest(BaseModel):
    collection: str
    query: str
    limite: int = 5


@router.post("/brain/search-test-collection")
async def brain_search_test_collection(
    body: SearchTestRequest,
    current_user: User = Depends(require_role("SUPERADMIN")),
):
    """Busca na collection de teste BGE-M3 já reindexada — avaliação manual
    do SUPERADMIN da qualidade de busca contra conteúdo real (Fase 4.3)."""
    from app.services.embeddings_compare import buscar_teste

    await _audit_brain(current_user.id, "BRAIN_SEARCH_TEST_COLLECTION")
    return await buscar_teste(body.collection, body.query, body.limite)


@router.post("/brain/insights")
async def brain_insights(
    current_user: User = Depends(require_role("SUPERADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Cérebro inteligente (Fase 85) — analisa o próprio sistema (mapa + logs +
    métricas + infra) e devolve melhorias/erros/riscos/evolução propostos por IA.
    Guardrail de custo mensal; auditado. Best-effort: erro vira 200 com `ok: False`
    (a aba do Cérebro trata graciosamente, nunca um 500 genérico)."""
    from app.services.ai_budget import enforce_budget
    from app.services.brain_insights import gerar_insights

    await enforce_budget(db, current_user.id, current_user.tenant_id)
    await _audit_brain(current_user.id, "BRAIN_INSIGHTS_GENERATE")
    return await gerar_insights(db, current_user.id)


# ─── Assistente IA do Cérebro (SUPERADMIN — chat multi-turn + streaming SSE) ──
class BrainChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


@router.post("/brain/assistant")
async def brain_assistant(
    body: BrainChatRequest,
    current_user: User = Depends(require_role("SUPERADMIN")),
    db: AsyncSession = Depends(get_db),
):
    """Chat administrativo com streaming (SSE). Cada linha `data: {json}`:
    {"delta": "..."} para tokens, {"done": true, "conversation_id", "cost_usd"} no fim.
    RAG na doc do sistema + snapshot de infra no contexto. Guardrail de custo."""
    from fastapi.responses import StreamingResponse
    from fastapi import HTTPException
    from app.models.assistant import AssistantConversation, AssistantMessage
    from app.services.ai_budget import enforce_budget
    from app.services.brain_assistant import responder_stream

    pergunta = (body.message or "").strip()
    if not pergunta:
        raise HTTPException(status_code=422, detail="Mensagem vazia.")

    # Guardrail de custo mensal do usuário (best-effort; 429 se estourou).
    await enforce_budget(db, current_user.id, current_user.tenant_id)

    # Conversa (cria ou recupera) + histórico
    conv = None
    if body.conversation_id:
        # Defesa em profundidade: só carrega conversa do próprio usuário (evita
        # que um SUPERADMIN abra conversa de outro por UUID adivinhado).
        try:
            conv_uuid = uuid.UUID(body.conversation_id)
        except (ValueError, AttributeError):
            conv_uuid = None
        if conv_uuid is not None:
            conv = (await db.execute(
                select(AssistantConversation).where(
                    AssistantConversation.id == conv_uuid,
                    AssistantConversation.user_id == current_user.id,
                )
            )).scalar_one_or_none()
    if conv is None:
        conv = AssistantConversation(user_id=current_user.id, titulo=pergunta[:80])
        db.add(conv)
        await db.flush()

    hist_rows = (await db.execute(
        select(AssistantMessage.role, AssistantMessage.content)
        .where(AssistantMessage.conversation_id == conv.id)
        .order_by(AssistantMessage.created_at)
    )).all()
    historico = [{"role": r, "content": c} for r, c in hist_rows]
    historico.append({"role": "user", "content": pergunta})

    db.add(AssistantMessage(conversation_id=conv.id, role="user", content=pergunta))
    await db.commit()
    conv_id = str(conv.id)
    await _audit_brain(current_user.id, "BRAIN_ASSISTANT_CHAT")

    async def gerar():
        resposta = []
        custo = 0.0
        try:
            async for tipo, dado in responder_stream(db, historico, pergunta):
                if tipo == "delta":
                    resposta.append(dado)
                    yield f"data: {json.dumps({'delta': dado}, ensure_ascii=False)}\n\n"
                elif tipo == "done":
                    custo = dado.get("cost_usd", 0.0)
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)[:200]})}\n\n"
        # Persiste a resposta do assistente (sessão nova — o generator roda após o request)
        try:
            from app.db.base import AsyncSessionLocal
            async with AsyncSessionLocal() as db2:
                db2.add(AssistantMessage(
                    conversation_id=uuid.UUID(conv_id), role="assistant",
                    content="".join(resposta), cost_usd=custo,
                ))
                await db2.commit()
        except Exception:
            pass
        yield f"data: {json.dumps({'done': True, 'conversation_id': conv_id, 'cost_usd': custo})}\n\n"

    return StreamingResponse(gerar(), media_type="text/event-stream")


@router.post("/brain/assistant/reindex")
async def brain_assistant_reindex(current_user: User = Depends(require_role("SUPERADMIN"))):
    """Reindexa a documentação do sistema na coleção RAG documentacao_sistema."""
    from app.services.brain_assistant import reindexar_documentacao
    await _audit_brain(current_user.id, "BRAIN_ASSISTANT_REINDEX")
    return await reindexar_documentacao()
