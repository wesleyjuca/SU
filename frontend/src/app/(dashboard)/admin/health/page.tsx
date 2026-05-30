"use client";
import { useState, useEffect, useCallback } from "react";
import { Activity, Database, Wifi, Server, RefreshCw, CheckCircle, XCircle, Mail, Shield, Clock, Bot } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";

interface ServiceStatus {
  ok: boolean;
  latency_ms: number;
}

interface AgentRun {
  agent: string;
  status: string;
  started_at: string;
}

interface HealthData {
  status: "operational" | "degraded";
  timestamp: string;
  version: string;
  environment: string;
  services: {
    postgresql: ServiceStatus;
    redis: ServiceStatus;
    qdrant: ServiceStatus;
  };
  email_enabled: boolean;
  sentry_enabled: boolean;
  recent_agent_runs: AgentRun[];
}

function LatencyBadge({ ms }: { ms: number }) {
  if (ms < 0) return <span className="text-xs text-afj-black/30">—</span>;
  const color = ms < 50 ? "text-green-600" : ms < 200 ? "text-amber-600" : "text-red-600";
  return <span className={`text-xs font-mono ${color}`}>{ms}ms</span>;
}

function StatusDot({ ok }: { ok: boolean }) {
  return ok
    ? <CheckCircle size={16} className="text-green-500 flex-shrink-0" />
    : <XCircle size={16} className="text-red-500 flex-shrink-0" />;
}

function RunStatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    SUCCESS: "bg-green-100 text-green-700",
    RUNNING: "bg-afj-gold/20 text-afj-gold",
    FAILED: "bg-red-100 text-red-700",
    AWAITING_APPROVAL: "bg-amber-100 text-amber-700",
  };
  return (
    <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${map[status] ?? "bg-afj-cream text-afj-black/50"}`}>
      {status}
    </span>
  );
}

export default function HealthPage() {
  const [data, setData] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);

  const fetchHealth = useCallback(async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/system/health/detailed", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        setData(await res.json());
        setLastRefresh(new Date());
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
  }, [fetchHealth]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(fetchHealth, 15000);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchHealth]);

  const isOk = data?.status === "operational";

  return (
    <div className="max-w-6xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Monitoramento" }]} />

      <div className="flex items-start justify-between">
        <div>
          <h1 className="font-display text-2xl font-semibold text-afj-black">Monitoramento do Sistema</h1>
          <p className="text-afj-black/50 text-sm">Status em tempo real dos serviços AFJ CORE</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-afj-black/60 cursor-pointer">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="accent-afj-gold"
            />
            Auto (15s)
          </label>
          <button
            onClick={fetchHealth}
            disabled={loading}
            className="btn-afj-outline text-xs py-1.5 px-3 rounded-sm flex items-center gap-1.5"
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
            Atualizar
          </button>
        </div>
      </div>

      {/* Status global */}
      <div className={`afj-card p-5 flex items-center gap-4 border-l-4 ${isOk ? "border-green-500" : "border-red-500"}`}>
        <Activity size={28} className={isOk ? "text-green-500" : "text-red-500"} />
        <div className="flex-1">
          <p className={`text-lg font-bold ${isOk ? "text-green-700" : "text-red-700"}`}>
            {loading ? "Verificando…" : isOk ? "Sistema Operacional" : "Sistema Degradado"}
          </p>
          {data && (
            <p className="text-xs text-afj-black/40">
              v{data.version} · {data.environment} ·{" "}
              {lastRefresh && `Atualizado ${lastRefresh.toLocaleTimeString("pt-BR")}`}
            </p>
          )}
        </div>
        {data && (
          <div className="text-right">
            <p className="text-xs text-afj-black/40">Verificado em</p>
            <p className="text-sm font-mono text-afj-black/70">
              {new Date(data.timestamp).toLocaleTimeString("pt-BR")}
            </p>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Serviços */}
        <div className="afj-card p-5">
          <h2 className="font-semibold text-sm text-afj-black mb-4 flex items-center gap-2">
            <Server size={15} className="text-afj-gold" />
            Serviços de Infraestrutura
          </h2>
          {loading && !data ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => <div key={i} className="h-12 bg-afj-cream-dark rounded animate-pulse" />)}
            </div>
          ) : data ? (
            <div className="space-y-3">
              {([
                { key: "postgresql", label: "PostgreSQL", icon: Database },
                { key: "redis", label: "Redis", icon: Wifi },
                { key: "qdrant", label: "Qdrant (Vector DB)", icon: Server },
              ] as const).map(({ key, label, icon: Icon }) => {
                const svc = data.services[key];
                return (
                  <div key={key} className="flex items-center gap-3 p-3 bg-afj-cream/50 rounded-sm">
                    <StatusDot ok={svc.ok} />
                    <Icon size={14} className="text-afj-black/40" />
                    <span className="flex-1 text-sm text-afj-black/80">{label}</span>
                    <LatencyBadge ms={svc.latency_ms} />
                    <span className={`text-xs font-medium ${svc.ok ? "text-green-600" : "text-red-600"}`}>
                      {svc.ok ? "Online" : "Offline"}
                    </span>
                  </div>
                );
              })}
            </div>
          ) : null}

          {/* Integrações opcionais */}
          {data && (
            <div className="mt-4 pt-4 border-t border-afj-cream-dark space-y-2">
              <p className="text-xs text-afj-black/40 font-medium mb-2">Integrações Opcionais</p>
              <div className="flex items-center gap-3 p-2.5 rounded-sm bg-afj-cream/30">
                <Mail size={13} className={data.email_enabled ? "text-green-500" : "text-afj-black/25"} />
                <span className="flex-1 text-sm text-afj-black/70">Email (SMTP)</span>
                <span className={`text-xs ${data.email_enabled ? "text-green-600 font-medium" : "text-afj-black/30"}`}>
                  {data.email_enabled ? "Ativo" : "Não configurado"}
                </span>
              </div>
              <div className="flex items-center gap-3 p-2.5 rounded-sm bg-afj-cream/30">
                <Shield size={13} className={data.sentry_enabled ? "text-green-500" : "text-afj-black/25"} />
                <span className="flex-1 text-sm text-afj-black/70">Sentry (Error Tracking)</span>
                <span className={`text-xs ${data.sentry_enabled ? "text-green-600 font-medium" : "text-afj-black/30"}`}>
                  {data.sentry_enabled ? "Ativo" : "Não configurado"}
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Agentes recentes */}
        <div className="afj-card p-5">
          <h2 className="font-semibold text-sm text-afj-black mb-4 flex items-center gap-2">
            <Bot size={15} className="text-afj-gold" />
            Atividade de Agentes (24h)
          </h2>
          {loading && !data ? (
            <div className="space-y-2">
              {[1, 2, 3, 4].map((i) => <div key={i} className="h-9 bg-afj-cream-dark rounded animate-pulse" />)}
            </div>
          ) : data && data.recent_agent_runs.length > 0 ? (
            <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
              {data.recent_agent_runs.map((run, i) => (
                <div key={i} className="flex items-center gap-3 text-xs py-1.5">
                  <Clock size={11} className="text-afj-black/25 flex-shrink-0" />
                  <span className="text-afj-black/60 font-mono flex-shrink-0">
                    {new Date(run.started_at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}
                  </span>
                  <span className="flex-1 text-afj-black/70 truncate">{run.agent}</span>
                  <RunStatusBadge status={run.status} />
                </div>
              ))}
            </div>
          ) : (
            <div className="py-8 text-center">
              <Bot size={24} className="mx-auto text-afj-black/15 mb-2" />
              <p className="text-sm text-afj-black/40">Nenhuma execução nas últimas 24h</p>
            </div>
          )}
        </div>
      </div>

      {/* Config info box */}
      <div className="afj-card p-4 bg-afj-cream/50">
        <p className="text-xs text-afj-black/50 leading-relaxed">
          <span className="font-semibold text-afj-black">Configuração:</span>{" "}
          Para ativar o email de alertas, configure <code className="bg-afj-cream-dark px-1 rounded text-[11px]">SMTP_HOST</code>,{" "}
          <code className="bg-afj-cream-dark px-1 rounded text-[11px]">SMTP_USER</code>,{" "}
          <code className="bg-afj-cream-dark px-1 rounded text-[11px]">SMTP_PASSWORD</code> e{" "}
          <code className="bg-afj-cream-dark px-1 rounded text-[11px]">EMAIL_ENABLED=true</code> nas variáveis de ambiente do backend.
          Para Sentry, configure <code className="bg-afj-cream-dark px-1 rounded text-[11px]">SENTRY_DSN</code>.
        </p>
      </div>
    </div>
  );
}
