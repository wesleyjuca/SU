"""Testes do motor de prazos processuais (app/utils/prazo.py)."""
from datetime import date
from app.utils.prazo import (
    pascoa, feriados_nacionais, is_dia_util, em_recesso_forense, calcular_prazo,
)


def test_pascoa_conhecida():
    assert pascoa(2024) == date(2024, 3, 31)
    assert pascoa(2025) == date(2025, 4, 20)
    assert pascoa(2026) == date(2026, 4, 5)


def test_feriados_moveis():
    f = feriados_nacionais(2025)
    assert date(2025, 3, 3) in f    # Carnaval segunda (Páscoa 20/04 − 48)
    assert date(2025, 3, 4) in f    # Carnaval terça
    assert date(2025, 4, 18) in f   # Sexta-feira Santa (−2)
    assert date(2025, 6, 19) in f   # Corpus Christi (+60)
    # Fixos
    assert date(2025, 9, 7) in f and date(2025, 12, 25) in f


def test_recesso_forense():
    assert em_recesso_forense(date(2025, 12, 20))
    assert em_recesso_forense(date(2026, 1, 20))
    assert not em_recesso_forense(date(2026, 1, 21))
    assert not em_recesso_forense(date(2025, 12, 19))


def test_dia_util_basico():
    assert not is_dia_util(date(2025, 5, 3))   # sábado
    assert not is_dia_util(date(2025, 5, 4))   # domingo
    assert not is_dia_util(date(2025, 5, 1))   # feriado (Dia do Trabalho)
    assert is_dia_util(date(2025, 5, 5))       # segunda comum


def test_15_dias_uteis_intimacao_sexta():
    # Intimação sexta 09/05/2025 → termo inicial = próximo dia útil = 12/05 (seg).
    # 15 dias úteis a partir de 12/05, sem feriados no intervalo → 30/05/2025 (sexta).
    r = calcular_prazo(date(2025, 5, 9), 15, dias_uteis=True)
    assert r["termo_inicial"] == date(2025, 5, 12)
    assert r["data_prazo"] == date(2025, 5, 30)
    assert is_dia_util(r["data_prazo"])


def test_prorroga_quando_cai_em_dia_nao_util():
    # Dias corridos: 5 dias a partir de uma quarta que caia o fim em fim de semana → prorroga.
    r = calcular_prazo(date(2025, 5, 7), 3, dias_uteis=False)  # termo inicial 08/05 (qui)
    # 3 corridos: 08,09,10 → 10/05 é sábado → prorroga p/ 12/05 (seg)
    assert r["termo_inicial"] == date(2025, 5, 8)
    assert r["data_prazo"] == date(2025, 5, 12)


def test_recesso_suspende_contagem():
    # Intimação 15/12/2025 (seg). Termo inicial 16/12. A contagem de dias úteis
    # deve pular o recesso (20/12–20/01) e o resultado cair depois de 20/01/2026.
    r = calcular_prazo(date(2025, 12, 15), 10, dias_uteis=True)
    assert r["data_prazo"] > date(2026, 1, 20)
    assert is_dia_util(r["data_prazo"])


def test_dias_corridos_vs_uteis_diferem():
    corridos = calcular_prazo(date(2025, 6, 2), 10, dias_uteis=False)["data_prazo"]
    uteis = calcular_prazo(date(2025, 6, 2), 10, dias_uteis=True)["data_prazo"]
    assert uteis > corridos  # úteis sempre >= corridos (pula fins de semana/feriados)


def test_feriado_extra_do_tenant():
    # Sem feriado extra
    base = calcular_prazo(date(2025, 5, 5), 5, dias_uteis=True)["data_prazo"]
    # Com um feriado local no meio do intervalo, o prazo estende +1 dia útil
    com_extra = calcular_prazo(
        date(2025, 5, 5), 5, dias_uteis=True, extra_feriados=["2025-05-08"]
    )["data_prazo"]
    assert com_extra > base
