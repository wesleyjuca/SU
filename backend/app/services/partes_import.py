"""Importador de PARTES do processo (Fase 75) — único escritor de ProcessParty.

A tabela `process_parties` existia desde o schema inicial mas nunca era
escrita (a base pública do DataJud não expõe partes). Com a fonte credenciada
PDPJ (que expõe partes), este módulo passa a populá-la.

Dedup por chave normalizada (tipo + nome + oab) para não duplicar a mesma parte
a cada atualização. Não faz commit — a transação é do chamador (igual ao
importador de movimentos, Fase 72).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import structlog
from sqlalchemy import select

log = structlog.get_logger()


@dataclass
class ParteEntrada:
    """Parte normalizada, independente da fonte."""
    tipo: str                       # AUTOR, REU, ADVOGADO, JUIZ, MP, PARTE
    nome: str
    cpf_cnpj: str | None = None
    oab: str | None = None
    polo: str | None = None         # ATIVO, PASSIVO


def _chave(tipo: str | None, nome: str | None, oab: str | None) -> str:
    """Chave de dedup: tipo + nome normalizado + oab (colapsa espaços/caixa)."""
    n = re.sub(r"\s+", " ", (nome or "")).strip().lower()
    return f"{(tipo or '').upper()}|{n}|{(oab or '').lower()}"


async def importar_partes(db, process, partes: list[ParteEntrada], origem: str = "IMPORTADO") -> dict:
    """Grava as partes NOVAS de um processo (dedup por tipo+nome+oab).

    `origem` (Fase 127) rotula de qual provedor as partes vieram (ex. "PDPJ",
    "ESCAVADOR") — o chamador automático passa o nome real do provedor;
    default genérico só existe pra chamadores que não o conheçam.

    NÃO faz commit. Retorna {"novas": int, "total": int}."""
    from app.models.process import ProcessParty

    if not partes:
        return {"novas": 0, "total": 0}

    existentes_rows = (await db.execute(
        select(ProcessParty.tipo, ProcessParty.nome, ProcessParty.oab)
        .where(ProcessParty.process_id == process.id)
    )).all()
    vistos = {_chave(t, n, o) for t, n, o in existentes_rows}

    novas = 0
    for p in partes:
        if not p.nome:
            continue
        chave = _chave(p.tipo, p.nome, p.oab)
        if chave in vistos:
            continue
        vistos.add(chave)
        db.add(ProcessParty(
            process_id=process.id,
            tipo=(p.tipo or "PARTE")[:20],
            nome=p.nome[:500],
            cpf_cnpj=(p.cpf_cnpj or None),
            oab=(p.oab or None),
            polo=(p.polo or None),
            origem=origem[:20],
        ))
        novas += 1

    if novas:
        log.info("partes_importadas", process_id=str(process.id), novas=novas)
    return {"novas": novas, "total": len(vistos)}
