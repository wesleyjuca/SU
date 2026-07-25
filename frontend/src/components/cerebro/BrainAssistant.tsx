"use client";
import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Loader2, Sparkles, RefreshCw, Mic, MicOff, Volume2, Database } from "lucide-react";
import { useVoice } from "@/hooks/useVoice";
import { useToast } from "@/components/ui/Toast";

interface Msg { role: "user" | "assistant"; content: string }

export function BrainAssistant() {
  const toast = useToast();
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [reindexing, setReindexing] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  // Ref p/ evitar reentrância no envio (o hook de voz chama enviar via callback).
  const streamingRef = useRef(false);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  // Envia a mensagem e consome o stream SSE (data: {delta}|{done}|{error}).
  // Retorna o texto final do assistente (para leitura por voz).
  const enviar = useCallback(async (texto: string): Promise<string> => {
    const pergunta = texto.trim();
    if (!pergunta || streamingRef.current) return "";
    setInput("");
    setMessages((m) => [...m, { role: "user", content: pergunta }, { role: "assistant", content: "" }]);
    streamingRef.current = true;
    setStreaming(true);
    let finalTexto = "";
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/system/brain/assistant", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ message: pergunta, conversation_id: conversationId }),
      });
      if (!res.ok || !res.body) {
        const msg = `Erro (HTTP ${res.status}).`;
        setMessages((m) => { const n = [...m]; n[n.length - 1] = { role: "assistant", content: msg }; return n; });
        return "";
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
              finalTexto += ev.delta;
              setMessages((m) => { const n = [...m]; n[n.length - 1] = { role: "assistant", content: n[n.length - 1].content + ev.delta }; return n; });
            } else if (ev.error) {
              finalTexto = "";
              setMessages((m) => { const n = [...m]; n[n.length - 1] = { role: "assistant", content: `Erro: ${ev.error}` }; return n; });
            } else if (ev.done && ev.conversation_id) {
              setConversationId(ev.conversation_id);
            }
          } catch { /* linha parcial */ }
        }
      }
    } catch {
      setMessages((m) => { const n = [...m]; n[n.length - 1] = { role: "assistant", content: "Falha de conexão." }; return n; });
      return "";
    } finally {
      streamingRef.current = false;
      setStreaming(false);
    }
    return finalTexto;
  }, [conversationId]);

  // ─── Conversa por voz (F6): STT dispara enviar, TTS lê a resposta ────────────
  const voice = useVoice({
    onFinal: (texto) => {
      // Fala do usuário concluída → envia e, ao terminar, lê a resposta em voz.
      enviar(texto).then((resposta) => {
        if (resposta && voiceActiveRef.current) voice.speak(resposta);
      });
    },
  });
  // Espelha o estado ativo p/ uso dentro do .then acima sem stale closure.
  const voiceActiveRef = useRef(false);
  useEffect(() => { voiceActiveRef.current = voice.active; }, [voice.active]);

  const reindexar = useCallback(async () => {
    setReindexing(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/system/brain/assistant/reindex", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const d = await res.json().catch(() => ({}));
      if (res.ok && d.ok) toast.success(`Documentação reindexada (${d.arquivos_indexados ?? 0} arquivo(s)).`);
      else toast.error(d.motivo || d.detail || "Erro ao reindexar documentação.");
    } catch {
      toast.error("Erro de conexão ao reindexar.");
    } finally {
      setReindexing(false);
    }
  }, [toast]);

  const enviarTexto = useCallback(() => {
    const txt = input;
    enviar(txt).then((resposta) => {
      // Se o modo voz estiver ligado, também lê respostas digitadas.
      if (resposta && voiceActiveRef.current) voice.speak(resposta);
    });
  }, [input, enviar, voice]);

  return (
    <div className="afj-card p-0 flex flex-col" style={{ height: 460 }}>
      <div className="flex items-center justify-between px-4 py-3 border-b border-afj-cream-dark">
        <h2 className="font-semibold text-afj-black text-sm flex items-center gap-2">
          <Sparkles size={15} className="text-afj-gold" /> Assistente do Cérebro
          {voice.speaking && (
            <span className="flex items-center gap-1 text-[11px] font-normal text-afj-gold">
              <Volume2 size={12} className="animate-pulse" /> falando…
            </span>
          )}
        </h2>
        <div className="flex items-center gap-1">
          {voice.supported && (
            <button
              onClick={voice.toggle}
              className={`p-1.5 rounded-sm transition-colors ${
                voice.active
                  ? "bg-afj-gold/15 text-afj-gold"
                  : "text-afj-black/40 hover:text-afj-black"
              }`}
              title={voice.active ? "Desligar conversa por voz" : "Conversar por voz"}
              aria-label={voice.active ? "Desligar conversa por voz" : "Conversar por voz"}
              aria-pressed={voice.active}
            >
              {voice.active ? <Mic size={15} className={voice.listening ? "animate-pulse" : ""} /> : <MicOff size={15} />}
            </button>
          )}
          <button
            onClick={reindexar}
            disabled={reindexing}
            className="text-afj-black/40 hover:text-afj-black p-1 disabled:opacity-40"
            title="Reindexar documentação do sistema" aria-label="Reindexar documentação do sistema">
            <Database size={14} className={reindexing ? "animate-pulse" : ""} />
          </button>
          <button
            onClick={() => { voice.stop(); setMessages([]); setConversationId(null); }}
            className="text-afj-black/40 hover:text-afj-black p-1" title="Nova conversa" aria-label="Nova conversa">
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.length === 0 && (
          <div className="text-center text-afj-black/40 text-sm py-8">
            <Sparkles size={24} className="mx-auto mb-2 text-afj-gold/40" />
            Pergunte sobre módulos, integrações, saúde da infraestrutura ou como algo funciona no sistema.
            {voice.supported && (
              <p className="text-[11px] mt-2 text-afj-black/30">
                Toque no microfone para conversar por voz (contínuo, com interrupção).
              </p>
            )}
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
        {/* Transcrição parcial da fala do usuário (interim) */}
        {voice.interim && (
          <div className="flex justify-end">
            <div className="max-w-[85%] rounded-lg px-3 py-2 text-sm italic text-afj-black/45 bg-afj-gold/5 border border-dashed border-afj-gold/30">
              {voice.interim}…
            </div>
          </div>
        )}
      </div>

      {voice.active && (
        <div className="px-4 py-1.5 border-t border-afj-cream-dark bg-afj-gold/5 text-[11px] text-afj-gold flex items-center gap-1.5">
          <Mic size={11} className={voice.listening ? "animate-pulse" : ""} />
          {voice.speaking ? "Assistente falando — fale para interromper" : voice.listening ? "Ouvindo… pode falar" : "Modo voz ativo"}
        </div>
      )}

      <form onSubmit={(e) => { e.preventDefault(); enviarTexto(); }}
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
