"use client";
import { useState, useEffect } from "react";
import { BarChart2, TrendingUp, TrendingDown, DollarSign, Loader2, RefreshCw, Scale, Bot } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell, AreaChart, Area, LineChart, Line,
} from "recharts";

// ─── Cores da identidade visual AFJ ──────────────────────────────────────────
const GOLD = "#B8954A";
const GOLD_LIGHT = "#D4AC64";
const NAVY = "#1E2229";
const GREEN = "#16A34A";
const RED_SOFT = "#DC2626";
const AMBER = "#D97706";
const MUTED = "#9CA3AF";
const AREA_COLORS = [GOLD, GOLD_LIGHT, "#C09A5A", "#8A6D2A", NAVY, "#353D4A", "#4B5563", MUTED];
const SITUACAO_COLORS: Record<string, string> = {
  ATIVO: GREEN, SUSPENSO: AMBER, ARQUIVADO: MUTED, ENCERRADO: NAVY,
};

// ─── Tipos ────────────────────────────────────────────────────────────────────
interface FinancialData {
  mensal: { mes: string; receitas: number; despesas: number; saldo: number }[];
  por_categoria: { categoria: string; tipo: string; total: number }[];
  summary: { receitas_pagas: number; receitas_pendentes: number; despesas_pagas: number; despesas_pendentes: number };
}
interface ProcessoData {
  por_situacao: { situacao: string; count: number }[];
  por_area: { area: string; count: number }[];
  criados_por_mes: { mes: string; count: number }[];
  total: number;
}
interface AgentesData {
  por_agente: { agent: string; custo: number; tokens: number; execucoes: number; avg_ms: number }[];
  por_dia: { dia: string; total: number; custo: number }[];
  total_execucoes: number;
  total_custo: number;
  total_tokens: number;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
const fmt = (v: number) => `R$ ${v.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`;
const fmtMes = (mes: string) => {
  try { return new Date(mes + "-15").toLocaleDateString("pt-BR", { month: "short", year: "2-digit" }); }
  catch { return mes; }
};
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

// ─── Tooltip customizado ──────────────────────────────────────────────────────
function CustomTooltip({ active, payload, label, isCurrency = true }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-afj-cream-dark rounded-sm shadow-lg px-3 py-2 text-xs">
      <p className="font-semibold text-afj-black mb-1">{label}</p>
      {payload.map((p: any, i: number) => (
        <p key={i} style={{ color: p.color }}>
          {p.name}: {isCurrency ? fmt(p.value) : p.value.toLocaleString("pt-BR")}
        </p>
      ))}
    </div>
  );
}

const TABS = ["Financeiro", "Processos", "Agentes IA"] as const;

export default function RelatoriosPage() {
  const [tab, setTab] = useState<typeof TABS[number]>("Financeiro");
  const [financial, setFinancial] = useState<FinancialData | null>(null);
  const [processos, setProcessos] = useState<ProcessoData | null>(null);
  const [agentes, setAgentes] = useState<AgentesData | null>(null);
  const [loading, setLoading] = useState(false);

  const token = () => typeof window !== "undefined" ? localStorage.getItem("afj_access_token") : null;
  const headers = () => ({ Authorization: `Bearer ${token()}` });

  async function loadFinancial() {
    setLoading(true);
    try {
      const res = await fetch("/api/v1/system/analytics/financeiro?meses=6", { headers: headers() });
      if (res.ok) setFinancial(await res.json());
    } finally { setLoading(false); }
  }

  async function loadProcessos() {
    setLoading(true);
    try {
      const res = await fetch("/api/v1/system/analytics/processos", { headers: headers() });
      if (res.ok) setProcessos(await res.json());
    } finally { setLoading(false); }
  }

  async function loadAgentes() {
    setLoading(true);
    try {
      const res = await fetch("/api/v1/system/analytics/agentes?dias=30", { headers: headers() });
      if (res.ok) setAgentes(await res.json());
    } finally { setLoading(false); }
  }

  useEffect(() => {
    if (tab === "Financeiro" && !financial) loadFinancial();
    if (tab === "Processos" && !processos) loadProcessos();
    if (tab === "Agentes IA" && !agentes) loadAgentes();
  }, [tab]);

  function refresh() {
    if (tab === "Financeiro") { setFinancial(null); loadFinancial(); }
    if (tab === "Processos") { setProcessos(null); loadProcessos(); }
    if (tab === "Agentes IA") { setAgentes(null); loadAgentes(); }
  }

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Relatórios" }]} />
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-semibold text-afj-black">Relatórios</h1>
          <p className="text-afj-black/50 text-sm">Análises financeiras, processuais e de IA</p>
        </div>
        <button onClick={refresh} disabled={loading} className="btn-afj-outline rounded-sm flex items-center gap-2 disabled:opacity-50">
          {loading ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
          Atualizar
        </button>
      </div>

      {/* ─── Tabs ─────────────────────────────────────────────────────────── */}
      <div className="flex gap-1 border-b border-afj-cream-dark">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px ${
              tab === t
                ? "border-afj-gold text-afj-gold"
                : "border-transparent text-afj-black/50 hover:text-afj-black"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* ─── Financeiro ───────────────────────────────────────────────────── */}
      {tab === "Financeiro" && (
        <div className="space-y-5">
          {/* KPI Cards */}
          {financial?.summary && (
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              {[
                { label: "Receitas Pagas", value: financial.summary.receitas_pagas, icon: TrendingUp, color: "text-green-600" },
                { label: "A Receber", value: financial.summary.receitas_pendentes, icon: DollarSign, color: "text-afj-gold" },
                { label: "Despesas Pagas", value: financial.summary.despesas_pagas, icon: TrendingDown, color: "text-red-500" },
                {
                  label: "Saldo (rec. - desp.)",
                  value: financial.summary.receitas_pagas - financial.summary.despesas_pagas,
                  icon: BarChart2,
                  color: (financial.summary.receitas_pagas - financial.summary.despesas_pagas) >= 0 ? "text-green-600" : "text-red-500",
                },
              ].map(({ label, value, icon: Icon, color }) => (
                <div key={label} className="afj-card p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <Icon size={15} className={color} />
                    <span className="text-xs text-afj-black/50">{label}</span>
                  </div>
                  <p className={`text-lg font-bold font-display ${color}`}>{fmt(value)}</p>
                </div>
              ))}
            </div>
          )}

          {loading && !financial && <ChartSkeleton />}

          {financial && (
            <>
              {/* Receitas vs Despesas por mês */}
              <div className="afj-card p-5">
                <h3 className="font-semibold text-sm text-afj-black mb-4">Receitas vs Despesas por Mês</h3>
                {financial.mensal.length > 0 ? (
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={financial.mensal.map(d => ({ ...d, mes: fmtMes(d.mes) }))} barGap={4}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#EAE5D8" vertical={false} />
                      <XAxis dataKey="mes" tick={{ fontSize: 11, fill: "#6B6B6B" }} axisLine={false} tickLine={false} />
                      <YAxis tickFormatter={(v) => `R$${(v/1000).toFixed(0)}k`} tick={{ fontSize: 11, fill: "#6B6B6B" }} axisLine={false} tickLine={false} width={55} />
                      <Tooltip content={<CustomTooltip />} />
                      <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11 }} />
                      <Bar dataKey="receitas" name="Receitas" fill={GOLD} radius={[2, 2, 0, 0]} />
                      <Bar dataKey="despesas" name="Despesas" fill={RED_SOFT} radius={[2, 2, 0, 0]} opacity={0.75} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : <EmptyState msg="Nenhum dado financeiro no período" />}
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                {/* Saldo Acumulado */}
                <div className="afj-card p-5">
                  <h3 className="font-semibold text-sm text-afj-black mb-4">Saldo Acumulado</h3>
                  {financial.mensal.length > 0 ? (
                    <ResponsiveContainer width="100%" height={180}>
                      <AreaChart data={financial.mensal.map(d => ({ ...d, mes: fmtMes(d.mes) }))}>
                        <defs>
                          <linearGradient id="saldoGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor={GOLD} stopOpacity={0.2} />
                            <stop offset="95%" stopColor={GOLD} stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#EAE5D8" vertical={false} />
                        <XAxis dataKey="mes" tick={{ fontSize: 10, fill: "#6B6B6B" }} axisLine={false} tickLine={false} />
                        <YAxis tickFormatter={(v) => `R$${(v/1000).toFixed(0)}k`} tick={{ fontSize: 10, fill: "#6B6B6B" }} axisLine={false} tickLine={false} width={50} />
                        <Tooltip content={<CustomTooltip />} />
                        <Area type="monotone" dataKey="saldo" name="Saldo" stroke={GOLD} fill="url(#saldoGrad)" strokeWidth={2} dot={false} />
                      </AreaChart>
                    </ResponsiveContainer>
                  ) : <EmptyState msg="Sem dados" />}
                </div>

                {/* Por Categoria */}
                <div className="afj-card p-5">
                  <h3 className="font-semibold text-sm text-afj-black mb-4">Por Categoria (pagos)</h3>
                  {financial.por_categoria.filter(c => c.tipo === "RECEITA").length > 0 ? (
                    <ResponsiveContainer width="100%" height={180}>
                      <PieChart>
                        <Pie
                          data={financial.por_categoria.filter(c => c.tipo === "RECEITA")}
                          dataKey="total" nameKey="categoria"
                          cx="50%" cy="50%" innerRadius={45} outerRadius={75}
                          paddingAngle={2}
                        >
                          {financial.por_categoria.filter(c => c.tipo === "RECEITA").map((_, i) => (
                            <Cell key={i} fill={AREA_COLORS[i % AREA_COLORS.length]} />
                          ))}
                        </Pie>
                        <Tooltip formatter={(v: number) => fmt(v)} />
                        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 10 }} />
                      </PieChart>
                    </ResponsiveContainer>
                  ) : <EmptyState msg="Sem receitas pagas por categoria" />}
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* ─── Processos ────────────────────────────────────────────────────── */}
      {tab === "Processos" && (
        <div className="space-y-5">
          {processos && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="afj-card p-4">
                <div className="flex items-center gap-2 mb-1"><Scale size={15} className="text-afj-gold" /><span className="text-xs text-afj-black/50">Total de Processos</span></div>
                <p className="text-2xl font-bold font-display text-afj-black">{processos.total}</p>
              </div>
              <div className="afj-card p-4">
                <div className="flex items-center gap-2 mb-1"><Scale size={15} className="text-green-600" /><span className="text-xs text-afj-black/50">Ativos</span></div>
                <p className="text-2xl font-bold font-display text-green-600">
                  {processos.por_situacao.find(s => s.situacao === "ATIVO")?.count ?? 0}
                </p>
              </div>
              <div className="afj-card p-4">
                <div className="flex items-center gap-2 mb-1"><Scale size={15} className="text-afj-black/40" /><span className="text-xs text-afj-black/50">Áreas distintas</span></div>
                <p className="text-2xl font-bold font-display text-afj-black">{processos.por_area.length}</p>
              </div>
            </div>
          )}

          {loading && !processos && <ChartSkeleton />}

          {processos && (
            <>
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                {/* Por Situação */}
                <div className="afj-card p-5">
                  <h3 className="font-semibold text-sm text-afj-black mb-4">Distribuição por Situação</h3>
                  {processos.por_situacao.length > 0 ? (
                    <ResponsiveContainer width="100%" height={200}>
                      <PieChart>
                        <Pie
                          data={processos.por_situacao} dataKey="count" nameKey="situacao"
                          cx="50%" cy="50%" innerRadius={50} outerRadius={80} paddingAngle={3}
                        >
                          {processos.por_situacao.map((entry, i) => (
                            <Cell key={i} fill={SITUACAO_COLORS[entry.situacao] ?? MUTED} />
                          ))}
                        </Pie>
                        <Tooltip formatter={(v: number) => [v, "processos"]} />
                        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11 }} />
                      </PieChart>
                    </ResponsiveContainer>
                  ) : <EmptyState msg="Nenhum processo cadastrado" />}
                </div>

                {/* Por Área do Direito */}
                <div className="afj-card p-5">
                  <h3 className="font-semibold text-sm text-afj-black mb-4">Por Área do Direito</h3>
                  {processos.por_area.length > 0 ? (
                    <ResponsiveContainer width="100%" height={200}>
                      <BarChart data={processos.por_area} layout="vertical" margin={{ left: 10 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#EAE5D8" horizontal={false} />
                        <XAxis type="number" tick={{ fontSize: 10, fill: "#6B6B6B" }} axisLine={false} tickLine={false} />
                        <YAxis type="category" dataKey="area" width={110} tick={{ fontSize: 10, fill: "#6B6B6B" }} axisLine={false} tickLine={false} />
                        <Tooltip content={<CustomTooltip isCurrency={false} />} />
                        <Bar dataKey="count" name="Processos" fill={GOLD} radius={[0, 2, 2, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  ) : <EmptyState msg="Sem classificação por área" />}
                </div>
              </div>

              {/* Processos criados por mês */}
              <div className="afj-card p-5">
                <h3 className="font-semibold text-sm text-afj-black mb-4">Processos Criados por Mês (últimos 6 meses)</h3>
                {processos.criados_por_mes.length > 0 ? (
                  <ResponsiveContainer width="100%" height={180}>
                    <AreaChart data={processos.criados_por_mes.map(d => ({ ...d, mes: fmtMes(d.mes) }))}>
                      <defs>
                        <linearGradient id="procGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor={NAVY} stopOpacity={0.15} />
                          <stop offset="95%" stopColor={NAVY} stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#EAE5D8" vertical={false} />
                      <XAxis dataKey="mes" tick={{ fontSize: 11, fill: "#6B6B6B" }} axisLine={false} tickLine={false} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "#6B6B6B" }} axisLine={false} tickLine={false} />
                      <Tooltip content={<CustomTooltip isCurrency={false} />} />
                      <Area type="monotone" dataKey="count" name="Processos" stroke={NAVY} fill="url(#procGrad)" strokeWidth={2} dot={{ fill: NAVY, r: 3 }} />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : <EmptyState msg="Sem dados de criação no período" />}
              </div>
            </>
          )}
        </div>
      )}

      {/* ─── Agentes IA ───────────────────────────────────────────────────── */}
      {tab === "Agentes IA" && (
        <div className="space-y-5">
          {agentes && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {[
                { label: "Execuções (30 dias)", value: agentes.total_execucoes.toLocaleString("pt-BR"), icon: Bot, color: "text-afj-gold" },
                { label: "Custo Total (USD)", value: `$${agentes.total_custo.toFixed(4)}`, icon: DollarSign, color: "text-afj-gold" },
                { label: "Tokens Consumidos", value: agentes.total_tokens.toLocaleString("pt-BR"), icon: BarChart2, color: "text-afj-black/60" },
              ].map(({ label, value, icon: Icon, color }) => (
                <div key={label} className="afj-card p-4">
                  <div className="flex items-center gap-2 mb-1"><Icon size={15} className={color} /><span className="text-xs text-afj-black/50">{label}</span></div>
                  <p className={`text-xl font-bold font-display ${color}`}>{value}</p>
                </div>
              ))}
            </div>
          )}

          {loading && !agentes && <ChartSkeleton />}

          {agentes && (
            <>
              {/* Custo por agente */}
              <div className="afj-card p-5">
                <h3 className="font-semibold text-sm text-afj-black mb-4">Custo por Agente (USD, últimos 30 dias)</h3>
                {agentes.por_agente.length > 0 ? (
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={agentes.por_agente.map(d => ({ ...d, agent: AGENT_LABELS[d.agent] ?? d.agent }))}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#EAE5D8" vertical={false} />
                      <XAxis dataKey="agent" tick={{ fontSize: 10, fill: "#6B6B6B" }} axisLine={false} tickLine={false} />
                      <YAxis tickFormatter={(v) => `$${v.toFixed(3)}`} tick={{ fontSize: 10, fill: "#6B6B6B" }} axisLine={false} tickLine={false} width={55} />
                      <Tooltip formatter={(v: number, name: string) => [name === "custo" ? `$${v.toFixed(4)}` : v, name === "custo" ? "Custo USD" : "Execuções"]} />
                      <Bar dataKey="custo" name="custo" fill={GOLD} radius={[2, 2, 0, 0]} />
                      <Bar dataKey="execucoes" name="execucoes" fill={NAVY} radius={[2, 2, 0, 0]} opacity={0.6} yAxisId="right" />
                    </BarChart>
                  </ResponsiveContainer>
                ) : <EmptyState msg="Nenhuma execução no período" />}
              </div>

              {/* Execuções por dia */}
              <div className="afj-card p-5">
                <h3 className="font-semibold text-sm text-afj-black mb-4">Execuções por Dia (últimos 30 dias)</h3>
                {agentes.por_dia.length > 0 ? (
                  <ResponsiveContainer width="100%" height={180}>
                    <LineChart data={agentes.por_dia.map(d => ({ ...d, dia: fmtDia(d.dia) }))}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#EAE5D8" vertical={false} />
                      <XAxis dataKey="dia" tick={{ fontSize: 10, fill: "#6B6B6B" }} axisLine={false} tickLine={false} />
                      <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: "#6B6B6B" }} axisLine={false} tickLine={false} />
                      <Tooltip content={<CustomTooltip isCurrency={false} />} />
                      <Line type="monotone" dataKey="total" name="Execuções" stroke={GOLD} strokeWidth={2} dot={false} activeDot={{ r: 4, fill: GOLD }} />
                    </LineChart>
                  </ResponsiveContainer>
                ) : <EmptyState msg="Sem execuções no período" />}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function ChartSkeleton() {
  return (
    <div className="afj-card p-5 space-y-3">
      <div className="h-5 bg-afj-cream-dark rounded animate-pulse w-48" />
      <div className="h-48 bg-afj-cream-dark/60 rounded animate-pulse" />
    </div>
  );
}

function EmptyState({ msg }: { msg: string }) {
  return (
    <div className="h-40 flex items-center justify-center text-afj-black/30 text-sm">
      {msg}
    </div>
  );
}
