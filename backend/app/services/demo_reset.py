"""Fase 199 — reset do tenant público de demonstração: apaga TODOS os dados
gerados no tenant demo e re-semeia o conjunto fictício original. Chamado
periodicamente (Celery Beat, `app/workers/tasks/demo_reset.py`) e sob
demanda (`POST /tenants-admin/demo/reset`, SUPERADMIN real).

Garantia contra vazar pro tenant `afj` (ou qualquer outro): esta função NÃO
recebe `tenant_id` como parâmetro — resolve o alvo internamente e aborta
(RuntimeError) se não achar o tenant certo. Nenhum caller pode passar o
UUID errado porque não existe parâmetro pra passar."""
import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger()


async def resetar_tenant_demo(db: AsyncSession) -> dict:
    from app.models.tenant import Tenant, TenantConfig
    from app.services.demo_fixtures import criar_elenco_demo, gerar_dados_ficticios

    tenant = (await db.execute(
        select(Tenant).where(Tenant.slug == "demo", Tenant.is_demo.is_(True))
    )).scalar_one_or_none()
    if tenant is None:
        raise RuntimeError("Tenant demo não encontrado ou is_demo=false — abortando reset por segurança.")
    if tenant.slug != "demo" or tenant.isento:
        raise RuntimeError("Invariante violado: tentativa de resetar um tenant que não é o demo — abortando.")
    demo_id = tenant.id

    # Apaga tudo tenant-scoped do tenant demo, numa única transação (rollback
    # automático se qualquer DELETE falhar — nunca fica em estado parcial).
    # `custom_agents` fica de fora DE PROPÓSITO: seu tenant_id é só auditoria
    # de quem propôs, o agente é plataforma-wide (visível/usável por todos os
    # tenants) — apagar por tenant_id removeria algo que outros tenants usam.
    # `tenant_configs` também fica de fora: 1 linha por tenant, é UPDATE
    # (reset de branding) não DELETE, ver abaixo.
    from app.models.agent_run import AgentRun, Approval
    from app.models.ai_config import AIProviderConfig
    from app.models.audit_log import AuditLog, LGPDConsentRecord
    from app.models.billing import BillingAccount, TenantPayment
    from app.models.client import Client
    from app.models.crm import Opportunity
    from app.models.document import Document, PetitionTemplate
    from app.models.financial import BillingInvoice, FinancialEntry
    from app.models.integrations import TenantIntegration
    from app.models.integrity import (
        ConductAcceptance, IntegrityCommitteeCase, IntegrityReport,
        IntegrityRisk, IntegrityTraining, IntegrityTrainingCompletion,
    )
    from app.models.intimacao import Intimacao
    from app.models.jurisprudencia_ingerida import JurisprudenciaIngerida
    from app.models.notification import Notification
    from app.models.process import LegalProcess
    from app.models.push_subscription import PushSubscription
    from app.models.sync_run import SyncRun
    from app.models.tese import Tese
    from app.models.user import AIBudgetLimit, AITaskOverride, User

    tabelas = [
        Approval, AgentRun, AITaskOverride, AIBudgetLimit, AIProviderConfig,
        Document, PetitionTemplate, FinancialEntry, BillingInvoice,
        TenantIntegration, ConductAcceptance, IntegrityReport, IntegrityRisk,
        IntegrityTraining, IntegrityTrainingCompletion, IntegrityCommitteeCase,
        Intimacao, JurisprudenciaIngerida, Notification, LegalProcess,
        PushSubscription, SyncRun, Tese, Opportunity, BillingAccount,
        TenantPayment, AuditLog, Client,
        User,  # sempre por último — cascata de sessions/permissions/etc.
    ]
    apagados = {}

    # LGPDConsentRecord não tem tenant_id próprio (só client_id, sem
    # ON DELETE CASCADE da FK) — precisa ser apagado por subquery ANTES do
    # DELETE de Client abaixo, senão a FK rejeita o DELETE de Client com
    # consentimento registrado.
    apagados["lgpd_consent_records"] = (await db.execute(
        delete(LGPDConsentRecord).where(
            LGPDConsentRecord.client_id.in_(select(Client.id).where(Client.tenant_id == demo_id))
        )
    )).rowcount

    # User.linked_client_id (portal do cliente) também não tem ON DELETE na
    # FK — desvincula antes do DELETE de Client pelo mesmo motivo acima.
    # gerar_dados_ficticios nunca seta isso, mas um convite de portal
    # disparado manualmente durante o uso do tenant demo poderia.
    await db.execute(
        User.__table__.update()
        .where(User.tenant_id == demo_id, User.linked_client_id.isnot(None))
        .values(linked_client_id=None)
    )

    # Fase 202 (achado da Fase 201) — sem isso, documentos aprovados no
    # tenant demo ficavam órfãos pra sempre em cada reset: o DELETE de
    # Document abaixo só apaga a linha do Postgres, nunca os chunks
    # vetoriais no Qdrant (buscas RAG continuariam trazendo conteúdo de
    # documentos supostamente apagados) nem o blob no S3 (quando
    # configurado). Lê a lista ANTES do DELETE genérico abaixo apagar as
    # linhas. Fail-soft (best-effort): uma falha aqui não pode travar o
    # reset do Postgres, que é a garantia principal desta função.
    from app.integrations import object_storage
    from app.rag.auto_ingest import _collection_for
    from app.rag.ingestion import delete_document_chunks

    documentos = (await db.execute(
        select(Document.id, Document.tipo, Document.arquivo_storage_key)
        .where(Document.tenant_id == demo_id)
    )).all()
    for doc_id, tipo, storage_key in documentos:
        try:
            await delete_document_chunks(_collection_for(tipo), str(doc_id))
        except Exception as exc:
            log.warning("demo_reset_qdrant_cleanup_failed", document_id=str(doc_id), error=str(exc))
        if storage_key and object_storage.is_configured():
            try:
                await object_storage.delete_bytes(storage_key)
            except Exception as exc:
                log.warning("demo_reset_s3_cleanup_failed", document_id=str(doc_id), error=str(exc))

    for modelo in tabelas:
        result = await db.execute(delete(modelo).where(modelo.tenant_id == demo_id))
        apagados[modelo.__tablename__] = result.rowcount

    # Branding volta ao padrão do tenant demo (a linha em si não é apagada).
    config = (await db.execute(
        select(TenantConfig).where(TenantConfig.tenant_id == demo_id)
    )).scalar_one_or_none()
    if config is not None:
        config.app_name = "Demo Jurídico"
        config.primary_color = "#1A6EAB"
        config.secondary_color = "#0D1B2A"
        config.accent_color = "#EBF4FB"
        config.modules_enabled = {
            "processos": True, "peticoes": True, "clientes": True,
            "financeiro": True, "agentes": True, "visual_law": True,
        }

    tenant.max_users = 4

    admin_id, socio_id, advogado_id, _ = await criar_elenco_demo(db, demo_id)
    await gerar_dados_ficticios(db, demo_id, admin_id, socio_id, advogado_id)

    await db.commit()
    log.info("demo_tenant_resetado", tenant_id=str(demo_id), apagados=apagados)
    return {"tenant_id": str(demo_id), "apagados": apagados}
