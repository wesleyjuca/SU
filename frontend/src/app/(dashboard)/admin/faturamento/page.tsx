"use client";
import { useState, useEffect } from "react";
import {
  Receipt, DollarSign, Settings2, PauseCircle, PlayCircle, X, Loader2, CheckCircle2,
} from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { useToast } from "@/components/ui/Toast";

interface BillingRow {
  tenant_id: string;
  name: string;
  slug: string;
  plan: string;
  is_root: boolean;
  configured: boolean;
  valor_mensal: number | null;
  dia_vencimento: number | null;
  status: string;
  proximo_vencimento: string | null;
  ultimo_pagamento: string | null;
}

const STATUS_STYLE: Record<string, string> = {
  ATIVO: "bg-green-50 text-green-700 border-green-200",
  INADIMPLENTE: "bg-amber-50 text-amber-700 border-amber-200",
  SUSPENSO: "bg-red-50 text-red-700 border-red-200",
  ISENTO: "bg-afj-gold/15 text-afj-gold-dark border-afj-gold/30",
  NAO_CONFIGURADO: "bg-gray-50 text-gray-500 border-gray-200",
};

const STATUS_LABEL: Record<string, string> = {
  ATIVO: "Em dia", INADIMPLENTE: "Vencido", SUSPENSO: "Suspenso",
  ISENTO: "Isento", NAO_CONFIGURADO: "Não configurado",
};

function authH(): HeadersInit {
  const token = typeof window !== "undefined" ? localStorage.getItem("afj_access_token") : null;
  return { "Content-Type": "application/json", Authorization: `Bearer ${token}` };
}

function fmtBRL(v: number | null): string {
  return v != null ? `R$ ${v.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}` : "—";
}
function fmtDate(iso: string | null): string {
  return iso ? new Date(iso.length > 10 ? iso : iso + "T00:00:00").toLocaleDateString("pt-BR") : "—";
}
function competenciaAtual(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export default function FaturamentoPage() {
  const toast = useToast();
  const [rows, setRows] = useState<BillingRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  // Modais: configurar cobrança / registrar pagamento
  const [cfg, setCfg] = useState<BillingRow | null>(null);
  const [cfgForm, setCfgForm] = useState({ valor_mensal: "", dia_vencimento: "10" });
  const [pay, setPay] = useState<BillingRow | null>(null);
  const [payForm, setPayForm] = useState({ valor: "", competencia: competenciaAtual() });
  const [saving, setSaving] = useState(false);

  useEffect(() => { fetchBilling(); }, []);

  async function fetchBilling() {
    setLoading(true);
    try {
      const res = await fetch("/api/v1/billing", { headers: authH() });
      if (res.ok) setRows(await res.json());
      else if (res.status === 403) toast.error("Acesso restrito ao super administrador da plataforma.");
    } catch { toast.error("Falha ao carregar o faturamento."); }
    finally { setLoading(false); }
  }

  function openCfg(r: BillingRow) {
    setCfgForm({ valor_mensal: r.valor_mensal != null ? String(r.valor_mensal) : "", dia_vencimento: String(r.dia_vencimento ?? 10) });
    setCfg(r);
  }
  function openPay(r: BillingRow) {
    setPayForm({ valor: r.valor_mensal != null ? String(r.valor_mensal) : "", competencia: competenciaAtual() });
    setPay(r);
  }

  async function saveCfg(e: React.FormEvent) {
    e.preventDefault();
    if (!cfg) return;
    setSaving(true);
    try {
      const res = await fetch(`/api/v1/billing/${cfg.tenant_id}`, {
        method: "PUT", headers: authH(),
        body: JSON.stringify({ valor_mensal: parseFloat(cfgForm.valor_mensal), dia_vencimento: parseInt(cfgForm.dia_vencimento) }),
      });
      if (res.ok) { toast.success("Cobrança configurada."); setCfg(null); fetchBilling(); }
      else { const d = await res.json(); toast.error(d.detail || "Erro ao configurar."); }
    } catch { toast.error("Falha de conexão."); }
    finally { setSaving(false); }
  }

  async function savePay(e: React.FormEvent) {
    e.preventDefault();
    if (!pay) return;
    setSaving(true);
    try {
      const res = await fetch(`/api/v1/billing/${pay.tenant_id}/payments`, {
        method: "POST", headers: authH(),
        body: JSON.stringify({ valor: parseFloat(payForm.valor), competencia: payForm.competencia }),
      });
      if (res.ok) { toast.success("Pagamento registrado — escritório em dia."); setPay(null); fetchBilling(); }
      else { const d = await res.json(); toast.error(d.detail || "Erro ao registrar pagamento."); }
    } catch { toast.error("Falha de conexão."); }
    finally { setSaving(false); }
  }

  async function setSuspend(r: BillingRow, suspend: boolean) {
    setBusy(r.tenant_id);
    try {
      const res = await fetch(`/api/v1/billing/${r.tenant_id}/${suspend ? "suspend" : "reactivate"}`, {
        method: "POST", headers: authH(),
      });
      if (res.ok) { toast.success(suspend ? "Escritório suspenso." : "Escritório reativado."); fetchBilling(); }
      else { const d = await res.json(); toast.error(d.detail || "Erro ao atualizar."); }
    } catch { toast.error("Falha de conexão."); }
    finally { setBusy(null); }
  }

  const receitaMensal = rows.filter((r) => !r.is_root && r.status !== "SUSPENSO").reduce((s, r) => s + (r.valor_mensal || 0), 0);
  const inadimplentes = rows.filter((r) => r.status === "INADIMPLENTE" || r.status === "SUSPENSO").length;

  return (
    <div className="max-w-6xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Admin" }, { label: "Faturamento" }]} />

      <div className="afj-page-header">
        <div>
          <h1 className="font-display text-2xl font-semibold text-afj-black flex items-center gap-2">
            <Receipt size={22} className="text-afj-gold" /> Faturamento
          </h1>
          <p className="text-afj-black/50 text-sm mt-0.5">
            Mensalidades dos escritórios clientes — registro manual de pagamentos e suspensão de inadimplentes.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="afj-stat-card"><p className="text-2xl font-bold text-afj-black">{loading ? "..." : rows.length}</p><p className="text-xs text-afj-black/50 mt-0.5">Escritórios</p></div>
        <div className="afj-stat-card"><p className="text-2xl font-bold text-green-600">{loading ? "..." : fmtBRL(receitaMensal)}</p><p className="text-xs text-afj-black/50 mt-0.5">Receita mensal recorrente</p></div>
        <div className="afj-stat-card"><p className="text-2xl font-bold text-red-600">{loading ? "..." : inadimplentes}</p><p className="text-xs text-afj-black/50 mt-0.5">Vencidos / suspensos</p></div>
      </div>

      {loading ? (
        <div className="afj-card p-8 space-y-3">
          {Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-10 bg-afj-cream-dark rounded animate-pulse" />)}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="afj-table w-full">
            <thead>
              <tr>
                <th>Escritório</th><th>Mensalidade</th><th>Vencimento</th><th>Último pagamento</th><th>Situação</th><th className="text-right">Ações</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.tenant_id}>
                  <td>
                    <span className="font-medium text-afj-black">{r.name}</span>
                    {r.is_root && <span className="ml-2 text-[10px] uppercase tracking-wide bg-afj-gold/15 text-afj-gold-dark px-1.5 py-0.5 rounded-sm">raiz</span>}
                    <span className="block font-mono text-[11px] text-afj-black/40">{r.slug}</span>
                  </td>
                  <td className="text-afj-black/70">{fmtBRL(r.valor_mensal)}{r.dia_vencimento ? <span className="text-afj-black/35 text-xs"> · dia {r.dia_vencimento}</span> : null}</td>
                  <td className="text-afj-black/70">{fmtDate(r.proximo_vencimento)}</td>
                  <td className="text-afj-black/70">{fmtDate(r.ultimo_pagamento)}</td>
                  <td>
                    <span className={`inline-flex items-center text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-sm border ${STATUS_STYLE[r.status] || STATUS_STYLE.NAO_CONFIGURADO}`}>
                      {STATUS_LABEL[r.status] || r.status}
                    </span>
                  </td>
                  <td>
                    {r.is_root ? (
                      <span className="block text-right text-xs text-afj-black/30">isento</span>
                    ) : (
                      <div className="flex items-center justify-end gap-1">
                        <button onClick={() => openCfg(r)} title="Configurar cobrança"
                          className="text-afj-black/40 hover:text-afj-gold p-1.5 rounded hover:bg-afj-cream"><Settings2 size={15} /></button>
                        <button onClick={() => openPay(r)} title="Registrar pagamento"
                          className="text-green-600 hover:text-green-700 p-1.5 rounded hover:bg-green-50"><DollarSign size={15} /></button>
                        {r.status === "SUSPENSO" ? (
                          <button onClick={() => setSuspend(r, false)} disabled={busy === r.tenant_id} title="Reativar"
                            className="text-green-600 hover:text-green-700 p-1.5 rounded hover:bg-green-50 disabled:opacity-40">
                            {busy === r.tenant_id ? <Loader2 size={15} className="animate-spin" /> : <PlayCircle size={15} />}</button>
                        ) : (
                          <button onClick={() => setSuspend(r, true)} disabled={busy === r.tenant_id} title="Suspender"
                            className="text-red-500 hover:text-red-600 p-1.5 rounded hover:bg-red-50 disabled:opacity-40">
                            {busy === r.tenant_id ? <Loader2 size={15} className="animate-spin" /> : <PauseCircle size={15} />}</button>
                        )}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Modal configurar cobrança */}
      {cfg && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => !saving && setCfg(null)}>
          <form onSubmit={saveCfg} className="bg-white rounded-sm shadow-xl w-full max-w-sm max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b border-afj-cream-dark">
              <h2 className="font-semibold text-afj-black">Cobrança — {cfg.name}</h2>
              <button type="button" onClick={() => setCfg(null)} className="text-afj-black/40 hover:text-afj-black"><X size={18} /></button>
            </div>
            <div className="p-5 space-y-3">
              <div>
                <label className="text-xs text-afj-black/60">Mensalidade (R$)</label>
                <input required type="number" min="0" step="0.01" value={cfgForm.valor_mensal}
                  onChange={(e) => setCfgForm({ ...cfgForm, valor_mensal: e.target.value })}
                  className="w-full mt-1 border border-afj-cream-dark rounded-sm px-3 py-2 text-sm" placeholder="Ex.: 499.00" />
              </div>
              <div>
                <label className="text-xs text-afj-black/60">Dia de vencimento (1-28)</label>
                <input required type="number" min="1" max="28" value={cfgForm.dia_vencimento}
                  onChange={(e) => setCfgForm({ ...cfgForm, dia_vencimento: e.target.value })}
                  className="w-full mt-1 border border-afj-cream-dark rounded-sm px-3 py-2 text-sm" />
              </div>
              <button type="submit" disabled={saving} className="btn-afj-primary w-full text-sm py-2 rounded-sm flex items-center justify-center gap-2 disabled:opacity-50">
                {saving ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />} Salvar
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Modal registrar pagamento */}
      {pay && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => !saving && setPay(null)}>
          <form onSubmit={savePay} className="bg-white rounded-sm shadow-xl w-full max-w-sm max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b border-afj-cream-dark">
              <h2 className="font-semibold text-afj-black">Registrar pagamento — {pay.name}</h2>
              <button type="button" onClick={() => setPay(null)} className="text-afj-black/40 hover:text-afj-black"><X size={18} /></button>
            </div>
            <div className="p-5 space-y-3">
              <p className="text-xs text-afj-black/50">Registrar um pagamento reativa o escritório e avança o próximo vencimento.</p>
              <div>
                <label className="text-xs text-afj-black/60">Valor pago (R$)</label>
                <input required type="number" min="0.01" step="0.01" value={payForm.valor}
                  onChange={(e) => setPayForm({ ...payForm, valor: e.target.value })}
                  className="w-full mt-1 border border-afj-cream-dark rounded-sm px-3 py-2 text-sm" />
              </div>
              <div>
                <label className="text-xs text-afj-black/60">Competência (mês de referência)</label>
                <input required type="month" value={payForm.competencia}
                  onChange={(e) => setPayForm({ ...payForm, competencia: e.target.value })}
                  className="w-full mt-1 border border-afj-cream-dark rounded-sm px-3 py-2 text-sm" />
              </div>
              <button type="submit" disabled={saving} className="btn-afj-primary w-full text-sm py-2 rounded-sm flex items-center justify-center gap-2 disabled:opacity-50">
                {saving ? <Loader2 size={14} className="animate-spin" /> : <DollarSign size={14} />} Registrar pagamento
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
