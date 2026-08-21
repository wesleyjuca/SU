"use client";
import { useState, useEffect, useCallback } from "react";
import { CheckCircle } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { ApprovalCard, ApprovalListItem, type Approval } from "@/components/approvals/ApprovalCard";

type Aba = "pendentes" | "resolvidas";

export default function AprovacoesPage() {
  const [aba, setAba] = useState<Aba>("pendentes");
  const [pendentes, setPendentes] = useState<Approval[]>([]);
  const [resolvidas, setResolvidas] = useState<Approval[]>([]);
  const [selected, setSelected] = useState<Approval | null>(null);
  const [loading, setLoading] = useState(true);

  const approvals = aba === "pendentes" ? pendentes : resolvidas;

  const fetchPendentes = useCallback(async () => {
    const token = localStorage.getItem("afj_access_token");
    const res = await fetch("/api/v1/approvals?status=PENDENTE", {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) return (await res.json()) as Approval[];
    return [];
  }, []);

  // Fase 205.2 — "Resolvidas": junta APROVADO + REJEITADO (o backend só
  // filtra por um status por vez) e ordena pela data de resolução mais
  // recente primeiro.
  const fetchResolvidas = useCallback(async () => {
    const token = localStorage.getItem("afj_access_token");
    const [aprovadasRes, rejeitadasRes] = await Promise.all([
      fetch("/api/v1/approvals?status=APROVADO&limit=100", { headers: { Authorization: `Bearer ${token}` } }),
      fetch("/api/v1/approvals?status=REJEITADO&limit=100", { headers: { Authorization: `Bearer ${token}` } }),
    ]);
    const [aprovadas, rejeitadas] = await Promise.all([
      aprovadasRes.ok ? aprovadasRes.json() : [],
      rejeitadasRes.ok ? rejeitadasRes.json() : [],
    ]);
    return [...aprovadas, ...rejeitadas].sort(
      (a: Approval, b: Approval) => new Date(b.resolved_at || b.created_at).getTime() - new Date(a.resolved_at || a.created_at).getTime()
    ) as Approval[];
  }, []);

  useEffect(() => {
    setLoading(true);
    setSelected(null);
    const carregar = aba === "pendentes" ? fetchPendentes : fetchResolvidas;
    carregar()
      .then((data) => {
        if (aba === "pendentes") setPendentes(data);
        else setResolvidas(data);
        if (data.length > 0) setSelected(data[0]);
      })
      .finally(() => setLoading(false));
  }, [aba, fetchPendentes, fetchResolvidas]);

  function handleResolved(id: string) {
    const remaining = pendentes.filter((a) => a.id !== id);
    setPendentes(remaining);
    setSelected(remaining.length > 0 ? remaining[0] : null);
  }

  return (
    <div className="max-w-7xl mx-auto space-y-4">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Aprovações" }]} />
      <div className="afj-page-header">
        <div>
          <h1 className="font-display text-2xl font-semibold text-afj-black">
            {aba === "pendentes" ? "Aprovações Pendentes" : "Histórico de Aprovações"}
          </h1>
          <p className="text-afj-black/50 text-sm">
            {aba === "pendentes"
              ? `Ações que aguardam validação humana antes de serem executadas${pendentes.length > 0 ? ` — ${pendentes.length} pendente(s)` : ""}`
              : "Aprovações e rejeições já resolvidas, mais recentes primeiro"}
          </p>
        </div>
      </div>

      {/* Abas */}
      <div className="flex items-center gap-1 border-b border-afj-cream-dark -mt-1">
        {([
          { key: "pendentes", label: "Pendentes" },
          { key: "resolvidas", label: "Resolvidas" },
        ] as const).map((t) => (
          <button
            key={t.key}
            onClick={() => setAba(t.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              aba === t.key
                ? "border-afj-gold text-afj-gold"
                : "border-transparent text-afj-black/50 hover:text-afj-black"
            }`}
          >
            {t.label}
          </button>
        ))}
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
          <p className="font-semibold text-afj-black">
            {aba === "pendentes" ? "Nenhuma aprovação pendente" : "Nenhuma aprovação resolvida ainda"}
          </p>
          <p className="text-afj-black/40 text-sm mt-1">
            {aba === "pendentes" ? "Todas as ações dos agentes foram revisadas" : "Aprovações e rejeições aparecem aqui depois de resolvidas"}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-[calc(100vh-240px)]">
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
              <ApprovalCard approval={selected} onResolved={handleResolved} readOnly={aba === "resolvidas"} />
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
