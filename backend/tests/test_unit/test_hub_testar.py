"""Fase 81 — testar_conexao do hub (lógica, sem rede/DB reais)."""
import pytest

from app.services import integration_hub as hub


class _FakeIntegSem:
    credentials_enc = None
    status = "DESCONECTADA"


class _FakeInteg:
    credentials_enc = "x"
    status = "CONECTADA"


@pytest.mark.asyncio
async def test_provider_desconhecido():
    r = await hub.testar_conexao(db=None, tenant_id="t", provider="nao_existe")
    assert r["ok"] is False and r["status"] == "DESCONHECIDO"


@pytest.mark.asyncio
async def test_sem_credencial(monkeypatch):
    async def _get(db, t, p): return None
    monkeypatch.setattr(hub, "get_integration", _get)
    r = await hub.testar_conexao(db=None, tenant_id="t", provider="pdpj")
    assert r["ok"] is False and r["status"] == "DESCONECTADA"


@pytest.mark.asyncio
async def test_provider_sem_teste_automatico(monkeypatch):
    # whatsapp existe mas não tem fonte credenciada testável → status atual
    async def _get(db, t, p): return _FakeInteg()
    monkeypatch.setattr(hub, "get_integration", _get)
    r = await hub.testar_conexao(db=None, tenant_id="t", provider="whatsapp")
    assert r["ok"] is True and "não disponível" in r["detail"]


@pytest.mark.asyncio
async def test_credencial_valida_marca_conectada(monkeypatch):
    integ = _FakeInteg()
    integ.status = "ERRO"
    async def _get(db, t, p): return integ
    monkeypatch.setattr(hub, "get_integration", _get)

    class _FakeFonte:
        async def testar(self): return (True, "ok (HTTP 404)")
    async def _fonte(db, t, p): return _FakeFonte()
    monkeypatch.setattr(hub, "_fonte_credenciada_do_provider", _fonte)

    class _DB:
        async def flush(self): pass
    r = await hub.testar_conexao(db=_DB(), tenant_id="t", provider="pdpj")
    assert r["ok"] is True and r["status"] == "CONECTADA" and integ.status == "CONECTADA"


@pytest.mark.asyncio
async def test_credencial_invalida_marca_erro(monkeypatch):
    integ = _FakeInteg()
    async def _get(db, t, p): return integ
    monkeypatch.setattr(hub, "get_integration", _get)

    class _FakeFonte:
        async def testar(self): return (False, "credencial rejeitada (HTTP 401)")
    async def _fonte(db, t, p): return _FakeFonte()
    monkeypatch.setattr(hub, "_fonte_credenciada_do_provider", _fonte)

    class _DB:
        async def flush(self): pass
    r = await hub.testar_conexao(db=_DB(), tenant_id="t", provider="escavador")
    assert r["ok"] is False and r["status"] == "ERRO" and integ.status == "ERRO"
