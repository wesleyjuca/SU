"""Cálculo de prazos processuais (dias úteis, feriados forenses, recesso).

Puro Python, determinístico e sem I/O — auditável e testável isoladamente.
Regras (CPC/2015):
- Art. 219: prazos processuais em DIAS ÚTEIS (default); materiais em dias corridos.
- Art. 224: exclui o dia do começo, inclui o do vencimento; a contagem inicia no
  1º dia útil seguinte à intimação; se o termo final cair em dia sem expediente,
  prorroga-se para o próximo dia útil.
- Art. 220: recesso forense de 20/12 a 20/01 (dias não úteis).

Feriados estaduais/municipais forenses variam por comarca — passe-os em
`extra_feriados` (lista de date) conforme configuração do escritório.
"""
from __future__ import annotations
from datetime import date, timedelta

# Feriados nacionais fixos (mês, dia)
_FIXOS = [(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (12, 25)]


def pascoa(ano: int) -> date:
    """Domingo de Páscoa (algoritmo de Gauss/Meeus para o calendário gregoriano)."""
    a = ano % 19
    b = ano // 100
    c = ano % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    ll = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ll) // 451
    mes = (h + ll - 7 * m + 114) // 31
    dia = ((h + ll - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)


def feriados_nacionais(ano: int) -> set[date]:
    """Feriados nacionais fixos + móveis derivados da Páscoa."""
    p = pascoa(ano)
    feriados = {date(ano, mes, dia) for (mes, dia) in _FIXOS}
    feriados.add(p - timedelta(days=48))  # Carnaval (segunda)
    feriados.add(p - timedelta(days=47))  # Carnaval (terça)
    feriados.add(p - timedelta(days=2))   # Sexta-feira Santa
    feriados.add(p + timedelta(days=60))  # Corpus Christi
    return feriados


def em_recesso_forense(d: date) -> bool:
    """Recesso forense: 20/12 a 31/12 e 01/01 a 20/01 (CPC art. 220)."""
    return (d.month == 12 and d.day >= 20) or (d.month == 1 and d.day <= 20)


def is_dia_util(d: date, extra_feriados: set[date] | None = None, incluir_recesso: bool = True) -> bool:
    """True se `d` é dia com expediente forense."""
    if d.weekday() >= 5:  # sábado(5)/domingo(6)
        return False
    if d in feriados_nacionais(d.year):
        return False
    if incluir_recesso and em_recesso_forense(d):
        return False
    if extra_feriados and d in extra_feriados:
        return False
    return True


def proximo_dia_util(d: date, extra_feriados: set[date] | None = None, incluir_recesso: bool = True) -> date:
    """Primeiro dia útil >= d."""
    atual = d
    while not is_dia_util(atual, extra_feriados, incluir_recesso):
        atual += timedelta(days=1)
    return atual


def _parse_feriados(extra_feriados) -> set[date]:
    out: set[date] = set()
    for f in extra_feriados or []:
        if isinstance(f, date):
            out.add(f)
        elif isinstance(f, str):
            try:
                out.add(date.fromisoformat(f[:10]))
            except ValueError:
                pass
    return out


def calcular_prazo(
    data_intimacao: date,
    dias: int,
    dias_uteis: bool = True,
    extra_feriados=None,
    incluir_recesso: bool = True,
) -> dict:
    """Calcula o termo final de um prazo a partir da data de intimação.

    Retorna {termo_inicial, data_prazo, feriados_no_periodo, dias, dias_uteis}.
    - termo_inicial: 1º dia útil seguinte à intimação (art. 224 §3).
    - conta `dias` (úteis pulando não-úteis; ou corridos) a partir do termo inicial.
    - se o termo final cair em dia sem expediente, prorroga (art. 224 §1).
    """
    if dias < 1:
        raise ValueError("dias deve ser >= 1")
    fer = _parse_feriados(extra_feriados)

    # Termo inicial: primeiro dia útil APÓS a intimação.
    termo_inicial = proximo_dia_util(data_intimacao + timedelta(days=1), fer, incluir_recesso)

    feriados_no_periodo = 0
    if dias_uteis:
        # O termo inicial conta como o 1º dia; avança até completar `dias` úteis.
        atual = termo_inicial
        contados = 1
        while contados < dias:
            atual += timedelta(days=1)
            if is_dia_util(atual, fer, incluir_recesso):
                contados += 1
            else:
                feriados_no_periodo += 1
        data_prazo = atual
    else:
        # Dias corridos; prorroga o vencimento se cair em dia sem expediente.
        data_prazo = proximo_dia_util(termo_inicial + timedelta(days=dias - 1), fer, incluir_recesso)

    return {
        "termo_inicial": termo_inicial,
        "data_prazo": data_prazo,
        "feriados_no_periodo": feriados_no_periodo,
        "dias": dias,
        "dias_uteis": dias_uteis,
    }
