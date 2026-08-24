"use client";
import { useState, useEffect, useRef, useCallback } from "react";
import { MessageSquare, Send, Loader2, RefreshCw, ChevronDown, ChevronRight } from "lucide-react";
import { portalApi } from "@/lib/portalApi";
import { useToast } from "@/components/ui/Toast";

interface Mensagem {
  id: string;
  descricao: string;
  autor: "cliente" | "escritorio";
  created_at: string;
}

/** Fase 233 — seção colapsável do dashboard único do portal (antes era
 * a rota `/portal/mensagens`). Fechada por padrão. */
export function MensagensSection() {
  const toast = useToast();
  const [aberto, setAberto] = useState(false);
  const [mensagens, setMensagens] = useState<Mensagem[]>([]);
  const [loading, setLoading] = useState(false);
  const [carregado, setCarregado] = useState(false);
  const [texto, setTexto] = useState("");
  const [sending, setSending] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async (scroll = false) => {
    setLoading(true);
    try {
      const data = await portalApi.get<Mensagem[]>("/portal/messages");
      setMensagens(data);
      setCarregado(true);
      if (scroll) setTimeout(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
    } catch {
      toast.error("Erro ao carregar mensagens.");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    if (aberto && !carregado) load(true);
  }, [aberto, carregado, load]);

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    if (!texto.trim()) return;
    setSending(true);
    try {
      await portalApi.post("/portal/messages", { descricao: texto.trim() });
      setTexto("");
      await load(true);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Erro ao enviar.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <button
        onClick={() => setAberto((v) => !v)}
        className="w-full flex items-center justify-between gap-3 p-4 hover:bg-gray-50/60 transition-colors"
      >
        <div className="flex items-center gap-2.5">
          <MessageSquare size={16} className="text-blue-600" />
          <h2 className="text-sm font-semibold text-gray-800">Mensagens</h2>
          {carregado && <span className="text-xs text-gray-400">({mensagens.length})</span>}
        </div>
        {aberto ? <ChevronDown size={16} className="text-gray-400" /> : <ChevronRight size={16} className="text-gray-400" />}
      </button>

      {aberto && (
        <div className="border-t border-gray-100 p-4 space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-xs text-gray-500">Fale com o escritório — sua mensagem chega direto ao advogado responsável.</p>
            <button onClick={() => load(true)} className="p-1.5 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-500 flex-shrink-0"
              title="Atualizar" aria-label="Atualizar">
              <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
            </button>
          </div>

          <div className="bg-gray-50/50 rounded-lg border border-gray-100 p-4 min-h-[240px] max-h-[45vh] overflow-y-auto space-y-3">
            {loading && !carregado ? (
              <div className="space-y-3">
                {Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-12 bg-gray-100 rounded-lg animate-pulse" />)}
              </div>
            ) : mensagens.length === 0 ? (
              <div className="py-10 text-center">
                <MessageSquare size={26} className="mx-auto text-gray-300 mb-2" />
                <p className="text-sm text-gray-500">Nenhuma mensagem ainda.</p>
                <p className="text-xs text-gray-400 mt-1">Envie a primeira mensagem abaixo — o escritório será notificado.</p>
              </div>
            ) : (
              mensagens.map((m) => (
                <div key={m.id} className={`flex ${m.autor === "cliente" ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                    m.autor === "cliente" ? "bg-blue-600 text-white rounded-br-sm" : "bg-white border border-gray-100 text-gray-800 rounded-bl-sm"
                  }`}>
                    {m.autor === "escritorio" && (
                      <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 mb-0.5">Escritório</p>
                    )}
                    <p className="whitespace-pre-wrap">{m.descricao}</p>
                    <p className={`text-[10px] mt-1 ${m.autor === "cliente" ? "text-blue-200" : "text-gray-400"}`}>
                      {new Date(m.created_at).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}
                    </p>
                  </div>
                </div>
              ))
            )}
            <div ref={endRef} />
          </div>

          <form onSubmit={enviar} className="flex gap-2">
            <input
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              placeholder="Escreva sua mensagem ao escritório..."
              className="flex-1 border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-blue-400 bg-white"
            />
            <button type="submit" disabled={sending || !texto.trim()}
              className="bg-blue-600 hover:bg-blue-700 text-white rounded-xl px-4 py-2.5 text-sm font-medium flex items-center gap-2 disabled:opacity-50 transition-colors">
              {sending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
              Enviar
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
