"use client";
import { useState, useEffect, useCallback } from "react";
import { Scale, AlertTriangle, CheckSquare, DollarSign, Clock, LogOut, RefreshCw } from "lucide-react";
import { useThemeStore } from "@/store";

interface Metrics {
  processos_ativos: number;
  prazos_proximos_7d: number;
  aprovacoes_pendentes: number;
  custo_ia_mes: number;
}
interface Prazo {
  id: string;
  descricao: string;
  tipo: string | null;
  data_prazo: string | null;
  numero_cnj: string | null;
  tribunal: string | null;
}

const fmtData = (iso: string | null) => {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00");
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
};
const diasAte = (iso: string | null): number | null => {
  if (!iso) return null;
  const d = new Date(iso + "T00:00:00");
  if (isNaN(d.getTime())) return null;
  return Math.ceil((d.getTime() - Date.now()) / 86_400_000);
};

export default function TvPanelPage() {
  const { theme } = useThemeStore();
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [prazos, setPrazos] = useState<Prazo[]>([]);
  const [now, setNow] = useState<Date | null>(null);
  const [erro, setErro] = useState(false);

  const load = useCallback(async () => {
    const token = typeof window !== "undefined" ? localStorage.getItem("afj_access_token") : null;
    if (!token) { window.location.href = "/login"; return; }
    const headers = { Authorization: `Bearer ${token}` };
    try {
      const [m, a] = await Promise.allSettled([
        fetch("/api/v1/system/metrics", { headers }),
        fetch("/api/v1/processes/agenda?dias=15", { headers }),
      ]);
      if (m.status === "fulfilled" && m.value.status === 401) { window.location.href = "/login"; return; }
      if (m.status === "fulfilled" && m.value.ok) setMetrics(await m.value.json());
      if (a.status === "fulfilled" && a.value.ok) setPrazos((await a.value.json()).slice(0, 10));
      setErro(false);
    } catch {
      setErro(true);
    }
  }, []);

  // Auto-refresh dos dados a cada 60s; relógio a cada segundo.
  useEffect(() => {
    setNow(new Date());
    load();
    const dataTimer = setInterval(load, 60_000);
    const clockTimer = setInterval(() => setNow(new Date()), 1_000);
    return () => { clearInterval(dataTimer); clearInterval(clockTimer); };
  }, [load]);

  const KPIS = [
    { label: "Processos Ativos", value: metrics?.processos_ativos, icon: Scale, tone: "text-afj-gold" },
    { label: "Prazos (7 dias)", value: metrics?.prazos_proximos_7d, icon: AlertTriangle, tone: (metrics?.prazos_proximos_7d ?? 0) > 0 ? "text-amber-400" : "text-afj-cream" },
    { label: "Aprovações Pendentes", value: metrics?.aprovacoes_pendentes, icon: CheckSquare, tone: (metrics?.aprovacoes_pendentes ?? 0) > 0 ? "text-red-400" : "text-afj-cream" },
    { label: "Custo IA (mês)", value: metrics ? `$${metrics.custo_ia_mes.toFixed(2)}` : undefined, icon: DollarSign, tone: "text-afj-gold" },
  ];

  return (
    <div className="min-h-screen flex flex-col p-6 lg:p-10 gap-6 lg:gap-8">
      {/* Cabeçalho */}
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          {theme.logoUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={theme.logoUrl} alt={theme.appName} className="h-12 lg:h-16 w-auto object-contain" />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img src="/logo-afj-mark.png" alt="AFJ" className="h-12 lg:h-16 w-auto object-contain" />
          )}
          <div>
            <h1 className="font-display text-2xl lg:text-4xl font-bold">{theme.appName || "AFJ CORE"}</h1>
            <p className="text-afj-cream/50 text-sm lg:text-lg tracking-wide">Painel do Escritório</p>
          </div>
        </div>
        <div className="flex items-center gap-6">
          <div className="text-right">
            <p className="font-display text-3xl lg:text-5xl font-bold tabular-nums">
              {now ? now.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }) : "--:--"}
            </p>
            <p className="text-afj-cream/50 text-sm lg:text-lg capitalize">
              {now ? now.toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "long" }) : ""}
            </p>
          </div>
          <a href="/dashboard" className="text-afj-cream/30 hover:text-afj-cream transition-colors" title="Sair do modo TV" aria-label="Sair do modo TV">
            <LogOut size={22} />
          </a>
        </div>
      </header>

      {erro && (
        <div className="flex items-center gap-2 text-amber-400 text-sm lg:text-lg">
          <RefreshCw size={16} /> Sem conexão com o servidor — tentando novamente…
        </div>
      )}

      {/* KPIs gigantes */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-5 lg:gap-8">
        {KPIS.map((k) => {
          const Icon = k.icon;
          return (
            <div key={k.label} className="rounded-lg bg-white/5 border border-white/10 p-6 lg:p-8 flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <span className="text-afj-cream/50 text-sm lg:text-xl uppercase tracking-widest">{k.label}</span>
                <Icon className={k.tone} size={28} />
              </div>
              <span className={`font-display font-bold tabular-nums text-6xl lg:text-8xl ${k.tone}`}>
                {k.value ?? "—"}
              </span>
            </div>
          );
        })}
      </div>

      {/* Prazos próximos */}
      <div className="flex-1 rounded-lg bg-white/5 border border-white/10 p-6 lg:p-8 min-h-0">
        <div className="flex items-center gap-3 mb-4 lg:mb-6">
          <Clock className="text-afj-gold" size={26} />
          <h2 className="font-display text-xl lg:text-3xl font-semibold">Prazos próximos</h2>
        </div>
        {prazos.length === 0 ? (
          <p className="text-afj-cream/40 text-lg lg:text-2xl py-8 text-center">Nenhum prazo nos próximos 15 dias 🎉</p>
        ) : (
          <div className="space-y-3 lg:space-y-4">
            {prazos.map((p) => {
              const d = diasAte(p.data_prazo);
              const urgente = d !== null && d <= 3;
              const atencao = d !== null && d > 3 && d <= 7;
              return (
                <div key={p.id} className="flex items-center gap-4 lg:gap-6">
                  <div className={`flex flex-col items-center justify-center rounded-md px-3 lg:px-5 py-2 lg:py-3 min-w-[72px] lg:min-w-[110px] ${urgente ? "bg-red-500/20 text-red-300" : atencao ? "bg-amber-500/20 text-amber-300" : "bg-white/10 text-afj-cream"}`}>
                    <span className="font-display text-2xl lg:text-4xl font-bold tabular-nums leading-none">{fmtData(p.data_prazo)}</span>
                    <span className="text-[10px] lg:text-sm uppercase tracking-wide mt-1">
                      {d !== null ? (d <= 0 ? "hoje" : `${d} dia${d !== 1 ? "s" : ""}`) : ""}
                    </span>
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-lg lg:text-2xl font-medium truncate">{p.descricao}</p>
                    <p className="text-afj-cream/45 text-sm lg:text-lg truncate">
                      {p.tipo ? `${p.tipo} · ` : ""}{p.numero_cnj || "Processo"}{p.tribunal ? ` · ${p.tribunal}` : ""}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
