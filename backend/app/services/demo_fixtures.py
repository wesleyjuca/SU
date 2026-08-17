"""Fase 199 — geração de dados fictícios reutilizável (clientes, processos,
prazos, financeiro), extraída de `scripts/seed_db.py` (que só aplicava isso
ao tenant `afj`). Usada tanto pelo seed inicial quanto pelo reset periódico
do tenant de demonstração pública (`app/services/demo_reset.py`) — por isso
não pode fechar sobre nada além dos parâmetros recebidos."""
import secrets
import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.financial import FinancialEntry
from app.models.process import LegalProcess, ProcessDeadline

# Credencial pública do tenant demo — divulgada, sem senha secreta a proteger.
DEMO_ADMIN_EMAIL = "demo@afjdemo.com.br"
DEMO_ADMIN_SENHA = "Demo@2026"


async def criar_elenco_demo(db: AsyncSession, tenant_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Cria os 4 usuários do tenant demo (ADMIN/SOCIO/ADVOGADO/ASSISTENTE) — só
    o ADMIN tem a credencial pública/divulgada, os outros 3 nascem com senha
    aleatória (só existem pra dar realismo a `responsavel_id` nos dados
    fictícios — ninguém loga com eles). `Tenant.max_users=4` (setado por quem
    chama) fecha, sem código novo em `ai_budget.py`, a brecha de criar um 5º
    usuário sem `AIBudgetLimit` pra escapar do teto de IA.
    Retorna (admin_id, socio_id, advogado_id, assistente_id)."""
    from app.core.security import hash_password
    from app.models.user import User, AIBudgetLimit

    admin = User(
        email=DEMO_ADMIN_EMAIL, hashed_password=hash_password(DEMO_ADMIN_SENHA),
        full_name="Visitante (Admin Demo)", role="ADMIN", is_active=True, tenant_id=tenant_id,
    )
    socio = User(
        email="socio@afjdemo.com.br", hashed_password=hash_password(secrets.token_urlsafe(24)),
        full_name="Dra. Sócia Demo", role="SOCIO", is_active=True, tenant_id=tenant_id,
    )
    advogado = User(
        email="advogado@afjdemo.com.br", hashed_password=hash_password(secrets.token_urlsafe(24)),
        full_name="Dr. Advogado Demo", role="ADVOGADO", is_active=True, tenant_id=tenant_id,
    )
    assistente = User(
        email="assistente@afjdemo.com.br", hashed_password=hash_password(secrets.token_urlsafe(24)),
        full_name="Assistente Demo", role="ASSISTENTE", is_active=True, tenant_id=tenant_id,
    )
    db.add_all([admin, socio, advogado, assistente])
    await db.flush()

    # Teto de IA (Fase 145) só pros 3 papéis que efetivamente disparam agente
    # (assistente não tem essa ação na UI, mas nada impede via API — sem
    # AIBudgetLimit ele ficaria sem teto, então cobre os 4 por segurança).
    for user in (admin, socio, advogado, assistente):
        db.add(AIBudgetLimit(user_id=user.id, tenant_id=tenant_id, monthly_limit_usd=1.0, alert_pct=80))
    await db.flush()

    return admin.id, socio.id, advogado.id, assistente.id


async def gerar_dados_ficticios(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    admin_id: uuid.UUID,
    socio_id: uuid.UUID,
    advogado_id: uuid.UUID,
) -> None:
    """5 clientes, 5 processos, 3 prazos, 5 lançamentos financeiros — mesmo
    conjunto usado desde o seed original, agora parametrizado por tenant."""
    clientes = [
        Client(
            tipo="PF", nome_completo="Maria das Graças Oliveira",
            email="maria.graca@email.com", telefone="85987654321",
            status="ATIVO", origem="Indicação", lgpd_consent=True,
            responsavel_id=advogado_id, tenant_id=tenant_id,
        ),
        Client(
            tipo="PJ", nome_completo="Construtora Norte Ltda",
            razao_social="Construtora Norte Ltda",
            email="contato@construtoranorte.com.br", telefone="8533334444",
            status="ATIVO", origem="Website", lgpd_consent=True,
            responsavel_id=advogado_id, tenant_id=tenant_id,
        ),
        Client(
            tipo="PF", nome_completo="Carlos Eduardo Sousa",
            email="carlos.sousa@email.com", telefone="85999998888",
            status="ATIVO", origem="Indicação", lgpd_consent=True,
            responsavel_id=advogado_id, tenant_id=tenant_id,
        ),
        Client(
            tipo="PF", nome_completo="Ana Paula Ferreira",
            email="ana.ferreira@email.com", telefone="85911112222",
            status="PROSPECTO", origem="Website", lgpd_consent=False,
            responsavel_id=advogado_id, tenant_id=tenant_id,
        ),
        Client(
            tipo="PJ", nome_completo="TechSolutions Nordeste S.A.",
            razao_social="TechSolutions Nordeste S.A.",
            email="juridico@techsolutions.com.br", telefone="8532221234",
            status="VIP", origem="Indicação", lgpd_consent=True,
            responsavel_id=socio_id, tenant_id=tenant_id,
        ),
    ]
    db.add_all(clientes)
    await db.flush()

    hoje = date.today()
    processos = [
        LegalProcess(
            numero_cnj="0001234-56.2024.8.06.0001",
            tribunal="TJCE", vara="1ª Vara Cível", comarca="Fortaleza",
            uf="CE", tipo_acao="Ação de Cobrança", area_direito="CIVIL",
            fase="CONHECIMENTO", situacao="ATIVO",
            valor_causa=Decimal("50000.00"),
            client_id=clientes[0].id, responsavel_id=advogado_id,
            oab_responsavel="CE654321", polo="AUTOR", monitoring_active=True,
            proximo_prazo_at=None,
            tenant_id=tenant_id,
        ),
        LegalProcess(
            numero_cnj="0009876-54.2023.5.07.0001",
            tribunal="TRT7", vara="1ª Vara do Trabalho", comarca="Fortaleza",
            uf="CE", tipo_acao="Reclamação Trabalhista", area_direito="TRABALHISTA",
            fase="CONHECIMENTO", situacao="ATIVO",
            valor_causa=Decimal("25000.00"),
            client_id=clientes[0].id, responsavel_id=advogado_id,
            polo="REU", monitoring_active=True,
            tenant_id=tenant_id,
        ),
        LegalProcess(
            numero_cnj="0005555-11.2024.4.05.8100",
            tribunal="TRF5", vara="3ª Vara Federal", comarca="Fortaleza",
            uf="CE", tipo_acao="Mandado de Segurança", area_direito="ADMINISTRATIVO",
            fase="RECURSAL", situacao="ATIVO",
            valor_causa=Decimal("120000.00"),
            client_id=clientes[4].id, responsavel_id=socio_id,
            polo="ATIVO", monitoring_active=True,
            tenant_id=tenant_id,
        ),
        LegalProcess(
            numero_cnj="0003333-22.2022.8.06.0050",
            tribunal="TJCE", vara="2ª Vara Cível", comarca="Caucaia",
            uf="CE", tipo_acao="Ação de Despejo", area_direito="IMOBILIARIO",
            fase="EXECUCAO", situacao="ATIVO",
            valor_causa=Decimal("8000.00"),
            client_id=clientes[1].id, responsavel_id=advogado_id,
            polo="AUTOR", monitoring_active=True,
            tenant_id=tenant_id,
        ),
        LegalProcess(
            tribunal="STJ", area_direito="CIVIL",
            tipo_acao="Recurso Especial", fase="RECURSAL",
            situacao="AGUARDANDO_JULGAMENTO",
            valor_causa=Decimal("200000.00"),
            client_id=clientes[2].id, responsavel_id=socio_id,
            polo="ATIVO", monitoring_active=True,
            tenant_id=tenant_id,
        ),
    ]
    db.add_all(processos)
    await db.flush()

    prazos = [
        ProcessDeadline(
            process_id=processos[0].id,
            descricao="Manifestação sobre documentos juntados",
            data_prazo=hoje + timedelta(days=5),
            tipo="MANIFESTACAO",
            status="PENDENTE",
            responsavel_id=advogado_id,
        ),
        ProcessDeadline(
            process_id=processos[1].id,
            descricao="Contestação à reconvenção",
            data_prazo=hoje + timedelta(days=10),
            data_fatal=hoje + timedelta(days=10),
            tipo="CONTESTACAO",
            status="PENDENTE",
            responsavel_id=advogado_id,
        ),
        ProcessDeadline(
            process_id=processos[2].id,
            descricao="Razões de apelação",
            data_prazo=hoje + timedelta(days=3),
            data_fatal=hoje + timedelta(days=3),
            tipo="RECURSO",
            status="PENDENTE",
            responsavel_id=socio_id,
        ),
    ]
    db.add_all(prazos)

    financeiro = [
        FinancialEntry(
            tipo="RECEITA", categoria="Honorários Advocatícios",
            descricao="Honorários — Ação de Cobrança (Maria das Graças)",
            valor=Decimal("5000.00"), status="PENDENTE",
            client_id=clientes[0].id, process_id=processos[0].id,
            created_by=advogado_id, tenant_id=tenant_id,
        ),
        FinancialEntry(
            tipo="DESPESA", categoria="Custas Processuais",
            descricao="Custas de distribuição — TJCE",
            valor=Decimal("350.00"), status="PAGO",
            process_id=processos[0].id,
            created_by=advogado_id, tenant_id=tenant_id,
        ),
        FinancialEntry(
            tipo="RECEITA", categoria="Honorários Advocatícios",
            descricao="Honorários mensais — TechSolutions Nordeste",
            valor=Decimal("15000.00"), status="PAGO",
            client_id=clientes[4].id,
            created_by=socio_id, tenant_id=tenant_id,
        ),
        FinancialEntry(
            tipo="DESPESA", categoria="Aluguel",
            descricao="Aluguel sala — mês corrente",
            valor=Decimal("4500.00"), status="PAGO",
            created_by=admin_id, tenant_id=tenant_id,
        ),
        FinancialEntry(
            tipo="RECEITA", categoria="Êxito",
            descricao="Honorários de êxito — Ação Trabalhista",
            valor=Decimal("7500.00"), status="PENDENTE",
            client_id=clientes[0].id, process_id=processos[1].id,
            created_by=advogado_id,
            data_vencimento=hoje + timedelta(days=30),
            tenant_id=tenant_id,
        ),
    ]
    db.add_all(financeiro)
    await db.flush()
