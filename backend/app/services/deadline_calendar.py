"""Sincronização best-effort de prazos processuais com o Google Agenda (Fase 91).

Chamado logo após um `ProcessDeadline` ser persistido (triagem de intimação ou
criação manual). Nunca levanta exceção — mesmo padrão fail-soft de
`app/services/email.py::send_email` pro envio via Gmail: sem Google conectado
ou qualquer erro, é um no-op silencioso (o prazo já foi criado normalmente).

Fase 139: a conta Google passou de "por usuário" pra "do escritório"
(tenant) — o evento agora vai pra Agenda compartilhada do escritório, não
mais pro calendário pessoal de quem criou o prazo."""
from __future__ import annotations

import structlog

log = structlog.get_logger()


async def sincronizar_prazo_no_google(db, deadline, tenant_id) -> None:
    try:
        from app.services import integration_hub
        from app.services.google_workspace import get_valid_token, calendar_create_allday_event, GoogleNotConnected
        token = await get_valid_token(db, tenant_id)
        titulo = f"Prazo: {deadline.tipo or deadline.descricao[:40]}"
        await calendar_create_allday_event(token, titulo, deadline.descricao, deadline.data_prazo)
        log.info("prazo_sincronizado_google_agenda", deadline_id=str(deadline.id))
        await integration_hub.registrar_uso(db, tenant_id, "google_workspace", sucesso=True)
    except GoogleNotConnected:
        pass  # sem Google conectado — comportamento idêntico ao atual
    except Exception as exc:
        log.warning("prazo_sincronizacao_google_falhou", error=str(exc), deadline_id=str(deadline.id))
        from app.services import integration_hub
        await integration_hub.registrar_uso(db, tenant_id, "google_workspace", sucesso=False, detalhe=str(exc)[:400])
