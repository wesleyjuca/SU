"""Seleção de fontes CREDENCIADAS por escritório (Fase 80).

As fontes credenciadas (PDPJ, Escavador, Judit) vivem fora do registry global
porque dependem de credencial por-tenant. Este módulo escolhe qual usar para uma
dada capability, na ordem de preferência, retornando a primeira que o escritório
conectou (opt-in). Nenhuma conectada → None (o chamador degrada graciosamente).
"""
from __future__ import annotations

from typing import Any

# Ordem de preferência para PARTES: oficial (PDPJ) antes dos agregadores.
_ORDEM_PARTES = ("pdpj", "escavador", "judit", "jusbrasil")

# Fase pós-262 — ordem para DESCOBERTA por OAB: só Escavador e Judit
# implementam essa capability hoje (PDPJ não tem esse tipo de busca;
# Jusbrasil tem código escrito, mas contra um endpoint confirmadamente
# desatualizado/incompatível com a API real — corrigi-lo não foi pedido
# nesta fase, fica de fora até ser revisitado).
_ORDEM_DESCOBERTA_OAB = ("escavador", "judit")


async def fonte_partes_credenciada(db, tenant_id: Any):
    """Primeira fonte credenciada com PARTES conectada
    (pdpj→escavador→judit→jusbrasil)."""
    from app.integrations.fontes import pdpj_fonte, escavador_fonte, judit_fonte, jusbrasil_fonte
    mods = {"pdpj": pdpj_fonte, "escavador": escavador_fonte, "judit": judit_fonte,
            "jusbrasil": jusbrasil_fonte}
    for nome in _ORDEM_PARTES:
        fonte = await mods[nome].para_tenant(db, tenant_id)
        if fonte is not None:
            return fonte
    return None


async def fontes_descoberta_credenciadas(db, tenant_id: Any) -> list:
    """Fase pós-262 — TODAS as fontes credenciadas com DESCOBRIR_OAB
    conectadas (não só a primeira, diferente de `fonte_partes_credenciada`
    acima): pra descoberta de processo por OAB, mais fontes = mais
    cobertura, não substituição — cada uma pode achar processos que a
    outra não tem. Lista vazia quando nenhuma estiver configurada (o
    chamador continua funcionando só com o Comunica público)."""
    from app.integrations.fontes import escavador_fonte, judit_fonte
    mods = {"escavador": escavador_fonte, "judit": judit_fonte}
    out = []
    for nome in _ORDEM_DESCOBERTA_OAB:
        fonte = await mods[nome].para_tenant(db, tenant_id)
        if fonte is not None:
            out.append(fonte)
    return out
