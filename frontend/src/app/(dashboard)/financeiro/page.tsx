"use client";
import { useState, useEffect } from "react";
import { DollarSign, TrendingUp, TrendingDown, Plus, CheckCircle, Clock, Trash2, FileDown, BarChart3 } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { useToast } from "@/components/ui/Toast";
import { useForm } from "react-hook-form";
import type { Resolver } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { FinanceiroSchema, type FinanceiroInput } from "@/lib/schemas";

interface Entry {
  id: string;
  tipo: string;
  categoria: string | null;
  descricao: string;
  valor: number;
  status: string;
  data_vencimento: string | null;
  data_pagamento: string | null;
  client_id: string | null;
  process_id: string | null;
  created_at: string;
}

interface Summary {
  receitas_pagas: number;
  receitas_pendentes: number;
  despesas_pagas: number;
  despesas_pendentes: number;
  saldo_atual: number;
  a_receber: number;
}

interface MonthlyData {
  mes: string;
  receitas: number;
  despesas: number;
}

const STATUS_STYLE: Record<string, string> = {
  PENDENTE: "badge-pendente",
  PAGO: "badge-ativo",
  CANCELADO: "badge-arquivado",
};

export default function FinanceiroPage() {
  const toast = useToast();
  const [entries, setEntries] = useState<Entry[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [monthlyData, setMonthlyData] = useState<MonthlyData[]>([]);
  const [loading, setLoading] = useState(true);
  const [filtroTipo, setFiltroTipo] = useState("");
  const [filtroStatus, setFiltroStatus] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const {
    register: registerFin,
    handleSubmit: handleSubmitFin,
    reset: resetFin,
    formState: { errors: finErrors, isSubmitting: finSubmitting },
  } = useForm<FinanceiroInput>({
    resolver: zodResolver(FinanceiroSchema) as Resolver<FinanceiroInput>,
    defaultValues: { tipo: "RECEITA", status: "PENDENTE" },
  });

  useEffect(() => { fetchEntries(); fetchSummary(); }, [filtroTipo, filtroStatus]);
  useEffect(() => { fetchMonthly(); }, []);

  async function fetchEntries() {
    setLoading(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const params = new URLSearchParams();
      if (filtroTipo) params.set("tipo", filtroTipo);
      if (filtroStatus) params.set("status", filtroStatus);
      const res = await fetch(`/api/v1/financial?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setEntries(await res.json());
    } finally { setLoading(false); }
  }

  async function fetchSummary() {
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/financial/summary", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setSummary(data.summary ?? data);
      }
    } catch {}
  }

  async function fetchMonthly() {
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/financial/monthly", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setMonthlyData(data.data ?? []);
      }
    } catch {}
  }

  async function salvar(data: FinanceiroInput) {
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/financial", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          ...data,
          data_vencimento: data.vencimento || null,
        }),
      });
      if (res.ok) {
        setShowModal(false);
        resetFin();
        fetchEntries();
        fetchSummary();
      } else {
        toast.error("Erro ao salvar lançamento. Tente novamente.");
      }
    } catch {
      toast.error("Erro de conexão. Tente novamente.");
    }
  }

  async function excluirLancamento(id: string) {
    const token = localStorage.getItem("afj_access_token");
    const res = await fetch(`/api/v1/financial/${id}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) { setDeletingId(null); fetchEntries(); fetchSummary(); }
  }

  async function exportarCSV() {
    const token = localStorage.getItem("afj_access_token");
    const res = await fetch("/api/v1/financial/export", {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      const blob = await res.blob();
      const a = Object.assign(document.createElement("a"), {
        href: URL.createObjectURL(blob),
        download: "financeiro.csv",
      });
      a.click();
      URL.revokeObjectURL(a.href);
    }
  }

  async function marcarPago(id: string) {
    const token = localStorage.getItem("afj_access_token");
    await fetch(`/api/v1/financial/${id}/mark-paid`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    fetchEntries();
    fetchSummary();
  }

  const fmt = (v: number) => `R$ ${v.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`;

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Financeiro" }]} />
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-semibold text-afj-black">Financeiro</h1>
          <p className="text-afj-black/50 text-sm">Honorários, despesas e fluxo de caixa</p>
        </div>
        <div className="flex gap-2">
          <button onClick={exportarCSV} className="btn-afj-outline rounded-md flex items-center gap-2" title="Exportar CSV" aria-label="Exportar lançamentos como CSV">
            <FileDown size={14} />
            Exportar
          </button>
          <button onClick={() => setShowModal(true)} className="btn-afj-primary rounded-md flex items-center gap-2">
            <Plus size={15} />
            Novo Lançamento
          </button>
        </div>
      </div>

      {/* KPIs */}
      {summary && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <div className="afj-card p-4">
            <div className="flex items-center gap-2 mb-2">
              <TrendingUp size={16} className="text-green-600" />
              <span className="text-xs text-afj-black/50">Receitas Pagas</span>
            </div>
            <p className="text-xl font-bold text-green-600">{fmt(summary.receitas_pagas || 0)}</p>
          </div>
          <div className="afj-card p-4">
            <div className="flex items-center gap-2 mb-2">
              <Clock size={16} className="text-amber-600" />
              <span className="text-xs text-afj-black/50">A Receber</span>
            </div>
            <p className="text-xl font-bold text-amber-600">{fmt(summary.receitas_pendentes || 0)}</p>
          </div>
          <div className="afj-card p-4">
            <div className="flex items-center gap-2 mb-2">
              <TrendingDown size={16} className="text-red-500" />
              <span className="text-xs text-afj-black/50">Despesas Pagas</span>
            </div>
            <p className="text-xl font-bold text-red-500">{fmt(summary.despesas_pagas || 0)}</p>
          </div>
          <div className="afj-card p-4">
            <div className="flex items-center gap-2 mb-2">
              <DollarSign size={16} className="text-afj-gold" />
              <span className="text-xs text-afj-black/50">Saldo Atual</span>
            </div>
            <p className={`text-xl font-bold ${(summary.saldo_atual || 0) >= 0 ? "text-green-600" : "text-red-500"}`}>
              {fmt(summary.saldo_atual || 0)}
            </p>
          </div>
        </div>
      )}

      {/* Gráfico mensal */}
      {monthlyData.length > 0 && (
        <div className="afj-card p-5">
          <div className="flex items-center gap-2 mb-4">
            <BarChart3 size={16} className="text-afj-gold" />
            <p className="text-sm font-semibold text-afj-black">Receitas vs Despesas — últimos 6 meses</p>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={monthlyData} margin={{ top: 0, right: 10, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E8E3DA" />
              <XAxis dataKey="mes" tick={{ fontSize: 11, fill: "#1A1A1A99" }} />
              <YAxis tick={{ fontSize: 11, fill: "#1A1A1A99" }} tickFormatter={(v) => `R$${(v/1000).toFixed(0)}k`} />
              <Tooltip
                formatter={(value: number) => [`R$ ${value.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`, undefined]}
                contentStyle={{ fontSize: 12 }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="receitas" fill="#16a34a" name="Receitas" radius={[2, 2, 0, 0]} />
              <Bar dataKey="despesas" fill="#ef4444" name="Despesas" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Filtros */}
      <div className="flex gap-3">
        <select
          value={filtroTipo}
          onChange={(e) => setFiltroTipo(e.target.value)}
          className="border border-afj-cream-dark rounded-md px-3 py-2 text-sm bg-white focus:outline-none focus:border-afj-gold"
        >
          <option value="">Todos os tipos</option>
          <option value="RECEITA">Receitas</option>
          <option value="DESPESA">Despesas</option>
        </select>
        <select
          value={filtroStatus}
          onChange={(e) => setFiltroStatus(e.target.value)}
          className="border border-afj-cream-dark rounded-md px-3 py-2 text-sm bg-white focus:outline-none focus:border-afj-gold"
        >
          <option value="">Todos os status</option>
          <option value="PENDENTE">Pendente</option>
          <option value="PAGO">Pago</option>
          <option value="CANCELADO">Cancelado</option>
        </select>
      </div>

      {/* Tabela */}
      {loading ? (
        <div className="afj-card p-4 space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-11 bg-afj-cream-dark rounded animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="afj-card overflow-hidden">
          <div className="overflow-x-auto">
          <table className="afj-table">
            <thead>
              <tr>
                <th>Descrição</th>
                <th>Tipo</th>
                <th>Categoria</th>
                <th>Valor</th>
                <th>Vencimento</th>
                <th>Status</th>
                <th>Ações</th>
              </tr>
            </thead>
            <tbody>
              {entries.length === 0 ? (
                <tr><td colSpan={7} className="text-center text-afj-black/40">Nenhum lançamento encontrado</td></tr>
              ) : entries.map((e) => (
                <tr key={e.id}>
                  <td className="font-medium">{e.descricao}</td>
                  <td>
                    <span className={`text-xs px-2 py-0.5 rounded-full ${e.tipo === "RECEITA" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                      {e.tipo}
                    </span>
                  </td>
                  <td className="text-afj-black/60 text-xs">{e.categoria || "—"}</td>
                  <td className={`font-semibold ${e.tipo === "RECEITA" ? "text-green-600" : "text-red-500"}`}>
                    {fmt(e.valor)}
                  </td>
                  <td className="text-afj-black/60 text-xs">
                    {e.data_vencimento ? new Date(e.data_vencimento).toLocaleDateString("pt-BR") : "—"}
                  </td>
                  <td>
                    <span className={STATUS_STYLE[e.status] ?? "badge-arquivado"}>{e.status}</span>
                  </td>
                  <td>
                    <div className="flex items-center gap-2">
                      {e.status === "PENDENTE" && (
                        <button
                          onClick={() => marcarPago(e.id)}
                          className="text-xs text-afj-gold hover:text-afj-gold/70 flex items-center gap-1"
                        >
                          <CheckCircle size={12} />
                          Pago
                        </button>
                      )}
                      <button
                        onClick={() => setDeletingId(e.id)}
                        className="text-afj-black/30 hover:text-red-500 transition-colors"
                        aria-label="Excluir lançamento"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      )}

      {/* Modal confirmação exclusão */}
      {deletingId && (
        <div className="fixed inset-0 bg-afj-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl p-6 w-full max-w-sm shadow-2xl text-center">
            <p className="font-semibold text-afj-black mb-2">Excluir lançamento?</p>
            <p className="text-afj-black/50 text-sm mb-5">Esta ação não pode ser desfeita.</p>
            <div className="flex gap-3">
              <button onClick={() => setDeletingId(null)} className="flex-1 btn-afj-outline rounded-md">Cancelar</button>
              <button onClick={() => excluirLancamento(deletingId)} className="flex-1 bg-red-500 text-white rounded-md py-2 text-sm font-medium hover:bg-red-600">Excluir</button>
            </div>
          </div>
        </div>
      )}

      {/* Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-afj-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-sm p-6 w-full max-w-md shadow-2xl">
            <h2 className="font-display text-xl font-semibold text-afj-black mb-5">Novo Lançamento</h2>
            <form onSubmit={handleSubmitFin(salvar)} className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">Tipo *</label>
                  <select
                    {...registerFin("tipo")}
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                  >
                    <option value="RECEITA">Receita</option>
                    <option value="DESPESA">Despesa</option>
                  </select>
                  {finErrors.tipo && <p className="text-xs text-red-500 mt-1">{finErrors.tipo.message}</p>}
                </div>
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">Status</label>
                  <select
                    {...registerFin("status")}
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                  >
                    <option value="PENDENTE">Pendente</option>
                    <option value="PAGO">Pago</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="text-xs text-afj-black/60 block mb-1">Descrição *</label>
                <input
                  {...registerFin("descricao")}
                  type="text"
                  placeholder="Ex: Honorários advocatícios"
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                />
                {finErrors.descricao && <p className="text-xs text-red-500 mt-1">{finErrors.descricao.message}</p>}
              </div>
              <div>
                <label className="text-xs text-afj-black/60 block mb-1">Categoria</label>
                <input
                  {...registerFin("categoria")}
                  type="text"
                  placeholder="Ex: Honorários, Custas..."
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                />
              </div>
              <div>
                <label className="text-xs text-afj-black/60 block mb-1">Valor (R$) *</label>
                <input
                  {...registerFin("valor")}
                  type="number"
                  step="0.01"
                  placeholder="0,00"
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                />
                {finErrors.valor && <p className="text-xs text-red-500 mt-1">{finErrors.valor.message}</p>}
              </div>
              <div>
                <label className="text-xs text-afj-black/60 block mb-1">Vencimento</label>
                <input
                  {...registerFin("vencimento")}
                  type="date"
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                />
              </div>
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => { setShowModal(false); resetFin(); }} className="flex-1 btn-afj-outline rounded-sm">
                  Cancelar
                </button>
                <button type="submit" disabled={finSubmitting} className="flex-1 btn-afj-primary rounded-sm disabled:opacity-50">
                  {finSubmitting ? "Salvando..." : "Salvar"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
