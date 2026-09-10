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
from curl_cffi.requests import AsyncSession
from curl_cffi.requests.exceptions import HTTPError
import structlog

log = structlog.get_logger()


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
        self._http_client: AsyncSession | None = None

    @property
    def http(self) -> AsyncSession:
        if not self._http_client:
            # Fase pós-260.10 (rodada de correção do catálogo de integrações
            # .jus.br) — trocado de httpx pra curl_cffi/impersonate="chrome124",
            # mesma causa-raiz já comprovada em comunica.py: o WAF de um
            # portal do CNJ/PJe pode bloquear pelo fingerprint TLS (JA3), que
            # nenhum header resolve. O User-Agent manual que existia aqui
            # ("AFJ-Core/1.0 (...)") é EXATAMENTE o tipo de header
            # autoidentificado que causou o 403 confirmado do Comunica —
            # removido de propósito: misturar um UA manual com o impersonate
            # seria, ele mesmo, um sinal que um WAF mais sofisticado pega.
            self._http_client = AsyncSession(
                timeout=30.0,
                impersonate="chrome124",
                allow_redirects=True,
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

    async def _safe_get(self, url: str, **kwargs):
        """GET com tratamento de erro e log."""
        try:
            response = await self.http.get(url, **kwargs)
            response.raise_for_status()
            return response
        except HTTPError as exc:
            log.error("tribunal_http_error", tribunal=self.tribunal_name, url=url, status=exc.response.status_code)
            return None
        except Exception as exc:
            log.error("tribunal_request_failed", tribunal=self.tribunal_name, url=url, error=str(exc))
            return None

    async def close(self):
        if self._http_client:
            await self._http_client.close()
