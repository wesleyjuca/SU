"""Fase 177.2 — avisar ADMIN/SOCIO/SUPERADMIN quando uma credencial do hub
(PDPJ/Escavador/Judit/Jusbrasil/WhatsApp/...) para de funcionar. Antes,
`registrar_uso()`/`testar_conexao()` só viravam um badge vermelho passivo na
página de Integrações — ninguém era avisado (podia ficar quebrado por
semanas). Testa a lógica de transição (só notifica na borda CONECTADA→ERRO,
nunca em falha repetida) sem depender de Postgres/rede reais."""
import pytest

from app.services import integration_hub as hub


class _FakeInteg:
    def __init__(self, status="CONECTADA", tenant_id="t1", provider="pdpj"):
        self.status = status
        self.tenant_id = tenant_id
        self.provider = provider
        self.last_success_at = None
        self.last_error_at = None
        self.last_error_detail = None
        self.credentials_enc = "x"


class _FakeUserIdsResult:
    def __init__(self, ids):
        self._ids = ids

    def scalars(self):
        ids = self._ids

        class _S:
            def all(self_inner):
                return ids
        return _S()


class _FakeDB:
    """Responde só o SELECT de User.id (usado por `_notify_integration_error`)
    — `get_integration`/`_fonte_credenciada_do_provider` são monkeypatchados
    à parte, então nunca chegam aqui."""

    def __init__(self, user_ids):
        self._user_ids = user_ids
        self.added = []
        self.commits = 0

    async def execute(self, _query):
        return _FakeUserIdsResult(self._user_ids)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def flush(self):
        pass


def _notificacoes_erro(db):
    return [n for n in db.added if getattr(n, "tipo", None) == "INTEGRACAO_ERRO"]


@pytest.mark.asyncio
async def test_registrar_uso_falha_transicao_notifica_admins(monkeypatch):
    integ = _FakeInteg(status="CONECTADA")

    async def _get(db, t, p):
        return integ
    monkeypatch.setattr(hub, "get_integration", _get)

    db = _FakeDB(user_ids=["admin1", "socio1", "superadmin1"])
    await hub.registrar_uso(db, "t1", "pdpj", sucesso=False, detalhe="token expirado")

    assert integ.status == "ERRO"
    notifs = _notificacoes_erro(db)
    assert len(notifs) == 3
    assert all(n.corpo == "token expirado" for n in notifs)
    assert all(n.link == "/integracoes" for n in notifs)
    assert all(n.priority == "ALTA" for n in notifs)
    assert db.commits == 1


@pytest.mark.asyncio
async def test_registrar_uso_falha_repetida_nao_notifica_de_novo(monkeypatch):
    integ = _FakeInteg(status="ERRO")  # já estava em erro

    async def _get(db, t, p):
        return integ
    monkeypatch.setattr(hub, "get_integration", _get)

    db = _FakeDB(user_ids=["admin1"])
    await hub.registrar_uso(db, "t1", "pdpj", sucesso=False, detalhe="ainda falhando")

    assert integ.status == "ERRO"
    assert _notificacoes_erro(db) == []


@pytest.mark.asyncio
async def test_registrar_uso_sucesso_nao_notifica(monkeypatch):
    integ = _FakeInteg(status="ERRO")

    async def _get(db, t, p):
        return integ
    monkeypatch.setattr(hub, "get_integration", _get)

    db = _FakeDB(user_ids=["admin1"])
    await hub.registrar_uso(db, "t1", "pdpj", sucesso=True)

    assert integ.status == "CONECTADA"
    assert _notificacoes_erro(db) == []


@pytest.mark.asyncio
async def test_testar_conexao_falha_transicao_notifica(monkeypatch):
    integ = _FakeInteg(status="CONECTADA", provider="escavador")

    async def _get(db, t, p):
        return integ
    monkeypatch.setattr(hub, "get_integration", _get)

    class _FakeFonte:
        async def testar(self):
            return (False, "credencial rejeitada (HTTP 401)")

    async def _fonte(db, t, p):
        return _FakeFonte()
    monkeypatch.setattr(hub, "_fonte_credenciada_do_provider", _fonte)

    db = _FakeDB(user_ids=["admin1", "socio1"])
    r = await hub.testar_conexao(db, "t1", "escavador")

    assert r["ok"] is False and integ.status == "ERRO"
    notifs = _notificacoes_erro(db)
    assert len(notifs) == 2
    assert "Escavador" in notifs[0].titulo


@pytest.mark.asyncio
async def test_testar_conexao_falha_repetida_nao_notifica_de_novo(monkeypatch):
    integ = _FakeInteg(status="ERRO", provider="escavador")

    async def _get(db, t, p):
        return integ
    monkeypatch.setattr(hub, "get_integration", _get)

    class _FakeFonte:
        async def testar(self):
            return (False, "ainda inválida")

    async def _fonte(db, t, p):
        return _FakeFonte()
    monkeypatch.setattr(hub, "_fonte_credenciada_do_provider", _fonte)

    db = _FakeDB(user_ids=["admin1"])
    await hub.testar_conexao(db, "t1", "escavador")

    assert _notificacoes_erro(db) == []


@pytest.mark.asyncio
async def test_notify_integration_error_fail_soft_nao_propaga(monkeypatch):
    """Se a própria query de destinatários falhar (ex.: DB fora do ar no
    meio da notificação), registrar_uso ainda tem que commitar a mudança de
    status — a notificação é um "nice to have", não pode travar o core."""
    integ = _FakeInteg(status="CONECTADA")

    async def _get(db, t, p):
        return integ
    monkeypatch.setattr(hub, "get_integration", _get)

    class _DbQuebradoNoUserQuery:
        commits = 0

        async def execute(self, _query):
            raise RuntimeError("conexão perdida no meio da notificação")

        async def commit(self):
            self.commits += 1

    db = _DbQuebradoNoUserQuery()
    await hub.registrar_uso(db, "t1", "pdpj", sucesso=False, detalhe="x")

    assert integ.status == "ERRO"
    assert db.commits == 1
