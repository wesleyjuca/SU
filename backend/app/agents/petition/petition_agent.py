"""
petition_agent — Gera petições jurídicas com base em templates, dados do processo e RAG.

Fluxo:
  1. Recupera petições similares do Qdrant (RAG)
  2. Busca dados do processo no DB
  3. Chama jurisprudence_agent internamente para precedentes
  4. Seleciona template pelo tipo de petição
  5. Gera com Claude — prompt anti-fabricação
  6. Valida citações (nenhuma sem fonte)
  7. Cria Document + Petition no DB
  8. Seta requires_approval = True → aguarda validação humana
"""
import time
import uuid
from typing import ClassVar

from app.agents.base.agent import BaseAgent
from app.agents.base.result import AgentResult, AgentStatus
from app.agents.brain.context import AgentContext
from app.integrations.anthropic_client import call_claude, AFJ_LEGAL_SYSTEM_PROMPT
from app.integrations.llm_client import last_call_truncated_ctx
from app.agents.petition.templates.base_template import get_template
import structlog
from app.config import settings

log = structlog.get_logger()

PETITION_SYSTEM_PROMPT = AFJ_LEGAL_SYSTEM_PROMPT + """

INSTRUÇÕES ESPECÍFICAS PARA PETIÇÕES:
- Estruture a petição com as seções padrão: EXCELENTÍSSIMO(A) SENHOR(A), QUALIFICAÇÃO DAS PARTES, DOS FATOS, DO DIREITO, DOS PEDIDOS, DO VALOR DA CAUSA (se aplicável).
- Use negrito (**texto**) para títulos de seção.
- Numere os pedidos.
- Encerre com "Termos em que, pede deferimento." e local/data.
- Nunca inclua assinatura — o advogado assina manualmente."""


class PetitionAgent(BaseAgent):
    name: ClassVar[str] = "petition_agent"
    description: ClassVar[str] = "Gera petições jurídicas com base em templates e RAG jurisprudencial"
    requires_human_approval: ClassVar[bool] = True

    async def execute(self, ctx: AgentContext) -> AgentResult:
        task = ctx.task_input
        tipo_peticao = task.get("tipo_peticao", "PETICAO_INICIAL")
        instrucoes = task.get("instrucoes", "")
        processo_dados = task.get("processo", {})

        # 1. Recuperar petições similares via RAG
        similaridades = await self.recall(
            ctx,
            query=f"{tipo_peticao} {processo_dados.get('tipo_acao', '')} {processo_dados.get('area_direito', '')}",
            collections=["peticoes_afj", "jurisprudencia", "legislacao"],
            k=5,
        )

        # 2. Buscar jurisprudência relevante
        jurisprudencia_ctx = await self._buscar_jurisprudencia(ctx, processo_dados)

        # 3. Obter template
        template = get_template(tipo_peticao)

        # 4. Montar contexto para o prompt
        contexto_processo = self._formatar_processo(processo_dados)
        contexto_rag = self._formatar_rag(similaridades)
        contexto_juris = self._formatar_jurisprudencia(jurisprudencia_ctx)

        prompt_usuario = f"""TIPO DE PETIÇÃO: {tipo_peticao}
TEMPLATE A SEGUIR: {template.instrucoes}

DADOS DO PROCESSO:
{contexto_processo}

JURISPRUDÊNCIA DISPONÍVEL (use apenas estas):
{contexto_juris}

PETIÇÕES SIMILARES DO ESCRITÓRIO (referência de estilo):
{contexto_rag}

INSTRUÇÕES ESPECÍFICAS DO ADVOGADO:
{instrucoes or "Nenhuma instrução adicional."}

Gere a petição completa seguindo o template e as regras absolutas do sistema."""

        # 5. Chamar Claude
        call_start_ms = int(time.time() * 1000)
        content, input_tokens, output_tokens, cost = await call_claude(
            messages=[{"role": "user", "content": prompt_usuario}],
            system=await self.resolve_system_prompt(PETITION_SYSTEM_PROMPT),
            max_tokens=8000,
            temperature=0.2,  # baixíssima temperatura para consistência jurídica
        )
        duration_ms = int(time.time() * 1000) - call_start_ms
        ctx.add_tokens(input_tokens + output_tokens, cost)
        ctx.add_audit_event("LLM_CALL", {
            "model": "default", "tokens": input_tokens + output_tokens,
            "cost_usd": round(cost, 4), "duration_ms": duration_ms,
        })

        total_tokens = input_tokens + output_tokens

        # 6. Validar — nenhuma citação sem fonte
        warnings = self._validar_citacoes(content, jurisprudencia_ctx)

        # Fase 130 — truncamento por limite de tokens passava despercebido: a
        # petição saía cortada no meio, sem fechamento nem seção de pedidos,
        # e ia pra aprovação parecendo completa (preview de 500 chars nunca
        # mostra o final cortado).
        if last_call_truncated_ctx.get():
            warnings.append(
                "Conteúdo pode estar truncado (limite de tokens atingido) — "
                "revise o final da petição antes de aprovar."
            )

        # Fase 130 — verificação automática de citações (LEI/PROCESSO, Fase
        # 93/126) contra a fonte oficial. Antes só existia como ação manual
        # separada (POST /documents/{id}/verificar-citacoes) que o revisor
        # podia simplesmente esquecer de clicar — uma citação plausível mas
        # fabricada passava pra aprovação sem nenhuma checagem automática.
        citacoes = []
        try:
            from app.services.citacao_check import verificar_citacoes
            citacoes = await verificar_citacoes(content, tribunal=processo_dados.get("tribunal"))
            for c in citacoes:
                if c["status"] != "confirmada":
                    warnings.append(f"Citação {c['tipo']} {c['referencia']}: {c['status']}")
        except Exception as exc:
            log.warning("petition_verificar_citacoes_falhou", error=str(exc))

        # 7. Criar documento no DB (se DB disponível)
        document_id = str(uuid.uuid4())
        if self.db:
            document_id = await self._salvar_documento(ctx, content, tipo_peticao, total_tokens, cost)

        ctx.document_id = uuid.UUID(document_id) if isinstance(document_id, str) else document_id
        ctx.set_state("peticao_gerada", True)
        ctx.set_state("peticao_warnings", warnings)

        return AgentResult(
            status=AgentStatus.AWAITING_APPROVAL,
            agent_name=self.name,
            output={
                "document_id": str(document_id),
                "tipo_peticao": tipo_peticao,
                "conteudo": content,
                "warnings": warnings,
                "citacoes": citacoes,
                "tokens_input": input_tokens,
                "tokens_output": output_tokens,
            },
            artifacts=[{"tipo": "peticao", "document_id": str(document_id), "preview": content[:500]}],
            approval_required={
                "tipo": "PETITION_REVIEW",
                "titulo": f"Revisar e aprovar {tipo_peticao.replace('_', ' ').title()}",
                "descricao": f"O agente gerou uma petição do tipo {tipo_peticao}. "
                             f"Revise o conteúdo antes de protocolá-la. "
                             + (f"Avisos: {'; '.join(warnings)}" if warnings else ""),
                "document_id": str(document_id),
            },
            tokens_used=total_tokens,
            cost_usd=cost,
        )

    async def _buscar_jurisprudencia(self, ctx: AgentContext, processo: dict) -> list[dict]:
        """Busca jurisprudência relevante via RAG — nunca inventa."""
        area = processo.get("area_direito", "")
        tipo_acao = processo.get("tipo_acao", "")
        query = f"jurisprudência {area} {tipo_acao}"
        return await self.recall(ctx, query=query, collections=["jurisprudencia"], k=8)

    def _formatar_processo(self, dados: dict) -> str:
        linhas = []
        for campo, valor in dados.items():
            if valor:
                linhas.append(f"- {campo.replace('_', ' ').title()}: {valor}")
        return "\n".join(linhas) if linhas else "Dados do processo não fornecidos."

    def _formatar_rag(self, chunks: list[dict]) -> str:
        if not chunks:
            return "Nenhuma petição similar encontrada na base do escritório."
        partes = []
        for i, chunk in enumerate(chunks[:3], 1):
            payload = chunk.get("payload", {})
            partes.append(f"[Ref. {i}] Tipo: {payload.get('tipo', 'N/A')} | Área: {payload.get('area', 'N/A')}\n{chunk.get('text', '')[:300]}...")
        return "\n\n".join(partes)

    def _formatar_jurisprudencia(self, chunks: list[dict]) -> str:
        if not chunks:
            return "ATENÇÃO: Nenhuma jurisprudência disponível. NÃO cite precedentes nesta petição."
        partes = []
        for chunk in chunks[:5]:
            payload = chunk.get("payload", {})
            texto = chunk.get("text", "")[:400]
            tribunal = payload.get("tribunal", "[NÃO VERIFICADO]")
            numero = payload.get("numero_processo", "[NÃO VERIFICADO]")
            relator = payload.get("relator", "[NÃO VERIFICADO]")
            data = payload.get("data_julgamento", "[NÃO VERIFICADO]")
            partes.append(f"• {tribunal} — {numero}\n  Relator: {relator} | Data: {data}\n  {texto}")
        return "\n\n".join(partes)

    def _validar_citacoes(self, conteudo: str, jurisprudencia: list[dict]) -> list[str]:
        """Detecta possíveis citações sem fonte — retorna lista de avisos."""
        warnings = []
        if "[NÃO VERIFICADO]" in conteudo:
            warnings.append("Conteúdo contém marcações [NÃO VERIFICADO] — revise as citações")
        if "[COMPLETAR]" in conteudo:
            warnings.append("Conteúdo contém seções [COMPLETAR] — preencha antes de protocolar")
        return warnings

    async def _salvar_documento(self, ctx: AgentContext, conteudo: str, tipo: str, tokens: int, cost: float) -> str:
        from app.models.document import Document, Petition
        doc_id = uuid.uuid4()
        doc = Document(
            id=doc_id,
            tenant_id=ctx.tenant_id,
            process_id=ctx.process_id,
            client_id=ctx.client_id,
            tipo="PETICAO",
            titulo=f"{tipo.replace('_', ' ').title()} — {doc_id}",
            conteudo_texto=conteudo,
            conteudo_html=f"<div class='petition'>{conteudo}</div>",
            status="RASCUNHO",
            gerado_por_ia=True,
            agent_run_id=ctx.run_id,
            created_by=ctx.triggered_by,
        )
        self.db.add(doc)

        petition = Petition(
            document_id=doc_id,
            process_id=ctx.process_id,
            tipo_peticao=tipo,
            template_used=tipo,
            ai_model=settings.DEFAULT_CLAUDE_MODEL,
            ai_tokens_used=tokens,
            review_status="PENDENTE_REVISAO",
        )
        self.db.add(petition)
        await self.db.flush()
        return str(doc_id)

    async def _register_tools(self):
        return []
