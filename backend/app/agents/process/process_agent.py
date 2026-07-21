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
import uuid

from app.agents.base.agent import BaseAgent
from app.agents.base.result import AgentResult, AgentStatus
from app.agents.brain.context import AgentContext
from app.integrations.anthropic_client import call_claude
from app.integrations.tribunais.cnj import CNJDataJudClient
import structlog

log = structlog.get_logger()

# Mapa UF → tribunais relevantes (TJ estadual + TRF regional + TRT regional)
UF_TO_TRIBUNAIS: dict[str, list[str]] = {
    "AC": ["TJAC", "TRF1", "TRT14"],
    "AL": ["TJAL", "TRF5", "TRT19"],
    "AM": ["TJAM", "TRF1", "TRT11"],
    "AP": ["TJAP", "TRF1", "TRT8"],
    "BA": ["TJBA", "TRF1", "TRT5"],
    "CE": ["TJCE", "TRF5", "TRT7"],
    "DF": ["TJDFT", "TRF1", "TRT10"],
    "ES": ["TJES", "TRF2", "TRT17"],
    "GO": ["TJGO", "TRF1", "TRT18"],
    "MA": ["TJMA", "TRF1", "TRT16"],
    "MG": ["TJMG", "TRF1", "TRT3"],
    "MS": ["TJMS", "TRF3", "TRT24"],
    "MT": ["TJMT", "TRF1", "TRT23"],
    "PA": ["TJPA", "TRF1", "TRT8"],
    "PB": ["TJPB", "TRF5", "TRT13"],
    "PE": ["TJPE", "TRF5", "TRT6"],
    "PI": ["TJPI", "TRF1", "TRT22"],
    "PR": ["TJPR", "TRF4", "TRT9"],
    "RJ": ["TJRJ", "TRF2", "TRT1"],
    "RN": ["TJRN", "TRF5", "TRT21"],
    "RO": ["TJRO", "TRF1", "TRT14"],
    "RR": ["TJRR", "TRF1", "TRT11"],
    "RS": ["TJRS", "TRF4", "TRT4"],
    "SC": ["TJSC", "TRF4", "TRT12"],
    "SE": ["TJSE", "TRF5", "TRT20"],
    "SP": ["TJSP", "TRF3", "TRT2"],
    "TO": ["TJTO", "TRF1", "TRT10"],
}


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

    async def _get_db(self):
        """Returns self.db if injected, otherwise creates a new session."""
        if self.db:
            return self.db, False  # (session, owned)
        from app.db.base import AsyncSessionLocal
        session = AsyncSessionLocal()
        await session.begin()
        return session, True  # (session, owned — must close)

    async def _poll_single_process(self, ctx: AgentContext, task: dict) -> AgentResult:
        """Busca andamentos de um processo específico."""
        numero_cnj = task.get("numero_cnj")
        tribunal = task.get("tribunal")

        if not numero_cnj or not tribunal:
            return AgentResult(status=AgentStatus.FAILED, agent_name=self.name, error="numero_cnj e tribunal são obrigatórios")

        client = self._get_tribunal_client(tribunal)

        try:
            movimentos = await client.fetch_movements(numero_cnj)
        except Exception as exc:
            log.error("tribunal_fetch_failed", tribunal=tribunal, numero=numero_cnj, error=str(exc))
            return AgentResult(status=AgentStatus.FAILED, agent_name=self.name, error=str(exc))

        # Resumo IA por movimento é caro no polling em lote (1 chamada × movimento ×
        # todos os processos, a cada 30 min) — só quando POLL_AI_SUMMARY está ligado.
        from app.config import settings
        movimentos_com_resumo = []
        total_tokens = 0
        total_cost = 0.0

        for mov in movimentos:
            resumo = ""
            if settings.POLL_AI_SUMMARY:
                resumo, tokens, _, cost = await self._resumir_movimento({"descricao": mov.descricao})
                total_tokens += tokens
                total_cost += cost
            movimentos_com_resumo.append({
                "data": mov.data.isoformat() if mov.data else None,
                "descricao": mov.descricao,
                "tipo": mov.tipo,
                "documento_url": mov.documento_url,
                "raw_data": mov.raw_data,
                "ai_resumo": resumo,
            })

        # Detectar prazos em movimentos
        prazos_detectados = await self._detectar_prazos(movimentos_com_resumo)

        # Persistir movimentos no banco (retorna quantos são NOVOS)
        process_id = ctx.process_id or (uuid.UUID(task["process_id"]) if task.get("process_id") else None)
        novos = 0
        if process_id and movimentos:
            novos = await self._save_movements(process_id, movimentos, movimentos_com_resumo)

        ctx.set_state("novos_movimentos", novos)
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

    async def _save_movements(self, process_id: uuid.UUID, movimentos, movimentos_com_resumo: list[dict]) -> int:
        """Persiste movimentos novos via importador ÚNICO (dedup canônico, Fase 72)
        e notifica a equipe. Retorna a quantidade de andamentos NOVOS."""
        from sqlalchemy import select
        from app.models.process import LegalProcess
        from app.services.movements_import import importar_movimentos, MovimentoEntrada

        db, owned = await self._get_db()
        novos = 0
        try:
            proc = (await db.execute(
                select(LegalProcess).where(LegalProcess.id == process_id)
            )).scalar_one_or_none()
            if not proc:
                return 0
            entradas = [
                MovimentoEntrada(
                    data=mov.data,
                    descricao=mov.descricao,
                    tipo=mov.tipo or "ANDAMENTO",
                    documento_url=mov.documento_url,
                    raw=str(mov.raw_data) if mov.raw_data else None,
                    ai_summary=enriched.get("ai_resumo") or None,
                )
                for mov, enriched in zip(movimentos, movimentos_com_resumo)
            ]
            resultado = await importar_movimentos(db, proc, entradas, notificar=True)
            novos = resultado["novos"]
            await db.commit()
        except Exception as exc:
            await db.rollback()
            novos = 0
            log.error("save_movements_failed", process_id=str(process_id), error=str(exc))
        finally:
            if owned:
                await db.close()
        return novos

    async def _poll_all_active(self, ctx: AgentContext) -> AgentResult:
        """Polling batch de todos os processos com monitoramento ativo."""
        db, owned = await self._get_db()

        try:
            from sqlalchemy import select
            from app.models.process import LegalProcess
            from app.config import settings

            result = await db.execute(
                select(LegalProcess)
                .where(
                    LegalProcess.monitoring_active == True,
                    LegalProcess.situacao != "ARQUIVADO",
                )
                .order_by(LegalProcess.proximo_prazo_at.asc().nulls_last())
                .limit(settings.PROCESS_POLLING_BATCH_SIZE)
            )
            processos = result.scalars().all()
        finally:
            if owned:
                await db.close()

        polled = 0
        errors = 0
        novos_movimentos = 0
        polled_ids: list[uuid.UUID] = []
        inicio_batch = datetime.now(timezone.utc)

        for processo in processos:
            try:
                sub_ctx = AgentContext(
                    task_type="poll_process",
                    task_input={
                        "action": "poll_process",
                        "numero_cnj": processo.numero_cnj,
                        "tribunal": processo.tribunal,
                        "process_id": str(processo.id),
                    },
                    process_id=processo.id,
                )
                result_poll = await self._poll_single_process(sub_ctx, sub_ctx.task_input)
                if result_poll.succeeded:
                    polled += 1
                    novos_movimentos += sub_ctx.get_state("novos_movimentos", 0)
                    polled_ids.append(processo.id)
                else:
                    errors += 1
            except Exception as exc:
                errors += 1
                log.error("batch_poll_error", processo=str(processo.id), error=str(exc))

        # Uma única sessão para o fechamento do batch (antes: 1 sessão POR processo)
        # — atualiza last_polled_at de todos e registra o SyncRun do ciclo.
        stats = {
            "total_processos": len(processos),
            "polled_ok": polled,
            "errors": errors,
            "novos_movimentos": novos_movimentos,
        }
        try:
            from sqlalchemy import update
            from app.models.process import LegalProcess as LP
            from app.models.sync_run import SyncRun
            from sqlalchemy.ext.asyncio import AsyncSession
            from app.db.base import engine
            async with AsyncSession(engine) as db2:
                if polled_ids:
                    await db2.execute(
                        update(LP).where(LP.id.in_(polled_ids)).values(last_polled_at=datetime.now(timezone.utc))
                    )
                db2.add(SyncRun(
                    tenant_id=None, fonte="datajud", tipo="POLLING",
                    status="OK" if errors == 0 else "ERRO",
                    stats=stats, started_at=inicio_batch,
                    finished_at=datetime.now(timezone.utc),
                ))
                await db2.commit()
        except Exception as exc:
            log.warning("poll_batch_close_failed", error=str(exc))

        return AgentResult(
            status=AgentStatus.SUCCESS,
            agent_name=self.name,
            output={**stats, "polled_at": datetime.now(timezone.utc).isoformat()},
        )

    async def _search_by_oab(self, ctx: AgentContext, task: dict) -> AgentResult:
        """Captura processos por OAB — DELEGA ao serviço consolidado (Fase 72).

        A implementação própria deste agente (sem enriquecimento, sem equipe,
        tribunal fixo) foi aposentada: capturar_por_oab é o caminho único, com
        dedup, responsável/equipe, enriquecimento DataJud e SyncRun."""
        from app.services.oab_capture import capturar_por_oab

        oab = task.get("oab")
        uf = (task.get("uf") or "").upper()
        tenant_id_str = task.get("_tenant_id") or (str(ctx.tenant_id) if ctx.tenant_id else None)
        if not oab or not uf:
            return AgentResult(status=AgentStatus.FAILED, agent_name=self.name, error="oab e uf são obrigatórios")
        if not tenant_id_str:
            return AgentResult(status=AgentStatus.FAILED, agent_name=self.name, error="tenant não identificado")

        db, owned = await self._get_db()
        try:
            resultado = await capturar_por_oab(
                db, uuid.UUID(tenant_id_str),
                dias_retro=int(task.get("dias_retro", 365)),
                triggered_by=ctx.triggered_by,
                apenas_oab=(oab, uf),
            )
        except Exception as exc:
            if owned:
                await db.rollback()
            log.error("search_by_oab_failed", oab=oab, error=str(exc))
            return AgentResult(status=AgentStatus.FAILED, agent_name=self.name, error=str(exc))
        finally:
            if owned:
                await db.close()

        return AgentResult(
            status=AgentStatus.SUCCESS,
            agent_name=self.name,
            output={"oab": oab, "uf": uf, **resultado},
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
        """Detecta prazos em movimentos recentes usando heurística."""
        prazos = []
        for mov in movimentos:
            descricao = mov.get("descricao", "") + " " + mov.get("ai_resumo", "")
            palavras_prazo = ["prazo", "dias", "intimar", "intimação", "citar", "citação", "manifestar", "responder em"]
            if any(p in descricao.lower() for p in palavras_prazo):
                prazos.append({
                    "movimento_data": mov.get("data"),
                    "descricao_prazo": descricao[:200],
                    "detectado_automaticamente": True,
                    "requer_validacao_humana": True,
                })
        return prazos

    def _get_tribunal_client(self, tribunal: str) -> CNJDataJudClient:
        """Retorna cliente DataJud CNJ para o tribunal informado."""
        return CNJDataJudClient(tribunal=tribunal.upper())

    async def _register_tools(self):
        return []
