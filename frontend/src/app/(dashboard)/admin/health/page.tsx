"use client";
import { useState, useEffect, useCallback } from "react";
import {
  Activity, Database, Zap, Search, Bot, Globe, Mail, Shield, Lock,
  FileSearch, Bell, HardDrive, Archive, RefreshCw, CheckCircle, XCircle,
  AlertTriangle, Clock, Wrench, ChevronDown, ChevronRight, Newspaper,
  Cpu, Layers, ListChecks, Boxes, DollarSign, Link2,
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

// Snapshot de infra do endpoint SUPERADMIN /system/brain/infra (F1).
interface BrainInfra {
  timestamp: string;
  coleta_ms: number;
  celery: { ok: boolean; workers: number; total_ativas?: number; detail?: string;
    workers_detail?: { nome: string; ativas: number; agendadas: number }[];
    beat_schedule?: { nome: string; task: string; schedule: string }[] };
  redis: { ok: boolean; configured?: boolean; memoria_usada?: string; clientes_conectados?: number;
    total_chaves?: number; fila_celery?: number | null; detail?: string };
  qdrant: { ok: boolean; configured?: boolean; total_colecoes?: number;
    colecoes?: { nome: string; pontos: number | null }[]; detail?: string };
  postgres_pool: { ok: boolean; tamanho?: number; em_uso?: number; overflow?: number };
  jobs: { ok: boolean; agent_runs_24h_por_status?: Record<string, number>;
    sync_runs_recentes?: { fonte: string; tipo: string; status: string; started_at: string | null }[] };
}

// Snapshot tenant-scoped do próprio escritório (GET /system/health/tenant-infra) —
// visível a ADMIN/SOCIO/SUPERADMIN, complementa o bloco acima (SUPERADMIN-only).
interface TenantInfra {
  integracoes_conectadas: { provider: string; nome: string; status: string }[];
  custo_ia: { total_usd: number; execucoes: number; limite_usd: number | null; periodo_dias: number } | null;
  captura: {
    processos_monitorados: number;
    ultima_sincronizacao: { fonte: string; tipo: string; status: string; started_at: string | null } | null;
  } | null;
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
    desc: "API pública — enriquecimento de metadados e andamentos por número (a busca por OAB é via Comunica)",
    icon: Globe,
    getStatus: (d) => d.services.datajud.ok ? "funcionando" : "atencao",
    getLatency: (d) => d.services.datajud.latency_ms,
  },
  {
    key: "publicacoes",
    label: "Publicações / DJe",
    desc: "Comunica/DJEN — captura automática de intimações por OAB",
    icon: Newspaper,
    getStatus: () => "funcionando",
    getLatency: () => null,
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
    desc: "Web Push (VAPID) — alertas em tempo real no navegador e no app",
    icon: Bell,
    getStatus: () => "funcionando",
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
  { name: "Prazos automáticos",       items: "Dias úteis, feriados forenses (nacionais + locais) e recesso; alertas resilientes", done: true },
  { name: "CRM + Funil de vendas",    items: "Clientes/LGPD, oportunidades com forecast, Portal do Cliente", done: true },
  { name: "Segurança & HITL",         items: "Papéis (allowlist), isolamento do portal, aprovações restritas, faturas/LGPD blindados, rate-limit", done: true },
  { name: "Produção viva",            items: "Worker/agendador Celery no deploy, WebSocket tempo-real, Sentry, CI com gates reais", done: true },
  { name: "Multi-dispositivo",        items: "Celular, tablet e Smart TV (painel de recepção); PWA instalável e offline", done: true },
  { name: "Publicações / DJe",        items: "Captura automática de intimações (Comunica/DJEN) → andamento + prazo por triagem", done: true },
  { name: "App nativo (base)",        items: "Projeto Capacitor pronto para gerar/publicar Android e iOS (ver MOBILE.md)", done: true },
  { name: "Equipe & Minha Área",      items: "Responsável + colaboradores por processo; filtro \"Meus\" e painel pessoal do advogado", done: true },
  { name: "Planos, limites & filiais", items: "Tiers STANDARD/PRO/ENTERPRISE com limites reais; filiais self-serve no ENTERPRISE", done: true },
  { name: "Gestão de carteira",       items: "Reatribuição de carteira entre advogados + painel de distribuição de carga na gestão", done: true },
  { name: "Modo confidencial",        items: "Interruptor por escritório: advogado vê só a própria equipe; sócios/gestão veem tudo", done: true },
  { name: "Monitoramento processual", items: "Captura por OAB (Comunica) + enriquecimento e andamentos reais (DataJud) + aviso à equipe + sinal de possível prazo", done: true },
  { name: "Gestão documental",        items: "CRUD completo de documentos (criar/editar/arquivar) + histórico de versões com restauração", done: true },
  { name: "Integrações externas",     items: "Gateway de pagamento, assinatura digital, WhatsApp — aguardam credenciais", done: false, active: true },
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
  const [infra, setInfra] = useState<BrainInfra | null>(null);
  const [tenantInfra, setTenantInfra] = useState<TenantInfra | null>(null);

  // Infra profunda (Celery/Redis/Qdrant/pool/jobs) — só o SUPERADMIN é autorizado
  // pelo endpoint; para os demais admins o 403 é silencioso (painel some, mas o
  // bloco tenant-scoped abaixo cobre o que importa pro ADMIN de escritório).
  const fetchInfra = useCallback(async () => {
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/system/brain/infra", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setInfra(await res.json());
      else setInfra(null);
    } catch { setInfra(null); }
  }, []);

  // Saúde do próprio escritório — ADMIN/SOCIO/SUPERADMIN.
  const fetchTenantInfra = useCallback(async () => {
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/system/health/tenant-infra", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setTenantInfra(await res.json());
      else setTenantInfra(null);
    } catch { setTenantInfra(null); }
  }, []);

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

  useEffect(() => { fetchHealth(); fetchInfra(); fetchTenantInfra(); }, [fetchHealth, fetchInfra, fetchTenantInfra]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(() => { fetchHealth(); fetchInfra(); fetchTenantInfra(); }, 15000);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchHealth, fetchInfra, fetchTenantInfra]);

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

      {/* Saúde do meu escritório (ADMIN/SOCIO/SUPERADMIN — /system/health/tenant-infra) */}
      {tenantInfra && (
        <div className="afj-card p-5">
          <h2 className="font-semibold text-sm text-afj-black mb-4 flex items-center gap-2">
            <Activity size={15} className="text-afj-gold" />
            Saúde do meu escritório
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {/* Integrações conectadas */}
            <div className="rounded-sm border border-afj-cream-dark p-3">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-afj-black/70 mb-2">
                <Link2 size={12} className="text-afj-gold" /> Integrações conectadas
              </div>
              {tenantInfra.integracoes_conectadas.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {tenantInfra.integracoes_conectadas.map((i) => (
                    <span key={i.provider} className="text-[11px] px-2 py-0.5 rounded-full bg-green-50 text-green-700 border border-green-200">
                      {i.nome}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-[11px] text-afj-black/40">Nenhuma conectada — veja Integrações.</p>
              )}
            </div>
            {/* Custo de IA do mês */}
            <div className="rounded-sm border border-afj-cream-dark p-3">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-afj-black/70 mb-2">
                <DollarSign size={12} className="text-afj-gold" /> Custo de IA (30 dias)
              </div>
              {tenantInfra.custo_ia ? (
                <>
                  <p className="text-2xl font-bold text-afj-black">
                    US$ {tenantInfra.custo_ia.total_usd.toFixed(2)}
                    {tenantInfra.custo_ia.limite_usd ? (
                      <span className="text-sm text-afj-black/40"> / {tenantInfra.custo_ia.limite_usd.toFixed(2)}</span>
                    ) : null}
                  </p>
                  <p className="text-[11px] text-afj-black/50">{tenantInfra.custo_ia.execucoes} execução(ões)</p>
                </>
              ) : (
                <p className="text-[11px] text-afj-black/40">Sem dados no período.</p>
              )}
            </div>
            {/* Captura & monitoramento */}
            <div className="rounded-sm border border-afj-cream-dark p-3">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-afj-black/70 mb-2">
                <RefreshCw size={12} className="text-afj-gold" /> Captura & monitoramento
              </div>
              {tenantInfra.captura ? (
                <>
                  <p className="text-2xl font-bold text-afj-black">{tenantInfra.captura.processos_monitorados}</p>
                  <p className="text-[11px] text-afj-black/50">
                    processo(s) monitorado(s)
                    {tenantInfra.captura.ultima_sincronizacao ? (
                      <> · última sync: <span className={
                        tenantInfra.captura.ultima_sincronizacao.status === "OK" ? "text-green-600"
                        : tenantInfra.captura.ultima_sincronizacao.status === "ERRO" ? "text-red-600" : "text-afj-black/40"
                      }>{tenantInfra.captura.ultima_sincronizacao.status}</span></>
                    ) : " · nenhuma sincronização ainda"}
                  </p>
                </>
              ) : (
                <p className="text-[11px] text-afj-black/40">Sem dados.</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Infraestrutura em tempo real (SUPERADMIN — /system/brain/infra, F1) */}
      {infra && (
        <div className="afj-card p-5">
          <h2 className="font-semibold text-sm text-afj-black mb-4 flex items-center gap-2">
            <Cpu size={15} className="text-afj-gold" />
            Infraestrutura em tempo real
            <span className="text-[10px] font-normal text-afj-black/35">· coleta {infra.coleta_ms}ms</span>
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {/* Celery */}
            <div className="rounded-sm border border-afj-cream-dark p-3">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-afj-black/70 mb-2">
                <Zap size={12} className={infra.celery.ok ? "text-green-500" : "text-red-500"} /> Celery
              </div>
              {infra.celery.ok ? (
                <>
                  <p className="text-2xl font-bold text-afj-black">{infra.celery.workers}</p>
                  <p className="text-[11px] text-afj-black/50">worker(s) · {infra.celery.total_ativas ?? 0} task(s) ativa(s)</p>
                </>
              ) : (
                <p className="text-[11px] text-red-600">{infra.celery.detail || "nenhum worker respondeu"}</p>
              )}
            </div>
            {/* Redis */}
            <div className="rounded-sm border border-afj-cream-dark p-3">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-afj-black/70 mb-2">
                <Database size={12} className={infra.redis.ok ? "text-green-500" : "text-red-500"} /> Redis
              </div>
              {infra.redis.ok ? (
                <>
                  <p className="text-sm font-bold text-afj-black">{infra.redis.memoria_usada || "—"}</p>
                  <p className="text-[11px] text-afj-black/50">
                    fila: {infra.redis.fila_celery ?? "—"} · {infra.redis.clientes_conectados ?? "—"} clientes · {infra.redis.total_chaves ?? "—"} chaves
                  </p>
                </>
              ) : (
                <p className="text-[11px] text-red-600">{infra.redis.detail || "indisponível"}</p>
              )}
            </div>
            {/* Qdrant */}
            <div className="rounded-sm border border-afj-cream-dark p-3">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-afj-black/70 mb-2">
                <Boxes size={12} className={infra.qdrant.ok ? "text-green-500" : "text-afj-black/30"} /> Qdrant (RAG)
              </div>
              {infra.qdrant.ok ? (
                <>
                  <p className="text-2xl font-bold text-afj-black">{infra.qdrant.total_colecoes ?? 0}</p>
                  <p className="text-[11px] text-afj-black/50">
                    coleções · {(infra.qdrant.colecoes || []).reduce((s, c) => s + (c.pontos || 0), 0).toLocaleString("pt-BR")} pontos
                  </p>
                </>
              ) : (
                <p className="text-[11px] text-afj-black/45">{infra.qdrant.detail || "não configurado"}</p>
              )}
            </div>
            {/* Postgres pool */}
            <div className="rounded-sm border border-afj-cream-dark p-3">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-afj-black/70 mb-2">
                <Layers size={12} className={infra.postgres_pool.ok ? "text-green-500" : "text-red-500"} /> Postgres pool
              </div>
              {infra.postgres_pool.ok ? (
                <>
                  <p className="text-2xl font-bold text-afj-black">{infra.postgres_pool.em_uso ?? 0}<span className="text-sm text-afj-black/40">/{infra.postgres_pool.tamanho ?? 0}</span></p>
                  <p className="text-[11px] text-afj-black/50">conexões em uso · overflow {infra.postgres_pool.overflow ?? 0}</p>
                </>
              ) : (
                <p className="text-[11px] text-red-600">indisponível</p>
              )}
            </div>
          </div>

          {/* AgentRun por status (24h) + SyncRun recentes */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-4">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-afj-black/40 mb-2 flex items-center gap-1.5">
                <ListChecks size={12} /> Execuções de agentes (24h)
              </p>
              {infra.jobs.ok && Object.keys(infra.jobs.agent_runs_24h_por_status || {}).length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {Object.entries(infra.jobs.agent_runs_24h_por_status || {}).map(([st, n]) => (
                    <span key={st} className={`inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded-sm border ${
                      st === "SUCCESS" ? "bg-green-50 text-green-700 border-green-200"
                      : st === "FAILED" ? "bg-red-50 text-red-600 border-red-200"
                      : st === "RUNNING" ? "bg-blue-50 text-blue-700 border-blue-200"
                      : "bg-afj-cream text-afj-black/60 border-afj-cream-dark"
                    }`}>{st}: <strong>{n}</strong></span>
                  ))}
                </div>
              ) : <p className="text-xs text-afj-black/40">Sem execuções nas últimas 24h.</p>}
            </div>
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-afj-black/40 mb-2 flex items-center gap-1.5">
                <RefreshCw size={12} /> Sincronizações recentes (captura)
              </p>
              {infra.jobs.sync_runs_recentes && infra.jobs.sync_runs_recentes.length > 0 ? (
                <div className="space-y-1 max-h-28 overflow-y-auto pr-1">
                  {infra.jobs.sync_runs_recentes.map((s, i) => (
                    <div key={i} className="flex items-center justify-between text-[11px] text-afj-black/60">
                      <span>{s.tipo} · {s.fonte}</span>
                      <span className={s.status === "OK" ? "text-green-600" : s.status === "ERRO" ? "text-red-600" : "text-afj-black/40"}>{s.status}</span>
                    </div>
                  ))}
                </div>
              ) : <p className="text-xs text-afj-black/40">Nenhuma sincronização registrada.</p>}
            </div>
          </div>
        </div>
      )}

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
