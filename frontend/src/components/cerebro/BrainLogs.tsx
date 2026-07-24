"use client";
import { useState, useEffect, useCallback } from "react";
import { ScrollText, RefreshCw } from "lucide-react";
import { fetchBrain, type LogEvento } from "./types";

interface LogsResp { ok: boolean; logs: LogEvento[] }

const NIVEIS = [
  { key: "", label: "Todos" },
  { key: "info", label: "Info+" },
  { key: "warning", label: "Aviso+" },
  { key: "error", label: "Erro" },
];

const COR_NIVEL: Record<string, string> = {
  debug: "text-afj-black/40", info: "text-afj-black/70",
  warning: "text-amber-600", warn: "text-amber-600",
  error: "text-red-600", critical: "text-red-700", exception: "text-red-700",
};

export function BrainLogs() {
  const [logs, setLogs] = useState<LogEvento[] | null>(null);
  const [nivel, setNivel] = useState("");
  const [auto, setAuto] = useState(true);

  const carregar = useCallback(async () => {
    const r = await fetchBrain<LogsResp>(`logs?limit=300${nivel ? `&level=${nivel}` : ""}`);
    setLogs(r?.logs ?? []);
  }, [nivel]);

  useEffect(() => { carregar(); }, [carregar]);
  useEffect(() => {
    if (!auto) return;
    const i = setInterval(carregar, 5000);
    return () => clearInterval(i);
  }, [auto, carregar]);

  return (
    <div className="afj-card p-0 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-afj-cream-dark flex-wrap gap-2">
        <h2 className="font-semibold text-afj-black text-sm flex items-center gap-2">
          <ScrollText size={15} className="text-afj-gold" /> Logs em tempo real
        </h2>
        <div className="flex items-center gap-1.5">
          <div className="flex rounded-sm border border-afj-cream-dark overflow-hidden">
            {NIVEIS.map((n) => (
              <button key={n.key} onClick={() => setNivel(n.key)}
                className={`text-[11px] px-2 py-1 ${nivel === n.key ? "bg-afj-gold/15 text-afj-gold font-semibold" : "text-afj-black/50 hover:bg-afj-cream/50"}`}>
                {n.label}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-1 text-[11px] text-afj-black/55 cursor-pointer">
            <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} className="accent-afj-gold" /> auto
          </label>
          <button onClick={carregar} className="text-afj-black/40 hover:text-afj-black p-1" aria-label="Recarregar">
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {logs === null ? (
        <p className="p-6 text-center text-sm text-afj-black/40">Carregando…</p>
      ) : logs.length === 0 ? (
        <p className="p-6 text-center text-sm text-afj-black/40">Nenhum log no buffer (nível selecionado).</p>
      ) : (
        <div className="max-h-[520px] overflow-y-auto font-mono text-[11px] leading-relaxed divide-y divide-afj-cream/60">
          {logs.map((l, i) => (
            <div key={i} className="px-4 py-1.5 flex gap-2 hover:bg-afj-cream/30">
              <span className="text-afj-black/35 whitespace-nowrap">{l.ts?.slice(11, 19) || "--:--:--"}</span>
              <span className={`uppercase font-semibold w-12 flex-shrink-0 ${COR_NIVEL[l.level] || "text-afj-black/50"}`}>{l.level}</span>
              <span className="text-afj-black/80 break-all">
                {l.event}
                {l.extra && Object.keys(l.extra).length > 0 && (
                  <span className="text-afj-black/35"> {Object.entries(l.extra).map(([k, v]) => `${k}=${v}`).join(" ")}</span>
                )}
              </span>
            </div>
          ))}
        </div>
      )}
      <p className="px-4 py-2 text-[11px] text-afj-black/35 border-t border-afj-cream-dark">
        Buffer em memória (últimos ~500 eventos deste processo). Não persistido.
      </p>
    </div>
  );
}
