from app.models.tenant import Tenant, TenantConfig
from app.models.user import User, UserPermission, Session
from app.models.client import Client, ClientContact, ClientInteraction, ClientPortalAccess
from app.models.process import LegalProcess, ProcessMovement, ProcessDeadline, ProcessParty, ProcessTeamMember
from app.models.document import Document, DocumentVersion, Petition, Contract
from app.models.agent_run import AgentRun, AgentStep, Approval, AgentMemory
from app.models.audit_log import AuditLog, LGPDConsentRecord
from app.models.financial import FinancialEntry, BillingInvoice
from app.models.notification import Notification
from app.models.integrity import (
    ConductAcceptance, IntegrityReport,
    IntegrityRisk, IntegrityTraining, IntegrityTrainingCompletion, IntegrityCommitteeCase,
)
from app.models.integrations import TenantIntegration
from app.models.sync_run import SyncRun
from app.models.assistant import AssistantConversation, AssistantMessage
from app.models.billing import BillingAccount, TenantPayment
from app.models.crm import Opportunity, CrmMeta
from app.models.intimacao import Intimacao
from app.models.tribunal import Tribunal
# Fase pós-260.7 — estes 2 nunca estiveram aqui: só entravam no metadata
# porque routers/services os importam em runtime. O alembic/env.py faz
# apenas `import app.models`, então o autogenerate não os via e propunha
# DROP TABLE nas duas tabelas. Registro explícito fecha essa armadilha.
from app.models.push_subscription import PushSubscription
from app.models.ai_call_log import AICallLog
from app.models.ai_config import AIProviderConfig
from app.models.jurisprudencia_ingerida import JurisprudenciaIngerida
from app.models.tese import Tese
from app.models.agent_prompt import AgentPromptConfig, AgentPromptVersion, AgentAttachment
from app.models.custom_agent import CustomAgent, CustomAgentVersion
from app.models.gov_registry_lookup import GovRegistryLookup
from app.models.agent_playbook import AgentAreaPlaybook

__all__ = [
    "Tenant", "TenantConfig",
    "User", "UserPermission", "Session",
    "Client", "ClientContact", "ClientInteraction", "ClientPortalAccess",
    "LegalProcess", "ProcessMovement", "ProcessDeadline", "ProcessParty",
    "Document", "DocumentVersion", "Petition", "Contract",
    "AgentRun", "AgentStep", "Approval", "AgentMemory",
    "AuditLog", "LGPDConsentRecord",
    "FinancialEntry", "BillingInvoice",
    "Notification",
    "ConductAcceptance", "IntegrityReport",
    "IntegrityRisk", "IntegrityTraining", "IntegrityTrainingCompletion", "IntegrityCommitteeCase",
    "TenantIntegration",
    "SyncRun",
    "AssistantConversation",
    "AssistantMessage",
    "BillingAccount", "TenantPayment",
    "Opportunity", "CrmMeta",
    "Intimacao",
    "ProcessTeamMember",
    "Tribunal",
    "AIProviderConfig",
    "JurisprudenciaIngerida",
    "Tese",
    "AgentPromptConfig",
    "AgentPromptVersion",
    "AgentAttachment",
    "CustomAgent", "CustomAgentVersion",
    "GovRegistryLookup",
    "AgentAreaPlaybook",
    "PushSubscription", "AICallLog",
]
