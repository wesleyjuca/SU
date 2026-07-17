"""Varredura do DJe (Comunica/DJEN) → intimações + andamentos + notificações.

TRIAGEM/HITL: cada intimação capturada é persistida (status NOVA), casada com o
processo por número CNJ (tenant-scoped) e vira ProcessMovement(INTIMACAO) +
notificação urgente ao responsável. O PRAZO **não** é criado aqui — só após
triagem humana (endpoint /publicacoes/{id}/triagem).
"""
from __future__ import annotations

import re
import uuid
from datetime import date, timedelta, datetime, timezone

import structlog
from sqlalchemy import select

log = structlog.get_logger()


def _digits(v: str | None) -> str:
    return re.sub(r"\D", "", v or "")


async def scan_publicacoes(db, tenant_id: uuid.UUID | None = None, dias_retro: int = 1) -> dict:
    """Varre a Comunica para as OABs monitoradas e persiste intimações novas.

    Se `tenant_id` for dado, restringe àquele escritório (varredura manual);
    senão varre todos (job diário). Idempotente por hash.
    """
    from app.models.user import User
    from app.models.process import LegalProcess, ProcessMovement
    from app.models.notification import Notification
    from app.models.intimacao import Intimacao
    from app.integrations.dje.comunica import buscar_comunicacoes

    hoje = date.today()
    data_inicio = hoje - timedelta(days=max(0, dias_retro))

    # OABs monitoradas (advogados ativos com OAB), por tenant.
    q = select(User.oab_number, User.oab_uf, User.tenant_id).where(
        User.oab_number.isnot(None), User.oab_uf.isnot(None), User.is_active == True  # noqa: E712
    )
    if tenant_id:
        q = q.where(User.tenant_id == tenant_id)
    oabs = [(n, u, t) for (n, u, t) in (await db.execute(q)).all() if n and u and t]

    # Cache do mapa CNJ→processo por tenant (evita recarregar por OAB).
    proc_cache: dict[uuid.UUID, dict[str, tuple]] = {}

    async def _proc_map(t_id: uuid.UUID) -> dict[str, tuple]:
        if t_id not in proc_cache:
            rows = (await db.execute(
                select(LegalProcess.id, LegalProcess.numero_cnj, LegalProcess.responsavel_id)
                .where(LegalProcess.tenant_id == t_id, LegalProcess.numero_cnj.isnot(None))
            )).all()
            proc_cache[t_id] = {_digits(cnj): (pid, resp) for (pid, cnj, resp) in rows if _digits(cnj)}
        return proc_cache[t_id]

    novas = 0
    casadas = 0
    for oab_numero, oab_uf, t_id in oabs:
        comunicacoes = await buscar_comunicacoes(oab_numero, oab_uf, data_inicio, hoje)
        pmap = await _proc_map(t_id) if comunicacoes else {}

        for c in comunicacoes:
            h = c.hash_dedupe()
            # dedupe por hash + tenant
            existe = (await db.execute(
                select(Intimacao.id).where(Intimacao.hash == h, Intimacao.tenant_id == t_id)
            )).scalar_one_or_none()
            if existe:
                continue

            dt_disp = None
            if c.data_disponibilizacao:
                try:
                    dt_disp = date.fromisoformat(c.data_disponibilizacao[:10])
                except Exception:
                    dt_disp = None

            match = pmap.get(c.numero_cnj or "")
            process_id, responsavel_id = (match if match else (None, None))

            intim = Intimacao(
                tenant_id=t_id,
                process_id=process_id,
                oab=f"{_digits(oab_numero)}/{oab_uf.upper()}",
                numero_cnj=c.numero_cnj,
                numero_cnj_fmt=c.numero_cnj_fmt,
                texto=c.texto,
                data_disponibilizacao=dt_disp,
                tribunal=c.tribunal,
                tipo_comunicacao=c.tipo_comunicacao,
                orgao=c.orgao,
                link=c.link,
                hash=h,
                status="NOVA",
            )
            db.add(intim)
            novas += 1

            # Casou com um processo: vira andamento + notificação ao responsável.
            if process_id:
                casadas += 1
                dm = datetime.combine(dt_disp or hoje, datetime.min.time()).replace(tzinfo=timezone.utc)
                # dedupe do movimento por (processo, data, descrição)
                desc = (c.texto or c.tipo_comunicacao or "Intimação")[:2000]
                dup = (await db.execute(
                    select(ProcessMovement.id).where(
                        ProcessMovement.process_id == process_id,
                        ProcessMovement.data_movimento == dm,
                        ProcessMovement.descricao == desc,
                    )
                )).scalar_one_or_none()
                if not dup:
                    db.add(ProcessMovement(
                        process_id=process_id,
                        data_movimento=dm,
                        descricao=desc,
                        tipo="INTIMACAO",
                        documento_url=c.link,
                    ))
                # Notifica o responsável E toda a equipe do processo (dedup).
                from app.models.process import ProcessTeamMember
                equipe_ids = {
                    r[0] for r in (await db.execute(
                        select(ProcessTeamMember.user_id).where(ProcessTeamMember.process_id == process_id)
                    )).all()
                }
                if responsavel_id:
                    equipe_ids.add(responsavel_id)
                for uid in equipe_ids:
                    db.add(Notification(
                        user_id=uid,
                        tenant_id=t_id,
                        tipo="NOVO_ANDAMENTO",
                        titulo=f"Nova intimação: {c.numero_cnj_fmt or 'processo'}",
                        corpo=(c.tipo_comunicacao or "Intimação") + (f" · {c.tribunal}" if c.tribunal else "") + " — revise e defina o prazo.",
                        priority="HIGH",
                        link="/publicacoes",
                    ))

    await db.commit()
    log.info("dje_scan_done", oabs=len(oabs), novas=novas, casadas=casadas, tenant=str(tenant_id) if tenant_id else "all")
    return {"oabs_monitoradas": len(oabs), "intimacoes_novas": novas, "casadas_com_processo": casadas}
