"use client";
import { useState, useEffect, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Scale, AlertTriangle, Calendar, Clock, Plus, CheckCircle, Loader2, Edit3, X, RefreshCw, Users, Trash2 } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { useToast } from "@/components/ui/Toast";
import { ProcessTimelineCard } from "@/components/processes/ProcessTimeline";
import type { Processo, Movimentacao, Prazo, Parte } from "@/types";
import { AREAS_DIREITO } from "@/lib/constants";
import { useConfirmDialog } from "@/hooks/useConfirmDialog";
import { PrazoCalculator } from "@/components/prazos/PrazoCalculator";

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

const TIPOS_PARTE = ["AUTOR", "REU", "ADVOGADO", "JUIZ", "MP", "PARTE"];
const PARTE_FORM_VAZIO = { nome: "", tipo: "AUTOR", polo: "", cpf_cnpj: "", oab: "", client_id: "" };

const SITUACOES_PROCESSO = ["ATIVO", "SUSPENSO", "ARQUIVADO", "ENCERRADO"];
const PROCESSO_FORM_VAZIO = {
  numero_cnj: "", tribunal: "", vara: "", comarca: "", uf: "", tipo_acao: "",
  area_direito: "", fase: "", situacao: "ATIVO", desfecho: "", tese_id: "", valor_causa: "",
  parte_contraria: "", polo: "", oab_responsavel: "", descricao: "", monitoring_active: true,
};

function diasPara(data: string | null): number | null {
  if (!data) return null;
  return Math.ceil((new Date(data).getTime() - Date.now()) / 86400000);
}

export default function ProcessoDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const toast = useToast();
  const { ask, confirmDialog } = useConfirmDialog();
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
  // Equipe do processo (responsável + colaboradores)
  const [colegas, setColegas] = useState<{ id: string; full_name: string; role: string; oab: string | null }[]>([]);
  const [editandoEquipe, setEditandoEquipe] = useState(false);
  const [equipeForm, setEquipeForm] = useState<{ responsavel_id: string; equipe: string[] }>({ responsavel_id: "", equipe: [] });
  const [salvandoEquipe, setSalvandoEquipe] = useState(false);
  const [atualizandoAndamentos, setAtualizandoAndamentos] = useState(false);
  const [partes, setPartes] = useState<Parte[]>([]);
  const [atualizandoPartes, setAtualizandoPartes] = useState(false);
  const [showParteModal, setShowParteModal] = useState(false);
  const [savingParte, setSavingParte] = useState(false);
  const [editingParteId, setEditingParteId] = useState<string | null>(null);
  const [parteForm, setParteForm] = useState(PARTE_FORM_VAZIO);
  const [excluindoParteId, setExcluindoParteId] = useState<string | null>(null);
  // Fase 179 — vincular a parte a um cliente já cadastrado (busca com debounce,
  // mesmo padrão de processos/page.tsx)
  const [clienteVinculadoNome, setClienteVinculadoNome] = useState<string | null>(null);
  const [clienteQuery, setClienteQuery] = useState("");
  const [clienteResultados, setClienteResultados] = useState<{ id: string; nome_completo: string; cpf: string | null; cnpj: string | null }[]>([]);
  const [buscandoCliente, setBuscandoCliente] = useState(false);
  const clienteDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Fase 181 — vínculo automático por CPF/CNPJ exato + sugestão por nome,
  // a partir dos próprios campos "Nome"/"CPF/CNPJ" da parte (sem precisar
  // abrir a busca manual acima).
  const [sugestoesParte, setSugestoesParte] = useState<{ id: string; nome_completo: string }[]>([]);
  const [vinculoAutomatico, setVinculoAutomatico] = useState(false);
  const [clienteAutoDismissado, setClienteAutoDismissado] = useState<string | null>(null);
  const matchDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [showProcessoModal, setShowProcessoModal] = useState(false);
  const [savingProcesso, setSavingProcesso] = useState(false);
  const [processoForm, setProcessoForm] = useState(PROCESSO_FORM_VAZIO);
  const [teses, setTeses] = useState<{ id: string; nome: string }[]>([]);

  async function fetchTeses() {
    const token = localStorage.getItem("afj_access_token");
    const res = await fetch("/api/v1/teses", { headers: { Authorization: `Bearer ${token}` } });
    if (res.ok) setTeses(await res.json());
  }

  function abrirEditorProcesso() {
    if (!processo) return;
    setProcessoForm({
      numero_cnj: processo.numero_cnj ?? "",
      tribunal: processo.tribunal ?? "",
      vara: processo.vara ?? "",
      comarca: processo.comarca ?? "",
      uf: processo.uf ?? "",
      tipo_acao: processo.tipo_acao ?? "",
      area_direito: processo.area_direito ?? "",
      fase: processo.fase ?? "",
      situacao: processo.situacao ?? "ATIVO",
      desfecho: processo.desfecho ?? "",
      tese_id: processo.tese_id ?? "",
      valor_causa: processo.valor_causa != null ? String(processo.valor_causa) : "",
      parte_contraria: processo.parte_contraria ?? "",
      polo: processo.polo ?? "",
      oab_responsavel: processo.oab_responsavel ?? "",
      descricao: processo.descricao ?? "",
      monitoring_active: processo.monitoring_active,
    });
    if (teses.length === 0) fetchTeses();
    setShowProcessoModal(true);
  }

  async function salvarProcesso(e: React.FormEvent) {
    e.preventDefault();
    setSavingProcesso(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/processes/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          numero_cnj: processoForm.numero_cnj || undefined,
          tribunal: processoForm.tribunal || undefined,
          vara: processoForm.vara || undefined,
          comarca: processoForm.comarca || undefined,
          uf: processoForm.uf || undefined,
          tipo_acao: processoForm.tipo_acao || undefined,
          area_direito: processoForm.area_direito || undefined,
          fase: processoForm.fase || undefined,
          situacao: processoForm.situacao || undefined,
          desfecho: processoForm.desfecho || undefined,
          tese_id: processoForm.tese_id || undefined,
          valor_causa: processoForm.valor_causa ? Number(processoForm.valor_causa) : undefined,
          parte_contraria: processoForm.parte_contraria || undefined,
          polo: processoForm.polo || undefined,
          oab_responsavel: processoForm.oab_responsavel || undefined,
          descricao: processoForm.descricao || undefined,
          monitoring_active: processoForm.monitoring_active,
        }),
      });
      if (res.ok) {
        toast.success("Processo atualizado.");
        setShowProcessoModal(false);
        fetchAll();
      } else {
        const d = await res.json().catch(() => ({}));
        toast.error(d.detail || "Erro ao salvar o processo.");
      }
    } catch { toast.error("Erro de conexão."); }
    finally { setSavingProcesso(false); }
  }

  async function atualizarPartes() {
    setAtualizandoPartes(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/processes/${id}/atualizar-partes`, {
        method: "POST", headers: { Authorization: `Bearer ${token}` },
      });
      const d = await res.json().catch(() => ({}));
      if (res.ok) {
        if (d.novas > 0) { toast.success(d.message || "Partes atualizadas."); fetchAll(); }
        else toast.warning(d.message || "Nenhuma parte nova.");
      } else toast.error(d.detail || "Erro ao atualizar partes.");
    } catch { toast.error("Erro de conexão."); }
    finally { setAtualizandoPartes(false); }
  }

  function abrirModalParte(parte?: Parte) {
    if (parte) {
      setEditingParteId(parte.id);
      setParteForm({ nome: parte.nome, tipo: parte.tipo, polo: parte.polo ?? "", cpf_cnpj: parte.cpf_cnpj ?? "", oab: parte.oab ?? "", client_id: parte.client_id ?? "" });
      setClienteVinculadoNome(parte.cliente_nome ?? null);
    } else {
      setEditingParteId(null);
      setParteForm(PARTE_FORM_VAZIO);
      setClienteVinculadoNome(null);
    }
    setClienteQuery("");
    setClienteResultados([]);
    setSugestoesParte([]);
    setVinculoAutomatico(false);
    setClienteAutoDismissado(null);
    setShowParteModal(true);
  }

  // Fase 179 — busca de cliente com debounce (mesmo padrão de processos/page.tsx)
  useEffect(() => {
    if (!showParteModal) return;
    if (clienteDebounceRef.current) clearTimeout(clienteDebounceRef.current);
    if (!clienteQuery.trim()) { setClienteResultados([]); return; }
    clienteDebounceRef.current = setTimeout(async () => {
      setBuscandoCliente(true);
      try {
        const token = localStorage.getItem("afj_access_token");
        const res = await fetch(`/api/v1/clients?search=${encodeURIComponent(clienteQuery)}&limit=8`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) setClienteResultados(await res.json());
      } finally { setBuscandoCliente(false); }
    }, 300);
    return () => {
      if (clienteDebounceRef.current) clearTimeout(clienteDebounceRef.current);
    };
  }, [clienteQuery, showParteModal]);

  function selecionarClienteParaParte(c: { id: string; nome_completo: string; cpf: string | null; cnpj: string | null }) {
    setParteForm((f) => ({ ...f, client_id: c.id, nome: c.nome_completo, cpf_cnpj: c.cpf || c.cnpj || f.cpf_cnpj }));
    setClienteVinculadoNome(c.nome_completo);
    setClienteQuery("");
    setClienteResultados([]);
    setSugestoesParte([]);
  }

  function removerVinculoCliente() {
    setClienteAutoDismissado(parteForm.client_id || null);
    setParteForm((f) => ({ ...f, client_id: "" }));
    setClienteVinculadoNome(null);
    setVinculoAutomatico(false);
  }

  // Fase 181 — a partir do que já está sendo digitado em Nome/CPF-CNPJ da
  // parte, procura cliente já cadastrado: CPF/CNPJ exato linka sozinho,
  // nome parecido vira sugestão clicável (nunca linka sozinho por nome).
  useEffect(() => {
    if (!showParteModal || parteForm.client_id) { setSugestoesParte([]); return; }
    const cpfCnpj = parteForm.cpf_cnpj.trim();
    const nome = parteForm.nome.trim();
    if (matchDebounceRef.current) clearTimeout(matchDebounceRef.current);
    if (!cpfCnpj && nome.length < 3) { setSugestoesParte([]); return; }
    matchDebounceRef.current = setTimeout(async () => {
      try {
        const token = localStorage.getItem("afj_access_token");
        const params = new URLSearchParams();
        if (cpfCnpj) params.set("cpf_cnpj", cpfCnpj);
        if (nome.length >= 3) params.set("nome", nome);
        const res = await fetch(`/api/v1/clients/match?${params.toString()}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) return;
        const d = await res.json();
        if (d.match && d.match.id !== clienteAutoDismissado) {
          selecionarClienteParaParte({ id: d.match.id, nome_completo: d.match.nome_completo, cpf: null, cnpj: null });
          setVinculoAutomatico(true);
        } else if (d.match) {
          setSugestoesParte([{ id: d.match.id, nome_completo: d.match.nome_completo }]);
        } else {
          setSugestoesParte(d.sugestoes || []);
        }
      } catch { /* silencioso — não deve travar o cadastro manual */ }
    }, 400);
    return () => {
      if (matchDebounceRef.current) clearTimeout(matchDebounceRef.current);
    };
  }, [parteForm.cpf_cnpj, parteForm.nome, parteForm.client_id, showParteModal, clienteAutoDismissado]);

  async function salvarParte(e: React.FormEvent) {
    e.preventDefault();
    if (!parteForm.nome.trim()) return;
    setSavingParte(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const url = editingParteId
        ? `/api/v1/processes/${id}/partes/${editingParteId}`
        : `/api/v1/processes/${id}/partes`;
      const res = await fetch(url, {
        method: editingParteId ? "PUT" : "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          nome: parteForm.nome,
          tipo: parteForm.tipo,
          polo: parteForm.polo || undefined,
          cpf_cnpj: parteForm.cpf_cnpj || undefined,
          oab: parteForm.oab || undefined,
          client_id: parteForm.client_id || undefined,
        }),
      });
      if (res.ok) {
        toast.success(editingParteId ? "Parte atualizada." : "Parte cadastrada.");
        setShowParteModal(false);
        setParteForm(PARTE_FORM_VAZIO);
        setEditingParteId(null);
        fetchAll();
      } else {
        const d = await res.json().catch(() => ({}));
        toast.error(d.detail || "Erro ao salvar a parte.");
      }
    } catch { toast.error("Erro de conexão."); }
    finally { setSavingParte(false); }
  }

  async function excluirParte(parteId: string) {
    if ((await ask({ message: "Excluir esta parte?", danger: true, confirmLabel: "Excluir" })) === null) return;
    setExcluindoParteId(parteId);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/processes/${id}/partes/${parteId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) { toast.success("Parte excluída."); fetchAll(); }
      else toast.error("Erro ao excluir a parte.");
    } catch { toast.error("Erro de conexão."); }
    finally { setExcluindoParteId(null); }
  }

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
    fetchTeses();
  }, [id]);

  async function fetchAll() {
    const token = localStorage.getItem("afj_access_token");
    const headers = { Authorization: `Bearer ${token}` };
    setLoading(true);
    try {
      const [pRes, mRes, dRes, paRes] = await Promise.all([
        fetch(`/api/v1/processes/${id}`, { headers }),
        fetch(`/api/v1/processes/${id}/movements`, { headers }),
        fetch(`/api/v1/processes/${id}/deadlines`, { headers }),
        fetch(`/api/v1/processes/${id}/partes`, { headers }),
      ]);
      if (pRes.ok) setProcesso(await pRes.json());
      if (mRes.ok) setMovimentacoes(await mRes.json());
      if (dRes.ok) setPrazos(await dRes.json());
      if (paRes.ok) setPartes(await paRes.json());
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
              onClick={atualizarPartes}
              disabled={atualizandoPartes || !processo.numero_cnj}
              title={processo.numero_cnj ? "Importar partes do processo (PJe/PDPJ — requer integração conectada)" : "Processo sem número CNJ"}
              className="btn-afj-outline rounded-sm flex items-center gap-1.5 text-xs disabled:opacity-50"
            >
              {atualizandoPartes ? <Loader2 size={12} className="animate-spin" /> : <Users size={12} />}
              Atualizar partes
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
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-semibold text-afj-black text-sm">Informações do Processo</h2>
              <button onClick={abrirEditorProcesso} className="tap-target text-afj-black/30 hover:text-afj-gold" title="Editar processo" aria-label="Editar processo">
                <Edit3 size={14} />
              </button>
            </div>
            <div className="space-y-2 text-sm">
              {[
                { label: "Área do Direito", value: processo.area_direito },
                { label: "Tipo de Ação", value: processo.tipo_acao },
                { label: "Fase", value: processo.fase },
                { label: "Polo", value: processo.polo },
                { label: "Parte Contrária", value: processo.parte_contraria },
                { label: "OAB Responsável", value: processo.oab_responsavel },
                { label: "Comarca / UF", value: processo.comarca ? `${processo.comarca} / ${processo.uf}` : processo.uf },
                { label: "Desfecho", value: processo.desfecho },
                { label: "Tese", value: teses.find((t) => t.id === processo.tese_id)?.nome ?? null },
                {
                  label: "Origem",
                  value: processo.fonte === "OAB" ? "Captura automática (OAB)"
                    : processo.fonte === "MANUAL" ? "Cadastro manual"
                    : processo.fonte ?? null,
                },
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
              {processo.descricao && (
                <div className="pt-1 border-t border-afj-cream-dark/60">
                  <span className="text-afj-black/50 text-xs block mb-1">Descrição</span>
                  <p className="text-afj-black text-xs whitespace-pre-wrap">{processo.descricao}</p>
                </div>
              )}
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

          {/* Partes do processo (manual ou importada — PJe/PDPJ/Escavador/Judit/Jusbrasil) */}
          <div className="afj-card p-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-semibold text-afj-black text-sm flex items-center gap-1.5">
                <Users size={14} className="text-afj-gold" /> Partes
                {partes.length > 0 && (
                  <span className="text-[10px] uppercase tracking-wider text-afj-black/35">{partes.length}</span>
                )}
              </h2>
              <button
                onClick={() => abrirModalParte()}
                className="text-xs text-afj-gold hover:underline flex items-center gap-1"
              >
                <Plus size={11} /> Adicionar
              </button>
            </div>
            {partes.length > 0 ? (
              <div className="space-y-1.5 text-sm">
                {partes.map((p) => (
                  <div key={p.id} className="flex justify-between gap-2 group">
                    <span className="text-afj-black/80 text-xs">
                      {p.nome}
                      {p.oab && <span className="text-afj-black/40"> · OAB {p.oab}</span>}
                      {p.origem === "MANUAL" && <span className="text-afj-black/30"> · manual</span>}
                      {p.client_id && (
                        <a
                          href={`/clientes/${p.client_id}`}
                          className="ml-1.5 text-afj-gold hover:underline"
                          title={`Vinculado ao cliente ${p.cliente_nome ?? ""}`}
                        >
                          · cliente: {p.cliente_nome ?? "vinculado"}
                        </a>
                      )}
                    </span>
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      <span className="text-[10px] uppercase tracking-wider text-afj-black/35">{p.tipo}</span>
                      <button onClick={() => abrirModalParte(p)} className="tap-target text-afj-black/25 hover:text-afj-gold opacity-0 group-hover:opacity-100" title="Editar parte" aria-label="Editar parte">
                        <Edit3 size={11} />
                      </button>
                      <button onClick={() => excluirParte(p.id)} disabled={excluindoParteId === p.id} className="tap-target text-afj-black/25 hover:text-red-600 opacity-0 group-hover:opacity-100 disabled:opacity-50" title="Excluir parte" aria-label="Excluir parte">
                        {excluindoParteId === p.id ? <Loader2 size={11} className="animate-spin" /> : <Trash2 size={11} />}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-afj-black/40">
                Nenhuma parte cadastrada. Cadastre manualmente (&quot;+ Adicionar&quot;) ou use &quot;Atualizar partes&quot; (requer PJe/PDPJ, Escavador, Judit ou Jusbrasil conectado em Integrações).
              </p>
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
          <ProcessTimelineCard
            movimentacoes={movimentacoes}
            onGerarPrazo={(descricao) => {
              setPrazoForm({ descricao: descricao.slice(0, 200), tipo: "", data_prazo: "", data_fatal: "", observacoes: "" });
              setShowPrazoModal(true);
            }}
          />
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
              <PrazoCalculator
                onCalculado={(dataPrazo) => setPrazoForm((p) => ({ ...p, data_prazo: dataPrazo, data_fatal: dataPrazo }))}
              />

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

      {/* Modal: Editar Processo (Fase 133 — antes só tribunal/situação/área eram editáveis, num modal escondido na lista) */}
      {showProcessoModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-sm shadow-xl w-full max-w-2xl max-h-[85vh] overflow-y-auto">
            <div className="flex items-center justify-between px-5 py-4 border-b border-afj-cream-dark">
              <h2 className="font-semibold text-afj-black">Editar Processo</h2>
              <button onClick={() => setShowProcessoModal(false)} className="text-afj-black/40 hover:text-afj-black">
                <X size={18} />
              </button>
            </div>
            <form onSubmit={salvarProcesso} className="p-5 space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">Número CNJ</label>
                  <input value={processoForm.numero_cnj} onChange={(e) => setProcessoForm({ ...processoForm, numero_cnj: e.target.value })}
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold" />
                </div>
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">Tribunal *</label>
                  <input required value={processoForm.tribunal} onChange={(e) => setProcessoForm({ ...processoForm, tribunal: e.target.value })}
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold" />
                </div>
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">Vara</label>
                  <input value={processoForm.vara} onChange={(e) => setProcessoForm({ ...processoForm, vara: e.target.value })}
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold" />
                </div>
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">Comarca</label>
                  <input value={processoForm.comarca} onChange={(e) => setProcessoForm({ ...processoForm, comarca: e.target.value })}
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold" />
                </div>
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">UF</label>
                  <input maxLength={2} value={processoForm.uf} onChange={(e) => setProcessoForm({ ...processoForm, uf: e.target.value.toUpperCase() })}
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">Área do Direito</label>
                  <select value={processoForm.area_direito} onChange={(e) => setProcessoForm({ ...processoForm, area_direito: e.target.value })}
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm bg-white focus:outline-none focus:border-afj-gold">
                    <option value="">Sem área definida</option>
                    {AREAS_DIREITO.map((a) => <option key={a} value={a}>{a}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">Tipo de Ação</label>
                  <input value={processoForm.tipo_acao} onChange={(e) => setProcessoForm({ ...processoForm, tipo_acao: e.target.value })}
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold" />
                </div>
              </div>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">Fase</label>
                  <input value={processoForm.fase} onChange={(e) => setProcessoForm({ ...processoForm, fase: e.target.value })}
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold" />
                </div>
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">Situação</label>
                  <select value={processoForm.situacao} onChange={(e) => setProcessoForm({ ...processoForm, situacao: e.target.value })}
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm bg-white focus:outline-none focus:border-afj-gold">
                    {SITUACOES_PROCESSO.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">Desfecho</label>
                  <select value={processoForm.desfecho} onChange={(e) => setProcessoForm({ ...processoForm, desfecho: e.target.value })}
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm bg-white focus:outline-none focus:border-afj-gold">
                    <option value="">—</option>
                    <option value="EXITO">Êxito</option>
                    <option value="PARCIAL">Parcial</option>
                    <option value="ACORDO">Acordo</option>
                    <option value="DERROTA">Derrota</option>
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-4 gap-3">
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">Tese</label>
                  <select value={processoForm.tese_id} onChange={(e) => setProcessoForm({ ...processoForm, tese_id: e.target.value })}
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm bg-white focus:outline-none focus:border-afj-gold">
                    <option value="">—</option>
                    {teses.map((t) => <option key={t.id} value={t.id}>{t.nome}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">Valor da Causa (R$)</label>
                  <input type="number" min="0" step="0.01" value={processoForm.valor_causa} onChange={(e) => setProcessoForm({ ...processoForm, valor_causa: e.target.value })}
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold" />
                </div>
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">Polo</label>
                  <select value={processoForm.polo} onChange={(e) => setProcessoForm({ ...processoForm, polo: e.target.value })}
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm bg-white focus:outline-none focus:border-afj-gold">
                    <option value="">—</option>
                    <option value="ATIVO">Ativo</option>
                    <option value="PASSIVO">Passivo</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">OAB Responsável</label>
                  <input value={processoForm.oab_responsavel} onChange={(e) => setProcessoForm({ ...processoForm, oab_responsavel: e.target.value })}
                    placeholder="123/CE" className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold" />
                </div>
              </div>
              <div>
                <label className="text-xs text-afj-black/60 block mb-1">Parte Contrária</label>
                <input value={processoForm.parte_contraria} onChange={(e) => setProcessoForm({ ...processoForm, parte_contraria: e.target.value })}
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold" />
              </div>
              <div>
                <label className="text-xs text-afj-black/60 block mb-1">Descrição</label>
                <textarea rows={3} value={processoForm.descricao} onChange={(e) => setProcessoForm({ ...processoForm, descricao: e.target.value })}
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold" />
              </div>
              <label className="flex items-center gap-2 text-sm text-afj-black/70 cursor-pointer">
                <input type="checkbox" checked={processoForm.monitoring_active} onChange={(e) => setProcessoForm({ ...processoForm, monitoring_active: e.target.checked })} className="accent-afj-gold" />
                Monitoramento automático ativo
              </label>
              <div className="flex gap-2 justify-end pt-2">
                <button type="button" onClick={() => setShowProcessoModal(false)} disabled={savingProcesso} className="btn-afj-outline text-sm py-2 px-4 rounded-sm">Cancelar</button>
                <button type="submit" disabled={savingProcesso} className="btn-afj-primary text-sm py-2 px-4 rounded-sm flex items-center gap-2">
                  {savingProcesso ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle size={14} />} Salvar
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Adicionar/Editar Parte */}
      {showParteModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-sm shadow-xl w-full max-w-md max-h-[85vh] overflow-y-auto">
            <div className="flex items-center justify-between px-5 py-4 border-b border-afj-cream-dark">
              <h2 className="font-semibold text-afj-black">{editingParteId ? "Editar Parte" : "Adicionar Parte"}</h2>
              <button onClick={() => setShowParteModal(false)} className="text-afj-black/40 hover:text-afj-black">
                <X size={18} />
              </button>
            </div>
            <form onSubmit={salvarParte} className="p-5 space-y-4">
              <div>
                <label className="text-xs text-afj-black/60 block mb-1">Vincular a um cliente existente (opcional)</label>
                {parteForm.client_id ? (
                  <div className="border border-afj-cream-dark rounded-sm px-3 py-2 text-sm bg-afj-cream/40">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-afj-black/80">{clienteVinculadoNome ?? "Cliente vinculado"}</span>
                      <button type="button" onClick={removerVinculoCliente} className="text-xs text-afj-black/40 hover:text-red-600">
                        Remover vínculo
                      </button>
                    </div>
                    {vinculoAutomatico && (
                      <p className="text-[10px] text-afj-gold-dark mt-1">
                        Vinculado automaticamente — mesmo CPF/CNPJ de um cliente já cadastrado.
                      </p>
                    )}
                  </div>
                ) : (
                  <div className="relative">
                    <input
                      value={clienteQuery}
                      onChange={(e) => setClienteQuery(e.target.value)}
                      placeholder="Buscar por nome, e-mail ou razão social..."
                      className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                    />
                    {(buscandoCliente || clienteResultados.length > 0) && clienteQuery.trim() && (
                      <div className="absolute z-10 mt-1 w-full bg-white border border-afj-cream-dark rounded-sm shadow-lg max-h-48 overflow-y-auto">
                        {buscandoCliente ? (
                          <div className="px-3 py-2 text-xs text-afj-black/40 flex items-center gap-2">
                            <Loader2 size={11} className="animate-spin" /> Buscando...
                          </div>
                        ) : clienteResultados.length > 0 ? (
                          clienteResultados.map((c) => (
                            <button
                              type="button"
                              key={c.id}
                              onClick={() => selecionarClienteParaParte(c)}
                              className="w-full text-left px-3 py-2 text-xs hover:bg-afj-cream/60 border-b border-afj-cream-dark last:border-0"
                            >
                              {c.nome_completo}
                            </button>
                          ))
                        ) : (
                          <div className="px-3 py-2 text-xs text-afj-black/40">Nenhum cliente encontrado.</div>
                        )}
                      </div>
                    )}
                  </div>
                )}
                <p className="text-[10px] text-afj-black/35 mt-1">
                  Ao vincular, nome e CPF/CNPJ abaixo são preenchidos automaticamente (você ainda pode editá-los).
                </p>
              </div>
              <div>
                <label className="text-xs text-afj-black/60 block mb-1">Nome *</label>
                <input
                  required
                  value={parteForm.nome}
                  onChange={(e) => setParteForm({ ...parteForm, nome: e.target.value })}
                  placeholder="Nome completo ou razão social"
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                />
                {sugestoesParte.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    <span className="text-[10px] text-afj-black/40 self-center">Cliente parecido:</span>
                    {sugestoesParte.map((s) => (
                      <button
                        type="button"
                        key={s.id}
                        onClick={() => selecionarClienteParaParte({ id: s.id, nome_completo: s.nome_completo, cpf: null, cnpj: null })}
                        className="text-[11px] px-2 py-1 rounded-full border border-afj-gold/40 text-afj-gold-dark hover:bg-afj-gold/10"
                      >
                        {s.nome_completo}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">Tipo *</label>
                  <select
                    value={parteForm.tipo}
                    onChange={(e) => setParteForm({ ...parteForm, tipo: e.target.value })}
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm bg-white focus:outline-none focus:border-afj-gold"
                  >
                    {TIPOS_PARTE.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">Polo</label>
                  <select
                    value={parteForm.polo}
                    onChange={(e) => setParteForm({ ...parteForm, polo: e.target.value })}
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm bg-white focus:outline-none focus:border-afj-gold"
                  >
                    <option value="">—</option>
                    <option value="ATIVO">Ativo</option>
                    <option value="PASSIVO">Passivo</option>
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">CPF/CNPJ</label>
                  <input
                    value={parteForm.cpf_cnpj}
                    onChange={(e) => setParteForm({ ...parteForm, cpf_cnpj: e.target.value })}
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                  />
                </div>
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">OAB</label>
                  <input
                    value={parteForm.oab}
                    onChange={(e) => setParteForm({ ...parteForm, oab: e.target.value })}
                    placeholder="123/CE"
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                  />
                </div>
              </div>
              <div className="flex gap-2 justify-end pt-2">
                <button type="button" onClick={() => setShowParteModal(false)} disabled={savingParte} className="btn-afj-outline text-sm py-2 px-4 rounded-sm">Cancelar</button>
                <button type="submit" disabled={savingParte} className="btn-afj-primary text-sm py-2 px-4 rounded-sm flex items-center gap-2">
                  {savingParte ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle size={14} />} Salvar
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      {confirmDialog}
    </div>
  );
}
