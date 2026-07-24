"""Arquitetura de FONTES processuais (Fase 73 — fundação).

Uma `FonteProcessual` é um conector uniforme para dados de processos, cada um
declarando suas `Capability` (descobrir por OAB, detalhar, movimentos, partes).
O `registry` expõe as fontes instanciadas e permite selecioná-las por capability.
Chamadas de rede são envelopadas por um `CircuitBreaker` real (fail-soft).

Este pacote é ADITIVO: nada no caminho vivo de captura o importa ainda — a
adoção (religar `capturar_por_oab`/polling) acontece na Fase 74.
"""
from app.integrations.fontes.base import (
    Capability,
    FonteProcessual,
    ProcessoDescoberto,
)
from app.integrations.fontes.circuit_breaker import CircuitBreaker
from app.integrations.fontes.registry import (
    fontes_com_capability,
    obter_fonte,
    todas_as_fontes,
)

__all__ = [
    "Capability",
    "FonteProcessual",
    "ProcessoDescoberto",
    "CircuitBreaker",
    "fontes_com_capability",
    "obter_fonte",
    "todas_as_fontes",
]
