"""Fase 73 — fundação de fontes processuais (lógica pura, sem rede/Redis)."""
from datetime import date, datetime, timezone

import pytest

from app.integrations.fontes.base import Capability, ProcessoDescoberto
from app.integrations.fontes.circuit_breaker import CLOSED, HALF_OPEN, OPEN, CircuitBreaker


# ─── CircuitBreaker ───────────────────────────────────────────────────────────
def test_breaker_abre_no_limiar_de_falhas():
    cb = CircuitBreaker(failure_threshold=3, reset_timeout=999, name="t")
    assert cb.state == CLOSED and cb.allow()
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CLOSED and cb.allow()   # ainda abaixo do limiar
    cb.record_failure()
    assert cb.state == OPEN and not cb.allow()  # 3ª falha abre


def test_breaker_reabre_e_meio_aberto_com_timeout_zero():
    # reset_timeout=0 → transição preguiçosa open→half_open é imediata.
    cb = CircuitBreaker(failure_threshold=1, reset_timeout=0, name="t")
    cb.record_failure()
    # já expirou → half_open deixa passar UMA tentativa
    assert cb.state == HALF_OPEN and cb.allow()
    # falha em half_open reabre
    cb.record_failure()
    assert cb.state == HALF_OPEN  # reabriu, mas timeout 0 → já half_open de novo


def test_breaker_sucesso_fecha():
    cb = CircuitBreaker(failure_threshold=2, reset_timeout=999)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == OPEN
    cb.record_success()
    assert cb.state == CLOSED and cb.allow()


@pytest.mark.asyncio
async def test_breaker_run_fail_soft_e_conta_falha():
    cb = CircuitBreaker(failure_threshold=1, reset_timeout=999, name="t")

    async def explode():
        raise RuntimeError("boom")

    r = await cb.run(explode, default=[])
    assert r == []                 # não propaga; devolve default
    assert cb.state == OPEN         # falha contabilizada abriu


@pytest.mark.asyncio
async def test_breaker_run_aberto_nao_chama():
    cb = CircuitBreaker(failure_threshold=1, reset_timeout=999)
    cb.record_failure()            # abre
    chamou = {"v": False}

    async def factory():
        chamou["v"] = True
        return "x"

    r = await cb.run(factory, default="D")
    assert r == "D" and chamou["v"] is False


# ─── Registry ─────────────────────────────────────────────────────────────────
def test_registry_filtra_por_capability():
    from app.integrations.fontes import registry

    descobre = registry.fontes_com_capability(Capability.DESCOBRIR_OAB)
    assert [f.nome for f in descobre] == ["comunica"]

    detalha = {f.nome for f in registry.fontes_com_capability(Capability.DETALHAR)}
    assert "datajud" in detalha

    movs = {f.nome for f in registry.fontes_com_capability(Capability.MOVIMENTOS)}
    assert "datajud" in movs

    # Nenhuma fonte pública fornece partes (fica p/ PJe/PDPJ na Fase 75).
    assert registry.fontes_com_capability(Capability.PARTES) == []

    assert registry.obter_fonte("comunica") is not None
    assert registry.obter_fonte("inexistente") is None


# ─── ComunicaFonte — mapeamento e dedup ───────────────────────────────────────
class _FakeComunicacao:
    def __init__(self, numero_cnj, tribunal):
        self.numero_cnj = numero_cnj
        self.tribunal = tribunal


@pytest.mark.asyncio
async def test_comunica_fonte_mapeia_e_dedup(monkeypatch):
    from app.integrations.fontes.comunica_fonte import ComunicaFonte
    import app.integrations.dje.comunica as comunica_mod

    async def fake_buscar(oab_numero, oab_uf, data_inicio, data_fim, *, max_paginas, itens_por_pagina, stats):
        stats["requests"] = 1
        stats["ok"] = True
        return [
            _FakeComunicacao("123", "TJSP"),
            _FakeComunicacao("123", "TJSP"),   # duplicado → some
            _FakeComunicacao(None, "TJRJ"),    # sem número → ignorado
            _FakeComunicacao("456", None),     # tribunal ausente ok
        ]

    monkeypatch.setattr(comunica_mod, "buscar_comunicacoes", fake_buscar)

    fonte = ComunicaFonte()
    achados = await fonte.descobrir_por_oab("12345", "SP", date(2026, 1, 1), date(2026, 1, 31))
    numeros = [a.numero_cnj for a in achados]
    assert numeros == ["123", "456"]
    assert all(isinstance(a, ProcessoDescoberto) for a in achados)
    assert achados[0].fonte == "comunica" and achados[0].uf == "SP" and achados[0].tribunal == "TJSP"
    assert fonte._breaker.state == CLOSED  # ok=True → sucesso


@pytest.mark.asyncio
async def test_comunica_fonte_fonte_off_conta_falha(monkeypatch):
    from app.integrations.fontes.comunica_fonte import ComunicaFonte
    import app.integrations.dje.comunica as comunica_mod

    async def fake_off(oab_numero, oab_uf, data_inicio, data_fim, *, max_paginas, itens_por_pagina, stats):
        stats["requests"] = 1   # tentou...
        # ...mas nunca marcou ok → fonte inalcançável
        return []

    monkeypatch.setattr(comunica_mod, "buscar_comunicacoes", fake_off)
    fonte = ComunicaFonte()
    fonte._breaker.failure_threshold = 1
    achados = await fonte.descobrir_por_oab("12345", "SP", date(2026, 1, 1), date(2026, 1, 31))
    assert achados == [] and fonte._breaker.state == OPEN


# ─── DataJudFonte ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_datajud_fonte_capabilities_e_detalhar(monkeypatch):
    from app.integrations.fontes.datajud_fonte import DataJudFonte

    fonte = DataJudFonte()
    assert fonte.suporta(Capability.DETALHAR) and fonte.suporta(Capability.MOVIMENTOS)
    assert not fonte.suporta(Capability.PARTES)

    class _FakeClient:
        def __init__(self, *a, **k):
            self.tribunal = "TJCE"
            self.closed = False
        async def fetch_processo(self, numero, tribunal=None):
            return {"numero_processo": numero, "movimentos": [
                {"nome": "Distribuído", "dataHora": "2026-01-05T10:00:00Z"},
            ]}
        async def fetch_movements(self, numero, since=None):
            from app.integrations.tribunais.base import MovementData
            return [MovementData(data=datetime(2026, 1, 5, tzinfo=timezone.utc),
                                 descricao="Juntada", tipo="123", raw_data={"x": 1})]
        async def close(self):
            self.closed = True

    monkeypatch.setattr(fonte, "_client", lambda tribunal: _FakeClient())
    det = await fonte.detalhar("999", "TJSP")
    assert det and det["numero_processo"] == "999"

    movs = await fonte.movimentos("999", "TJSP", since=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert len(movs) == 1 and movs[0].descricao == "Distribuído"

    # fetch_movements_datajud preserva o shape MovementData (código + raw)
    md = await fonte.fetch_movements_datajud("999", "TJSP")
    assert len(md) == 1 and md[0].tipo == "123" and md[0].raw_data == {"x": 1}
