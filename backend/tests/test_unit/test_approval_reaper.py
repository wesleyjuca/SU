"""Fase 191 — reaper de `Approval` PENDENTE vencida. NUNCA aprova/rejeita
sozinho (violaria o invariante HITL do CLAUDE.md) — só escala, notificando
todos os gestores do escritório (ADMIN/SOCIO/SUPERADMIN), e marca
`escalated_at` pra não repetir a cada rodada."""
import uuid

import pytest


class _FakeApproval:
    def __init__(self, tenant_id, titulo="Aprovar petição inicial"):
        self.id = uuid.uuid4()
        self.tenant_id = tenant_id
        self.titulo = titulo
        self.tipo = "PETITION_FILING"
        self.prioridade = "NORMAL"
        self.status = "PENDENTE"
        self.escalated_at = None


class _FakeScalarsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, queue):
        self._queue = list(queue)
        self.added = []
        self.commits = 0

    async def execute(self, query):
        return self._queue.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


def _patch_notify(monkeypatch):
    import app.services.notification as notif_mod
    import app.api.v1.ws as ws_mod

    calls = {"ws": []}

    async def _fake_publish_notification_ws(notif):
        pass

    async def _fake_publish_event(user_id, event, data):
        calls["ws"].append((user_id, event, data))

    monkeypatch.setattr(notif_mod, "publish_notification_ws", _fake_publish_notification_ws)
    monkeypatch.setattr(ws_mod, "publish_event", _fake_publish_event)
    return calls


@pytest.mark.asyncio
async def test_sem_aprovacoes_vencidas_nao_escala_nem_commita(monkeypatch):
    from app.workers.tasks.approval_reaper import executar_reaper_approvals

    _patch_notify(monkeypatch)
    db = _FakeDB([_FakeScalarsResult([])])

    resultado = await executar_reaper_approvals(db)

    assert resultado["escaladas"] == 0
    assert db.commits == 0


@pytest.mark.asyncio
async def test_aprovacao_vencida_notifica_todos_os_gestores_e_marca_escalada(monkeypatch):
    from app.workers.tasks.approval_reaper import executar_reaper_approvals

    calls = _patch_notify(monkeypatch)
    tenant = uuid.uuid4()
    approval = _FakeApproval(tenant)
    gestor_a, gestor_b = uuid.uuid4(), uuid.uuid4()

    db = _FakeDB([
        _FakeScalarsResult([approval]),        # aprovações vencidas
        _FakeScalarsResult([gestor_a, gestor_b]),  # gestores do tenant
    ])

    resultado = await executar_reaper_approvals(db)

    assert resultado["escaladas"] == 1
    assert approval.escalated_at is not None
    assert db.commits == 1
    assert len(db.added) == 2  # 1 Notification por gestor
    assert len(calls["ws"]) == 2
    assert all(evt == "NEW_APPROVAL_PENDING" for _, evt, _ in calls["ws"])
    assert all(data["escalada"] is True for _, _, data in calls["ws"])


@pytest.mark.asyncio
async def test_multiplas_aprovacoes_vencidas_de_tenants_diferentes(monkeypatch):
    from app.workers.tasks.approval_reaper import executar_reaper_approvals

    _patch_notify(monkeypatch)
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    approval_a = _FakeApproval(tenant_a)
    approval_b = _FakeApproval(tenant_b)

    db = _FakeDB([
        _FakeScalarsResult([approval_a, approval_b]),
        _FakeScalarsResult([uuid.uuid4()]),  # gestores do tenant_a
        _FakeScalarsResult([uuid.uuid4()]),  # gestores do tenant_b
    ])

    resultado = await executar_reaper_approvals(db)

    assert resultado["escaladas"] == 2
    assert approval_a.escalated_at is not None
    assert approval_b.escalated_at is not None
