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

        # Gerar sumários com IA para cada movimento
        movimentos_com_resumo = []
        total_tokens = 0
        total_cost = 0.0

        for mov in movimentos:
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

        # Persistir movimentos no banco
        process_id = ctx.process_id or (uuid.UUID(task["process_id"]) if task.get("process_id") else None)
        if process_id and movimentos:
            await self._save_movements(process_id, movimentos, movimentos_com_resumo)

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

    async def _save_movements(self, process_id: uuid.UUID, movimentos, movimentos_com_resumo: list[dict]):
        """Persiste movimentos no ProcessMovement evitando duplicatas."""
        from sqlalchemy import select
        from app.models.process import ProcessMovement

        db, owned = await self._get_db()
        try:
            for mov, enriched in zip(movimentos, movimentos_com_resumo):
                # Evitar duplicatas por data + descrição
                existing = await db.execute(
                    select(ProcessMovement).where(
                        ProcessMovement.process_id == process_id,
                        ProcessMovement.data_movimento == mov.data,
                        ProcessMovement.descricao == mov.descricao,
                    )
                )
                if existing.scalar_one_or_none():
                    continue

                pm = ProcessMovement(
                    process_id=process_id,
                    data_movimento=mov.data,
                    descricao=mov.descricao,
                    tipo=mov.tipo,
                    documento_url=mov.documento_url,
                    raw_html=str(mov.raw_data) if mov.raw_data else None,
                    ai_summary=enriched.get("ai_resumo"),
                )
                db.add(pm)
            await db.commit()
        except Exception as exc:
            await db.rollback()
            log.error("save_movements_failed", process_id=str(process_id), error=str(exc))
        finally:
            if owned:
                await db.close()

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
                    # Atualizar last_polled_at
                    db2, owned2 = await self._get_db()
                    try:
                        from sqlalchemy import update
                        from app.models.process import LegalProcess as LP
                        await db2.execute(
                            update(LP).where(LP.id == processo.id).values(last_polled_at=datetime.now(timezone.utc))
                        )
                        await db2.commit()
                    finally:
                        if owned2:
                            await db2.close()
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
        """Busca processos vinculados a uma OAB específica e salva no banco."""
        oab = task.get("oab")
        uf = task.get("uf", "")
        tribunal = task.get("tribunal")
        tenant_id_str = task.get("_tenant_id")

        if not oab:
            return AgentResult(status=AgentStatus.FAILED, agent_name=self.name, error="oab é obrigatório")

        # Se tribunal específico fornecido, busca nele; caso contrário busca em todos os tribunais da UF
        if tribunal:
            tribunais_busca = [tribunal.upper()]
        else:
            uf_upper = uf.upper() if uf else ""
            tribunais_busca = UF_TO_TRIBUNAIS.get(uf_upper, [f"TJ{uf_upper}"] if uf_upper else ["TJSP"])

        todos_processos: list[str] = []
        for trib in tribunais_busca:
            client = self._get_tribunal_client(trib)
            try:
                processos = await client.search_by_oab(oab, uf)
                todos_processos.extend(processos)
            except Exception as exc:
                log.warning("oab_search_tribunal_failed", tribunal=trib, oab=oab, error=str(exc))

        # Persistir processos encontrados
        salvos = 0
        if todos_processos and tenant_id_str:
            salvos = await self._save_processes_from_oab(
                processos_numeros=todos_processos,
                tribunal=tribunais_busca[0] if len(tribunais_busca) == 1 else "VÁRIOS",
                oab=oab,
                uf=uf,
                tenant_id=uuid.UUID(tenant_id_str),
            )

        return AgentResult(
            status=AgentStatus.SUCCESS,
            agent_name=self.name,
            output={
                "oab": oab,
                "uf": uf,
                "processos_encontrados": len(todos_processos),
                "processos_salvos": salvos,
                "numeros_cnj": todos_processos[:50],  # limita payload
            },
        )

    async def _save_processes_from_oab(
        self,
        processos_numeros: list[str],
        tribunal: str,
        oab: str,
        uf: str,
        tenant_id: uuid.UUID,
    ) -> int:
        """Persiste processos encontrados por OAB no banco, evitando duplicatas."""
        from sqlalchemy import select
        from app.models.process import LegalProcess

        db, owned = await self._get_db()
        salvos = 0
        try:
            for numero_cnj in processos_numeros:
                if not numero_cnj:
                    continue
                existing = await db.execute(
                    select(LegalProcess).where(
                        LegalProcess.numero_cnj == numero_cnj,
                        LegalProcess.tenant_id == tenant_id,
                    )
                )
                if existing.scalar_one_or_none():
                    continue

                processo = LegalProcess(
                    tenant_id=tenant_id,
                    numero_cnj=numero_cnj,
                    tribunal=tribunal if tribunal != "VÁRIOS" else f"TJ{uf.upper()}",
                    uf=uf.upper() if uf else None,
                    situacao="ATIVO",
                    oab_responsavel=oab,
                    monitoring_active=True,
                    metadata_json={"fonte_captura": "OAB", "oab_origem": oab},
                )
                db.add(processo)
                salvos += 1
            await db.commit()
        except Exception as exc:
            await db.rollback()
            log.error("save_processes_from_oab_failed", oab=oab, error=str(exc))
        finally:
            if owned:
                await db.close()
        return salvos

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
