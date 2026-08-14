"""Mapa do sistema (Bloco F / F1) — nós e arestas para o painel "Cérebro".

Descreve os grandes blocos da aplicação (camadas de API, agentes de IA,
integrações externas, serviços de infra) e como se conectam. As contagens
vêm dos registries reais (routers, orchestrator, PROVIDERS) — não de números
mágicos — então o mapa acompanha a evolução do código.
"""
from __future__ import annotations


def _contar_routers() -> int:
    try:
        from app.api.v1 import router as r
        return sum(1 for _ in r.api_router.routes)
    except Exception:
        return 0


def _agentes() -> list[str]:
    try:
        from app.agents.brain.orchestrator import resolve_agent_class  # noqa: F401
        # o mapa de agentes vive no orchestrator; reflete via introspecção do módulo
        import app.agents.brain.orchestrator as orch
        import inspect
        src = inspect.getsource(orch.resolve_agent_class)
        # extrai as chaves "xxx_agent": do agent_map
        import re
        return re.findall(r'"(\w+_agent)"\s*:', src)
    except Exception:
        return []


def _providers_integracao() -> list[str]:
    try:
        from app.services.integration_hub import PROVIDERS
        return list(PROVIDERS.keys())
    except Exception:
        return []


def _fontes_captura() -> list[str]:
    """Nomes das fontes processuais registradas (comunica, datajud, …)."""
    try:
        from app.integrations.fontes.registry import todas_as_fontes
        return [getattr(f, "nome", "?") for f in todas_as_fontes()]
    except Exception:
        return []


def _fontes_caps() -> dict[str, list[str]]:
    """Capabilities por fonte registrada (p/ o drill-down do nó no mapa)."""
    try:
        from app.integrations.fontes.registry import todas_as_fontes
        return {
            getattr(f, "nome", "?"): sorted(c.value for c in getattr(f, "capabilities", set()))
            for f in todas_as_fontes()
        }
    except Exception:
        return {}


def _tribunais_count() -> int:
    """Nº de tribunais na tabela de referência (fonte única, Fase 74)."""
    try:
        from app.services.tribunais_ref import linhas_seed
        return len(linhas_seed())
    except Exception:
        return 0


# ─── Camadas do Cérebro Neural (Fase 84) ──────────────────────────────────────
# Anéis concêntricos ao redor do núcleo (API): inteligência → memória →
# execução → integrações. A classificação é por id/prefixo — qualquer nó novo
# (agente, provider ou fonte futuros) já nasce na camada certa (auto-crescimento
# sem posições fixas). `_grupo_fallback` só entra em jogo para um id totalmente
# desconhecido, mapeando pelo `grupo` legado como aproximação razoável.
_CAMADA_POR_ID: dict[str, str] = {
    "api": "nucleo",
    "orchestrator": "inteligencia", "llm": "inteligencia", "qdrant": "inteligencia",
    "postgres": "memoria", "redis": "memoria",
    "celery": "execucao", "captura": "execucao",
}
_PREFIXOS_INTELIGENCIA = ("agente_",)
_SUFIXOS_INTELIGENCIA = ("_agent",)
_PREFIXOS_INTEGRACOES = ("prov_", "fonte_")
_GRUPO_FALLBACK: dict[str, str] = {
    "api": "nucleo", "agentes": "inteligencia", "infra": "memoria",
    "integracoes": "integracoes", "dados": "memoria",
}

_PESO_NUCLEO = 5
_PESO_SERVICO_CENTRAL = 3
_PESO_FOLHA = 1
_IDS_SERVICO_CENTRAL = {"orchestrator", "celery", "hub", "postgres", "redis", "qdrant", "llm", "captura"}

_PESO_ARESTA_ESTRUTURAL = 3   # liga núcleo/orquestrador a serviços centrais
_PESO_ARESTA_FOLHA = 1        # liga um hub a um nó-folha (agente/provider/fonte)
_TIPOS_ARESTA_ESTRUTURAL = {"dados", "cache", "dispara", "fila", "ia", "rag", "agenda", "config"}


def _classificar_camada(no: dict) -> str:
    """Camada concêntrica de um nó (nucleo|inteligencia|memoria|execucao|integracoes)."""
    nid = no.get("id") or ""
    if nid in _CAMADA_POR_ID:
        return _CAMADA_POR_ID[nid]
    if nid.startswith(_PREFIXOS_INTELIGENCIA) or nid.endswith(_SUFIXOS_INTELIGENCIA):
        return "inteligencia"
    if nid.startswith(_PREFIXOS_INTEGRACOES):
        return "integracoes"
    return _GRUPO_FALLBACK.get(no.get("grupo") or "", "integracoes")


def _peso_no(no: dict) -> int:
    """Importância do nó (tamanho visual). Núcleo > serviços centrais > folhas."""
    nid = no.get("id") or ""
    if nid == "api":
        return _PESO_NUCLEO
    if nid in _IDS_SERVICO_CENTRAL:
        return _PESO_SERVICO_CENTRAL
    return _PESO_FOLHA


def _peso_aresta(tipo: str) -> int:
    """Espessura da sinapse. Fluxos estruturais > ligações a nós-folha."""
    return _PESO_ARESTA_ESTRUTURAL if tipo in _TIPOS_ARESTA_ESTRUTURAL else _PESO_ARESTA_FOLHA


def construir_mapa() -> dict:
    """Retorna {nós, arestas} para renderizar o grafo do Cérebro.

    Nós têm: id, label, grupo (api|agentes|integracoes|infra|dados), e um
    campo `saude_key` que o frontend casa com o snapshot de /brain/infra para
    colorir o nó. Arestas são dependências/fluxos de dados."""
    agentes = _agentes()
    providers = _providers_integracao()
    fontes = _fontes_captura()
    tribunais = _tribunais_count()

    nos = [
        # Camada de API / núcleo
        {"id": "api", "label": "API FastAPI", "grupo": "api",
         "meta": {"routers": _contar_routers()}},
        {"id": "orchestrator", "label": "Orquestrador (LangGraph)", "grupo": "agentes",
         "meta": {"agentes": len(agentes)}},
        {"id": "captura", "label": "Captura Nacional", "grupo": "agentes",
         "meta": {"fontes": fontes, "pdpj": "credenciado (por escritório)", "tribunais": tribunais}},
        # Infra
        {"id": "postgres", "label": "PostgreSQL", "grupo": "infra", "saude_key": "postgres_pool"},
        {"id": "redis", "label": "Redis", "grupo": "infra", "saude_key": "redis"},
        {"id": "qdrant", "label": "Qdrant (RAG)", "grupo": "infra", "saude_key": "qdrant"},
        {"id": "celery", "label": "Celery (workers)", "grupo": "infra", "saude_key": "celery"},
        # Integrações externas (hub + Google)
        {"id": "hub", "label": "Hub de Integrações", "grupo": "integracoes",
         "meta": {"providers": providers}},
        {"id": "llm", "label": "LLM (Anthropic/Gemini)", "grupo": "integracoes"},
    ]
    # Nós por agente (compactos) ligados ao orquestrador
    for nome in agentes:
        nos.append({"id": nome, "label": nome.replace("_agent", ""), "grupo": "agentes"})
    # Nós por provider de integração
    for p in providers:
        nos.append({"id": f"prov_{p}", "label": p, "grupo": "integracoes"})
    # Nós por fonte da captura (comunica, datajud, …) + PDPJ credenciado
    caps = _fontes_caps()
    for f in fontes:
        nos.append({"id": f"fonte_{f}", "label": f, "grupo": "integracoes",
                    "meta": {"capabilities": caps.get(f, [])}})
    nos.append({"id": "fonte_pdpj", "label": "pdpj (credenciado)", "grupo": "integracoes",
                "meta": {"capabilities": ["detalhar", "movimentos", "partes"], "credenciado": True}})

    arestas = [
        {"de": "api", "para": "postgres", "tipo": "dados"},
        {"de": "api", "para": "redis", "tipo": "cache"},
        {"de": "api", "para": "orchestrator", "tipo": "dispara"},
        {"de": "orchestrator", "para": "celery", "tipo": "fila"},
        {"de": "orchestrator", "para": "llm", "tipo": "ia"},
        {"de": "orchestrator", "para": "qdrant", "tipo": "rag"},
        {"de": "celery", "para": "captura", "tipo": "agenda"},
        {"de": "captura", "para": "postgres", "tipo": "dados"},
        {"de": "api", "para": "hub", "tipo": "config"},
    ]
    for nome in agentes:
        arestas.append({"de": "orchestrator", "para": nome, "tipo": "roteia"})
    for p in providers:
        arestas.append({"de": "hub", "para": f"prov_{p}", "tipo": "conecta"})
    for f in fontes:
        arestas.append({"de": "captura", "para": f"fonte_{f}", "tipo": "fonte"})
    arestas.append({"de": "captura", "para": "fonte_pdpj", "tipo": "fonte"})

    # Camada concêntrica + peso (Fase 84) — aditivo, não quebra o schema atual.
    for no in nos:
        no["camada"] = _classificar_camada(no)
        no["peso"] = _peso_no(no)
    for a in arestas:
        a["peso"] = _peso_aresta(a["tipo"])

    return {"nos": nos, "arestas": arestas,
            "resumo": {"agentes": len(agentes), "providers": len(providers),
                       "routers": _contar_routers(), "fontes": len(fontes), "tribunais": tribunais}}
