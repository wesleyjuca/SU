"""Conector STF — Supremo Tribunal Federal.

Portal de consulta processual: https://portal.stf.jus.br/processos/
API DataJud CNJ disponível para o STF via CNJDataJudClient(tribunal='STF').
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import structlog

from app.integrations.tribunais.base import BaseTribunalClient, MovementData

log = structlog.get_logger()


class STFClient(BaseTribunalClient):
    """
    Conector para o Supremo Tribunal Federal.

    Estratégia preferencial: usar CNJDataJudClient(tribunal='STF') para consultas
    via API DataJud (com CNJ_API_KEY).

    Consulta pública disponível em: https://portal.stf.jus.br/processos/
    Não requer autenticação para acesso básico.
    """

    tribunal_name = "stf"
    base_url = "https://portal.stf.jus.br"

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
            client = CNJDataJudClient(tribunal="STF")
            client._api_key = cnj_key
            client._authenticated = True
            return await client.fetch_movements(numero_cnj, since)

        log.info("stf_datajud_fallback", numero_cnj=numero_cnj,
                 note="Configure CNJ_API_KEY para acesso via DataJud")
        return []

    async def search_by_oab(self, oab: str, uf: str) -> list[str]:
        from app.config import settings
        cnj_key = getattr(settings, "CNJ_API_KEY", None)
        if cnj_key:
            from app.integrations.tribunais.cnj import CNJDataJudClient
            client = CNJDataJudClient(tribunal="STF")
            client._api_key = cnj_key
            client._authenticated = True
            return await client.search_by_oab(oab, uf)
        return []
