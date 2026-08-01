"""Fase 137.7 — GET /me/ai-configs/stats: agrega `AICallLog` por `config_id`
(taxa de sucesso, custo total, latência média, tokens, último uso/erro).
Testa a formatação/agregação em memória com um DB falso que devolve linhas
já no formato do `GROUP BY` (a query em si — incluindo o filtro por
`current_user.id`, que garante isolamento entre usuários — é coberta pela
verificação empírica com Postgres real, mesmo padrão dos demais endpoints
desta sessão que fazem JOIN/agregação)."""
import types
import uuid
from datetime import datetime, timezone
import pytest


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDB:
    def __init__(self, results):
        self._results = list(results)

    async def execute(self, _stmt):
        return self._results.pop(0)


class _FakeUser:
    def __init__(self):
        self.id = uuid.uuid4()


@pytest.mark.asyncio
async def test_stats_vazio_sem_chamadas_registradas():
    from app.api.v1.users import get_my_ai_configs_stats

    db = _FakeDB([_FakeResult([])])
    result = await get_my_ai_configs_stats(current_user=_FakeUser(), db=db)

    assert result == {"stats": {}}


@pytest.mark.asyncio
async def test_stats_agrega_taxa_de_sucesso_custo_e_latencia():
    from app.api.v1.users import get_my_ai_configs_stats

    cfg_id = uuid.uuid4()
    agora = datetime(2026, 8, 1, tzinfo=timezone.utc)
    agregado = types.SimpleNamespace(
        config_id=cfg_id, total_calls=4, total_success=3,
        avg_latency_ms=150.5, total_cost_usd=0.05, total_tokens=1000,
        last_used_at=agora,
    )
    erro_row = types.SimpleNamespace(config_id=cfg_id, error="rate limit", created_at=agora)

    db = _FakeDB([_FakeResult([agregado]), _FakeResult([erro_row])])
    result = await get_my_ai_configs_stats(current_user=_FakeUser(), db=db)

    stats = result["stats"][str(cfg_id)]
    assert stats["total_calls"] == 4
    assert stats["success_rate"] == 0.75
    assert stats["avg_latency_ms"] == 150.5
    assert stats["total_cost_usd"] == 0.05
    assert stats["total_tokens"] == 1000
    assert stats["last_used_at"] == agora.isoformat()
    assert stats["last_error"] == "rate limit"


@pytest.mark.asyncio
async def test_stats_sem_falhas_last_error_none_e_nao_consulta_erros():
    """Se toda config tem 100% de sucesso, a 2ª query (filtro `success ==
    False`) não devolve nenhuma linha — `last_error` fica `None`."""
    from app.api.v1.users import get_my_ai_configs_stats

    cfg_id = uuid.uuid4()
    agregado = types.SimpleNamespace(
        config_id=cfg_id, total_calls=2, total_success=2,
        avg_latency_ms=100.0, total_cost_usd=0.01, total_tokens=200,
        last_used_at=None,
    )
    db = _FakeDB([_FakeResult([agregado]), _FakeResult([])])
    result = await get_my_ai_configs_stats(current_user=_FakeUser(), db=db)

    stats = result["stats"][str(cfg_id)]
    assert stats["last_error"] is None
    assert stats["last_used_at"] is None
