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
