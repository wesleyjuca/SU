"use client";
import { useState } from "react";
import { X, Loader2, Send } from "lucide-react";
import { api } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";

interface ProposeCustomAgentModalProps {
  onClose: () => void;
  onProposed: () => void;
}

// Mesma lista de VALID_COLLECTIONS do backend (app/api/v1/rag.py) — hardcoded
// aqui como já é o padrão do array AGENTS nesta mesma página.
const RAG_COLLECTIONS = [
  { value: "jurisprudencia", label: "Jurisprudência" },
  { value: "legislacao", label: "Legislação" },
  { value: "doutrina", label: "Doutrina" },
  { value: "doutrina_privada", label: "Doutrina (privada)" },
  { value: "peticoes_afj", label: "Petições AFJ" },
  { value: "memorias_afj", label: "Memórias AFJ" },
  { value: "documentos_clientes", label: "Docs. Clientes" },
];

export function ProposeCustomAgentModal({ onClose, onProposed }: ProposeCustomAgentModalProps) {
  const toast = useToast();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [colecoes, setColecoes] = useState<string[]>([]);
  const [enviando, setEnviando] = useState(false);

  function toggleColecao(value: string) {
    setColecoes((prev) => (prev.includes(value) ? prev.filter((c) => c !== value) : [...prev, value]));
  }

  async function enviar() {
    if (!name.trim() || !description.trim() || !systemPrompt.trim()) return;
    setEnviando(true);
    try {
      await api.post("/custom-agents", {
        name: name.trim(),
        description: description.trim(),
        system_prompt: systemPrompt.trim(),
        rag_collections: colecoes.length > 0 ? colecoes : null,
      });
      toast.success("Agente proposto. Aguardando aprovação do SUPERADMIN.");
      onProposed();
      onClose();
    } catch (err: any) {
      toast.error(err?.message || "Erro ao propor agente.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-afj-navy/80 z-50 flex items-center justify-center p-4 backdrop-blur-sm">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b border-afj-cream-dark">
          <h2 className="font-display text-lg font-semibold text-afj-black">Propor Agente de IA</h2>
          <button onClick={onClose} className="text-afj-black/40 hover:text-afj-black">
            <X size={18} />
          </button>
        </div>

        <div className="p-5 space-y-3">
          <p className="text-xs text-afj-black/50">
            Fica pendente até um SUPERADMIN aprovar. Depois de aprovado, fica disponível pra todo o escritório.
          </p>

          <div>
            <label className="text-xs text-afj-black/60 block mb-1">Nome</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ex: Analisador de Contratos de Aluguel"
              className="w-full px-3 py-2 text-sm border border-afj-cream-dark rounded-sm focus:outline-none focus:border-afj-gold"
            />
          </div>

          <div>
            <label className="text-xs text-afj-black/60 block mb-1">Descrição</label>
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="O que esse agente faz"
              className="w-full px-3 py-2 text-sm border border-afj-cream-dark rounded-sm focus:outline-none focus:border-afj-gold"
            />
          </div>

          <div>
            <label className="text-xs text-afj-black/60 block mb-1">Prompt de sistema</label>
            <textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              placeholder="Instruções fixas que definem o comportamento do agente..."
              rows={6}
              className="w-full px-3 py-2.5 text-sm border border-afj-cream-dark rounded-sm focus:outline-none focus:border-afj-gold font-mono"
            />
          </div>

          <div>
            <label className="text-xs text-afj-black/60 block mb-1.5">
              Bases de conhecimento (opcional — o agente busca contexto nelas antes de responder)
            </label>
            <div className="flex flex-wrap gap-2">
              {RAG_COLLECTIONS.map((c) => (
                <button
                  key={c.value}
                  type="button"
                  onClick={() => toggleColecao(c.value)}
                  className={`text-xs px-3 py-1.5 rounded-sm border transition-colors ${
                    colecoes.includes(c.value)
                      ? "border-afj-gold bg-afj-gold/5 text-afj-gold font-medium"
                      : "border-afj-cream-dark text-afj-black/50 hover:border-afj-gold/50"
                  }`}
                >
                  {c.label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex justify-end pt-2">
            <button
              onClick={enviar}
              disabled={enviando || !name.trim() || !description.trim() || !systemPrompt.trim()}
              className="btn-afj-primary rounded-sm flex items-center gap-2 disabled:opacity-40"
            >
              {enviando ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />}
              {enviando ? "Enviando..." : "Propor"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
