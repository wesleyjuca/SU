"use client";
import { useState, useEffect } from "react";
import { CheckCircle, XCircle, AlertTriangle, Clock, FileText } from "lucide-react";

interface Approval {
  id: string;
  tipo: string;
  titulo: string;
  descricao: string;
  ai_suggestion: Record<string, unknown>;
  prioridade: string;
  status: string;
  created_at: string;
}

function PriorityBadge({ prioridade }: { prioridade: string }) {
  const styles: Record<string, string> = {
    URGENT: "badge-urgente",
    HIGH: "bg-orange-100 text-orange-800 text-xs font-medium px-2 py-0.5 rounded-full",
    NORMAL: "badge-pendente",
    LOW: "badge-arquivado",
  };
  return <span className={styles[prioridade] ?? "badge-pendente"}>{prioridade}</span>;
}

export default function AprovacoesPage() {
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [selected, setSelected] = useState<Approval | null>(null);
  const [loading, setLoading] = useState(true);
  const [rejectionReason, setRejectionReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

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
        if (data.length > 0) setSelected(data[0]);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  async function resolve(approved: boolean) {
    if (!selected) return;
    if (!approved && !rejectionReason.trim()) {
      alert("Justificativa obrigatória para rejeição");
      return;
    }
    setSubmitting(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/approvals/${selected.id}/resolve`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          approved,
          rejection_reason: approved ? null : rejectionReason,
        }),
      });
      if (res.ok) {
        setApprovals((prev) => prev.filter((a) => a.id !== selected.id));
        setSelected(null);
        setRejectionReason("");
        await fetchApprovals();
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-7xl mx-auto space-y-4">
      <div>
        <h1 className="font-display text-2xl font-semibold text-afj-black">Aprovações Pendentes</h1>
        <p className="text-afj-black/50 text-sm">Ações que aguardam validação humana antes de serem executadas</p>
      </div>

      {loading ? (
        <div className="afj-card p-8 text-center text-afj-black/40">Carregando aprovações...</div>
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
              <button
                key={a.id}
                onClick={() => setSelected(a)}
                className={`w-full text-left p-4 rounded-lg border transition-all ${
                  selected?.id === a.id
                    ? "border-afj-gold bg-afj-gold/5"
                    : "border-afj-cream-dark bg-white hover:border-afj-gold/40"
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <PriorityBadge prioridade={a.prioridade} />
                  <span className="text-afj-black/30 text-xs flex items-center gap-1">
                    <Clock size={10} />
                    {new Date(a.created_at).toLocaleDateString("pt-BR")}
                  </span>
                </div>
                <p className="text-sm font-medium text-afj-black mt-2 line-clamp-2">{a.titulo}</p>
                <p className="text-xs text-afj-black/50 mt-1">{a.tipo}</p>
              </button>
            ))}
          </div>

          {/* Painel de detalhes direito */}
          <div className="lg:col-span-2 overflow-y-auto">
            {selected ? (
              <div className="afj-card-premium p-6 space-y-5">
                <div className="flex items-start justify-between">
                  <div>
                    <PriorityBadge prioridade={selected.prioridade} />
                    <h2 className="font-display text-xl font-semibold text-afj-black mt-2">{selected.titulo}</h2>
                    <p className="text-sm text-afj-black/50 mt-0.5">{selected.tipo}</p>
                  </div>
                  <AlertTriangle className="text-amber-500 flex-shrink-0" size={20} />
                </div>

                {/* Descrição */}
                {selected.descricao && (
                  <div>
                    <h3 className="text-sm font-semibold text-afj-black mb-2">Descrição</h3>
                    <p className="text-sm text-afj-black/70 bg-afj-cream rounded-md p-3">{selected.descricao}</p>
                  </div>
                )}

                {/* Sugestão da IA */}
                {selected.ai_suggestion && (
                  <div>
                    <h3 className="text-sm font-semibold text-afj-black mb-2 flex items-center gap-2">
                      <FileText size={14} className="text-afj-gold" />
                      Sugestão da IA
                    </h3>
                    <div className="bg-amber-50 border border-amber-200 rounded-md p-4 text-sm text-afj-black/80">
                      <pre className="whitespace-pre-wrap font-sans text-xs overflow-auto max-h-48">
                        {JSON.stringify(selected.ai_suggestion, null, 2)}
                      </pre>
                    </div>
                  </div>
                )}

                {/* Campo de justificativa para rejeição */}
                <div>
                  <label className="text-sm font-medium text-afj-black block mb-1.5">
                    Justificativa (obrigatório para rejeição)
                  </label>
                  <textarea
                    value={rejectionReason}
                    onChange={(e) => setRejectionReason(e.target.value)}
                    placeholder="Descreva o motivo da rejeição ou modificações necessárias..."
                    rows={3}
                    className="w-full border border-afj-cream-dark rounded-md px-3 py-2 text-sm text-afj-black
                               focus:outline-none focus:border-afj-gold bg-white resize-none"
                  />
                </div>

                {/* Botões de ação */}
                <div className="flex gap-3 pt-2 border-t border-afj-cream-dark">
                  <button
                    onClick={() => resolve(false)}
                    disabled={submitting}
                    className="flex items-center gap-2 px-4 py-2.5 border border-red-200 text-red-700 rounded-md text-sm
                               font-medium hover:bg-red-50 transition-colors disabled:opacity-50"
                  >
                    <XCircle size={16} />
                    Rejeitar
                  </button>
                  <button
                    onClick={() => resolve(true)}
                    disabled={submitting}
                    className="flex-1 flex items-center justify-center gap-2 btn-afj-primary rounded-md disabled:opacity-50"
                  >
                    <CheckCircle size={16} />
                    {submitting ? "Aprovando..." : "Aprovar"}
                  </button>
                </div>
              </div>
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
