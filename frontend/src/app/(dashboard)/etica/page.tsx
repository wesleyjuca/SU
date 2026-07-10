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

const PROGRAMA_PLANEJADO = [
  { icon: AlertTriangle, titulo: "Matriz de Riscos de Integridade", desc: "Mapeamento periódico de riscos com controles e responsáveis." },
  { icon: GraduationCap, titulo: "Treinamentos Obrigatórios", desc: "Trilhas de ética, LGPD e uso responsável de IA com registro de conclusão." },
  { icon: Users2, titulo: "Comitê de Integridade", desc: "Instância que avalia casos, aprova políticas e reporta à sociedade." },
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

  const fetchTudo = useCallback(async () => {
    try {
      const me = await fetch("/api/v1/users/me", { headers: authH() });
      const meData = me.ok ? await me.json() : {};
      const r = meData.role || "";
      setRole(r);

      const c = await fetch("/api/v1/integrity/conduct", { headers: authH() });
      if (c.ok) setConduct(await c.json());

      if (r === "ADMIN" || r === "SUPERADMIN" || r === "SOCIO") {
        const a = await fetch("/api/v1/integrity/conduct/acceptances", { headers: authH() });
        if (a.ok) setAceites(await a.json());
        const rep = await fetch("/api/v1/integrity/reports", { headers: authH() });
        if (rep.ok) setReports(await rep.json());
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

  const STATUS_BADGE: Record<string, string> = {
    ABERTO: "bg-red-50 text-red-700 border-red-200",
    EM_ANALISE: "bg-amber-50 text-amber-700 border-amber-200",
    RESOLVIDO: "bg-green-50 text-green-700 border-green-200",
  };

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
                <p className="text-[10px] text-afj-black/35">
                  Protocolo {r.id.slice(0, 8).toUpperCase()} · {new Date(r.created_at).toLocaleString("pt-BR")}
                </p>
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

      {/* Próximos passos do programa */}
      <div>
        <h2 className="afj-section-header flex items-center gap-2">
          <Clock size={15} className="text-afj-gold" /> Próximos passos do programa
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
          {PROGRAMA_PLANEJADO.map((p) => {
            const Icon = p.icon;
            return (
              <div key={p.titulo} className="afj-card p-4 border-l-2 border-afj-gold/40">
                <p className="font-semibold text-afj-black text-sm flex items-center gap-2">
                  <Icon size={15} className="text-afj-gold" /> {p.titulo}
                  <span className="text-[10px] uppercase tracking-wider text-afj-black/35 font-normal">Planejado</span>
                </p>
                <p className="text-xs text-afj-black/55 mt-1.5 leading-relaxed">{p.desc}</p>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
