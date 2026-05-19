#!/usr/bin/env python3
"""Seed completo do banco — 2 tenants, 4 usuários/tenant, 5 clientes, 5 processos, etc."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.base import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User
from app.models.client import Client
from app.models.process import LegalProcess, ProcessDeadline
from app.models.financial import FinancialEntry
from app.models.tenant import Tenant, TenantConfig
from decimal import Decimal
from datetime import date, timedelta
import uuid


async def seed():
    async with AsyncSessionLocal() as db:
        print("Iniciando seed completo...")

        # ── Tenants ──────────────────────────────────────────────────────────
        tenant_afj = Tenant(
            name="Almeida, Freire & Jucá Advogados",
            slug="afj",
            plan="ENTERPRISE",
            is_active=True,
        )
        tenant_demo = Tenant(
            name="Escritório Demo",
            slug="demo",
            plan="STANDARD",
            is_active=True,
        )
        db.add(tenant_afj)
        db.add(tenant_demo)
        await db.flush()

        config_afj = TenantConfig(
            tenant_id=tenant_afj.id,
            app_name="AFJ CORE",
            primary_color="#C9A84C",
            secondary_color="#1A1A1A",
            accent_color="#F5F0E8",
            modules_enabled={
                "processos": True, "peticoes": True, "clientes": True,
                "financeiro": True, "agentes": True, "visual_law": True,
            },
        )
        config_demo = TenantConfig(
            tenant_id=tenant_demo.id,
            app_name="Demo Jurídico",
            primary_color="#1A6EAB",
            secondary_color="#0D1B2A",
            accent_color="#EBF4FB",
            modules_enabled={
                "processos": True, "peticoes": True, "clientes": True,
                "financeiro": False, "agentes": True, "visual_law": True,
            },
        )
        db.add(config_afj)
        db.add(config_demo)
        await db.flush()

        # ── Usuários AFJ ─────────────────────────────────────────────────────
        admin = User(
            email="admin@afjadvogados.com.br",
            hashed_password=hash_password("Admin@123"),
            full_name="Administrador AFJ",
            oab_number="123456CE",
            role="ADMIN",
            is_active=True,
            tenant_id=tenant_afj.id,
        )
        socio = User(
            email="socio@afjadvogados.com.br",
            hashed_password=hash_password("Socio@123"),
            full_name="Dr. Almeida Freire",
            oab_number="111111CE",
            role="SOCIO",
            is_active=True,
            tenant_id=tenant_afj.id,
        )
        advogado = User(
            email="advogado@afjadvogados.com.br",
            hashed_password=hash_password("Advogado@123"),
            full_name="Dr. João Silva",
            oab_number="654321CE",
            role="ADVOGADO",
            is_active=True,
            tenant_id=tenant_afj.id,
        )
        assistente = User(
            email="assistente@afjadvogados.com.br",
            hashed_password=hash_password("Assistente@123"),
            full_name="Ana Secretária",
            role="ASSISTENTE",
            is_active=True,
            tenant_id=tenant_afj.id,
        )
        db.add_all([admin, socio, advogado, assistente])
        await db.flush()

        # Usuários demo
        admin_demo = User(
            email="admin@demo.com",
            hashed_password=hash_password("Demo@123"),
            full_name="Admin Demo",
            role="ADMIN",
            is_active=True,
            tenant_id=tenant_demo.id,
        )
        db.add(admin_demo)
        await db.flush()

        # ── Clientes ─────────────────────────────────────────────────────────
        clientes = [
            Client(
                tipo="PF", nome_completo="Maria das Graças Oliveira",
                email="maria.graca@email.com", telefone="85987654321",
                status="ATIVO", origem="Indicação", lgpd_consent=True,
                responsavel_id=advogado.id, tenant_id=tenant_afj.id,
            ),
            Client(
                tipo="PJ", nome_completo="Construtora Norte Ltda",
                razao_social="Construtora Norte Ltda",
                email="contato@construtoranorte.com.br", telefone="8533334444",
                status="ATIVO", origem="Website", lgpd_consent=True,
                responsavel_id=advogado.id, tenant_id=tenant_afj.id,
            ),
            Client(
                tipo="PF", nome_completo="Carlos Eduardo Sousa",
                email="carlos.sousa@email.com", telefone="85999998888",
                status="ATIVO", origem="Indicação", lgpd_consent=True,
                responsavel_id=advogado.id, tenant_id=tenant_afj.id,
            ),
            Client(
                tipo="PF", nome_completo="Ana Paula Ferreira",
                email="ana.ferreira@email.com", telefone="85911112222",
                status="PROSPECTO", origem="Website", lgpd_consent=False,
                responsavel_id=advogado.id, tenant_id=tenant_afj.id,
            ),
            Client(
                tipo="PJ", nome_completo="TechSolutions Nordeste S.A.",
                razao_social="TechSolutions Nordeste S.A.",
                email="juridico@techsolutions.com.br", telefone="8532221234",
                status="VIP", origem="Indicação", lgpd_consent=True,
                responsavel_id=socio.id, tenant_id=tenant_afj.id,
            ),
        ]
        db.add_all(clientes)
        await db.flush()

        # ── Processos ────────────────────────────────────────────────────────
        hoje = date.today()
        processos = [
            LegalProcess(
                numero_cnj="0001234-56.2024.8.06.0001",
                tribunal="TJCE", vara="1ª Vara Cível", comarca="Fortaleza",
                uf="CE", tipo_acao="Ação de Cobrança", area_direito="CIVIL",
                fase="CONHECIMENTO", situacao="ATIVO",
                valor_causa=Decimal("50000.00"),
                client_id=clientes[0].id, responsavel_id=advogado.id,
                oab_responsavel="CE654321", polo="AUTOR", monitoring_active=True,
                proximo_prazo_at=None,
                tenant_id=tenant_afj.id,
            ),
            LegalProcess(
                numero_cnj="0009876-54.2023.5.07.0001",
                tribunal="TRT7", vara="1ª Vara do Trabalho", comarca="Fortaleza",
                uf="CE", tipo_acao="Reclamação Trabalhista", area_direito="TRABALHISTA",
                fase="CONHECIMENTO", situacao="ATIVO",
                valor_causa=Decimal("25000.00"),
                client_id=clientes[0].id, responsavel_id=advogado.id,
                polo="REU", monitoring_active=True,
                tenant_id=tenant_afj.id,
            ),
            LegalProcess(
                numero_cnj="0005555-11.2024.4.05.8100",
                tribunal="TRF5", vara="3ª Vara Federal", comarca="Fortaleza",
                uf="CE", tipo_acao="Mandado de Segurança", area_direito="ADMINISTRATIVO",
                fase="RECURSAL", situacao="ATIVO",
                valor_causa=Decimal("120000.00"),
                client_id=clientes[4].id, responsavel_id=socio.id,
                polo="ATIVO", monitoring_active=True,
                tenant_id=tenant_afj.id,
            ),
            LegalProcess(
                numero_cnj="0003333-22.2022.8.06.0050",
                tribunal="TJCE", vara="2ª Vara Cível", comarca="Caucaia",
                uf="CE", tipo_acao="Ação de Despejo", area_direito="IMOBILIARIO",
                fase="EXECUCAO", situacao="ATIVO",
                valor_causa=Decimal("8000.00"),
                client_id=clientes[1].id, responsavel_id=advogado.id,
                polo="AUTOR", monitoring_active=True,
                tenant_id=tenant_afj.id,
            ),
            LegalProcess(
                tribunal="STJ", area_direito="CIVIL",
                tipo_acao="Recurso Especial", fase="RECURSAL",
                situacao="AGUARDANDO_JULGAMENTO",
                valor_causa=Decimal("200000.00"),
                client_id=clientes[2].id, responsavel_id=socio.id,
                polo="ATIVO", monitoring_active=True,
                tenant_id=tenant_afj.id,
            ),
        ]
        db.add_all(processos)
        await db.flush()

        # Prazos
        prazos = [
            ProcessDeadline(
                process_id=processos[0].id,
                descricao="Manifestação sobre documentos juntados",
                data_prazo=hoje + timedelta(days=5),
                tipo="MANIFESTACAO",
                status="PENDENTE",
                responsavel_id=advogado.id,
            ),
            ProcessDeadline(
                process_id=processos[1].id,
                descricao="Contestação à reconvenção",
                data_prazo=hoje + timedelta(days=10),
                data_fatal=hoje + timedelta(days=10),
                tipo="CONTESTACAO",
                status="PENDENTE",
                responsavel_id=advogado.id,
            ),
            ProcessDeadline(
                process_id=processos[2].id,
                descricao="Razões de apelação",
                data_prazo=hoje + timedelta(days=3),
                data_fatal=hoje + timedelta(days=3),
                tipo="RECURSO",
                status="PENDENTE",
                responsavel_id=socio.id,
            ),
        ]
        db.add_all(prazos)

        # ── Financeiro ───────────────────────────────────────────────────────
        financeiro = [
            FinancialEntry(
                tipo="RECEITA", categoria="Honorários Advocatícios",
                descricao="Honorários — Ação de Cobrança (Maria das Graças)",
                valor=Decimal("5000.00"), status="PENDENTE",
                client_id=clientes[0].id, process_id=processos[0].id,
                created_by=advogado.id, tenant_id=tenant_afj.id,
            ),
            FinancialEntry(
                tipo="DESPESA", categoria="Custas Processuais",
                descricao="Custas de distribuição — TJCE",
                valor=Decimal("350.00"), status="PAGO",
                process_id=processos[0].id,
                created_by=advogado.id, tenant_id=tenant_afj.id,
            ),
            FinancialEntry(
                tipo="RECEITA", categoria="Honorários Advocatícios",
                descricao="Honorários mensais — TechSolutions Nordeste",
                valor=Decimal("15000.00"), status="PAGO",
                client_id=clientes[4].id,
                created_by=socio.id, tenant_id=tenant_afj.id,
            ),
            FinancialEntry(
                tipo="DESPESA", categoria="Aluguel",
                descricao="Aluguel sala — junho 2026",
                valor=Decimal("4500.00"), status="PAGO",
                created_by=admin.id, tenant_id=tenant_afj.id,
            ),
            FinancialEntry(
                tipo="RECEITA", categoria="Êxito",
                descricao="Honorários de êxito — Ação Trabalhista",
                valor=Decimal("7500.00"), status="PENDENTE",
                client_id=clientes[0].id, process_id=processos[1].id,
                created_by=advogado.id,
                data_vencimento=hoje + timedelta(days=30),
                tenant_id=tenant_afj.id,
            ),
        ]
        db.add_all(financeiro)

        await db.commit()
        print("\n✓ Seed completo concluído!")
        print("  Tenants:")
        print("    afj     — Almeida, Freire & Jucá (ENTERPRISE)")
        print("    demo    — Escritório Demo (STANDARD)")
        print("\n  Usuários AFJ:")
        print("    admin@afjadvogados.com.br       / Admin@123      (ADMIN)")
        print("    socio@afjadvogados.com.br       / Socio@123      (SOCIO)")
        print("    advogado@afjadvogados.com.br    / Advogado@123   (ADVOGADO)")
        print("    assistente@afjadvogados.com.br  / Assistente@123 (ASSISTENTE)")
        print("\n  Usuários Demo:")
        print("    admin@demo.com                  / Demo@123       (ADMIN)")
        print(f"\n  5 clientes, 5 processos, 3 prazos, 5 lançamentos financeiros")


if __name__ == "__main__":
    asyncio.run(seed())
