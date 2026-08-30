"""Fonte de descoberta por OAB via Comunica/DJEN (Fase 73).

Envolve `integrations/dje/comunica.py::buscar_comunicacoes` (pública, nacional,
sem auth) e o normaliza em `ProcessoDescoberto`. `buscar_comunicacoes` já é
fail-soft (nunca levanta); usamos o dict `stats` que ela preenche para alimentar
o circuit breaker — assim "fonte inalcançável" (respondeu, mas nunca 200) conta
como falha, enquanto "0 no período" conta como sucesso.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.integrations.fontes.base import Capability, FonteProcessual, ProcessoDescoberto
from app.integrations.fontes.circuit_breaker import CircuitBreaker


class ComunicaFonte(FonteProcessual):
    nome = "comunica"
    capabilities = {Capability.DESCOBRIR_OAB}

    def __init__(self) -> None:
        self._breaker = CircuitBreaker(name=self.nome)

    async def descobrir_por_oab(
        self,
        oab_numero: str,
        oab_uf: str,
        data_inicio: date,
        data_fim: date,
        *,
        max_paginas: int = 20,
        itens_por_pagina: int = 50,
        stats: dict | None = None,
        **kwargs: Any,
    ) -> list[ProcessoDescoberto]:
        # Fase 251 — achado: este era o único breaker do projeto que nunca
        # sincronizava com o Redis (todo outro `FonteProcessual` usa
        # `self._breaker.run(...)`, que hidrata/persiste sozinho). Como
        # `ComunicaFonte` é um singleton por processo (registry.py), o
        # painel Cérebro (processo web) nunca via as falhas registradas
        # pelo worker Celery — mesma lacuna que a Fase 166 já tinha
        # resolvido para as outras fontes. `buscar_comunicacoes` nunca
        # lança (é fail-soft por design), então o sinal de sucesso/falha
        # vem de `stats`, não de uma exceção — por isso não dá pra usar
        # `run()` diretamente; hidrata/persiste manualmente com os mesmos
        # métodos que `run()` usa por baixo.
        await self._breaker.sincronizar_de_redis()
        if not self._breaker.allow():
            return []

        from app.integrations.dje.comunica import buscar_comunicacoes

        st = stats if stats is not None else {}
        comunicacoes = await buscar_comunicacoes(
            oab_numero, oab_uf, data_inicio, data_fim,
            max_paginas=max_paginas, itens_por_pagina=itens_por_pagina, stats=st,
        )
        # `itens` acumula o total BRUTO de comunicações (antes do dedup por CNJ),
        # para o chamador preservar a métrica "comunicações encontradas".
        st["itens"] = st.get("itens", 0) + len(comunicacoes)
        # buscar_comunicacoes não levanta; deduzimos sucesso/falha pelos stats.
        if st.get("requests") and not st.get("ok"):
            self._breaker.record_failure()
        else:
            self._breaker.record_success()
        await self._breaker.sincronizar_para_redis()

        vistos: set[str] = set()
        out: list[ProcessoDescoberto] = []
        for c in comunicacoes:
            numero = getattr(c, "numero_cnj", None)
            if not numero or numero in vistos:
                continue
            vistos.add(numero)
            out.append(ProcessoDescoberto(
                numero_cnj=numero,
                tribunal=getattr(c, "tribunal", None) or None,
                uf=oab_uf.upper() if oab_uf else None,
                fonte=self.nome,
                raw=c,
            ))
        return out
