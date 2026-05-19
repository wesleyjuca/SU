"""Conector e-Proc — TRF1, TRF4, TRF5 e tribunais estaduais que adotaram o sistema.

NOTA: e-Proc é um sistema do Conselho da Justiça Federal (CJF). Integração via
Serviço SOAP/REST requer certificado digital e autorização do CJF.
Consulta pública disponível em: https://eproc1g.trf1.jus.br/eproc/externo_controlador.php
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import structlog

from app.integrations.tribunais.base import BaseTribunalClient, MovementData

log = structlog.get_logger()

EPROC_URLS: dict[str, str] = {
    "TRF1": "https://eproc1g.trf1.jus.br/eproc",
    "TRF4": "https://eproc.trf4.jus.br/eproc",
    "TRF5": "https://eproc.trf5.jus.br/eproc",
    "TJRS": "https://eproc.tjrs.jus.br/eproc",
    "TJSC": "https://eproc.tjsc.jus.br/eproc",
}

EPROC_PUBLIC_QUERY = "{base}/externo_controlador.php?acao=processo_seleciona_publica&num_processo={numero}"


class EProcClient(BaseTribunalClient):
    """
    Placeholder estruturado para integração com e-Proc (CJF).

    Integração real requer:
    - Certificado digital (A1 ou A3) emitido para o escritório
    - Cadastro no e-Proc do TRF correspondente
    - Autorização do CJF para acesso automatizado
    """

    tribunal_name = "eproc"

    def __init__(self, tribunal: str = "TRF5"):
        super().__init__()
        self.tribunal = tribunal.upper()
        self.base_url = EPROC_URLS.get(self.tribunal, "")

    async def authenticate(self) -> bool:
        if not self.base_url:
            log.warning("eproc_tribunal_not_configured", tribunal=self.tribunal)
            return False

        from app.config import settings
        cert_path = getattr(settings, f"EPROC_{self.tribunal}_CERT_PATH", None)

        if not cert_path:
            log.warning("eproc_cert_missing", tribunal=self.tribunal)
            return False

        log.info("eproc_auth_placeholder", tribunal=self.tribunal,
                 note="Integração real requer certificado digital CJF")
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
