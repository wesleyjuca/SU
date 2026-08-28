"use client";
import { useState, useEffect, useCallback } from "react";
import {
  ShieldCheck, CheckCircle2, Clock, Scale, Shield, Users2, FileSearch,
  Lock, AlertTriangle, BookOpenCheck, Megaphone, GraduationCap, ClipboardCheck,
  Loader2, Pencil, ChevronDown, Send,
} from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { useToast } from "@/components/ui/Toast";

// ─── Pilares técnicos já ativos no sistema ────────────────────────────────────
const PILARES_ATIVOS = [
  {
    icon: Users2, titulo: "Supervisão Humana (HITL)",
    desc: "Nenhuma ação crítica da IA é executada sem aprovação humana; rejeições exigem justificativa registrada.",
  },
  {
    icon: FileSearch, titulo: "Auditoria Imutável",
    desc: "Ações relevantes geram registro de auditoria com autor, data e resultado.",
  },
  {
    icon: Lock, titulo: "Isolamento entre Escritórios",
    desc: "Dados e conhecimento (RAG) estritamente separados por escritório em todas as consultas.",
  },
  {
    icon: Shield, titulo: "LGPD e Consentimento",
    desc: "Controle de consentimento por cliente, monitorado pelo agente de compliance.",
  },
  {
    icon: Scale, titulo: "Ética OAB no Marketing",
    desc: "Materiais de marketing verificados contra o Código de Ética da OAB.",
  },
  {
    icon: BookOpenCheck, titulo: "Citações Verificáveis",
    desc: "Citações não confirmadas nas bases são marcadas e bloqueiam aprovação automática.",
  },
  {
    icon: ClipboardCheck, titulo: "Revisão de Acessos",
    desc: "Painel em Admin → Usuários destaca contas ociosas (30/60+ dias sem acesso) para desativação rápida.",
  },
];

const CATEGORIAS = [
  { value: "ETICA", label: "Violação ética" },
  { value: "CONFLITO_INTERESSES", label: "Conflito de interesses" },
  { value: "DADOS_LGPD", label: "Dados pessoais / LGPD" },
  { value: "USO_DE_IA", label: "Mau uso de IA" },
  { value: "ASSEDIO", label: "Assédio ou discriminação" },
  { value: "OUTROS", label: "Outros" },
];

interface Conduct { text: string; version: number; updated_at: string | null; accepted: boolean; accepted_at: string | null }
interface Report { id: string; categoria: string; descricao: string; anonimo: boolean; status: string; resolucao: string | null; created_at: string }

// Fase 189 — "Próximos passos do programa" deixam de ser cards estáticos.
interface Risk {
  id: string; risco: string; categoria: string; probabilidade: string; impacto: string;
  controles: string; responsavel_id: string | null; responsavel_nome: string | null;
  status: string; ultima_revisao_em: string | null; created_at: string;
}
interface Training {
  id: string; titulo: string; categoria: string; conteudo: string;
  obrigatorio: boolean; ativo: boolean; concluido: boolean; concluido_em: string | null; created_at: string;
}
interface TrainingCompletions { titulo: string; total_usuarios_ativos: number; total_concluintes: number; concluintes: { nome: string; email: string; completed_at: string }[] }
interface CommitteeCase {
  id: string; report_id: string | null; titulo: string; descricao: string;
  status: string; decisao: string | null; membros: string[]; decided_at: string | null; created_at: string;
}

const PROBABILIDADES = ["BAIXA", "MEDIA", "ALTA"];
const IMPACTOS = ["BAIXO", "MEDIO", "ALTO"];
const CATEGORIAS_TREINAMENTO = [
  { value: "ETICA", label: "Ética" }, { value: "LGPD", label: "LGPD" }, { value: "USO_DE_IA", label: "Uso de IA" },
];

function authH(): HeadersInit {
  const t = typeof window !== "undefined" ? localStorage.getItem("afj_access_token") : null;
  return { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) };
}

export default function EticaPage() {
  const toast = useToast();
  const [role, setRole] = useState<string>("");
  const isGestor = role === "ADMIN" || role === "SUPERADMIN" || role === "SOCIO";

  // Código de Conduta
  const [conduct, setConduct] = useState<Conduct | null>(null);
  const [showTexto, setShowTexto] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [savingConduct, setSavingConduct] = useState(false);
  const [accepting, setAccepting] = useState(false);
  const [aceites, setAceites] = useState<{ total_aceites: number; total_usuarios_ativos: number } | null>(null);

  // Canal de Denúncias
  const [cat, setCat] = useState("ETICA");
  const [descricao, setDescricao] = useState("");
  const [anonimo, setAnonimo] = useState(true);
  const [sending, setSending] = useState(false);
  const [protocolo, setProtocolo] = useState<string | null>(null);
  const [reports, setReports] = useState<Report[]>([]);
  // Fase 241 (achado do diagnóstico de cadastros) — `resolucao` já existia
  // no backend/model, mas nenhum input do frontend permitia preenchê-la.
  const [resolucaoDrafts, setResolucaoDrafts] = useState<Record<string, string>>({});
  const [salvandoResolucaoId, setSalvandoResolucaoId] = useState<string | null>(null);

  // Matriz de Riscos (Fase 189.1)
  const [risks, setRisks] = useState<Risk[]>([]);
  const [showRiskForm, setShowRiskForm] = useState(false);
  const [riskForm, setRiskForm] = useState({ risco: "", categoria: "ETICA", probabilidade: "MEDIA", impacto: "MEDIO", controles: "" });
  const [savingRisk, setSavingRisk] = useState(false);

  // Treinamentos Obrigatórios (Fase 189.2)
  const [trainings, setTrainings] = useState<Training[]>([]);
  const [showTrainingForm, setShowTrainingForm] = useState(false);
  const [trainingForm, setTrainingForm] = useState({ titulo: "", categoria: "ETICA", conteudo: "", obrigatorio: true });
  const [savingTraining, setSavingTraining] = useState(false);
  const [completingId, setCompletingId] = useState<string | null>(null);
  const [completionsAbertas, setCompletionsAbertas] = useState<Record<string, TrainingCompletions>>({});

  // Comitê de Integridade (Fase 189.3)
  const [cases, setCases] = useState<CommitteeCase[]>([]);
  const [showCaseForm, setShowCaseForm] = useState(false);
  const [caseForm, setCaseForm] = useState<{ titulo: string; descricao: string; report_id: string; membros: string[] }>({ titulo: "", descricao: "", report_id: "", membros: [] });
  const [savingCase, setSavingCase] = useState(false);
  // Fase 241 (achado do diagnóstico de cadastros) — membros eram texto
  // livre separado por vírgula, sem checagem contra colaboradores reais.
  const [colegas, setColegas] = useState<{ id: string; full_name: string }[]>([]);

  const fetchTudo = useCallback(async () => {
    try {
      const me = await fetch("/api/v1/users/me", { headers: authH() });
      const meData = me.ok ? await me.json() : {};
      const r = meData.role || "";
      setRole(r);

      const c = await fetch("/api/v1/integrity/conduct", { headers: authH() });
      if (c.ok) setConduct(await c.json());

      const t = await fetch("/api/v1/integrity/trainings", { headers: authH() });
      if (t.ok) setTrainings(await t.json());

      if (r === "ADMIN" || r === "SUPERADMIN" || r === "SOCIO") {
        const a = await fetch("/api/v1/integrity/conduct/acceptances", { headers: authH() });
        if (a.ok) setAceites(await a.json());
        const rep = await fetch("/api/v1/integrity/reports", { headers: authH() });
        if (rep.ok) setReports(await rep.json());
        const rk = await fetch("/api/v1/integrity/risks", { headers: authH() });
        if (rk.ok) setRisks(await rk.json());
        const cs = await fetch("/api/v1/integrity/committee-cases", { headers: authH() });
        if (cs.ok) setCases(await cs.json());
        const col = await fetch("/api/v1/users/colegas", { headers: authH() });
        if (col.ok) setColegas(await col.json());
      }
    } catch { /* página segue com o que carregou */ }
  }, []);

  useEffect(() => { fetchTudo(); }, [fetchTudo]);

  async function salvarConduct() {
    setSavingConduct(true);
    try {
      const res = await fetch("/api/v1/integrity/conduct", {
        method: "PUT", headers: authH(), body: JSON.stringify({ text: draft }),
      });
      const d = await res.json().catch(() => ({}));
      if (res.ok) { setEditing(false); toast.success(`Código publicado (versão ${d.version}). Todos devem aceitar novamente.`); fetchTudo(); }
      else toast.error(d.detail || "Erro ao publicar.");
    } catch { toast.error("Falha de conexão."); }
    finally { setSavingConduct(false); }
  }

  async function aceitar() {
    setAccepting(true);
    try {
      const res = await fetch("/api/v1/integrity/conduct/accept", { method: "POST", headers: authH() });
      if (res.ok) { toast.success("Aceite registrado. Obrigado!"); fetchTudo(); }
      else { const d = await res.json().catch(() => ({})); toast.error(d.detail || "Erro ao registrar aceite."); }
    } catch { toast.error("Falha de conexão."); }
    finally { setAccepting(false); }
  }

  async function enviarRelato(e: React.FormEvent) {
    e.preventDefault();
    if (!descricao.trim()) return;
    setSending(true);
    try {
      const res = await fetch("/api/v1/integrity/reports", {
        method: "POST", headers: authH(),
        body: JSON.stringify({ categoria: cat, descricao, anonimo }),
      });
      const d = await res.json().catch(() => ({}));
      if (res.ok) { setProtocolo(d.protocolo); setDescricao(""); if (isGestor) fetchTudo(); }
      else toast.error(d.detail || "Erro ao enviar o relato.");
    } catch { toast.error("Falha de conexão."); }
    finally { setSending(false); }
  }

  async function mudarStatus(id: string, status: string) {
    try {
      const res = await fetch(`/api/v1/integrity/reports/${id}`, {
        method: "PUT", headers: authH(), body: JSON.stringify({ status }),
      });
      if (res.ok) fetchTudo();
      else toast.error("Erro ao atualizar o relato.");
    } catch { toast.error("Falha de conexão."); }
  }

  async function salvarResolucao(id: string) {
    const resolucao = (resolucaoDrafts[id] ?? "").trim();
    setSalvandoResolucaoId(id);
    try {
      const res = await fetch(`/api/v1/integrity/reports/${id}`, {
        method: "PUT", headers: authH(), body: JSON.stringify({ resolucao }),
      });
      if (res.ok) { toast.success("Resolução salva."); fetchTudo(); }
      else toast.error("Erro ao salvar a resolução.");
    } catch { toast.error("Falha de conexão."); }
    finally { setSalvandoResolucaoId(null); }
  }

  // Fase 208.3 — pré-preenche o formulário da Matriz de Riscos a partir de um
  // relato, mas NUNCA cria o risco sozinho: o staff ainda revisa/completa os
  // controles e confirma via "Registrar risco" (mesmo POST manual de sempre).
  async function sugerirRisco(reportId: string) {
    try {
      const res = await fetch(`/api/v1/integrity/reports/${reportId}/suggest-risk`, { headers: authH() });
      if (!res.ok) { toast.error("Erro ao gerar sugestão de risco."); return; }
      const d = await res.json();
      setRiskForm({ risco: d.risco, categoria: d.categoria, probabilidade: d.probabilidade, impacto: d.impacto, controles: "" });
      setShowRiskForm(true);
      if (d.risco_existente_id) {
        toast.warning("Já existe um risco ativo dessa categoria na matriz — revise antes de criar outro.");
      } else {
        toast.success("Sugestão pré-preenchida — revise e complete os controles antes de salvar.");
      }
    } catch { toast.error("Falha de conexão."); }
  }

  const STATUS_BADGE: Record<string, string> = {
    ABERTO: "bg-red-50 text-red-700 border-red-200",
    EM_ANALISE: "bg-amber-50 text-amber-700 border-amber-200",
    RESOLVIDO: "bg-green-50 text-green-700 border-green-200",
  };

  // ── Matriz de Riscos ──
  async function criarRisco(e: React.FormEvent) {
    e.preventDefault();
    if (!riskForm.risco.trim() || !riskForm.controles.trim()) return;
    setSavingRisk(true);
    try {
      const res = await fetch("/api/v1/integrity/risks", {
        method: "POST", headers: authH(), body: JSON.stringify(riskForm),
      });
      const d = await res.json().catch(() => ({}));
      if (res.ok) {
        toast.success("Risco registrado na matriz.");
        setShowRiskForm(false);
        setRiskForm({ risco: "", categoria: "ETICA", probabilidade: "MEDIA", impacto: "MEDIO", controles: "" });
        fetchTudo();
      } else toast.error(d.detail || "Erro ao registrar o risco.");
    } catch { toast.error("Falha de conexão."); }
    finally { setSavingRisk(false); }
  }

  async function atualizarRisco(id: string, body: Record<string, unknown>) {
    try {
      const res = await fetch(`/api/v1/integrity/risks/${id}`, {
        method: "PUT", headers: authH(), body: JSON.stringify(body),
      });
      if (res.ok) fetchTudo();
      else toast.error("Erro ao atualizar o risco.");
    } catch { toast.error("Falha de conexão."); }
  }

  // ── Treinamentos Obrigatórios ──
  async function criarTreinamento(e: React.FormEvent) {
    e.preventDefault();
    if (!trainingForm.titulo.trim() || !trainingForm.conteudo.trim()) return;
    setSavingTraining(true);
    try {
      const res = await fetch("/api/v1/integrity/trainings", {
        method: "POST", headers: authH(), body: JSON.stringify(trainingForm),
      });
      const d = await res.json().catch(() => ({}));
      if (res.ok) {
        toast.success("Trilha de treinamento criada.");
        setShowTrainingForm(false);
        setTrainingForm({ titulo: "", categoria: "ETICA", conteudo: "", obrigatorio: true });
        fetchTudo();
      } else toast.error(d.detail || "Erro ao criar a trilha.");
    } catch { toast.error("Falha de conexão."); }
    finally { setSavingTraining(false); }
  }

  async function concluirTreinamento(id: string) {
    setCompletingId(id);
    try {
      const res = await fetch(`/api/v1/integrity/trainings/${id}/complete`, { method: "POST", headers: authH() });
      if (res.ok) { toast.success("Conclusão registrada."); fetchTudo(); }
      else toast.error("Erro ao registrar a conclusão.");
    } catch { toast.error("Falha de conexão."); }
    finally { setCompletingId(null); }
  }

  async function alternarConclusoes(id: string) {
    if (completionsAbertas[id]) {
      setCompletionsAbertas((prev) => { const next = { ...prev }; delete next[id]; return next; });
      return;
    }
    try {
      const res = await fetch(`/api/v1/integrity/trainings/${id}/completions`, { headers: authH() });
      if (res.ok) { const d = await res.json(); setCompletionsAbertas((prev) => ({ ...prev, [id]: d })); }
      else toast.error("Erro ao carregar as conclusões.");
    } catch { toast.error("Falha de conexão."); }
  }

  // ── Comitê de Integridade ──
  async function criarCaso(e: React.FormEvent) {
    e.preventDefault();
    if (!caseForm.titulo.trim() || !caseForm.descricao.trim()) return;
    setSavingCase(true);
    try {
      const res = await fetch("/api/v1/integrity/committee-cases", {
        method: "POST", headers: authH(),
        body: JSON.stringify({
          titulo: caseForm.titulo, descricao: caseForm.descricao,
          report_id: caseForm.report_id || null,
          membros: caseForm.membros,
        }),
      });
      const d = await res.json().catch(() => ({}));
      if (res.ok) {
        toast.success("Caso registrado no Comitê.");
        setShowCaseForm(false);
        setCaseForm({ titulo: "", descricao: "", report_id: "", membros: [] });
        fetchTudo();
      } else toast.error(d.detail || "Erro ao registrar o caso.");
    } catch { toast.error("Falha de conexão."); }
    finally { setSavingCase(false); }
  }

  async function decidirCaso(id: string, decisao: string) {
    try {
      const res = await fetch(`/api/v1/integrity/committee-cases/${id}`, {
        method: "PUT", headers: authH(), body: JSON.stringify({ status: "DECIDIDO", decisao }),
      });
      if (res.ok) { toast.success("Decisão registrada."); fetchTudo(); }
      else toast.error("Erro ao registrar a decisão.");
    } catch { toast.error("Falha de conexão."); }
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Ética & Integridade" }]} />

      <div className="afj-page-header">
        <div>
          <h1 className="afj-page-title flex items-center gap-2">
            <ShieldCheck size={22} className="text-afj-gold" /> Plano de Ética, Controle e Integridade
          </h1>
          <p className="text-afj-black/45 text-sm mt-1">
            Controles ativos, Código de Conduta com aceite registrado e Canal de Denúncias confidencial.
          </p>
        </div>
      </div>

      {/* ── Código de Conduta ── */}
      <div className="afj-card p-5 space-y-4">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <h2 className="font-semibold text-sm text-afj-black flex items-center gap-2">
            <BookOpenCheck size={16} className="text-afj-gold" /> Código de Conduta
            {conduct && conduct.version > 0 && (
              <span className="text-[10px] uppercase tracking-wider text-afj-black/35">versão {conduct.version}</span>
            )}
          </h2>
          <div className="flex items-center gap-2">
            {isGestor && aceites && conduct && conduct.version > 0 && (
              <span className="text-xs text-afj-black/50">
                {aceites.total_aceites}/{aceites.total_usuarios_ativos} aceitaram
              </span>
            )}
            {role === "ADMIN" && !editing && (
              <button onClick={() => { setDraft(conduct?.text || ""); setEditing(true); }}
                className="btn-afj-outline text-xs py-1.5 px-3 rounded-sm flex items-center gap-1.5">
                <Pencil size={12} /> {conduct && conduct.version > 0 ? "Editar" : "Publicar código"}
              </button>
            )}
          </div>
        </div>

        {editing ? (
          <div className="space-y-3">
            <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={12}
              placeholder={"1. COMPROMISSO ÉTICO\nTodos os integrantes do escritório se comprometem a...\n\n2. CONFLITOS DE INTERESSE\n...\n\n3. USO RESPONSÁVEL DE IA\n..."}
              className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm font-mono focus:outline-none focus:border-afj-gold resize-none" />
            <p className="text-[11px] text-afj-black/40">Publicar incrementa a versão — todos os usuários precisarão aceitar novamente.</p>
            <div className="flex gap-2">
              <button onClick={salvarConduct} disabled={savingConduct || !draft.trim()}
                className="btn-afj-primary rounded-sm text-sm flex items-center gap-2 disabled:opacity-50">
                {savingConduct && <Loader2 size={13} className="animate-spin" />} Publicar
              </button>
              <button onClick={() => setEditing(false)} className="btn-afj-outline rounded-sm text-sm">Cancelar</button>
            </div>
          </div>
        ) : conduct && conduct.version > 0 ? (
          <div className="space-y-3">
            {conduct.accepted ? (
              <div className="flex items-center gap-2 text-xs text-green-700 bg-green-50 border border-green-200 rounded-sm px-3 py-2.5">
                <CheckCircle2 size={14} /> Você aceitou esta versão em {conduct.accepted_at ? new Date(conduct.accepted_at).toLocaleDateString("pt-BR") : "—"}.
              </div>
            ) : (
              <div className="flex items-center justify-between gap-3 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-sm px-3 py-2.5 flex-wrap">
                <span className="flex items-center gap-2"><AlertTriangle size={14} /> Você ainda não aceitou a versão vigente.</span>
                <button onClick={aceitar} disabled={accepting}
                  className="btn-afj-primary text-xs py-1.5 px-3 rounded-sm flex items-center gap-1.5 disabled:opacity-50">
                  {accepting && <Loader2 size={12} className="animate-spin" />} Li e aceito
                </button>
              </div>
            )}
            <button onClick={() => setShowTexto((v) => !v)}
              className="w-full flex items-center justify-between text-left text-xs text-afj-black/60 border border-afj-cream-dark rounded-sm px-3 py-2 hover:bg-afj-cream/40 transition-colors">
              <span>{showTexto ? "Ocultar texto do código" : "Ler o Código de Conduta"}</span>
              <ChevronDown size={14} className={`transition-transform ${showTexto ? "rotate-180" : ""}`} />
            </button>
            {showTexto && (
              <pre className="whitespace-pre-wrap text-xs text-afj-black/70 bg-afj-cream/50 border border-afj-cream-dark rounded-sm p-4 leading-relaxed font-sans">
                {conduct.text}
              </pre>
            )}
          </div>
        ) : (
          <p className="text-xs text-afj-black/45">
            Nenhum Código de Conduta publicado ainda{role === "ADMIN" ? " — clique em “Publicar código” para criar o primeiro." : ". Aguarde a publicação pelo administrador."}
          </p>
        )}
      </div>

      {/* ── Canal de Denúncias ── */}
      <div className="afj-card p-5 space-y-4">
        <h2 className="font-semibold text-sm text-afj-black flex items-center gap-2">
          <Megaphone size={16} className="text-afj-gold" /> Canal de Denúncias
        </h2>
        <p className="text-xs text-afj-black/50 -mt-2">
          Relate violações éticas com confidencialidade. No modo anônimo, sua identidade <strong>não é gravada</strong> no sistema.
        </p>

        {protocolo ? (
          <div className="bg-green-50 border border-green-200 rounded-sm p-4 text-center space-y-2">
            <CheckCircle2 size={22} className="mx-auto text-green-600" />
            <p className="text-sm font-semibold text-green-800">Relato registrado</p>
            <p className="text-xs text-green-700">Protocolo: <span className="font-mono font-bold">{protocolo}</span> — guarde para referência.</p>
            <button onClick={() => setProtocolo(null)} className="text-xs text-afj-gold hover:underline">Enviar outro relato</button>
          </div>
        ) : (
          <form onSubmit={enviarRelato} className="space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-[10px] font-semibold text-afj-black/55 uppercase tracking-widest block mb-1.5">Categoria</label>
                <select value={cat} onChange={(e) => setCat(e.target.value)}
                  className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-3 py-2.5 text-sm focus:outline-none focus:border-afj-gold">
                  {CATEGORIAS.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                </select>
              </div>
              <label className="flex items-end gap-2.5 cursor-pointer pb-2.5">
                <input type="checkbox" checked={anonimo} onChange={(e) => setAnonimo(e.target.checked)} className="accent-afj-gold w-4 h-4" />
                <span className="text-sm text-afj-black/75">Enviar anonimamente</span>
              </label>
            </div>
            <div>
              <label className="text-[10px] font-semibold text-afj-black/55 uppercase tracking-widest block mb-1.5">Descrição do relato</label>
              <textarea value={descricao} onChange={(e) => setDescricao(e.target.value)} rows={4} required
                placeholder="Descreva a situação com o máximo de detalhes (o quê, quando, envolvidos)..."
                className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-3 py-2.5 text-sm placeholder:text-afj-black/25 focus:outline-none focus:border-afj-gold resize-none" />
            </div>
            <button type="submit" disabled={sending || !descricao.trim()}
              className="btn-afj-primary rounded-sm text-sm flex items-center gap-2 disabled:opacity-50">
              {sending ? <Loader2 size={13} className="animate-spin" /> : <Send size={13} />} Enviar relato
            </button>
          </form>
        )}

        {/* Gestão (ADMIN/SÓCIO) */}
        {isGestor && reports.length > 0 && (
          <div className="border-t border-afj-cream-dark pt-4 space-y-2.5">
            <p className="text-[10px] font-semibold text-afj-black/55 uppercase tracking-widest">Relatos recebidos ({reports.length})</p>
            {reports.map((r) => (
              <div key={r.id} className="border border-afj-cream-dark rounded-sm p-3 space-y-2">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <span className="text-xs font-semibold text-afj-black">
                    {CATEGORIAS.find((c) => c.value === r.categoria)?.label || r.categoria}
                    {r.anonimo && <span className="ml-2 text-[10px] text-afj-black/35 uppercase">anônimo</span>}
                  </span>
                  <div className="flex items-center gap-2">
                    <span className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-sm border ${STATUS_BADGE[r.status] || ""}`}>
                      {r.status.replace("_", " ")}
                    </span>
                    <select value={r.status} onChange={(e) => mudarStatus(r.id, e.target.value)}
                      className="text-[11px] border border-afj-cream-dark rounded-sm px-1.5 py-1 bg-white focus:outline-none focus:border-afj-gold">
                      <option value="ABERTO">Aberto</option>
                      <option value="EM_ANALISE">Em análise</option>
                      <option value="RESOLVIDO">Resolvido</option>
                    </select>
                  </div>
                </div>
                <p className="text-xs text-afj-black/60 leading-relaxed">{r.descricao}</p>
                <div>
                  <label className="text-[10px] font-semibold text-afj-black/45 uppercase tracking-wider block mb-1">Resolução / parecer</label>
                  <textarea
                    rows={2}
                    value={resolucaoDrafts[r.id] ?? r.resolucao ?? ""}
                    onChange={(e) => setResolucaoDrafts((d) => ({ ...d, [r.id]: e.target.value }))}
                    placeholder="Registre a apuração/decisão sobre este relato..."
                    className="w-full border border-afj-cream-dark rounded-sm px-2.5 py-1.5 text-xs focus:outline-none focus:border-afj-gold"
                  />
                  {(resolucaoDrafts[r.id] ?? "") !== (r.resolucao ?? "") && (
                    <button
                      onClick={() => salvarResolucao(r.id)}
                      disabled={salvandoResolucaoId === r.id}
                      className="mt-1 text-[10px] font-medium text-afj-gold hover:underline disabled:opacity-50"
                    >
                      {salvandoResolucaoId === r.id ? "Salvando..." : "Salvar resolução"}
                    </button>
                  )}
                </div>
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <p className="text-[10px] text-afj-black/35">
                    Protocolo {r.id.slice(0, 8).toUpperCase()} · {new Date(r.created_at).toLocaleString("pt-BR")}
                  </p>
                  <button onClick={() => sugerirRisco(r.id)} className="text-[10px] font-medium text-afj-gold hover:underline">
                    Sugerir risco a partir desta denúncia
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Pilares técnicos ativos */}
      <div>
        <h2 className="afj-section-header flex items-center gap-2">
          <CheckCircle2 size={15} className="text-green-600" /> Controles técnicos em operação
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
          {PILARES_ATIVOS.map((p) => {
            const Icon = p.icon;
            return (
              <div key={p.titulo} className="afj-card p-4 border-l-2 border-green-400/60">
                <p className="font-semibold text-afj-black text-sm flex items-center gap-2">
                  <Icon size={15} className="text-afj-gold" /> {p.titulo}
                </p>
                <p className="text-xs text-afj-black/55 mt-1.5 leading-relaxed">{p.desc}</p>
              </div>
            );
          })}
        </div>
      </div>

      {/* Próximos passos do programa — Fase 189: deixam de ser cards estáticos */}
      <div>
        <h2 className="afj-section-header flex items-center gap-2">
          <Clock size={15} className="text-afj-gold" /> Próximos passos do programa
        </h2>
      </div>

      {/* ── Matriz de Riscos de Integridade (gestor) ── */}
      {isGestor && (
        <div className="afj-card p-5 space-y-4">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <h2 className="font-semibold text-sm text-afj-black flex items-center gap-2">
              <AlertTriangle size={16} className="text-afj-gold" /> Matriz de Riscos de Integridade
            </h2>
            <button onClick={() => setShowRiskForm((v) => !v)} className="btn-afj-outline text-xs py-1.5 px-3 rounded-sm">
              {showRiskForm ? "Cancelar" : "Novo risco"}
            </button>
          </div>

          {showRiskForm && (
            <form onSubmit={criarRisco} className="space-y-3 border-b border-afj-cream-dark pb-4">
              <input type="text" value={riskForm.risco} onChange={(e) => setRiskForm((f) => ({ ...f, risco: e.target.value }))}
                placeholder="Descreva o risco (ex.: conflito de interesse não declarado)" required
                className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold" />
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <select value={riskForm.categoria} onChange={(e) => setRiskForm((f) => ({ ...f, categoria: e.target.value }))}
                  className="bg-afj-cream border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold">
                  {CATEGORIAS.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                </select>
                <select value={riskForm.probabilidade} onChange={(e) => setRiskForm((f) => ({ ...f, probabilidade: e.target.value }))}
                  className="bg-afj-cream border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold">
                  {PROBABILIDADES.map((p) => <option key={p} value={p}>Probabilidade {p.toLowerCase()}</option>)}
                </select>
                <select value={riskForm.impacto} onChange={(e) => setRiskForm((f) => ({ ...f, impacto: e.target.value }))}
                  className="bg-afj-cream border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold">
                  {IMPACTOS.map((p) => <option key={p} value={p}>Impacto {p.toLowerCase()}</option>)}
                </select>
              </div>
              <textarea value={riskForm.controles} onChange={(e) => setRiskForm((f) => ({ ...f, controles: e.target.value }))}
                rows={2} placeholder="Controles adotados para mitigar este risco" required
                className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold resize-none" />
              <button type="submit" disabled={savingRisk} className="btn-afj-primary rounded-sm text-sm flex items-center gap-2 disabled:opacity-50">
                {savingRisk && <Loader2 size={13} className="animate-spin" />} Registrar risco
              </button>
            </form>
          )}

          {risks.length === 0 ? (
            <p className="text-xs text-afj-black/45">Nenhum risco mapeado ainda.</p>
          ) : (
            <div className="space-y-2.5">
              {risks.map((r) => (
                <div key={r.id} className="border border-afj-cream-dark rounded-sm p-3 space-y-1.5">
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <span className="text-xs font-semibold text-afj-black">{r.risco}</span>
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded-sm border bg-afj-cream border-afj-cream-dark text-afj-black/50">
                        Prob. {r.probabilidade.toLowerCase()}
                      </span>
                      <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded-sm border bg-afj-cream border-afj-cream-dark text-afj-black/50">
                        Impacto {r.impacto.toLowerCase()}
                      </span>
                      <select value={r.status} onChange={(e) => atualizarRisco(r.id, { status: e.target.value })}
                        className="text-[11px] border border-afj-cream-dark rounded-sm px-1.5 py-1 bg-white focus:outline-none focus:border-afj-gold">
                        <option value="ATIVO">Ativo</option>
                        <option value="MITIGADO">Mitigado</option>
                        <option value="ENCERRADO">Encerrado</option>
                      </select>
                    </div>
                  </div>
                  <p className="text-xs text-afj-black/55 leading-relaxed">{r.controles}</p>
                  <div className="flex items-center justify-between gap-2 flex-wrap text-[10px] text-afj-black/35">
                    <span>{r.responsavel_nome ? `Responsável: ${r.responsavel_nome}` : "Sem responsável definido"}</span>
                    <button onClick={() => atualizarRisco(r.id, { marcar_revisado: true })} className="text-afj-gold hover:underline">
                      {r.ultima_revisao_em ? `Revisado em ${new Date(r.ultima_revisao_em).toLocaleDateString("pt-BR")} — revisar agora` : "Marcar como revisado"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Treinamentos Obrigatórios ── */}
      <div className="afj-card p-5 space-y-4">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <h2 className="font-semibold text-sm text-afj-black flex items-center gap-2">
            <GraduationCap size={16} className="text-afj-gold" /> Treinamentos Obrigatórios
          </h2>
          {isGestor && (
            <button onClick={() => setShowTrainingForm((v) => !v)} className="btn-afj-outline text-xs py-1.5 px-3 rounded-sm">
              {showTrainingForm ? "Cancelar" : "Nova trilha"}
            </button>
          )}
        </div>

        {isGestor && showTrainingForm && (
          <form onSubmit={criarTreinamento} className="space-y-3 border-b border-afj-cream-dark pb-4">
            <input type="text" value={trainingForm.titulo} onChange={(e) => setTrainingForm((f) => ({ ...f, titulo: e.target.value }))}
              placeholder="Título da trilha (ex.: Uso responsável de IA no escritório)" required
              className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold" />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <select value={trainingForm.categoria} onChange={(e) => setTrainingForm((f) => ({ ...f, categoria: e.target.value }))}
                className="bg-afj-cream border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold">
                {CATEGORIAS_TREINAMENTO.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
              <label className="flex items-center gap-2.5 cursor-pointer">
                <input type="checkbox" checked={trainingForm.obrigatorio}
                  onChange={(e) => setTrainingForm((f) => ({ ...f, obrigatorio: e.target.checked }))}
                  className="accent-afj-gold w-4 h-4" />
                <span className="text-sm text-afj-black/75">Obrigatório para toda a equipe</span>
              </label>
            </div>
            <textarea value={trainingForm.conteudo} onChange={(e) => setTrainingForm((f) => ({ ...f, conteudo: e.target.value }))}
              rows={4} placeholder="Conteúdo da trilha" required
              className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold resize-none" />
            <button type="submit" disabled={savingTraining} className="btn-afj-primary rounded-sm text-sm flex items-center gap-2 disabled:opacity-50">
              {savingTraining && <Loader2 size={13} className="animate-spin" />} Criar trilha
            </button>
          </form>
        )}

        {trainings.length === 0 ? (
          <p className="text-xs text-afj-black/45">Nenhuma trilha publicada ainda.</p>
        ) : (
          <div className="space-y-2.5">
            {trainings.map((t) => (
              <div key={t.id} className="border border-afj-cream-dark rounded-sm p-3 space-y-2">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <span className="text-xs font-semibold text-afj-black flex items-center gap-2">
                    {t.titulo}
                    <span className="text-[10px] uppercase tracking-wider text-afj-black/35">
                      {CATEGORIAS_TREINAMENTO.find((c) => c.value === t.categoria)?.label || t.categoria}
                    </span>
                    {t.obrigatorio && <span className="text-[10px] uppercase tracking-wider text-red-500/70">Obrigatório</span>}
                  </span>
                  {t.concluido ? (
                    <span className="text-[10px] flex items-center gap-1 text-green-700 uppercase tracking-wider">
                      <CheckCircle2 size={11} /> Concluído
                    </span>
                  ) : (
                    <button onClick={() => concluirTreinamento(t.id)} disabled={completingId === t.id}
                      className="btn-afj-primary text-xs py-1 px-2.5 rounded-sm flex items-center gap-1.5 disabled:opacity-50">
                      {completingId === t.id && <Loader2 size={11} className="animate-spin" />} Marcar concluído
                    </button>
                  )}
                </div>
                <p className="text-xs text-afj-black/55 leading-relaxed">{t.conteudo}</p>
                {isGestor && (
                  <div>
                    <button onClick={() => alternarConclusoes(t.id)} className="text-[11px] text-afj-gold hover:underline">
                      {completionsAbertas[t.id] ? "Ocultar conclusões" : "Ver quem já concluiu"}
                    </button>
                    {completionsAbertas[t.id] && (
                      <p className="text-[11px] text-afj-black/45 mt-1">
                        {completionsAbertas[t.id].total_concluintes}/{completionsAbertas[t.id].total_usuarios_ativos} da equipe concluíram
                        {completionsAbertas[t.id].concluintes.length > 0 && (
                          <> — {completionsAbertas[t.id].concluintes.map((c) => c.nome).join(", ")}</>
                        )}
                      </p>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Comitê de Integridade (gestor) ── */}
      {isGestor && (
        <div className="afj-card p-5 space-y-4">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <h2 className="font-semibold text-sm text-afj-black flex items-center gap-2">
              <Users2 size={16} className="text-afj-gold" /> Comitê de Integridade
            </h2>
            <button onClick={() => setShowCaseForm((v) => !v)} className="btn-afj-outline text-xs py-1.5 px-3 rounded-sm">
              {showCaseForm ? "Cancelar" : "Novo caso"}
            </button>
          </div>

          {showCaseForm && (
            <form onSubmit={criarCaso} className="space-y-3 border-b border-afj-cream-dark pb-4">
              <input type="text" value={caseForm.titulo} onChange={(e) => setCaseForm((f) => ({ ...f, titulo: e.target.value }))}
                placeholder="Título do caso ou deliberação" required
                className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold" />
              {reports.length > 0 && (
                <select value={caseForm.report_id} onChange={(e) => setCaseForm((f) => ({ ...f, report_id: e.target.value }))}
                  className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold">
                  <option value="">Deliberação de política (sem relato vinculado)</option>
                  {reports.map((r) => (
                    <option key={r.id} value={r.id}>
                      Relato {r.id.slice(0, 8).toUpperCase()} — {CATEGORIAS.find((c) => c.value === r.categoria)?.label || r.categoria}
                    </option>
                  ))}
                </select>
              )}
              <textarea value={caseForm.descricao} onChange={(e) => setCaseForm((f) => ({ ...f, descricao: e.target.value }))}
                rows={3} placeholder="Descrição do caso a ser avaliado" required
                className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold resize-none" />
              <div>
                <label className="text-xs text-afj-black/60 block mb-1">Membros participantes</label>
                {colegas.length > 0 ? (
                  <div className="border border-afj-cream-dark rounded-sm px-3 py-2 max-h-32 overflow-y-auto space-y-1 bg-afj-cream">
                    {colegas.map((c) => (
                      <label key={c.id} className="flex items-center gap-2 text-sm text-afj-black/70 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={caseForm.membros.includes(c.full_name)}
                          onChange={(e) => setCaseForm((f) => ({
                            ...f,
                            membros: e.target.checked
                              ? [...f.membros, c.full_name]
                              : f.membros.filter((m) => m !== c.full_name),
                          }))}
                        />
                        {c.full_name}
                      </label>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-afj-black/40">Nenhum colaborador disponível.</p>
                )}
              </div>
              <button type="submit" disabled={savingCase} className="btn-afj-primary rounded-sm text-sm flex items-center gap-2 disabled:opacity-50">
                {savingCase && <Loader2 size={13} className="animate-spin" />} Registrar caso
              </button>
            </form>
          )}

          {cases.length === 0 ? (
            <p className="text-xs text-afj-black/45">Nenhum caso registrado ainda.</p>
          ) : (
            <div className="space-y-2.5">
              {cases.map((c) => (
                <CommitteeCaseCard key={c.id} case_={c} onDecidir={decidirCaso} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function CommitteeCaseCard({ case_, onDecidir }: { case_: CommitteeCase; onDecidir: (id: string, decisao: string) => void }) {
  const [decisao, setDecisao] = useState(case_.decisao || "");
  const decidido = case_.status === "DECIDIDO";
  return (
    <div className="border border-afj-cream-dark rounded-sm p-3 space-y-2">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <span className="text-xs font-semibold text-afj-black">{case_.titulo}</span>
        <span className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-sm border ${
          decidido ? "bg-green-50 text-green-700 border-green-200" : "bg-amber-50 text-amber-700 border-amber-200"
        }`}>
          {decidido ? "Decidido" : "Em análise"}
        </span>
      </div>
      <p className="text-xs text-afj-black/55 leading-relaxed">{case_.descricao}</p>
      {case_.membros.length > 0 && (
        <p className="text-[10px] text-afj-black/35">Membros: {case_.membros.join(", ")}</p>
      )}
      {decidido ? (
        <p className="text-xs text-afj-black/70 bg-afj-cream/50 border border-afj-cream-dark rounded-sm px-2.5 py-1.5">
          <strong>Decisão:</strong> {case_.decisao}
        </p>
      ) : (
        <div className="flex items-center gap-2">
          <input type="text" value={decisao} onChange={(e) => setDecisao(e.target.value)}
            placeholder="Registrar a decisão do comitê..."
            className="flex-1 border border-afj-cream-dark rounded-sm px-2.5 py-1.5 text-xs focus:outline-none focus:border-afj-gold" />
          <button onClick={() => decisao.trim() && onDecidir(case_.id, decisao.trim())}
            className="btn-afj-outline text-xs py-1.5 px-3 rounded-sm flex-shrink-0">
            Decidir
          </button>
        </div>
      )}
    </div>
  );
}
