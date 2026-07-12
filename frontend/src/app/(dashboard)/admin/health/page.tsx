"use client";
import { useState, useEffect, useCallback } from "react";
import {
  Activity, Database, Zap, Search, Bot, Globe, Mail, Shield, Lock,
  FileSearch, Bell, HardDrive, Archive, RefreshCw, CheckCircle, XCircle,
  AlertTriangle, Clock, Wrench, ChevronDown, ChevronRight,
} from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";

type ModuleStatus = "funcionando" | "atencao" | "erro" | "nao_configurado" | "em_desenvolvimento" | "planejado";

interface ServiceStatus {
  ok: boolean;
  latency_ms: number;
  configured?: boolean;   // IA central: há chave de sistema? (BYOK dispensa)
  provider?: string;      // provider de IA ativo: "anthropic" | "gemini"
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
  uptime_seconds: number | null;
  services: {
    postgresql: ServiceStatus;
    redis: ServiceStatus;
    qdrant: ServiceStatus;
    anthropic: ServiceStatus;
    datajud: ServiceStatus;
  };
  email_enabled: boolean;
  sentry_enabled: boolean;
  recent_agent_runs: AgentRun[];
}

interface Module {
  key: string;
  label: string;
  desc: string;
  icon: React.ElementType;
  getStatus: (data: HealthData) => ModuleStatus;
  getLatency?: (data: HealthData) => number | null;
}

const MODULES: Module[] = [
  {
    key: "postgresql",
    label: "Banco de Dados",
    desc: "PostgreSQL — armazenamento principal",
    icon: Database,
    getStatus: (d) => d.services.postgresql.ok ? (d.services.postgresql.latency_ms > 200 ? "atencao" : "funcionando") : "erro",
    getLatency: (d) => d.services.postgresql.latency_ms,
  },
  {
    key: "redis",
    label: "Cache",
    desc: "Redis — sessões e fila de tarefas",
    icon: Zap,
    getStatus: (d) => d.services.redis.ok ? (d.services.redis.latency_ms > 200 ? "atencao" : "funcionando") : "erro",
    getLatency: (d) => d.services.redis.latency_ms,
  },
  {
    key: "qdrant",
    label: "Busca Vetorial",
    desc: "Qdrant — RAG de jurisprudência",
    icon: Search,
    getStatus: (d) => d.services.qdrant.ok ? "funcionando" : "atencao",
    getLatency: (d) => d.services.qdrant.latency_ms,
  },
  {
    key: "anthropic",
    label: "IA Generativa",
    desc: "IA central do escritório — usuários podem usar chave própria (BYOK)",
    icon: Bot,
    // BYOK-first: sem chave central não é erro, é "não configurado" (neutro).
    getStatus: (d) =>
      d.services.anthropic.configured === false
        ? "nao_configurado"
        : d.services.anthropic.ok
          ? (d.services.anthropic.latency_ms > 1000 ? "atencao" : "funcionando")
          : "erro",
    getLatency: (d) => d.services.anthropic.latency_ms,
  },
  {
    key: "datajud",
    label: "CNJ DataJud",
    desc: "API pública — captura de processos",
    icon: Globe,
    getStatus: (d) => d.services.datajud.ok ? "funcionando" : "atencao",
    getLatency: (d) => d.services.datajud.latency_ms,
  },
  {
    key: "auth",
    label: "Autenticação",
    desc: "JWT — tokens de acesso e sessão",
    icon: Lock,
    getStatus: () => "funcionando",
    getLatency: () => null,
  },
  {
    key: "email",
    label: "E-mail (SMTP)",
    desc: "Envio de notificações por e-mail",
    icon: Mail,
    getStatus: (d) => d.email_enabled ? "funcionando" : "atencao",
    getLatency: () => null,
  },
  {
    key: "sentry",
    label: "Rastreamento de Erros",
    desc: "Sentry — monitoramento de exceções",
    icon: Shield,
    getStatus: (d) => d.sentry_enabled ? "funcionando" : "atencao",
    getLatency: () => null,
  },
  {
    key: "auditoria",
    label: "Auditoria",
    desc: "Log imutável de ações do sistema",
    icon: FileSearch,
    getStatus: () => "funcionando",
    getLatency: () => null,
  },
  {
    key: "notificacoes",
    label: "Notificações Push",
    desc: "Alertas em tempo real no navegador",
    icon: Bell,
    getStatus: () => "em_desenvolvimento",
    getLatency: () => null,
  },
  {
    key: "backup",
    label: "Backup Automático",
    desc: "Backup incremental diário",
    icon: HardDrive,
    getStatus: () => "planejado",
    getLatency: () => null,
  },
  {
    key: "storage",
    label: "Armazenamento",
    desc: "Documentos e arquivos do escritório",
    icon: Archive,
    getStatus: () => "funcionando",
    getLatency: () => null,
  },
];

const STATUS_CONFIG: Record<ModuleStatus, { label: string; bg: string; text: string; border: string; icon: React.ElementType }> = {
  funcionando:       { label: "Funcionando",       bg: "bg-green-50",   text: "text-green-700",  border: "border-green-200", icon: CheckCircle },
  atencao:           { label: "Atenção",            bg: "bg-amber-50",   text: "text-amber-700",  border: "border-amber-200", icon: AlertTriangle },
  erro:              { label: "Erro",               bg: "bg-red-50",     text: "text-red-700",    border: "border-red-200",   icon: XCircle },
  nao_configurado:   { label: "Não Configurado",    bg: "bg-gray-50",    text: "text-gray-500",   border: "border-gray-200",  icon: Clock },
  em_desenvolvimento:{ label: "Em Desenvolvimento", bg: "bg-blue-50",    text: "text-blue-700",   border: "border-blue-200",  icon: Wrench },
  planejado:         { label: "Planejado",          bg: "bg-gray-50",    text: "text-gray-500",   border: "border-gray-200",  icon: Clock },
};

const PHASES = [
  { name: "Fundação",                 items: "Auth, Processos, Clientes, Agenda, Documentos", done: true },
  { name: "IA + HITL",                items: "19 agentes (LangGraph), Petições/Contratos com aprovação humana, RAG, BYOK", done: true },
  { name: "Financeiro + Faturamento", items: "Receitas/despesas, inadimplência, faturas a cliente (PDF timbrado)", done: true },
  { name: "Multi-tenant / SaaS",      items: "Isolamento por escritório, unidades da banca, cobrança mensal + bloqueio suave", done: true },
  { name: "Relatórios + Gestão",      items: "Financeiro/processos/IA, consolidado da banca (PDF/Excel/CSV), rentabilidade/produtividade/êxito", done: true },
  { name: "Prazos automáticos",       items: "Dias úteis, feriados forenses (nacionais + locais) e recesso; alertas", done: true },
  { name: "CRM + Funil de vendas",    items: "Clientes/LGPD, oportunidades com forecast, Portal do Cliente", done: true },
  { name: "Integrações externas",     items: "Gateway de pagamento, protocolo/assinatura digital, WhatsApp — aguardam credenciais", done: false, active: true },
  { name: "Mobile / PWA",             items: "App instalável hoje; offline ampliado e push em evolução", done: false },
];

// Conclusão honesta: pilares concluídos + metade dos parciais (integrações
// externas aguardam credenciais; PWA em evolução).
const COMPLETION_PERCENT = Math.round(
  (PHASES.filter((p) => p.done).length + PHASES.filter((p) => !p.done).length * 0.5) / PHASES.length * 100
);

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function LatencyBadge({ ms }: { ms: number | null }) {
  if (ms === null || ms < 0) return <span className="text-xs text-gray-300">—</span>;
  const color = ms < 100 ? "text-green-600" : ms < 500 ? "text-amber-600" : "text-red-600";
  return <span className={`text-[10px] font-mono ${color}`}>{ms}ms</span>;
}

function RunStatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    SUCCESS: "bg-green-100 text-green-700",
    RUNNING: "bg-afj-gold/20 text-afj-gold",
    FAILED: "bg-red-100 text-red-700",
    AWAITING_APPROVAL: "bg-amber-100 text-amber-700",
    CANCELADO: "bg-gray-200 text-gray-600",
  };
  return (
    <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${map[status] ?? "bg-afj-cream text-afj-black/50"}`}>
      {status}
    </span>
  );
}

function ModuleCard({ module, data }: { module: Module; data: HealthData }) {
  const status = module.getStatus(data);
  const latency = module.getLatency?.(data) ?? null;
  const cfg = STATUS_CONFIG[status];
  const StatusIcon = cfg.icon;
  const ModIcon = module.icon;

  return (
    <div className={`rounded-sm border p-4 ${cfg.bg} ${cfg.border} flex flex-col gap-2`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <ModIcon size={15} className={cfg.text} />
          <span className="text-sm font-semibold text-afj-black">{module.label}</span>
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          {latency !== null && latency >= 0 && <LatencyBadge ms={latency} />}
          <StatusIcon size={14} className={cfg.text} />
        </div>
      </div>
      <p className="text-[11px] text-afj-black/50 leading-relaxed">{module.desc}</p>
      <span className={`text-[10px] font-semibold uppercase tracking-wider ${cfg.text}`}>
        {cfg.label}
      </span>
    </div>
  );
}

export default function HealthPage() {
  const [data, setData] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [showRoadmap, setShowRoadmap] = useState(false);
  const [showDiagnostic, setShowDiagnostic] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const fetchHealth = useCallback(async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/system/health/detailed", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        setData(await res.json());
        setFetchError(null);
        setLastRefresh(new Date());
      } else {
        // Não afirmar "degradado": apenas registramos que não foi possível verificar.
        setFetchError(`O serviço de verificação respondeu HTTP ${res.status}.`);
      }
    } catch {
      setFetchError("Não foi possível contatar o serviço de verificação (rede/servidor).");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchHealth(); }, [fetchHealth]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(fetchHealth, 15000);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchHealth]);

  // 3 estados: operacional (verde), degradado (vermelho, só se o backend disse),
  // e não-verificado (âmbar) quando não há dado por erro de fetch.
  const bannerState: "ok" | "degraded" | "unknown" =
    data?.status === "operational" ? "ok"
      : data?.status === "degraded" ? "degraded"
        : (!data && (fetchError || (!loading))) ? "unknown"
          : "unknown";

  const warnings = data
    ? MODULES.filter((m) => {
        const s = m.getStatus(data);
        return s === "atencao" || s === "erro";
      })
    : [];

  const diagnosticMessages: string[] = data
    ? [
        !data.services.postgresql.ok ? "PostgreSQL offline — verifique a URL do banco de dados." : null,
        !data.services.redis.ok ? "Redis offline — verifique REDIS_URL nas variáveis de ambiente." : null,
        // IA central: só alerta se configurada e falhando. Sem chave central o
        // sistema opera em BYOK (cada usuário usa a própria chave) — não é erro.
        (data.services.anthropic.configured !== false && !data.services.anthropic.ok)
          ? `IA central (${data.services.anthropic.provider ?? "provider"}) inacessível — verifique a chave de API do sistema.` : null,
        data.services.postgresql.ok && data.services.postgresql.latency_ms > 200
          ? "Latência alta no banco de dados (>200ms) — considere otimizar queries ou verificar carga." : null,
        !data.email_enabled ? "E-mail não configurado — configure SMTP_HOST, SMTP_USER e SMTP_PASSWORD." : null,
        !data.sentry_enabled ? "Monitoramento de erros inativo — configure SENTRY_DSN para rastreamento." : null,
      ].filter(Boolean) as string[]
    : [];

  return (
    <div className="max-w-6xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Saúde do Sistema" }]} />

      {/* Header */}
      <div className="afj-page-header">
        <div>
          <h1 className="font-display text-2xl font-semibold text-afj-black">Saúde do Sistema</h1>
          <p className="text-afj-black/50 text-sm">Monitoramento em tempo real dos serviços AFJ CORE</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm text-afj-black/60 cursor-pointer">
            <input type="checkbox" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} className="accent-afj-gold" />
            Auto (15s)
          </label>
          {warnings.length > 0 && (
            <button
              onClick={() => setShowDiagnostic(true)}
              className="btn-afj-outline text-xs py-1.5 px-3 rounded-sm flex items-center gap-1.5 text-amber-600 border-amber-300 hover:bg-amber-50"
            >
              <AlertTriangle size={12} />
              {warnings.length} alerta(s)
            </button>
          )}
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

      {/* Banner de status global (3 estados) */}
      {(() => {
        const B = {
          ok:       { border: "border-green-500", text: "text-green-700", icon: "text-green-500", label: "Sistema Operacional" },
          degraded: { border: "border-red-500",   text: "text-red-700",   icon: "text-red-500",   label: "Sistema Degradado" },
          unknown:  { border: "border-amber-400", text: "text-amber-700", icon: "text-amber-500", label: "Não foi possível verificar" },
        }[bannerState];
        return (
      <div className={`afj-card p-5 flex items-center gap-4 border-l-4 ${B.border}`}>
        <Activity size={28} className={B.icon} />
        <div className="flex-1">
          <p className={`text-lg font-bold ${B.text}`}>
            {loading && !data ? "Verificando…" : B.label}
          </p>
          {data ? (
            <p className="text-xs text-afj-black/40 mt-0.5">
              v{data.version} · {data.environment}
              {data.uptime_seconds !== null && ` · Uptime: ${formatUptime(data.uptime_seconds)}`}
              {lastRefresh && ` · Atualizado ${lastRefresh.toLocaleTimeString("pt-BR")}`}
            </p>
          ) : (fetchError && !loading) ? (
            <p className="text-xs text-afj-black/50 mt-0.5">{fetchError} Isso não significa que o sistema está fora do ar — apenas que a verificação não respondeu.</p>
          ) : null}
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
        );
      })()}

      {/* Grid de módulos */}
      {loading && !data ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="h-24 bg-afj-cream-dark rounded animate-pulse" />
          ))}
        </div>
      ) : data ? (
        <div>
          <h2 className="afj-section-title mb-3">Módulos do Sistema</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {MODULES.map((m) => (
              <ModuleCard key={m.key} module={m} data={data} />
            ))}
          </div>
        </div>
      ) : null}

      {/* Atividade de agentes e roadmap */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
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

        {/* Roadmap / Progresso */}
        <div className="afj-card p-5">
          <button
            onClick={() => setShowRoadmap(!showRoadmap)}
            className="w-full flex items-center justify-between mb-4"
          >
            <h2 className="font-semibold text-sm text-afj-black flex items-center gap-2">
              <Activity size={15} className="text-afj-gold" />
              Progresso do Projeto
            </h2>
            {showRoadmap ? <ChevronDown size={14} className="text-afj-black/40" /> : <ChevronRight size={14} className="text-afj-black/40" />}
          </button>

          {/* Barra de progresso */}
          <div className="mb-4">
            <div className="flex justify-between text-xs text-afj-black/50 mb-1.5">
              <span>Conclusão geral</span>
              <span className="font-semibold text-afj-black">{COMPLETION_PERCENT}%</span>
            </div>
            <div className="h-2.5 bg-afj-cream-dark rounded-full overflow-hidden">
              <div
                className="h-full bg-afj-gold rounded-full transition-all duration-500"
                style={{ width: `${COMPLETION_PERCENT}%` }}
              />
            </div>
          </div>

          {showRoadmap && (
            <div className="space-y-2.5">
              {PHASES.map((p, i) => (
                <div key={i} className={`flex items-start gap-2.5 text-xs ${p.active ? "font-medium" : ""}`}>
                  <div className={`mt-0.5 flex-shrink-0 w-4 h-4 rounded-full flex items-center justify-center ${
                    p.done ? "bg-green-500 text-white" : p.active ? "bg-afj-gold text-white" : "bg-afj-cream-dark text-afj-black/30"
                  }`}>
                    {p.done ? <CheckCircle size={10} /> : p.active ? <Activity size={9} /> : <Clock size={9} />}
                  </div>
                  <div>
                    <p className={`${p.done ? "text-afj-black/60 line-through" : p.active ? "text-afj-black" : "text-afj-black/40"}`}>
                      {p.name}
                    </p>
                    <p className="text-afj-black/30 text-[10px]">{p.items}</p>
                  </div>
                </div>
              ))}
            </div>
          )}

          {!showRoadmap && (
            <p className="text-xs text-afj-black/40 text-center mt-1">Clique para ver o roadmap completo</p>
          )}
        </div>
      </div>

      {/* Modal de diagnóstico */}
      {showDiagnostic && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setShowDiagnostic(false)}>
          <div className="bg-white rounded-sm shadow-xl max-w-md w-full p-6 space-y-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-display text-lg font-semibold text-afj-black flex items-center gap-2">
              <AlertTriangle size={18} className="text-amber-500" />
              Diagnóstico Automático
            </h3>
            {diagnosticMessages.length > 0 ? (
              <div className="space-y-3">
                {diagnosticMessages.map((msg, i) => (
                  <div key={i} className="flex gap-2.5 text-sm bg-amber-50 border border-amber-200 rounded-sm p-3">
                    <AlertTriangle size={14} className="text-amber-600 flex-shrink-0 mt-0.5" />
                    <p className="text-amber-800">{msg}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-afj-black/50">Nenhum problema crítico detectado.</p>
            )}
            <button onClick={() => setShowDiagnostic(false)} className="w-full btn-afj-primary rounded-sm">
              Fechar
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
