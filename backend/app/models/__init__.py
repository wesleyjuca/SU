from app.models.user import User, UserPermission, Session
from app.models.client import Client, ClientContact, ClientInteraction
from app.models.process import LegalProcess, ProcessMovement, ProcessDeadline, ProcessParty, ProcessTeamMember
from app.models.document import Document, DocumentVersion, Petition, Contract
from app.models.agent_run import AgentRun, AgentStep, Approval, AgentMemory
from app.models.audit_log import AuditLog, LGPDConsentRecord
from app.models.financial import FinancialEntry, BillingInvoice
from app.models.notification import Notification
from app.models.integrity import ConductAcceptance, IntegrityReport
from app.models.integrations import TenantIntegration
from app.models.sync_run import SyncRun
from app.models.assistant import AssistantConversation, AssistantMessage
from app.models.billing import BillingAccount, TenantPayment
from app.models.crm import Opportunity
from app.models.intimacao import Intimacao
from app.models.tribunal import Tribunal
from app.models.ai_config import AIProviderConfig
from app.models.jurisprudencia_ingerida import JurisprudenciaIngerida
from app.models.tese import Tese
from app.models.agent_prompt import AgentPromptConfig, AgentPromptVersion, AgentAttachment

__all__ = [
    "User", "UserPermission", "Session",
    "Client", "ClientContact", "ClientInteraction",
    "LegalProcess", "ProcessMovement", "ProcessDeadline", "ProcessParty",
    "Document", "DocumentVersion", "Petition", "Contract",
    "AgentRun", "AgentStep", "Approval", "AgentMemory",
    "AuditLog", "LGPDConsentRecord",
    "FinancialEntry", "BillingInvoice",
    "Notification",
    "ConductAcceptance", "IntegrityReport",
    "TenantIntegration",
    "SyncRun",
    "AssistantConversation",
    "AssistantMessage",
    "BillingAccount", "TenantPayment",
    "Opportunity",
    "Intimacao",
    "ProcessTeamMember",
    "Tribunal",
    "AIProviderConfig",
    "JurisprudenciaIngerida",
    "Tese",
    "AgentPromptConfig",
    "AgentPromptVersion",
    "AgentAttachment",
]
