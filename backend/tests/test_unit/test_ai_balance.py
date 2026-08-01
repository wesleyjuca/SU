"""Fase 137.6 — `ordenar_configs()` (app/services/ai_balance.py): função pura
que decide a ordem de tentativa das `AIProviderConfig` de um usuário
conforme o "modo de uso" (padrao/round_robin/performance). Sem DB/crypto —
opera sobre objetos `AIProviderConfig`-like (só precisa de `.id`,
`.is_default`, `.priority`, `.created_at`)."""
import uuid
from datetime import datetime, timedelta, timezone

from app.services.ai_balance import ordenar_configs


class _FakeConfig:
    def __init__(self, is_default=False, priority=None, created_at=None, config_id=None):
        self.id = config_id or uuid.uuid4()
        self.is_default = is_default
        self.priority = priority
        self.created_at = created_at or datetime.now(timezone.utc)


def _t(segundos_atras: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(seconds=segundos_atras)


def test_padrao_replica_ordem_de_sempre():
    a = _FakeConfig(is_default=False, priority=2, created_at=_t(100))
    b = _FakeConfig(is_default=True, priority=None, created_at=_t(200))
    c = _FakeConfig(is_default=False, priority=1, created_at=_t(50))
    resultado = ordenar_configs([a, b, c], "padrao")
    assert resultado == [b, c, a]  # padrão primeiro, depois por priority asc


def test_padrao_prioridade_nula_vai_pro_fim():
    a = _FakeConfig(is_default=False, priority=None, created_at=_t(100))
    b = _FakeConfig(is_default=False, priority=1, created_at=_t(50))
    resultado = ordenar_configs([a, b], "padrao")
    assert resultado == [b, a]


def test_modo_desconhecido_cai_em_padrao():
    a = _FakeConfig(is_default=True, created_at=_t(100))
    b = _FakeConfig(is_default=False, created_at=_t(50))
    resultado_none = ordenar_configs([a, b], None)
    resultado_garbage = ordenar_configs([a, b], "modo-que-nao-existe")
    assert resultado_none == [a, b]
    assert resultado_garbage == [a, b]


def test_zero_ou_uma_config_e_sempre_noop():
    assert ordenar_configs([], "round_robin") == []
    a = _FakeConfig()
    assert ordenar_configs([a], "performance") == [a]


def test_round_robin_offset_zero_ordem_base():
    a = _FakeConfig(created_at=_t(100))
    b = _FakeConfig(created_at=_t(50))
    c = _FakeConfig(created_at=_t(10))
    resultado = ordenar_configs([c, a, b], "round_robin", rotation_offset=0)
    assert resultado == [a, b, c]  # ordenado por created_at asc, ignora is_default/priority


def test_round_robin_rotaciona_por_offset():
    a = _FakeConfig(created_at=_t(100))
    b = _FakeConfig(created_at=_t(50))
    c = _FakeConfig(created_at=_t(10))
    resultado = ordenar_configs([a, b, c], "round_robin", rotation_offset=1)
    assert resultado == [b, c, a]


def test_round_robin_offset_maior_que_n_faz_wrap():
    a = _FakeConfig(created_at=_t(100))
    b = _FakeConfig(created_at=_t(50))
    resultado = ordenar_configs([a, b], "round_robin", rotation_offset=5)  # 5 % 2 == 1
    assert resultado == [b, a]


def test_round_robin_ignora_is_default_e_priority():
    padrao = _FakeConfig(is_default=True, priority=1, created_at=_t(50))
    outra = _FakeConfig(is_default=False, priority=99, created_at=_t(10))
    resultado = ordenar_configs([padrao, outra], "round_robin", rotation_offset=0)
    assert resultado == [padrao, outra]  # por created_at, não por is_default/priority


def test_performance_prioriza_melhor_score_e_da_chance_a_config_sem_dados():
    """Caso A/B/C: A tem sucesso alto/custo baixo/latência baixa (melhor);
    B tem sucesso baixo/custo alto/latência alta (pior); C não tem nenhuma
    chamada na janela (score neutro) — ranking esperado: A, C, B."""
    a = _FakeConfig(created_at=_t(300))
    b = _FakeConfig(created_at=_t(200))
    c = _FakeConfig(created_at=_t(100))
    stats = {
        str(a.id): {"total_calls": 10, "success_rate": 1.0, "avg_cost_usd": 0.001, "avg_latency_ms": 200},
        str(b.id): {"total_calls": 10, "success_rate": 0.5, "avg_cost_usd": 0.01, "avg_latency_ms": 2000},
        # c sem entrada em `stats` — zero chamadas na janela
    }
    resultado = ordenar_configs([b, c, a], "performance", stats=stats)
    assert resultado == [a, c, b]


def test_performance_todas_sem_dados_cai_no_tiebreak_por_created_at():
    a = _FakeConfig(created_at=_t(100))
    b = _FakeConfig(created_at=_t(50))
    resultado = ordenar_configs([b, a], "performance", stats={})
    assert resultado == [a, b]  # score neutro empatado -> created_at asc


def test_performance_determinismo():
    a = _FakeConfig(created_at=_t(100))
    b = _FakeConfig(created_at=_t(50))
    stats = {
        str(a.id): {"total_calls": 5, "success_rate": 0.9, "avg_cost_usd": 0.002, "avg_latency_ms": 300},
        str(b.id): {"total_calls": 5, "success_rate": 0.9, "avg_cost_usd": 0.002, "avg_latency_ms": 300},
    }
    r1 = ordenar_configs([a, b], "performance", stats=stats)
    r2 = ordenar_configs([a, b], "performance", stats=stats)
    assert r1 == r2  # mesma entrada -> mesma saída, sempre
