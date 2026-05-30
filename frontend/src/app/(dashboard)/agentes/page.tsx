"use client";
import { useState } from "react";
import { Play, Loader2 } from "lucide-react";
import { AgentStatusCard } from "@/components/agents/AgentStatusCard";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { useToast } from "@/components/ui/Toast";
import type { AgentCardData } from "@/components/agents/AgentStatusCard";

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
  const [taskType, setTaskType] = useState("generate_petition");
  const [taskDesc, setTaskDesc] = useState("");
  const [result, setResult] = useState<string | null>(null);
  const [triggering, setTriggering] = useState<string | null>(null);

  async function triggerAgent(agentName: string) {
    setResult(null);
    setTriggering(agentName);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/agents/trigger", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          task_type: taskType,
          task_input: { descricao: taskDesc || `Tarefa via agente ${agentName}` },
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setResult(`Run iniciado: ${data.run_id}`);
      } else {
        toast.error(`Erro ao iniciar agente: ${res.status}`);
      }
    } catch {
      toast.error("Erro de conexão ao iniciar agente.");
    } finally {
      setTriggering(null);
    }
  }

  const categories = [...new Set(AGENTS.map((a) => a.category))];

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Agentes IA" }]} />
      <div>
        <h1 className="font-display text-2xl font-semibold text-afj-black">Agentes IA</h1>
        <p className="text-afj-black/50 text-sm">19 agentes especializados — {AGENTS.length} disponíveis</p>
      </div>

      {result && (
        <div className="bg-green-50 border border-green-200 text-green-800 rounded-lg px-4 py-3 text-sm">
          {result}
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
        </div>
      </div>

      {/* Grid de agentes por categoria */}
      {categories.map((cat) => (
        <div key={cat}>
          <h2 className="text-xs font-semibold text-afj-black/40 uppercase tracking-wider mb-3">{cat}</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {AGENTS.filter((a) => a.category === cat).map((agent) => (
              <AgentStatusCard
                key={agent.name}
                agent={agent}
                categoryColor={CATEGORY_COLORS[agent.category]}
                onTrigger={triggerAgent}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
