"use client";
import { useState, useEffect, useCallback } from "react";
import { Sparkles, RefreshCw, Check, X, ChevronDown, ChevronUp, Pencil, Loader2 } from "lucide-react";
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
  requires_human_approval: boolean;
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
  // Fase 193 — editar um agente já APROVADO (antes só dava pra recriar do zero).
  const [editandoId, setEditandoId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState({ description: "", system_prompt: "", rag_collections: "", max_cost_usd_per_run: "", requires_human_approval: false });
  const [salvandoEdicao, setSalvandoEdicao] = useState(false);

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

  function abrirEdicao(a: CustomAgentRow) {
    setEditandoId(a.id);
    setExpandido(a.id);
    setEditForm({
      description: a.description,
      system_prompt: a.system_prompt,
      rag_collections: (a.rag_collections || []).join(", "),
      max_cost_usd_per_run: String(a.max_cost_usd_per_run),
      requires_human_approval: a.requires_human_approval,
    });
  }

  async function salvarEdicao(id: string) {
    setSalvandoEdicao(true);
    try {
      const rag_collections = editForm.rag_collections.trim()
        ? editForm.rag_collections.split(",").map((s) => s.trim()).filter(Boolean)
        : [];
      const atualizado = await api.patch<CustomAgentRow>(`/custom-agents/${id}`, {
        description: editForm.description,
        system_prompt: editForm.system_prompt,
        rag_collections,
        max_cost_usd_per_run: Number(editForm.max_cost_usd_per_run) || 0,
        requires_human_approval: editForm.requires_human_approval,
      });
      toast.success("Agente atualizado.");
      setAgentes((prev) => (prev ?? []).map((a) => (a.id === id ? atualizado : a)));
      setEditandoId(null);
    } catch (err: any) {
      toast.error(err?.message || "Erro ao atualizar o agente.");
    } finally {
      setSalvandoEdicao(false);
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
                    {status === "APROVADO" && editandoId !== a.id && (
                      <button
                        onClick={() => abrirEdicao(a)}
                        className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-sm bg-afj-cream text-afj-black/70 hover:bg-afj-cream-dark flex-shrink-0"
                      >
                        <Pencil size={12} /> Editar
                      </button>
                    )}
                  </div>
                  {aberto && editandoId === a.id ? (
                    <div className="mt-2.5 ml-6 space-y-2.5 text-xs">
                      <div>
                        <label className="text-afj-black/40 mb-1 block">Descrição</label>
                        <input type="text" value={editForm.description}
                          onChange={(e) => setEditForm((f) => ({ ...f, description: e.target.value }))}
                          className="w-full border border-afj-cream-dark rounded-sm px-2.5 py-1.5 focus:outline-none focus:border-afj-gold" />
                      </div>
                      <div>
                        <label className="text-afj-black/40 mb-1 block">Prompt de sistema</label>
                        <textarea value={editForm.system_prompt} rows={8}
                          onChange={(e) => setEditForm((f) => ({ ...f, system_prompt: e.target.value }))}
                          className="w-full font-mono border border-afj-cream-dark rounded-sm px-2.5 py-1.5 focus:outline-none focus:border-afj-gold resize-none" />
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                        <div>
                          <label className="text-afj-black/40 mb-1 block">Bases de conhecimento (separadas por vírgula)</label>
                          <input type="text" value={editForm.rag_collections}
                            onChange={(e) => setEditForm((f) => ({ ...f, rag_collections: e.target.value }))}
                            className="w-full border border-afj-cream-dark rounded-sm px-2.5 py-1.5 focus:outline-none focus:border-afj-gold" />
                        </div>
                        <div>
                          <label className="text-afj-black/40 mb-1 block">Teto de custo por execução (US$)</label>
                          <input type="number" step="0.01" min="0" value={editForm.max_cost_usd_per_run}
                            onChange={(e) => setEditForm((f) => ({ ...f, max_cost_usd_per_run: e.target.value }))}
                            className="w-full border border-afj-cream-dark rounded-sm px-2.5 py-1.5 focus:outline-none focus:border-afj-gold" />
                        </div>
                      </div>
                      <label className="flex items-center gap-2 cursor-pointer select-none">
                        <input type="checkbox" checked={editForm.requires_human_approval}
                          onChange={(e) => setEditForm((f) => ({ ...f, requires_human_approval: e.target.checked }))}
                          className="accent-afj-gold w-3.5 h-3.5" />
                        <span className="text-afj-black/70">Exigir aprovação humana quando usado em uma chain</span>
                      </label>
                      <div className="flex gap-2">
                        <button onClick={() => salvarEdicao(a.id)} disabled={salvandoEdicao}
                          className="btn-afj-primary text-xs py-1.5 px-3 rounded-sm flex items-center gap-1.5 disabled:opacity-50">
                          {salvandoEdicao && <Loader2 size={12} className="animate-spin" />} Salvar alterações
                        </button>
                        <button onClick={() => setEditandoId(null)} disabled={salvandoEdicao}
                          className="btn-afj-outline text-xs py-1.5 px-3 rounded-sm">
                          Cancelar
                        </button>
                      </div>
                    </div>
                  ) : aberto && (
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
                        {a.requires_human_approval && " · Exige aprovação humana quando usado em uma chain"}
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
