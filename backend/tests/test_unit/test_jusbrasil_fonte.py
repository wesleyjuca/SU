"""Fase 88 — conector credenciado Jusbrasil (lógica pura)."""
import pytest

from app.integrations.fontes.jusbrasil_fonte import JusbrasilFonte
from app.integrations.fontes.base import Capability


def test_capabilities():
    f = JusbrasilFonte(token="t")
    assert f.suporta(Capability.DESCOBRIR_OAB)
    assert f.suporta(Capability.DETALHAR)
    assert f.suporta(Capability.MOVIMENTOS)
    assert f.suporta(Capability.PARTES)


@pytest.mark.asyncio
async def test_gating_sem_token():
    assert await JusbrasilFonte("").partes("0001234-56.2026.8.06.0001") == []
    assert await JusbrasilFonte("").descobrir_por_oab("1", "CE", None, None) == []


@pytest.mark.asyncio
async def test_numero_invalido():
    assert await JusbrasilFonte("tok").partes("sem-digitos") == []


@pytest.mark.asyncio
async def test_para_tenant_sem_credencial(monkeypatch):
    from app.integrations.fontes import jusbrasil_fonte
    from app.services import integration_hub

    async def _sem_creds(db, tenant_id, provider):
        return None
    monkeypatch.setattr(integration_hub, "get_credentials", _sem_creds)
    assert await jusbrasil_fonte.para_tenant(db=None, tenant_id="t") is None


@pytest.mark.asyncio
async def test_para_tenant_com_credencial(monkeypatch):
    from app.integrations.fontes import jusbrasil_fonte
    from app.services import integration_hub

    async def _com_creds(db, tenant_id, provider):
        assert provider == "jusbrasil"
        return {"token": "abc123", "base_url": None}
    monkeypatch.setattr(integration_hub, "get_credentials", _com_creds)
    fonte = await jusbrasil_fonte.para_tenant(db=None, tenant_id="t")
    assert isinstance(fonte, jusbrasil_fonte.JusbrasilFonte)


def test_ordem_de_fallback_inclui_jusbrasil_por_ultimo():
    from app.integrations.fontes.credenciadas import _ORDEM_PARTES
    assert _ORDEM_PARTES == ("pdpj", "escavador", "judit", "jusbrasil")


@pytest.mark.asyncio
async def test_fonte_partes_credenciada_alcanca_jusbrasil(monkeypatch):
    from app.integrations.fontes import pdpj_fonte, escavador_fonte, judit_fonte, jusbrasil_fonte
    from app.integrations.fontes.credenciadas import fonte_partes_credenciada

    chamadas = []

    async def _none(nome):
        chamadas.append(nome)
        return None

    monkeypatch.setattr(pdpj_fonte, "para_tenant", lambda db, t: _none("pdpj"))
    monkeypatch.setattr(escavador_fonte, "para_tenant", lambda db, t: _none("escavador"))
    monkeypatch.setattr(judit_fonte, "para_tenant", lambda db, t: _none("judit"))
    monkeypatch.setattr(jusbrasil_fonte, "para_tenant", lambda db, t: _none("jusbrasil"))

    assert await fonte_partes_credenciada(db=None, tenant_id="t") is None
    assert chamadas == ["pdpj", "escavador", "judit", "jusbrasil"]

    async def _jb(db, t):
        return jusbrasil_fonte.JusbrasilFonte("tok")
    monkeypatch.setattr(jusbrasil_fonte, "para_tenant", _jb)
    fonte = await fonte_partes_credenciada(db=None, tenant_id="t")
    assert isinstance(fonte, jusbrasil_fonte.JusbrasilFonte)
