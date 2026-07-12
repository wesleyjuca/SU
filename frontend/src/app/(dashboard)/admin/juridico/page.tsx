"use client";
import { useState, useEffect } from "react";
import { Gavel, Plus, X, Save, Loader2, CalendarClock } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { useToast } from "@/components/ui/Toast";

interface Feriado { data: string; descricao: string | null }

function authH(): HeadersInit {
  const t = typeof window !== "undefined" ? localStorage.getItem("afj_access_token") : null;
  return { "Content-Type": "application/json", Authorization: `Bearer ${t}` };
}

export default function JuridicoPage() {
  const toast = useToast();
  const [feriados, setFeriados] = useState<Feriado[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [novo, setNovo] = useState({ data: "", descricao: "" });

  useEffect(() => { fetchFeriados(); }, []);

  async function fetchFeriados() {
    setLoading(true);
    try {
      const res = await fetch("/api/v1/tenant/feriados", { headers: authH() });
      if (res.ok) { const d = await res.json(); setFeriados(d.feriados || []); }
    } catch { toast.error("Falha ao carregar feriados."); }
    finally { setLoading(false); }
  }

  function adicionar() {
    if (!novo.data) { toast.error("Informe a data."); return; }
    if (feriados.some((f) => f.data === novo.data)) { toast.error("Data já cadastrada."); return; }
    setFeriados([...feriados, { data: novo.data, descricao: novo.descricao.trim() || null }].sort((a, b) => a.data.localeCompare(b.data)));
    setNovo({ data: "", descricao: "" });
  }

  function remover(data: string) {
    setFeriados(feriados.filter((f) => f.data !== data));
  }

  async function salvar() {
    setSaving(true);
    try {
      const res = await fetch("/api/v1/tenant/feriados", {
        method: "PUT", headers: authH(),
        body: JSON.stringify({ feriados: feriados.map((f) => ({ data: f.data, descricao: f.descricao })) }),
      });
      if (res.ok) toast.success("Feriados forenses salvos.");
      else { const d = await res.json(); toast.error(d.detail || "Erro ao salvar."); }
    } catch { toast.error("Falha de conexão."); }
    finally { setSaving(false); }
  }

  return (
    <div className="max-w-3xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Admin" }, { label: "Config. Jurídica" }]} />
      <div className="afj-page-header">
        <div>
          <h1 className="font-display text-2xl font-semibold text-afj-black flex items-center gap-2">
            <Gavel size={22} className="text-afj-gold" /> Configuração Jurídica
          </h1>
          <p className="text-afj-black/50 text-sm mt-0.5">Parâmetros que afetam o cálculo de prazos do escritório.</p>
        </div>
      </div>

      <div className="afj-card p-5">
        <div className="flex items-center gap-2 mb-1">
          <CalendarClock size={16} className="text-afj-gold" />
          <h2 className="font-semibold text-afj-black">Feriados forenses locais</h2>
        </div>
        <p className="text-xs text-afj-black/50 mb-4">
          Complementam os feriados nacionais e o recesso forense (20/12–20/01) no cálculo automático de prazos.
          Cadastre aqui os feriados da(s) comarca(s) onde o escritório atua (ex.: aniversário da cidade, feriados estaduais).
        </p>

        {/* Adicionar */}
        <div className="flex gap-2 items-end mb-4">
          <div>
            <label className="text-[11px] text-afj-black/50 block mb-0.5">Data</label>
            <input type="date" value={novo.data} onChange={(e) => setNovo({ ...novo, data: e.target.value })}
              className="border border-afj-cream-dark rounded-sm px-2 py-1.5 text-sm" />
          </div>
          <div className="flex-1">
            <label className="text-[11px] text-afj-black/50 block mb-0.5">Descrição (opcional)</label>
            <input value={novo.descricao} onChange={(e) => setNovo({ ...novo, descricao: e.target.value })}
              placeholder="Ex.: Aniversário de Rio Branco" className="w-full border border-afj-cream-dark rounded-sm px-3 py-1.5 text-sm" />
          </div>
          <button onClick={adicionar} className="btn-afj-outline rounded-sm py-1.5 px-3 text-sm flex items-center gap-1.5"><Plus size={14} /> Adicionar</button>
        </div>

        {/* Lista */}
        {loading ? (
          <div className="space-y-2">{Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-9 bg-afj-cream-dark rounded animate-pulse" />)}</div>
        ) : feriados.length === 0 ? (
          <p className="text-sm text-afj-black/40 text-center py-4">Nenhum feriado local cadastrado — o cálculo usa nacionais + recesso.</p>
        ) : (
          <div className="divide-y divide-afj-cream-dark border border-afj-cream-dark rounded-sm">
            {feriados.map((f) => (
              <div key={f.data} className="flex items-center justify-between px-3 py-2">
                <div>
                  <span className="text-sm font-medium text-afj-black">{new Date(f.data + "T00:00:00").toLocaleDateString("pt-BR")}</span>
                  {f.descricao && <span className="text-xs text-afj-black/50 ml-2">{f.descricao}</span>}
                </div>
                <button onClick={() => remover(f.data)} className="text-red-400 hover:text-red-600 p-1"><X size={16} /></button>
              </div>
            ))}
          </div>
        )}

        <button onClick={salvar} disabled={saving} className="btn-afj-primary rounded-sm py-2 px-4 text-sm mt-4 flex items-center gap-2 disabled:opacity-50">
          {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Salvar feriados
        </button>
      </div>
    </div>
  );
}
