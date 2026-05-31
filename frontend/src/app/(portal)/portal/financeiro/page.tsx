"use client";
import { useState, useEffect } from "react";
import { DollarSign, CheckCircle, Clock } from "lucide-react";
import { portalApi } from "@/lib/portalApi";
import { useToast } from "@/components/ui/Toast";

interface PortalFinanceiro {
  id: string;
  descricao: string;
  categoria: string | null;
  valor: number;
  status: string;
  data_vencimento: string | null;
  data_pagamento: string | null;
}

const STATUS_BADGE: Record<string, { cls: string; label: string }> = {
  PENDENTE: { cls: "bg-amber-100 text-amber-700", label: "Pendente" },
  PAGO: { cls: "bg-green-100 text-green-700", label: "Pago" },
  CANCELADO: { cls: "bg-gray-100 text-gray-500", label: "Cancelado" },
};

const CATEGORIA_LABEL: Record<string, string> = {
  HONORARIOS: "Honorários",
  CUSTAS: "Custas",
  DESLOCAMENTO: "Deslocamento",
};

function formatBRL(value: number) {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);
}

export default function PortalFinanceiroPage() {
  const toast = useToast();
  const [entries, setEntries] = useState<PortalFinanceiro[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("TODOS");

  useEffect(() => {
    portalApi.get<PortalFinanceiro[]>("/portal/financial")
      .then(setEntries)
      .catch(() => toast.error("Erro ao carregar dados financeiros."))
      .finally(() => setLoading(false));
  }, []);

  const totalPendente = entries.filter((e) => e.status === "PENDENTE").reduce((s, e) => s + e.valor, 0);
  const totalPago = entries.filter((e) => e.status === "PAGO").reduce((s, e) => s + e.valor, 0);

  const filtered = filter === "TODOS" ? entries : entries.filter((e) => e.status === filter);

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-7 w-48 bg-gray-200 rounded animate-pulse" />
        <div className="grid grid-cols-2 gap-4">
          {[1, 2].map((i) => <div key={i} className="bg-white rounded-xl border p-5 h-20 animate-pulse" />)}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-gray-900">Financeiro</h1>

      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="bg-white rounded-xl border border-amber-200 p-5">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-9 h-9 rounded-lg bg-amber-50 flex items-center justify-center">
              <Clock size={18} className="text-amber-600" />
            </div>
            <p className="text-sm font-medium text-gray-600">Valor Pendente</p>
          </div>
          <p className="text-2xl font-bold text-amber-700">{formatBRL(totalPendente)}</p>
        </div>
        <div className="bg-white rounded-xl border border-green-200 p-5">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-9 h-9 rounded-lg bg-green-50 flex items-center justify-center">
              <CheckCircle size={18} className="text-green-600" />
            </div>
            <p className="text-sm font-medium text-gray-600">Total Pago</p>
          </div>
          <p className="text-2xl font-bold text-green-700">{formatBRL(totalPago)}</p>
        </div>
      </div>

      {/* Filter */}
      <div className="flex gap-2">
        {["TODOS", "PENDENTE", "PAGO", "CANCELADO"].map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors border ${
              filter === s
                ? "bg-[#B8954A] text-white border-[#B8954A]"
                : "bg-white text-gray-600 border-gray-200 hover:border-[#B8954A]/40"
            }`}
          >
            {s === "TODOS" ? "Todos" : STATUS_BADGE[s]?.label ?? s}
          </button>
        ))}
      </div>

      {/* List */}
      {filtered.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
          <DollarSign className="mx-auto text-gray-300 mb-3" size={36} />
          <p className="font-semibold text-gray-600">Nenhum lançamento encontrado</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Descrição</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider hidden sm:table-cell">Categoria</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider hidden md:table-cell">Vencimento</th>
                <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Valor</th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {filtered.map((e) => {
                const badge = STATUS_BADGE[e.status] ?? { cls: "bg-gray-100 text-gray-500", label: e.status };
                return (
                  <tr key={e.id} className="hover:bg-gray-50/50 transition-colors">
                    <td className="px-4 py-3">
                      <p className="font-medium text-gray-800">{e.descricao}</p>
                      {e.data_pagamento && e.status === "PAGO" && (
                        <p className="text-[10px] text-gray-400 mt-0.5">
                          Pago em {new Date(e.data_pagamento).toLocaleDateString("pt-BR")}
                        </p>
                      )}
                    </td>
                    <td className="px-4 py-3 hidden sm:table-cell">
                      <span className="text-xs text-gray-500">{e.categoria ? (CATEGORIA_LABEL[e.categoria] ?? e.categoria) : "—"}</span>
                    </td>
                    <td className="px-4 py-3 hidden md:table-cell">
                      <span className="text-xs text-gray-500">
                        {e.data_vencimento ? new Date(e.data_vencimento).toLocaleDateString("pt-BR") : "—"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className="font-semibold text-gray-800">{formatBRL(e.valor)}</span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${badge.cls}`}>
                        {badge.label}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
