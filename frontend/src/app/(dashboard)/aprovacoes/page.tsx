"use client";
import { useState, useEffect } from "react";
import { CheckCircle } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { ApprovalCard, ApprovalListItem, type Approval } from "@/components/approvals/ApprovalCard";

export default function AprovacoesPage() {
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [selected, setSelected] = useState<Approval | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchApprovals();
  }, []);

  async function fetchApprovals() {
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/approvals?status=PENDENTE", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setApprovals(data);
        if (data.length > 0 && !selected) setSelected(data[0]);
      }
    } finally {
      setLoading(false);
    }
  }

  function handleResolved(id: string) {
    const remaining = approvals.filter((a) => a.id !== id);
    setApprovals(remaining);
    setSelected(remaining.length > 0 ? remaining[0] : null);
  }

  return (
    <div className="max-w-7xl mx-auto space-y-4">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Aprovações" }]} />
      <div className="afj-page-header">
        <div>
          <h1 className="font-display text-2xl font-semibold text-afj-black">Aprovações Pendentes</h1>
          <p className="text-afj-black/50 text-sm">
            Ações que aguardam validação humana antes de serem executadas
            {approvals.length > 0 && ` — ${approvals.length} pendente(s)`}
          </p>
        </div>
      </div>

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="afj-card p-5 h-20 animate-pulse bg-afj-cream-dark/40" />
          ))}
        </div>
      ) : approvals.length === 0 ? (
        <div className="afj-card p-12 text-center">
          <CheckCircle className="mx-auto text-green-500 mb-3" size={40} />
          <p className="font-semibold text-afj-black">Nenhuma aprovação pendente</p>
          <p className="text-afj-black/40 text-sm mt-1">Todas as ações dos agentes foram revisadas</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-[calc(100vh-200px)]">
          {/* Lista esquerda */}
          <div className="lg:col-span-1 overflow-y-auto space-y-2">
            {approvals.map((a) => (
              <ApprovalListItem
                key={a.id}
                approval={a}
                selected={selected?.id === a.id}
                onClick={() => setSelected(a)}
              />
            ))}
          </div>

          {/* Painel de detalhes direito */}
          <div className="lg:col-span-2 overflow-y-auto">
            {selected ? (
              <ApprovalCard approval={selected} onResolved={handleResolved} />
            ) : (
              <div className="afj-card p-12 text-center text-afj-black/40">
                Selecione uma aprovação para revisar
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
