"use client";
import { useState, useEffect } from "react";
import { Filter, Plus, X, Loader2, Trash2, TrendingUp, Target, Pencil } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { useToast } from "@/components/ui/Toast";
import { useUserStore } from "@/store";

interface Opp {
  id: string; titulo: string; valor_estimado: number; estagio: string; probabilidade: number;
  cliente: string | null; client_id: string | null; origem: string | null; expected_close: string | null; motivo_perda: string | null;
}
interface Funil {
  estagios: string[];
  colunas: Record<string, Opp[]>;
  totais: Record<string, { count: number; valor: number }>;
  truncado: Record<string, boolean>;
  forecast: number; pipeline_aberto: number; abertas: number;
}
interface Cliente { id: string; nome_completo: string }
interface Meta { id: string; periodo: string; tipo: string; valor_meta: number; realizado: number; percentual: number | null }

const PERIODO_ATUAL = (() => {
  const hoje = new Date();
  return `${hoje.getFullYear()}-${String(hoje.getMonth() + 1).padStart(2, "0")}`;
})();

const LABEL: Record<string, string> = {
  LEAD: "Lead", QUALIFICACAO: "Qualificação", PROPOSTA: "Proposta",
  NEGOCIACAO: "Negociação", GANHO: "Ganho", PERDIDO: "Perdido",
};
const COL_STYLE: Record<string, string> = {
  LEAD: "border-t-gray-400", QUALIFICACAO: "border-t-blue-400", PROPOSTA: "border-t-afj-gold",
  NEGOCIACAO: "border-t-amber-500", GANHO: "border-t-green-500", PERDIDO: "border-t-red-400",
};

function authH(): HeadersInit {
  const t = typeof window !== "undefined" ? localStorage.getItem("afj_access_token") : null;
  return { "Content-Type": "application/json", Authorization: `Bearer ${t}` };
}
const fmtBRL = (v: number) => `R$ ${v.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`;

export default function FunilPage() {
  const toast = useToast();
  const userRole = useUserStore((s) => s.user?.role);
  const canDefinirMeta = ["ADMIN", "SOCIO", "GESTOR"].includes(userRole ?? "");
  const [funil, setFunil] = useState<Funil | null>(null);
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [modal, setModal] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ titulo: "", valor_estimado: "", estagio: "LEAD", probabilidade: "50", client_id: "", origem: "", expected_close: "" });

  const [meta, setMeta] = useState<Meta | null>(null);
  const [editingMeta, setEditingMeta] = useState(false);
  const [metaValor, setMetaValor] = useState("");
  const [savingMeta, setSavingMeta] = useState(false);

  useEffect(() => { fetchFunil(); fetchClientes(); fetchMeta(); }, []);

  async function fetchMeta() {
    try {
      const res = await fetch(`/api/v1/crm/metas?periodo=${PERIODO_ATUAL}`, { headers: authH() });
      if (res.ok) {
        const metas: Meta[] = await res.json();
        setMeta(metas.find((m) => m.tipo === "RECEITA") ?? null);
      }
    } catch { /* silencioso — widget opcional */ }
  }

  async function salvarMeta(e: React.FormEvent) {
    e.preventDefault();
    const valor = Number(metaValor);
    if (!valor || valor <= 0) return;
    setSavingMeta(true);
    try {
      const res = await fetch("/api/v1/crm/metas", {
        method: "POST", headers: authH(),
        body: JSON.stringify({ periodo: PERIODO_ATUAL, tipo: "RECEITA", valor_meta: valor }),
      });
      if (res.ok) { setEditingMeta(false); setMetaValor(""); fetchMeta(); }
      else toast.error("Erro ao salvar meta.");
    } catch { toast.error("Falha de conexão."); }
    finally { setSavingMeta(false); }
  }

  async function fetchFunil() {
    setLoading(true);
    try {
      const res = await fetch("/api/v1/crm/funil", { headers: authH() });
      if (res.ok) setFunil(await res.json());
    } catch { toast.error("Falha ao carregar o funil."); }
    finally { setLoading(false); }
  }
  async function fetchClientes() {
    try {
      const res = await fetch("/api/v1/clients?limit=200", { headers: authH() });
      if (res.ok) { const d = await res.json(); setClientes(Array.isArray(d) ? d : d.items ?? []); }
    } catch {}
  }

  async function criar(e: React.FormEvent) {
    e.preventDefault();
    if (!form.titulo.trim()) { toast.error("Informe o título."); return; }
    setSaving(true);
    try {
      const res = await fetch("/api/v1/crm/opportunities", {
        method: "POST", headers: authH(),
        body: JSON.stringify({
          titulo: form.titulo,
          valor_estimado: parseFloat(form.valor_estimado) || 0,
          estagio: form.estagio,
          probabilidade: parseInt(form.probabilidade) || 0,
          client_id: form.client_id || undefined,
          origem: form.origem || undefined,
          expected_close: form.expected_close || undefined,
        }),
      });
      if (res.ok) {
        toast.success("Oportunidade criada.");
        setModal(false); setForm({ titulo: "", valor_estimado: "", estagio: "LEAD", probabilidade: "50", client_id: "", origem: "", expected_close: "" });
        fetchFunil();
      } else { const d = await res.json(); toast.error(d.detail || "Erro ao criar."); }
    } catch { toast.error("Falha de conexão."); }
    finally { setSaving(false); }
  }

  async function mover(opp: Opp, estagio: string) {
    let body: Record<string, unknown> = { estagio };
    if (estagio === "PERDIDO") {
      const motivo = window.prompt("Motivo da perda:");
      if (!motivo) return;
      body.motivo_perda = motivo;
    }
    setBusy(opp.id);
    try {
      const res = await fetch(`/api/v1/crm/opportunities/${opp.id}`, { method: "PATCH", headers: authH(), body: JSON.stringify(body) });
      if (res.ok) { fetchFunil(); if (estagio === "GANHO") toast.success("Negócio ganho! 🎉"); }
      else { const d = await res.json(); toast.error(d.detail || "Erro ao mover."); }
    } catch { toast.error("Falha de conexão."); }
    finally { setBusy(null); }
  }

  async function excluir(opp: Opp) {
    setBusy(opp.id);
    try {
      const res = await fetch(`/api/v1/crm/opportunities/${opp.id}`, { method: "DELETE", headers: authH() });
      if (res.ok) fetchFunil(); else toast.error("Erro ao excluir.");
    } catch { toast.error("Falha de conexão."); }
    finally { setBusy(null); }
  }

  return (
    <div className="max-w-full mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Clientes", href: "/clientes" }, { label: "Funil de Vendas" }]} />
      <div className="afj-page-header">
        <div>
          <h1 className="font-display text-2xl font-semibold text-afj-black flex items-center gap-2">
            <Filter size={22} className="text-afj-gold" /> Funil de Vendas
          </h1>
          <p className="text-afj-black/50 text-sm mt-0.5">Pipeline de captação — oportunidades por estágio, com previsão ponderada.</p>
        </div>
        <button onClick={() => setModal(true)} className="btn-afj-primary text-sm py-2 px-4 rounded-sm flex items-center gap-2">
          <Plus size={15} /> Nova oportunidade
        </button>
      </div>

      {/* Meta de captação do mês (Fase 213) */}
      <div className="afj-card p-4">
        <div className="flex items-center justify-between gap-3 mb-2">
          <span className="flex items-center gap-2 text-sm font-medium text-afj-black">
            <Target size={14} className="text-afj-gold" />
            Meta de receita — {PERIODO_ATUAL}
          </span>
          {canDefinirMeta && !editingMeta && (
            <button onClick={() => { setMetaValor(meta ? String(meta.valor_meta) : ""); setEditingMeta(true); }}
              className="text-afj-black/40 hover:text-afj-gold">
              <Pencil size={13} />
            </button>
          )}
        </div>
        {editingMeta ? (
          <form onSubmit={salvarMeta} className="flex items-center gap-2">
            <input
              type="number" min="1" step="0.01" autoFocus value={metaValor}
              onChange={(e) => setMetaValor(e.target.value)}
              placeholder="Valor da meta (R$)"
              className="flex-1 border border-afj-cream-dark rounded-sm px-3 py-1.5 text-sm focus:outline-none focus:border-afj-gold"
            />
            <button type="submit" disabled={savingMeta} className="btn-afj-primary text-xs py-1.5 px-3 rounded-sm">
              {savingMeta ? <Loader2 size={13} className="animate-spin" /> : "Salvar"}
            </button>
            <button type="button" onClick={() => setEditingMeta(false)} className="text-afj-black/40 hover:text-afj-black">
              <X size={15} />
            </button>
          </form>
        ) : meta ? (
          <div>
            <div className="flex items-baseline justify-between text-sm mb-1">
              <span className="text-afj-black/60">Realizado: <strong className="text-afj-black">{fmtBRL(meta.realizado)}</strong></span>
              <span className="text-afj-black/60">Meta: <strong className="text-afj-black">{fmtBRL(meta.valor_meta)}</strong></span>
            </div>
            <div className="h-2 bg-afj-cream-dark rounded-full overflow-hidden">
              <div
                className={`h-full ${(meta.percentual ?? 0) >= 100 ? "bg-green-500" : "bg-afj-gold"}`}
                style={{ width: `${Math.min(100, meta.percentual ?? 0)}%` }}
              />
            </div>
            <p className="text-xs text-afj-black/40 mt-1">{meta.percentual ?? 0}% da meta atingido</p>
          </div>
        ) : (
          <p className="text-xs text-afj-black/40">
            {canDefinirMeta ? "Nenhuma meta definida pra este mês." : "Nenhuma meta definida pra este mês pela gestão."}
          </p>
        )}
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="afj-stat-card"><p className="text-2xl font-bold text-afj-black">{loading ? "..." : funil?.abertas ?? 0}</p><p className="text-xs text-afj-black/50 mt-0.5">Oportunidades abertas</p></div>
        <div className="afj-stat-card"><p className="text-2xl font-bold text-afj-black">{loading ? "..." : fmtBRL(funil?.pipeline_aberto ?? 0)}</p><p className="text-xs text-afj-black/50 mt-0.5">Pipeline aberto</p></div>
        <div className="afj-stat-card flex-row items-center gap-3"><TrendingUp size={22} className="text-green-600" /><div><p className="text-2xl font-bold text-green-600">{loading ? "..." : fmtBRL(funil?.forecast ?? 0)}</p><p className="text-xs text-afj-black/50 mt-0.5">Previsão ponderada (forecast)</p></div></div>
      </div>

      {loading ? (
        <div className="afj-card p-8 space-y-3">{Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-24 bg-afj-cream-dark rounded animate-pulse" />)}</div>
      ) : funil && (
        <div className="overflow-x-auto pb-4">
          <div className="flex gap-3 min-w-max">
            {funil.estagios.map((est) => (
              <div key={est} className={`w-64 flex-shrink-0 bg-afj-cream/40 rounded-sm border-t-2 ${COL_STYLE[est]}`}>
                <div className="px-3 py-2 flex items-center justify-between">
                  <span className="text-xs font-semibold text-afj-black uppercase tracking-wide">{LABEL[est]}</span>
                  <span className="text-[11px] text-afj-black/50">{funil.totais[est].count} · {fmtBRL(funil.totais[est].valor)}</span>
                </div>
                <div className="px-2 pb-2 space-y-2 max-h-[60vh] overflow-y-auto">
                  {funil.colunas[est].map((o) => (
                    <div key={o.id} className="bg-white border border-afj-cream-dark rounded-sm p-2.5 shadow-sm">
                      <p className="text-sm font-medium text-afj-black leading-snug">{o.titulo}</p>
                      {o.cliente && <p className="text-[11px] text-afj-black/50 mt-0.5">{o.cliente}</p>}
                      <div className="flex items-center justify-between mt-1.5">
                        <span className="text-xs font-semibold text-afj-gold-dark">{fmtBRL(o.valor_estimado)}</span>
                        <span className="text-[10px] text-afj-black/40">{o.probabilidade}%</span>
                      </div>
                      <div className="flex items-center gap-1 mt-2">
                        <select value={o.estagio} disabled={busy === o.id}
                          onChange={(e) => e.target.value !== o.estagio && mover(o, e.target.value)}
                          className="flex-1 text-[11px] border border-afj-cream-dark rounded-sm px-1.5 py-1 bg-white">
                          {funil.estagios.map((s) => <option key={s} value={s}>{LABEL[s]}</option>)}
                        </select>
                        <button onClick={() => excluir(o)} disabled={busy === o.id} title="Excluir" className="text-red-400 hover:text-red-600 p-1">
                          {busy === o.id ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
                        </button>
                      </div>
                      {o.motivo_perda && <p className="text-[10px] text-red-500 mt-1">Perda: {o.motivo_perda}</p>}
                    </div>
                  ))}
                  {funil.colunas[est].length === 0 && <p className="text-[11px] text-afj-black/30 text-center py-3">—</p>}
                  {funil.truncado[est] && (
                    <p className="text-[10px] text-afj-black/40 text-center py-2">
                      Mostrando {funil.colunas[est].length} de {funil.totais[est].count} — os totais acima já contam todas
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Modal nova oportunidade */}
      {modal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => !saving && setModal(false)}>
          <form onSubmit={criar} className="bg-white rounded-sm shadow-xl w-full max-w-md" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b border-afj-cream-dark">
              <h2 className="font-semibold text-afj-black">Nova oportunidade</h2>
              <button type="button" onClick={() => setModal(false)} className="text-afj-black/40 hover:text-afj-black"><X size={18} /></button>
            </div>
            <div className="p-5 space-y-3">
              <div>
                <label className="text-xs text-afj-black/60">Título *</label>
                <input required value={form.titulo} onChange={(e) => setForm({ ...form, titulo: e.target.value })}
                  placeholder="Ex.: Consultoria trabalhista — Empresa Y" className="w-full mt-1 border border-afj-cream-dark rounded-sm px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="text-xs text-afj-black/60">Cliente (opcional)</label>
                <select value={form.client_id} onChange={(e) => setForm({ ...form, client_id: e.target.value })}
                  className="w-full mt-1 border border-afj-cream-dark rounded-sm px-3 py-2 text-sm bg-white">
                  <option value="">Lead sem cadastro</option>
                  {clientes.map((c) => <option key={c.id} value={c.id}>{c.nome_completo}</option>)}
                </select>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div><label className="text-[11px] text-afj-black/50">Valor (R$)</label><input type="number" min="0" step="0.01" value={form.valor_estimado} onChange={(e) => setForm({ ...form, valor_estimado: e.target.value })} className="w-full mt-0.5 border border-afj-cream-dark rounded-sm px-2 py-1.5 text-sm" /></div>
                <div><label className="text-[11px] text-afj-black/50">Prob. (%)</label><input type="number" min="0" max="100" value={form.probabilidade} onChange={(e) => setForm({ ...form, probabilidade: e.target.value })} className="w-full mt-0.5 border border-afj-cream-dark rounded-sm px-2 py-1.5 text-sm" /></div>
                <div>
                  <label className="text-[11px] text-afj-black/50">Estágio</label>
                  <select value={form.estagio} onChange={(e) => setForm({ ...form, estagio: e.target.value })} className="w-full mt-0.5 border border-afj-cream-dark rounded-sm px-2 py-1.5 text-sm bg-white">
                    {["LEAD", "QUALIFICACAO", "PROPOSTA", "NEGOCIACAO"].map((s) => <option key={s} value={s}>{LABEL[s]}</option>)}
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div><label className="text-[11px] text-afj-black/50">Origem</label><input value={form.origem} onChange={(e) => setForm({ ...form, origem: e.target.value })} placeholder="Indicação, site…" className="w-full mt-0.5 border border-afj-cream-dark rounded-sm px-2 py-1.5 text-sm" /></div>
                <div><label className="text-[11px] text-afj-black/50">Previsão fecham.</label><input type="date" value={form.expected_close} onChange={(e) => setForm({ ...form, expected_close: e.target.value })} className="w-full mt-0.5 border border-afj-cream-dark rounded-sm px-2 py-1.5 text-sm" /></div>
              </div>
              <button type="submit" disabled={saving} className="btn-afj-primary w-full text-sm py-2 rounded-sm flex items-center justify-center gap-2 disabled:opacity-50">
                {saving ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />} Criar oportunidade
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
