#!/usr/bin/env python3
"""Seed do banco de dados para desenvolvimento."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.base import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User
from app.models.client import Client
from app.models.process import LegalProcess
from app.models.financial import FinancialEntry
from decimal import Decimal
import uuid


async def seed():
    async with AsyncSessionLocal() as db:
        # Admin user
        admin = User(
            email="admin@afjadvogados.com.br",
            hashed_password=hash_password("Admin@123"),
            full_name="Administrador AFJ",
            oab_number="123456",
            oab_uf="CE",
            role="ADMIN",
            is_active=True,
        )
        db.add(admin)
        await db.flush()

        # Advogado
        advogado = User(
            email="advogado@afjadvogados.com.br",
            hashed_password=hash_password("Advogado@123"),
            full_name="Dr. João Silva",
            oab_number="654321",
            oab_uf="CE",
            role="ADVOGADO",
            is_active=True,
        )
        db.add(advogado)
        await db.flush()

        # Clientes
        cliente1 = Client(
            tipo="PF",
            nome_completo="Maria das Graças Oliveira",
            email="maria.graca@email.com",
            telefone="(85) 98765-4321",
            whatsapp="(85) 98765-4321",
            status="ATIVO",
            origem="Indicação",
            lgpd_consent=True,
            responsavel_id=advogado.id,
        )
        cliente2 = Client(
            tipo="PJ",
            nome_completo="Construtora Norte Ltda",
            razao_social="Construtora Norte Ltda",
            email="contato@construtoranorte.com.br",
            telefone="(85) 3333-4444",
            status="PROSPECTO",
            origem="Website",
            lgpd_consent=False,
            responsavel_id=advogado.id,
        )
        db.add(cliente1)
        db.add(cliente2)
        await db.flush()

        # Processos
        processo1 = LegalProcess(
            numero_cnj="0001234-56.2024.8.06.0001",
            tribunal="TJCE",
            vara="1ª Vara Cível",
            comarca="Fortaleza",
            uf="CE",
            tipo_acao="Ação de Cobrança",
            area_direito="CIVIL",
            fase="Instrução",
            situacao="ATIVO",
            valor_causa=Decimal("50000.00"),
            client_id=cliente1.id,
            responsavel_id=advogado.id,
            oab_responsavel="CE 654321",
            polo="AUTOR",
            monitoring_active=True,
        )
        processo2 = LegalProcess(
            numero_cnj="0009876-54.2023.5.07.0001",
            tribunal="TRT7",
            vara="1ª Vara do Trabalho",
            comarca="Fortaleza",
            uf="CE",
            tipo_acao="Reclamação Trabalhista",
            area_direito="TRABALHISTA",
            situacao="ATIVO",
            valor_causa=Decimal("25000.00"),
            client_id=cliente1.id,
            responsavel_id=advogado.id,
            polo="REU",
            monitoring_active=True,
        )
        db.add(processo1)
        db.add(processo2)
        await db.flush()

        # Lançamentos financeiros
        receita1 = FinancialEntry(
            tipo="RECEITA",
            categoria="Honorários Advocatícios",
            descricao=f"Honorários — Ação de Cobrança (Maria das Graças)",
            valor=Decimal("5000.00"),
            status="PENDENTE",
            client_id=cliente1.id,
            process_id=processo1.id,
            created_by=advogado.id,
        )
        despesa1 = FinancialEntry(
            tipo="DESPESA",
            categoria="Custas Processuais",
            descricao="Custas de distribuição — TJCE",
            valor=Decimal("350.00"),
            status="PAGO",
            process_id=processo1.id,
            created_by=advogado.id,
        )
        db.add(receita1)
        db.add(despesa1)

        await db.commit()
        print("✓ Seed concluído com sucesso!")
        print(f"  Admin: admin@afjadvogados.com.br / Admin@123")
        print(f"  Advogado: advogado@afjadvogados.com.br / Advogado@123")
        print(f"  {2} clientes, {2} processos, {2} lançamentos financeiros")


if __name__ == "__main__":
    asyncio.run(seed())
