"""
process_agent — Monitora processos judiciais via polling de tribunais.

Polling agendado via Celery Beat. Detecta:
- Novos andamentos
- Intimações com prazo
- Publicações no DJe
- Novos processos vinculados à OAB cadastrada
"""
from typing import ClassVar
from datetime import datetime, timezone
from app.agents.base.agent import BaseAgent
from app.agents.base.result import AgentResult, AgentStatus
from app.agents.brain.context import AgentContext
from app.integrations.anthropic_client import call_claude, AFJ_LEGAL_SYSTEM_PROMPT
import structlog

log = structlog.get_logger()


class ProcessAgent(BaseAgent):
    name: ClassVar[str] = "process_agent"
    description: ClassVar[str] = "Monitora processos judiciais e detecta andamentos, prazos e intimações"
    requires_human_approval: ClassVar[bool] = False

    async def execute(self, ctx: AgentContext) -> AgentResult:
        task = ctx.task_input
        action = task.get("action", "poll_all")

        if action == "poll_process":
            return await self._poll_single_process(ctx, task)
        elif action == "poll_all":
            return await self._poll_all_active(ctx)
        elif action == "search_by_oab":
            return await self._search_by_oab(ctx, task)
        else:
            return AgentResult(
                status=AgentStatus.FAILED,
                agent_name=self.name,
                error=f"Ação desconhecida: {action}",
            )

    async def _poll_single_process(self, ctx: AgentContext, task: dict) -> AgentResult:
        """Busca andamentos de um processo específico."""
        numero_cnj = task.get("numero_cnj")
        tribunal = task.get("tribunal")

        if not numero_cnj or not tribunal:
            return AgentResult(status=AgentStatus.FAILED, agent_name=self.name, error="numero_cnj e tribunal são obrigatórios")

        # Instanciar conector do tribunal
        client = self._get_tribunal_client(tribunal)
        if not client:
            return AgentResult(
                status=AgentStatus.PARTIAL,
                agent_name=self.name,
                output={"aviso": f"Conector para {tribunal} ainda não implementado"},
            )

        try:
            movimentos = await client.fetch_movements(numero_cnj)
        except Exception as exc:
            log.error("tribunal_fetch_failed", tribunal=tribunal, numero=numero_cnj, error=str(exc))
            return AgentResult(status=AgentStatus.FAILED, agent_name=self.name, error=str(exc))

        # Gerar sumários com IA para cada movimento
        movimentos_com_resumo = []
        total_tokens = 0
        total_cost = 0.0

        for mov in movimentos:
            resumo, tokens, _, cost = await self._resumir_movimento(mov)
            total_tokens += tokens
            total_cost += cost
            movimentos_com_resumo.append({**mov, "ai_resumo": resumo})

        # Detectar prazos em movimentos
        prazos_detectados = await self._detectar_prazos(movimentos_com_resumo)

        ctx.set_state("novos_movimentos", len(movimentos))
        ctx.set_state("prazos_detectados", len(prazos_detectados))

        return AgentResult(
            status=AgentStatus.SUCCESS,
            agent_name=self.name,
            output={
                "numero_cnj": numero_cnj,
                "tribunal": tribunal,
                "movimentos": movimentos_com_resumo,
                "prazos": prazos_detectados,
                "polled_at": datetime.now(timezone.utc).isoformat(),
            },
            tokens_used=total_tokens,
            cost_usd=total_cost,
        )

    async def _poll_all_active(self, ctx: AgentContext) -> AgentResult:
        """Polling batch de todos os processos com monitoramento ativo."""
        if not self.db:
            return AgentResult(status=AgentStatus.FAILED, agent_name=self.name, error="DB não disponível")

        from sqlalchemy import select, func
        from app.models.process import LegalProcess
        from app.config import settings

        result = await self.db.execute(
            select(LegalProcess)
            .where(
                LegalProcess.monitoring_active == True,
                LegalProcess.situacao != "ARQUIVADO",
            )
            .order_by(LegalProcess.proximo_prazo_at.asc().nulls_last())
            .limit(settings.PROCESS_POLLING_BATCH_SIZE)
        )
        processos = result.scalars().all()

        polled = 0
        errors = 0
        novos_movimentos = 0

        for processo in processos:
            try:
                sub_ctx = AgentContext(
                    task_type="poll_process",
                    task_input={
                        "action": "poll_process",
                        "numero_cnj": processo.numero_cnj,
                        "tribunal": processo.tribunal,
                    },
                    process_id=processo.id,
                )
                result_poll = await self._poll_single_process(sub_ctx, sub_ctx.task_input)
                if result_poll.succeeded:
                    polled += 1
                    novos_movimentos += sub_ctx.get_state("novos_movimentos", 0)
                    # Atualizar last_polled_at
                    processo.last_polled_at = datetime.now(timezone.utc)
                else:
                    errors += 1
            except Exception as exc:
                errors += 1
                log.error("batch_poll_error", processo=str(processo.id), error=str(exc))

        return AgentResult(
            status=AgentStatus.SUCCESS,
            agent_name=self.name,
            output={
                "total_processos": len(processos),
                "polled_ok": polled,
                "errors": errors,
                "novos_movimentos": novos_movimentos,
                "polled_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    async def _search_by_oab(self, ctx: AgentContext, task: dict) -> AgentResult:
        """Busca processos vinculados a uma OAB específica."""
        oab = task.get("oab")
        uf = task.get("uf", "")
        tribunal = task.get("tribunal")

        client = self._get_tribunal_client(tribunal) if tribunal else None
        if not client:
            return AgentResult(
                status=AgentStatus.PARTIAL,
                agent_name=self.name,
                output={"aviso": f"Busca por OAB para {tribunal} não disponível ainda"},
            )

        processos = await client.search_by_oab(oab, uf)
        return AgentResult(
            status=AgentStatus.SUCCESS,
            agent_name=self.name,
            output={"oab": oab, "processos_encontrados": processos},
        )

    async def _resumir_movimento(self, movimento: dict) -> tuple[str, int, int, float]:
        """Gera resumo IA de um andamento processual (2-3 frases)."""
        descricao = movimento.get("descricao", "")
        if not descricao or len(descricao) < 50:
            return descricao, 0, 0, 0.0

        content, input_t, output_t, cost = await call_claude(
            messages=[{"role": "user", "content": f"Resuma este andamento processual em 2-3 frases objetivas para um advogado:\n\n{descricao[:2000]}"}],
            system="Você é assistente jurídico. Seja objetivo e técnico. Destaque prazos e obrigações.",
            max_tokens=200,
        )
        return content, input_t + output_t, output_t, cost

    async def _detectar_prazos(self, movimentos: list[dict]) -> list[dict]:
        """Detecta prazos em movimentos recentes usando IA."""
        prazos = []
        for mov in movimentos:
            descricao = mov.get("descricao", "") + " " + mov.get("ai_resumo", "")
            # Heurística simples — expansão futura com NLP especializado
            palavras_prazo = ["prazo", "dias", "intimar", "intimação", "citar", "citação", "manifestar", "responder em"]
            if any(p in descricao.lower() for p in palavras_prazo):
                prazos.append({
                    "movimento_data": mov.get("data"),
                    "descricao_prazo": descricao[:200],
                    "detectado_automaticamente": True,
                    "requer_validacao_humana": True,
                })
        return prazos

    def _get_tribunal_client(self, tribunal: str):
        """Retorna o conector correto para o tribunal."""
        from app.integrations.tribunais.base import BaseTribunalClient
        # Mapeamento de conectores disponíveis (implementados progressivamente)
        conectores = {
            # "PJE": PJeClient,
            # "ESAJ": ESAJClient,
        }
        client_class = conectores.get(tribunal.upper())
        return client_class() if client_class else None

    async def _register_tools(self):
        return []
