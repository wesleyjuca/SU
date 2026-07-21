"""Fase 72 — testes do importador único de movimentos (dedup canônico)."""
from datetime import datetime, timezone

from app.services.movements_import import dedup_hash, parse_datajud_movimentos


def test_dedup_hash_normaliza_espacos_e_caixa():
    dt = datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)
    a = dedup_hash(dt, "Intime-se  a parte   autora")
    b = dedup_hash(dt, "intime-se a parte autora")
    assert a == b  # espaços colapsados + caixa baixa → mesmo hash


def test_dedup_hash_muda_com_dia_ou_texto():
    d1 = datetime(2026, 7, 20, tzinfo=timezone.utc)
    d2 = datetime(2026, 7, 21, tzinfo=timezone.utc)
    assert dedup_hash(d1, "Despacho") != dedup_hash(d2, "Despacho")
    assert dedup_hash(d1, "Despacho") != dedup_hash(d1, "Sentença")
    # Mesmo dia com horas diferentes → MESMO hash (dedup é por dia)
    d1b = datetime(2026, 7, 20, 23, 59, tzinfo=timezone.utc)
    assert dedup_hash(d1, "Despacho") == dedup_hash(d1b, "Despacho")


def test_parse_datajud_movimentos():
    dados = {"movimentos": [
        {"nome": "Distribuição", "dataHora": "2026-07-01T10:00:00Z"},
        {"nome": "", "dataHora": "2026-07-02T10:00:00Z"},          # sem nome → ignora
        {"nome": "Conclusão", "dataHora": "data-inválida"},         # data ruim → now()
    ]}
    out = parse_datajud_movimentos(dados)
    assert len(out) == 2
    assert out[0].descricao == "Distribuição"
    assert out[0].data.year == 2026 and out[0].data.month == 7
    assert out[1].descricao == "Conclusão" and out[1].data is not None


def test_parse_datajud_respeita_limite():
    dados = {"movimentos": [{"nome": f"Mov {i}", "dataHora": "2026-01-01T00:00:00Z"} for i in range(300)]}
    assert len(parse_datajud_movimentos(dados, limite=200)) == 200
