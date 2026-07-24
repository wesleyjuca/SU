// Tipos compartilhados dos endpoints /system/brain/* (Cérebro 2.0 — Fase 78)

export interface MapaNo { id: string; label: string; grupo: string; saude_key?: string; meta?: Record<string, unknown> }
export interface MapaAresta { de: string; para: string; tipo: string }
export interface Mapa { nos: MapaNo[]; arestas: MapaAresta[]; resumo: Record<string, number> }

export interface FonteSaude { nome: string; capabilities: string[]; breaker: string | null }
export interface CeleryWorker { nome: string; ativas: number; agendadas: number; concorrencia?: number | null }
export interface BeatItem { nome: string; task?: string; schedule?: string }
export interface QdrantColecao { nome: string; pontos: number | null }
export interface SyncRun { fonte: string; tipo: string; status: string; started_at: string | null }

export interface Infra {
  timestamp?: string;
  coleta_ms?: number;
  celery: {
    ok: boolean; workers: number; total_ativas?: number;
    workers_detail?: CeleryWorker[]; beat_schedule?: BeatItem[]; detail?: string;
  };
  redis: {
    ok: boolean; configured?: boolean; memoria_usada?: string; clientes_conectados?: number;
    uptime_dias?: number; total_chaves?: number; fila_celery?: number | null; detail?: string;
  };
  qdrant: { ok: boolean; configured?: boolean; colecoes?: QdrantColecao[]; total_colecoes?: number; detail?: string };
  postgres_pool: { ok: boolean; tamanho?: number; em_uso?: number; overflow?: number; detail?: string };
  jobs?: { ok: boolean; agent_runs_24h_por_status?: Record<string, number>; sync_runs_recentes?: SyncRun[] };
  fontes?: {
    ok: boolean; fontes: FonteSaude[];
    pdpj?: { registrado: boolean; credential_gated: boolean } | null; tribunais?: number | null;
  };
}

export interface LogEvento {
  ts: string;
  level: string;
  event: string;
  extra?: Record<string, string>;
}

export interface MetricasTenant {
  tenant_id: string;
  nome: string;
  plano: string | null;
  ativo: boolean;
  usuarios_ativos: number;
  processos: number;
  agent_runs_24h: number;
  sync_runs: number;
  ultima_atividade: string | null;
}

export interface AuditEvento {
  id: number; timestamp: string | null; action: string; user_id: string | null;
  agent_name: string | null; resource_type: string | null; resource_id: string | null;
  success: boolean; contains_pii: boolean;
  ip_address: string | null; legal_basis: string | null; tenant_id: string | null;
}

/** GET /api/v1/system/brain/<path> com o Bearer token; null em qualquer falha. */
export async function fetchBrain<T>(path: string): Promise<T | null> {
  try {
    const token = localStorage.getItem("afj_access_token");
    const res = await fetch(`/api/v1/system/brain/${path}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}
