"use client";
import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Loader2, Sparkles, RefreshCw } from "lucide-react";

interface Msg { role: "user" | "assistant"; content: string }

export function BrainAssistant() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  // Envia a mensagem e consome o stream SSE (data: {delta}|{done}|{error}).
  const enviar = useCallback(async (texto: string) => {
    const pergunta = texto.trim();
    if (!pergunta || streaming) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: pergunta }, { role: "assistant", content: "" }]);
    setStreaming(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/system/brain/assistant", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ message: pergunta, conversation_id: conversationId }),
      });
      if (!res.ok || !res.body) {
        setMessages((m) => { const n = [...m]; n[n.length - 1] = { role: "assistant", content: `Erro (HTTP ${res.status}).` }; return n; });
        return;
      }
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const linhas = buf.split("\n\n");
        buf = linhas.pop() || "";
        for (const linha of linhas) {
          const t = linha.trim();
          if (!t.startsWith("data:")) continue;
          try {
            const ev = JSON.parse(t.slice(5).trim());
            if (ev.delta) {
              setMessages((m) => { const n = [...m]; n[n.length - 1] = { role: "assistant", content: n[n.length - 1].content + ev.delta }; return n; });
            } else if (ev.error) {
              setMessages((m) => { const n = [...m]; n[n.length - 1] = { role: "assistant", content: `Erro: ${ev.error}` }; return n; });
            } else if (ev.done && ev.conversation_id) {
              setConversationId(ev.conversation_id);
            }
          } catch { /* linha parcial */ }
        }
      }
    } catch {
      setMessages((m) => { const n = [...m]; n[n.length - 1] = { role: "assistant", content: "Falha de conexão." }; return n; });
    } finally {
      setStreaming(false);
    }
  }, [streaming, conversationId]);

  return (
    <div className="afj-card p-0 flex flex-col" style={{ height: 460 }}>
      <div className="flex items-center justify-between px-4 py-3 border-b border-afj-cream-dark">
        <h2 className="font-semibold text-afj-black text-sm flex items-center gap-2">
          <Sparkles size={15} className="text-afj-gold" /> Assistente do Cérebro
        </h2>
        <button
          onClick={() => { setMessages([]); setConversationId(null); }}
          className="text-afj-black/40 hover:text-afj-black p-1" title="Nova conversa" aria-label="Nova conversa">
          <RefreshCw size={14} />
        </button>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.length === 0 && (
          <div className="text-center text-afj-black/40 text-sm py-8">
            <Sparkles size={24} className="mx-auto mb-2 text-afj-gold/40" />
            Pergunte sobre módulos, integrações, saúde da infraestrutura ou como algo funciona no sistema.
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[85%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap ${
              m.role === "user" ? "bg-afj-gold/15 text-afj-black" : "bg-afj-cream/70 text-afj-black/85"}`}>
              {m.content || (streaming && i === messages.length - 1 ? <Loader2 size={14} className="animate-spin text-afj-gold" /> : "")}
            </div>
          </div>
        ))}
      </div>

      <form onSubmit={(e) => { e.preventDefault(); enviar(input); }}
        className="flex items-center gap-2 px-3 py-3 border-t border-afj-cream-dark">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Pergunte ao assistente do sistema..."
          disabled={streaming}
          className="flex-1 text-sm border border-afj-cream-dark rounded-sm px-3 py-2 focus:outline-none focus:border-afj-gold disabled:opacity-60"
        />
        <button type="submit" disabled={streaming || !input.trim()}
          className="btn-afj-primary rounded-sm p-2 disabled:opacity-50" aria-label="Enviar">
          {streaming ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
        </button>
      </form>
    </div>
  );
}
