"""Conector CNJ DataJud — API pública documentada do CNJ ElasticSearch."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import structlog

from app.integrations.tribunais.base import BaseTribunalClient, MovementData

log = structlog.get_logger()

DATAJUD_BASE = "https://api-publica.datajud.cnj.jus.br"

TRIBUNAL_INDICES: dict[str, str] = {
    "TJCE": "api_publica_tjce",
    "TJSP": "api_publica_tjsp",
    "TJBA": "api_publica_tjba",
    "TJRJ": "api_publica_tjrj",
    "TJMG": "api_publica_tjmg",
    "TJRS": "api_publica_tjrs",
    "TJPE": "api_publica_tjpe",
    "TJPR": "api_publica_tjpr",
    "TJSC": "api_publica_tjsc",
    "TJGO": "api_publica_tjgo",
    "TJDF": "api_publica_tjdft",
    "STJ": "api_publica_stj",
    "STF": "api_publica_stf",
    "TST": "api_publica_tst",
    "TRF1": "api_publica_trf1",
    "TRF2": "api_publica_trf2",
    "TRF3": "api_publica_trf3",
    "TRF4": "api_publica_trf4",
    "TRF5": "api_publica_trf5",
}


class CNJDataJudClient(BaseTribunalClient):
    """
    Conector para a API pública DataJud do CNJ.
    Documentação: https://datajud-wiki.cnj.jus.br/
    Requer: CNJ_API_KEY (variável de ambiente)
    """

    tribunal_name = "datajud_cnj"

    def __init__(self, tribunal: str = "TJCE"):
        super().__init__()
        self.tribunal = tribunal.upper()
        self._api_key: Optional[str] = None
        self._authenticated = False

    @property
    def _index(self) -> str:
        return TRIBUNAL_INDICES.get(self.tribunal, f"api_publica_{self.tribunal.lower()}")

    @property
    def _search_url(self) -> str:
        return f"{DATAJUD_BASE}/{self._index}/_search"

    async def authenticate(self) -> bool:
        from app.config import settings
        api_key = getattr(settings, "CNJ_API_KEY", None)
        if not api_key:
            log.warning("cnj_api_key_missing", tribunal=self.tribunal)
            return False
        self._api_key = api_key
        self._authenticated = True
        return True

    async def fetch_movements(
        self,
        numero_cnj: str,
        since: Optional[datetime] = None,
    ) -> list[MovementData]:
        if not self._authenticated:
            await self.authenticate()
        if not self._api_key:
            return []

        numero_clean = numero_cnj.replace(".", "").replace("-", "")

        query: dict = {
            "query": {
                "bool": {
                    "must": [{"match": {"numeroProcesso": numero_clean}}]
                }
            },
            "_source": ["movimentos", "dataAjuizamento", "tribunal"],
            "size": 1,
        }

        headers = {"Authorization": f"APIKey {self._api_key}", "Content-Type": "application/json"}

        try:
            response = await self.http.post(self._search_url, json=query, headers=headers)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            log.error("datajud_fetch_failed", numero_cnj=numero_cnj, error=str(exc))
            return []

        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            return []

        movements: list[MovementData] = []
        source = hits[0].get("_source", {})
        for mov in source.get("movimentos", []):
            data_str = mov.get("dataHora", "")
            try:
                data_dt = datetime.fromisoformat(data_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                data_dt = datetime.utcnow()

            if since and data_dt < since:
                continue

            codigo = mov.get("codigo", "")
            nome = mov.get("nome", "Movimentação sem descrição")
            complemento = mov.get("complemento", "")
            descricao = f"{nome}: {complemento}".strip(": ") if complemento else nome

            movements.append(
                MovementData(
                    data=data_dt,
                    descricao=descricao,
                    tipo=str(codigo) if codigo else None,
                    raw_data=mov,
                )
            )

        movements.sort(key=lambda m: m.data, reverse=True)
        return movements

    async def search_by_oab(self, oab: str, uf: str) -> list[str]:
        if not self._authenticated:
            await self.authenticate()
        if not self._api_key:
            return []

        query = {
            "query": {
                "nested": {
                    "path": "partes",
                    "query": {
                        "nested": {
                            "path": "partes.advogados",
                            "query": {
                                "bool": {
                                    "must": [
                                        {"match": {"partes.advogados.numeroOAB": oab}},
                                        {"match": {"partes.advogados.ufOAB": uf.upper()}},
                                    ]
                                }
                            },
                        }
                    },
                }
            },
            "_source": ["numeroProcesso"],
            "size": 100,
        }

        headers = {"Authorization": f"APIKey {self._api_key}", "Content-Type": "application/json"}

        try:
            response = await self.http.post(self._search_url, json=query, headers=headers)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            log.error("datajud_oab_search_failed", oab=oab, uf=uf, error=str(exc))
            return []

        hits = data.get("hits", {}).get("hits", [])
        return [h.get("_source", {}).get("numeroProcesso", "") for h in hits if h.get("_source", {}).get("numeroProcesso")]
