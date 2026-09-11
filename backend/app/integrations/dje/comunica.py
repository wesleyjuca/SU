"""Cliente da API Comunica/DJEN do PJe (Diário de Justiça Eletrônico Nacional).

Fonte PÚBLICA e gratuita (sem autenticação) de comunicações judiciais/intimações,
consultável por OAB. Documentação: https://comunicaapi.pje.jus.br/

À prova de falha: qualquer erro (rede, formato, host inacessível no sandbox)
retorna lista vazia — a varredura nunca derruba o worker.

Cliente HTTP: `curl_cffi` (não `httpx`) com `impersonate=` — o WAF deste
portal continuou devolvendo 403 mesmo com headers de navegador reais (Fase
250) e sem relação com o circuit breaker (Fase 251); `curl_cffi` reproduz o
fingerprint TLS/JA3 de um navegador real, não só os headers. Ver o
comentário dentro de `buscar_comunicacoes()` para o histórico completo.

Fase pós-262 — achado: mesmo com `impersonate="chrome124"` (fase anterior)
e a suíte de testes passando, o usuário relatou que a busca por OAB/UF e a
captura de publicações continuam sem funcionar em produção. Este sandbox
nunca conseguiu confirmar isso ao vivo — egress bloqueado pro domínio real
— então não dá pra saber se é o MESMO WAF resistindo até a esse fingerprint
específico, um bloqueio por IP do Railway, ou outra causa. `buscar_
comunicacoes()` passou a tentar uma pequena CADEIA de fingerprints TLS
conhecidos (`_IMPERSONATE_PROFILES`), parando no primeiro que responder
200 — correção honestamente best-effort (nenhum dos 3 foi confirmado
funcionando contra o domínio real), documentada como tal. `stats[
"impersonate"]` registra qual perfil funcionou (ou o último tentado, se
nenhum funcionou) — pedir esse dado ao usuário depois do próximo deploy é
o próximo passo de diagnóstico se o sintoma persistir.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

import structlog
from curl_cffi.requests import AsyncSession

log = structlog.get_logger()

COMUNICA_URL = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"
_TIMEOUT = 20.0
# Fase pós-262 — ordem de tentativa: chrome124 é o que já estava em
# produção (fase anterior); chrome120/safari17 são fallbacks de baixo
# custo (cada um reproduz o fingerprint TLS de um navegador real distinto,
# sem downside — só mais 1-2 tentativas na pior hipótese de o WAF
# continuar bloqueando todos).
_IMPERSONATE_PROFILES = ("chrome124", "chrome120", "safari17")


@dataclass
class Comunicacao:
    """Intimação/publicação normalizada (campos da Comunica variam por edição)."""
    id_externo: str
    numero_cnj: str | None       # número do processo (só dígitos, p/ casamento)
    numero_cnj_fmt: str | None   # número com máscara (exibição)
    texto: str
    data_disponibilizacao: str | None   # ISO date
    tribunal: str | None
    tipo_comunicacao: str | None
    orgao: str | None
    link: str | None

    def hash_dedupe(self) -> str:
        base = f"{self.id_externo}|{self.numero_cnj}|{self.data_disponibilizacao}|{self.texto[:120]}"
        import hashlib
        return hashlib.sha256(base.encode("utf-8", "ignore")).hexdigest()


def _digits(v: str | None) -> str | None:
    if not v:
        return None
    d = re.sub(r"\D", "", v)
    return d or None


def _first(item: dict, *keys: str):
    for k in keys:
        if k in item and item[k] not in (None, ""):
            return item[k]
    return None


def _normalize(item: dict) -> Comunicacao:
    numero_fmt = _first(item, "numeroprocessocommascara", "numeroProcessoComMascara",
                        "numero_processo", "numeroProcesso", "numeroprocesso")
    return Comunicacao(
        id_externo=str(_first(item, "id", "hash", "numeroComunicacao", "numerocomunicacao") or ""),
        numero_cnj=_digits(numero_fmt),
        numero_cnj_fmt=str(numero_fmt) if numero_fmt else None,
        texto=str(_first(item, "texto", "textodocomunicado", "conteudo") or ""),
        data_disponibilizacao=(_first(item, "data_disponibilizacao", "dataDisponibilizacao",
                                      "datadisponibilizacao") or None),
        tribunal=_first(item, "siglaTribunal", "siglatribunal", "tribunal"),
        tipo_comunicacao=_first(item, "tipoComunicacao", "tipocomunicacao", "tipo"),
        orgao=_first(item, "nomeOrgao", "nomeorgao", "orgao"),
        link=_first(item, "link", "linkPje"),
    )


_ITEM_KEYS = ("items", "content", "comunicacoes", "data", "results")
_TOTAL_KEYS = ("count", "total", "totalRegistros", "totalElements", "totalCount")


def _extrai_itens(data) -> list:
    """Extrai a lista de itens da resposta (formato varia por edição da API).

    Robusto ao envelope documentado no swagger cnj/pcp/1.0.0 e a variações:
    lista pura, {items|content|comunicacoes|data|results: [...]} ou o mesmo
    aninhado sob {"data": {...}}."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in _ITEM_KEYS:
            v = data.get(k)
            if isinstance(v, list):
                return v
        inner = data.get("data")
        if isinstance(inner, dict):
            for k in _ITEM_KEYS:
                v = inner.get(k)
                if isinstance(v, list):
                    return v
    return []


def _extrai_total(data) -> int | None:
    """Total de registros informado pela API (p/ parar de paginar cedo)."""
    if isinstance(data, dict):
        for k in _TOTAL_KEYS:
            v = data.get(k)
            if isinstance(v, int) and v >= 0:
                return v
        inner = data.get("data")
        if isinstance(inner, dict):
            for k in _TOTAL_KEYS:
                v = inner.get(k)
                if isinstance(v, int) and v >= 0:
                    return v
    return None


async def buscar_comunicacoes(
    oab_numero: str,
    oab_uf: str,
    data_inicio: date,
    data_fim: date,
    max_paginas: int = 1,
    itens_por_pagina: int = 50,
    stats: dict | None = None,
) -> list[Comunicacao]:
    """Consulta a Comunica por OAB e intervalo de disponibilização.

    `max_paginas` controla quantas páginas varrer (1 = comportamento antigo, p/ a
    varredura diária do DJe; a captura por OAB usa um valor maior). Para de paginar
    assim que uma página vem incompleta/vazia.

    `stats` (opcional) é preenchido para diagnóstico: `ok` (True se a fonte
    respondeu 200 ao menos uma vez), `requests` (nº de chamadas) e `error` (última
    exceção). Permite ao chamador distinguir "fonte inalcançável" de "0 no período".

    Retorna [] em qualquer falha (host inacessível no sandbox, timeout, formato
    inesperado). Em produção (Railway), roda de verdade.
    """
    numero = _digits(oab_numero)
    if not numero or not oab_uf:
        return []

    # Fase pós-262 — diagnóstico do ÚLTIMO perfil tentado, usado só se
    # NENHUM perfil da cadeia conseguir 200 na 1ª página.
    ultimo_perfil: str | None = None
    ultimo_status: int | None = None
    ultimo_corpo = ""
    ultimo_exc: Exception | None = None

    for perfil in _IMPERSONATE_PROFILES:
        out: list[Comunicacao] = []
        sucesso_neste_perfil = False
        ultimo_perfil = perfil
        try:
            async with AsyncSession(
                timeout=_TIMEOUT,
                headers={
                    # Fase 250 — achado real em produção: um User-Agent que se
                    # autoidentifica como bot/sistema ("AFJ-Core/1.0 (...)") leva
                    # 403 do WAF do Comunica/DJEN, mesmo sendo uma API pública
                    # pensada pra consumo por terceiros. Headers de navegador
                    # sozinhos (Fase 250) e o fix do circuit breaker (Fase 251)
                    # não resolveram — o 403 persistiu (Fase 252). A causa mais
                    # provável, dado que headers HTTP já foram descartados: o WAF
                    # faz fingerprint na camada TLS (JA3), que o stack TLS puro-
                    # Python do `httpx` nunca reproduz de verdade, não importa o
                    # header enviado. `impersonate=` abaixo faz a libcurl
                    # reproduzir o aperto de mão TLS real de um navegador —
                    # com isso, `User-Agent`/`Accept`/`Accept-Language` saem
                    # daqui e passam a ser gerados automaticamente pelo
                    # `curl_cffi` (`default_headers=True`, o padrão), consistente
                    # com o fingerprint escolhido — misturar um UA manual com um
                    # impersonate diferente seria, ele mesmo, um sinal que um WAF
                    # mais sofisticado pega. `Referer`/`Origin` seguem manuais
                    # (específicos desta chamada, não implícitos em "ser um
                    # navegador real") — mesmo formato de requisição que o site
                    # público (comunica.pje.jus.br) já faz. Fase pós-260.10.
                    "Referer": "https://comunica.pje.jus.br/consulta",
                    "Origin": "https://comunica.pje.jus.br",
                },
                impersonate=perfil,
                allow_redirects=True,
            ) as client:
                for pagina in range(1, max(1, max_paginas) + 1):
                    params = {
                        "numeroOab": numero,
                        "ufOab": oab_uf.upper(),
                        "dataDisponibilizacaoInicio": data_inicio.isoformat(),
                        "dataDisponibilizacaoFim": data_fim.isoformat(),
                        "itensPorPagina": itens_por_pagina,
                        "pagina": pagina,
                    }
                    resp = await client.get(COMUNICA_URL, params=params)
                    if stats is not None:
                        stats["requests"] = stats.get("requests", 0) + 1
                    if resp.status_code != 200:
                        # Fase 252 — achado: o 403 persistiu mesmo depois do fix de
                        # headers de navegador (Fase 250), o que sugere um bloqueio
                        # mais fundo (fingerprint TLS, IP do Railway na lista negra
                        # do WAF) — mas até agora só capturávamos o status code,
                        # nunca o CORPO da resposta. Se o WAF devolve uma página de
                        # desafio (Cloudflare/Akamai, HTML) em vez de um 403 seco,
                        # estávamos cegos pra essa diferença. Corpo truncado (não é
                        # PII — é a resposta pública de um WAF), sem risco de
                        # estourar o log.
                        corpo_bruto = (resp.text or "")[:500]
                        log.warning("comunica_http", status=resp.status_code, oab=numero, uf=oab_uf,
                                    pagina=pagina, perfil=perfil, corpo=corpo_bruto)
                        ultimo_status = resp.status_code
                        ultimo_corpo = corpo_bruto
                        break
                    sucesso_neste_perfil = True
                    if stats is not None:
                        stats["ok"] = True
                        stats["impersonate"] = perfil
                    corpo = resp.json()
                    itens = _extrai_itens(corpo)
                    for it in itens:
                        if isinstance(it, dict):
                            try:
                                out.append(_normalize(it))
                            except Exception:
                                continue
                    # Página incompleta → não há próxima.
                    if len(itens) < itens_por_pagina:
                        break
                    # Parada antecipada: se a API informa o total e já o coletamos.
                    total = _extrai_total(corpo)
                    if total is not None:
                        if stats is not None:
                            stats["total"] = total
                        if len(out) >= total:
                            break
        except Exception as exc:
            ultimo_exc = exc
            log.warning("comunica_falhou", error=str(exc), oab=numero, uf=oab_uf, perfil=perfil)
            continue

        if sucesso_neste_perfil:
            log.info("comunica_ok", oab=numero, uf=oab_uf, encontradas=len(out), perfil=perfil)
            return out
        # 1ª página deste perfil não respondeu 200 — tenta o próximo perfil
        # da cadeia antes de desistir.

    # Nenhum perfil da cadeia conseguiu 200 — devolve vazio (fail-soft, como
    # sempre) com o diagnóstico do ÚLTIMO perfil tentado.
    if stats is not None:
        stats["impersonate"] = ultimo_perfil
        if ultimo_status is not None:
            stats["status_code"] = ultimo_status
            stats["error"] = (
                f"HTTP {ultimo_status} da Comunica/DJEN em todos os perfis tentados "
                f"({', '.join(_IMPERSONATE_PROFILES)})"
            )
            stats["body_snippet"] = ultimo_corpo
        elif ultimo_exc is not None:
            stats["error"] = str(ultimo_exc)
    return []
