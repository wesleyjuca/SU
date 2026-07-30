"""Captura de processos por OAB via Comunica/DJEN (fonte pública, sem credenciais).

Por que a Comunica e não o DataJud/PJe: o dataset público do DataJud não expõe
partes/advogados (busca por OAB volta vazia mesmo com API key), e PJe/ESAJ exigem
login do escritório. A Comunica (mesma fonte do monitor de intimações, Fase 50)
consulta por numeroOab+ufOab sem autenticação e devolve o número CNJ + tribunal.

Estratégia: varre as comunicações das OABs do escritório numa janela ampla,
extrai os processos distintos e cria os que ainda não existem — ligando cada um
ao advogado dono da OAB (responsável + equipe) quando ele tem login.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, timedelta

import structlog
from sqlalchemy import select

log = structlog.get_logger()


def _digits(v: str | None) -> str:
    return re.sub(r"\D", "", v or "")


async def _oabs_do_tenant(db, tenant_id: uuid.UUID) -> list[tuple[str, str, uuid.UUID | None]]:
    """OABs monitoradas do escritório: usuários ativos com OAB ∪ OABs do TenantConfig.

    Retorna tuplas (numero, uf, owner_user_id|None), dedup por (numero, uf).
    O owner é o User dono daquela OAB (para ligar o processo ao responsável).
    """
    from app.models.user import User
    from app.models.tenant import TenantConfig

    vistos: dict[tuple[str, str], uuid.UUID | None] = {}

    # OABs de usuários com login
    rows = (await db.execute(
        select(User.oab_number, User.oab_uf, User.id).where(
            User.tenant_id == tenant_id,
            User.oab_number.isnot(None),
            User.oab_uf.isnot(None),
            User.is_active == True,  # noqa: E712
        )
    )).all()
    for numero, uf, uid in rows:
        n, u = _digits(numero), (uf or "").strip().upper()
        if n and len(u) == 2 and (n, u) not in vistos:
            vistos[(n, u)] = uid

    # OABs cadastradas no escritório (sócios sem login)
    cfg = (await db.execute(
        select(TenantConfig).where(TenantConfig.tenant_id == tenant_id)
    )).scalar_one_or_none()
    for o in ((cfg.extra_data or {}).get("oabs_monitoradas") or []) if cfg else []:
        n, u = _digits(o.get("numero")), (o.get("uf") or "").strip().upper()
        if n and len(u) == 2 and (n, u) not in vistos:
            vistos[(n, u)] = None

    return [(n, u, owner) for (n, u), owner in vistos.items()]


_AREA_KEYWORDS: list[tuple[str, str]] = [
    ("TRABALH", "TRABALHISTA"),
    ("TRIBUT", "TRIBUTARIO"),
    ("PREVIDENC", "PREVIDENCIARIO"),
    ("CONSUM", "CONSUMIDOR"),
    ("PENAL", "PENAL"),
    ("CRIMIN", "PENAL"),
    ("FAMIL", "CIVIL"),
    ("CIVIL", "CIVIL"),
]


def _area_from_assuntos(assuntos: list[str]) -> str | None:
    """Mapeia (best-effort) os assuntos do CNJ para a área do direito do sistema."""
    texto = " ".join(assuntos).upper()
    for chave, area in _AREA_KEYWORDS:
        if chave in texto:
            return area
    return None


async def _enriquecer_via_datajud(db, procs: list[tuple]) -> None:
    """Preenche metadados (classe/assunto/órgão/data) e importa os andamentos de
    cada processo pelo número, via DataJud público + importador único (Fase 72).
    Best-effort: qualquer falha é ignorada."""
    if not procs:
        return
    from datetime import datetime
    from app.integrations.fontes.registry import obter_fonte
    from app.services.movements_import import importar_movimentos, parse_datajud_movimentos

    # Fase 74: detalhe via DataJudFonte (mesmo cliente CNJ, agora sob circuit
    # breaker + client fechado a cada chamada). A fonte é fail-soft (breaker).
    fonte_dj = obter_fonte("datajud")
    for proc, tribunal in procs:
        dados = await fonte_dj.detalhar(proc.numero_cnj, tribunal) if fonte_dj else None
        if not dados:
            continue
        if dados.get("classe") and not proc.tipo_acao:
            proc.tipo_acao = dados["classe"][:255]
        if dados.get("orgao_julgador") and not proc.vara:
            proc.vara = dados["orgao_julgador"][:255]
        area = _area_from_assuntos(dados.get("assuntos") or [])
        if area and not proc.area_direito:
            proc.area_direito = area
        if dados.get("data_ajuizamento") and not proc.distribuicao_data:
            try:
                proc.distribuicao_data = datetime.fromisoformat(
                    dados["data_ajuizamento"].replace("Z", "+00:00")
                ).date()
            except (ValueError, AttributeError):
                pass
        meta = dict(proc.metadata_json or {})
        meta["datajud"] = {"classe": dados.get("classe"), "grau": dados.get("grau"),
                           "assuntos": (dados.get("assuntos") or [])[:5]}
        proc.metadata_json = meta

        # Backfill inicial: sem notificação de equipe (processo recém-criado)
        await importar_movimentos(
            db, proc, parse_datajud_movimentos(dados, limite=100), notificar=False,
        )


async def _enriquecer_partes(db, tenant_id, procs: list[tuple]) -> int:
    """Se o escritório conectou uma fonte de partes credenciada (PDPJ/Escavador/
    Judit), preenche as PARTES dos processos recém-criados — dado que o DataJud
    público não expõe. No-op silencioso quando não há credencial. Retorna quantas
    partes foram gravadas."""
    if not procs:
        return 0
    from app.integrations.fontes.credenciadas import fonte_partes_credenciada
    from app.services.partes_import import importar_partes

    fonte = await fonte_partes_credenciada(db, tenant_id)
    if not fonte:
        return 0
    total = 0
    for proc, tribunal in procs:
        try:
            partes = await fonte.partes(proc.numero_cnj, tribunal)
        except Exception:
            partes = []
        if partes:
            res = await importar_partes(db, proc, partes)
            total += res.get("novas", 0)
    return total


async def capturar_por_oab(
    db,
    tenant_id: uuid.UUID,
    dias_retro: int = 365,
    triggered_by: uuid.UUID | None = None,
    apenas_oab: tuple[str, str] | None = None,
) -> dict:
    """Captura processos das OABs do escritório e cria os inexistentes.

    Idempotente: dedup contra LegalProcess por (tenant, numero_cnj).
    `apenas_oab=(numero, uf)` restringe a captura a uma única OAB (caminho do
    agente, Fase 72 — antes havia uma 2ª implementação paralela e mais pobre).
    Cada execução registra um SyncRun (histórico de sincronizações).
    """
    from app.models.process import LegalProcess, ProcessTeamMember
    from app.models.user import User
    from app.models.notification import Notification
    from app.integrations.fontes.registry import obter_fonte
    from app.services.movements_import import iniciar_sync, finalizar_sync
    from app.services.tribunais_ref import normalizar_codigo

    hoje = date.today()
    inicio = hoje - timedelta(days=max(1, dias_retro))

    if apenas_oab:
        n, u = _digits(apenas_oab[0]), (apenas_oab[1] or "").strip().upper()
        owner = None
        if n and len(u) == 2:
            candidatos = (await db.execute(
                select(User.id, User.oab_number).where(
                    User.tenant_id == tenant_id,
                    User.oab_uf == u,
                    User.oab_number.isnot(None),
                    User.is_active == True,  # noqa: E712
                )
            )).all()
            owner = next((uid for uid, num in candidatos if _digits(num) == n), None)
        oabs = [(n, u, owner)] if n and len(u) == 2 else []
    else:
        oabs = await _oabs_do_tenant(db, tenant_id)

    sync = await iniciar_sync(db, tenant_id, fonte="comunica+datajud", tipo="CAPTURA")
    if not oabs:
        resultado = {"oabs": 0, "comunicacoes_encontradas": 0, "processos_encontrados": 0,
                     "processos_criados": 0, "fonte_respondeu": False}
        await finalizar_sync(db, sync, "OK", resultado)
        await db.commit()
        return resultado

    # Diagnóstico da fonte (distingue "inalcançável" de "0 no período").
    # `stats["itens"]` acumula o total bruto de comunicações (a fonte preenche).
    stats: dict = {}
    fonte_comunica = obter_fonte("comunica")

    # numero_cnj (dígitos) -> dados do processo a criar
    achados: dict[str, dict] = {}
    for numero, uf, owner in oabs:
        descobertos = await fonte_comunica.descobrir_por_oab(
            numero, uf, inicio, hoje, max_paginas=20, stats=stats,
        ) if fonte_comunica else []
        for p in descobertos:
            cnj = p.numero_cnj
            if not cnj or cnj in achados:
                continue
            raw = p.raw
            numero_fmt = getattr(raw, "numero_cnj_fmt", None) or cnj
            achados[cnj] = {
                "numero_cnj_fmt": numero_fmt,
                "tribunal": normalizar_codigo(p.tribunal or f"TJ{uf}"),
                "uf": uf,
                "oab": f"{numero}/{uf}",
                "owner": owner,
            }
    total_comunicacoes = stats.get("itens", 0)

    if not achados:
        resultado = {"oabs": len(oabs), "comunicacoes_encontradas": total_comunicacoes,
                     "processos_encontrados": 0, "processos_criados": 0,
                     "fonte_respondeu": bool(stats.get("ok")),
                     "fonte_detalhe": stats.get("error")}
        await finalizar_sync(db, sync, "OK" if stats.get("ok") else "ERRO", resultado)
        await db.commit()
        return resultado

    # Já existentes no tenant (dedup por dígitos do CNJ)
    existentes = {
        _digits(n) for (n,) in (await db.execute(
            select(LegalProcess.numero_cnj).where(
                LegalProcess.tenant_id == tenant_id, LegalProcess.numero_cnj.isnot(None)
            )
        )).all() if n
    }

    criados = 0
    novos: list[tuple] = []  # (proc, tribunal) p/ enriquecer via DataJud
    for cnj, info in achados.items():
        if cnj in existentes:
            continue
        proc = LegalProcess(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            numero_cnj=info["numero_cnj_fmt"],
            tribunal=info["tribunal"],
            uf=info["uf"],
            situacao="ATIVO",
            oab_responsavel=info["oab"],
            responsavel_id=info["owner"],
            monitoring_active=True,
            fonte="OAB",
            metadata_json={"oab_origem": info["oab"]},
        )
        db.add(proc)
        await db.flush()
        # Liga ao advogado dono da OAB (aparece na Minha Área / modo confidencial)
        if info["owner"]:
            db.add(ProcessTeamMember(process_id=proc.id, user_id=info["owner"], papel="RESPONSAVEL"))
        novos.append((proc, info["tribunal"]))
        criados += 1

    # Enriquecimento via DataJud (metadados + andamentos por número). Bounded p/ não
    # estourar timeout; a busca por OAB NÃO existe no DataJud público (só por número).
    await _enriquecer_via_datajud(db, novos[:40])
    # Partes via fonte credenciada (PDPJ/Escavador/Judit; só com opt-in, senão no-op).
    await _enriquecer_partes(db, tenant_id, novos[:40])

    if triggered_by and criados:
        from app.services.notification import publish_notification_ws
        notif = Notification(
            user_id=triggered_by,
            tenant_id=tenant_id,
            tipo="NOVO_ANDAMENTO",
            titulo="Captura por OAB concluída",
            corpo=f"{criados} novo(s) processo(s) capturado(s) pelas OABs do escritório.",
            priority="NORMAL",
            link="/processos",
        )
        db.add(notif)
        await publish_notification_ws(notif)

    resultado = {
        "oabs": len(oabs),
        "comunicacoes_encontradas": total_comunicacoes,
        "processos_encontrados": len(achados),
        "processos_criados": criados,
        "fonte_respondeu": bool(stats.get("ok")),
        "fonte_detalhe": stats.get("error"),
    }
    await finalizar_sync(db, sync, "OK", resultado)
    await db.commit()
    log.info("oab_capture_done", tenant=str(tenant_id), oabs=len(oabs),
             comunicacoes=total_comunicacoes, encontrados=len(achados), criados=criados)
    return resultado
