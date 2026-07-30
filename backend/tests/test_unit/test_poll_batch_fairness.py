"""Fase 116 — cap por tenant do lote de polling (per_tenant_poll_cap).

A parte comportamental (que a query particionada de fato distribui o lote
de forma justa entre tenants) foi validada empiricamente contra um Postgres
real numa simulação de volume (2 escritórios, ~7.300 processos, um deles com
prazos deliberadamente mais atrasados que o outro): antes da correção, o
tenant com prazos mais urgentes monopolizava 50/50 do lote; depois, com o
cap por tenant aplicado, a divisão ficou 25/25 — nenhum tenant fica sem
fatia do polling. Este teste cobre a fórmula pura (ceil division com piso 1)
que decide esse cap, sem depender de banco real (process_agent.py não
importa app.dependencies, roda local sem stubs).
"""
from app.agents.process.process_agent import per_tenant_poll_cap


def test_cap_divide_igualmente_quando_exato():
    assert per_tenant_poll_cap(batch_size=50, num_tenants=2) == 25


def test_cap_arredonda_para_cima_quando_nao_divide_exato():
    # 50/3 = 16.67 -> arredonda pra 17, nunca deixa resto sem cobertura
    assert per_tenant_poll_cap(batch_size=50, num_tenants=3) == 17


def test_cap_com_um_tenant_so_e_o_batch_inteiro():
    assert per_tenant_poll_cap(batch_size=50, num_tenants=1) == 50


def test_cap_nunca_fica_abaixo_de_1():
    assert per_tenant_poll_cap(batch_size=5, num_tenants=100) == 1


def test_cap_com_zero_tenants_nao_quebra_nem_zera_o_lote():
    # num_tenants=0 é o caso degenerado (nenhum processo monitorado) — cai
    # no batch_size inteiro em vez de ZeroDivisionError ou cap=0.
    assert per_tenant_poll_cap(batch_size=50, num_tenants=0) == 50
