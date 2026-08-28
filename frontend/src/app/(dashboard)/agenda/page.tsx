"use client";
import { useState, useEffect } from "react";
import { CalendarClock, Calendar, AlertTriangle, CheckCircle, Clock, Loader2, RefreshCw, Plus, X } from "lucide-react";
import Link from "next/link";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { useToast } from "@/components/ui/Toast";

interface AgendaItem {
  id: string;
  descricao: string;
  tipo: string | null;
  status: string;
  data_prazo: string | null;
  data_fatal: string | null;
  process_id: string;
  numero_cnj: string | null;
  tribunal: string;
  area_direito: string | null;
}

function diasPara(data: string | null): number | null {
  if (!data) return null;
  return Math.ceil((new Date(data).getTime() - Date.now()) / 86400000);
}

function urgencyClass(dias: number | null): string {
  if (dias === null) return "border-l-afj-cream-dark";
  if (dias < 0) return "border-l-red-600";
  if (dias <= 2) return "border-l-red-500";
  if (dias <= 7) return "border-l-amber-400";
  return "border-l-afj-gold/50";
}

function urgencyLabel(dias: number | null) {
  if (dias === null) return null;
  if (dias < 0) return { text: `${Math.abs(dias)}d em atraso`, cls: "text-red-600 font-bold" };
  if (dias === 0) return { text: "Hoje!", cls: "text-red-600 font-bold" };
  if (dias === 1) return { text: "Amanhã", cls: "text-red-500 font-semibold" };
  if (dias <= 7) return { text: `${dias} dias`, cls: "text-amber-600 font-semibold" };
  return { text: `${dias} dias`, cls: "text-afj-black/40" };
}

const FILTRO_DIAS = [7, 15, 30, 60];

// Link pré-preenchido do Google Agenda (funciona sem conexão OAuth)
function googleCalendarUrl(item: AgendaItem): string {
  const d = item.data_prazo ? new Date(item.data_prazo) : new Date();
  const ymd = (dt: Date) => dt.toISOString().slice(0, 10).replace(/-/g, "");
  const fim = new Date(d.getTime() + 86400000);
  const titulo = `Prazo: ${item.descricao}`;
  const detalhes = `Processo ${item.numero_cnj || "s/ CNJ"} — ${item.tribunal}${item.data_fatal ? ` | Data fatal: ${new Date(item.data_fatal).toLocaleDateString("pt-BR")}` : ""} (AFJ CORE)`;
  const params = new URLSearchParams({
    action: "TEMPLATE",
    text: titulo,
    details: detalhes,
    dates: `${ymd(d)}/${ymd(fim)}`,
  });
  return `https://calendar.google.com/calendar/render?${params.toString()}`;
}

export default function AgendaPage() {
  const toast = useToast();
  const [items, setItems] = useState<AgendaItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [dias, setDias] = useState(30);
  const [somenteMeus, setSomenteMeus] = useState(false);
  const [completing, setCompleting] = useState<string | null>(null);
  const [googleEnabled, setGoogleEnabled] = useState(false);

  // Novo prazo (com calculadora)
  const [modal, setModal] = useState(false);
  const [processos, setProcessos] = useState<{ id: string; numero_cnj: string | null; tribunal: string }[]>([]);
  const [form, setForm] = useState({ process_id: "", descricao: "", tipo: "", data_prazo: "" });
  const [calc, setCalc] = useState({ data_intimacao: "", dias: "", dias_uteis: true });
  const [calcResult, setCalcResult] = useState<{ data_prazo: string; feriados_no_periodo: number; dias_uteis: boolean } | null>(null);
  const [calculando, setCalculando] = useState(false);
  const [salvando, setSalvando] = useState(false);

  useEffect(() => { fetchAgenda(); }, [dias, somenteMeus]);

  async function abrirNovoPrazo() {
    setModal(true);
    if (processos.length === 0) {
      try {
        const token = localStorage.getItem("afj_access_token");
        const res = await fetch("/api/v1/processes?limit=200", { headers: { Authorization: `Bearer ${token}` } });
        if (res.ok) { const d = await res.json(); setProcessos(Array.isArray(d) ? d : d.items ?? []); }
      } catch {}
    }
  }

  async function calcularPrazo() {
    if (!calc.data_intimacao || !calc.dias || Number(calc.dias) < 1) { toast.error("Informe a data da intimação e o nº de dias."); return; }
    setCalculando(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/processes/deadlines/calcular", {
        method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ data_intimacao: calc.data_intimacao, dias: Number(calc.dias), dias_uteis: calc.dias_uteis }),
      });
      if (res.ok) { const r = await res.json(); setCalcResult(r); setForm((f) => ({ ...f, data_prazo: r.data_prazo })); }
      else toast.error("Não foi possível calcular o prazo.");
    } catch { toast.error("Falha de conexão."); }
    finally { setCalculando(false); }
  }

  async function salvarPrazo(e: React.FormEvent) {
    e.preventDefault();
    if (!form.process_id || !form.descricao.trim() || !form.data_prazo) { toast.error("Selecione o processo, a descrição e a data do prazo."); return; }
    setSalvando(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/processes/${form.process_id}/deadlines`, {
        method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ descricao: form.descricao, tipo: form.tipo || undefined, data_prazo: form.data_prazo }),
      });
      if (res.ok) {
        toast.success("Prazo lançado.");
        setModal(false);
        setForm({ process_id: "", descricao: "", tipo: "", data_prazo: "" });
        setCalc({ data_intimacao: "", dias: "", dias_uteis: true }); setCalcResult(null);
        fetchAgenda();
      } else toast.error("Erro ao salvar o prazo.");
    } catch { toast.error("Falha de conexão."); }
    finally { setSalvando(false); }
  }

  // O atalho do Google Agenda só aparece se o escritório habilitou o módulo
  useEffect(() => {
    const token = localStorage.getItem("afj_access_token");
    fetch("/api/v1/integrations/google/status", { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setGoogleEnabled(Boolean(d?.enabled)))
      .catch(() => {});
  }, []);

  async function fetchAgenda() {
    setLoading(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/processes/agenda?dias=${dias}${somenteMeus ? "&mine=true" : ""}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setItems(await res.json());
    } finally { setLoading(false); }
  }

  async function marcarCumprido(item: AgendaItem) {
    setCompleting(item.id);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/processes/${item.process_id}/deadlines/${item.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ status: "CUMPRIDO" }),
      });
      if (res.ok) {
        setItems((prev) => prev.filter((i) => i.id !== item.id));
      } else {
        toast.error("Erro ao marcar prazo como cumprido.");
      }
    } catch {
      toast.error("Erro de conexão. Tente novamente.");
    } finally { setCompleting(null); }
  }

  const vencidos = items.filter((i) => {
    const d = diasPara(i.data_prazo);
    return d !== null && d < 0;
  });
  const hoje = items.filter((i) => diasPara(i.data_prazo) === 0);
  const proximos = items.filter((i) => {
    const d = diasPara(i.data_prazo);
    return d !== null && d > 0;
  });

  const Section = ({ title, list, icon: Icon, badgeCls }: {
    title: string;
    list: AgendaItem[];
    icon: React.ElementType;
    badgeCls: string;
  }) => list.length === 0 ? null : (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Icon size={15} className="text-afj-black/50" />
        <h2 className="font-semibold text-sm text-afj-black">{title}</h2>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${badgeCls}`}>{list.length}</span>
      </div>
      <div className="space-y-2">
        {list.map((item) => {
          const dias = diasPara(item.data_prazo);
          const diasFatal = diasPara(item.data_fatal);
          // Fase 240 (achado do diagnóstico de cadastros) — data_fatal era
          // gravada mas nunca influenciava a cor/urgência, nem tinha
          // qualquer distinção visual: um prazo fatal amanhã e um prazo
          // comum amanhã apareciam exatamente iguais. Usa a data mais
          // urgente entre as duas pra colorir o card, e mostra um selo
          // "FATAL" com a data quando ela existir.
          const diasGovernante = diasFatal !== null && (dias === null || diasFatal < dias) ? diasFatal : dias;
          const urgency = urgencyLabel(diasGovernante);
          return (
            <div
              key={item.id}
              className={`afj-card p-4 border-l-4 ${urgencyClass(diasGovernante)} hover:shadow-md transition-shadow animate-fade-in`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-afj-black text-sm">{item.descricao}</p>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1.5">
                    <Link
                      href={`/processos/${item.process_id}`}
                      className="text-xs text-afj-gold hover:underline font-mono"
                    >
                      {item.numero_cnj || "Sem CNJ"}
                    </Link>
                    <span className="text-xs text-afj-black/40">{item.tribunal}</span>
                    {item.area_direito && (
                      <span className="text-xs text-afj-black/40">{item.area_direito}</span>
                    )}
                    {item.tipo && (
                      <span className="text-xs bg-afj-cream px-1.5 py-0.5 rounded">{item.tipo}</span>
                    )}
                    {item.data_fatal && (
                      <span
                        className="text-xs bg-red-50 text-red-700 border border-red-200 px-1.5 py-0.5 rounded font-semibold"
                        title="Data fatal — prazo processual improrrogável"
                      >
                        FATAL · {new Date(item.data_fatal).toLocaleDateString("pt-BR")}
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-3 flex-shrink-0">
                  <div className="text-right">
                    <p className="text-xs text-afj-black/50">
                      {item.data_prazo ? new Date(item.data_prazo).toLocaleDateString("pt-BR") : "—"}
                    </p>
                    {urgency && <p className={`text-xs ${urgency.cls}`}>{urgency.text}</p>}
                  </div>
                  {googleEnabled && (
                    <a
                      href={googleCalendarUrl(item)}
                      target="_blank"
                      rel="noreferrer"
                      title="Adicionar ao Google Agenda"
                      aria-label="Adicionar prazo ao Google Agenda"
                      className="text-afj-black/30 hover:text-afj-gold p-1 rounded hover:bg-afj-cream"
                    >
                      <Calendar size={16} />
                    </a>
                  )}
                  <button
                    onClick={() => marcarCumprido(item)}
                    disabled={completing === item.id}
                    title="Marcar como cumprido"
                    aria-label="Marcar prazo como cumprido"
                    className="text-green-600 hover:text-green-700 disabled:opacity-40 p-1 rounded hover:bg-green-50"
                  >
                    {completing === item.id
                      ? <Loader2 size={16} className="animate-spin" />
                      : <CheckCircle size={16} />}
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Agenda de Prazos" }]} />

      <div className="afj-page-header">
        <div>
          <h1 className="font-display text-2xl font-semibold text-afj-black">Agenda de Prazos</h1>
          <p className="text-afj-black/50 text-sm mt-0.5">
            Prazos processuais ordenados por urgência
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => setSomenteMeus(!somenteMeus)}
            className={`text-xs px-3 py-1.5 rounded-sm border transition-colors ${
              somenteMeus
                ? "border-afj-gold bg-afj-gold/10 text-afj-gold font-semibold"
                : "border-afj-cream-dark text-afj-black/50 hover:border-afj-gold/50"
            }`}
          >
            Meus prazos
          </button>
          <span className="w-px h-5 bg-afj-cream-dark" />
          {FILTRO_DIAS.map((d) => (
            <button
              key={d}
              onClick={() => setDias(d)}
              className={`text-xs px-3 py-1.5 rounded-sm border transition-colors ${
                dias === d
                  ? "border-afj-gold bg-afj-gold/5 text-afj-gold font-medium"
                  : "border-afj-cream-dark text-afj-black/50 hover:border-afj-gold/50"
              }`}
            >
              {d}d
            </button>
          ))}
          <button
            onClick={fetchAgenda}
            className="text-afj-black/40 hover:text-afj-gold p-1.5 transition-colors"
            aria-label="Atualizar agenda"
          >
            <RefreshCw size={14} />
          </button>
          <button onClick={abrirNovoPrazo} className="btn-afj-primary text-sm py-1.5 px-3 rounded-sm flex items-center gap-1.5">
            <Plus size={14} /> Novo prazo
          </button>
        </div>
      </div>

      {/* Resumo */}
      <div className="grid grid-cols-3 gap-4">
        <div className="afj-card p-4 border-l-4 border-l-red-500">
          <p className="text-xs text-afj-black/50 mb-1">Vencidos</p>
          <p className="text-2xl font-bold text-red-600">{loading ? "..." : vencidos.length}</p>
        </div>
        <div className="afj-card p-4 border-l-4 border-l-amber-400">
          <p className="text-xs text-afj-black/50 mb-1">Hoje</p>
          <p className="text-2xl font-bold text-amber-600">{loading ? "..." : hoje.length}</p>
        </div>
        <div className="afj-card p-4 border-l-4 border-l-afj-gold">
          <p className="text-xs text-afj-black/50 mb-1">Próximos {dias} dias</p>
          <p className="text-2xl font-bold text-afj-black">{loading ? "..." : proximos.length}</p>
        </div>
      </div>

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="afj-card p-4 h-20 animate-pulse bg-afj-cream-dark/40" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="afj-card p-10 text-center">
          <CalendarClock size={36} className="mx-auto text-afj-black/20 mb-3" />
          <p className="font-semibold text-afj-black">Nenhum prazo no período</p>
          <p className="text-afj-black/40 text-sm mt-1">Ajuste o filtro ou cadastre prazos nos processos</p>
        </div>
      ) : (
        <div className="space-y-6">
          <Section title="Vencidos" list={vencidos} icon={AlertTriangle} badgeCls="bg-red-100 text-red-700" />
          <Section title="Hoje" list={hoje} icon={Clock} badgeCls="bg-amber-100 text-amber-700" />
          <Section title="Próximos" list={proximos} icon={Calendar} badgeCls="bg-afj-cream text-afj-black/60" />
        </div>
      )}

      {/* Modal novo prazo (com calculadora) */}
      {modal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => !salvando && setModal(false)}>
          <form onSubmit={salvarPrazo} className="bg-white rounded-sm shadow-xl w-full max-w-md max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b border-afj-cream-dark sticky top-0 bg-white">
              <h2 className="font-semibold text-afj-black">Novo prazo</h2>
              <button type="button" onClick={() => setModal(false)} className="text-afj-black/40 hover:text-afj-black"><X size={18} /></button>
            </div>
            <div className="p-5 space-y-3">
              <div>
                <label className="text-xs text-afj-black/60">Processo *</label>
                <select required value={form.process_id} onChange={(e) => setForm({ ...form, process_id: e.target.value })}
                  className="w-full mt-1 border border-afj-cream-dark rounded-sm px-3 py-2 text-sm bg-white">
                  <option value="">Selecione...</option>
                  {processos.map((p) => <option key={p.id} value={p.id}>{p.numero_cnj || "Sem CNJ"} — {p.tribunal}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs text-afj-black/60">Descrição *</label>
                <input required value={form.descricao} onChange={(e) => setForm({ ...form, descricao: e.target.value })}
                  placeholder="Ex.: Prazo para contestação" className="w-full mt-1 border border-afj-cream-dark rounded-sm px-3 py-2 text-sm" />
              </div>

              {/* Calculadora */}
              <div className="border border-afj-gold/30 bg-afj-gold/5 rounded-sm p-3 space-y-2">
                <p className="text-xs font-semibold text-afj-black/70 flex items-center gap-1.5"><Calendar size={13} className="text-afj-gold" /> Calcular por intimação</p>
                <div className="grid grid-cols-3 gap-2">
                  <div><label className="text-[11px] text-afj-black/50 block mb-0.5">Intimação</label><input type="date" value={calc.data_intimacao} onChange={(e) => setCalc({ ...calc, data_intimacao: e.target.value })} className="w-full border border-afj-cream-dark rounded-sm px-2 py-1.5 text-sm bg-white" /></div>
                  <div><label className="text-[11px] text-afj-black/50 block mb-0.5">Dias</label><input type="number" min={1} value={calc.dias} onChange={(e) => setCalc({ ...calc, dias: e.target.value })} placeholder="15" className="w-full border border-afj-cream-dark rounded-sm px-2 py-1.5 text-sm bg-white" /></div>
                  <div className="flex items-end"><label className="flex items-center gap-1.5 text-[11px] text-afj-black/60 pb-1.5 cursor-pointer"><input type="checkbox" checked={calc.dias_uteis} onChange={(e) => setCalc({ ...calc, dias_uteis: e.target.checked })} className="accent-afj-gold" /> Dias úteis</label></div>
                </div>
                <button type="button" onClick={calcularPrazo} disabled={calculando} className="btn-afj-outline text-xs py-1.5 px-3 rounded-sm w-full disabled:opacity-50">
                  {calculando ? "Calculando..." : "Calcular data do prazo"}
                </button>
                {calcResult && (
                  <p className="text-xs text-afj-black/70 bg-white border border-afj-gold/30 rounded-sm px-2 py-1.5">
                    Vence em <strong>{new Date(calcResult.data_prazo + "T00:00:00").toLocaleDateString("pt-BR")}</strong> ({calc.dias} {calcResult.dias_uteis ? "dias úteis" : "dias corridos"}, considerando feriados/recesso).
                  </p>
                )}
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-afj-black/60">Tipo</label>
                  <select value={form.tipo} onChange={(e) => setForm({ ...form, tipo: e.target.value })} className="w-full mt-1 border border-afj-cream-dark rounded-sm px-3 py-2 text-sm bg-white">
                    <option value="">Selecionar...</option>
                    {["RECURSO", "CONTESTACAO", "MANIFESTACAO", "AUDIENCIA", "PERICIA", "OUTRO"].map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-afj-black/60">Data do prazo *</label>
                  <input required type="date" value={form.data_prazo} onChange={(e) => setForm({ ...form, data_prazo: e.target.value })} className="w-full mt-1 border border-afj-cream-dark rounded-sm px-3 py-2 text-sm" />
                </div>
              </div>

              <button type="submit" disabled={salvando} className="btn-afj-primary w-full text-sm py-2 rounded-sm flex items-center justify-center gap-2 disabled:opacity-50">
                {salvando ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />} Lançar prazo
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
