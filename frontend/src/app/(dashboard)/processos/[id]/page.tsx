"use client";
import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Scale, AlertTriangle, Calendar, Clock, Plus, CheckCircle, Loader2, Edit3, X } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { ProcessTimelineCard } from "@/components/processes/ProcessTimeline";
import type { Processo, Movimentacao, Prazo } from "@/types";

const SITUACAO_STYLE: Record<string, string> = {
  ATIVO: "badge-ativo",
  SUSPENSO: "badge-pendente",
  ARQUIVADO: "badge-arquivado",
  ENCERRADO: "badge-arquivado",
};

const TIPOS_MOVIMENTO = [
  "Despacho", "Decisão Interlocutória", "Sentença", "Acórdão",
  "Petição", "Juntada", "Citação", "Intimação", "Audiência",
  "Perícia", "Outro",
];

function diasPara(data: string | null): number | null {
  if (!data) return null;
  return Math.ceil((new Date(data).getTime() - Date.now()) / 86400000);
}

export default function ProcessoDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [processo, setProcesso] = useState<Processo | null>(null);
  const [movimentacoes, setMovimentacoes] = useState<Movimentacao[]>([]);
  const [prazos, setPrazos] = useState<Prazo[]>([]);
  const [loading, setLoading] = useState(true);
  const [showMovModal, setShowMovModal] = useState(false);
  const [savingMov, setSavingMov] = useState(false);
  const [cumpridoId, setCumpridoId] = useState<string | null>(null);
  const [movForm, setMovForm] = useState({ descricao: "", tipo: "Despacho", data_movimento: "" });

  useEffect(() => {
    if (id) fetchAll();
  }, [id]);

  async function fetchAll() {
    const token = localStorage.getItem("afj_access_token");
    const headers = { Authorization: `Bearer ${token}` };
    setLoading(true);
    try {
      const [pRes, mRes, dRes] = await Promise.all([
        fetch(`/api/v1/processes/${id}`, { headers }),
        fetch(`/api/v1/processes/${id}/movements`, { headers }),
        fetch(`/api/v1/processes/${id}/deadlines`, { headers }),
      ]);
      if (pRes.ok) setProcesso(await pRes.json());
      if (mRes.ok) setMovimentacoes(await mRes.json());
      if (dRes.ok) setPrazos(await dRes.json());
    } finally { setLoading(false); }
  }

  async function registrarMovimentacao(e: React.FormEvent) {
    e.preventDefault();
    if (!movForm.descricao.trim()) return;
    setSavingMov(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/processes/${id}/movements`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          descricao: movForm.descricao,
          tipo: movForm.tipo,
          data_movimento: movForm.data_movimento || undefined,
        }),
      });
      if (res.ok) {
        setShowMovModal(false);
        setMovForm({ descricao: "", tipo: "Despacho", data_movimento: "" });
        fetchAll();
      }
    } finally { setSavingMov(false); }
  }

  async function marcarCumprido(prazoId: string) {
    setCumpridoId(prazoId);
    try {
      const token = localStorage.getItem("afj_access_token");
      await fetch(`/api/v1/processes/${id}/deadlines/${prazoId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ status: "CUMPRIDO" }),
      });
      fetchAll();
    } finally { setCumpridoId(null); }
  }

  if (loading) return (
    <div className="max-w-7xl mx-auto space-y-4">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Processos", href: "/processos" }, { label: "..." }]} />
      <div className="h-8 bg-afj-cream-dark rounded animate-pulse w-64" />
      <div className="afj-card p-6 space-y-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-6 bg-afj-cream-dark rounded animate-pulse" />
        ))}
      </div>
    </div>
  );

  if (!processo) return (
    <div className="max-w-7xl mx-auto">
      <div className="afj-card p-12 text-center">
        <Scale className="mx-auto text-afj-black/20 mb-3" size={40} />
        <p className="font-semibold text-afj-black">Processo não encontrado</p>
        <button onClick={() => router.back()} className="btn-afj-outline rounded-sm mt-4 text-sm">Voltar</button>
      </div>
    </div>
  );

  const proximoPrazo = diasPara(processo.proximo_prazo_at);
  const prazosPendentes = prazos.filter((p) => p.status === "PENDENTE");

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <Breadcrumb crumbs={[
        { label: "Dashboard", href: "/dashboard" },
        { label: "Processos", href: "/processos" },
        { label: processo.numero_cnj ?? "Processo" },
      ]} />

      {/* Header */}
      <div>
        <button onClick={() => router.back()} className="flex items-center gap-2 text-sm text-afj-black/50 hover:text-afj-black mb-3">
          <ArrowLeft size={14} />
          Voltar para Processos
        </button>
        <div className="flex items-start justify-between">
          <div>
            <h1 className="font-display text-2xl font-semibold text-afj-black font-mono">
              {processo.numero_cnj || "Sem número CNJ"}
            </h1>
            <p className="text-afj-black/50 text-sm mt-1">{processo.tribunal}{processo.vara ? ` · ${processo.vara}` : ""}</p>
          </div>
          <div className="flex items-center gap-2">
            <span className={SITUACAO_STYLE[processo.situacao] ?? "badge-arquivado"}>{processo.situacao}</span>
            {processo.monitoring_active && (
              <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full flex items-center gap-1">
                <span className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse" />
                Monitorado
              </span>
            )}
            <button
              onClick={() => setShowMovModal(true)}
              className="btn-afj-primary rounded-sm flex items-center gap-1.5 text-xs ml-2"
            >
              <Plus size={12} />
              Registrar Movimentação
            </button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Coluna esquerda: info + prazos */}
        <div className="space-y-4">
          {/* Dados básicos */}
          <div className="afj-card p-4">
            <h2 className="font-semibold text-afj-black text-sm mb-3">Informações do Processo</h2>
            <div className="space-y-2 text-sm">
              {[
                { label: "Área do Direito", value: processo.area_direito },
                { label: "Tipo de Ação", value: processo.tipo_acao },
                { label: "Fase", value: processo.fase },
                { label: "Polo", value: processo.polo },
                { label: "Parte Contrária", value: processo.parte_contraria },
                { label: "OAB Responsável", value: processo.oab_responsavel },
                { label: "Comarca / UF", value: processo.comarca ? `${processo.comarca} / ${processo.uf}` : processo.uf },
                {
                  label: "Valor da Causa",
                  value: processo.valor_causa
                    ? `R$ ${processo.valor_causa.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`
                    : null,
                },
                {
                  label: "Distribuído em",
                  value: processo.distribuicao_data
                    ? new Date(processo.distribuicao_data).toLocaleDateString("pt-BR")
                    : null,
                },
              ].map(({ label, value }) => value && (
                <div key={label} className="flex justify-between gap-2">
                  <span className="text-afj-black/50 flex-shrink-0">{label}</span>
                  <span className="text-afj-black text-right font-medium text-xs">{value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Próximo prazo */}
          {processo.proximo_prazo_at && (
            <div className={`afj-card p-4 border-l-4 ${
              proximoPrazo !== null && proximoPrazo < 0 ? "border-l-red-500" :
              proximoPrazo !== null && proximoPrazo <= 3 ? "border-l-red-400" :
              proximoPrazo !== null && proximoPrazo <= 7 ? "border-l-amber-400" : "border-l-afj-gold"
            }`}>
              <div className="flex items-center gap-2 mb-1">
                <Clock size={14} className="text-afj-black/50" />
                <span className="text-xs text-afj-black/50">Próximo Prazo</span>
              </div>
              <p className="font-bold text-afj-black">
                {new Date(processo.proximo_prazo_at).toLocaleDateString("pt-BR")}
              </p>
              {proximoPrazo !== null && (
                <p className={`text-sm flex items-center gap-1 mt-1 ${
                  proximoPrazo < 0 ? "text-red-600 font-bold" :
                  proximoPrazo <= 3 ? "text-red-500 font-semibold" :
                  proximoPrazo <= 7 ? "text-amber-600" : "text-afj-black/50"
                }`}>
                  {proximoPrazo < 0 ? <AlertTriangle size={12} /> : null}
                  {proximoPrazo < 0
                    ? `Venceu há ${Math.abs(proximoPrazo)} dias`
                    : `${proximoPrazo} dias restantes`}
                </p>
              )}
            </div>
          )}

          {/* Prazos pendentes */}
          {prazosPendentes.length > 0 && (
            <div className="afj-card p-4">
              <h2 className="font-semibold text-afj-black text-sm mb-3 flex items-center gap-2">
                <Calendar size={14} />
                Prazos Pendentes ({prazosPendentes.length})
              </h2>
              <div className="space-y-2">
                {prazosPendentes.map((p) => {
                  const dias = diasPara(p.data_prazo);
                  return (
                    <div key={p.id} className="text-xs border border-afj-cream-dark rounded-sm p-2">
                      <p className="font-medium text-afj-black">{p.descricao}</p>
                      <div className="flex items-center justify-between mt-1.5">
                        <span className="text-afj-black/50">{new Date(p.data_prazo).toLocaleDateString("pt-BR")}</span>
                        <div className="flex items-center gap-2">
                          {dias !== null && (
                            <span className={`font-semibold ${dias < 0 ? "text-red-600" : dias <= 3 ? "text-red-500" : dias <= 7 ? "text-amber-600" : "text-afj-black/40"}`}>
                              {dias < 0 ? `${Math.abs(dias)}d atraso` : `${dias}d`}
                            </span>
                          )}
                          <button
                            onClick={() => marcarCumprido(p.id)}
                            disabled={cumpridoId === p.id}
                            className="text-green-600 hover:text-green-700 disabled:opacity-40 flex items-center gap-0.5"
                            title="Marcar como cumprido"
                          >
                            {cumpridoId === p.id
                              ? <Loader2 size={12} className="animate-spin" />
                              : <CheckCircle size={12} />}
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Timeline de movimentações */}
        <div className="lg:col-span-2">
          <ProcessTimelineCard movimentacoes={movimentacoes} />
        </div>
      </div>

      {/* Modal: Registrar Movimentação */}
      {showMovModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-sm shadow-xl w-full max-w-md">
            <div className="flex items-center justify-between px-5 py-4 border-b border-afj-cream-dark">
              <h2 className="font-semibold text-afj-black">Registrar Movimentação</h2>
              <button onClick={() => setShowMovModal(false)} className="text-afj-black/40 hover:text-afj-black">
                <X size={18} />
              </button>
            </div>
            <form onSubmit={registrarMovimentacao} className="p-5 space-y-4">
              <div>
                <label className="text-xs text-afj-black/60 block mb-1">Tipo</label>
                <select
                  value={movForm.tipo}
                  onChange={(e) => setMovForm({ ...movForm, tipo: e.target.value })}
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                >
                  {TIPOS_MOVIMENTO.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs text-afj-black/60 block mb-1">Data da Movimentação</label>
                <input
                  type="date"
                  value={movForm.data_movimento}
                  onChange={(e) => setMovForm({ ...movForm, data_movimento: e.target.value })}
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                />
              </div>
              <div>
                <label className="text-xs text-afj-black/60 block mb-1">Descrição *</label>
                <textarea
                  required
                  value={movForm.descricao}
                  onChange={(e) => setMovForm({ ...movForm, descricao: e.target.value })}
                  rows={4}
                  placeholder="Descreva o andamento processual..."
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold resize-none"
                />
              </div>
              <div className="flex gap-3 pt-1">
                <button
                  type="button"
                  onClick={() => setShowMovModal(false)}
                  className="flex-1 btn-afj-outline rounded-sm"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={savingMov || !movForm.descricao.trim()}
                  className="flex-1 btn-afj-primary rounded-sm flex items-center justify-center gap-2 disabled:opacity-40"
                >
                  {savingMov ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
                  Registrar
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
