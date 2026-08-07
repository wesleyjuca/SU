"use client";
import { useState, useEffect, useCallback } from "react";
import { Sparkles, RefreshCw, Check, X, ChevronDown, ChevronUp } from "lucide-react";
import { api } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";

interface CustomAgentRow {
  id: string;
  name: string;
  description: string;
  system_prompt: string;
  rag_collections: string[] | null;
  status: string;
  max_cost_usd_per_run: number;
  created_by: string;
  created_at: string;
}

const STATUS_FILTROS = [
  { value: "PENDENTE", label: "Pendentes" },
  { value: "APROVADO", label: "Aprovados" },
  { value: "REJEITADO", label: "Rejeitados" },
];

export function BrainCustomAgents() {
  const toast = useToast();
  const [status, setStatus] = useState("PENDENTE");
  const [agentes, setAgentes] = useState<CustomAgentRow[] | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [expandido, setExpandido] = useState<string | null>(null);
  const [resolvendo, setResolvendo] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    setCarregando(true);
    try {
      const data = await api.get<CustomAgentRow[]>(`/custom-agents?status=${status}`);
      setAgentes(data);
    } catch {
      setAgentes([]);
    } finally {
      setCarregando(false);
    }
  }, [status]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  async function resolver(id: string, approved: boolean) {
    setResolvendo(id);
    try {
      const rejection_reason = approved ? undefined : window.prompt("Motivo da rejeição (opcional):") || undefined;
      await api.post(`/custom-agents/${id}/resolve`, { approved, rejection_reason });
      toast.success(approved ? "Agente aprovado." : "Agente rejeitado.");
      setAgentes((prev) => (prev ?? []).filter((a) => a.id !== id));
    } catch (err: any) {
      toast.error(err?.message || "Erro ao resolver proposta.");
    } finally {
      setResolvendo(null);
    }
  }

  return (
    <div className="space-y-3">
      <div className="afj-card p-0 overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-afj-cream-dark gap-3 flex-wrap">
          <h2 className="font-semibold text-afj-black text-sm flex items-center gap-2">
            <Sparkles size={15} className="text-afj-gold" /> Agentes de IA propostos
          </h2>
          <div className="flex items-center gap-2 flex-wrap">
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="border border-afj-cream-dark rounded-sm px-2 py-1.5 text-xs bg-white focus:outline-none focus:border-afj-gold"
            >
              {STATUS_FILTROS.map((f) => (
                <option key={f.value} value={f.value}>{f.label}</option>
              ))}
            </select>
            <button
              onClick={carregar}
              disabled={carregando}
              className="text-afj-black/40 hover:text-afj-black p-1 disabled:opacity-50"
              aria-label="Recarregar"
            >
              <RefreshCw size={14} className={carregando ? "animate-spin" : ""} />
            </button>
          </div>
        </div>

        {agentes === null ? (
          <p className="p-6 text-center text-sm text-afj-black/40">Carregando…</p>
        ) : agentes.length === 0 ? (
          <p className="p-6 text-center text-sm text-afj-black/40">
            Nenhum agente {status === "PENDENTE" ? "pendente de aprovação" : status === "APROVADO" ? "aprovado" : "rejeitado"} no momento.
          </p>
        ) : (
          <div className="divide-y divide-afj-cream-dark">
            {agentes.map((a) => {
              const aberto = expandido === a.id;
              return (
                <div key={a.id} className="px-4 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <button
                      onClick={() => setExpandido(aberto ? null : a.id)}
                      className="flex-1 text-left flex items-start gap-2"
                    >
                      {aberto ? <ChevronUp size={14} className="mt-0.5 text-afj-black/40 flex-shrink-0" /> : <ChevronDown size={14} className="mt-0.5 text-afj-black/40 flex-shrink-0" />}
                      <div>
                        <p className="font-medium text-sm text-afj-black">{a.name}</p>
                        <p className="text-xs text-afj-black/50 mt-0.5">{a.description}</p>
                      </div>
                    </button>
                    {status === "PENDENTE" && (
                      <div className="flex gap-1.5 flex-shrink-0">
                        <button
                          onClick={() => resolver(a.id, true)}
                          disabled={resolvendo === a.id}
                          className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-sm bg-green-50 text-green-700 hover:bg-green-100 disabled:opacity-40"
                        >
                          <Check size={12} /> Aprovar
                        </button>
                        <button
                          onClick={() => resolver(a.id, false)}
                          disabled={resolvendo === a.id}
                          className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-sm bg-red-50 text-red-700 hover:bg-red-100 disabled:opacity-40"
                        >
                          <X size={12} /> Rejeitar
                        </button>
                      </div>
                    )}
                  </div>
                  {aberto && (
                    <div className="mt-2.5 ml-6 space-y-2 text-xs">
                      <div>
                        <p className="text-afj-black/40 mb-1">Prompt de sistema:</p>
                        <pre className="whitespace-pre-wrap font-mono bg-afj-cream/50 rounded-sm p-2 text-afj-black/70">{a.system_prompt}</pre>
                      </div>
                      {a.rag_collections && a.rag_collections.length > 0 && (
                        <p className="text-afj-black/50">
                          Bases de conhecimento: {a.rag_collections.join(", ")}
                        </p>
                      )}
                      <p className="text-afj-black/40">
                        Teto de custo por execução: US$ {a.max_cost_usd_per_run.toFixed(2)} · Proposto em {new Date(a.created_at).toLocaleString("pt-BR")}
                      </p>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
