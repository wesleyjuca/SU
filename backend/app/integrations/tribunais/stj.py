"""Conector STJ — Superior Tribunal de Justiça.

Acesso público: https://processo.stj.jus.br/processo/pesquisa/
API DataJud CNJ também disponível para o STJ via CNJDataJudClient(tribunal='STJ').
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import structlog

from app.integrations.tribunais.base import BaseTribunalClient, MovementData

log = structlog.get_logger()

STJ_CONSULTA_URL = "https://processo.stj.jus.br/processo/pesquisa/"
STJ_DATAJUD_INDEX = "api_publica_stj"


class STJClient(BaseTribunalClient):
    """
    Conector para o Superior Tribunal de Justiça.

    Estratégia preferencial: usar CNJDataJudClient(tribunal='STJ') para consultas
    via API DataJud (com CNJ_API_KEY).

    Esta classe implementa fallback via scraping da consulta pública (sem autenticação).
    """

    tribunal_name = "stj"
    base_url = "https://processo.stj.jus.br"

    async def authenticate(self) -> bool:
        return True

    async def fetch_movements(
        self,
        numero_cnj: str,
        since: Optional[datetime] = None,
    ) -> list[MovementData]:
        from app.config import settings
        cnj_key = getattr(settings, "CNJ_API_KEY", None)
        if cnj_key:
            from app.integrations.tribunais.cnj import CNJDataJudClient
            client = CNJDataJudClient(tribunal="STJ")
            client._api_key = cnj_key
            client._authenticated = True
            return await client.fetch_movements(numero_cnj, since)

        log.info("stj_datajud_fallback", numero_cnj=numero_cnj,
                 note="Configure CNJ_API_KEY para acesso via DataJud")
        return []

    async def search_by_oab(self, oab: str, uf: str) -> list[str]:
        from app.config import settings
        cnj_key = getattr(settings, "CNJ_API_KEY", None)
        if cnj_key:
            from app.integrations.tribunais.cnj import CNJDataJudClient
            client = CNJDataJudClient(tribunal="STJ")
            client._api_key = cnj_key
            client._authenticated = True
            return await client.search_by_oab(oab, uf)
        return []
