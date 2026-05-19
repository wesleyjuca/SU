"""
Contrato base para todos os conectores de tribunal.
Cada conector respeita: LGPD, autenticação oficial, logs completos.

NUNCA:
- Burlar autenticação
- Acessar dados sem autorização do usuário
- Executar protocolos automaticamente
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import httpx
import structlog

log = structlog.get_logger()

CIRCUIT_BREAKER_FAILURES = 3
CIRCUIT_BREAKER_TIMEOUT_SECONDS = 1800  # 30 minutos


@dataclass
class MovementData:
    data: datetime
    descricao: str
    tipo: Optional[str] = None
    documento_url: Optional[str] = None
    raw_data: dict = None

    def to_dict(self) -> dict:
        return {
            "data": self.data.isoformat() if self.data else None,
            "descricao": self.descricao,
            "tipo": self.tipo,
            "documento_url": self.documento_url,
        }


class BaseTribunalClient(ABC):
    tribunal_name: str = "base"
    base_url: str = ""

    def __init__(self):
        self._http_client: httpx.AsyncClient | None = None

    @property
    def http(self) -> httpx.AsyncClient:
        if not self._http_client:
            self._http_client = httpx.AsyncClient(
                timeout=30.0,
                headers={"User-Agent": "AFJ-Core/1.0 (Sistema interno de escritório de advocacia)"},
                follow_redirects=True,
            )
        return self._http_client

    @abstractmethod
    async def authenticate(self) -> bool:
        """Autentica no sistema do tribunal. Retorna True se bem-sucedido."""
        ...

    @abstractmethod
    async def fetch_movements(
        self,
        numero_cnj: str,
        since: Optional[datetime] = None,
    ) -> list[MovementData]:
        """Retorna andamentos do processo desde a data informada."""
        ...

    @abstractmethod
    async def search_by_oab(self, oab: str, uf: str) -> list[str]:
        """Retorna lista de números CNJ de processos vinculados à OAB."""
        ...

    async def _safe_get(self, url: str, **kwargs) -> httpx.Response | None:
        """GET com tratamento de erro e log."""
        try:
            response = await self.http.get(url, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            log.error("tribunal_http_error", tribunal=self.tribunal_name, url=url, status=exc.response.status_code)
            return None
        except Exception as exc:
            log.error("tribunal_request_failed", tribunal=self.tribunal_name, url=url, error=str(exc))
            return None

    async def close(self):
        if self._http_client:
            await self._http_client.aclose()
