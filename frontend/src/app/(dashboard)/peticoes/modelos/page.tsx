"use client";
import { useState, useEffect, useRef } from "react";
import { FileStack, Plus, Pencil, Trash2, X, Loader2, Search, Upload, Download } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { useToast } from "@/components/ui/Toast";

interface Template {
  id: string;
  nome: string;
  tipo_peticao: string | null;
  descricao: string | null;
  conteudo: string;
  ativo: boolean;
  created_at: string;
}

const TIPOS = [
  "PETICAO_INICIAL", "CONTESTACAO", "RECURSO_APELACAO", "AGRAVO",
  "MANDADO_SEGURANCA", "HABEAS_CORPUS", "IMPUGNACAO", "MEMORIA_CALCULO", "OUTROS",
];

type FormState = {
  nome: string; tipo_peticao: string; descricao: string; conteudo: string; ativo: boolean;
};
const EMPTY: FormState = { nome: "", tipo_peticao: "PETICAO_INICIAL", descricao: "", conteudo: "", ativo: true };

export default function ModelosPeticaoPage() {
  const toast = useToast();
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [busca, setBusca] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [importing, setImporting] = useState(false);
  const [form, setForm] = useState<FormState>(EMPTY);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => { fetchTemplates(); }, []);

  function authH(): HeadersInit {
    const t = localStorage.getItem("afj_access_token");
    return { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) };
  }

  async function fetchTemplates() {
    setLoading(true);
    try {
      const res = await fetch("/api/v1/petition-templates", { headers: authH() });
      if (res.ok) setTemplates(await res.json());
    } finally { setLoading(false); }
  }

  function abrirNovo() { setEditingId(null); setForm(EMPTY); setShowModal(true); }
  function abrirEdicao(t: Template) {
    setEditingId(t.id);
    setForm({
      nome: t.nome, tipo_peticao: t.tipo_peticao || "OUTROS",
      descricao: t.descricao || "", conteudo: t.conteudo, ativo: t.ativo,
    });
    setShowModal(true);
  }

  async function salvar(e: React.FormEvent) {
    e.preventDefault();
    if (!form.nome.trim() || !form.conteudo.trim()) return;
    setSaving(true);
    try {
      const url = editingId ? `/api/v1/petition-templates/${editingId}` : "/api/v1/petition-templates";
      const res = await fetch(url, {
        method: editingId ? "PUT" : "POST",
        headers: authH(),
        body: JSON.stringify(form),
      });
      if (res.ok) { setShowModal(false); setForm(EMPTY); setEditingId(null); fetchTemplates(); toast.success(editingId ? "Modelo atualizado." : "Modelo criado."); }
      else toast.error("Erro ao salvar o modelo.");
    } catch { toast.error("Falha de conexão."); }
    finally { setSaving(false); }
  }

  async function importarArquivo(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    try {
      const t = localStorage.getItem("afj_access_token");
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch("/api/v1/petition-templates/upload", {
        method: "POST",
        headers: { ...(t ? { Authorization: `Bearer ${t}` } : {}) },
        body: fd,
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        toast.success(`Modelo "${data.nome}" importado. Revise e ajuste os marcadores.`);
        fetchTemplates();
        // Abre direto para revisão
        abrirEdicao(data as Template);
      } else {
        toast.error(data.detail || "Erro ao importar o arquivo.");
      }
    } catch { toast.error("Falha de conexão."); }
    finally {
      setImporting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function baixarDocx(t: Template) {
    try {
      const tk = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/petition-templates/${t.id}/docx`, {
        headers: { ...(tk ? { Authorization: `Bearer ${tk}` } : {}) },
      });
      if (!res.ok) { toast.error("Erro ao gerar o .docx."); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${t.nome}.docx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Falha de conexão."); }
  }

  async function excluir(id: string) {
    try {
      const res = await fetch(`/api/v1/petition-templates/${id}`, { method: "DELETE", headers: authH() });
      if (res.ok) { setDeletingId(null); fetchTemplates(); }
      else toast.error("Erro ao excluir.");
    } catch { toast.error("Falha de conexão."); }
  }

  const filtrados = templates.filter((t) =>
    !busca || t.nome.toLowerCase().includes(busca.toLowerCase()) ||
    (t.tipo_peticao || "").toLowerCase().includes(busca.toLowerCase())
  );

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Petições", href: "/peticoes" }, { label: "Modelos" }]} />

      <div className="afj-page-header">
        <div>
          <h1 className="afj-page-title flex items-center gap-2">
            <FileStack size={20} className="text-afj-gold" /> Modelos de Petição
          </h1>
          <p className="text-afj-black/45 text-sm mt-1">
            Biblioteca de modelos do escritório reutilizados pela IA na geração de petições.
          </p>
        </div>
        <div className="flex gap-2">
          <input ref={fileRef} type="file" accept=".docx,.txt" onChange={importarArquivo} className="hidden" />
          <button onClick={() => fileRef.current?.click()} disabled={importing}
            className="btn-afj-outline rounded-sm flex items-center gap-2 disabled:opacity-50">
            {importing ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />} Importar do Word
          </button>
          <button onClick={abrirNovo} className="btn-afj-primary rounded-sm flex items-center gap-2">
            <Plus size={15} /> Novo Modelo
          </button>
        </div>
      </div>

      <div className="relative">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-afj-black/30" />
        <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="Buscar por nome ou tipo..."
          className="w-full pl-9 pr-4 py-2 text-sm border border-afj-cream-dark rounded-sm bg-white focus:outline-none focus:border-afj-gold" />
      </div>

      {loading ? (
        <div className="afj-card p-4 space-y-3">
          {Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-11 bg-afj-cream-dark rounded animate-pulse" />)}
        </div>
      ) : filtrados.length === 0 ? (
        <div className="afj-card p-12 text-center">
          <FileStack className="mx-auto text-afj-black/20 mb-3" size={40} />
          <p className="font-semibold text-afj-black">Nenhum modelo cadastrado</p>
          <p className="text-afj-black/40 text-sm mt-1">Crie modelos com estrutura e cláusulas-padrão para acelerar a geração.</p>
          <button onClick={abrirNovo} className="btn-afj-primary rounded-sm mt-4 text-sm">Criar Modelo</button>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {filtrados.map((t) => (
            <div key={t.id} className="afj-card p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="font-semibold text-afj-black text-sm truncate">{t.nome}</p>
                  <div className="flex items-center gap-2 mt-0.5">
                    {t.tipo_peticao && <span className="text-[10px] uppercase tracking-wider text-afj-gold">{t.tipo_peticao.replace(/_/g, " ")}</span>}
                    {!t.ativo && <span className="text-[10px] uppercase tracking-wider text-afj-black/35">Inativo</span>}
                  </div>
                </div>
                <div className="flex items-center gap-1.5 flex-shrink-0">
                  <button onClick={() => baixarDocx(t)} className="text-afj-black/30 hover:text-afj-gold" aria-label="Baixar .docx (editar no Word)" title="Baixar .docx — edite no Word e reimporte"><Download size={13} /></button>
                  <button onClick={() => abrirEdicao(t)} className="text-afj-black/30 hover:text-afj-gold" aria-label="Editar"><Pencil size={13} /></button>
                  <button onClick={() => setDeletingId(t.id)} className="text-afj-black/30 hover:text-red-500" aria-label="Excluir"><Trash2 size={13} /></button>
                </div>
              </div>
              {t.descricao && <p className="text-xs text-afj-black/50 mt-2 line-clamp-2">{t.descricao}</p>}
              <p className="text-[11px] text-afj-black/35 mt-2">{t.conteudo.length} caracteres</p>
            </div>
          ))}
        </div>
      )}

      {/* Modal criar/editar */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setShowModal(false)}>
          <form onSubmit={salvar} onClick={(e) => e.stopPropagation()}
            className="bg-white rounded-sm shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-display text-lg font-semibold text-afj-black">{editingId ? "Editar Modelo" : "Novo Modelo"}</h3>
              <button type="button" onClick={() => setShowModal(false)} className="text-afj-black/40 hover:text-afj-black"><X size={18} /></button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-afj-black/60 block mb-1">Nome *</label>
                <input value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} required
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold" />
              </div>
              <div>
                <label className="text-xs text-afj-black/60 block mb-1">Tipo de petição</label>
                <select value={form.tipo_peticao} onChange={(e) => setForm({ ...form, tipo_peticao: e.target.value })}
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm bg-white focus:outline-none focus:border-afj-gold">
                  {TIPOS.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
                </select>
              </div>
            </div>

            <div>
              <label className="text-xs text-afj-black/60 block mb-1">Descrição (opcional)</label>
              <input value={form.descricao} onChange={(e) => setForm({ ...form, descricao: e.target.value })}
                placeholder="Quando usar este modelo..."
                className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold" />
            </div>

            <div>
              <label className="text-xs text-afj-black/60 block mb-1">Conteúdo / Estrutura do modelo *</label>
              <textarea value={form.conteudo} onChange={(e) => setForm({ ...form, conteudo: e.target.value })} required rows={12}
                placeholder="Estrutura, cláusulas-padrão e marcadores. Ex.:&#10;EXCELENTÍSSIMO(A) SENHOR(A) DOUTOR(A) JUIZ(A)...&#10;&#10;[AUTOR], já qualificado, vem propor AÇÃO...&#10;&#10;DOS FATOS&#10;[FATOS]&#10;&#10;DO DIREITO&#10;[FUNDAMENTOS]&#10;&#10;DOS PEDIDOS&#10;[PEDIDOS]"
                className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm font-mono focus:outline-none focus:border-afj-gold resize-none" />
              <p className="text-[11px] text-afj-black/40 mt-1">A IA usa isto como base; marcadores como [AUTOR], [FATOS], [PEDIDOS] guiam a redação.</p>
            </div>

            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={form.ativo} onChange={(e) => setForm({ ...form, ativo: e.target.checked })} className="accent-afj-gold w-4 h-4" />
              <span className="text-sm text-afj-black/75">Ativo (aparece na seleção ao gerar petições)</span>
            </label>

            <div className="flex gap-3 pt-1">
              <button type="submit" disabled={saving} className="btn-afj-primary rounded-sm flex items-center gap-2 disabled:opacity-50">
                {saving && <Loader2 size={14} className="animate-spin" />} {editingId ? "Salvar" : "Criar"}
              </button>
              <button type="button" onClick={() => setShowModal(false)} className="btn-afj-outline rounded-sm">Cancelar</button>
            </div>
          </form>
        </div>
      )}

      {/* Confirmar exclusão */}
      {deletingId && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setDeletingId(null)}>
          <div className="bg-white rounded-sm shadow-xl max-w-sm w-full p-6 space-y-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-semibold text-afj-black">Excluir modelo?</h3>
            <p className="text-sm text-afj-black/55">Esta ação é permanente e não pode ser desfeita.</p>
            <div className="flex gap-3">
              <button onClick={() => excluir(deletingId)} className="flex-1 bg-red-600 text-white rounded-sm py-2 text-sm font-medium hover:bg-red-700">Excluir</button>
              <button onClick={() => setDeletingId(null)} className="btn-afj-outline rounded-sm flex-1">Cancelar</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
