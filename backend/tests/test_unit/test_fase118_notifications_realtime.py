"""Fase 118 — NOTIFICATION/NEW_APPROVAL_PENDING publicados via WebSocket em
tempo real (antes só existiam no banco, o sino/badge dependiam só do polling
de 60s do frontend). `app.api.v1.ws` importa `app.core.security` -> `jose` ->
`cryptography`, que neste sandbox derruba o interpretador (bug conhecido
`cryptography`/PyO3, o mesmo que bloqueia `pytest` direto aqui) — stuba
`app.api.v1.ws` inteiro em `sys.modules` antes do import, testando a lógica
real de publicação sem tocar o módulo real (que segue intacto/funcional em
produção — só este sandbox tem o bug de import).
"""
import asyncio
import sys
import types
import uuid


def setup_module(module):
    if "app.api.v1.ws" in sys.modules and getattr(sys.modules["app.api.v1.ws"], "_fase118_fake", False):
        return
    fake_ws = types.ModuleType("app.api.v1.ws")
    fake_ws._fase118_fake = True
    fake_ws.calls = []

    async def fake_publish_event(user_id, event_type, data):
        fake_ws.calls.append((user_id, event_type, data))

    fake_ws.publish_event = fake_publish_event
    sys.modules["app.api.v1.ws"] = fake_ws


def _fake_ws_calls():
    return sys.modules["app.api.v1.ws"].calls


class _FakeNotification:
    def __init__(self, user_id, id=None, tipo="SISTEMA", titulo="Título", corpo=None,
                 priority="NORMAL", link=None):
        self.user_id = user_id
        self.id = id
        self.tipo = tipo
        self.titulo = titulo
        self.corpo = corpo
        self.priority = priority
        self.link = link


def test_publish_notification_ws_envia_evento_para_o_user_certo():
    from app.services import notification_service as ns
    _fake_ws_calls().clear()

    uid = uuid.uuid4()
    notif = _FakeNotification(user_id=uid, id=uuid.uuid4(), tipo="PRAZO_VENCENDO",
                               titulo="Prazo em 3 dias", corpo="detalhe", priority="HIGH", link="/processos/1")
    asyncio.run(ns.publish_notification_ws(notif))

    assert len(_fake_ws_calls()) == 1
    user_id, event_type, data = _fake_ws_calls()[0]
    assert user_id == str(uid)
    assert event_type == "NOTIFICATION"
    assert data["tipo"] == "PRAZO_VENCENDO"
    assert data["titulo"] == "Prazo em 3 dias"
    assert data["priority"] == "HIGH"
    assert data["link"] == "/processos/1"
    assert data["id"] == str(notif.id)


def test_publish_notification_ws_sem_id_flushed_manda_none():
    """Chamado logo após db.add(), antes do flush — id ainda não foi atribuído
    pelo Postgres. O evento sai com id=None; o frontend cai no fallback local."""
    from app.services import notification_service as ns
    _fake_ws_calls().clear()

    notif = _FakeNotification(user_id=uuid.uuid4(), id=None)
    asyncio.run(ns.publish_notification_ws(notif))

    assert _fake_ws_calls()[0][2]["id"] is None


def test_create_notification_publica_apos_persistir():
    from app.services import notification_service as ns
    _fake_ws_calls().clear()

    class _FakeDB:
        async def commit(self):
            pass

        async def refresh(self, obj):
            obj.id = uuid.uuid4()

        def add(self, obj):
            pass

    uid = uuid.uuid4()
    result = asyncio.run(ns.create_notification(_FakeDB(), uid, "Novo prazo", tipo="PRAZO_VENCENDO"))

    assert len(_fake_ws_calls()) == 1
    sent_user_id, event_type, data = _fake_ws_calls()[0]
    assert sent_user_id == str(uid)
    assert event_type == "NOTIFICATION"
    assert data["id"] == str(result.id)


def test_create_batch_publica_uma_vez_por_usuario():
    from app.services import notification_service as ns
    _fake_ws_calls().clear()

    class _FakeDB:
        async def commit(self):
            pass

        def add(self, obj):
            pass

    uids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    count = asyncio.run(ns.create_batch(_FakeDB(), uids, "Aviso geral"))

    assert count == 3
    assert len(_fake_ws_calls()) == 3
    sent_users = {c[0] for c in _fake_ws_calls()}
    assert sent_users == {str(u) for u in uids}


def test_notify_tenant_of_approval_publica_para_cada_usuario_da_query():
    """A exclusão de CLIENT/inativos é feita pelo próprio SELECT (where role !=
    CLIENT and is_active) — aqui confirmamos que _notify_tenant_of_approval
    publica exatamente para quem a query devolver, um evento por usuário,
    com o approval_id/tipo/titulo/prioridade corretos."""
    from app.services import approval_service as aps
    _fake_ws_calls().clear()

    staff_ids = [uuid.uuid4(), uuid.uuid4()]

    class _FakeScalarsResult:
        def all(self):
            return staff_ids

    class _FakeResult:
        def scalars(self):
            return _FakeScalarsResult()

    class _FakeDB:
        async def execute(self, query):
            return _FakeResult()

    class _FakeApproval:
        id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        tipo = "PETITION_FILING"
        titulo = "Aprovar petição X"
        prioridade = "ALTA"

    approval = _FakeApproval()
    asyncio.run(aps._notify_tenant_of_approval(_FakeDB(), approval))

    assert len(_fake_ws_calls()) == 2
    sent_users = {c[0] for c in _fake_ws_calls()}
    assert sent_users == {str(u) for u in staff_ids}
    for _, event_type, data in _fake_ws_calls():
        assert event_type == "NEW_APPROVAL_PENDING"
        assert data["approval_id"] == str(approval.id)
        assert data["tipo"] == "PETITION_FILING"
        assert data["titulo"] == "Aprovar petição X"
        assert data["prioridade"] == "ALTA"


def test_notify_tenant_of_approval_sem_staff_nao_publica_nada():
    from app.services import approval_service as aps
    _fake_ws_calls().clear()

    class _FakeScalarsResult:
        def all(self):
            return []

    class _FakeResult:
        def scalars(self):
            return _FakeScalarsResult()

    class _FakeDB:
        async def execute(self, query):
            return _FakeResult()

    class _FakeApproval:
        id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        tipo = "PETITION_FILING"
        titulo = "x"
        prioridade = "NORMAL"

    asyncio.run(aps._notify_tenant_of_approval(_FakeDB(), _FakeApproval()))
    assert _fake_ws_calls() == []


def test_create_approval_from_state_chama_notify_tenant():
    """Guarda de regressão: create_approval_from_state (chamado após todo run de
    agente que termina em pending_approval) dispara a notificação em tempo real,
    sem alterar o retorno (approval.id) nem o invariante HITL (status=PENDENTE)."""
    from app.services import approval_service as aps

    notified = []

    async def fake_notify(db, approval):
        notified.append(approval.id)

    original = aps._notify_tenant_of_approval
    aps._notify_tenant_of_approval = fake_notify
    try:
        class _FakeDB:
            def add(self, obj):
                self._added = obj

            async def flush(self):
                # Simula o que o INSERT real faria: atribuir o default de id.
                self._added.id = uuid.uuid4()

        class _FakeAgentRun:
            id = uuid.uuid4()
            tenant_id = uuid.uuid4()

        final_state = {
            "pending_approval": {"tipo": "PETITION_FILING", "titulo": "Aprovar", "prioridade": "NORMAL"},
            "agent_results": [],
        }
        approval_id = asyncio.run(aps.create_approval_from_state(_FakeDB(), _FakeAgentRun(), final_state))
    finally:
        aps._notify_tenant_of_approval = original

    assert approval_id is not None
    assert notified == [approval_id]


def test_create_approval_from_state_sem_pending_approval_nao_notifica():
    from app.services import approval_service as aps
    notified = []

    async def fake_notify(db, approval):
        notified.append(approval.id)

    original = aps._notify_tenant_of_approval
    aps._notify_tenant_of_approval = fake_notify
    try:
        result = asyncio.run(aps.create_approval_from_state(None, None, {}))
    finally:
        aps._notify_tenant_of_approval = original

    assert result is None
    assert notified == []
