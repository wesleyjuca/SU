"""Unit tests para atribuição da trilha de auditoria (user_id + tenant_id)."""
import types
import uuid
import app.dependencies as deps
import app.core.middleware as mw
import app.db.base as dbbase
from app.core.security import create_access_token


async def test_get_current_user_populates_request_state():
    uid, tid = uuid.uuid4(), uuid.uuid4()

    class _User:
        def __init__(self):
            self.id = uid
            self.tenant_id = tid
            self.is_active = True
            self.role = "ADMIN"

    class _Result:
        def scalar_one_or_none(self):
            return _User()

    class _DB:
        async def execute(self, stmt):
            return _Result()

    class _Creds:
        def __init__(self, t):
            self.credentials = t

    req = types.SimpleNamespace(state=types.SimpleNamespace())
    token = create_access_token(str(uid), "ADMIN")
    await deps.get_current_user(request=req, credentials=_Creds(token), db=_DB())

    assert req.state.user_id == uid
    assert req.state.tenant_id == tid


async def test_write_audit_persists_tenant_id(monkeypatch):
    uid, tid = uuid.uuid4(), uuid.uuid4()
    captured = {}

    class _AuditSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def add(self, entry):
            captured["entry"] = entry

        async def commit(self):
            captured["committed"] = True

    monkeypatch.setattr(dbbase, "AsyncSessionLocal", lambda: _AuditSession())

    middleware = mw.AuditMiddleware(app=lambda *a: None)
    req = types.SimpleNamespace(
        state=types.SimpleNamespace(user_id=uid, tenant_id=tid),
        method="POST",
        url=types.SimpleNamespace(path="/api/v1/clients"),
        client=types.SimpleNamespace(host="1.2.3.4"),
        headers={"user-agent": "x"},
    )
    resp = types.SimpleNamespace(status_code=201)
    await middleware._write_audit(req, resp, 12)

    entry = captured["entry"]
    assert entry.user_id == uid and entry.tenant_id == tid
    assert captured.get("committed") is True
