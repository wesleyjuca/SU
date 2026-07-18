"use client";
import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Scale, AlertTriangle, Calendar, Clock, Plus, CheckCircle, Loader2, Edit3, X, RefreshCw } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { useToast } from "@/components/ui/Toast";
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

  const toast = useToast();
  const [processo, setProcesso] = useState<Processo | null>(null);
  const [movimentacoes, setMovimentacoes] = useState<Movimentacao[]>([]);
  const [prazos, setPrazos] = useState<Prazo[]>([]);
  const [loading, setLoading] = useState(true);
  const [showMovModal, setShowMovModal] = useState(false);
  const [savingMov, setSavingMov] = useState(false);
  const [cumpridoId, setCumpridoId] = useState<string | null>(null);
  const [movForm, setMovForm] = useState({ descricao: "", tipo: "Despacho", data_movimento: "" });
  const [showPrazoModal, setShowPrazoModal] = useState(false);
  const [savingPrazo, setSavingPrazo] = useState(false);
  const [prazoForm, setPrazoForm] = useState({ descricao: "", tipo: "", data_prazo: "", data_fatal: "", observacoes: "" });
  const [calc, setCalc] = useState({ data_intimacao: "", dias: "", dias_uteis: true });
  const [calcResult, setCalcResult] = useState<{ data_prazo: string; feriados_no_periodo: number; dias_uteis: boolean } | null>(null);
  const [calculando, setCalculando] = useState(false);
  // Equipe do processo (responsável + colaboradores)
  const [colegas, setColegas] = useState<{ id: string; full_name: string; role: string; oab: string | null }[]>([]);
  const [editandoEquipe, setEditandoEquipe] = useState(false);
  const [equipeForm, setEquipeForm] = useState<{ responsavel_id: string; equipe: string[] }>({ responsavel_id: "", equipe: [] });
  const [salvandoEquipe, setSalvandoEquipe] = useState(false);
  const [atualizandoAndamentos, setAtualizandoAndamentos] = useState(false);

  async function atualizarAndamentos() {
    setAtualizandoAndamentos(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/processes/${id}/atualizar-andamentos`, {
        method: "POST", headers: { Authorization: `Bearer ${token}` },
      });
      const d = await res.json().catch(() => ({}));
      if (res.ok) {
        if (d.novos > 0) { toast.success(d.message || "Andamentos atualizados."); fetchAll(); }
        else toast.warning(d.message || "Nenhum andamento novo.");
      } else toast.error(d.detail || "Erro ao atualizar andamentos.");
    } catch { toast.error("Erro de conexão."); }
    finally { setAtualizandoAndamentos(false); }
  }

  async function fetchColegas() {
    const token = localStorage.getItem("afj_access_token");
    const res = await fetch("/api/v1/users/colegas", { headers: { Authorization: `Bearer ${token}` } });
    if (res.ok) setColegas(await res.json());
  }

  function abrirEditorEquipe() {
    setEquipeForm({
      responsavel_id: processo?.responsavel_id ?? "",
      equipe: (processo?.equipe ?? []).filter((m) => m.papel !== "RESPONSAVEL").map((m) => m.id),
    });
    if (colegas.length === 0) fetchColegas();
    setEditandoEquipe(true);
  }

  async function salvarEquipe() {
    if (!equipeForm.responsavel_id) { toast.error("Escolha o advogado responsável."); return; }
    setSalvandoEquipe(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/processes/${id}/equipe`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(equipeForm),
      });
      const d = await res.json().catch(() => ({}));
      if (res.ok) {
        toast.success("Equipe do processo atualizada.");
        setProcesso(d);
        setEditandoEquipe(false);
      } else toast.error(d.detail || "Erro ao salvar a equipe.");
    } catch { toast.error("Erro de conexão."); }
    finally { setSalvandoEquipe(false); }
  }

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
      } else {
        toast.error("Erro ao registrar movimentação. Tente novamente.");
      }
    } finally { setSavingMov(false); }
  }

  async function calcularPrazo() {
    if (!calc.data_intimacao || !calc.dias || Number(calc.dias) < 1) {
      toast.error("Informe a data da intimação e o nº de dias.");
      return;
    }
    setCalculando(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/processes/deadlines/calcular`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ data_intimacao: calc.data_intimacao, dias: Number(calc.dias), dias_uteis: calc.dias_uteis }),
      });
      if (res.ok) {
        const r = await res.json();
        setCalcResult(r);
        setPrazoForm((p) => ({ ...p, data_prazo: r.data_prazo, data_fatal: r.data_prazo }));
      } else {
        toast.error("Não foi possível calcular o prazo.");
      }
    } catch { toast.error("Falha de conexão."); }
    finally { setCalculando(false); }
  }

  async function criarPrazo(e: React.FormEvent) {
    e.preventDefault();
    if (!prazoForm.descricao.trim() || !prazoForm.data_prazo) return;
    setSavingPrazo(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/processes/${id}/deadlines`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          descricao: prazoForm.descricao,
          tipo: prazoForm.tipo || undefined,
          data_prazo: prazoForm.data_prazo,
          data_fatal: prazoForm.data_fatal || undefined,
          observacoes: prazoForm.observacoes || undefined,
        }),
      });
      if (res.ok) {
        setShowPrazoModal(false);
        setPrazoForm({ descricao: "", tipo: "", data_prazo: "", data_fatal: "", observacoes: "" });
        setCalc({ data_intimacao: "", dias: "", dias_uteis: true });
        setCalcResult(null);
        fetchAll();
      } else {
        toast.error("Erro ao salvar prazo. Tente novamente.");
      }
    } finally { setSavingPrazo(false); }
  }

  async function marcarCumprido(prazoId: string) {
    setCumpridoId(prazoId);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/processes/${id}/deadlines/${prazoId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ status: "CUMPRIDO" }),
      });
      if (res.ok) {
        fetchAll();
      } else {
        toast.error("Erro ao marcar prazo como cumprido.");
      }
    } catch {
      toast.error("Erro de conexão. Tente novamente.");
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
              onClick={atualizarAndamentos}
              disabled={atualizandoAndamentos || !processo.numero_cnj}
              title={processo.numero_cnj ? "Buscar andamentos no tribunal (DataJud)" : "Processo sem número CNJ"}
              className="btn-afj-outline rounded-sm flex items-center gap-1.5 text-xs disabled:opacity-50"
            >
              {atualizandoAndamentos ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
              Atualizar andamentos
            </button>
            <button
              onClick={() => setShowPrazoModal(true)}
              className="btn-afj-outline rounded-sm flex items-center gap-1.5 text-xs"
            >
              <Calendar size={12} />
              + Prazo
            </button>
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

          {/* Equipe do processo */}
          <div className="afj-card p-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-semibold text-afj-black text-sm">Equipe do Processo</h2>
              <button onClick={abrirEditorEquipe} className="tap-target text-afj-black/30 hover:text-afj-gold" title="Editar equipe" aria-label="Editar equipe do processo">
                <Edit3 size={14} />
              </button>
            </div>
            {(processo.responsavel_nome || (processo.equipe ?? []).length > 0) ? (
              <div className="space-y-1.5 text-sm">
                {processo.responsavel_nome && (
                  <div className="flex justify-between gap-2">
                    <span className="text-afj-black font-medium text-xs">{processo.responsavel_nome}</span>
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-afj-gold">Responsável</span>
                  </div>
                )}
                {(processo.equipe ?? []).filter((m) => m.papel !== "RESPONSAVEL").map((m) => (
                  <div key={m.id} className="flex justify-between gap-2">
                    <span className="text-afj-black/70 text-xs">{m.nome}</span>
                    <span className="text-[10px] uppercase tracking-wider text-afj-black/35">Colaborador</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-afj-black/40">Nenhum advogado atribuído — clique no lápis para definir a equipe.</p>
            )}
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
          <div className="afj-card p-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-semibold text-afj-black text-sm flex items-center gap-2">
                <Calendar size={14} />
                Prazos Pendentes ({prazosPendentes.length})
              </h2>
              <button
                onClick={() => setShowPrazoModal(true)}
                className="text-xs text-afj-gold hover:underline flex items-center gap-1"
              >
                <Plus size={11} /> Adicionar
              </button>
            </div>
          {prazosPendentes.length > 0 ? (
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
          ) : (
            <p className="text-xs text-afj-black/40 py-2 text-center">Nenhum prazo pendente</p>
          )}
          </div>
        </div>

        {/* Timeline de movimentações */}
        <div className="lg:col-span-2">
          <ProcessTimelineCard movimentacoes={movimentacoes} />
        </div>
      </div>

      {/* Modal: Adicionar Prazo */}
      {showPrazoModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-sm shadow-xl w-full max-w-md max-h-[85vh] overflow-y-auto">
            <div className="flex items-center justify-between px-5 py-4 border-b border-afj-cream-dark">
              <h2 className="font-semibold text-afj-black">Adicionar Prazo</h2>
              <button onClick={() => setShowPrazoModal(false)} className="text-afj-black/40 hover:text-afj-black">
                <X size={18} />
              </button>
            </div>
            <form onSubmit={criarPrazo} className="p-5 space-y-4">
              <div>
                <label className="text-xs text-afj-black/60 block mb-1">Descrição *</label>
                <input
                  required
                  value={prazoForm.descricao}
                  onChange={(e) => setPrazoForm({ ...prazoForm, descricao: e.target.value })}
                  placeholder="Ex: Prazo para contestação"
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                />
              </div>
              {/* Calculadora de prazo — dias úteis + feriados forenses (CPC art. 219/224) */}
              <div className="border border-afj-gold/30 bg-afj-gold/5 rounded-sm p-3 space-y-2">
                <p className="text-xs font-semibold text-afj-black/70 flex items-center gap-1.5">
                  <Calendar size={13} className="text-afj-gold" /> Calcular por intimação
                </p>
                <div className="grid grid-cols-3 gap-2">
                  <div className="col-span-1">
                    <label className="text-[11px] text-afj-black/50 block mb-0.5">Intimação/publicação</label>
                    <input type="date" value={calc.data_intimacao}
                      onChange={(e) => setCalc({ ...calc, data_intimacao: e.target.value })}
                      className="w-full border border-afj-cream-dark rounded-sm px-2 py-1.5 text-sm bg-white" />
                  </div>
                  <div>
                    <label className="text-[11px] text-afj-black/50 block mb-0.5">Prazo (dias)</label>
                    <input type="number" min={1} value={calc.dias}
                      onChange={(e) => setCalc({ ...calc, dias: e.target.value })}
                      placeholder="15" className="w-full border border-afj-cream-dark rounded-sm px-2 py-1.5 text-sm bg-white" />
                  </div>
                  <div className="flex items-end">
                    <label className="flex items-center gap-1.5 text-[11px] text-afj-black/60 pb-1.5 cursor-pointer">
                      <input type="checkbox" checked={calc.dias_uteis}
                        onChange={(e) => setCalc({ ...calc, dias_uteis: e.target.checked })} className="accent-afj-gold" />
                      Dias úteis
                    </label>
                  </div>
                </div>
                <button type="button" onClick={calcularPrazo} disabled={calculando}
                  className="btn-afj-outline text-xs py-1.5 px-3 rounded-sm w-full disabled:opacity-50">
                  {calculando ? "Calculando..." : "Calcular data do prazo"}
                </button>
                {calcResult && (
                  <p className="text-xs text-afj-black/70 bg-white border border-afj-gold/30 rounded-sm px-2 py-1.5">
                    Vence em <strong>{new Date(calcResult.data_prazo + "T00:00:00").toLocaleDateString("pt-BR")}</strong>
                    {" "}({calc.dias} {calcResult.dias_uteis ? "dias úteis" : "dias corridos"}
                    {calcResult.feriados_no_periodo > 0 ? `, ${calcResult.feriados_no_periodo} feriado(s)/não-úteis no período` : ""}).
                    <span className="block text-[10px] text-afj-black/40 mt-0.5">Confira feriados locais da comarca — o cálculo usa feriados nacionais + recesso.</span>
                  </p>
                )}
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">Tipo</label>
                  <select
                    value={prazoForm.tipo}
                    onChange={(e) => setPrazoForm({ ...prazoForm, tipo: e.target.value })}
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                  >
                    <option value="">Selecionar...</option>
                    {["RECURSO", "CONTESTACAO", "MANIFESTACAO", "AUDIENCIA", "PERICIA", "OUTRO"].map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">Data do Prazo *</label>
                  <input
                    required
                    type="date"
                    value={prazoForm.data_prazo}
                    onChange={(e) => setPrazoForm({ ...prazoForm, data_prazo: e.target.value })}
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                  />
                </div>
              </div>
              <div>
                <label className="text-xs text-afj-black/60 block mb-1">Data Fatal (opcional)</label>
                <input
                  type="date"
                  value={prazoForm.data_fatal}
                  onChange={(e) => setPrazoForm({ ...prazoForm, data_fatal: e.target.value })}
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                />
              </div>
              <div>
                <label className="text-xs text-afj-black/60 block mb-1">Observações</label>
                <textarea
                  value={prazoForm.observacoes}
                  onChange={(e) => setPrazoForm({ ...prazoForm, observacoes: e.target.value })}
                  rows={2}
                  placeholder="Observações adicionais..."
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold resize-none"
                />
              </div>
              <div className="flex gap-3 pt-1">
                <button type="button" onClick={() => setShowPrazoModal(false)} className="flex-1 btn-afj-outline rounded-sm">
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={savingPrazo || !prazoForm.descricao.trim() || !prazoForm.data_prazo}
                  className="flex-1 btn-afj-primary rounded-sm flex items-center justify-center gap-2 disabled:opacity-40"
                >
                  {savingPrazo ? <Loader2 size={13} className="animate-spin" /> : <Calendar size={13} />}
                  Salvar Prazo
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Registrar Movimentação */}
      {showMovModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-sm shadow-xl w-full max-w-md max-h-[85vh] overflow-y-auto">
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

      {/* Modal: equipe do processo */}
      {editandoEquipe && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => !salvandoEquipe && setEditandoEquipe(false)}>
          <div className="bg-white rounded-sm p-6 w-full max-w-md shadow-2xl max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <h2 className="font-display text-lg font-semibold text-afj-black mb-1">Equipe do processo</h2>
            <p className="text-xs text-afj-black/45 mb-4">Defina o responsável e os colaboradores — cada advogado vê os próprios processos em &quot;Meus&quot;.</p>

            <label className="block text-xs font-semibold text-afj-black/50 uppercase tracking-wider mb-1">Advogado responsável</label>
            <select
              value={equipeForm.responsavel_id}
              onChange={(e) => setEquipeForm((f) => ({ ...f, responsavel_id: e.target.value, equipe: f.equipe.filter((id2) => id2 !== e.target.value) }))}
              className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm bg-white focus:outline-none focus:border-afj-gold mb-4"
            >
              <option value="">Selecione…</option>
              {colegas.map((c) => (
                <option key={c.id} value={c.id}>{c.full_name}{c.oab ? ` — OAB ${c.oab}` : ""}</option>
              ))}
            </select>

            <label className="block text-xs font-semibold text-afj-black/50 uppercase tracking-wider mb-1">Colaboradores</label>
            <div className="border border-afj-cream-dark rounded-sm max-h-48 overflow-y-auto mb-5 divide-y divide-afj-cream-dark/60">
              {colegas.filter((c) => c.id !== equipeForm.responsavel_id).map((c) => (
                <label key={c.id} className="flex items-center gap-2 px-3 py-2 text-sm cursor-pointer hover:bg-afj-cream/50">
                  <input
                    type="checkbox"
                    className="accent-afj-gold"
                    checked={equipeForm.equipe.includes(c.id)}
                    onChange={(e) =>
                      setEquipeForm((f) => ({
                        ...f,
                        equipe: e.target.checked ? [...f.equipe, c.id] : f.equipe.filter((id2) => id2 !== c.id),
                      }))
                    }
                  />
                  <span className="text-afj-black/80">{c.full_name}</span>
                  <span className="text-[10px] text-afj-black/35 ml-auto uppercase">{c.role}</span>
                </label>
              ))}
              {colegas.length === 0 && <p className="text-xs text-afj-black/40 p-3">Carregando colaboradores…</p>}
            </div>

            <div className="flex gap-2 justify-end">
              <button onClick={() => setEditandoEquipe(false)} disabled={salvandoEquipe} className="btn-afj-outline text-sm py-2 px-4 rounded-sm">Cancelar</button>
              <button onClick={salvarEquipe} disabled={salvandoEquipe} className="btn-afj-primary text-sm py-2 px-4 rounded-sm flex items-center gap-2">
                {salvandoEquipe ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle size={14} />} Salvar equipe
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
