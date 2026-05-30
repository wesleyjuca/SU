"use client";
import { useState, useEffect } from "react";
import dynamic from "next/dynamic";
import { BarChart2, Loader2, RefreshCw } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import type { FinancialData } from "@/components/relatorios/FinanceiroCharts";
import type { ProcessoData } from "@/components/relatorios/ProcessosCharts";
import type { AgentesData } from "@/components/relatorios/AgentesCharts";

const FinanceiroCharts = dynamic(() => import("@/components/relatorios/FinanceiroCharts"), {
  ssr: false,
  loading: () => <ChartSkeleton />,
});
const ProcessosCharts = dynamic(() => import("@/components/relatorios/ProcessosCharts"), {
  ssr: false,
  loading: () => <ChartSkeleton />,
});
const AgentesCharts = dynamic(() => import("@/components/relatorios/AgentesCharts"), {
  ssr: false,
  loading: () => <ChartSkeleton />,
});

const TABS = ["Financeiro", "Processos", "Agentes IA"] as const;

export default function RelatoriosPage() {
  const [tab, setTab] = useState<typeof TABS[number]>("Financeiro");
  const [financial, setFinancial] = useState<FinancialData | null>(null);
  const [processos, setProcessos] = useState<ProcessoData | null>(null);
  const [agentes, setAgentes] = useState<AgentesData | null>(null);
  const [loading, setLoading] = useState(false);

  const headers = () => ({
    Authorization: `Bearer ${typeof window !== "undefined" ? localStorage.getItem("afj_access_token") : ""}`,
  });

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
      <div className="afj-page-header">
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
        loading && !financial
          ? <ChartSkeleton />
          : financial
            ? <FinanceiroCharts data={financial} />
            : <EmptyTab icon={<BarChart2 size={28} className="text-afj-black/20" />} msg="Sem dados financeiros" />
      )}

      {/* ─── Processos ────────────────────────────────────────────────────── */}
      {tab === "Processos" && (
        loading && !processos
          ? <ChartSkeleton />
          : processos
            ? <ProcessosCharts data={processos} />
            : <EmptyTab icon={<BarChart2 size={28} className="text-afj-black/20" />} msg="Sem dados processuais" />
      )}

      {/* ─── Agentes IA ───────────────────────────────────────────────────── */}
      {tab === "Agentes IA" && (
        loading && !agentes
          ? <ChartSkeleton />
          : agentes
            ? <AgentesCharts data={agentes} />
            : <EmptyTab icon={<BarChart2 size={28} className="text-afj-black/20" />} msg="Sem dados de agentes" />
      )}
    </div>
  );
}

function ChartSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="afj-card p-4 h-20 animate-pulse bg-afj-cream-dark/40" />
        ))}
      </div>
      <div className="afj-card p-5">
        <div className="h-5 bg-afj-cream-dark rounded animate-pulse w-48 mb-4" />
        <div className="h-48 bg-afj-cream-dark/60 rounded animate-pulse" />
      </div>
    </div>
  );
}

function EmptyTab({ icon, msg }: { icon: React.ReactNode; msg: string }) {
  return (
    <div className="afj-card p-12 text-center">
      <div className="mx-auto mb-3 flex justify-center">{icon}</div>
      <p className="text-afj-black/40 text-sm">{msg}</p>
    </div>
  );
}
