"""Fase 82 — ring buffer de logs do Cérebro (lógica pura)."""
from app.core import log_buffer as lb


def _reset():
    lb._BUF.clear()


def test_captura_ordena_recentes_primeiro():
    _reset()
    lb.capture_processor(None, "info", {"event": "a", "level": "info", "timestamp": "2026-01-01T00:00:00", "x": 1})
    lb.capture_processor(None, "warning", {"event": "b", "level": "warning", "timestamp": "2026-01-01T00:00:01"})
    lb.capture_processor(None, "error", {"event": "c", "level": "error"})
    s = lb.snapshot(limit=10)
    assert [e["event"] for e in s] == ["c", "b", "a"]
    # extra captura campos fora dos meta, como string
    assert s[2]["extra"] == {"x": "1"}


def test_filtro_por_nivel_minimo():
    _reset()
    lb.capture_processor(None, "info", {"event": "i", "level": "info"})
    lb.capture_processor(None, "warning", {"event": "w", "level": "warning"})
    lb.capture_processor(None, "error", {"event": "e", "level": "error"})
    assert [x["event"] for x in lb.snapshot(level="warning")] == ["e", "w"]
    assert [x["event"] for x in lb.snapshot(level="error")] == ["e"]
    assert len(lb.snapshot(level="debug")) == 3


def test_limit_e_trim_maxlen():
    _reset()
    for i in range(600):
        lb.capture_processor(None, "info", {"event": str(i), "level": "info"})
    assert len(list(lb._BUF)) == lb._MAX == 500      # deque limitado
    assert len(lb.snapshot(limit=5)) == 5
    assert lb.snapshot(limit=1)[0]["event"] == "599"  # mais recente


def test_capture_nunca_levanta():
    _reset()
    # event_dict estranho não deve quebrar o logging
    assert lb.capture_processor(None, "info", {"event": object()}) is not None
