"""Conector PJe — Processo Judicial Eletrônico."""
from datetime import datetime
from typing import Optional
import httpx
import structlog

from app.integrations.tribunais.base import BaseTribunalClient, MovementData

log = structlog.get_logger()

PJE_BASE_URLS = {
    "TJCE": "https://pje.tjce.jus.br/pje",
    "TJBA": "https://pje.tjba.jus.br/pje",
    "TJPE": "https://pje.tjpe.jus.br/pje",
    "TJMA": "https://pje.tjma.jus.br/pje",
    "TJPI": "https://pje.tjpi.jus.br/pje",
    "TRT7": "https://pje.trt7.jus.br/pje",
    "TRT16": "https://pje.trt16.jus.br/pje",
}


class PJeClient(BaseTribunalClient):
    """Cliente para o sistema PJe."""

    def __init__(self, tribunal: str, username: Optional[str] = None, password: Optional[str] = None):
        self.tribunal = tribunal.upper()
        self.username = username
        self.password = password
        self.base_url = PJE_BASE_URLS.get(self.tribunal, "")
        self._session_token: Optional[str] = None

    async def authenticate(self) -> bool:
        if not self.base_url or not self.username or not self.password:
            log.warning("pje_no_credentials", tribunal=self.tribunal)
            return False
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                res = await client.post(
                    f"{self.base_url}/login",
                    data={"username": self.username, "password": self.password},
                    follow_redirects=True,
                )
                if res.status_code in (200, 302):
                    self._session_token = res.cookies.get("JSESSIONID")
                    return bool(self._session_token)
        except Exception as exc:
            log.error("pje_auth_failed", tribunal=self.tribunal, error=str(exc))
        return False

    async def fetch_movements(self, numero_cnj: str, since: datetime) -> list[MovementData]:
        if not self._session_token:
            await self.authenticate()
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                res = await client.get(
                    f"{self.base_url}/api/v1/processo/{numero_cnj}/movimentos",
                    cookies={"JSESSIONID": self._session_token or ""},
                    params={"dataInicio": since.strftime("%Y-%m-%d")},
                )
                if res.status_code == 200:
                    data = res.json()
                    return self._parse_movements(data)
        except Exception as exc:
            log.error("pje_fetch_failed", numero_cnj=numero_cnj, error=str(exc))
        return []

    async def search_by_oab(self, oab: str, uf: str) -> list[str]:
        if not self._session_token:
            await self.authenticate()
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                res = await client.get(
                    f"{self.base_url}/api/v1/processos",
                    cookies={"JSESSIONID": self._session_token or ""},
                    params={"oab": oab, "uf": uf},
                )
                if res.status_code == 200:
                    data = res.json()
                    return [p.get("numero") for p in data.get("processos", []) if p.get("numero")]
        except Exception as exc:
            log.error("pje_search_failed", oab=oab, error=str(exc))
        return []

    def _parse_movements(self, data: dict) -> list[MovementData]:
        movements = []
        for item in data.get("movimentos", []):
            try:
                movements.append(MovementData(
                    data_movimento=datetime.fromisoformat(item["dataMovimento"]),
                    descricao=item.get("descricao", ""),
                    tipo=item.get("tipo"),
                    documento_url=item.get("documentoUrl"),
                    raw_html=item.get("html"),
                ))
            except (KeyError, ValueError):
                continue
        return movements
