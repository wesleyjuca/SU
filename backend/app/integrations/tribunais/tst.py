"""Conector TST — Tribunal Superior do Trabalho.

Portal de consulta: https://pje.tst.jus.br/consultaprocessual/
API DataJud CNJ disponível via CNJDataJudClient(tribunal='TST').
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import structlog

from app.integrations.tribunais.base import BaseTribunalClient, MovementData

log = structlog.get_logger()

TST_PJE_URL = "https://pje.tst.jus.br/consultaprocessual/"


class TSTClient(BaseTribunalClient):
    """
    Conector para o Tribunal Superior do Trabalho.

    O TST usa o sistema PJe (Processo Judicial Eletrônico).
    Estratégia preferencial: CNJDataJudClient(tribunal='TST') com API DataJud.

    Para processos trabalhistas (TRT), use o PJeClient configurado para o TRT correspondente.
    """

    tribunal_name = "tst"
    base_url = "https://pje.tst.jus.br"

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
            client = CNJDataJudClient(tribunal="TST")
            client._api_key = cnj_key
            client._authenticated = True
            return await client.fetch_movements(numero_cnj, since)

        log.info("tst_datajud_fallback", numero_cnj=numero_cnj,
                 note="Configure CNJ_API_KEY para acesso via DataJud")
        return []

    async def search_by_oab(self, oab: str, uf: str) -> list[str]:
        from app.config import settings
        cnj_key = getattr(settings, "CNJ_API_KEY", None)
        if cnj_key:
            from app.integrations.tribunais.cnj import CNJDataJudClient
            client = CNJDataJudClient(tribunal="TST")
            client._api_key = cnj_key
            client._authenticated = True
            return await client.search_by_oab(oab, uf)
        return []
