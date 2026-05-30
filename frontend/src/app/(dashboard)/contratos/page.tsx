"use client";
import { useState, useEffect } from "react";
import { FileSignature, Plus, Search, Calendar, Pencil, Trash2, X, Loader2, RefreshCw } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { useToast } from "@/components/ui/Toast";

interface Contrato {
  id: string;
  titulo: string;
  tipo: string;
  status: string;
  valor_total: number | null;
  data_inicio: string | null;
  data_fim: string | null;
  renovacao_auto: boolean;
  client_id: string | null;
  created_at: string;
}

interface Cliente { id: string; nome_completo: string; razao_social: string | null; }

const STATUS_STYLE: Record<string, string> = {
  RASCUNHO: "badge-pendente",
  ATIVO: "badge-ativo",
  ENCERRADO: "badge-arquivado",
  CANCELADO: "badge-arquivado",
};

const TIPOS_CONTRATO = ["HONORARIOS", "PRESTACAO_SERVICOS", "PARCERIA", "OUTROS"];

const STATUS_OPTIONS = ["RASCUNHO", "ATIVO", "ENCERRADO", "CANCELADO"];

type FormState = {
  client_id: string;
  tipo: string;
  titulo: string;
  descricao: string;
  valor_total: string;
  data_inicio: string;
  data_fim: string;
  renovacao_auto: boolean;
};

const EMPTY_FORM: FormState = {
  client_id: "", tipo: "HONORARIOS", titulo: "", descricao: "",
  valor_total: "", data_inicio: "", data_fim: "", renovacao_auto: false,
};

export default function ContratosPage() {
  const toast = useToast();
  const [contratos, setContratos] = useState<Contrato[]>([]);
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [editStatus, setEditStatus] = useState("RASCUNHO");

  useEffect(() => {
    fetchContratos();
    fetchClientes();
  }, []);

  async function fetchContratos() {
    setLoading(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/documents?tipo=CONTRATO", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setContratos(await res.json());
    } finally { setLoading(false); }
  }

  async function fetchClientes() {
    const token = localStorage.getItem("afj_access_token");
    const res = await fetch("/api/v1/clients?limit=100", {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) setClientes(await res.json());
  }

  async function criarContrato(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/documents/contracts/create", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          client_id: form.client_id || undefined,
          tipo: form.tipo,
          titulo: form.titulo,
          descricao: form.descricao || undefined,
          valor_total: form.valor_total ? parseFloat(form.valor_total) : undefined,
          data_inicio: form.data_inicio || undefined,
          data_fim: form.data_fim || undefined,
          renovacao_auto: form.renovacao_auto,
        }),
      });
      if (res.ok) {
        setShowModal(false);
        setForm(EMPTY_FORM);
        fetchContratos();
      } else {
        toast.error("Erro ao criar contrato. Tente novamente.");
      }
    } finally { setSaving(false); }
  }

  async function editarContrato(id: string) {
    setSaving(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/documents/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          titulo: form.titulo,
          status: editStatus,
        }),
      });
      if (res.ok) {
        setEditingId(null);
        fetchContratos();
      } else {
        toast.error("Erro ao salvar contrato. Tente novamente.");
      }
    } catch {
      toast.error("Erro de conexão. Tente novamente.");
    } finally { setSaving(false); }
  }

  async function excluirContrato(id: string) {
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/documents/${id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        setDeletingId(null);
        fetchContratos();
      } else {
        toast.error("Erro ao arquivar contrato. Tente novamente.");
      }
    } catch {
      toast.error("Erro de conexão. Tente novamente.");
    }
  }

  const filtrados = contratos.filter((c) =>
    !search || c.titulo?.toLowerCase().includes(search.toLowerCase())
  );

  const fmt = (v: number) => `R$ ${v.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`;

  const clienteNome = (id: string | null) => {
    if (!id) return null;
    const c = clientes.find((c) => c.id === id);
    return c ? (c.razao_social || c.nome_completo) : null;
  };

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Contratos" }]} />
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-semibold text-afj-black">Contratos</h1>
          <p className="text-afj-black/50 text-sm">{filtrados.length} contrato(s)</p>
        </div>
        <div className="flex gap-2">
          <button onClick={fetchContratos} className="btn-afj-outline rounded-sm p-2" title="Atualizar" aria-label="Atualizar lista">
            <RefreshCw size={14} />
          </button>
          <button onClick={() => { setForm(EMPTY_FORM); setShowModal(true); }} className="btn-afj-primary rounded-sm flex items-center gap-2">
            <Plus size={15} />
            Novo Contrato
          </button>
        </div>
      </div>

      <div className="flex gap-3">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-afj-black/30" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por título..."
            className="w-full pl-9 pr-4 py-2 text-sm border border-afj-cream-dark rounded-sm focus:outline-none focus:border-afj-gold bg-white"
          />
        </div>
      </div>

      {loading ? (
        <div className="afj-card p-4 space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-11 bg-afj-cream-dark rounded animate-pulse" />
          ))}
        </div>
      ) : filtrados.length === 0 ? (
        <div className="afj-card p-12 text-center">
          <FileSignature className="mx-auto text-afj-black/20 mb-3" size={40} />
          <p className="font-semibold text-afj-black">Nenhum contrato encontrado</p>
          <p className="text-afj-black/40 text-sm mt-1">Crie um novo contrato ou aguarde a geração pelo agente</p>
          <button onClick={() => { setForm(EMPTY_FORM); setShowModal(true); }} className="btn-afj-primary rounded-sm mt-4 text-sm">
            Criar Contrato
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtrados.map((c) => (
            <div key={c.id} className="afj-card p-4 hover:border-afj-gold/30 transition-colors">
              <div className="flex items-start justify-between mb-3">
                <span className={STATUS_STYLE[c.status] ?? "badge-arquivado"}>{c.status}</span>
                {c.renovacao_auto && (
                  <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full">Auto-renovação</span>
                )}
              </div>
              <p className="font-semibold text-afj-black text-sm">{c.titulo}</p>
              <p className="text-xs text-afj-black/50 mt-0.5">{c.tipo}</p>
              {clienteNome(c.client_id) && (
                <p className="text-xs text-afj-gold mt-1">{clienteNome(c.client_id)}</p>
              )}
              {(c.valor_total !== null && c.valor_total !== undefined) && (
                <p className="text-sm font-semibold text-afj-gold mt-2">{fmt(c.valor_total)}</p>
              )}
              {(c.data_inicio || c.data_fim) && (
                <div className="mt-3 pt-2 border-t border-afj-cream-dark flex items-center gap-2 text-xs text-afj-black/50">
                  <Calendar size={11} />
                  {c.data_inicio && new Date(c.data_inicio).toLocaleDateString("pt-BR")}
                  {c.data_inicio && c.data_fim && " → "}
                  {c.data_fim && new Date(c.data_fim).toLocaleDateString("pt-BR")}
                </div>
              )}
              <div className="mt-3 pt-2 border-t border-afj-cream-dark flex items-center justify-end gap-2">
                <button
                  onClick={() => {
                    setEditingId(c.id);
                    setForm({ ...EMPTY_FORM, titulo: c.titulo });
                    setEditStatus(c.status);
                  }}
                  className="text-afj-black/30 hover:text-afj-gold transition-colors"
                  aria-label="Editar contrato"
                >
                  <Pencil size={13} />
                </button>
                <button
                  onClick={() => setDeletingId(c.id)}
                  className="text-afj-black/30 hover:text-red-500 transition-colors"
                  aria-label="Excluir contrato"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modal: Novo Contrato */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-sm shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between px-5 py-4 border-b border-afj-cream-dark sticky top-0 bg-white">
              <h2 className="font-semibold text-afj-black">Novo Contrato</h2>
              <button onClick={() => setShowModal(false)} className="text-afj-black/40 hover:text-afj-black"><X size={18} /></button>
            </div>
            <form onSubmit={criarContrato} className="p-5 space-y-4">
              <div>
                <label className="text-xs text-afj-black/60 block mb-1">Título *</label>
                <input
                  required
                  value={form.titulo}
                  onChange={(e) => setForm({ ...form, titulo: e.target.value })}
                  placeholder="Ex: Contrato de Honorários — João Silva"
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">Tipo</label>
                  <select
                    value={form.tipo}
                    onChange={(e) => setForm({ ...form, tipo: e.target.value })}
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                  >
                    {TIPOS_CONTRATO.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">Cliente</label>
                  <select
                    value={form.client_id}
                    onChange={(e) => setForm({ ...form, client_id: e.target.value })}
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                  >
                    <option value="">Sem cliente</option>
                    {clientes.map((c) => (
                      <option key={c.id} value={c.id}>{c.razao_social || c.nome_completo}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div>
                <label className="text-xs text-afj-black/60 block mb-1">Valor Total (R$)</label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={form.valor_total}
                  onChange={(e) => setForm({ ...form, valor_total: e.target.value })}
                  placeholder="0,00"
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">Data Início</label>
                  <input
                    type="date"
                    value={form.data_inicio}
                    onChange={(e) => setForm({ ...form, data_inicio: e.target.value })}
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                  />
                </div>
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">Data Fim</label>
                  <input
                    type="date"
                    value={form.data_fim}
                    onChange={(e) => setForm({ ...form, data_fim: e.target.value })}
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                  />
                </div>
              </div>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={form.renovacao_auto}
                  onChange={(e) => setForm({ ...form, renovacao_auto: e.target.checked })}
                  className="accent-afj-gold"
                />
                <span className="text-sm text-afj-black/70">Renovação automática</span>
              </label>
              <div className="flex gap-3 pt-1">
                <button type="button" onClick={() => setShowModal(false)} className="flex-1 btn-afj-outline rounded-sm">Cancelar</button>
                <button
                  type="submit"
                  disabled={saving || !form.titulo.trim()}
                  className="flex-1 btn-afj-primary rounded-sm flex items-center justify-center gap-2 disabled:opacity-40"
                >
                  {saving ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
                  Criar
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Editar Contrato */}
      {editingId && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-sm shadow-xl w-full max-w-sm">
            <div className="flex items-center justify-between px-5 py-4 border-b border-afj-cream-dark">
              <h2 className="font-semibold text-afj-black">Editar Contrato</h2>
              <button onClick={() => setEditingId(null)} className="text-afj-black/40 hover:text-afj-black"><X size={18} /></button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="text-xs text-afj-black/60 block mb-1">Título</label>
                <input
                  value={form.titulo}
                  onChange={(e) => setForm({ ...form, titulo: e.target.value })}
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                />
              </div>
              <div>
                <label className="text-xs text-afj-black/60 block mb-1">Status</label>
                <select
                  value={editStatus}
                  onChange={(e) => setEditStatus(e.target.value)}
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                >
                  {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div className="flex gap-3">
                <button onClick={() => setEditingId(null)} className="flex-1 btn-afj-outline rounded-sm">Cancelar</button>
                <button
                  onClick={() => editarContrato(editingId)}
                  disabled={saving}
                  className="flex-1 btn-afj-primary rounded-sm flex items-center justify-center gap-2 disabled:opacity-40"
                >
                  {saving ? <Loader2 size={13} className="animate-spin" /> : null}
                  Salvar
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Confirmação exclusão */}
      {deletingId && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-sm shadow-xl w-full max-w-sm p-6 text-center">
            <p className="font-semibold text-afj-black mb-2">Arquivar contrato?</p>
            <p className="text-afj-black/50 text-sm mb-5">O contrato será arquivado e não aparecerá na lista.</p>
            <div className="flex gap-3">
              <button onClick={() => setDeletingId(null)} className="flex-1 btn-afj-outline rounded-sm">Cancelar</button>
              <button onClick={() => excluirContrato(deletingId)} className="flex-1 bg-red-500 text-white rounded-sm py-2 text-sm font-medium uppercase tracking-wide hover:bg-red-600">
                Arquivar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
