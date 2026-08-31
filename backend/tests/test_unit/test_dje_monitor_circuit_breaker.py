"""Fase 142 — reforço defensivo contra 403 na varredura diária da Comunica/
DJEN: um circuit breaker local a `scan_publicacoes` para de martelar o
portal pro resto da lista de OABs assim que acumula falhas consecutivas,
em vez de repetir o mesmo padrão rejeitado até o fim (achado: a varredura
diária chamava `buscar_comunicacoes` direto, sem o CircuitBreaker que o
fluxo sob demanda via ComunicaFonte já usa)."""
import uuid

import pytest

import app.services.dje_monitor as dje_monitor


class _FakeScalarsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, oabs_rows):
        # 1a chamada: OABs monitoradas (User); 2a: TenantConfig.extra_data (sempre vazia neste teste).
        self._results = [_FakeScalarsResult(oabs_rows), _FakeScalarsResult([])]

    async def execute(self, query):
        return self._results.pop(0) if self._results else _FakeScalarsResult([])

    def add(self, obj):
        pass

    async def flush(self):
        pass

    async def commit(self):
        pass


def _oabs(n):
    return [(f"{1000+i}", "SP", uuid.uuid4()) for i in range(n)]


async def _fake_sleep(*args, **kwargs):
    pass


@pytest.mark.asyncio
async def test_breaker_abre_apos_3_falhas_e_pula_oabs_restantes(monkeypatch):
    chamadas = []

    async def _fake_buscar_falha_sempre(oab_numero, oab_uf, data_inicio, data_fim, stats=None, **kwargs):
        chamadas.append(oab_numero)
        if stats is not None:
            stats["requests"] = 1
            stats["ok"] = False
            stats["error"] = "HTTP 403 da Comunica/DJEN"
        return []

    monkeypatch.setattr("app.integrations.dje.comunica.buscar_comunicacoes", _fake_buscar_falha_sempre)
    monkeypatch.setattr(dje_monitor.asyncio, "sleep", _fake_sleep)

    db = _FakeDB(_oabs(6))
    resultado = await dje_monitor.scan_publicacoes(db, tenant_id=None, dias_retro=1)

    # 3 falhas consecutivas abrem o breaker (mesmo threshold de comunica_fonte.py);
    # as 3 OABs restantes são puladas sem nova chamada à API.
    assert len(chamadas) == 3
    assert resultado["oabs_puladas_circuito"] == 3
    assert resultado["comunica_bloqueada"] is True
    assert resultado["oabs_monitoradas"] == 6


@pytest.mark.asyncio
async def test_sucesso_normal_nao_abre_breaker_nem_pula_oabs(monkeypatch):
    chamadas = []

    async def _fake_buscar_sucesso(oab_numero, oab_uf, data_inicio, data_fim, stats=None, **kwargs):
        chamadas.append(oab_numero)
        if stats is not None:
            stats["requests"] = 1
            stats["ok"] = True
        return []

    monkeypatch.setattr("app.integrations.dje.comunica.buscar_comunicacoes", _fake_buscar_sucesso)
    monkeypatch.setattr(dje_monitor.asyncio, "sleep", _fake_sleep)

    db = _FakeDB(_oabs(4))
    resultado = await dje_monitor.scan_publicacoes(db, tenant_id=None, dias_retro=1)

    assert len(chamadas) == 4
    assert resultado["oabs_puladas_circuito"] == 0
    assert resultado["comunica_bloqueada"] is False


@pytest.mark.asyncio
async def test_falha_expoe_fonte_respondeu_e_detalhe(monkeypatch):
    """Fase 252 — achado: `scan_publicacoes` descartava o `stats` de cada
    OAB a cada iteração do loop, então "0 intimações" por não ter novidade
    no dia e "0 intimações" por 403 da Comunica pareciam idênticos pro
    endpoint /publicacoes/varrer (ao contrário de `capturar_por_oab`, que
    já expunha isso desde a Fase 114). Confirma que o resultado final
    agora carrega `fonte_respondeu=False`/`fonte_detalhe` com a causa real."""
    async def _fake_buscar_falha_sempre(oab_numero, oab_uf, data_inicio, data_fim, stats=None, **kwargs):
        if stats is not None:
            stats["requests"] = 1
            stats["ok"] = False
            stats["status_code"] = 403
            stats["error"] = "HTTP 403 da Comunica/DJEN"
        return []

    monkeypatch.setattr("app.integrations.dje.comunica.buscar_comunicacoes", _fake_buscar_falha_sempre)
    monkeypatch.setattr(dje_monitor.asyncio, "sleep", _fake_sleep)

    db = _FakeDB(_oabs(1))
    resultado = await dje_monitor.scan_publicacoes(db, tenant_id=None, dias_retro=1)

    assert resultado["fonte_respondeu"] is False
    assert resultado["fonte_detalhe"] == "HTTP 403 da Comunica/DJEN"


@pytest.mark.asyncio
async def test_sucesso_expoe_fonte_respondeu_true(monkeypatch):
    async def _fake_buscar_sucesso(oab_numero, oab_uf, data_inicio, data_fim, stats=None, **kwargs):
        if stats is not None:
            stats["requests"] = 1
            stats["ok"] = True
        return []

    monkeypatch.setattr("app.integrations.dje.comunica.buscar_comunicacoes", _fake_buscar_sucesso)
    monkeypatch.setattr(dje_monitor.asyncio, "sleep", _fake_sleep)

    db = _FakeDB(_oabs(1))
    resultado = await dje_monitor.scan_publicacoes(db, tenant_id=None, dias_retro=1)

    assert resultado["fonte_respondeu"] is True
    assert resultado["fonte_detalhe"] is None


@pytest.mark.asyncio
async def test_intervalo_entre_requisicoes_e_respeitado(monkeypatch):
    """Regressão: cada OAB deve passar por um pequeno sleep — confirma que o
    reforço (rajada sem pausa) foi de fato aplicado, sem depender de medir
    tempo real (mocka asyncio.sleep e conta as chamadas)."""
    sleeps = []

    async def _fake_sleep(seconds):
        sleeps.append(seconds)

    async def _fake_buscar(oab_numero, oab_uf, data_inicio, data_fim, stats=None, **kwargs):
        if stats is not None:
            stats["requests"] = 1
            stats["ok"] = True
        return []

    monkeypatch.setattr("app.integrations.dje.comunica.buscar_comunicacoes", _fake_buscar)
    monkeypatch.setattr(dje_monitor.asyncio, "sleep", _fake_sleep)

    db = _FakeDB(_oabs(3))
    await dje_monitor.scan_publicacoes(db, tenant_id=None, dias_retro=1)

    assert len(sleeps) == 3
    assert all(s == dje_monitor._INTERVALO_ENTRE_OABS_S for s in sleeps)
