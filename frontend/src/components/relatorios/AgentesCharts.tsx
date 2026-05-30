"use client";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line,
} from "recharts";
import { Bot, DollarSign, BarChart2 } from "lucide-react";

const GOLD = "#B8954A";
const NAVY = "#1E2229";

const fmtDia = (dia: string) => {
  try { return new Date(dia).toLocaleDateString("pt-BR", { day: "2-digit", month: "short" }); }
  catch { return dia; }
};

const AGENT_LABELS: Record<string, string> = {
  petition_agent: "Petição", review_agent: "Revisão", process_agent: "Processo",
  court_monitor_agent: "Tribunais", jurisprudence_agent: "Jurisprudência",
  crm_agent: "CRM", financial_agent: "Financeiro", analytics_agent: "Analytics",
  strategy_agent: "Estratégia", contract_agent: "Contratos", marketing_agent: "Marketing",
  visual_law_agent: "Visual Law", ocr_agent: "OCR", audit_agent: "Auditoria",
  compliance_agent: "Compliance", publication_monitor_agent: "Publicações",
  innovation_agent: "Inovação", coding_agent: "Código", orchestration_agent: "Orquestrador",
};

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-afj-cream-dark rounded-sm shadow-lg px-3 py-2 text-xs">
      <p className="font-semibold text-afj-black mb-1">{label}</p>
      {payload.map((p: any, i: number) => (
        <p key={i} style={{ color: p.color }}>{p.name}: {p.value.toLocaleString("pt-BR")}</p>
      ))}
    </div>
  );
}

function EmptyState({ msg }: { msg: string }) {
  return <div className="h-40 flex items-center justify-center text-afj-black/30 text-sm">{msg}</div>;
}

export interface AgentesData {
  por_agente: { agent: string; custo: number; tokens: number; execucoes: number; avg_ms: number }[];
  por_dia: { dia: string; total: number; custo: number }[];
  total_execucoes: number;
  total_custo: number;
  total_tokens: number;
}

export default function AgentesCharts({ data }: { data: AgentesData }) {
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {[
          { label: "Execuções (30 dias)", value: data.total_execucoes.toLocaleString("pt-BR"), icon: Bot, color: "text-afj-gold" },
          { label: "Custo Total (USD)", value: `$${data.total_custo.toFixed(4)}`, icon: DollarSign, color: "text-afj-gold" },
          { label: "Tokens Consumidos", value: data.total_tokens.toLocaleString("pt-BR"), icon: BarChart2, color: "text-afj-black/60" },
        ].map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="afj-card p-4">
            <div className="flex items-center gap-2 mb-1"><Icon size={15} className={color} /><span className="text-xs text-afj-black/50">{label}</span></div>
            <p className={`text-xl font-bold font-display ${color}`}>{value}</p>
          </div>
        ))}
      </div>

      <div className="afj-card p-5">
        <h3 className="font-semibold text-sm text-afj-black mb-4">Custo por Agente (USD, últimos 30 dias)</h3>
        {data.por_agente.length > 0 ? (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={data.por_agente.map(d => ({ ...d, agent: AGENT_LABELS[d.agent] ?? d.agent }))}>
              <CartesianGrid strokeDasharray="3 3" stroke="#EAE5D8" vertical={false} />
              <XAxis dataKey="agent" tick={{ fontSize: 10, fill: "#6B6B6B" }} axisLine={false} tickLine={false} />
              <YAxis tickFormatter={(v) => `$${v.toFixed(3)}`} tick={{ fontSize: 10, fill: "#6B6B6B" }} axisLine={false} tickLine={false} width={55} />
              <Tooltip formatter={(v: number, name: string) => [name === "custo" ? `$${(v as number).toFixed(4)}` : v, name === "custo" ? "Custo USD" : "Execuções"]} />
              <Bar dataKey="custo" name="custo" fill={GOLD} radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : <EmptyState msg="Nenhuma execução no período" />}
      </div>

      <div className="afj-card p-5">
        <h3 className="font-semibold text-sm text-afj-black mb-4">Execuções por Dia (últimos 30 dias)</h3>
        {data.por_dia.length > 0 ? (
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={data.por_dia.map(d => ({ ...d, dia: fmtDia(d.dia) }))}>
              <CartesianGrid strokeDasharray="3 3" stroke="#EAE5D8" vertical={false} />
              <XAxis dataKey="dia" tick={{ fontSize: 10, fill: "#6B6B6B" }} axisLine={false} tickLine={false} />
              <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: "#6B6B6B" }} axisLine={false} tickLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <Line type="monotone" dataKey="total" name="Execuções" stroke={GOLD} strokeWidth={2} dot={false} activeDot={{ r: 4, fill: GOLD }} />
            </LineChart>
          </ResponsiveContainer>
        ) : <EmptyState msg="Sem execuções no período" />}
      </div>
    </div>
  );
}
