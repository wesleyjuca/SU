"use client";
import { useState, useEffect } from "react";
import dynamic from "next/dynamic";
import { BarChart2, Loader2, RefreshCw, Download, MapPin } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import type { FinancialData } from "@/components/relatorios/FinanceiroCharts";
import type { ProcessoData } from "@/components/relatorios/ProcessosCharts";
import type { AgentesData } from "@/components/relatorios/AgentesCharts";
import type { GestaoData } from "@/components/relatorios/GestaoCharts";

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
const GestaoCharts = dynamic(() => import("@/components/relatorios/GestaoCharts"), {
  ssr: false,
  loading: () => <ChartSkeleton />,
});

const TABS = ["Gestão", "Financeiro", "Processos", "Agentes IA", "Geográfico"] as const;

// Fase 257.3 — shape de GET /clients/geolocalizacao/regioes.
type GeograficoData = {
  total_geocodificados: number;
  regioes: { cidade: string; uf: string; quantidade: number }[];
};

// Fase 206.3 — dado um período [from, to], devolve o período imediatamente
// anterior de mesma duração (pra comparativo lado a lado).
function periodoAnterior(from: string, to: string): { from: string; to: string } {
  const DIA_MS = 24 * 60 * 60 * 1000;
  const f = new Date(from + "T00:00:00Z");
  const t = new Date(to + "T00:00:00Z");
  const duracaoMs = t.getTime() - f.getTime();
  const antTo = new Date(f.getTime() - DIA_MS);
  const antFrom = new Date(antTo.getTime() - duracaoMs);
  const fmt = (d: Date) => d.toISOString().slice(0, 10);
  return { from: fmt(antFrom), to: fmt(antTo) };
}

export default function RelatoriosPage() {
  const [tab, setTab] = useState<typeof TABS[number]>("Gestão");
  const [gestao, setGestao] = useState<GestaoData | null>(null);
  const [gestaoAnterior, setGestaoAnterior] = useState<GestaoData | null>(null);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [financial, setFinancial] = useState<FinancialData | null>(null);
  const [processos, setProcessos] = useState<ProcessoData | null>(null);
  const [agentes, setAgentes] = useState<AgentesData | null>(null);
  const [geografico, setGeografico] = useState<GeograficoData | null>(null);
  const [exportando, setExportando] = useState(false);
  const [loading, setLoading] = useState(false);

  async function loadGestao() {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (dateFrom) params.set("date_from", dateFrom);
      if (dateTo) params.set("date_to", dateTo);
      const qs = params.toString() ? `?${params.toString()}` : "";
      const res = await fetch(`/api/v1/system/analytics/gestao${qs}`, { headers: headers() });
      setGestao(res.ok ? await res.json() : null);

      if (dateFrom && dateTo) {
        const ant = periodoAnterior(dateFrom, dateTo);
        const paramsAnt = new URLSearchParams({ date_from: ant.from, date_to: ant.to });
        const resAnt = await fetch(`/api/v1/system/analytics/gestao?${paramsAnt.toString()}`, { headers: headers() });
        setGestaoAnterior(resAnt.ok ? await resAnt.json() : null);
      } else {
        setGestaoAnterior(null);
      }
    } finally { setLoading(false); }
  }

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

  async function loadGeografico() {
    setLoading(true);
    try {
      const res = await fetch("/api/v1/clients/geolocalizacao/regioes", { headers: headers() });
      if (res.ok) setGeografico(await res.json());
    } finally { setLoading(false); }
  }

  // Fase 257.3 — reaproveita o mesmo padrão de download já usado em
  // Auditoria/Financeiro (blob + link temporário, sem lib nova).
  async function exportarGeografico(fmt: "pdf" | "csv") {
    setExportando(true);
    try {
      const res = await fetch(`/api/v1/clients/geolocalizacao/regioes/export?format=${fmt}`, { headers: headers() });
      if (res.ok) {
        const blob = await res.blob();
        const a = Object.assign(document.createElement("a"), {
          href: URL.createObjectURL(blob),
          download: `clientes-por-regiao.${fmt}`,
        });
        a.click();
        URL.revokeObjectURL(a.href);
      }
    } finally {
      setExportando(false);
    }
  }

  useEffect(() => {
    if (tab === "Gestão" && !gestao) loadGestao();
    if (tab === "Financeiro" && !financial) loadFinancial();
    if (tab === "Processos" && !processos) loadProcessos();
    if (tab === "Agentes IA" && !agentes) loadAgentes();
    if (tab === "Geográfico" && !geografico) loadGeografico();
  }, [tab]);

  function refresh() {
    if (tab === "Gestão") { setGestao(null); setGestaoAnterior(null); loadGestao(); }
    if (tab === "Financeiro") { setFinancial(null); loadFinancial(); }
    if (tab === "Processos") { setProcessos(null); loadProcessos(); }
    if (tab === "Agentes IA") { setAgentes(null); loadAgentes(); }
    if (tab === "Geográfico") { setGeografico(null); loadGeografico(); }
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

      {/* ─── Gestão ───────────────────────────────────────────────────────── */}
      {tab === "Gestão" && (
        <div className="space-y-4">
          <div className="afj-card p-3 flex items-end gap-3 flex-wrap">
            <div>
              <label className="text-[11px] text-afj-black/55 block mb-1 uppercase tracking-widest font-semibold">De</label>
              <input
                type="date" value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="border border-afj-cream-dark rounded-sm px-3 py-1.5 text-sm focus:outline-none focus:border-afj-gold"
              />
            </div>
            <div>
              <label className="text-[11px] text-afj-black/55 block mb-1 uppercase tracking-widest font-semibold">Até</label>
              <input
                type="date" value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="border border-afj-cream-dark rounded-sm px-3 py-1.5 text-sm focus:outline-none focus:border-afj-gold"
              />
            </div>
            <button
              onClick={() => { setGestao(null); setGestaoAnterior(null); loadGestao(); }}
              disabled={loading}
              className="btn-afj-outline rounded-sm text-sm disabled:opacity-50"
            >
              Aplicar
            </button>
            {(dateFrom || dateTo) && (
              <button
                onClick={() => { setDateFrom(""); setDateTo(""); setGestao(null); setGestaoAnterior(null); loadGestao(); }}
                className="text-xs text-afj-black/40 hover:text-afj-black underline"
              >
                Limpar período
              </button>
            )}
            <p className="text-[11px] text-afj-black/35 ml-auto">
              {dateFrom && dateTo
                ? "Comparando com o período imediatamente anterior de mesma duração."
                : "Sem período definido, mostra o histórico completo."}
            </p>
          </div>

          {loading && !gestao
            ? <ChartSkeleton />
            : gestao
              ? <GestaoCharts data={gestao} dataAnterior={gestaoAnterior} />
              : <EmptyTab icon={<BarChart2 size={28} className="text-afj-black/20" />} msg="Sem dados de gestão" />
          }
        </div>
      )}

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

      {/* ─── Geográfico (Fase 257.3 — item reservado desde a Fase 230) ─────── */}
      {tab === "Geográfico" && (
        loading && !geografico
          ? <ChartSkeleton />
          : geografico && geografico.regioes.length > 0
            ? (
              <div className="space-y-4">
                <div className="afj-card p-3 flex items-center justify-between flex-wrap gap-2">
                  <p className="text-sm text-afj-black/60">
                    {geografico.total_geocodificados} cliente(s) geocodificado(s) em {geografico.regioes.length} região(ões).
                    Ver marcadores no <a href="/mapa" className="text-afj-gold hover:underline">Mapa</a>.
                  </p>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => exportarGeografico("csv")} disabled={exportando}
                      className="btn-afj-outline rounded-sm text-xs flex items-center gap-1.5 disabled:opacity-50"
                    >
                      <Download size={12} /> CSV
                    </button>
                    <button
                      onClick={() => exportarGeografico("pdf")} disabled={exportando}
                      className="btn-afj-outline rounded-sm text-xs flex items-center gap-1.5 disabled:opacity-50"
                    >
                      <Download size={12} /> PDF
                    </button>
                  </div>
                </div>
                <div className="afj-card overflow-hidden">
                  <table className="afj-table w-full">
                    <thead>
                      <tr>
                        <th>Cidade</th>
                        <th>UF</th>
                        <th className="text-right">Clientes</th>
                      </tr>
                    </thead>
                    <tbody>
                      {geografico.regioes.map((r) => (
                        <tr key={`${r.cidade}-${r.uf}`}>
                          <td className="flex items-center gap-1.5"><MapPin size={12} className="text-afj-black/30" /> {r.cidade}</td>
                          <td>{r.uf}</td>
                          <td className="text-right">{r.quantidade}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )
            : <EmptyTab icon={<MapPin size={28} className="text-afj-black/20" />} msg="Nenhum cliente geocodificado ainda" />
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
