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
    """Preenche metadados (classe/assunto/órgão/data) e cria os andamentos de cada
    processo pelo número, via DataJud público. Best-effort: qualquer falha é ignorada."""
    if not procs:
        return
    from datetime import datetime, timezone
    from app.models.process import ProcessMovement
    from app.integrations.tribunais.cnj import CNJDataJudClient

    client = CNJDataJudClient()
    try:
        for proc, tribunal in procs:
            try:
                dados = await client.fetch_processo(proc.numero_cnj, tribunal)
            except Exception:
                dados = None
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

            # Andamentos (dedup por processo+data+descrição)
            vistos: set[tuple] = set()
            for mov in (dados.get("movimentos") or [])[:100]:
                nome = (mov.get("nome") or "").strip()
                if not nome:
                    continue
                dh = mov.get("dataHora", "")
                try:
                    dt = datetime.fromisoformat(dh.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    dt = datetime.now(timezone.utc)
                chave = (dt.date().isoformat(), nome[:120])
                if chave in vistos:
                    continue
                vistos.add(chave)
                db.add(ProcessMovement(
                    process_id=proc.id,
                    data_movimento=dt,
                    descricao=nome[:2000],
                    tipo="ANDAMENTO",
                ))
            proc.ultimo_andamento_at = datetime.now(timezone.utc)
    finally:
        await client.close()


async def capturar_por_oab(
    db,
    tenant_id: uuid.UUID,
    dias_retro: int = 365,
    triggered_by: uuid.UUID | None = None,
) -> dict:
    """Captura processos das OABs do escritório e cria os inexistentes.

    Idempotente: dedup contra LegalProcess por (tenant, numero_cnj).
    """
    from app.models.process import LegalProcess, ProcessTeamMember
    from app.models.notification import Notification
    from app.integrations.dje.comunica import buscar_comunicacoes

    hoje = date.today()
    inicio = hoje - timedelta(days=max(1, dias_retro))

    oabs = await _oabs_do_tenant(db, tenant_id)
    if not oabs:
        return {"oabs": 0, "comunicacoes_encontradas": 0, "processos_encontrados": 0,
                "processos_criados": 0, "fonte_respondeu": False}

    # Diagnóstico da fonte (distingue "inalcançável" de "0 no período").
    stats: dict = {}
    total_comunicacoes = 0

    # numero_cnj (dígitos) -> dados do processo a criar
    achados: dict[str, dict] = {}
    for numero, uf, owner in oabs:
        comunicacoes = await buscar_comunicacoes(numero, uf, inicio, hoje, max_paginas=20, stats=stats)
        total_comunicacoes += len(comunicacoes)
        for c in comunicacoes:
            cnj = c.numero_cnj
            if not cnj or cnj in achados:
                continue
            achados[cnj] = {
                "numero_cnj_fmt": c.numero_cnj_fmt or cnj,
                "tribunal": (c.tribunal or f"TJ{uf}").upper(),
                "uf": uf,
                "oab": f"{numero}/{uf}",
                "owner": owner,
            }

    if not achados:
        return {"oabs": len(oabs), "comunicacoes_encontradas": total_comunicacoes,
                "processos_encontrados": 0, "processos_criados": 0,
                "fonte_respondeu": bool(stats.get("ok"))}

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
            metadata_json={"fonte_captura": "OAB", "oab_origem": info["oab"]},
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

    if triggered_by and criados:
        db.add(Notification(
            user_id=triggered_by,
            tenant_id=tenant_id,
            tipo="NOVO_ANDAMENTO",
            titulo="Captura por OAB concluída",
            corpo=f"{criados} novo(s) processo(s) capturado(s) pelas OABs do escritório.",
            priority="NORMAL",
            link="/processos",
        ))

    await db.commit()
    log.info("oab_capture_done", tenant=str(tenant_id), oabs=len(oabs),
             comunicacoes=total_comunicacoes, encontrados=len(achados), criados=criados)
    return {
        "oabs": len(oabs),
        "comunicacoes_encontradas": total_comunicacoes,
        "processos_encontrados": len(achados),
        "processos_criados": criados,
        "fonte_respondeu": bool(stats.get("ok")),
    }
