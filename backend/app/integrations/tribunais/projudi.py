"""Conector PROJUDI — Tribunais de Justiça (TJCE, TJBA, TJGO, TJPA, TJAM, TJRR).

NOTA: PROJUDI é um sistema legado não público. Esta implementação é um placeholder
estruturado que respeita o contrato BaseTribunalClient. A integração real requer
convênio formal com o TJ respectivo e credenciais de acesso autorizadas.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import structlog

from app.integrations.tribunais.base import BaseTribunalClient, MovementData

log = structlog.get_logger()

PROJUDI_TRIBUNAIS: dict[str, str] = {
    "TJCE": "https://projudi.tjce.jus.br",
    "TJBA": "https://projudi.tjba.jus.br",
    "TJGO": "https://projudi.tjgo.jus.br",
    "TJPA": "https://projudi.tjpa.jus.br",
    "TJAM": "https://projudi.tjam.jus.br",
    "TJRR": "https://projudi.tjrr.jus.br",
    "TJAP": "https://projudi.tjap.jus.br",
    "TJAC": "https://projudi.tjac.jus.br",
}


class ProjudiClient(BaseTribunalClient):
    """
    Placeholder estruturado para integração com sistemas PROJUDI.

    Integração real requer:
    - Convênio com o TJ
    - Certificado digital A3 ou credenciais autorizadas
    - Homologação pelo TJCE/TJBA/etc.
    """

    tribunal_name = "projudi"

    def __init__(self, tribunal: str = "TJCE"):
        super().__init__()
        self.tribunal = tribunal.upper()
        self.base_url = PROJUDI_TRIBUNAIS.get(self.tribunal, "")
        self._session_token: Optional[str] = None

    async def authenticate(self) -> bool:
        if not self.base_url:
            log.warning("projudi_tribunal_not_configured", tribunal=self.tribunal)
            return False

        from app.config import settings
        username = getattr(settings, f"PROJUDI_{self.tribunal}_USER", None)
        password = getattr(settings, f"PROJUDI_{self.tribunal}_PASS", None)

        if not username or not password:
            log.warning("projudi_credentials_missing", tribunal=self.tribunal)
            return False

        log.info("projudi_auth_placeholder", tribunal=self.tribunal,
                 note="Integração real requer convênio com o TJ")
        return False

    async def fetch_movements(
        self,
        numero_cnj: str,
        since: Optional[datetime] = None,
    ) -> list[MovementData]:
        authenticated = await self.authenticate()
        if not authenticated:
            return []
        return []

    async def search_by_oab(self, oab: str, uf: str) -> list[str]:
        authenticated = await self.authenticate()
        if not authenticated:
            return []
        return []
