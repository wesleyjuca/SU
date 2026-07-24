"""Parsing tolerante de PARTES para fontes credenciadas (PDPJ/Escavador/Judit).

As respostas variam por provedor/versão, então o extractor é deliberadamente
permissivo: reconhece `partes`, `poloAtivo`/`poloPassivo` (PDPJ) e `envolvidos`
(Escavador) — cada item podendo ser uma parte, um advogado, ou trazer advogados
aninhados. Fail-soft: entradas malformadas são ignoradas.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.partes_import import ParteEntrada


def _first(item: dict, *keys: str):
    for k in keys:
        v = item.get(k)
        if v not in (None, "", []):
            return v
    return None


def _polo_para_tipo(polo: str | None) -> tuple[str, str | None]:
    """Mapeia o polo bruto p/ (tipo, polo_normalizado) do ProcessParty."""
    p = (polo or "").strip().upper()
    if p.startswith(("AT", "ATIVO")) or p in {"A", "REQUERENTE", "AUTOR", "EXEQUENTE"}:
        return "AUTOR", "ATIVO"
    if p.startswith(("PA", "PASSIVO")) or p in {"P", "REQUERIDO", "REU", "RÉU", "EXECUTADO"}:
        return "REU", "PASSIVO"
    return "PARTE", (p or None)


def _oab_fmt(item: dict) -> str | None:
    num = _first(item, "numeroOab", "oab", "inscricaoOab", "numero_oab")
    uf = _first(item, "ufOab", "uf", "uf_oab", "estadoOab")
    if num and uf:
        return f"{num}/{uf}"[:20]
    return str(num)[:20] if num else None


def extrair_partes(dados: dict) -> "list[ParteEntrada]":
    """Extrai partes + advogados de uma resposta de processo (tolerante)."""
    from app.services.partes_import import ParteEntrada

    out: list[ParteEntrada] = []

    def _consumir(lista, polo_hint: str | None):
        for item in lista or []:
            if not isinstance(item, dict):
                continue
            nome = _first(item, "nome", "nomeParte", "razaoSocial", "nome_completo")
            if not nome:
                continue
            tipo_bruto = (str(_first(item, "tipo", "tipoParte", "papel", "tipo_pessoa") or "")).upper()
            polo = _first(item, "polo", "tipoPolo", "poloProcessual", "polo_processual") or polo_hint

            if "ADVOG" in tipo_bruto:
                _, polo_norm = _polo_para_tipo(polo)
                out.append(ParteEntrada(tipo="ADVOGADO", nome=str(nome)[:500],
                                        cpf_cnpj=None, oab=_oab_fmt(item), polo=polo_norm))
            else:
                tipo, polo_norm = _polo_para_tipo(polo)
                doc = _first(item, "documento", "cpfCnpj", "numeroDocumento", "cpf", "cnpj")
                out.append(ParteEntrada(tipo=tipo, nome=str(nome)[:500],
                                        cpf_cnpj=str(doc)[:18] if doc else None,
                                        oab=None, polo=polo_norm))

            for adv in (_first(item, "advogados", "representantes") or []):
                if not isinstance(adv, dict):
                    continue
                nome_adv = _first(adv, "nome", "nomeAdvogado", "nome_completo")
                if not nome_adv:
                    continue
                _, polo_norm = _polo_para_tipo(polo)
                out.append(ParteEntrada(tipo="ADVOGADO", nome=str(nome_adv)[:500],
                                        cpf_cnpj=None, oab=_oab_fmt(adv), polo=polo_norm))

    if isinstance(dados.get("partes"), list):
        _consumir(dados["partes"], None)
    if isinstance(dados.get("envolvidos"), list):
        _consumir(dados["envolvidos"], None)
    _consumir(dados.get("poloAtivo"), "ATIVO")
    _consumir(dados.get("poloPassivo"), "PASSIVO")
    return out
