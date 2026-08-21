"use client";
import { useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { Receipt, Plus, X, FileText, Trash2, CheckCircle, Send, Loader2, Link2, Copy } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { useToast } from "@/components/ui/Toast";

interface Item { descricao: string; valor: string }
interface Invoice {
  id: string; numero: string; cliente: string | null; client_id: string | null;
  itens: { descricao: string; valor: number }[]; valor_total: number; status: string;
  periodo_inicio: string | null; periodo_fim: string | null; data_vencimento: string | null;
  emitido_em: string | null; pago_em: string | null;
  payment_link: string | null; payment_provider: string | null;
}
interface Cliente { id: string; nome_completo: string }

const STATUS_STYLE: Record<string, string> = {
  RASCUNHO: "bg-gray-50 text-gray-600 border-gray-200",
  EMITIDA: "bg-amber-50 text-amber-700 border-amber-200",
  PAGA: "bg-green-50 text-green-700 border-green-200",
  CANCELADA: "bg-red-50 text-red-600 border-red-200",
};

function authH(): HeadersInit {
  const t = typeof window !== "undefined" ? localStorage.getItem("afj_access_token") : null;
  return { "Content-Type": "application/json", Authorization: `Bearer ${t}` };
}
const fmtBRL = (v: number) => `R$ ${v.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`;
const fmtDate = (s: string | null) => (s ? new Date(s.slice(0, 10) + "T00:00:00").toLocaleDateString("pt-BR") : "—");

export default function FaturasPage() {
  const toast = useToast();
  const searchParams = useSearchParams();
  const clientIdFiltro = searchParams.get("client_id");
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [modal, setModal] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ client_id: "", periodo_inicio: "", periodo_fim: "", data_vencimento: "" });
  const [itens, setItens] = useState<Item[]>([{ descricao: "", valor: "" }]);

  useEffect(() => { fetchInvoices(); fetchClientes(); }, [clientIdFiltro]);

  async function fetchInvoices() {
    setLoading(true);
    try {
      const url = clientIdFiltro
        ? `/api/v1/financial/invoices?client_id=${encodeURIComponent(clientIdFiltro)}`
        : "/api/v1/financial/invoices";
      const res = await fetch(url, { headers: authH() });
      if (res.ok) setInvoices(await res.json());
    } catch { toast.error("Falha ao carregar faturas."); }
    finally { setLoading(false); }
  }
  async function fetchClientes() {
    try {
      const res = await fetch("/api/v1/clients?limit=200", { headers: authH() });
      if (res.ok) { const d = await res.json(); setClientes(Array.isArray(d) ? d : d.items ?? []); }
    } catch {}
  }

  const total = itens.reduce((s, i) => s + (parseFloat(i.valor) || 0), 0);

  async function criar(e: React.FormEvent) {
    e.preventDefault();
    const validItens = itens.filter((i) => i.descricao.trim() && parseFloat(i.valor) > 0);
    if (!form.client_id || validItens.length === 0) { toast.error("Selecione o cliente e adicione ao menos um item."); return; }
    setSaving(true);
    try {
      const res = await fetch("/api/v1/financial/invoices", {
        method: "POST", headers: authH(),
        body: JSON.stringify({
          client_id: form.client_id,
          periodo_inicio: form.periodo_inicio || undefined,
          periodo_fim: form.periodo_fim || undefined,
          data_vencimento: form.data_vencimento || undefined,
          itens: validItens.map((i) => ({ descricao: i.descricao, valor: parseFloat(i.valor) })),
        }),
      });
      if (res.ok) {
        toast.success("Fatura criada (rascunho).");
        setModal(false); setForm({ client_id: "", periodo_inicio: "", periodo_fim: "", data_vencimento: "" });
        setItens([{ descricao: "", valor: "" }]); fetchInvoices();
      } else { const d = await res.json(); toast.error(d.detail || "Erro ao criar fatura."); }
    } catch { toast.error("Falha de conexão."); }
    finally { setSaving(false); }
  }

  async function mudarStatus(inv: Invoice, status: string) {
    setBusy(inv.id);
    try {
      const res = await fetch(`/api/v1/financial/invoices/${inv.id}`, { method: "PATCH", headers: authH(), body: JSON.stringify({ status }) });
      if (res.ok) { toast.success(`Fatura marcada como ${status.toLowerCase()}.`); fetchInvoices(); }
      else toast.error("Erro ao atualizar.");
    } catch { toast.error("Falha de conexão."); }
    finally { setBusy(null); }
  }

  async function excluir(inv: Invoice) {
    setBusy(inv.id);
    try {
      const res = await fetch(`/api/v1/financial/invoices/${inv.id}`, { method: "DELETE", headers: authH() });
      if (res.ok) { toast.success("Rascunho excluído."); fetchInvoices(); }
      else { const d = await res.json(); toast.error(d.detail || "Erro ao excluir."); }
    } catch { toast.error("Falha de conexão."); }
    finally { setBusy(null); }
  }

  async function copiarLink(link: string) {
    try { await navigator.clipboard.writeText(link); toast.success("Link de pagamento copiado — envie ao cliente."); }
    catch { toast.warning(`Link: ${link}`); }
  }

  async function gerarLinkPagamento(inv: Invoice) {
    setBusy(inv.id);
    try {
      const res = await fetch(`/api/v1/financial/invoices/${inv.id}/payment-link`, { method: "POST", headers: authH() });
      const d = await res.json().catch(() => ({}));
      if (res.ok && d.payment_link) {
        await copiarLink(d.payment_link);
        fetchInvoices();
      } else toast.error(d.detail || "Erro ao gerar o link de pagamento.");
    } catch { toast.error("Falha de conexão."); }
    finally { setBusy(null); }
  }

  async function baixarPdf(inv: Invoice) {
    setBusy(inv.id);
    try {
      const res = await fetch(`/api/v1/financial/invoices/${inv.id}/pdf`, { headers: authH() });
      if (!res.ok) { toast.error("Erro ao gerar PDF."); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = Object.assign(document.createElement("a"), { href: url, download: `fatura-${inv.numero}.pdf` });
      a.click(); URL.revokeObjectURL(url);
    } catch { toast.error("Falha de conexão."); }
    finally { setBusy(null); }
  }

  const totalReceber = invoices.filter((i) => i.status === "EMITIDA").reduce((s, i) => s + i.valor_total, 0);

  return (
    <div className="max-w-6xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Financeiro", href: "/financeiro" }, { label: "Faturas" }]} />
      <div className="afj-page-header">
        <div>
          <h1 className="font-display text-2xl font-semibold text-afj-black flex items-center gap-2">
            <Receipt size={22} className="text-afj-gold" /> Faturas a Cliente
          </h1>
          <p className="text-afj-black/50 text-sm mt-0.5">Faturas de honorários — emissão, PDF timbrado e controle de pagamento.</p>
        </div>
        <button onClick={() => setModal(true)} className="btn-afj-primary text-sm py-2 px-4 rounded-sm flex items-center gap-2">
          <Plus size={15} /> Nova fatura
        </button>
      </div>

      {clientIdFiltro && (
        <div className="flex items-center gap-2 text-xs bg-afj-gold/10 border border-afj-gold/30 rounded-sm px-3 py-2">
          <span className="text-afj-black/70">
            Mostrando só as faturas de <strong>{invoices[0]?.cliente || "este cliente"}</strong>
          </span>
          <Link href="/financeiro/faturas" className="text-afj-gold hover:underline ml-auto">Ver todas</Link>
        </div>
      )}

      <div className="grid grid-cols-3 gap-4">
        <div className="afj-stat-card"><p className="text-2xl font-bold text-afj-black">{loading ? "..." : invoices.length}</p><p className="text-xs text-afj-black/50 mt-0.5">Faturas</p></div>
        <div className="afj-stat-card"><p className="text-2xl font-bold text-amber-600">{loading ? "..." : fmtBRL(totalReceber)}</p><p className="text-xs text-afj-black/50 mt-0.5">Emitidas a receber</p></div>
        <div className="afj-stat-card"><p className="text-2xl font-bold text-green-600">{loading ? "..." : invoices.filter((i) => i.status === "PAGA").length}</p><p className="text-xs text-afj-black/50 mt-0.5">Pagas</p></div>
      </div>

      {loading ? (
        <div className="afj-card p-8 space-y-3">{Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-10 bg-afj-cream-dark rounded animate-pulse" />)}</div>
      ) : invoices.length === 0 ? (
        <div className="afj-card p-10 text-center">
          <Receipt size={36} className="mx-auto text-afj-black/20 mb-3" />
          <p className="font-semibold text-afj-black">Nenhuma fatura ainda</p>
          <p className="text-afj-black/40 text-sm mt-1">Clique em “Nova fatura” para cobrar honorários de um cliente.</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="afj-table w-full">
            <thead><tr><th>Número</th><th>Cliente</th><th className="text-right">Valor</th><th>Vencimento</th><th>Status</th><th className="text-right">Ações</th></tr></thead>
            <tbody>
              {invoices.map((inv) => (
                <tr key={inv.id}>
                  <td className="font-mono text-xs text-afj-black/70">{inv.numero}</td>
                  <td className="font-medium text-afj-black">{inv.cliente || "—"}</td>
                  <td className="text-right text-afj-black/80">{fmtBRL(inv.valor_total)}</td>
                  <td className="text-afj-black/60">{fmtDate(inv.data_vencimento)}</td>
                  <td><span className={`inline-flex text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-sm border ${STATUS_STYLE[inv.status] || STATUS_STYLE.RASCUNHO}`}>{inv.status}</span></td>
                  <td>
                    <div className="flex items-center justify-end gap-1">
                      <button onClick={() => baixarPdf(inv)} disabled={busy === inv.id} title="Baixar PDF" className="text-afj-black/40 hover:text-afj-gold p-1.5 rounded hover:bg-afj-cream disabled:opacity-40">
                        {busy === inv.id ? <Loader2 size={15} className="animate-spin" /> : <FileText size={15} />}
                      </button>
                      {inv.status === "RASCUNHO" && (
                        <button onClick={() => mudarStatus(inv, "EMITIDA")} disabled={busy === inv.id} title="Emitir" className="text-amber-600 hover:text-amber-700 p-1.5 rounded hover:bg-amber-50 disabled:opacity-40"><Send size={15} /></button>
                      )}
                      {inv.status === "EMITIDA" && (
                        <>
                          {inv.payment_link ? (
                            <button onClick={() => copiarLink(inv.payment_link!)} disabled={busy === inv.id} title="Copiar link de pagamento" className="text-afj-gold hover:text-afj-gold/80 p-1.5 rounded hover:bg-afj-cream disabled:opacity-40"><Copy size={15} /></button>
                          ) : (
                            <button onClick={() => gerarLinkPagamento(inv)} disabled={busy === inv.id} title="Gerar link de pagamento (Stripe/Mercado Pago)" className="text-afj-gold hover:text-afj-gold/80 p-1.5 rounded hover:bg-afj-cream disabled:opacity-40"><Link2 size={15} /></button>
                          )}
                          <button onClick={() => mudarStatus(inv, "PAGA")} disabled={busy === inv.id} title="Marcar paga" className="text-green-600 hover:text-green-700 p-1.5 rounded hover:bg-green-50 disabled:opacity-40"><CheckCircle size={15} /></button>
                        </>
                      )}
                      {inv.status === "RASCUNHO" && (
                        <button onClick={() => excluir(inv)} disabled={busy === inv.id} title="Excluir rascunho" className="text-red-500 hover:text-red-600 p-1.5 rounded hover:bg-red-50 disabled:opacity-40"><Trash2 size={15} /></button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Modal nova fatura */}
      {modal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => !saving && setModal(false)}>
          <form onSubmit={criar} className="bg-white rounded-sm shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b border-afj-cream-dark sticky top-0 bg-white">
              <h2 className="font-semibold text-afj-black">Nova fatura</h2>
              <button type="button" onClick={() => setModal(false)} className="text-afj-black/40 hover:text-afj-black"><X size={18} /></button>
            </div>
            <div className="p-5 space-y-3">
              <div>
                <label className="text-xs text-afj-black/60">Cliente *</label>
                <select required value={form.client_id} onChange={(e) => setForm({ ...form, client_id: e.target.value })}
                  className="w-full mt-1 border border-afj-cream-dark rounded-sm px-3 py-2 text-sm bg-white">
                  <option value="">Selecione...</option>
                  {clientes.map((c) => <option key={c.id} value={c.id}>{c.nome_completo}</option>)}
                </select>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div><label className="text-[11px] text-afj-black/50">Período de</label><input type="date" value={form.periodo_inicio} onChange={(e) => setForm({ ...form, periodo_inicio: e.target.value })} className="w-full mt-0.5 border border-afj-cream-dark rounded-sm px-2 py-1.5 text-sm" /></div>
                <div><label className="text-[11px] text-afj-black/50">até</label><input type="date" value={form.periodo_fim} onChange={(e) => setForm({ ...form, periodo_fim: e.target.value })} className="w-full mt-0.5 border border-afj-cream-dark rounded-sm px-2 py-1.5 text-sm" /></div>
                <div><label className="text-[11px] text-afj-black/50">Vencimento</label><input type="date" value={form.data_vencimento} onChange={(e) => setForm({ ...form, data_vencimento: e.target.value })} className="w-full mt-0.5 border border-afj-cream-dark rounded-sm px-2 py-1.5 text-sm" /></div>
              </div>
              <div>
                <label className="text-xs text-afj-black/60">Itens</label>
                <div className="space-y-2 mt-1">
                  {itens.map((it, idx) => (
                    <div key={idx} className="flex gap-2">
                      <input value={it.descricao} onChange={(e) => setItens(itens.map((x, i) => i === idx ? { ...x, descricao: e.target.value } : x))} placeholder="Descrição (ex.: Honorários contratuais)" className="flex-1 border border-afj-cream-dark rounded-sm px-3 py-2 text-sm" />
                      <input type="number" min="0" step="0.01" value={it.valor} onChange={(e) => setItens(itens.map((x, i) => i === idx ? { ...x, valor: e.target.value } : x))} placeholder="0,00" className="w-28 border border-afj-cream-dark rounded-sm px-3 py-2 text-sm" />
                      {itens.length > 1 && <button type="button" onClick={() => setItens(itens.filter((_, i) => i !== idx))} className="text-red-400 hover:text-red-600 px-1"><X size={16} /></button>}
                    </div>
                  ))}
                </div>
                <button type="button" onClick={() => setItens([...itens, { descricao: "", valor: "" }])} className="text-xs text-afj-gold hover:underline mt-2">+ Adicionar item</button>
              </div>
              <div className="flex items-center justify-between border-t border-afj-cream-dark pt-3">
                <span className="text-sm text-afj-black/60">Total</span>
                <span className="text-lg font-bold text-afj-black">{fmtBRL(total)}</span>
              </div>
              <button type="submit" disabled={saving} className="btn-afj-primary w-full text-sm py-2 rounded-sm flex items-center justify-center gap-2 disabled:opacity-50">
                {saving ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />} Criar fatura (rascunho)
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
