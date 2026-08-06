"use client";
import { useEffect, useState } from "react";
import { X, Loader2, Save, RotateCcw, History, Paperclip, Trash2, Upload } from "lucide-react";
import { api } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";

interface PromptSlot {
  slot: string;
  label: string;
}

interface PromptData {
  agent_name: string;
  slot: string;
  prompt_text: string | null;
  versao: number;
  updated_by: string | null;
  updated_at: string | null;
}

interface PromptVersion {
  id: string;
  versao: number;
  prompt_text: string | null;
  changed_by: string | null;
  change_summary: string | null;
  created_at: string;
}

interface Attachment {
  id: string;
  filename: string;
  content_type: string | null;
  size_bytes: number | null;
  has_extracted_text: boolean;
  uploaded_by: string | null;
  created_at: string;
}

interface AgentDetailDrawerProps {
  agentName: string;
  onClose: () => void;
}

export function AgentDetailDrawer({ agentName, onClose }: AgentDetailDrawerProps) {
  const toast = useToast();
  const [slots, setSlots] = useState<PromptSlot[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeSlot, setActiveSlot] = useState<string | null>(null);
  const [prompt, setPrompt] = useState<PromptData | null>(null);
  const [texto, setTexto] = useState("");
  const [changeSummary, setChangeSummary] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [versions, setVersions] = useState<PromptVersion[] | null>(null);
  const [mostrarHistorico, setMostrarHistorico] = useState(false);
  const [attachments, setAttachments] = useState<Attachment[] | null>(null);
  const [enviandoAnexo, setEnviandoAnexo] = useState(false);

  useEffect(() => {
    api
      .get<{ agent_name: string; slots: PromptSlot[] }>(`/agents/${agentName}/prompt-slots`)
      .then((data) => {
        setSlots(data.slots);
        if (data.slots.length > 0) setActiveSlot(data.slots[0].slot);
      })
      .catch(() => setSlots([]))
      .finally(() => setLoading(false));
    api
      .get<Attachment[]>(`/agents/${agentName}/attachments`)
      .then(setAttachments)
      .catch(() => setAttachments([]));
  }, [agentName]);

  useEffect(() => {
    if (!activeSlot) return;
    setMostrarHistorico(false);
    setVersions(null);
    api
      .get<PromptData>(`/agents/${agentName}/prompt?slot=${activeSlot}`)
      .then((data) => {
        setPrompt(data);
        setTexto(data.prompt_text ?? "");
        setChangeSummary("");
      })
      .catch(() => toast.error("Erro ao carregar prompt."));
  }, [agentName, activeSlot]);

  async function salvar(restaurarPadrao = false) {
    if (!activeSlot) return;
    setSalvando(true);
    try {
      const data = await api.put<PromptData>(`/agents/${agentName}/prompt?slot=${activeSlot}`, {
        prompt_text: restaurarPadrao ? null : texto,
        change_summary: changeSummary || null,
      });
      setPrompt(data);
      setTexto(data.prompt_text ?? "");
      setChangeSummary("");
      toast.success(restaurarPadrao ? "Prompt restaurado ao padrão." : "Prompt salvo.");
    } catch {
      toast.error("Erro ao salvar prompt.");
    } finally {
      setSalvando(false);
    }
  }

  async function carregarHistorico() {
    if (!activeSlot) return;
    setMostrarHistorico((v) => !v);
    if (versions) return;
    try {
      const data = await api.get<PromptVersion[]>(`/agents/${agentName}/prompt/versions?slot=${activeSlot}`);
      setVersions(data);
    } catch {
      toast.error("Erro ao carregar histórico.");
    }
  }

  async function uploadAnexo(file: File) {
    setEnviandoAnexo(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`/api/v1/agents/${agentName}/attachments`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Erro ao enviar anexo");
      }
      const novo = await res.json();
      setAttachments((prev) => [novo, ...(prev ?? [])]);
      toast.success("Anexo adicionado.");
    } catch (err: any) {
      toast.error(err?.message || "Erro ao enviar anexo.");
    } finally {
      setEnviandoAnexo(false);
    }
  }

  async function excluirAnexo(id: string) {
    try {
      await api.delete(`/agents/${agentName}/attachments/${id}`);
      setAttachments((prev) => (prev ?? []).filter((a) => a.id !== id));
      toast.success("Anexo removido.");
    } catch {
      toast.error("Erro ao remover anexo.");
    }
  }

  return (
    <div className="fixed inset-0 bg-afj-navy/80 z-50 flex items-center justify-center p-4 backdrop-blur-sm">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b border-afj-cream-dark">
          <h2 className="font-display text-lg font-semibold text-afj-black">{agentName}</h2>
          <button onClick={onClose} className="text-afj-black/40 hover:text-afj-black">
            <X size={18} />
          </button>
        </div>

        <div className="p-5 space-y-5">
          {loading && (
            <div className="flex items-center gap-2 text-sm text-afj-black/50">
              <Loader2 size={14} className="animate-spin" /> Carregando...
            </div>
          )}

          {!loading && slots && slots.length === 0 && (
            <p className="text-sm text-afj-black/50">
              Este agente não usa IA generativa — lógica determinística.
            </p>
          )}

          {!loading && slots && slots.length > 0 && (
            <>
              {slots.length > 1 && (
                <div className="flex gap-2">
                  {slots.map((s) => (
                    <button
                      key={s.slot}
                      onClick={() => setActiveSlot(s.slot)}
                      className={`text-xs px-3 py-1.5 rounded-sm border ${
                        activeSlot === s.slot
                          ? "border-afj-gold bg-afj-gold/5 text-afj-gold font-medium"
                          : "border-afj-cream-dark text-afj-black/50"
                      }`}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
              )}
              {slots.length === 1 && <p className="text-xs text-afj-black/50">{slots[0].label}</p>}

              {prompt && (
                <div className="space-y-2">
                  <textarea
                    value={texto}
                    onChange={(e) => setTexto(e.target.value)}
                    placeholder={prompt.prompt_text === null ? "Usando o prompt padrão do sistema..." : ""}
                    rows={10}
                    className="w-full px-3 py-2.5 text-sm border border-afj-cream-dark rounded-sm focus:outline-none focus:border-afj-gold font-mono"
                  />
                  <input
                    value={changeSummary}
                    onChange={(e) => setChangeSummary(e.target.value)}
                    placeholder="Resumo da mudança (opcional)"
                    className="w-full px-3 py-1.5 text-xs border border-afj-cream-dark rounded-sm focus:outline-none focus:border-afj-gold"
                  />
                  <div className="flex items-center justify-between">
                    <button
                      onClick={carregarHistorico}
                      className="text-xs text-afj-black/50 hover:text-afj-gold flex items-center gap-1"
                    >
                      <History size={12} /> Histórico (v{prompt.versao})
                    </button>
                    <div className="flex gap-2">
                      <button
                        onClick={() => salvar(true)}
                        disabled={salvando}
                        className="btn-afj-outline rounded-sm text-xs flex items-center gap-1.5 disabled:opacity-40"
                      >
                        <RotateCcw size={12} /> Restaurar padrão
                      </button>
                      <button
                        onClick={() => salvar(false)}
                        disabled={salvando}
                        className="btn-afj-primary rounded-sm text-xs flex items-center gap-1.5 disabled:opacity-40"
                      >
                        {salvando ? <Loader2 size={12} className="animate-spin" /> : <Save size={12} />} Salvar
                      </button>
                    </div>
                  </div>

                  {mostrarHistorico && (
                    <div className="border-t border-afj-cream-dark pt-2 space-y-1.5 max-h-48 overflow-y-auto">
                      {versions === null && <p className="text-xs text-afj-black/40">Carregando...</p>}
                      {versions && versions.length === 0 && (
                        <p className="text-xs text-afj-black/40">Sem edições anteriores.</p>
                      )}
                      {versions?.map((v) => (
                        <div key={v.id} className="text-xs text-afj-black/50 flex justify-between">
                          <span>
                            v{v.versao} — {v.change_summary || "sem resumo"}
                          </span>
                          <span>{new Date(v.created_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          <div className="border-t border-afj-cream-dark pt-4">
            <p className="text-xs font-medium text-afj-black/70 mb-2 flex items-center gap-1.5">
              <Paperclip size={12} /> Anexos de contexto
            </p>
            <p className="text-xs text-afj-black/40 mb-2">
              Texto extraído automaticamente só para arquivos de texto simples; PDFs/imagens ficam armazenados mas fora do contexto por enquanto.
            </p>
            <div className="space-y-1.5 mb-2">
              {(attachments ?? []).map((a) => (
                <div key={a.id} className="flex items-center justify-between text-xs px-2 py-1.5 bg-afj-cream/50 rounded-sm">
                  <span className="truncate">{a.filename}</span>
                  <button onClick={() => excluirAnexo(a.id)} className="text-afj-black/30 hover:text-red-500 flex-shrink-0">
                    <Trash2 size={12} />
                  </button>
                </div>
              ))}
              {attachments && attachments.length === 0 && (
                <p className="text-xs text-afj-black/40">Nenhum anexo.</p>
              )}
            </div>
            <label className="btn-afj-outline rounded-sm text-xs inline-flex items-center gap-1.5 cursor-pointer">
              {enviandoAnexo ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
              Anexar arquivo
              <input
                type="file"
                className="hidden"
                disabled={enviandoAnexo}
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) uploadAnexo(file);
                  e.target.value = "";
                }}
              />
            </label>
          </div>
        </div>
      </div>
    </div>
  );
}
