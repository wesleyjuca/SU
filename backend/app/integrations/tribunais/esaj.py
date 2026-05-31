"""Conector e-SAJ — Sistema de Automação da Justiça (TJSP, TJBA, TJMS, etc.)."""
from datetime import datetime
import httpx
import re
import structlog

from app.integrations.tribunais.base import BaseTribunalClient, MovementData

log = structlog.get_logger()

ESAJ_BASE_URLS = {
    "TJSP": "https://esaj.tjsp.jus.br",
    "TJBA": "https://esaj.tjba.jus.br",
    "TJMS": "https://esaj.tjms.jus.br",
    "TJRJ": "https://www3.tjrj.jus.br",
    "TJMG": "https://www5.tjmg.jus.br",
}

# Prefixo do processo por tribunal (para construir URL de consulta)
ESAJ_PROCESS_PREFIX = {
    "TJSP": "cpopg",   # consulta pública 1º grau
    "TJBA": "cpopg",
    "TJMS": "cpopg",
}


class ESAJClient(BaseTribunalClient):
    """Cliente para o sistema e-SAJ (TJSP, TJBA, TJMS, etc.)."""

    def __init__(self, tribunal: str):
        self.tribunal = tribunal.upper()
        self.base_url = ESAJ_BASE_URLS.get(self.tribunal, "")
        self._cookies: dict = {}

    async def authenticate(self) -> bool:
        """e-SAJ tem consulta pública sem autenticação para o 1º grau."""
        if not self.base_url:
            log.warning("esaj_tribunal_not_supported", tribunal=self.tribunal)
            return False
        return True

    async def fetch_movements(self, numero_cnj: str, since: datetime) -> list[MovementData]:
        if not self.base_url:
            return []

        prefix = ESAJ_PROCESS_PREFIX.get(self.tribunal, "cpopg")
        codigo_processo = _cnj_to_esaj_code(numero_cnj)

        url = f"{self.base_url}/{prefix}/show.do"
        params = {
            "processo.codigo": codigo_processo,
            "processo.foro": _extract_foro(numero_cnj),
        }

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                res = await client.get(url, params=params)
                if res.status_code == 200:
                    return _parse_esaj_html(res.text, since)
        except Exception as exc:
            log.error("esaj_fetch_failed", numero_cnj=numero_cnj, tribunal=self.tribunal, error=str(exc))

        return []

    async def search_by_oab(self, oab: str, uf: str) -> list[str]:
        if not self.base_url:
            return []

        prefix = ESAJ_PROCESS_PREFIX.get(self.tribunal, "cpopg")
        url = f"{self.base_url}/{prefix}/search.do"
        params = {
            "cbPesquisa": "NUMOAB",
            "txtPesquisa": oab,
            "ufoab": uf,
        }

        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                res = await client.get(url, params=params)
                if res.status_code == 200:
                    return _extract_process_numbers(res.text)
        except Exception as exc:
            log.error("esaj_search_failed", oab=oab, tribunal=self.tribunal, error=str(exc))

        return []


def _cnj_to_esaj_code(numero_cnj: str) -> str:
    """Extrai código do processo do número CNJ (formato NNNNNNN-DD.AAAA.J.TT.OOOO)."""
    digits = re.sub(r"\D", "", numero_cnj)
    if len(digits) >= 7:
        return digits[:7]
    return digits


def _extract_foro(numero_cnj: str) -> str:
    """Extrai o código do foro do número CNJ (últimos 4 dígitos)."""
    digits = re.sub(r"\D", "", numero_cnj)
    return digits[-4:] if len(digits) >= 4 else "0001"


def _parse_esaj_html(html: str, since: datetime) -> list[MovementData]:
    """Parser simplificado de HTML do e-SAJ para extrair movimentações."""
    from bs4 import BeautifulSoup

    movements = []
    try:
        soup = BeautifulSoup(html, "html.parser")

        # Tabela de movimentações no e-SAJ tem classe específica
        table = soup.find("table", {"id": "tabelaTodasMovimentacoes"}) or \
                soup.find("table", class_="fundocinza1")

        if not table:
            return []

        rows = table.find_all("tr")
        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 3:
                continue

            date_text = cols[0].get_text(strip=True)
            descricao = cols[2].get_text(strip=True) or cols[1].get_text(strip=True)

            try:
                data_mov = datetime.strptime(date_text, "%d/%m/%Y")
                if data_mov < since:
                    continue
                movements.append(MovementData(
                    data_movimento=data_mov,
                    descricao=descricao,
                    tipo=None,
                    documento_url=None,
                    raw_html=str(row),
                ))
            except ValueError:
                continue
    except Exception as exc:
        log.warning("esaj_parse_error", error=str(exc))

    return movements


def _extract_process_numbers(html: str) -> list[str]:
    """Extrai números CNJ de uma página de resultados do e-SAJ."""
    cnj_pattern = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")
    return list(set(cnj_pattern.findall(html)))
