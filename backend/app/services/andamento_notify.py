"""Notificação de novos andamentos processuais à equipe do processo.

Fecha o ciclo do monitoramento: quando o polling (batch ou manual "Atualizar
andamentos") traz movimentações novas, o responsável e a equipe são avisados —
espelha o padrão de notificação de intimações do dje_monitor.
"""
from __future__ import annotations

from sqlalchemy import select


async def notificar_equipe_andamento(db, process, qtd: int, com_prazo: bool = False) -> int:
    """Cria uma Notification de novo andamento para o responsável + equipe do
    processo (dedup por usuário). `com_prazo` destaca que há andamento que
    provavelmente inicia um prazo. Retorna quantos usuários foram notificados."""
    if qtd <= 0 or not getattr(process, "tenant_id", None):
        return 0

    from app.models.process import ProcessTeamMember
    from app.models.notification import Notification

    equipe_ids = {
        r[0] for r in (await db.execute(
            select(ProcessTeamMember.user_id).where(ProcessTeamMember.process_id == process.id)
        )).all()
    }
    if process.responsavel_id:
        equipe_ids.add(process.responsavel_id)
    if not equipe_ids:
        return 0

    rotulo = process.numero_cnj or "processo"
    corpo = (f"{qtd} novo(s) andamento(s) no processo — "
             + ("⚠ inclui possível prazo, verifique." if com_prazo
                else "confira e verifique possíveis prazos."))
    for uid in equipe_ids:
        db.add(Notification(
            user_id=uid,
            tenant_id=process.tenant_id,
            tipo="NOVO_ANDAMENTO",
            titulo=f"Novo andamento: {rotulo}",
            corpo=corpo,
            priority="HIGH",
            link=f"/processos/{process.id}",
        ))
    return len(equipe_ids)
