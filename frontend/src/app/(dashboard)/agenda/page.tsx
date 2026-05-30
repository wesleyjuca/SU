"use client";
import { useState, useEffect } from "react";
import { CalendarClock, Calendar, AlertTriangle, CheckCircle, Clock, Loader2, RefreshCw } from "lucide-react";
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

export default function AgendaPage() {
  const toast = useToast();
  const [items, setItems] = useState<AgendaItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [dias, setDias] = useState(30);
  const [completing, setCompleting] = useState<string | null>(null);

  useEffect(() => { fetchAgenda(); }, [dias]);

  async function fetchAgenda() {
    setLoading(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/processes/agenda?dias=${dias}`, {
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
          const urgency = urgencyLabel(dias);
          return (
            <div
              key={item.id}
              className={`afj-card p-4 border-l-4 ${urgencyClass(dias)} hover:shadow-md transition-shadow animate-fade-in`}
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
                  </div>
                </div>
                <div className="flex items-center gap-3 flex-shrink-0">
                  <div className="text-right">
                    <p className="text-xs text-afj-black/50">
                      {item.data_prazo ? new Date(item.data_prazo).toLocaleDateString("pt-BR") : "—"}
                    </p>
                    {urgency && <p className={`text-xs ${urgency.cls}`}>{urgency.text}</p>}
                  </div>
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
        <div className="flex items-center gap-2">
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
    </div>
  );
}
