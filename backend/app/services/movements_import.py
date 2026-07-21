"""Importador ÚNICO de movimentações processuais (Fase 72 — consolidação).

Antes havia 4 implementações concorrentes (agente de polling, endpoint
atualizar-andamentos, enriquecimento da captura por OAB e dje_monitor), cada
uma com critério de dedup diferente (prefixo de 120 chars vs texto integral)
— o mesmo movimento podia ser gravado duas vezes por caminhos distintos.

Este módulo define o critério CANÔNICO de deduplicação (dedup_hash =
sha256 da data + descrição normalizada) e é o único lugar que cria
ProcessMovement. O índice único parcial (process_id, dedup_hash) no banco
garante a idempotência mesmo sob corrida.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import structlog
from sqlalchemy import select

log = structlog.get_logger()


def dedup_hash(data_movimento: datetime | None, descricao: str) -> str:
    """Hash canônico de um movimento: dia (ISO) + descrição normalizada.

    Normalização: colapsa espaços e baixa a caixa — assim o mesmo movimento
    vindo de fontes com truncamentos/espaçamentos diferentes deduplica."""
    dia = data_movimento.date().isoformat() if data_movimento else ""
    texto = re.sub(r"\s+", " ", (descricao or "")).strip().lower()
    return hashlib.sha256(f"{dia}|{texto}".encode()).hexdigest()


@dataclass
class MovimentoEntrada:
    """Movimento normalizado, independente da fonte."""
    data: datetime
    descricao: str
    tipo: str = "ANDAMENTO"
    documento_url: str | None = None
    raw: str | None = None
    ai_summary: str | None = None


def parse_datajud_movimentos(dados: dict, limite: int = 200) -> list[MovimentoEntrada]:
    """Converte a resposta do DataJud (fetch_processo/fetch_movements-dict) em
    MovimentoEntrada — parsing que estava duplicado em 3 lugares."""
    out: list[MovimentoEntrada] = []
    for mov in (dados.get("movimentos") or [])[:limite]:
        nome = (mov.get("nome") or "").strip()
        if not nome:
            continue
        dh = mov.get("dataHora", "")
        try:
            dt = datetime.fromisoformat(dh.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            dt = datetime.now(timezone.utc)
        out.append(MovimentoEntrada(data=dt, descricao=nome[:2000]))
    return out


async def _hashes_existentes(db, process_id: uuid.UUID) -> set[str]:
    """Hashes dos movimentos já gravados. Linhas legadas (dedup_hash NULL)
    entram pelo hash recalculado de (data, descrição)."""
    from app.models.process import ProcessMovement

    rows = (await db.execute(
        select(ProcessMovement.dedup_hash, ProcessMovement.data_movimento, ProcessMovement.descricao)
        .where(ProcessMovement.process_id == process_id)
    )).all()
    vistos: set[str] = set()
    for h, dm, desc in rows:
        vistos.add(h or dedup_hash(dm, desc or ""))
    return vistos


async def importar_movimentos(
    db,
    process,
    movimentos: list[MovimentoEntrada],
    *,
    notificar: bool = True,
) -> dict:
    """Grava os movimentos NOVOS de um processo (dedup canônico) e, opcional-
    mente, notifica a equipe. NÃO faz commit — transação é do chamador.

    Retorna {"novos": int, "com_prazo": bool}."""
    from app.models.process import ProcessMovement
    from app.utils.prazo import movimento_sugere_prazo

    if not movimentos:
        return {"novos": 0, "com_prazo": False}

    vistos = await _hashes_existentes(db, process.id)
    novos = 0
    com_prazo = False
    agora = datetime.now(timezone.utc)

    for m in movimentos:
        h = dedup_hash(m.data, m.descricao)
        if h in vistos:
            continue
        vistos.add(h)
        sugere = movimento_sugere_prazo(f"{m.descricao} {m.ai_summary or ''}")
        com_prazo = com_prazo or sugere
        db.add(ProcessMovement(
            process_id=process.id,
            data_movimento=m.data,
            descricao=m.descricao,
            tipo=m.tipo,
            documento_url=m.documento_url,
            raw_html=m.raw,
            ai_summary=m.ai_summary,
            possivel_prazo=sugere,
            dedup_hash=h,
        ))
        novos += 1

    process.last_polled_at = agora
    if novos:
        process.ultimo_andamento_at = agora
        if notificar:
            from app.services.andamento_notify import notificar_equipe_andamento
            await notificar_equipe_andamento(db, process, novos, com_prazo=com_prazo)

    return {"novos": novos, "com_prazo": com_prazo}


# ─── Histórico de sincronizações (SyncRun) ────────────────────────────────────
async def iniciar_sync(db, tenant_id, fonte: str, tipo: str) -> "object":
    """Abre um registro de sincronização (RUNNING). Best-effort: nunca quebra o fluxo."""
    try:
        from app.models.sync_run import SyncRun
        run = SyncRun(tenant_id=tenant_id, fonte=fonte, tipo=tipo, status="RUNNING")
        db.add(run)
        await db.flush()
        return run
    except Exception as exc:
        log.warning("sync_run_start_failed", error=str(exc))
        return None


async def finalizar_sync(db, run, status: str, stats: dict | None = None) -> None:
    if run is None:
        return
    try:
        run.status = status
        run.finished_at = datetime.now(timezone.utc)
        run.stats = stats or {}
        await db.flush()
    except Exception as exc:
        log.warning("sync_run_finish_failed", error=str(exc))
