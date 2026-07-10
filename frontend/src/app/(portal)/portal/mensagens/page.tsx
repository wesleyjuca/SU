"use client";
import { useState, useEffect, useRef, useCallback } from "react";
import { MessageSquare, Send, Loader2, RefreshCw } from "lucide-react";
import { portalApi } from "@/lib/portalApi";
import { useToast } from "@/components/ui/Toast";

interface Mensagem {
  id: string;
  descricao: string;
  autor: "cliente" | "escritorio";
  created_at: string;
}

export default function PortalMensagensPage() {
  const toast = useToast();
  const [mensagens, setMensagens] = useState<Mensagem[]>([]);
  const [loading, setLoading] = useState(true);
  const [texto, setTexto] = useState("");
  const [sending, setSending] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async (scroll = false) => {
    try {
      const data = await portalApi.get<Mensagem[]>("/portal/messages");
      setMensagens(data);
      if (scroll) setTimeout(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
    } catch {
      toast.error("Erro ao carregar mensagens.");
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { load(true); }, [load]);

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
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-900 flex items-center gap-2">
            <MessageSquare size={20} className="text-blue-600" /> Mensagens
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Fale com o escritório — sua mensagem chega diretamente ao advogado responsável.
          </p>
        </div>
        <button onClick={() => load(true)} className="p-2 rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-500"
          title="Atualizar" aria-label="Atualizar">
          <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {/* Thread */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 min-h-[320px] max-h-[55vh] overflow-y-auto space-y-3">
        {loading ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-12 bg-gray-100 rounded-lg animate-pulse" />)}
          </div>
        ) : mensagens.length === 0 ? (
          <div className="py-14 text-center">
            <MessageSquare size={30} className="mx-auto text-gray-300 mb-2" />
            <p className="text-sm text-gray-500">Nenhuma mensagem ainda.</p>
            <p className="text-xs text-gray-400 mt-1">Envie a primeira mensagem abaixo — o escritório será notificado.</p>
          </div>
        ) : (
          mensagens.map((m) => (
            <div key={m.id} className={`flex ${m.autor === "cliente" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                m.autor === "cliente"
                  ? "bg-blue-600 text-white rounded-br-sm"
                  : "bg-gray-100 text-gray-800 rounded-bl-sm"
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

      {/* Form */}
      <form onSubmit={enviar} className="flex gap-2">
        <input
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          placeholder="Escreva sua mensagem ao escritório..."
          className="flex-1 border border-gray-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-blue-400 bg-white"
        />
        <button type="submit" disabled={sending || !texto.trim()}
          className="bg-blue-600 hover:bg-blue-700 text-white rounded-xl px-5 py-3 text-sm font-medium flex items-center gap-2 disabled:opacity-50 transition-colors">
          {sending ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
          Enviar
        </button>
      </form>
    </div>
  );
}
