"use client";
import { useEffect, useRef, useState } from "react";
import { Play, Loader2, XCircle, Sparkles, Plus, CheckCircle2, Circle, AlertCircle, BookOpen } from "lucide-react";
import { AgentStatusCard } from "@/components/agents/AgentStatusCard";
import { AgentDetailDrawer } from "@/components/agents/AgentDetailDrawer";
import { ProposeCustomAgentModal } from "@/components/agents/ProposeCustomAgentModal";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { useToast } from "@/components/ui/Toast";
import { useUserStore } from "@/store";
import { api } from "@/lib/api";
import { useAgentStatus } from "@/hooks/useAgentStatus";
import type { AgentCardData } from "@/components/agents/AgentStatusCard";

interface CustomAgent {
  id: string;
  name: string;
  description: string;
}

function CustomAgentCard({ agent }: { agent: CustomAgent }) {
  const toast = useToast();
  const [instrucao, setInstrucao] = useState("");
  const [executando, setExecutando] = useState(false);

  async function executar() {
    setExecutando(true);
    try {
      const data = await api.post<{ run_id: string }>("/agents/trigger", {
        task_type: "run_custom_agent",
        task_input: { custom_agent_id: agent.id, descricao: instrucao || undefined },
      });
      toast.success(`Execução iniciada: ${data.run_id}`);
      setInstrucao("");
    } catch (err: any) {
      toast.error(err?.message || "Erro ao executar agente.");
    } finally {
      setExecutando(false);
    }
  }

  return (
    <div className="afj-card p-4 flex flex-col gap-3">
      <div className="flex items-start gap-2">
        <div className="w-8 h-8 rounded-lg bg-afj-gold/10 flex items-center justify-center flex-shrink-0">
          <Sparkles size={14} className="text-afj-gold" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-sm text-afj-black truncate">{agent.name}</p>
          <p className="text-xs text-afj-black/50 mt-0.5 line-clamp-2">{agent.description}</p>
        </div>
      </div>
      <input
        value={instrucao}
        onChange={(e) => setInstrucao(e.target.value)}
        placeholder="Instrução para esta execução (opcional)"
        className="w-full px-2.5 py-1.5 text-xs border border-afj-cream-dark rounded-sm focus:outline-none focus:border-afj-gold"
      />
      <button
        onClick={executar}
        disabled={executando}
        className="w-full flex items-center justify-center gap-1.5 py-1.5 rounded text-xs font-medium bg-afj-cream hover:bg-afj-gold/10 text-afj-black/60 hover:text-afj-gold disabled:opacity-50 transition-colors"
      >
        {executando ? <Loader2 size={10} className="animate-spin" /> : <Play size={10} />}
        {executando ? "Iniciando..." : "Executar"}
      </button>
    </div>
  );
}

const AGENTS: AgentCardData[] = [
  { name: "orchestration_agent", label: "Orquestrador", desc: "Coordena todos os agentes", category: "CORE" },
  { name: "petition_agent", label: "Petição", desc: "Gera petições jurídicas com Claude", category: "JURIDICO" },
  { name: "review_agent", label: "Revisão", desc: "Revisão jurídica em 4 etapas", category: "JURIDICO" },
  { name: "process_agent", label: "Processo", desc: "Monitora andamentos processuais", category: "JURIDICO" },
  { name: "court_monitor_agent", label: "Tribunais", desc: "Monitora tribunais e publica DJe", category: "MONITORAMENTO" },
  { name: "publication_monitor_agent", label: "Publicações", desc: "Scan de Diários Oficiais", category: "MONITORAMENTO" },
  { name: "jurisprudence_agent", label: "Jurisprudência", desc: "Busca precedentes verificáveis", category: "JURIDICO" },
  { name: "strategy_agent", label: "Estratégia", desc: "Análise estratégica jurídica", category: "JURIDICO" },
  { name: "crm_agent", label: "CRM", desc: "Gestão de clientes e leads", category: "NEGOCIOS" },
  { name: "contract_agent", label: "Contratos", desc: "Geração e gestão de contratos", category: "JURIDICO" },
  { name: "financial_agent", label: "Financeiro", desc: "Gestão financeira e honorários", category: "NEGOCIOS" },
  { name: "marketing_agent", label: "Marketing", desc: "Captação e campanhas", category: "NEGOCIOS" },
  { name: "analytics_agent", label: "Analytics", desc: "Relatórios e insights", category: "ANALISE" },
  { name: "visual_law_agent", label: "Visual Law", desc: "Fluxogramas e timelines jurídicas", category: "JURIDICO" },
  { name: "ocr_agent", label: "OCR", desc: "Digitalização e extração de documentos", category: "SUPORTE" },
  { name: "audit_agent", label: "Auditoria", desc: "Revisão de logs e compliance", category: "SUPORTE" },
  { name: "compliance_agent", label: "Compliance", desc: "Verificações LGPD e regulatórias", category: "SUPORTE" },
  { name: "innovation_agent", label: "Inovação", desc: "Propõe melhorias ao sistema", category: "SUPORTE" },
  { name: "coding_agent", label: "Código", desc: "Geração e correção de código", category: "SUPORTE" },
];

// Fase 169.1 — chains reais (TASK_ROUTE_MAP em router.py), antes inalcançáveis
// pela UI (só rodavam via chamada direta à API, e mesmo assim truncavam pro
// primeiro agente).
const CHAIN_TASK_TYPES: { value: string; label: string }[] = [
  { value: "new_process_intake", label: "Entrada de novo processo (processo → jurisprudência → estratégia → CRM)" },
  { value: "generate_and_review_petition", label: "Gerar e revisar petição (jurisprudência → petição → revisão)" },
  { value: "full_contract_flow", label: "Fluxo completo de contrato (contrato → revisão)" },
];

interface RunStep {
  step_number: number;
  step_name: string | null;
  status: string;
  duration_ms: number | null;
}

const CATEGORY_COLORS: Record<string, string> = {
  CORE: "bg-afj-gold/10 text-afj-gold border-afj-gold/20",
  JURIDICO: "bg-blue-50 text-blue-700 border-blue-100",
  MONITORAMENTO: "bg-purple-50 text-purple-700 border-purple-100",
  NEGOCIOS: "bg-green-50 text-green-700 border-green-100",
  ANALISE: "bg-orange-50 text-orange-700 border-orange-100",
  SUPORTE: "bg-gray-50 text-gray-700 border-gray-100",
};

export default function AgentesPage() {
  const toast = useToast();
  const user = useUserStore((s) => s.user);
  const isSuperadmin = user?.role === "SUPERADMIN";
  const podePropoAgente = ["ADMIN", "SOCIO", "SUPERADMIN"].includes(user?.role ?? "");
  // Fase 216 — gate próprio (não reaproveita podePropoAgente, que é sobre
  // um assunto diferente: propor agente customizado).
  const podeEditarPlaybook = ["ADMIN", "SOCIO", "GESTOR"].includes(user?.role ?? "");
  const [playbooks, setPlaybooks] = useState<{ id: string; area_direito: string; texto: string }[]>([]);
  const [areaSelecionada, setAreaSelecionada] = useState("CIVIL");
  const [textoPlaybook, setTextoPlaybook] = useState("");
  const [salvandoPlaybook, setSalvandoPlaybook] = useState(false);
  const [detailAgent, setDetailAgent] = useState<string | null>(null);
  const [mostrarPropor, setMostrarPropor] = useState(false);
  const [customAgents, setCustomAgents] = useState<CustomAgent[]>([]);
  const [taskType, setTaskType] = useState("generate_petition");
  const [taskDesc, setTaskDesc] = useState("");
  const [arquivosInput, setArquivosInput] = useState("");
  const [result, setResult] = useState<string | null>(null);
  const [triggering, setTriggering] = useState<string | null>(null);
  const [lastRunId, setLastRunId] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [runSteps, setRunSteps] = useState<RunStep[] | null>(null);
  const [runStatus, setRunStatus] = useState<string | null>(null);
  const [lastRunWasChain, setLastRunWasChain] = useState(false);
  const isChain = CHAIN_TASK_TYPES.some((c) => c.value === taskType);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Fase 196 — resposta de IA em streaming: só populado pra disparo direto
  // (não-chain); o backend nem publica o evento pra chains multi-passo.
  const { streamingText } = useAgentStatus();
  const streamedContent = lastRunId ? streamingText[lastRunId] : undefined;

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  // Fase 176.4 — achado da Fase 175: o banner de resultado ("Run iniciado:
  // X") nunca era atualizado pra disparos de agente único (não-chain) — só
  // a lista de passos de uma chain reagia ao polling. Agora o próprio
  // banner reflete o status terminal de QUALQUER run, chain ou não.
  useEffect(() => {
    if (!runStatus || !lastRunId) return;
    if (runStatus === "SUCCESS") setResult(`Run ${lastRunId} concluído com sucesso.`);
    else if (runStatus === "FAILED") setResult(`Run ${lastRunId} falhou.`);
    else if (runStatus === "AWAITING_APPROVAL") setResult(`Run ${lastRunId} aguardando aprovação humana.`);
    else if (runStatus === "CANCELADO") setResult(`Run ${lastRunId} cancelado.`);
  }, [runStatus, lastRunId]);

  function pollRunSteps(runId: string) {
    if (pollRef.current) clearInterval(pollRef.current);
    let attempts = 0;
    const token = localStorage.getItem("afj_access_token");
    pollRef.current = setInterval(async () => {
      if (++attempts > 60) {
        if (pollRef.current) clearInterval(pollRef.current);
        return;
      }
      try {
        const res = await fetch(`/api/v1/agents/runs/${runId}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          const run = await res.json();
          setRunStatus(run.status);
          setRunSteps(run.steps ?? null);
          if (["SUCCESS", "FAILED", "AWAITING_APPROVAL", "CANCELADO"].includes(run.status)) {
            if (pollRef.current) clearInterval(pollRef.current);
          }
        }
      } catch {
        // fail-soft: só para de atualizar os passos, não quebra a página
      }
    }, 3000);
  }

  // Fase 205.5 — chamado quando trigger falha com 429 (teto de IA atingido).
  // Notifica ADMIN/SÓCIO/SUPERADMIN do escritório em vez de deixar o usuário
  // ter que pedir o aumento fora do sistema.
  async function solicitarAumentoOrcamento() {
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/system/ai-budget/request-increase", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const d = await res.json().catch(() => ({}));
      if (res.ok) toast.success(d.message || "Solicitação de aumento enviada.");
    } catch {
      // fail-soft: o toast do erro 429 original já foi mostrado
    }
  }

  async function triggerAgent(agentName: string) {
    setResult(null);
    setLastRunId(null);
    setRunSteps(null);
    setRunStatus(null);
    setLastRunWasChain(false);
    setTriggering(agentName);
    try {
      const token = localStorage.getItem("afj_access_token");
      const task_input: Record<string, unknown> = { descricao: taskDesc || `Tarefa via agente ${agentName}` };
      if (taskType === "generate_code" && arquivosInput.trim()) {
        task_input.arquivos = arquivosInput.split(",").map((s) => s.trim()).filter(Boolean);
      }
      const res = await fetch("/api/v1/agents/trigger", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          task_type: taskType,
          task_input,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setLastRunId(data.run_id);
        setResult(`Run iniciado: ${data.run_id}`);
        setLastRunWasChain(isChain);
        pollRunSteps(data.run_id);
      } else if (res.status === 429) {
        // Fase 205.5 — antes mostrava só "Erro ao iniciar agente: 429",
        // perdendo a mensagem real do bloqueio de orçamento. Agora mostra o
        // motivo de verdade e já dispara a solicitação de aumento pro
        // ADMIN/SÓCIO, sem exigir que o usuário saia da tela pra pedir.
        const d = await res.json().catch(() => ({}));
        toast.error(d.detail || "Limite mensal de IA atingido.");
        solicitarAumentoOrcamento();
      } else {
        toast.error(`Erro ao iniciar agente: ${res.status}`);
      }
    } catch {
      toast.error("Erro de conexão ao iniciar agente.");
    } finally {
      setTriggering(null);
    }
  }

  async function cancelarRun() {
    if (!lastRunId) return;
    setCancelling(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/agents/runs/${lastRunId}/cancel`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        if (pollRef.current) clearInterval(pollRef.current);
        setResult(`Execução ${lastRunId} cancelada.`);
        setLastRunId(null);
        setRunSteps(null);
        setRunStatus(null);
      } else {
        const data = await res.json().catch(() => ({}));
        toast.error(data.detail || "Não foi possível cancelar a execução.");
      }
    } catch {
      toast.error("Erro de conexão ao cancelar.");
    } finally {
      setCancelling(false);
    }
  }

  const categories = [...new Set(AGENTS.map((a) => a.category))];

  async function carregarCustomAgents() {
    try {
      const data = await api.get<CustomAgent[]>("/custom-agents?status=APROVADO");
      setCustomAgents(data);
    } catch {
      // fail-soft: seção de agentes customizados simplesmente não aparece
    }
  }

  useEffect(() => {
    carregarCustomAgents();
  }, []);

  // Fase 216 — playbooks de agentes por área.
  async function carregarPlaybooks() {
    try {
      const data = await api.get<{ id: string; area_direito: string; texto: string }[]>("/playbooks");
      setPlaybooks(data);
    } catch {
      // fail-soft: seção de playbooks simplesmente não aparece
    }
  }

  useEffect(() => {
    carregarPlaybooks();
  }, []);

  useEffect(() => {
    const atual = playbooks.find((p) => p.area_direito === areaSelecionada);
    setTextoPlaybook(atual?.texto ?? "");
  }, [areaSelecionada, playbooks]);

  async function salvarPlaybook() {
    setSalvandoPlaybook(true);
    try {
      await api.post("/playbooks", { area_direito: areaSelecionada, texto: textoPlaybook });
      await carregarPlaybooks();
      toast.success("Orientação salva.");
    } catch {
      toast.error("Erro ao salvar orientação. Tente novamente.");
    } finally {
      setSalvandoPlaybook(false);
    }
  }

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Agentes IA" }]} />
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-semibold text-afj-black">Agentes IA</h1>
          <p className="text-afj-black/50 text-sm">19 agentes especializados — {AGENTS.length} disponíveis</p>
        </div>
        {podePropoAgente && (
          <button
            onClick={() => setMostrarPropor(true)}
            className="btn-afj-outline rounded-md flex items-center gap-1.5 whitespace-nowrap"
          >
            <Plus size={14} />
            Propor Agente
          </button>
        )}
      </div>

      {result && (
        <div className="bg-green-50 border border-green-200 text-green-800 rounded-lg px-4 py-3 text-sm flex items-center justify-between gap-3">
          <span>{result}</span>
          {lastRunId && (
            <button
              onClick={cancelarRun}
              disabled={cancelling}
              className="flex items-center gap-1.5 text-red-600 hover:text-red-700 font-medium disabled:opacity-40 whitespace-nowrap"
            >
              {cancelling ? <Loader2 size={14} className="animate-spin" /> : <XCircle size={14} />}
              Cancelar execução
            </button>
          )}
        </div>
      )}

      {/* Fase 196 — resposta de IA ao vivo, pedaço a pedaço, pra disparo
          direto (não-chain). Some assim que o run termina (streamingText
          é limpo em AGENT_RUN_COMPLETED, ver useAgentStatus). */}
      {streamedContent && !lastRunWasChain && (
        <div className="afj-card p-4 space-y-2">
          <h3 className="text-xs font-semibold text-afj-black/50 uppercase tracking-wider flex items-center gap-1.5">
            <Sparkles size={12} className="text-afj-gold" />
            Resposta em andamento
          </h3>
          <p className="text-sm text-afj-black/80 whitespace-pre-wrap leading-relaxed">{streamedContent}</p>
        </div>
      )}

      {/* Fase 169.1/169.2 — progresso passo-a-passo de uma chain (só aparece
          quando o run é multi-agente; AgentStep é gravado 1 linha por
          passo). Passos após um gate HITL retomam automaticamente depois
          da aprovação (169.2) — este painel só não reflete isso ao vivo se
          a aprovação acontecer numa aba/sessão diferente da que disparou. */}
      {lastRunWasChain && runSteps && runSteps.length > 0 && (
        <div className="afj-card p-4 space-y-2">
          <h3 className="text-xs font-semibold text-afj-black/50 uppercase tracking-wider">
            Progresso da cadeia ({runSteps.length} {runSteps.length === 1 ? "passo" : "passos"})
          </h3>
          <ol className="space-y-1.5">
            {runSteps.map((s) => (
              <li key={s.step_number} className="flex items-center gap-2 text-sm">
                {s.status === "SUCCESS" ? (
                  <CheckCircle2 size={14} className="text-green-600 flex-shrink-0" />
                ) : s.status === "FAILED" ? (
                  <AlertCircle size={14} className="text-red-600 flex-shrink-0" />
                ) : (
                  <Circle size={14} className="text-afj-black/30 flex-shrink-0" />
                )}
                <span className="text-afj-black/40">{s.step_number + 1}.</span>
                <span className="text-afj-black">{s.step_name}</span>
                {s.duration_ms != null && (
                  <span className="text-afj-black/40 text-xs">({(s.duration_ms / 1000).toFixed(1)}s)</span>
                )}
              </li>
            ))}
          </ol>
          {runStatus === "AWAITING_APPROVAL" && (
            <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2.5 py-1.5 mt-2">
              Aguardando aprovação humana em /aprovacoes. Os passos seguintes da
              cadeia (se houver) continuam automaticamente assim que for aprovada.
            </p>
          )}
        </div>
      )}

      {/* Painel de disparo rápido */}
      <div className="afj-card-premium p-5">
        <h2 className="font-semibold text-sm text-afj-black mb-3 flex items-center gap-2">
          <Play size={14} className="text-afj-gold" />
          Disparar Tarefa
        </h2>
        <div className="space-y-3">
          <div className="flex gap-3 flex-wrap">
            <select
              value={taskType}
              onChange={(e) => setTaskType(e.target.value)}
              className="border border-afj-cream-dark rounded-md px-3 py-2 text-sm text-afj-black bg-white focus:outline-none focus:border-afj-gold"
            >
              <option value="generate_petition">Gerar Petição</option>
              <option value="review_document">Revisar Documento</option>
              <option value="search_jurisprudence">Buscar Jurisprudência</option>
              <option value="monitor_process">Monitorar Processo</option>
              <option value="generate_strategy">Gerar Estratégia</option>
              <option value="analytics_report">Relatório Analytics</option>
              <option value="audit_review">Revisão de Auditoria</option>
              <option value="compliance_check">Verificação de Compliance</option>
              <option value="innovation_proposal">Proposta de Inovação</option>
              <option value="generate_code">Gerar Código</option>
              <option value="marketing_campaign">Campanha de Marketing</option>
              <optgroup label="Fluxos encadeados">
                {CHAIN_TASK_TYPES.map((c) => (
                  <option key={c.value} value={c.value}>{c.label}</option>
                ))}
              </optgroup>
            </select>
            <button
              onClick={() => triggerAgent("orchestration_agent")}
              disabled={!!triggering}
              className="btn-afj-primary rounded-md disabled:opacity-50 flex items-center gap-2"
            >
              {triggering ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  Iniciando...
                </>
              ) : "Executar via Orquestrador"}
            </button>
          </div>
          <div>
            <label className="text-xs text-afj-black/60 block mb-1">Descrição da tarefa (opcional)</label>
            <input
              value={taskDesc}
              onChange={(e) => setTaskDesc(e.target.value)}
              placeholder="Descreva o que o agente deve executar..."
              className="w-full border border-afj-cream-dark rounded-md px-3 py-2 text-sm focus:outline-none focus:border-afj-gold bg-white"
            />
          </div>
          {taskType === "generate_code" && (
            <div>
              <label className="text-xs text-afj-black/60 block mb-1">
                Arquivos de contexto (opcional, caminhos relativos separados por vírgula — ex: backend/app/agents/coding/coding_agent.py)
              </label>
              <input
                value={arquivosInput}
                onChange={(e) => setArquivosInput(e.target.value)}
                placeholder="backend/app/..., frontend/src/..."
                className="w-full border border-afj-cream-dark rounded-md px-3 py-2 text-sm focus:outline-none focus:border-afj-gold bg-white"
              />
            </div>
          )}
        </div>
      </div>

      {/* Fase 216 — Playbooks de agentes por área */}
      <div className="afj-card-premium p-5">
        <h2 className="font-semibold text-sm text-afj-black mb-3 flex items-center gap-2">
          <BookOpen size={14} className="text-afj-gold" />
          Playbooks por Área
        </h2>
        <p className="text-xs text-afj-black/50 mb-3">
          Orientação/checklist do escritório, injetada automaticamente na análise estratégica (&quot;Gerar Estratégia&quot;) sempre que a área bater.
        </p>
        <div className="space-y-3">
          <select
            value={areaSelecionada}
            onChange={(e) => setAreaSelecionada(e.target.value)}
            className="border border-afj-cream-dark rounded-md px-3 py-2 text-sm text-afj-black bg-white focus:outline-none focus:border-afj-gold"
          >
            {["CIVIL", "TRABALHISTA", "TRIBUTARIO", "PENAL", "PREVIDENCIARIO", "CONSUMIDOR"].map((a) => (
              <option key={a} value={a}>{a}</option>
            ))}
          </select>
          <textarea
            value={textoPlaybook}
            onChange={(e) => setTextoPlaybook(e.target.value)}
            readOnly={!podeEditarPlaybook}
            placeholder={podeEditarPlaybook ? "Ex: sempre checar prescrição antes de propor a tese principal..." : "Nenhuma orientação cadastrada pra esta área."}
            rows={3}
            className={`w-full border border-afj-cream-dark rounded-md px-3 py-2 text-sm focus:outline-none focus:border-afj-gold ${podeEditarPlaybook ? "bg-white" : "bg-afj-cream/40"}`}
          />
          {podeEditarPlaybook && (
            <button
              onClick={salvarPlaybook}
              disabled={salvandoPlaybook}
              className="btn-afj-primary rounded-md disabled:opacity-50"
            >
              {salvandoPlaybook ? "Salvando..." : "Salvar orientação"}
            </button>
          )}
          {playbooks.length > 0 && (
            <div className="pt-2 border-t border-afj-cream-dark">
              <p className="text-[10px] uppercase tracking-wide text-afj-black/40 mb-1.5">Áreas com orientação cadastrada</p>
              <div className="flex flex-wrap gap-1.5">
                {playbooks.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => setAreaSelecionada(p.area_direito)}
                    className="text-xs px-2 py-1 rounded-full bg-afj-cream border border-afj-cream-dark hover:border-afj-gold transition-colors"
                    title={p.texto.slice(0, 120)}
                  >
                    {p.area_direito}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Grid de agentes por categoria */}
      {categories.map((cat) => (
        <div key={cat}>
          <h2 className="text-xs font-semibold text-afj-black/40 uppercase tracking-wider mb-3">{cat}</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {/* Sem onTrigger: o botão dos cartões disparava o task_type do
                seletor global (clicar em OCR gerava petição). O disparo agora
                é feito apenas pelo painel "Disparar Tarefa". Clique no card
                abre o detalhe de prompt/anexos, só pra SUPERADMIN. */}
            {AGENTS.filter((a) => a.category === cat).map((agent) => (
              <AgentStatusCard
                key={agent.name}
                agent={agent}
                categoryColor={CATEGORY_COLORS[agent.category]}
                onOpenDetail={isSuperadmin ? setDetailAgent : undefined}
              />
            ))}
          </div>
        </div>
      ))}

      {/* Agentes customizados aprovados — propostos por ADMIN, aprovados pelo SUPERADMIN */}
      {customAgents.length > 0 && (
        <div>
          <h2 className="text-xs font-semibold text-afj-black/40 uppercase tracking-wider mb-3 flex items-center gap-1.5">
            <Sparkles size={12} className="text-afj-gold" />
            Agentes Customizados
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {customAgents.map((agent) => (
              <CustomAgentCard key={agent.id} agent={agent} />
            ))}
          </div>
        </div>
      )}

      {detailAgent && (
        <AgentDetailDrawer agentName={detailAgent} onClose={() => setDetailAgent(null)} />
      )}

      {mostrarPropor && (
        <ProposeCustomAgentModal
          onClose={() => setMostrarPropor(false)}
          onProposed={carregarCustomAgents}
        />
      )}
    </div>
  );
}
