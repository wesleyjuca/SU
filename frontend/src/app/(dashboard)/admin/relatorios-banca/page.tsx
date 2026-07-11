"use client";
import { useState, useEffect, useCallback } from "react";
import dynamic from "next/dynamic";
import { BarChart2, Building2, Scale, DollarSign, Bot, FileText, FileDown, FileSpreadsheet, Loader2 } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { useToast } from "@/components/ui/Toast";

const ConsolidadoCharts = dynamic(() => import("@/components/relatorios/ConsolidadoCharts"), { ssr: false });

interface Linha {
  tenant_id: string;
  unidade: string;
  is_matriz: boolean;
  processos_ativos: number;
  processos_total: number;
  receita_mes: number;
  despesa_mes: number;
  saldo_mes: number;
  custo_ia_mes: number;
  execucoes_mes: number;
  usuarios_ativos: number;
}
interface Totais {
  processos_ativos: number; processos_total: number;
  receita_mes: number; despesa_mes: number; saldo_mes: number;
  custo_ia_mes: number; execucoes_mes: number; usuarios_ativos: number;
}
interface Report {
  banca: { id: string; name: string; unidades: number };
  linhas: Linha[];
  totais: Totais;
  series: { mes: string; receita: number; despesa: number }[];
}
interface Scope {
  can_view: boolean;
  is_superadmin: boolean;
  bancas: { id: string; name: string; unidades: number }[];
}

function authH(): HeadersInit {
  const token = typeof window !== "undefined" ? localStorage.getItem("afj_access_token") : null;
  return { Authorization: `Bearer ${token}` };
}
const fmtBRL = (v: number) => `R$ ${v.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`;

export default function RelatoriosBancaPage() {
  const toast = useToast();
  const [scope, setScope] = useState<Scope | null>(null);
  const [bancaId, setBancaId] = useState<string>("");
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState<"pdf" | "xlsx" | "csv" | null>(null);

  useEffect(() => {
    fetch("/api/v1/reports/scope", { headers: authH() })
      .then((r) => (r.ok ? r.json() : null))
      .then((s: Scope | null) => {
        setScope(s);
        if (s?.can_view && s.bancas.length > 0) setBancaId(s.bancas[0].id);
        else setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const fetchReport = useCallback(async (id: string) => {
    setLoading(true);
    try {
      const qs = id ? `?banca_id=${id}` : "";
      const res = await fetch(`/api/v1/reports/consolidated${qs}`, { headers: authH() });
      if (res.ok) setReport(await res.json());
      else { const d = await res.json().catch(() => ({})); toast.error(d.detail || "Erro ao carregar o relatório."); }
    } catch { toast.error("Falha de conexão."); }
    finally { setLoading(false); }
  }, [toast]);

  useEffect(() => { if (bancaId) fetchReport(bancaId); }, [bancaId, fetchReport]);

  async function exportar(format: "pdf" | "xlsx" | "csv") {
    setExporting(format);
    try {
      const qs = bancaId ? `&banca_id=${bancaId}` : "";
      const res = await fetch(`/api/v1/reports/consolidated/export?format=${format}${qs}`, { headers: authH() });
      if (!res.ok) { toast.error("Erro ao exportar o relatório."); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const nome = `consolidado-banca.${format}`;
      const a = Object.assign(document.createElement("a"), { href: url, download: nome });
      a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Falha de conexão."); }
    finally { setExporting(null); }
  }

  return (
    <div className="max-w-6xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Admin" }, { label: "Relatórios da Banca" }]} />

      <div className="afj-page-header">
        <div>
          <h1 className="font-display text-2xl font-semibold text-afj-black flex items-center gap-2">
            <BarChart2 size={22} className="text-afj-gold" /> Relatórios da Banca
          </h1>
          <p className="text-afj-black/50 text-sm mt-0.5">
            Visão consolidada (matriz) das unidades do mesmo escritório — processos, financeiro e IA.
          </p>
        </div>
        <div className="flex gap-2 items-center flex-wrap">
          {scope?.is_superadmin && scope.bancas.length > 0 && (
            <select value={bancaId} onChange={(e) => setBancaId(e.target.value)}
              className="border border-afj-cream-dark rounded-sm px-3 py-2 text-sm bg-white">
              {scope.bancas.map((b) => <option key={b.id} value={b.id}>{b.name} ({b.unidades} un.)</option>)}
            </select>
          )}
          {report && (
            <>
              <button onClick={() => exportar("pdf")} disabled={exporting !== null}
                className="btn-afj-outline rounded-sm text-sm py-2 px-3 flex items-center gap-2 disabled:opacity-50"
                title="Exportar em PDF (timbrado)" aria-label="Exportar em PDF">
                {exporting === "pdf" ? <Loader2 size={14} className="animate-spin" /> : <FileText size={14} />} PDF
              </button>
              <button onClick={() => exportar("xlsx")} disabled={exporting !== null}
                className="btn-afj-outline rounded-sm text-sm py-2 px-3 flex items-center gap-2 disabled:opacity-50"
                title="Exportar em Excel (.xlsx)" aria-label="Exportar em Excel">
                {exporting === "xlsx" ? <Loader2 size={14} className="animate-spin" /> : <FileSpreadsheet size={14} />} Excel
              </button>
              <button onClick={() => exportar("csv")} disabled={exporting !== null}
                className="btn-afj-outline rounded-sm text-sm py-2 px-3 flex items-center gap-2 disabled:opacity-50"
                title="Exportar em CSV" aria-label="Exportar em CSV">
                {exporting === "csv" ? <Loader2 size={14} className="animate-spin" /> : <FileDown size={14} />} CSV
              </button>
            </>
          )}
        </div>
      </div>

      {scope && !scope.can_view ? (
        <div className="afj-card p-10 text-center">
          <Building2 size={36} className="mx-auto text-afj-black/20 mb-3" />
          <p className="font-semibold text-afj-black">Nenhuma matriz de banca disponível</p>
          <p className="text-afj-black/40 text-sm mt-1">
            {scope.is_superadmin
              ? "Ainda não há bancas com unidades cadastradas. Crie unidades em Escritórios."
              : "Este relatório fica disponível quando o seu escritório possui unidades (filiais)."}
          </p>
        </div>
      ) : loading ? (
        <div className="afj-card p-8 space-y-3">
          {Array.from({ length: 5 }).map((_, i) => <div key={i} className="h-10 bg-afj-cream-dark rounded animate-pulse" />)}
        </div>
      ) : report ? (
        <>
          {/* KPIs consolidados */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {[
              { icon: Scale, label: "Processos ativos", value: report.totais.processos_ativos.toLocaleString("pt-BR"), color: "text-afj-gold" },
              { icon: DollarSign, label: "Saldo do mês", value: fmtBRL(report.totais.saldo_mes), color: report.totais.saldo_mes >= 0 ? "text-green-600" : "text-red-500" },
              { icon: Bot, label: "Custo IA no mês", value: `$ ${report.totais.custo_ia_mes.toLocaleString("en-US", { minimumFractionDigits: 2 })}`, color: "text-afj-gold" },
              { icon: Building2, label: "Unidades + matriz", value: String(report.linhas.length), color: "text-afj-black" },
            ].map((k) => {
              const Icon = k.icon;
              return (
                <div key={k.label} className="afj-card p-4">
                  <div className="flex items-center gap-2 text-afj-black/45 text-xs mb-1">
                    <Icon size={13} className="text-afj-gold" /> {k.label}
                  </div>
                  <p className={`text-lg font-bold font-display ${k.color}`}>{k.value}</p>
                </div>
              );
            })}
          </div>

          {/* Matriz por unidade */}
          <div className="overflow-x-auto">
            <table className="afj-table w-full">
              <thead>
                <tr>
                  <th>Unidade</th>
                  <th className="text-right">Proc. ativos</th>
                  <th className="text-right">Proc. total</th>
                  <th className="text-right">Receita mês</th>
                  <th className="text-right">Despesa mês</th>
                  <th className="text-right">Saldo mês</th>
                  <th className="text-right">Custo IA</th>
                  <th className="text-right">Usuários</th>
                </tr>
              </thead>
              <tbody>
                {report.linhas.map((l) => (
                  <tr key={l.tenant_id}>
                    <td className="font-medium text-afj-black">
                      {l.unidade}
                      {l.is_matriz && <span className="ml-2 text-[10px] uppercase tracking-wide bg-afj-gold/15 text-afj-gold-dark px-1.5 py-0.5 rounded-sm">matriz</span>}
                    </td>
                    <td className="text-right text-afj-black/70">{l.processos_ativos}</td>
                    <td className="text-right text-afj-black/70">{l.processos_total}</td>
                    <td className="text-right text-green-700">{fmtBRL(l.receita_mes)}</td>
                    <td className="text-right text-red-600">{fmtBRL(l.despesa_mes)}</td>
                    <td className={`text-right font-medium ${l.saldo_mes >= 0 ? "text-afj-black" : "text-red-600"}`}>{fmtBRL(l.saldo_mes)}</td>
                    <td className="text-right text-afj-black/70">$ {l.custo_ia_mes.toFixed(2)}</td>
                    <td className="text-right text-afj-black/70">{l.usuarios_ativos}</td>
                  </tr>
                ))}
                <tr className="font-semibold bg-afj-cream/40">
                  <td className="text-afj-black">TOTAL DA BANCA</td>
                  <td className="text-right">{report.totais.processos_ativos}</td>
                  <td className="text-right">{report.totais.processos_total}</td>
                  <td className="text-right text-green-700">{fmtBRL(report.totais.receita_mes)}</td>
                  <td className="text-right text-red-600">{fmtBRL(report.totais.despesa_mes)}</td>
                  <td className={`text-right ${report.totais.saldo_mes >= 0 ? "text-afj-black" : "text-red-600"}`}>{fmtBRL(report.totais.saldo_mes)}</td>
                  <td className="text-right">$ {report.totais.custo_ia_mes.toFixed(2)}</td>
                  <td className="text-right">{report.totais.usuarios_ativos}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <ConsolidadoCharts linhas={report.linhas} series={report.series} />

          <p className="text-[11px] text-afj-black/35 text-center">
            Valores do mês corrente (lançamentos pagos) e custo de IA do mês. Cada unidade mantém seus dados isolados — este consolidado é só de leitura.
          </p>
        </>
      ) : null}
    </div>
  );
}
