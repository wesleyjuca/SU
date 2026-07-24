"""Registro das fontes processuais (Fase 73).

Ponto único para obter fontes por nome ou por capability. As instâncias são
criadas preguiçosamente na primeira consulta (sem custo no import do pacote).
A adoção pelos orquestradores (`capturar_por_oab`, polling) acontece na Fase 74.
"""
from __future__ import annotations

from app.integrations.fontes.base import Capability, FonteProcessual

_FONTES: dict[str, FonteProcessual] = {}


def _bootstrap() -> None:
    if _FONTES:
        return
    from app.integrations.fontes.comunica_fonte import ComunicaFonte
    from app.integrations.fontes.datajud_fonte import DataJudFonte
    for fonte in (ComunicaFonte(), DataJudFonte()):
        _FONTES[fonte.nome] = fonte


def obter_fonte(nome: str) -> FonteProcessual | None:
    _bootstrap()
    return _FONTES.get(nome)


def todas_as_fontes() -> list[FonteProcessual]:
    _bootstrap()
    return list(_FONTES.values())


def fontes_com_capability(cap: Capability) -> list[FonteProcessual]:
    """Fontes que declaram suportar `cap` (ex: escolher quem descobre por OAB)."""
    _bootstrap()
    return [f for f in _FONTES.values() if f.suporta(cap)]
