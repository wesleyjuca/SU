"""Task Celery: sincronização diária de jurisprudência do STJ (Fase 138.1).

Processa só o lote mais recente disponível no portal por execução — nunca um
backfill histórico completo dentro do beat automático (um backfill manual,
sob demanda e com teto explícito, é uma ação separada, fora de escopo desta
fase). Sem credencial nenhuma necessária — fonte pública, sem tenant.

Fase 138.5: cada acórdão novo é classificado (favorável/desfavorável +
área do direito) via LLM antes da ingestão, populando os campos
`favoravel`/`area_direito` do payload Qdrant (reservados desde a Fase 138.1,
nunca preenchidos até aqui). Acórdãos ingeridos ANTES desta fase não são
reclassificados retroativamente (decisão do usuário — backfill fica pra uma
ação futura separada, sob pedido explícito)."""
import json
import re
from datetime import datetime, timezone
from sqlalchemy import select
import structlog

from app.workers.worker import celery_app

log = structlog.get_logger()

AREA_DIREITO_VALIDAS = {
    "CIVIL", "TRABALHISTA", "PENAL", "TRIBUTARIO", "ADMINISTRATIVO",
    "CONSUMIDOR", "EMPRESARIAL", "PREVIDENCIARIO", "FAMILIA", "CONSTITUCIONAL",
    "AMBIENTAL", "OUTRO",
}  # mesmo vocabulário livre-mas-convencionado de LegalProcess.area_direito
   # (app/models/process.py:25), estendido com categorias STJ-relevantes.

CLASSIFICACAO_SYSTEM_PROMPT = """Você é um assistente jurídico que classifica acórdãos do STJ.
Leia a ementa/trecho do acórdão e responda APENAS um JSON, sem texto antes ou depois:
{"favoravel": true|false, "area_direito": "<uma das categorias>"}

"favoravel": true se o acórdão dá provimento ao recurso / reforma a decisão
recorrida em favor do recorrente; false se nega provimento / mantém a
decisão recorrida. Se genuinamente não for possível determinar a partir do
texto, responda favoravel como false e não invente.

"area_direito": escolha UMA destas categorias, em maiúsculas, a que melhor
descreve a matéria: CIVIL, TRABALHISTA, PENAL, TRIBUTARIO, ADMINISTRATIVO,
CONSUMIDOR, EMPRESARIAL, PREVIDENCIARIO, FAMILIA, CONSTITUCIONAL, AMBIENTAL,
OUTRO.

Responda só o JSON."""

CLASSIFICACAO_TRUNCAMENTO = 4000  # chars — ementa/relatório costuma bastar


def _extrair_classificacao(texto: str) -> dict | None:
    """Extrai {"favoravel": bool, "area_direito": str} da resposta do LLM.
    Tolerante a cerca de markdown/texto extra. None se malformado/campos
    ausentes/tipo errado ou fora do vocabulário — nunca lança."""
    if not texto:
        return None
    limpo = texto.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", limpo, re.DOTALL)
    candidato = m.group(1) if m else limpo
    if not m:
        i, f = candidato.find("{"), candidato.rfind("}")
        if i == -1 or f == -1 or f < i:
            return None
        candidato = candidato[i:f + 1]
    try:
        dados = json.loads(candidato)
    except Exception:
        return None
    if not isinstance(dados, dict):
        return None
    favoravel = dados.get("favoravel")
    area = str(dados.get("area_direito") or "").strip().upper()
    if not isinstance(favoravel, bool) or area not in AREA_DIREITO_VALIDAS:
        return None
    return {"favoravel": favoravel, "area_direito": area}


async def classificar_acordao(texto: str) -> dict | None:
    """Classifica favorabilidade + área de direito de 1 acórdão via LLM.
    Fail-soft: qualquer erro (rede, parsing, formato) retorna None — o
    chamador decide o que fazer (na sync: não popula os campos, loga e
    segue). Função standalone reutilizável fora do loop de sync (ex.: uma
    futura reclassificação em lote, sob pedido explícito)."""
    from app.integrations.llm_client import call_llm

    trecho = (texto or "")[:CLASSIFICACAO_TRUNCAMENTO]
    if not trecho.strip():
        return None
    try:
        conteudo, _in_tok, _out_tok, custo = await call_llm(
            messages=[{"role": "user", "content": trecho}],
            system=CLASSIFICACAO_SYSTEM_PROMPT,
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            temperature=0.0,
        )
    except Exception as exc:
        log.warning("stj_classificacao_llm_falhou", error=str(exc))
        return None

    resultado = _extrair_classificacao(conteudo)
    if resultado is None:
        log.warning("stj_classificacao_formato_invalido", resposta=conteudo[:200])
        return None
    resultado["custo_usd"] = custo
    return resultado


async def executar_sync_stj(db) -> dict:
    """Lógica de sincronização, separada do wrapper Celery pra ser
    testável/chamável diretamente com uma sessão real. Fail-soft por
    documento (uma decisão malformada não derruba as demais)."""
    from app.models.jurisprudencia_ingerida import JurisprudenciaIngerida
    from app.integrations.jurisprudencia.stj_client import buscar_lote_recente
    from app.rag.ingestion import ingest_document
    from app.services.movements_import import iniciar_sync, finalizar_sync

    run = await iniciar_sync(db, tenant_id=None, fonte="stj_dados_abertos", tipo="INGESTAO")

    processados = 0
    pulados = 0
    falhas = 0
    nao_classificados = 0
    custo_total = 0.0
    try:
        registros = await buscar_lote_recente()
    except Exception as exc:
        log.error("stj_sync_busca_falhou", error=str(exc))
        stats = {"processados": 0, "pulados": 0, "falhas": 0, "erro": str(exc)[:300]}
        await finalizar_sync(db, run, "ERRO", stats)
        await db.commit()
        raise

    # Fase 167 — sem este try/except em volta do loop inteiro, uma exceção
    # não tratada no MEIO da lista (ex.: DB caiu, ou o SoftTimeLimitExceeded
    # que o próprio Celery levanta perto do time_limit) propagava direto pra
    # fora de `executar_sync_stj`, pulando o `finalizar_sync("OK", ...)` no
    # final — o SyncRun ficava preso em RUNNING pra sempre, mesmo com o
    # worker já tendo morrido/desistido havia muito tempo.
    try:
        for reg in registros:
            fonte_documento_id = reg.get("fonte_documento_id")
            if not fonte_documento_id:
                continue
            existe = (await db.execute(
                select(JurisprudenciaIngerida).where(
                    JurisprudenciaIngerida.fonte == "stj_dados_abertos",
                    JurisprudenciaIngerida.fonte_documento_id == fonte_documento_id,
                )
            )).scalar_one_or_none()
            if existe:
                pulados += 1
                continue

            metadata_extraida = {
                k: v for k, v in reg.items() if k not in ("texto", "fonte_documento_id") and v
            }
            entrada = JurisprudenciaIngerida(
                fonte="stj_dados_abertos",
                fonte_documento_id=fonte_documento_id,
                collection_alvo="jurisprudencia",
                metadata_extraida=metadata_extraida,
                status="PENDENTE",
            )
            db.add(entrada)
            await db.flush()

            # Classificação (Fase 138.5) tem try/except próprio, separado do de
            # ingestão logo abaixo — uma falha aqui nunca deve marcar o
            # documento como FALHOU (bloquearia reingestão por um problema
            # cosmético, não fatal). `classificar_acordao` já é fail-soft e não
            # lança, mas o resultado ainda pode ser None.
            classificacao = await classificar_acordao(reg["texto"])
            if classificacao is None:
                nao_classificados += 1
            else:
                custo_total += classificacao.get("custo_usd", 0.0)

            try:
                qdrant_metadata = {"tribunal": "STJ", **metadata_extraida}
                if classificacao is not None:
                    qdrant_metadata["favoravel"] = classificacao["favoravel"]
                    qdrant_metadata["area_direito"] = classificacao["area_direito"]
                await ingest_document(
                    content=reg["texto"], collection="jurisprudencia",
                    metadata=qdrant_metadata, document_id=fonte_documento_id,
                    force_system_default=True,  # collection pública/compartilhada
                )
                entrada.status = "EMBEDDED"
                processados += 1
            except Exception as exc:
                entrada.status = "FALHOU"
                entrada.erro = str(exc)[:500]
                falhas += 1
                log.warning("stj_ingest_falhou", fonte_documento_id=fonte_documento_id, error=str(exc))
            entrada.processed_at = datetime.now(timezone.utc)
            await db.commit()
    except Exception as exc:
        log.error("stj_sync_loop_falhou", error=str(exc))
        stats = {
            "processados": processados, "pulados": pulados, "falhas": falhas,
            "nao_classificados": nao_classificados,
            "custo_classificacao_usd": round(custo_total, 4),
            "erro": str(exc)[:300],
        }
        await finalizar_sync(db, run, "ERRO", stats)
        await db.commit()
        raise

    stats = {
        "processados": processados, "pulados": pulados, "falhas": falhas,
        "nao_classificados": nao_classificados,
        "custo_classificacao_usd": round(custo_total, 4),
    }
    await finalizar_sync(db, run, "OK", stats)
    await db.commit()
    log.info("stj_sync_complete", **stats)
    return stats


@celery_app.task(
    name="app.workers.tasks.jurisprudencia_sync.sync_stj_diario", bind=True, max_retries=3,
    time_limit=3600, soft_time_limit=3300,
)
def sync_stj_diario(self):
    """Executa `executar_sync_stj()` — roda via Beat, re-tenta se a task
    inteira falhar (ex.: DB indisponível)."""
    from app.workers.async_utils import run_worker_coro

    async def _run():
        from app.db.base import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            return await executar_sync_stj(db)

    async def _run_with_lock():
        from app.workers.task_lock import TaskLock

        lock = TaskLock("sync_stj_diario", ttl_seconds=3900)
        if not await lock.acquire():
            log.info("task_skipped_lock_held", task="sync_stj_diario")
            return {"skipped": True, "reason": "lock_held"}
        try:
            return await _run()
        finally:
            await lock.release()

    try:
        return run_worker_coro(_run_with_lock())
    except Exception as exc:
        log.error("stj_sync_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=300)
