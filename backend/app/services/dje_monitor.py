"""Varredura do DJe (Comunica/DJEN) → intimações + andamentos + notificações.

TRIAGEM/HITL: cada intimação capturada é persistida (status NOVA), casada com o
processo por número CNJ (tenant-scoped) e vira ProcessMovement(INTIMACAO) +
notificação urgente ao responsável. O PRAZO **não** é criado aqui — só após
triagem humana (endpoint /publicacoes/{id}/triagem).
"""
from __future__ import annotations

import asyncio
import re
import uuid
from datetime import date, timedelta, datetime, timezone

import structlog
from sqlalchemy import select

from app.integrations.fontes.circuit_breaker import CircuitBreaker

log = structlog.get_logger()

# Fase 142 — pequeno intervalo entre requisições sequenciais à Comunica/DJEN
# dentro de uma mesma varredura, pra reduzir o risco de a rajada (dezenas de
# OABs, zero pausa) parecer tráfego de bot pro anti-bot do portal.
_INTERVALO_ENTRE_OABS_S = 0.5


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

    # União com as OABs cadastradas no escritório (sócios sem login também
    # capturam) — dedup por (número, UF, tenant).
    from app.models.tenant import TenantConfig
    cfg_q = select(TenantConfig.tenant_id, TenantConfig.extra_data)
    if tenant_id:
        cfg_q = cfg_q.where(TenantConfig.tenant_id == tenant_id)
    vistos = {(_digits(n), (u or "").upper(), t) for (n, u, t) in oabs}
    for t_id, extra in (await db.execute(cfg_q)).all():
        for o in ((extra or {}).get("oabs_monitoradas") or []):
            numero, uf = _digits(o.get("numero")), (o.get("uf") or "").strip().upper()
            if numero and len(uf) == 2 and (numero, uf, t_id) not in vistos:
                vistos.add((numero, uf, t_id))
                oabs.append((numero, uf, t_id))

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

    from app.services.movements_import import iniciar_sync, finalizar_sync
    sync = await iniciar_sync(db, tenant_id, fonte="comunica", tipo="SCAN")

    # Fase 142 — circuit breaker local a esta varredura: se a Comunica
    # começar a rejeitar (403/500/timeout) nas primeiras OABs, para de
    # martelar pras OABs restantes em vez de repetir o mesmo padrão
    # rejeitado até o fim da lista. Escopo é só esta chamada (não
    # compartilhado com o fluxo sob demanda via ComunicaFonte) — simples e
    # já resolve o caso mais comum (rajada dentro do próprio job diário).
    breaker = CircuitBreaker(name="comunica_scan_diario")
    puladas_circuito = 0

    novas = 0
    casadas = 0
    for oab_numero, oab_uf, t_id in oabs:
        if not breaker.allow():
            puladas_circuito += 1
            continue

        st: dict = {}
        comunicacoes = await buscar_comunicacoes(oab_numero, oab_uf, data_inicio, hoje, stats=st)
        if st.get("requests") and not st.get("ok"):
            breaker.record_failure()
        else:
            breaker.record_success()
        await asyncio.sleep(_INTERVALO_ENTRE_OABS_S)

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
                # dedupe CANÔNICO do movimento (Fase 72 — mesmo hash do importador
                # único; um andamento importado pelo polling não duplica como intimação)
                from app.services.movements_import import dedup_hash as _dh
                desc = (c.texto or c.tipo_comunicacao or "Intimação")[:2000]
                h_mov = _dh(dm, desc)
                dup = (await db.execute(
                    select(ProcessMovement.id).where(
                        ProcessMovement.process_id == process_id,
                        ProcessMovement.dedup_hash == h_mov,
                    )
                )).scalar_one_or_none()
                if not dup:
                    db.add(ProcessMovement(
                        process_id=process_id,
                        data_movimento=dm,
                        descricao=desc,
                        tipo="INTIMACAO",
                        documento_url=c.link,
                        dedup_hash=h_mov,
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
                from app.services.notification import publish_notification_ws
                for uid in equipe_ids:
                    notif = Notification(
                        user_id=uid,
                        tenant_id=t_id,
                        tipo="NOVO_ANDAMENTO",
                        titulo=f"Nova intimação: {c.numero_cnj_fmt or 'processo'}",
                        corpo=(c.tipo_comunicacao or "Intimação") + (f" · {c.tribunal}" if c.tribunal else "") + " — revise e defina o prazo.",
                        priority="HIGH",
                        link="/publicacoes",
                    )
                    db.add(notif)
                    await publish_notification_ws(notif)
                # WhatsApp best-effort para quem tem telefone cadastrado
                if equipe_ids:
                    from app.models.user import User as _User
                    from app.services.whatsapp import enviar_whatsapp
                    tels = (await db.execute(
                        select(_User.telefone).where(
                            _User.id.in_(equipe_ids), _User.telefone.isnot(None)
                        )
                    )).scalars().all()
                    for tel in tels:
                        await enviar_whatsapp(
                            db, t_id, tel,
                            f"Nova intimação: {c.numero_cnj_fmt or 'processo'} "
                            f"({c.tipo_comunicacao or 'Intimação'}) — revise e defina o prazo em Publicações.",
                        )

    resultado = {
        "oabs_monitoradas": len(oabs),
        "intimacoes_novas": novas,
        "casadas_com_processo": casadas,
        # Fase 142 — observabilidade do circuit breaker (ver painel Cérebro
        # → Infraestrutura): se comunica_bloqueada=True, a Comunica rejeitou
        # requisições nesta varredura e o job parou de insistir pras OABs
        # restantes em vez de martelar o portal até o fim da lista.
        "comunica_bloqueada": breaker.state != "closed",
        "oabs_puladas_circuito": puladas_circuito,
    }
    await finalizar_sync(db, sync, "OK", resultado)
    await db.commit()
    log.info(
        "dje_scan_done", oabs=len(oabs), novas=novas, casadas=casadas,
        puladas_circuito=puladas_circuito, tenant=str(tenant_id) if tenant_id else "all",
    )
    return resultado
