"""Conector CNJ DataJud — API pública documentada do CNJ ElasticSearch."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import structlog

from app.integrations.tribunais.base import BaseTribunalClient, MovementData

log = structlog.get_logger()

DATAJUD_BASE = "https://api-publica.datajud.cnj.jus.br"

TRIBUNAL_INDICES: dict[str, str] = {
    # ─── Tribunais Estaduais ──────────────────────────────────────────────────
    "TJAC": "api_publica_tjac",
    "TJAL": "api_publica_tjal",
    "TJAM": "api_publica_tjam",
    "TJAP": "api_publica_tjap",
    "TJBA": "api_publica_tjba",
    "TJCE": "api_publica_tjce",
    "TJDF": "api_publica_tjdft",
    "TJES": "api_publica_tjes",
    "TJGO": "api_publica_tjgo",
    "TJMA": "api_publica_tjma",
    "TJMG": "api_publica_tjmg",
    "TJMS": "api_publica_tjms",
    "TJMT": "api_publica_tjmt",
    "TJPA": "api_publica_tjpa",
    "TJPB": "api_publica_tjpb",
    "TJPE": "api_publica_tjpe",
    "TJPI": "api_publica_tjpi",
    "TJPR": "api_publica_tjpr",
    "TJRJ": "api_publica_tjrj",
    "TJRN": "api_publica_tjrn",
    "TJRO": "api_publica_tjro",
    "TJRR": "api_publica_tjrr",
    "TJRS": "api_publica_tjrs",
    "TJSC": "api_publica_tjsc",
    "TJSE": "api_publica_tjse",
    "TJSP": "api_publica_tjsp",
    "TJTO": "api_publica_tjto",
    # ─── Tribunais Superiores ─────────────────────────────────────────────────
    "STJ": "api_publica_stj",
    "STF": "api_publica_stf",
    "TST": "api_publica_tst",
    "TSE": "api_publica_tse",
    "STM": "api_publica_stm",
    # ─── Tribunais Regionais Federais ─────────────────────────────────────────
    "TRF1": "api_publica_trf1",
    "TRF2": "api_publica_trf2",
    "TRF3": "api_publica_trf3",
    "TRF4": "api_publica_trf4",
    "TRF5": "api_publica_trf5",
    "TRF6": "api_publica_trf6",
    # ─── Tribunais Regionais do Trabalho ──────────────────────────────────────
    "TRT1": "api_publica_trt1",
    "TRT2": "api_publica_trt2",
    "TRT3": "api_publica_trt3",
    "TRT4": "api_publica_trt4",
    "TRT5": "api_publica_trt5",
    "TRT6": "api_publica_trt6",
    "TRT7": "api_publica_trt7",
    "TRT8": "api_publica_trt8",
    "TRT9": "api_publica_trt9",
    "TRT10": "api_publica_trt10",
    "TRT11": "api_publica_trt11",
    "TRT12": "api_publica_trt12",
    "TRT13": "api_publica_trt13",
    "TRT14": "api_publica_trt14",
    "TRT15": "api_publica_trt15",
    "TRT16": "api_publica_trt16",
    "TRT17": "api_publica_trt17",
    "TRT18": "api_publica_trt18",
    "TRT19": "api_publica_trt19",
    "TRT20": "api_publica_trt20",
    "TRT21": "api_publica_trt21",
    "TRT22": "api_publica_trt22",
    "TRT23": "api_publica_trt23",
    "TRT24": "api_publica_trt24",
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
