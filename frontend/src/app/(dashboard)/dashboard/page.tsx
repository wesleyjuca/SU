"use client";
import { useState, useEffect } from "react";
import { Scale, AlertTriangle, CheckSquare, DollarSign, Bot, Activity, Loader2 } from "lucide-react";
import Link from "next/link";

interface Metrics {
  processos_ativos: number;
  prazos_proximos_7d: number;
  aprovacoes_pendentes: number;
  custo_ia_mes: number;
  tokens_ia_mes: number;
  agentes_ativos_24h: number;
  updated_at: string;
}

interface AgentRun {
  id: string;
  agent_name: string;
  status: string;
  created_at: string;
  duration_ms?: number;
}

const AGENT_NAMES = [
  "petition_agent", "review_agent", "process_agent", "court_monitor_agent",
  "jurisprudence_agent", "crm_agent", "financial_agent", "analytics_agent",
  "strategy_agent", "contract_agent", "marketing_agent", "visual_law_agent",
  "ocr_agent", "audit_agent", "compliance_agent", "publication_monitor_agent",
  "innovation_agent", "coding_agent", "orchestration_agent",
];

const AGENT_LABELS: Record<string, string> = {
  petition_agent: "Petição", review_agent: "Revisão", process_agent: "Processo",
  court_monitor_agent: "Tribunais", jurisprudence_agent: "Jurisprudência",
  crm_agent: "CRM", financial_agent: "Financeiro", analytics_agent: "Analytics",
  strategy_agent: "Estratégia", contract_agent: "Contratos", marketing_agent: "Marketing",
  visual_law_agent: "Visual Law", ocr_agent: "OCR", audit_agent: "Auditoria",
  compliance_agent: "Compliance", publication_monitor_agent: "Publicações",
  innovation_agent: "Inovação", coding_agent: "Código", orchestration_agent: "Orquestrador",
};

function AgentDot({ status }: { status: string }) {
  const cls = {
    idle: "agent-idle", running: "agent-running", success: "agent-success",
    error: "agent-error", approval: "agent-approval",
  }[status] ?? "agent-idle";
  return <span className={cls} />;
}

function StatusColor(status: string): string {
  return { RUNNING: "bg-afj-gold", SUCCESS: "bg-green-500", FAILED: "bg-red-500", AWAITING_APPROVAL: "bg-amber-500" }[status] ?? "bg-gray-400";
}

export default function DashboardPage() {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [agentStatus, setAgentStatus] = useState<Record<string, string>>({});

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    const token = localStorage.getItem("afj_access_token");
    if (!token) { setLoading(false); return; }

    const headers = { Authorization: `Bearer ${token}` };
    try {
      const [metricsRes, runsRes] = await Promise.allSettled([
        fetch("/api/v1/system/metrics", { headers }),
        fetch("/api/v1/agents/runs?limit=10", { headers }),
      ]);

      if (metricsRes.status === "fulfilled" && metricsRes.value.ok) {
        setMetrics(await metricsRes.value.json());
      }
      if (runsRes.status === "fulfilled" && runsRes.value.ok) {
        const data = await runsRes.value.json();
        const list: AgentRun[] = Array.isArray(data) ? data : (data.runs ?? []);
        setRuns(list);

        // Build agent status map from recent runs
        const statusMap: Record<string, string> = {};
        for (const run of list) {
          const ag = run.agent_name;
          if (!statusMap[ag]) {
            statusMap[ag] = run.status === "RUNNING" ? "running"
              : run.status === "SUCCESS" ? "success"
              : run.status === "FAILED" ? "error"
              : run.status === "AWAITING_APPROVAL" ? "approval"
              : "idle";
          }
        }
        setAgentStatus(statusMap);
      }
    } finally {
      setLoading(false);
    }
  }

  const kpiValue = (v: number | undefined, prefix = "", suffix = "") =>
    loading ? "..." : v !== undefined ? `${prefix}${v}${suffix}` : "—";

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div>
        <h1 className="font-display text-2xl font-semibold text-afj-black">Dashboard</h1>
        <p className="text-afj-black/50 text-sm mt-0.5">Visão geral do escritório em tempo real</p>
      </div>

      {/* ─── KPI Cards ─────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="kpi-box">
          <div className="flex items-center justify-between">
            <span className="kpi-label">Processos Ativos</span>
            <Scale size={18} className="text-afj-gold" />
          </div>
          <span className="kpi-value">
            {loading ? <Loader2 size={20} className="animate-spin text-afj-gold" /> : (metrics?.processos_ativos ?? "—")}
          </span>
          <span className="text-xs text-afj-black/40">processos monitorados</span>
        </div>

        <div className="kpi-box">
          <div className="flex items-center justify-between">
            <span className="kpi-label">Prazos (7 dias)</span>
            <AlertTriangle size={18} className="text-amber-500" />
          </div>
          <span className={`kpi-value ${(metrics?.prazos_proximos_7d ?? 0) > 0 ? "text-amber-600" : ""}`}>
            {loading ? <Loader2 size={20} className="animate-spin text-amber-500" /> : (metrics?.prazos_proximos_7d ?? "—")}
          </span>
          <span className="text-xs text-afj-black/40">próximos vencimentos</span>
        </div>

        <div className="kpi-box">
          <div className="flex items-center justify-between">
            <span className="kpi-label">Aprovações Pendentes</span>
            <CheckSquare size={18} className="text-red-500" />
          </div>
          <span className={`kpi-value ${(metrics?.aprovacoes_pendentes ?? 0) > 0 ? "text-red-600" : ""}`}>
            {loading ? <Loader2 size={20} className="animate-spin text-red-500" /> : (metrics?.aprovacoes_pendentes ?? "—")}
          </span>
          <span className="text-xs text-afj-black/40">aguardando revisão</span>
        </div>

        <div className="kpi-box">
          <div className="flex items-center justify-between">
            <span className="kpi-label">Custo IA (mês)</span>
            <DollarSign size={18} className="text-afj-gold" />
          </div>
          <span className="kpi-value">
            {loading ? <Loader2 size={20} className="animate-spin text-afj-gold" /> : metrics ? `$${metrics.custo_ia_mes.toFixed(2)}` : "—"}
          </span>
          <span className="text-xs text-afj-black/40">{metrics ? `${metrics.tokens_ia_mes.toLocaleString()} tokens` : "tokens utilizados"}</span>
        </div>
      </div>

      {/* ─── Grid principal ─────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Status dos 19 agentes */}
        <div className="lg:col-span-1 afj-card p-5">
          <div className="flex items-center gap-2 mb-4">
            <Bot size={16} className="text-afj-gold" />
            <h2 className="font-semibold text-sm text-afj-black">Agentes IA</h2>
            <span className="ml-auto text-xs text-afj-black/40">
              {metrics?.agentes_ativos_24h ? `${metrics.agentes_ativos_24h} ativos` : "19 agentes"}
            </span>
          </div>
          <div className="space-y-2">
            {AGENT_NAMES.map((ag) => (
              <div key={ag} className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-2">
                  <AgentDot status={agentStatus[ag] ?? "idle"} />
                  <span className="text-afj-black/80">{AGENT_LABELS[ag] ?? ag}</span>
                </div>
                <span className="text-afj-black/30 text-xs capitalize">{agentStatus[ag] ?? "idle"}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Feed de atividade */}
        <div className="lg:col-span-2 afj-card p-5">
          <div className="flex items-center gap-2 mb-4">
            <Activity size={16} className="text-afj-gold" />
            <h2 className="font-semibold text-sm text-afj-black">Atividade Recente</h2>
            <button onClick={loadData} className="ml-auto text-xs text-afj-black/40 hover:text-afj-gold">
              Atualizar
            </button>
          </div>

          {runs.length > 0 ? (
            <div className="space-y-3">
              {runs.slice(0, 8).map((run) => (
                <div key={run.id} className="flex items-start gap-3 text-sm">
                  <span className={`w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0 ${StatusColor(run.status)}`} />
                  <div className="flex-1 min-w-0">
                    <span className="font-medium text-afj-black/80">[{AGENT_LABELS[run.agent_name] ?? run.agent_name}]</span>{" "}
                    <span className="text-afj-black/60">{run.status}</span>
                    {run.duration_ms && <span className="text-afj-black/30 ml-1">({run.duration_ms}ms)</span>}
                  </div>
                  <span className="text-afj-black/30 text-xs flex-shrink-0">
                    {new Date(run.created_at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="space-y-3">
              {[
                { tipo: "Sistema", msg: "AFJ CORE SYSTEM operacional", color: "bg-green-500" },
                { tipo: "Agentes", msg: "19 agentes carregados e prontos", color: "bg-afj-gold" },
                { tipo: "Banco", msg: "Schema do banco criado e indexado", color: "bg-blue-500" },
                { tipo: "Qdrant", msg: "6 collections de memória institucional criadas", color: "bg-purple-500" },
              ].map((item, i) => (
                <div key={i} className="flex items-start gap-3 text-sm">
                  <span className={`w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0 ${item.color}`} />
                  <div className="flex-1 min-w-0">
                    <span className="font-medium text-afj-black/80">[{item.tipo}]</span>{" "}
                    <span className="text-afj-black/60">{item.msg}</span>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="mt-6 p-4 bg-afj-gold/5 border border-afj-gold/20 rounded-lg">
            <p className="text-sm text-afj-black/70">
              <span className="font-semibold text-afj-black">AFJ CORE SYSTEM</span> está operacional.
              Configure as integrações de tribunal e adicione processos para iniciar o monitoramento automático.
            </p>
            <div className="mt-3 flex gap-2">
              <Link href="/processos" className="btn-afj-primary text-xs py-1.5 px-3 rounded">
                Adicionar Processo
              </Link>
              <Link href="/agentes" className="btn-afj-outline text-xs py-1.5 px-3 rounded">
                Ver Agentes
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
