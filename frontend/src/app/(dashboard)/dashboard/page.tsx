"use client";
import { Scale, AlertTriangle, CheckSquare, DollarSign, Bot, Activity } from "lucide-react";

const AGENT_NAMES = [
  { name: "petition_agent", label: "Petição", status: "idle" },
  { name: "review_agent", label: "Revisão", status: "idle" },
  { name: "process_agent", label: "Processo", status: "running" },
  { name: "court_monitor_agent", label: "Tribunais", status: "idle" },
  { name: "jurisprudence_agent", label: "Jurisprudência", status: "idle" },
  { name: "crm_agent", label: "CRM", status: "idle" },
  { name: "financial_agent", label: "Financeiro", status: "idle" },
  { name: "analytics_agent", label: "Analytics", status: "idle" },
  { name: "strategy_agent", label: "Estratégia", status: "idle" },
  { name: "contract_agent", label: "Contratos", status: "idle" },
  { name: "marketing_agent", label: "Marketing", status: "idle" },
  { name: "visual_law_agent", label: "Visual Law", status: "idle" },
  { name: "ocr_agent", label: "OCR", status: "idle" },
  { name: "audit_agent", label: "Auditoria", status: "idle" },
  { name: "compliance_agent", label: "Compliance", status: "idle" },
  { name: "publication_monitor_agent", label: "Publicações", status: "idle" },
  { name: "innovation_agent", label: "Inovação", status: "idle" },
  { name: "coding_agent", label: "Código", status: "idle" },
  { name: "orchestration_agent", label: "Orquestrador", status: "idle" },
];

function AgentDot({ status }: { status: string }) {
  const cls = {
    idle: "agent-idle",
    running: "agent-running",
    success: "agent-success",
    error: "agent-error",
    approval: "agent-approval",
  }[status] ?? "agent-idle";
  return <span className={cls} />;
}

export default function DashboardPage() {
  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Cabeçalho */}
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
          <span className="kpi-value">—</span>
          <span className="text-xs text-afj-black/40">Carregando dados...</span>
        </div>

        <div className="kpi-box">
          <div className="flex items-center justify-between">
            <span className="kpi-label">Prazos (7 dias)</span>
            <AlertTriangle size={18} className="text-amber-500" />
          </div>
          <span className="kpi-value text-amber-600">—</span>
          <span className="text-xs text-afj-black/40">Verificando prazos...</span>
        </div>

        <div className="kpi-box">
          <div className="flex items-center justify-between">
            <span className="kpi-label">Aprovações Pendentes</span>
            <CheckSquare size={18} className="text-red-500" />
          </div>
          <span className="kpi-value text-red-600">—</span>
          <span className="text-xs text-afj-black/40">Aguardando revisão humana</span>
        </div>

        <div className="kpi-box">
          <div className="flex items-center justify-between">
            <span className="kpi-label">Custo IA (mês)</span>
            <DollarSign size={18} className="text-afj-gold" />
          </div>
          <span className="kpi-value">—</span>
          <span className="text-xs text-afj-black/40">Tokens utilizados</span>
        </div>
      </div>

      {/* ─── Grid principal ─────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Status dos 19 agentes */}
        <div className="lg:col-span-1 afj-card p-5">
          <div className="flex items-center gap-2 mb-4">
            <Bot size={16} className="text-afj-gold" />
            <h2 className="font-semibold text-sm text-afj-black">Agentes IA</h2>
            <span className="ml-auto text-xs text-afj-black/40">19 agentes</span>
          </div>
          <div className="space-y-2">
            {AGENT_NAMES.map((agent) => (
              <div key={agent.name} className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-2">
                  <AgentDot status={agent.status} />
                  <span className="text-afj-black/80">{agent.label}</span>
                </div>
                <span className="text-afj-black/30 text-xs capitalize">{agent.status}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Feed de atividade */}
        <div className="lg:col-span-2 afj-card p-5">
          <div className="flex items-center gap-2 mb-4">
            <Activity size={16} className="text-afj-gold" />
            <h2 className="font-semibold text-sm text-afj-black">Atividade Recente</h2>
          </div>
          <div className="space-y-3">
            {[
              { tipo: "Sistema", msg: "AFJ CORE SYSTEM iniciado com sucesso", time: "agora", color: "bg-green-500" },
              { tipo: "Agentes", msg: "19 agentes carregados e prontos", time: "agora", color: "bg-afj-gold" },
              { tipo: "Banco", msg: "Schema do banco criado e indexado", time: "agora", color: "bg-blue-500" },
              { tipo: "Qdrant", msg: "6 collections de memória institucional criadas", time: "agora", color: "bg-purple-500" },
            ].map((item, i) => (
              <div key={i} className="flex items-start gap-3 text-sm">
                <span className={`w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0 ${item.color}`} />
                <div className="flex-1 min-w-0">
                  <span className="font-medium text-afj-black/80">[{item.tipo}]</span>{" "}
                  <span className="text-afj-black/60">{item.msg}</span>
                </div>
                <span className="text-afj-black/30 text-xs flex-shrink-0">{item.time}</span>
              </div>
            ))}
          </div>

          <div className="mt-6 p-4 bg-afj-gold/5 border border-afj-gold/20 rounded-lg">
            <p className="text-sm text-afj-black/70">
              <span className="font-semibold text-afj-black">AFJ CORE SYSTEM</span> está operacional.
              Configure as integrações de tribunal e adicione processos para iniciar o monitoramento automático.
            </p>
            <div className="mt-3 flex gap-2">
              <a href="/processos" className="btn-afj-primary text-xs py-1.5 px-3 rounded">
                Adicionar Processo
              </a>
              <a href="/agentes" className="btn-afj-outline text-xs py-1.5 px-3 rounded">
                Ver Agentes
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
