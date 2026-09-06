"""Guarda anti-regressão do direito ao esquecimento (LGPD art. 18 IV).

Responde, com artefato executável, a pergunta que ficou aberta por 6
rodadas de teste geral (Fases 219, 228, 235, 246, 247 e pós-255): "vale um
mecanismo estrutural para pegar dado de titular esquecido pelo erase, em
vez de achar essa mesma classe de bug pela 9ª vez?".

Como funciona: cria um titular cujo CADA campo textual recebe um token
único — inclusive dentro do `endereco_json` —, semeia as linhas ligadas
pelos endpoints reais, chama `DELETE /lgpd/clients/{id}/data` e então varre
o BANCO INTEIRO via `information_schema`, coluna a coluna (text/varchar/
jsonb), procurando o token. Qualquer ocorrência é PII sobrevivente, e a
falha nomeia `tabela.coluna`.

Por que uma varredura por VALOR e não uma checagem por TABELA: a guarda
estrutural que o projeto vinha cogitando (toda tabela com FK até
`clients.id` precisa aparecer no erase) não teria pego nenhum dos 3 piores
casos reais — `clients.endereco_json`, `documents.titulo` e
`opportunities.titulo` estão em tabelas que JÁ eram cobertas; só as colunas
ficavam de fora. Este desenho encontrou os três sozinho, sem ninguém
apontar onde olhar.
"""
import uuid

from sqlalchemy import text

from app.db.base import AsyncSessionLocal

# Colunas que guardam dado do titular por finalidade legítima e não são
# apagadas de propósito — cada uma com a razão registrada no `lgpd.py`.
COLUNAS_PRESERVADAS_DE_PROPOSITO: set[tuple[str, str]] = {
    # `audit_logs` é imutável por trigger de banco e é a própria prova de
    # que o esquecimento foi executado (retenção é decisão jurídica em
    # aberto, registrada no CLAUDE.md como débito).
    ("audit_logs", "action"),
    ("audit_logs", "resource_type"),
    ("audit_logs", "old_value"),
    ("audit_logs", "new_value"),
}


async def _varrer_banco(token: str) -> list[tuple[str, str, int]]:
    """Devolve [(tabela, coluna, nº de linhas)] onde o token sobreviveu."""
    achados: list[tuple[str, str, int]] = []
    async with AsyncSessionLocal() as db:
        colunas = (await db.execute(text("""
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND data_type IN ('text', 'character varying', 'jsonb', 'json')
            ORDER BY table_name, column_name
        """))).fetchall()

        for tabela, coluna in colunas:
            if (tabela, coluna) in COLUNAS_PRESERVADAS_DE_PROPOSITO:
                continue
            try:
                quantas = (await db.execute(
                    text(f'SELECT COUNT(*) FROM "{tabela}" WHERE "{coluna}"::text ILIKE :padrao'),
                    {"padrao": f"%{token}%"},
                )).scalar()
            except Exception:
                await db.rollback()  # tipo exótico/coluna inacessível: ignora
                continue
            if quantas:
                achados.append((tabela, coluna, quantas))
    return achados


async def _limpar(client_id: str) -> None:
    """Remove o titular de teste e tudo que aponta para ele.

    Um teste que suja o banco quebra os seguintes: nesta mesma rodada,
    `test_password_change_success` trocava a senha do ADMIN semeado e não
    restaurava, e derrubou o login de toda a sessão assim que a suíte
    voltou a rodar de verdade.
    """
    async with AsyncSessionLocal() as db:
        fks = (await db.execute(text("""
            SELECT tc.table_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu
              ON tc.constraint_name = ccu.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY' AND ccu.table_name = 'clients'
        """))).fetchall()
        for tabela, coluna in fks:
            try:
                await db.execute(text(f'DELETE FROM "{tabela}" WHERE "{coluna}" = :cid'),
                                 {"cid": client_id})
            except Exception:
                await db.rollback()
        await db.execute(text("DELETE FROM clients WHERE id = :cid"), {"cid": client_id})
        await db.commit()


async def test_esquecimento_nao_deixa_pii_em_nenhuma_coluna(client, auth_headers):
    token = f"ZZSENTINELA{uuid.uuid4().hex[:12].upper()}"
    cliente_id = None
    try:
        resposta = await client.post("/api/v1/clients", headers=auth_headers, json={
            "nome_completo": f"Titular {token}",
            "tipo": "PF",
            "email": f"{token.lower()}@exemplo.test",
            "telefone": "85999990000",
            "whatsapp": "85999990000",
            "observacoes": f"observacao {token}",
            "endereco_json": {
                "cep": "60000000", "logradouro": f"Rua {token}", "numero": "100",
                "bairro": f"Bairro {token}", "cidade": "Fortaleza", "uf": "CE",
                "latitude": -3.7319, "longitude": -38.5267,
            },
        })
        assert resposta.status_code in (200, 201), resposta.text
        cliente_id = resposta.json()["id"]

        # Linhas ligadas, pelos endpoints reais. Cada uma é best-effort: o
        # valor da guarda está na varredura, não em semear todas.
        await client.post(f"/api/v1/clients/{cliente_id}/contacts", headers=auth_headers, json={
            "nome": f"Contato {token}", "email": f"c{token.lower()}@x.test",
            "telefone": "8533332222", "cargo": f"Cargo {token}"})
        await client.post(f"/api/v1/clients/{cliente_id}/interactions", headers=auth_headers,
                          json={"tipo": "LIGACAO", "descricao": f"interacao {token}"})
        await client.post("/api/v1/crm/opportunities", headers=auth_headers, json={
            "titulo": f"Oportunidade {token}", "client_id": cliente_id,
            "valor_estimado": 1000, "descricao": f"desc {token}"})
        await client.post("/api/v1/financial", headers=auth_headers, json={
            "tipo": "RECEITA", "categoria": "HONORARIOS", "valor": 500,
            "descricao": f"lancamento {token}", "client_id": cliente_id,
            "data_vencimento": "2027-01-10"})
        await client.post("/api/v1/documents", headers=auth_headers, json={
            "titulo": f"Documento {token}", "tipo": "PETICAO",
            "client_id": cliente_id, "conteudo_texto": f"corpo {token}"})

        processo = await client.post("/api/v1/processes", headers=auth_headers, json={
            "numero_cnj": f"0000001-11.2027.8.06.{uuid.uuid4().hex[:4]}",
            "titulo": f"Processo {token}", "client_id": cliente_id,
            "tribunal": "TJCE", "area": "CIVEL", "descricao": f"descricao {token}"})
        if processo.status_code in (200, 201):
            pid = processo.json()["id"]
            await client.post(f"/api/v1/processes/{pid}/partes", headers=auth_headers, json={
                "nome": f"Parte {token}", "tipo": "AUTOR", "client_id": cliente_id})
            await client.post(f"/api/v1/processes/{pid}/movements", headers=auth_headers,
                              json={"data": "2027-01-05", "descricao": f"movimentacao {token}"})
            await client.post(f"/api/v1/processes/{pid}/deadlines", headers=auth_headers, json={
                "descricao": f"prazo {token}", "data_prazo": "2027-02-01",
                "tipo": "CONTESTACAO"})

        antes = await _varrer_banco(token)
        assert antes, "o token não foi gravado em lugar nenhum — a guarda não provaria nada"

        apagar = await client.delete(f"/api/v1/lgpd/clients/{cliente_id}/data",
                                     headers=auth_headers)
        assert apagar.status_code == 200, apagar.text

        sobreviventes = await _varrer_banco(token)
        assert not sobreviventes, (
            "PII do titular sobreviveu ao direito ao esquecimento em: "
            + ", ".join(f"{t}.{c} ({n} linha[s])" for t, c, n in sobreviventes)
            + ". Se a coluna guarda dado do titular, anonimize em "
              "`erase_client_data`; se ela existe por finalidade legítima, "
              "adicione a COLUNAS_PRESERVADAS_DE_PROPOSITO com a razão."
        )
    finally:
        if cliente_id:
            await _limpar(cliente_id)
