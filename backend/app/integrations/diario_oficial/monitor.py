"""Monitor do Diário de Justiça Eletrônico (DJe) para publicações de OAB cadastradas."""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

import structlog

log = structlog.get_logger()

TRIBUNAIS_DJE: dict[str, str] = {
    "TJCE": "https://esaj.tjce.jus.br/cdje/consultaSimples.do",
    "TJSP": "https://www.dje.tjsp.jus.br/cdje/consultaSimples.do",
    "TJBA": "https://e.tjba.jus.br/dje",
    "TJRJ": "https://www.tjrj.jus.br/dje",
    "TJMG": "https://www.tjmg.jus.br/portal-tjmg/dje",
    "STJ": "https://scon.stj.jus.br/SCON/diario/",
    "STF": "https://portal.stf.jus.br/servicos/diarioJustica/",
    "TST": "https://aplicacao.tst.jus.br/dspace/handle/1939/1",
    "TRF1": "https://www.trf1.jus.br/publicacoes/dje",
    "TRF5": "https://www.trf5.jus.br/trf5/component/diario/",
}


@dataclass
class DJePublicacao:
    tribunal: str
    data_publicacao: date
    oab_encontrada: str
    numero_processo: Optional[str]
    conteudo: str
    url_fonte: Optional[str] = None
    verificado: bool = False


@dataclass
class DJeMonitor:
    """Monitor de publicações no Diário de Justiça Eletrônico.

    Placeholder para integração real com sistemas dos tribunais.
    Implementação real requer autenticação por tribunal.
    """

    tribunais: list[str] = field(default_factory=lambda: list(TRIBUNAIS_DJE.keys()))
    timeout_seconds: int = 30
    _circuit_open: dict[str, datetime] = field(default_factory=dict)

    def _is_circuit_open(self, tribunal: str) -> bool:
        if tribunal not in self._circuit_open:
            return False
        if datetime.utcnow() - self._circuit_open[tribunal] > timedelta(minutes=30):
            del self._circuit_open[tribunal]
            return False
        return True

    def _open_circuit(self, tribunal: str) -> None:
        self._circuit_open[tribunal] = datetime.utcnow()
        log.warning("dje_circuit_open", tribunal=tribunal)

    async def scan_today(self) -> list[DJePublicacao]:
        """Varre todos os tribunais configurados no dia de hoje."""
        today = date.today()
        all_results: list[DJePublicacao] = []

        tasks = [self._fetch_dje_page(tribunal, today) for tribunal in self.tribunais]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for tribunal, result in zip(self.tribunais, results):
            if isinstance(result, Exception):
                log.error("dje_scan_failed", tribunal=tribunal, error=str(result))
            elif result:
                all_results.extend(result)

        log.info("dje_scan_today_complete", date=str(today), total=len(all_results))
        return all_results

    async def search_oab(self, oab: str, uf: str) -> list[DJePublicacao]:
        """Busca publicações para uma OAB específica no tribunal correspondente à UF."""
        tribunal_key = f"TJ{uf.upper()}"
        if tribunal_key not in TRIBUNAIS_DJE:
            log.warning("dje_tribunal_not_configured", oab=oab, uf=uf)
            return []

        results = await self._fetch_dje_page(tribunal_key, date.today(), oab_filter=oab)
        return results or []

    async def _fetch_dje_page(
        self,
        tribunal: str,
        pub_date: date,
        oab_filter: Optional[str] = None,
    ) -> list[DJePublicacao]:
        """Busca publicações de um tribunal para uma data específica.

        IMPORTANTE: Este é um placeholder. A integração real requer:
        - Autenticação específica por tribunal
        - Parsing de HTML/PDF do DJe
        - Tratamento de captcha (alguns tribunais)
        - Rate limiting respeitoso
        """
        if self._is_circuit_open(tribunal):
            log.debug("dje_circuit_skipped", tribunal=tribunal)
            return []

        try:
            results = await self._simulate_fetch(tribunal, pub_date, oab_filter)
            return results
        except Exception as exc:
            log.error("dje_fetch_error", tribunal=tribunal, date=str(pub_date), error=str(exc))
            self._open_circuit(tribunal)
            return []

    async def _simulate_fetch(
        self,
        tribunal: str,
        pub_date: date,
        oab_filter: Optional[str] = None,
    ) -> list[DJePublicacao]:
        """Simulação — substituir por integração real com cada tribunal."""
        await asyncio.sleep(0)
        return []

    async def scan_for_oabs(self, oabs: list[str], ufs: list[str]) -> list[DJePublicacao]:
        """Varre DJes dos tribunais das UFs informadas buscando publicações para lista de OABs."""
        today = date.today()
        tribunais_alvo = {f"TJ{uf.upper()}" for uf in ufs if f"TJ{uf.upper()}" in TRIBUNAIS_DJE}

        all_results: list[DJePublicacao] = []
        for tribunal in tribunais_alvo:
            if self._is_circuit_open(tribunal):
                continue
            try:
                page_results = await self._fetch_dje_page(tribunal, today)
                for pub in page_results:
                    oab_digits = re.sub(r"\D", "", pub.oab_encontrada)
                    if any(re.sub(r"\D", "", oab) == oab_digits for oab in oabs):
                        all_results.append(pub)
            except Exception as exc:
                log.error("dje_scan_oabs_error", tribunal=tribunal, error=str(exc))
                self._open_circuit(tribunal)

        return all_results


dje_monitor = DJeMonitor()
