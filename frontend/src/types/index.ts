// Tipos compartilhados AFJ CORE SYSTEM

// ─── Auth ────────────────────────────────────────────────────────────────────

export interface User {
  id: string;
  email: string;
  full_name: string;
  oab_number: string | null;
  role: "ADMIN" | "SOCIO" | "ADVOGADO" | "PARALEGAL" | "ASSISTENTE";
  is_active: boolean;
  created_at: string;
}

// ─── Clientes ────────────────────────────────────────────────────────────────

export interface Cliente {
  id: string;
  tipo: "PF" | "PJ";
  nome_completo: string;
  email: string | null;
  telefone: string | null;
  whatsapp: string | null;
  origem: string | null;
  status: string;
  lgpd_consent: boolean;
  lgpd_consent_at: string | null;
  created_at: string;
}

// ─── Processos ───────────────────────────────────────────────────────────────

export interface Processo {
  id: string;
  numero_cnj: string | null;
  numero_original: string | null;
  tribunal: string;
  vara: string | null;
  comarca: string | null;
  uf: string | null;
  tipo_acao: string | null;
  area_direito: string | null;
  fase: string | null;
  situacao: "ATIVO" | "SUSPENSO" | "ARQUIVADO" | "ENCERRADO";
  valor_causa: number | null;
  client_id: string | null;
  polo: string | null;
  parte_contraria: string | null;
  oab_responsavel: string | null;
  distribuicao_data: string | null;
  ultimo_andamento_at: string | null;
  proximo_prazo_at: string | null;
  monitoring_active: boolean;
  created_at: string;
}

export interface ProcessoDetalhe extends Processo {
  movimentacoes: Movimentacao[];
  prazos: Prazo[];
}

export interface Movimentacao {
  id: string;
  process_id: string;
  data_movimento: string;
  descricao: string;
  tipo: string | null;
  documento_url: string | null;
  ai_summary: string | null;
  created_at: string;
}

export interface Prazo {
  id: string;
  process_id: string;
  descricao: string;
  data_prazo: string;
  data_fatal: string | null;
  tipo: string | null;
  status: "PENDENTE" | "CUMPRIDO" | "PERDIDO";
}

// ─── Documentos ──────────────────────────────────────────────────────────────

export interface Documento {
  id: string;
  process_id: string | null;
  client_id: string | null;
  tipo: string;
  titulo: string;
  conteudo_texto: string | null;
  conteudo_html: string | null;
  arquivo_url: string | null;
  versao: number;
  status: "RASCUNHO" | "REVISAO" | "APROVADO" | "PROTOCOLADO";
  gerado_por_ia: boolean;
  agent_run_id: string | null;
  created_at: string;
}

export interface Peticao {
  id: string;
  document_id: string;
  process_id: string | null;
  tipo_peticao: string;
  template_used: string | null;
  ai_model: string | null;
  ai_tokens_used: number | null;
  review_status: string | null;
  reviewed_by: string | null;
  review_notes: string | null;
  created_at: string;
}

export interface Contrato {
  id: string;
  document_id: string;
  client_id: string | null;
  tipo: string;
  valor_total: number | null;
  data_inicio: string | null;
  data_fim: string | null;
  status: string;
  renovacao_auto: boolean;
  created_at: string;
}

// ─── Agentes ─────────────────────────────────────────────────────────────────

export type AgentStatus =
  | "idle"
  | "running"
  | "success"
  | "failed"
  | "awaiting_approval"
  | "paused";

export interface AgentRun {
  id: string;
  agent_name: string;
  trigger_type: "MANUAL" | "SCHEDULED" | "WEBHOOK" | "CHAINED";
  triggered_by: string | null;
  task_type: string;
  input_data: Record<string, unknown>;
  output_data: Record<string, unknown> | null;
  status: "RUNNING" | "SUCCESS" | "FAILED" | "PAUSED" | "AWAITING_APPROVAL";
  error_message: string | null;
  tokens_used: number | null;
  cost_usd: string | null;
  duration_ms: number | null;
  requires_approval: boolean;
  started_at: string;
  completed_at: string | null;
}

export interface Approval {
  id: string;
  run_id: string | null;
  tipo: string;
  titulo: string;
  descricao: string;
  ai_suggestion: Record<string, unknown>;
  prioridade: "LOW" | "NORMAL" | "HIGH" | "URGENT";
  status: "PENDENTE" | "APROVADO" | "REJEITADO";
  assignee_id: string | null;
  approved_by: string | null;
  rejection_reason: string | null;
  expires_at: string | null;
  resolved_at: string | null;
  created_at: string;
}

// ─── Financeiro ──────────────────────────────────────────────────────────────

export interface FinancialEntry {
  id: string;
  tipo: "RECEITA" | "DESPESA";
  categoria: string | null;
  client_id: string | null;
  process_id: string | null;
  descricao: string;
  valor: number;
  data_vencimento: string | null;
  data_pagamento: string | null;
  status: "PENDENTE" | "PAGO" | "CANCELADO";
  created_at: string;
}

// ─── Auditoria ───────────────────────────────────────────────────────────────

export interface AuditLog {
  id: number;
  event_id: string;
  timestamp: string;
  user_id: string | null;
  agent_name: string | null;
  run_id: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  success: boolean;
  contains_pii: boolean;
  legal_basis: string | null;
  ip_address: string | null;
  error_detail: string | null;
}

// ─── Paginação ───────────────────────────────────────────────────────────────

export interface PaginatedResponse<T> {
  total: number;
  limit: number;
  offset: number;
  items: T[];
}

// ─── API helpers ─────────────────────────────────────────────────────────────

export interface ApiError {
  detail: string;
  status?: number;
}

export type ApiResponse<T> = { data: T; error: null } | { data: null; error: ApiError };
