"use client";
import { useState, useEffect } from "react";
import { DollarSign, TrendingUp, TrendingDown, Plus, CheckCircle, Clock, Trash2 } from "lucide-react";

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

const STATUS_STYLE: Record<string, string> = {
  PENDENTE: "badge-pendente",
  PAGO: "badge-ativo",
  CANCELADO: "badge-arquivado",
};

export default function FinanceiroPage() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [filtroTipo, setFiltroTipo] = useState("");
  const [filtroStatus, setFiltroStatus] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [form, setForm] = useState({
    tipo: "RECEITA",
    categoria: "",
    descricao: "",
    valor: "",
    data_vencimento: "",
    status: "PENDENTE",
  });

  useEffect(() => { fetchEntries(); fetchSummary(); }, [filtroTipo, filtroStatus]);

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

  async function salvar(e: React.FormEvent) {
    e.preventDefault();
    const token = localStorage.getItem("afj_access_token");
    const res = await fetch("/api/v1/financial", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({
        ...form,
        valor: parseFloat(form.valor),
        data_vencimento: form.data_vencimento || null,
      }),
    });
    if (res.ok) { setShowModal(false); fetchEntries(); fetchSummary(); }
  }

  async function excluirLancamento(id: string) {
    const token = localStorage.getItem("afj_access_token");
    const res = await fetch(`/api/v1/financial/${id}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) { setDeletingId(null); fetchEntries(); fetchSummary(); }
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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-semibold text-afj-black">Financeiro</h1>
          <p className="text-afj-black/50 text-sm">Honorários, despesas e fluxo de caixa</p>
        </div>
        <button onClick={() => setShowModal(true)} className="btn-afj-primary rounded-md flex items-center gap-2">
          <Plus size={15} />
          Novo Lançamento
        </button>
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
        <div className="afj-card p-8 text-center text-afj-black/40">Carregando...</div>
      ) : (
        <div className="afj-card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-afj-cream-dark bg-afj-cream/50">
                <th className="text-left px-4 py-3 text-afj-black/50 font-medium">Descrição</th>
                <th className="text-left px-4 py-3 text-afj-black/50 font-medium">Tipo</th>
                <th className="text-left px-4 py-3 text-afj-black/50 font-medium">Categoria</th>
                <th className="text-left px-4 py-3 text-afj-black/50 font-medium">Valor</th>
                <th className="text-left px-4 py-3 text-afj-black/50 font-medium">Vencimento</th>
                <th className="text-left px-4 py-3 text-afj-black/50 font-medium">Status</th>
                <th className="text-left px-4 py-3 text-afj-black/50 font-medium">Ações</th>
              </tr>
            </thead>
            <tbody>
              {entries.length === 0 ? (
                <tr><td colSpan={7} className="px-4 py-8 text-center text-afj-black/40">Nenhum lançamento encontrado</td></tr>
              ) : entries.map((e) => (
                <tr key={e.id} className="border-b border-afj-cream-dark hover:bg-afj-cream/30 transition-colors">
                  <td className="px-4 py-3 font-medium text-afj-black">{e.descricao}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${e.tipo === "RECEITA" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                      {e.tipo}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-afj-black/60 text-xs">{e.categoria || "—"}</td>
                  <td className={`px-4 py-3 font-semibold ${e.tipo === "RECEITA" ? "text-green-600" : "text-red-500"}`}>
                    {fmt(e.valor)}
                  </td>
                  <td className="px-4 py-3 text-afj-black/60 text-xs">
                    {e.data_vencimento ? new Date(e.data_vencimento).toLocaleDateString("pt-BR") : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <span className={STATUS_STYLE[e.status] ?? "badge-arquivado"}>{e.status}</span>
                  </td>
                  <td className="px-4 py-3">
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
                        title="Excluir"
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
          <div className="bg-white rounded-xl p-6 w-full max-w-md shadow-2xl">
            <h2 className="font-display text-xl font-semibold text-afj-black mb-5">Novo Lançamento</h2>
            <form onSubmit={salvar} className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">Tipo *</label>
                  <select value={form.tipo} onChange={(e) => setForm({ ...form, tipo: e.target.value })}
                    className="w-full border border-afj-cream-dark rounded-md px-3 py-2 text-sm focus:outline-none focus:border-afj-gold">
                    <option value="RECEITA">Receita</option>
                    <option value="DESPESA">Despesa</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">Status</label>
                  <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}
                    className="w-full border border-afj-cream-dark rounded-md px-3 py-2 text-sm focus:outline-none focus:border-afj-gold">
                    <option value="PENDENTE">Pendente</option>
                    <option value="PAGO">Pago</option>
                  </select>
                </div>
              </div>
              {[
                { label: "Descrição *", key: "descricao", type: "text" },
                { label: "Categoria", key: "categoria", type: "text" },
                { label: "Valor (R$) *", key: "valor", type: "number" },
                { label: "Vencimento", key: "data_vencimento", type: "date" },
              ].map(({ label, key, type }) => (
                <div key={key}>
                  <label className="text-xs text-afj-black/60 block mb-1">{label}</label>
                  <input type={type} step={type === "number" ? "0.01" : undefined}
                    value={(form as any)[key]}
                    onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                    className="w-full border border-afj-cream-dark rounded-md px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                    required={label.includes("*")} />
                </div>
              ))}
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => setShowModal(false)} className="flex-1 btn-afj-outline rounded-md">Cancelar</button>
                <button type="submit" className="flex-1 btn-afj-primary rounded-md">Salvar</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
