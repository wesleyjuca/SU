"use client";
import { useState } from "react";
import { CheckCircle, XCircle, AlertTriangle, FileText, Clock } from "lucide-react";

export interface Approval {
  id: string;
  tipo: string;
  titulo: string;
  descricao: string;
  ai_suggestion: Record<string, unknown>;
  prioridade: string;
  status: string;
  created_at: string;
  expires_at?: string | null;
  resolved_at?: string | null;
}

interface ApprovalCardProps {
  approval: Approval;
  onResolved: (id: string) => void;
  readOnly?: boolean;
}

// Fase 205.2 — contagem regressiva até expires_at (Fase 191: aprovação
// pendente vencida é escalada pro gestor, nunca auto-resolvida). Só faz
// sentido pra aprovações ainda PENDENTE — resolvidas não têm mais prazo.
export function ExpiresBadge({ expiresAt }: { expiresAt: string }) {
  const diffMs = new Date(expiresAt).getTime() - Date.now();
  const diffHoras = Math.round(diffMs / (1000 * 60 * 60));
  if (diffMs <= 0) {
    return (
      <span className="flex items-center gap-1 text-[10px] font-medium text-red-600" title={`Venceu em ${new Date(expiresAt).toLocaleString("pt-BR")}`}>
        <Clock size={10} /> vencida
      </span>
    );
  }
  const texto = diffHoras < 24 ? `${diffHoras}h restantes` : `${Math.round(diffHoras / 24)}d restantes`;
  const urgente = diffHoras < 24;
  return (
    <span
      className={`flex items-center gap-1 text-[10px] font-medium ${urgente ? "text-amber-600" : "text-afj-black/40"}`}
      title={`Vence em ${new Date(expiresAt).toLocaleString("pt-BR")}`}
    >
      <Clock size={10} /> {texto}
    </span>
  );
}

const RESOLVED_STATUS_STYLE: Record<string, string> = {
  APROVADO: "bg-green-50 text-green-700 border border-green-200",
  REJEITADO: "bg-red-50 text-red-700 border border-red-200",
};

export function ResolvedStatusBadge({ status }: { status: string }) {
  return (
    <span className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-sm ${RESOLVED_STATUS_STYLE[status] ?? "bg-gray-50 text-gray-600 border border-gray-200"}`}>
      {status === "APROVADO" ? "Aprovada" : status === "REJEITADO" ? "Rejeitada" : status}
    </span>
  );
}

const PRIORITY_STYLE: Record<string, string> = {
  URGENT: "badge-urgente",
  HIGH: "bg-orange-100 text-orange-800 text-xs font-medium px-2 py-0.5 rounded-full",
  NORMAL: "badge-pendente",
  LOW: "badge-arquivado",
};

export function PriorityBadge({ prioridade }: { prioridade: string }) {
  return (
    <span className={PRIORITY_STYLE[prioridade] ?? "badge-pendente"}>{prioridade}</span>
  );
}

export function ApprovalListItem({
  approval,
  selected,
  onClick,
}: {
  approval: Approval;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left p-4 rounded-lg border transition-all ${
        selected
          ? "border-afj-gold bg-afj-gold/5"
          : "border-afj-cream-dark bg-white hover:border-afj-gold/40"
      }`}
    >
      <div className="flex items-center justify-between mb-1">
        <PriorityBadge prioridade={approval.prioridade} />
        {approval.status === "PENDENTE" ? (
          approval.expires_at ? (
            <ExpiresBadge expiresAt={approval.expires_at} />
          ) : (
            <span className="text-afj-black/30 text-xs flex items-center gap-1">
              <Clock size={10} />
              {new Date(approval.created_at).toLocaleDateString("pt-BR")}
            </span>
          )
        ) : (
          <ResolvedStatusBadge status={approval.status} />
        )}
      </div>
      <p className="text-sm font-medium text-afj-black mt-2 line-clamp-2">{approval.titulo}</p>
      <p className="text-xs text-afj-black/50 mt-1">{approval.tipo}</p>
      {approval.status !== "PENDENTE" && approval.resolved_at && (
        <p className="text-[10px] text-afj-black/30 mt-1">
          Resolvida em {new Date(approval.resolved_at).toLocaleString("pt-BR")}
        </p>
      )}
    </button>
  );
}

export function ApprovalCard({ approval, onResolved, readOnly = false }: ApprovalCardProps) {
  const [rejectionReason, setRejectionReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function resolve(approved: boolean) {
    if (!approved && !rejectionReason.trim()) {
      setError("Justificativa obrigatória para rejeição");
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/approvals/${approval.id}/resolve`, {
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
        onResolved(approval.id);
      } else {
        const err = await res.json();
        setError(err.detail || "Erro ao processar aprovação");
      }
    } catch {
      setError("Erro de conexão");
    } finally {
      setSubmitting(false);
    }
  }

  // Format AI suggestion for display
  const suggestionText = typeof approval.ai_suggestion === "string"
    ? approval.ai_suggestion
    : JSON.stringify(approval.ai_suggestion, null, 2);

  return (
    <div className="afj-card p-6 space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <PriorityBadge prioridade={approval.prioridade} />
          <h2 className="font-display text-xl font-semibold text-afj-black mt-2">{approval.titulo}</h2>
          <p className="text-sm text-afj-black/50 mt-0.5">{approval.tipo}</p>
        </div>
        <AlertTriangle className="text-amber-500 flex-shrink-0 mt-1" size={20} />
      </div>

      {/* Descrição */}
      {approval.descricao && (
        <div>
          <h3 className="text-sm font-semibold text-afj-black mb-2">O que o agente quer fazer</h3>
          <p className="text-sm text-afj-black/70 bg-afj-cream rounded-md p-3 leading-relaxed">
            {approval.descricao}
          </p>
        </div>
      )}

      {/* Sugestão da IA */}
      {approval.ai_suggestion && Object.keys(approval.ai_suggestion).length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-afj-black mb-2 flex items-center gap-2">
            <FileText size={14} className="text-afj-gold" />
            Conteúdo / Sugestão da IA
          </h3>
          <div className="bg-amber-50 border border-amber-200 rounded-md p-4">
            <pre className="whitespace-pre-wrap font-sans text-xs text-afj-black/80 overflow-auto max-h-60 leading-relaxed">
              {suggestionText}
            </pre>
          </div>
        </div>
      )}

      {readOnly ? (
        // Fase 205.2 — aba "Resolvidas": mostra o desfecho em vez do
        // formulário de decisão (já não há mais nada a decidir aqui).
        <div className={`rounded-md px-3 py-2.5 text-sm ${approval.status === "APROVADO" ? "bg-green-50 border border-green-200 text-green-800" : "bg-red-50 border border-red-200 text-red-800"}`}>
          <div className="flex items-center gap-2 font-medium">
            <ResolvedStatusBadge status={approval.status} />
            {approval.resolved_at && (
              <span className="text-xs font-normal opacity-70">
                em {new Date(approval.resolved_at).toLocaleString("pt-BR")}
              </span>
            )}
          </div>
        </div>
      ) : (
        <>
          {/* Justificativa */}
          <div>
            <label className="text-sm font-medium text-afj-black block mb-1.5">
              Justificativa <span className="text-afj-black/40 font-normal">(obrigatório para rejeição)</span>
            </label>
            <textarea
              value={rejectionReason}
              onChange={(e) => {
                setRejectionReason(e.target.value);
                setError(null);
              }}
              placeholder="Descreva o motivo da rejeição ou as modificações necessárias..."
              rows={3}
              className="w-full border border-afj-cream-dark rounded-md px-3 py-2 text-sm text-afj-black
                         focus:outline-none focus:border-afj-gold bg-white resize-none"
            />
            {error && <p className="text-xs text-red-600 mt-1">{error}</p>}
          </div>

          {/* Aviso de responsabilidade */}
          <div className="bg-blue-50 border border-blue-100 rounded-md px-3 py-2 text-xs text-blue-800">
            Ao aprovar, você confirma ter revisado o conteúdo. Esta ação será registrada no log de auditoria.
          </div>

          {/* Botões — empilha em telas muito estreitas (Fase 207.2) pra não
              espremer o alvo de toque do "Rejeitar" ao lado do "Aprovar". */}
          <div className="flex flex-col sm:flex-row gap-3 pt-2 border-t border-afj-cream-dark">
            <button
              onClick={() => resolve(false)}
              disabled={submitting}
              className="min-h-[44px] flex items-center justify-center gap-2 px-4 py-2.5 border border-red-200 text-red-700 rounded-md
                         text-sm font-medium hover:bg-red-50 transition-colors disabled:opacity-50"
            >
              <XCircle size={16} />
              Rejeitar
            </button>
            <button
              onClick={() => resolve(true)}
              disabled={submitting}
              className="flex-1 min-h-[44px] flex items-center justify-center gap-2 btn-afj-primary rounded-md disabled:opacity-50"
            >
              <CheckCircle size={16} />
              {submitting ? "Processando..." : "Aprovar"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
