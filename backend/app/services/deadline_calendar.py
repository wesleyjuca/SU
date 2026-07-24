"""Sincronização best-effort de prazos processuais com o Google Agenda (Fase 91).

Chamado logo após um `ProcessDeadline` ser persistido (triagem de intimação ou
criação manual). Nunca levanta exceção — mesmo padrão fail-soft de
`app/services/email.py::send_email` pro envio via Gmail: sem Google conectado
ou qualquer erro, é um no-op silencioso (o prazo já foi criado normalmente).
"""
from __future__ import annotations

import structlog

log = structlog.get_logger()


async def sincronizar_prazo_no_google(db, deadline, user_id) -> None:
    try:
        from app.services.google_workspace import get_valid_token, calendar_create_allday_event, GoogleNotConnected
        token = await get_valid_token(db, user_id)
        titulo = f"Prazo: {deadline.tipo or deadline.descricao[:40]}"
        await calendar_create_allday_event(token, titulo, deadline.descricao, deadline.data_prazo)
        log.info("prazo_sincronizado_google_agenda", deadline_id=str(deadline.id))
    except GoogleNotConnected:
        pass  # sem Google conectado — comportamento idêntico ao atual
    except Exception as exc:
        log.warning("prazo_sincronizacao_google_falhou", error=str(exc), deadline_id=str(deadline.id))
