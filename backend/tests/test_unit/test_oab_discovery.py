"""Fase 194 — descoberta automática periódica de processos novos por OAB.
`capturar_por_oab()` (app/services/oab_capture.py) já existia e funcionava
desde a Fase 73/102 — só disparava manualmente (POST /oabs/capturar) ou
por agente sob demanda; nenhuma entrada no beat_schedule automatizava a
descoberta. Este teste cobre só o loop novo (por tenant, fail-soft), não
a lógica interna de captura em si (já coberta em outros testes)."""
import uuid

import pytest


class _FakeScalarsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, tenant_ids):
        self._tenant_ids = tenant_ids

    async def execute(self, query):
        return _FakeScalarsResult(self._tenant_ids)


@pytest.mark.asyncio
async def test_roda_capturar_por_oab_pra_cada_tenant_ativo(monkeypatch):
    import app.workers.tasks.oab_discovery as mod

    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    db = _FakeDB([tenant_a, tenant_b])

    chamadas = []

    async def _fake_capturar(db_arg, tenant_id, dias_retro):
        chamadas.append((tenant_id, dias_retro))
        return {"oabs": 1, "processos_criados": 2} if tenant_id == tenant_a else {"oabs": 0, "processos_criados": 0}

    monkeypatch.setattr("app.services.oab_capture.capturar_por_oab", _fake_capturar)

    resultado = await mod.executar_descoberta_por_oab(db)

    assert len(chamadas) == 2
    assert all(dias == mod.DIAS_RETRO_PERIODICO for _, dias in chamadas)
    assert resultado["tenants_verificados"] == 2
    assert resultado["tenants_com_oab"] == 1
    assert resultado["processos_criados"] == 2


@pytest.mark.asyncio
async def test_falha_em_um_tenant_nao_aborta_os_demais(monkeypatch):
    """Mesmo princípio fail-soft-por-tenant já usado em google_drive_sync.py
    (Fase 167) — uma exceção num tenant não pode derrubar a descoberta dos
    demais."""
    import app.workers.tasks.oab_discovery as mod

    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    db = _FakeDB([tenant_a, tenant_b])

    async def _fake_capturar(db_arg, tenant_id, dias_retro):
        if tenant_id == tenant_a:
            raise RuntimeError("fonte pública fora do ar")
        return {"oabs": 1, "processos_criados": 3}

    monkeypatch.setattr("app.services.oab_capture.capturar_por_oab", _fake_capturar)

    resultado = await mod.executar_descoberta_por_oab(db)

    assert resultado["tenants_verificados"] == 2
    assert resultado["tenants_com_oab"] == 1  # só tenant_b contou
    assert resultado["processos_criados"] == 3


@pytest.mark.asyncio
async def test_sem_tenants_ativos_nao_chama_captura(monkeypatch):
    import app.workers.tasks.oab_discovery as mod

    db = _FakeDB([])

    async def _explode(*a, **kw):
        raise AssertionError("capturar_por_oab não deveria ser chamado sem tenants")
    monkeypatch.setattr("app.services.oab_capture.capturar_por_oab", _explode)

    resultado = await mod.executar_descoberta_por_oab(db)

    assert resultado == {"tenants_verificados": 0, "tenants_com_oab": 0, "processos_criados": 0}
