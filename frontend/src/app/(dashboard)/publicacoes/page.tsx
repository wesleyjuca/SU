"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { Newspaper, RefreshCw, Check, X, Scale, ExternalLink, Loader2, Sparkles } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { useToast } from "@/components/ui/Toast";
import { useUserStore } from "@/store";

interface Publicacao {
  id: string;
  process_id: string | null;
  oab: string | null;
  numero_cnj: string | null;
  texto: string;
  data_disponibilizacao: string | null;
  tribunal: string | null;
  tipo_comunicacao: string | null;
  orgao: string | null;
  link: string | null;
  status: string;
}

const STATUS_BADGE: Record<string, string> = {
  NOVA: "bg-amber-50 text-amber-700 border-amber-200",
  TRIADA: "bg-green-50 text-green-700 border-green-200",
  IGNORADA: "bg-gray-50 text-gray-500 border-gray-200",
};
const TIPOS_PRAZO = ["CONTESTACAO", "RECURSO", "MANIFESTACAO", "EMBARGOS", "CONTRARRAZOES", "CUMPRIMENTO", "OUTROS"];

export default function PublicacoesPage() {
  const toast = useToast();
  const { user } = useUserStore();
  const canManage = ["ADMIN", "SOCIO", "GESTOR"].includes(user?.role ?? "");
  const [items, setItems] = useState<Publicacao[]>([]);
  const [loading, setLoading] = useState(true);
  const [filtro, setFiltro] = useState("NOVA");
  const [somenteMeus, setSomenteMeus] = useState(false);
  const [varrendo, setVarrendo] = useState(false);
  const [triar, setTriar] = useState<Publicacao | null>(null);
  const [tipo, setTipo] = useState("MANIFESTACAO");
  const [dias, setDias] = useState(15);
  const [salvando, setSalvando] = useState(false);
  const [sugestao, setSugestao] = useState<{ confianca: string; justificativa: string } | null>(null);
  const [sugerindo, setSugerindo] = useState(false);

  const token = () => (typeof window !== "undefined" ? localStorage.getItem("afj_access_token") : null);

  useEffect(() => { fetchItems(); }, [filtro, somenteMeus]);

  async function fetchItems() {
    setLoading(true);
    try {
      const qp = new URLSearchParams();
      if (filtro) qp.set("status", filtro);
      if (somenteMeus) qp.set("mine", "true");
      const params = qp.toString() ? `?${qp}` : "";
      const res = await fetch(`/api/v1/publicacoes${params}`, { headers: { Authorization: `Bearer ${token()}` } });
      if (res.ok) setItems(await res.json());
    } finally { setLoading(false); }
  }

  async function varrer() {
    setVarrendo(true);
    try {
      const res = await fetch("/api/v1/publicacoes/varrer", { method: "POST", headers: { Authorization: `Bearer ${token()}` } });
      const d = await res.json().catch(() => ({}));
      if (res.ok) {
        toast.success(`Varredura concluída: ${d.intimacoes_novas ?? 0} nova(s), ${d.casadas_com_processo ?? 0} vinculada(s).`);
        fetchItems();
      } else toast.error(d.detail || "Erro na varredura.");
    } catch { toast.error("Erro de conexão."); }
    finally { setVarrendo(false); }
  }

  function abrirTriagem(p: Publicacao) {
    setTriar(p);
    setTipo("MANIFESTACAO");
    setDias(15);
    setSugestao(null);
    setSugerindo(true);
    fetch(`/api/v1/publicacoes/${p.id}/sugestao-prazo`, { method: "POST", headers: { Authorization: `Bearer ${token()}` } })
      .then((res) => (res.ok ? res.json() : null))
      .then((d) => {
        if (!d?.ok) return;
        setTipo(d.tipo);
        setDias(d.dias);
        setSugestao({ confianca: d.confianca, justificativa: d.justificativa });
      })
      .catch(() => {})
      .finally(() => setSugerindo(false));
  }

  async function confirmarTriagem() {
    if (!triar) return;
    setSalvando(true);
    try {
      const res = await fetch(`/api/v1/publicacoes/${triar.id}/triagem`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token()}` },
        body: JSON.stringify({ tipo, dias, dias_uteis: true }),
      });
      const d = await res.json().catch(() => ({}));
      if (res.ok) {
        toast.success(`Prazo criado para ${new Date(d.data_prazo + "T00:00:00").toLocaleDateString("pt-BR")}.`);
        setTriar(null);
        fetchItems();
      } else toast.error(d.detail || "Erro ao criar prazo.");
    } catch { toast.error("Erro de conexão."); }
    finally { setSalvando(false); }
  }

  async function ignorar(id: string) {
    try {
      const res = await fetch(`/api/v1/publicacoes/${id}/ignorar`, { method: "POST", headers: { Authorization: `Bearer ${token()}` } });
      if (res.ok) { toast.success("Intimação arquivada."); fetchItems(); }
      else toast.error("Erro ao arquivar.");
    } catch { toast.error("Erro de conexão."); }
  }

  return (
    <div className="max-w-[1600px] mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Publicações" }]} />
      <div className="afj-page-header">
        <div>
          <h1 className="afj-page-title flex items-center gap-2">
            <Newspaper size={22} className="text-afj-gold" /> Publicações & Intimações
          </h1>
          <p className="text-afj-black/45 text-sm mt-1">
            Captura automática no Diário de Justiça Eletrônico (DJEN/Comunica) pelas OABs do escritório. Cada intimação vira andamento no processo; confirme o tipo e os dias para gerar o prazo.
          </p>
        </div>
        {canManage && (
          <button onClick={varrer} disabled={varrendo} className="btn-afj-outline rounded-sm flex items-center gap-2 disabled:opacity-50">
            {varrendo ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            {varrendo ? "Varrendo..." : "Varrer agora"}
          </button>
        )}
      </div>

      <div className="flex gap-2 flex-wrap items-center">
        {[["NOVA", "A triar"], ["TRIADA", "Triadas"], ["IGNORADA", "Arquivadas"], ["", "Todas"]].map(([v, l]) => (
          <button key={v} onClick={() => setFiltro(v)}
            className={`text-xs px-3 py-1.5 rounded-sm border transition-colors ${filtro === v ? "bg-afj-gold/10 border-afj-gold/40 text-afj-gold" : "border-afj-cream-dark text-afj-black/50 hover:border-afj-gold/30"}`}>
            {l}
          </button>
        ))}
        <span className="w-px h-5 bg-afj-cream-dark mx-1" />
        <button onClick={() => setSomenteMeus(!somenteMeus)}
          className={`text-xs px-3 py-1.5 rounded-sm border transition-colors ${somenteMeus ? "bg-afj-gold/10 border-afj-gold/40 text-afj-gold font-semibold" : "border-afj-cream-dark text-afj-black/50 hover:border-afj-gold/30"}`}>
          Meus processos
        </button>
      </div>

      {loading ? (
        <div className="space-y-3">{Array.from({ length: 4 }).map((_, i) => <div key={i} className="afj-card h-28 animate-pulse bg-afj-cream-dark/40" />)}</div>
      ) : items.length === 0 ? (
        <div className="afj-card p-12 text-center">
          <Newspaper className="mx-auto text-afj-black/20 mb-3" size={40} />
          <p className="font-semibold text-afj-black">Nenhuma publicação {filtro === "NOVA" ? "a triar" : ""}</p>
          <p className="text-afj-black/40 text-sm mt-1">Intimações capturadas no DJe aparecerão aqui. Cadastre a OAB dos advogados para o monitoramento.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((p) => (
            <div key={p.id} className="afj-card p-4">
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-sm border ${STATUS_BADGE[p.status] ?? "badge-arquivado"}`}>{p.status}</span>
                  {p.tribunal && <span className="text-xs text-afj-black/50">{p.tribunal}</span>}
                  {p.tipo_comunicacao && <span className="text-xs text-afj-black/40">· {p.tipo_comunicacao}</span>}
                  {p.data_disponibilizacao && <span className="text-xs text-afj-black/40">· {new Date(p.data_disponibilizacao + "T00:00:00").toLocaleDateString("pt-BR")}</span>}
                </div>
                <div className="flex items-center gap-3">
                  {p.process_id ? (
                    <Link href={`/processos/${p.process_id}`} className="text-xs text-afj-gold hover:underline flex items-center gap-1">
                      <Scale size={12} /> {p.numero_cnj}
                    </Link>
                  ) : (
                    <span className="text-xs text-afj-black/35" title="Processo não encontrado no sistema">{p.numero_cnj || "Sem processo"} (não vinculado)</span>
                  )}
                  {p.link && <a href={p.link} target="_blank" rel="noopener noreferrer" className="text-afj-black/30 hover:text-afj-gold" title="Abrir no DJe"><ExternalLink size={13} /></a>}
                </div>
              </div>
              {p.orgao && <p className="text-xs text-afj-black/45 mt-2">{p.orgao}</p>}
              <p className="text-sm text-afj-black/70 mt-2 leading-relaxed line-clamp-4 whitespace-pre-wrap">{p.texto}</p>
              {p.status === "NOVA" && (
                <div className="flex items-center gap-2 mt-3">
                  <button
                    onClick={() => abrirTriagem(p)}
                    disabled={!p.process_id}
                    title={p.process_id ? "Gerar prazo" : "Vincule o processo (número CNJ) antes de gerar o prazo"}
                    className="btn-afj-primary text-xs py-1.5 px-3 rounded-sm flex items-center gap-1 disabled:opacity-40">
                    <Check size={13} /> Triar (gerar prazo)
                  </button>
                  <button onClick={() => ignorar(p.id)} className="btn-afj-outline text-xs py-1.5 px-3 rounded-sm flex items-center gap-1">
                    <X size={13} /> Ignorar
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Modal de triagem */}
      {triar && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50" onClick={() => !salvando && setTriar(null)}>
          <div className="afj-card w-full max-w-md p-6 max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <h2 className="font-display text-lg font-semibold text-afj-black mb-1">Gerar prazo da intimação</h2>
            <p className="text-xs text-afj-black/45 mb-4">
              {triar.numero_cnj} · disponibilizado em {triar.data_disponibilizacao ? new Date(triar.data_disponibilizacao + "T00:00:00").toLocaleDateString("pt-BR") : "—"}. O prazo é calculado em dias úteis (CPC art. 219) com feriados forenses.
            </p>
            {sugerindo && (
              <p className="text-xs text-afj-black/40 flex items-center gap-1.5 mb-3">
                <Loader2 size={12} className="animate-spin" /> Consultando sugestão da IA...
              </p>
            )}
            {sugestao && (
              <p className="text-xs text-afj-gold/90 bg-afj-gold/5 border border-afj-gold/20 rounded-sm px-2.5 py-1.5 mb-3 flex items-start gap-1.5">
                <Sparkles size={12} className="flex-shrink-0 mt-0.5" />
                <span>Sugestão da IA (confiança: {sugestao.confianca}) — revise antes de confirmar. {sugestao.justificativa}</span>
              </p>
            )}
            <label className="block text-xs font-semibold text-afj-black/50 uppercase tracking-wider mb-1">Tipo de prazo</label>
            <select value={tipo} onChange={(e) => setTipo(e.target.value)} className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm bg-white focus:outline-none focus:border-afj-gold mb-4">
              {TIPOS_PRAZO.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <label className="block text-xs font-semibold text-afj-black/50 uppercase tracking-wider mb-1">Dias (úteis)</label>
            <input type="number" min={1} max={180} value={dias} onChange={(e) => setDias(parseInt(e.target.value) || 1)} className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm bg-white focus:outline-none focus:border-afj-gold mb-5" />
            <div className="flex gap-2 justify-end">
              <button onClick={() => setTriar(null)} disabled={salvando} className="btn-afj-outline text-sm py-2 px-4 rounded-sm">Cancelar</button>
              <button onClick={confirmarTriagem} disabled={salvando} className="btn-afj-primary text-sm py-2 px-4 rounded-sm flex items-center gap-2">
                {salvando ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />} Criar prazo
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
