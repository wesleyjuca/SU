"""Rodada pós-166a43c (achado real de auditoria) — `escavador_fonte.py`,
`judit_fonte.py`, `jusbrasil_fonte.py` e `pdpj_fonte.py` usavam
`CircuitBreaker.run(..., default=None)` sem nenhuma forma de distinguir
"disjuntor aberto/erro real" de "processo genuinamente sem partes" — mesma
classe de bug já corrigida só pro DataJud (`sinalizar_falha`,
`test_fontes.py::test_datajud_fonte_sinalizar_falha_distingue_breaker_aberto`).

`movimentos()`/`detalhar()` dessas 4 fontes são código morto (zero chamador
em produção, confirmado por grep) — fora de escopo aqui. `partes()` É usado
ativamente por `oab_capture.py::_enriquecer_partes()`, que hoje mascarava
"fonte fora do ar" como "0 partes encontradas".

Prova nos dois sentidos: disjuntor fechado + cliente HTTP que teria sucesso
funciona nos dois modos; disjuntor forçado aberto (3 falhas) faz `partes()`
devolver `None` (não `[]`) só quando `sinalizar_falha=True` — o default
(`False`) preserva `[]`, comportamento antigo, sem regressão pra ninguém
que não passar o parâmetro."""
import pytest

from app.integrations.fontes.circuit_breaker import OPEN


class _FakeHTTPResponse:
    status_code = 200

    def json(self):
        return {"poloAtivo": [{"nome": "Fulano de Tal"}]}


class _FakeHTTPClienteSempreSucesso:
    """Substitui `httpx.AsyncClient`/`curl_cffi.requests.AsyncSession` — se
    for chamado com o disjuntor aberto, o teste falha (prova de que o
    disjuntor de fato intercepta antes da rede)."""

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, *a, **kw):
        return _FakeHTTPResponse()


@pytest.mark.asyncio
async def test_escavador_partes_sinalizar_falha_distingue_breaker_aberto(monkeypatch):
    import app.integrations.fontes.escavador_fonte as mod

    fonte = mod.EscavadorFonte(token="tok")
    monkeypatch.setattr(mod.httpx, "AsyncClient", _FakeHTTPClienteSempreSucesso)

    assert await fonte.partes("0001234-56.2026.8.06.0001", sinalizar_falha=True)

    for _ in range(3):
        fonte._breaker.record_failure()
    assert fonte._breaker.state == OPEN

    assert await fonte.partes("0001234-56.2026.8.06.0001") == []
    assert await fonte.partes("0001234-56.2026.8.06.0001", sinalizar_falha=True) is None


@pytest.mark.asyncio
async def test_judit_partes_sinalizar_falha_distingue_breaker_aberto(monkeypatch):
    import app.integrations.fontes.judit_fonte as mod

    fonte = mod.JuditFonte(token="tok")
    monkeypatch.setattr(mod.httpx, "AsyncClient", _FakeHTTPClienteSempreSucesso)

    assert await fonte.partes("0001234-56.2026.8.06.0001", sinalizar_falha=True)

    for _ in range(3):
        fonte._breaker.record_failure()
    assert fonte._breaker.state == OPEN

    assert await fonte.partes("0001234-56.2026.8.06.0001") == []
    assert await fonte.partes("0001234-56.2026.8.06.0001", sinalizar_falha=True) is None


@pytest.mark.asyncio
async def test_jusbrasil_partes_sinalizar_falha_distingue_breaker_aberto(monkeypatch):
    import app.integrations.fontes.jusbrasil_fonte as mod

    fonte = mod.JusbrasilFonte(token="tok")
    monkeypatch.setattr(mod.httpx, "AsyncClient", _FakeHTTPClienteSempreSucesso)

    assert await fonte.partes("0001234-56.2026.8.06.0001", sinalizar_falha=True)

    for _ in range(3):
        fonte._breaker.record_failure()
    assert fonte._breaker.state == OPEN

    assert await fonte.partes("0001234-56.2026.8.06.0001") == []
    assert await fonte.partes("0001234-56.2026.8.06.0001", sinalizar_falha=True) is None


@pytest.mark.asyncio
async def test_pdpj_partes_sinalizar_falha_distingue_breaker_aberto(monkeypatch):
    import app.integrations.fontes.pdpj_fonte as mod

    fonte = mod.PdpjFonte(token="tok")
    monkeypatch.setattr(mod, "AsyncSession", _FakeHTTPClienteSempreSucesso)

    assert await fonte.partes("0001234-56.2026.8.06.0001", sinalizar_falha=True)

    for _ in range(3):
        fonte._breaker.record_failure()
    assert fonte._breaker.state == OPEN

    assert await fonte.partes("0001234-56.2026.8.06.0001") == []
    assert await fonte.partes("0001234-56.2026.8.06.0001", sinalizar_falha=True) is None


@pytest.mark.asyncio
async def test_oab_capture_enriquecer_partes_reporta_falha_real(monkeypatch):
    """A prova de ponta a ponta do achado: `_enriquecer_partes()` (chamador
    real em produção) precisa contar como FALHA quando a fonte credenciada
    está fora do ar — não mais como "0 partes, sem erro"."""
    from app.services import oab_capture
    from app.integrations.fontes import credenciadas

    class _FonteQuebrada:
        nome = "escavador"

        async def partes(self, numero_cnj, tribunal=None, *, sinalizar_falha=False):
            assert sinalizar_falha is True, "oab_capture precisa pedir sinalizar_falha=True"
            return None  # disjuntor aberto/erro real

    async def _fake_fonte(db, tenant_id):
        return _FonteQuebrada()

    monkeypatch.setattr(credenciadas, "fonte_partes_credenciada", _fake_fonte)

    usos_registrados = []

    async def _fake_registrar_uso(db, tenant_id, nome, *, sucesso, detalhe=None):
        usos_registrados.append({"nome": nome, "sucesso": sucesso, "detalhe": detalhe})

    from app.services import integration_hub
    monkeypatch.setattr(integration_hub, "registrar_uso", _fake_registrar_uso)

    class _ProcFake:
        numero_cnj = "0001234-56.2026.8.06.0001"

    resultado = await oab_capture._enriquecer_partes(
        db=None, tenant_id="t", procs=[(_ProcFake(), "TJCE")],
    )

    assert resultado == {"total": 0, "fonte_configurada": True}
    assert usos_registrados == [{"nome": "escavador", "sucesso": False, "detalhe": None}]
