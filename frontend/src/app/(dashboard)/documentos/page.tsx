"use client";
import { useState, useEffect, useRef } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { FolderOpen, Search, FileText, Download, Upload, ScanLine, X, CloudUpload, FilePlus, Eye, Plus, Pencil, Trash2, Save, Loader2, History, RotateCcw, Scale, CheckCircle2, AlertTriangle, HelpCircle, Paperclip } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { useToast } from "@/components/ui/Toast";
import { useConfirmDialog } from "@/hooks/useConfirmDialog";

const TIPOS = ["PETICAO", "CONTRATO", "PROCURACAO", "PARECER", "RECURSO", "OUTROS"];
const STATUSES = ["RASCUNHO", "REVISAO", "APROVADO", "PROTOCOLADO", "REJEITADO"];

interface Documento {
  id: string;
  titulo: string;
  tipo: string;
  status: string;
  gerado_por_ia: boolean;
  versao: number;
  process_id: string | null;
  client_id: string | null;
  created_at: string;
  tem_texto: boolean;
  tem_arquivo_original: boolean;
  ocr_status: string | null;
  protocolado_em: string | null;
  follow_up_dias: number | null;
  follow_up_alertado: boolean;
}

// Chip que sinaliza o estado do texto/OCR do documento.
function OcrBadge({ d }: { d: Documento }) {
  if (d.ocr_status === "PENDENTE") {
    return <span className="text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded-sm bg-amber-50 text-amber-700 border border-amber-200">OCR…</span>;
  }
  if (d.tem_texto) {
    return <span className="text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded-sm bg-green-50 text-green-700 border border-green-200" title="Texto pesquisável disponível">Texto</span>;
  }
  if (d.ocr_status && ["FALHOU", "VAZIO", "INDISPONIVEL"].includes(d.ocr_status)) {
    return <span className="text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded-sm bg-gray-50 text-gray-500 border border-gray-200" title="OCR sem texto — tente reprocessar">Sem texto</span>;
  }
  return null;
}

const STATUS_STYLE: Record<string, string> = {
  RASCUNHO: "badge-pendente",
  REVISAO: "badge-pendente",
  APROVADO: "badge-ativo",
  PROTOCOLADO: "badge-ativo",
  REJEITADO: "badge-arquivado",
};

const TIPO_COLORS: Record<string, string> = {
  PETICAO: "bg-blue-100 text-blue-700",
  CONTRATO: "bg-purple-100 text-purple-700",
  PROCURACAO: "bg-orange-100 text-orange-700",
  PARECER: "bg-teal-100 text-teal-700",
  RECURSO: "bg-red-100 text-red-700",
  OUTROS: "bg-gray-100 text-gray-700",
};

const PAGE_SIZE = 50;

export default function DocumentosPage() {
  const toast = useToast();
  const { ask, confirmDialog } = useConfirmDialog();
  const searchParams = useSearchParams();
  const clientIdFiltro = searchParams.get("client_id");
  const [docs, setDocs] = useState<Documento[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const [filtroTipo, setFiltroTipo] = useState("");
  const [filtroStatus, setFiltroStatus] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<{ done: number; total: number } | null>(null);
  const [ocrRunning, setOcrRunning] = useState<string | null>(null);
  const [googleConnected, setGoogleConnected] = useState(false);
  const [savingDrive, setSavingDrive] = useState<string | null>(null);
  const [savingDoc, setSavingDoc] = useState<string | null>(null);
  const [loadingTexto, setLoadingTexto] = useState<string | null>(null);
  const [textoModal, setTextoModal] = useState<{ titulo: string; texto: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Criar / editar / excluir
  const emptyForm = { titulo: "", tipo: "OUTROS", status: "RASCUNHO", conteudo_texto: "", follow_up_dias: "" };
  const [showNew, setShowNew] = useState(false);
  const [newForm, setNewForm] = useState(emptyForm);
  const [editDoc, setEditDoc] = useState<Documento | null>(null);
  const [editForm, setEditForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const [loadingEdit, setLoadingEdit] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  // Verificação de citações (Fase 93)
  interface Citacao { referencia: string; tipo: string; status: string; titulo: string | null }
  const [citacoes, setCitacoes] = useState<Citacao[] | null>(null);
  const [verificando, setVerificando] = useState(false);

  const authH = () => ({
    "Content-Type": "application/json",
    Authorization: `Bearer ${typeof window !== "undefined" ? localStorage.getItem("afj_access_token") : ""}`,
  });

  async function criarDoc() {
    if (!newForm.titulo.trim()) { toast.error("Informe o título."); return; }
    setSaving(true);
    try {
      const res = await fetch("/api/v1/documents", {
        method: "POST", headers: authH(),
        body: JSON.stringify({ titulo: newForm.titulo, tipo: newForm.tipo, conteudo_texto: newForm.conteudo_texto || null }),
      });
      const d = await res.json().catch(() => ({}));
      if (res.ok) { toast.success("Documento criado."); setShowNew(false); setNewForm(emptyForm); fetchDocs(); }
      else toast.error(d.detail || "Erro ao criar documento.");
    } catch { toast.error("Erro de conexão."); }
    finally { setSaving(false); }
  }

  async function verificarCitacoes() {
    if (!editDoc) return;
    setVerificando(true);
    try {
      const res = await fetch(`/api/v1/documents/${editDoc.id}/verificar-citacoes`, { method: "POST", headers: authH() });
      const d = await res.json().catch(() => ({}));
      if (res.ok) {
        setCitacoes(d.citacoes || []);
        if (!d.citacoes?.length) toast.success("Nenhuma citação de lei ou processo encontrada no texto.");
      } else toast.error(d.detail || "Erro ao verificar citações.");
    } catch { toast.error("Erro de conexão."); }
    finally { setVerificando(false); }
  }

  async function abrirEdicao(d: Documento) {
    setEditDoc(d);
    const followUp = d.follow_up_dias != null ? String(d.follow_up_dias) : "";
    setEditForm({ titulo: d.titulo, tipo: d.tipo, status: d.status, conteudo_texto: "", follow_up_dias: followUp });
    setCitacoes(null);
    setLoadingEdit(true);
    try {
      const res = await fetch(`/api/v1/documents/${d.id}/content`, { headers: authH() });
      if (res.ok) {
        const c = await res.json();
        setEditForm({ titulo: d.titulo, tipo: d.tipo, status: d.status, conteudo_texto: c.conteudo_texto || c.conteudo_html || "", follow_up_dias: followUp });
      }
    } catch { /* mantém o form base */ }
    finally { setLoadingEdit(false); }
  }

  async function salvarEdicao() {
    if (!editDoc) return;
    setSaving(true);
    try {
      const followUpDias = editForm.follow_up_dias.trim() ? parseInt(editForm.follow_up_dias, 10) : null;
      const body: Record<string, unknown> = {
        titulo: editForm.titulo, tipo: editForm.tipo, status: editForm.status,
        conteudo_texto: editForm.conteudo_texto,
      };
      if (followUpDias != null && !isNaN(followUpDias) && followUpDias > 0) body.follow_up_dias = followUpDias;
      const res = await fetch(`/api/v1/documents/${editDoc.id}`, {
        method: "PUT", headers: authH(),
        body: JSON.stringify(body),
      });
      const d = await res.json().catch(() => ({}));
      if (res.ok) { toast.success("Documento atualizado."); setEditDoc(null); fetchDocs(); }
      else toast.error(d.detail || "Erro ao salvar.");
    } catch { toast.error("Erro de conexão."); }
    finally { setSaving(false); }
  }

  // Histórico de versões
  interface Versao { id: string; versao: number; change_summary: string | null; autor: string | null; created_at: string | null }
  const [histDoc, setHistDoc] = useState<Documento | null>(null);
  const [versoes, setVersoes] = useState<Versao[]>([]);
  const [loadingHist, setLoadingHist] = useState(false);
  const [restaurando, setRestaurando] = useState<string | null>(null);

  async function abrirHistorico(d: Documento) {
    setHistDoc(d);
    setVersoes([]);
    setLoadingHist(true);
    try {
      const res = await fetch(`/api/v1/documents/${d.id}/versions`, { headers: authH() });
      if (res.ok) setVersoes(await res.json());
    } catch { toast.error("Erro ao carregar o histórico."); }
    finally { setLoadingHist(false); }
  }

  async function restaurarVersao(v: Versao) {
    if (!histDoc) return;
    if ((await ask({ message: `Restaurar a versão ${v.versao}? O conteúdo atual será guardado como uma nova versão.` })) === null) return;
    setRestaurando(v.id);
    try {
      const res = await fetch(`/api/v1/documents/${histDoc.id}/versions/${v.id}/restore`, { method: "POST", headers: authH() });
      if (res.ok) { toast.success(`Versão ${v.versao} restaurada.`); setHistDoc(null); fetchDocs(); }
      else { const e = await res.json().catch(() => ({})); toast.error(e.detail || "Erro ao restaurar."); }
    } catch { toast.error("Erro de conexão."); }
    finally { setRestaurando(null); }
  }

  async function excluirDoc(d: Documento) {
    if ((await ask({ message: `Arquivar "${d.titulo}"? Ele sai da lista mas pode ser recuperado filtrando por arquivados.` })) === null) return;
    setDeleting(d.id);
    try {
      const res = await fetch(`/api/v1/documents/${d.id}`, { method: "DELETE", headers: authH() });
      if (res.ok) { toast.success("Documento arquivado."); fetchDocs(); }
      else { const e = await res.json().catch(() => ({})); toast.error(e.detail || "Erro ao arquivar."); }
    } catch { toast.error("Erro de conexão."); }
    finally { setDeleting(null); }
  }

  useEffect(() => { fetchDocs(0, false); }, [filtroTipo, filtroStatus, clientIdFiltro]);

  // Google Workspace: mostra "Salvar no Drive" apenas para quem conectou a conta
  useEffect(() => {
    const token = localStorage.getItem("afj_access_token");
    fetch("/api/v1/integrations/google/status", { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setGoogleConnected(Boolean(d?.connected)))
      .catch(() => {});
  }, []);

  async function salvarNoDrive(docId: string, titulo: string) {
    setSavingDrive(docId);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/integrations/google/drive-save/${docId}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const d = await res.json().catch(() => ({}));
      if (res.ok) toast.success(`"${titulo}" salvo no seu Google Drive.`);
      else toast.error(d.detail || "Erro ao salvar no Drive.");
    } catch { toast.error("Erro de conexão."); }
    finally { setSavingDrive(null); }
  }

  // Fase 182 — grava como Google Doc colaborável (a Drive API converte o
  // HTML automaticamente), alternativa ao PDF timbrado de salvarNoDrive().
  async function salvarComoGoogleDoc(docId: string, titulo: string) {
    setSavingDoc(docId);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/integrations/google/drive-save-doc/${docId}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const d = await res.json().catch(() => ({}));
      if (res.ok) toast.success(`"${titulo}" salvo como Google Doc.`);
      else toast.error(d.detail || "Erro ao salvar como Google Doc.");
    } catch { toast.error("Erro de conexão."); }
    finally { setSavingDoc(null); }
  }

  async function fetchDocs(newOffset = 0, append = false) {
    if (append) setLoadingMore(true);
    else setLoading(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const params = new URLSearchParams();
      if (filtroTipo) params.set("tipo", filtroTipo);
      if (filtroStatus) params.set("status", filtroStatus);
      if (clientIdFiltro) params.set("client_id", clientIdFiltro);
      params.set("limit", String(PAGE_SIZE));
      params.set("offset", String(newOffset));
      const res = await fetch(`/api/v1/documents?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data: Documento[] = await res.json();
        setDocs((prev) => (append ? [...prev, ...data] : data));
        setHasMore(data.length === PAGE_SIZE);
        setOffset(newOffset + data.length);
      }
    } finally {
      if (append) setLoadingMore(false);
      else setLoading(false);
    }
  }

  const filtrados = docs.filter((d) =>
    !search || d.titulo.toLowerCase().includes(search.toLowerCase())
  );

  async function uploadDoc(file: File): Promise<boolean> {
    try {
      const token = localStorage.getItem("afj_access_token");
      const formData = new FormData();
      formData.append("file", file);
      formData.append("titulo", file.name.replace(/\.[^/.]+$/, ""));
      formData.append("tipo", "OUTROS");
      const res = await fetch("/api/v1/documents/upload", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      if (res.ok) return true;
      const d = await res.json().catch(() => ({}));
      toast.error(`"${file.name}": ${d.detail || "erro ao enviar."}`);
      return false;
    } catch {
      toast.error(`"${file.name}": erro de conexão.`);
      return false;
    }
  }

  // Fase 242 — upload múltiplo: envia um arquivo por vez (mesmo endpoint de
  // sempre, sem mudança de backend), com progresso "x de N enviados".
  async function uploadDocs(files: FileList) {
    setUploading(true);
    const total = files.length;
    let ok = 0;
    try {
      for (let i = 0; i < total; i++) {
        setUploadProgress({ done: i, total });
        if (await uploadDoc(files[i])) ok++;
      }
      setUploadProgress({ done: total, total });
      if (ok > 0) toast.success(total === 1 ? "Arquivo enviado com sucesso." : `${ok} de ${total} arquivos enviados.`);
      fetchDocs();
    } finally {
      setUploading(false);
      setUploadProgress(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function processarOcr(docId: string) {
    setOcrRunning(docId);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/documents/${docId}/ocr`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        toast.success("OCR iniciado. O texto extraído aparecerá em instantes.");
        setTimeout(fetchDocs, 5000);
      } else {
        toast.error("Erro ao iniciar OCR.");
      }
    } catch {
      toast.error("Erro de conexão.");
    } finally {
      setOcrRunning(null);
    }
  }

  async function verTexto(docId: string, titulo: string) {
    setLoadingTexto(docId);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/documents/${docId}/content`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const d = await res.json();
        setTextoModal({ titulo, texto: d.conteudo_texto || d.conteudo_html || "(sem texto extraído)" });
      } else {
        toast.error("Erro ao carregar o texto do documento.");
      }
    } catch {
      toast.error("Erro de conexão.");
    } finally {
      setLoadingTexto(null);
    }
  }

  async function downloadDoc(id: string, titulo: string) {
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/documents/${id}/download`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const blob = await res.blob();
        const a = Object.assign(document.createElement("a"), {
          href: URL.createObjectURL(blob),
          download: `${titulo.slice(0, 60)}.pdf`,
        });
        a.click();
        URL.revokeObjectURL(a.href);
      } else {
        toast.error("Erro ao baixar documento. Tente novamente.");
      }
    } catch {
      toast.error("Erro de conexão ao baixar documento.");
    }
  }

  async function downloadOriginal(id: string, titulo: string) {
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/documents/${id}/original`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const blob = await res.blob();
        const a = Object.assign(document.createElement("a"), {
          href: URL.createObjectURL(blob),
          download: titulo.slice(0, 60),
        });
        a.click();
        URL.revokeObjectURL(a.href);
      } else {
        toast.error("Erro ao baixar o arquivo original.");
      }
    } catch {
      toast.error("Erro de conexão ao baixar o arquivo original.");
    }
  }

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Documentos" }]} />
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-semibold text-afj-black">Documentos</h1>
          <p className="text-afj-black/50 text-sm">{filtrados.length} documento(s)</p>
        </div>
        <div className="flex items-center gap-3">
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.png,.jpg,.jpeg,.doc,.docx"
            className="hidden"
            onChange={(e) => { const files = e.target.files; if (files && files.length) uploadDocs(files); }}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="btn-afj-outline rounded-sm flex items-center gap-2 disabled:opacity-50"
          >
            {uploading ? <X size={14} className="animate-spin" /> : <Upload size={14} />}
            {uploading && uploadProgress ? `Enviando ${uploadProgress.done + 1} de ${uploadProgress.total}...` : "Upload"}
          </button>
          <button
            onClick={() => { setShowNew(true); setNewForm(emptyForm); }}
            className="btn-afj-primary rounded-sm flex items-center gap-2"
          >
            <Plus size={14} /> Novo documento
          </button>
        </div>
      </div>

      {clientIdFiltro && (
        <div className="flex items-center gap-2 text-xs bg-afj-gold/10 border border-afj-gold/30 rounded-sm px-3 py-2">
          <span className="text-afj-black/70">Mostrando só os documentos deste cliente</span>
          <Link href="/documentos" className="text-afj-gold hover:underline ml-auto">Ver todos</Link>
        </div>
      )}

      {/* Filtros */}
      <div className="flex gap-3 flex-wrap">
        <div className="relative flex-1 min-w-48">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-afj-black/30" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por título..."
            className="w-full pl-9 pr-4 py-2 text-sm border border-afj-cream-dark rounded-sm focus:outline-none focus:border-afj-gold bg-white"
          />
        </div>
        <select
          value={filtroTipo}
          onChange={(e) => setFiltroTipo(e.target.value)}
          className="border border-afj-cream-dark rounded-sm px-3 py-2 text-sm bg-white focus:outline-none focus:border-afj-gold"
        >
          <option value="">Todos os tipos</option>
          {["PETICAO", "CONTRATO", "PROCURACAO", "PARECER", "RECURSO", "OUTROS"].map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <select
          value={filtroStatus}
          onChange={(e) => setFiltroStatus(e.target.value)}
          className="border border-afj-cream-dark rounded-sm px-3 py-2 text-sm bg-white focus:outline-none focus:border-afj-gold"
        >
          <option value="">Todos os status</option>
          <option value="RASCUNHO">Rascunho</option>
          <option value="REVISAO">Em Revisão</option>
          <option value="APROVADO">Aprovado</option>
          <option value="PROTOCOLADO">Protocolado</option>
        </select>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="afj-card p-5 h-32 animate-pulse bg-afj-cream-dark/40" />
          ))}
        </div>
      ) : filtrados.length === 0 ? (
        <div className="afj-card p-12 text-center">
          <FolderOpen className="mx-auto text-afj-black/20 mb-3" size={40} />
          <p className="font-semibold text-afj-black">Nenhum documento encontrado</p>
          <p className="text-afj-black/40 text-sm mt-1">Documentos gerados pelo sistema aparecerão aqui</p>
        </div>
      ) : (
        <div className="afj-card">
          <div className="overflow-x-auto">
          <table className="afj-table">
            <thead>
              <tr>
                <th>Título</th>
                <th>Tipo</th>
                <th>Status</th>
                <th>Versão</th>
                <th>Origem</th>
                <th>Data</th>
                <th>Ações</th>
              </tr>
            </thead>
            <tbody>
              {filtrados.map((d) => (
                <tr key={d.id}>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <FileText size={14} className="text-afj-black/30 flex-shrink-0" />
                      <span className="font-medium text-afj-black">{d.titulo}</span>
                      <OcrBadge d={d} />
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${TIPO_COLORS[d.tipo] ?? "bg-gray-100 text-gray-700"}`}>
                      {d.tipo}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={STATUS_STYLE[d.status] ?? "badge-arquivado"}>{d.status}</span>
                  </td>
                  <td className="px-4 py-3 text-afj-black/50 text-xs">v{d.versao}</td>
                  <td className="px-4 py-3">
                    {d.gerado_por_ia ? (
                      <span className="text-xs bg-purple-100 text-purple-700 px-2 py-0.5 rounded-full">IA</span>
                    ) : (
                      <span className="text-xs text-afj-black/30">Manual</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-afj-black/40 text-xs">
                    {new Date(d.created_at).toLocaleDateString("pt-BR")}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      {d.tem_texto && (
                        <button
                          onClick={() => verTexto(d.id, d.titulo)}
                          disabled={loadingTexto === d.id}
                          className="tap-target text-afj-black/30 hover:text-afj-gold transition-colors disabled:opacity-40"
                          title="Ver texto extraído"
                          aria-label="Ver texto extraído do documento"
                        >
                          <Eye size={14} />
                        </button>
                      )}
                      <button
                        onClick={() => processarOcr(d.id)}
                        disabled={ocrRunning === d.id}
                        className="tap-target text-afj-black/30 hover:text-afj-gold transition-colors disabled:opacity-40"
                        title="Processar OCR (extrair texto)"
                        aria-label="Processar OCR do documento"
                      >
                        <ScanLine size={14} className={ocrRunning === d.id ? "animate-pulse" : ""} />
                      </button>
                      <button
                        onClick={() => abrirEdicao(d)}
                        className="tap-target text-afj-black/30 hover:text-afj-gold transition-colors"
                        title="Editar documento"
                        aria-label="Editar documento"
                      >
                        <Pencil size={14} />
                      </button>
                      <button
                        onClick={() => abrirHistorico(d)}
                        className="tap-target text-afj-black/30 hover:text-afj-gold transition-colors"
                        title="Histórico de versões"
                        aria-label="Histórico de versões"
                      >
                        <History size={14} />
                      </button>
                      <button
                        onClick={() => downloadDoc(d.id, d.titulo)}
                        className="tap-target text-afj-black/30 hover:text-afj-gold transition-colors"
                        title="Baixar PDF"
                        aria-label="Baixar documento como PDF"
                      >
                        <Download size={14} />
                      </button>
                      {d.tem_arquivo_original && (
                        <button
                          onClick={() => downloadOriginal(d.id, d.titulo)}
                          className="tap-target text-afj-black/30 hover:text-afj-gold transition-colors"
                          title="Baixar arquivo original enviado"
                          aria-label="Baixar arquivo original enviado"
                        >
                          <Paperclip size={14} />
                        </button>
                      )}
                      <button
                        onClick={() => excluirDoc(d)}
                        disabled={deleting === d.id}
                        className="tap-target text-afj-black/30 hover:text-red-500 transition-colors disabled:opacity-40"
                        title="Arquivar documento"
                        aria-label="Arquivar documento"
                      >
                        <Trash2 size={14} />
                      </button>
                      {googleConnected && (
                        <button
                          onClick={() => salvarNoDrive(d.id, d.titulo)}
                          disabled={savingDrive === d.id}
                          className="tap-target text-afj-black/30 hover:text-afj-gold transition-colors disabled:opacity-40"
                          title="Salvar no Google Drive (PDF timbrado)"
                          aria-label="Salvar no Google Drive"
                        >
                          <CloudUpload size={14} />
                        </button>
                      )}
                      {googleConnected && (
                        <button
                          onClick={() => salvarComoGoogleDoc(d.id, d.titulo)}
                          disabled={savingDoc === d.id}
                          className="tap-target text-afj-black/30 hover:text-afj-gold transition-colors disabled:opacity-40"
                          title="Salvar como Google Doc (editável, sem timbrado)"
                          aria-label="Salvar como Google Doc"
                        >
                          <FilePlus size={14} />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      )}

      {/* Carregar mais */}
      {hasMore && !loading && (
        <div className="flex justify-center">
          <button
            onClick={() => fetchDocs(offset, true)}
            disabled={loadingMore}
            className="btn-afj-outline rounded-sm text-sm disabled:opacity-50"
          >
            {loadingMore ? "Carregando..." : "Carregar mais documentos"}
          </button>
        </div>
      )}

      {/* Modal: Novo documento */}
      {showNew && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={() => !saving && setShowNew(false)}>
          <div className="afj-card w-full max-w-lg max-h-[85vh] overflow-y-auto p-6 space-y-4" onClick={(e) => e.stopPropagation()}>
            <h2 className="font-display text-lg font-semibold text-afj-black flex items-center gap-2"><Plus size={18} className="text-afj-gold" /> Novo documento</h2>
            <div>
              <label className="text-[11px] text-afj-black/55 block mb-1 uppercase tracking-widest font-semibold">Título</label>
              <input value={newForm.titulo} onChange={(e) => setNewForm({ ...newForm, titulo: e.target.value })}
                placeholder="Ex.: Parecer sobre o caso X" className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold" />
            </div>
            <div>
              <label className="text-[11px] text-afj-black/55 block mb-1 uppercase tracking-widest font-semibold">Tipo</label>
              <select value={newForm.tipo} onChange={(e) => setNewForm({ ...newForm, tipo: e.target.value })}
                className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm bg-white focus:outline-none focus:border-afj-gold">
                {TIPOS.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <label className="text-[11px] text-afj-black/55 block mb-1 uppercase tracking-widest font-semibold">Conteúdo</label>
              <textarea value={newForm.conteudo_texto} onChange={(e) => setNewForm({ ...newForm, conteudo_texto: e.target.value })}
                rows={8} placeholder="Digite o conteúdo do documento..." className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold resize-none" />
            </div>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowNew(false)} disabled={saving} className="btn-afj-outline rounded-sm text-sm py-2 px-4">Cancelar</button>
              <button onClick={criarDoc} disabled={saving} className="btn-afj-primary rounded-sm text-sm py-2 px-4 flex items-center gap-2">
                {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Criar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Editar documento */}
      {editDoc && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={() => !saving && setEditDoc(null)}>
          <div className="afj-card w-full max-w-lg max-h-[85vh] overflow-y-auto p-6 space-y-4" onClick={(e) => e.stopPropagation()}>
            <h2 className="font-display text-lg font-semibold text-afj-black flex items-center gap-2"><Pencil size={18} className="text-afj-gold" /> Editar documento</h2>
            <div>
              <label className="text-[11px] text-afj-black/55 block mb-1 uppercase tracking-widest font-semibold">Título</label>
              <input value={editForm.titulo} onChange={(e) => setEditForm({ ...editForm, titulo: e.target.value })}
                className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[11px] text-afj-black/55 block mb-1 uppercase tracking-widest font-semibold">Tipo</label>
                <select value={editForm.tipo} onChange={(e) => setEditForm({ ...editForm, tipo: e.target.value })}
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm bg-white focus:outline-none focus:border-afj-gold">
                  {TIPOS.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div>
                <label className="text-[11px] text-afj-black/55 block mb-1 uppercase tracking-widest font-semibold">Status</label>
                <select value={editForm.status} onChange={(e) => setEditForm({ ...editForm, status: e.target.value })}
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm bg-white focus:outline-none focus:border-afj-gold">
                  {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
            </div>
            {editForm.status === "PROTOCOLADO" && (
              <div>
                <label className="text-[11px] text-afj-black/55 block mb-1 uppercase tracking-widest font-semibold">
                  Alerta de follow-up (dias sem retorno da corte)
                </label>
                <input
                  type="number" min={1}
                  value={editForm.follow_up_dias}
                  onChange={(e) => setEditForm({ ...editForm, follow_up_dias: e.target.value })}
                  placeholder="ex.: 30 (deixe vazio pra não alertar)"
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                />
                {editDoc?.protocolado_em && (
                  <p className="text-[11px] text-afj-black/40 mt-1">
                    Protocolada em {new Date(editDoc.protocolado_em).toLocaleDateString("pt-BR")}
                    {editDoc.follow_up_alertado && " — alerta já disparado"}
                  </p>
                )}
              </div>
            )}
            <div>
              <label className="text-[11px] text-afj-black/55 block mb-1 uppercase tracking-widest font-semibold">Conteúdo</label>
              <textarea value={editForm.conteudo_texto} onChange={(e) => setEditForm({ ...editForm, conteudo_texto: e.target.value })}
                rows={10} disabled={loadingEdit}
                placeholder={loadingEdit ? "Carregando conteúdo..." : "Conteúdo do documento..."}
                className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold resize-none disabled:opacity-60" />
            </div>

            <div>
              <button onClick={verificarCitacoes} disabled={verificando || loadingEdit}
                className="btn-afj-outline rounded-sm text-xs py-1.5 px-3 flex items-center gap-1.5 disabled:opacity-50">
                {verificando ? <Loader2 size={13} className="animate-spin" /> : <Scale size={13} />}
                {verificando ? "Verificando..." : "Verificar citações"}
              </button>
              {citacoes && citacoes.length > 0 && (
                <div className="mt-2 space-y-1.5">
                  {citacoes.map((c) => {
                    const cfg = c.status === "confirmada"
                      ? { icon: CheckCircle2, cls: "bg-green-50 text-green-700 border-green-200", label: "Confirmada" }
                      : c.status === "nao_encontrada"
                      ? { icon: AlertTriangle, cls: "bg-amber-50 text-amber-700 border-amber-200", label: "Não encontrada" }
                      : { icon: HelpCircle, cls: "bg-gray-50 text-gray-500 border-gray-200", label: "Não verificável" };
                    const Icon = cfg.icon;
                    return (
                      <div key={c.referencia} className={`flex items-center gap-2 text-xs px-2.5 py-1.5 rounded-sm border ${cfg.cls}`}>
                        <Icon size={13} className="flex-shrink-0" />
                        <span className="font-medium">{c.tipo === "PROCESSO" ? "Processo" : "Lei"} {c.referencia}</span>
                        <span className="opacity-70">— {cfg.label}{c.titulo ? `: ${c.titulo}` : ""}</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            <p className="text-[11px] text-afj-black/40">Aprovar/protocolar é restrito a advogados, sócios e administradores.</p>
            <div className="flex gap-2 justify-end">
              <button onClick={() => setEditDoc(null)} disabled={saving} className="btn-afj-outline rounded-sm text-sm py-2 px-4">Cancelar</button>
              <button onClick={salvarEdicao} disabled={saving || loadingEdit} className="btn-afj-primary rounded-sm text-sm py-2 px-4 flex items-center gap-2">
                {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Salvar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Histórico de versões */}
      {histDoc && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={() => setHistDoc(null)}>
          <div className="afj-card w-full max-w-lg max-h-[80vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-3 border-b border-afj-cream-dark">
              <div className="flex items-center gap-2 min-w-0">
                <History size={16} className="text-afj-gold flex-shrink-0" />
                <span className="font-semibold text-afj-black truncate">Histórico — {histDoc.titulo}</span>
              </div>
              <button onClick={() => setHistDoc(null)} className="text-afj-black/40 hover:text-afj-black" aria-label="Fechar"><X size={18} /></button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-2">
              {loadingHist ? (
                Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-12 bg-afj-cream-dark rounded animate-pulse" />)
              ) : versoes.length === 0 ? (
                <p className="text-sm text-afj-black/40 text-center py-8">Ainda não há versões anteriores. Edite o conteúdo do documento para começar o histórico.</p>
              ) : (
                versoes.map((v) => (
                  <div key={v.id} className="flex items-center justify-between gap-3 border border-afj-cream-dark rounded-sm px-3 py-2.5">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-afj-black">v{v.versao} <span className="text-afj-black/45 font-normal">· {v.change_summary || "—"}</span></p>
                      <p className="text-xs text-afj-black/40">{v.autor || "—"}{v.created_at ? ` · ${new Date(v.created_at).toLocaleString("pt-BR")}` : ""}</p>
                    </div>
                    <button onClick={() => restaurarVersao(v)} disabled={restaurando === v.id}
                      className="btn-afj-outline rounded-sm py-1.5 px-3 text-xs flex items-center gap-1.5 flex-shrink-0 disabled:opacity-50">
                      {restaurando === v.id ? <Loader2 size={12} className="animate-spin" /> : <RotateCcw size={12} />} Restaurar
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* Modal: texto extraído (OCR ou conteúdo do documento) */}
      {textoModal && (
        <div
          className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
          onClick={() => setTextoModal(null)}
        >
          <div
            className="afj-card w-full max-w-2xl max-h-[80vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-5 py-3 border-b border-afj-cream-dark">
              <div className="flex items-center gap-2 min-w-0">
                <FileText size={16} className="text-afj-gold flex-shrink-0" />
                <span className="font-semibold text-afj-black truncate">{textoModal.titulo}</span>
              </div>
              <button
                onClick={() => setTextoModal(null)}
                className="text-afj-black/40 hover:text-afj-black transition-colors"
                aria-label="Fechar"
              >
                <X size={18} />
              </button>
            </div>
            <pre className="flex-1 overflow-auto px-5 py-4 text-sm text-afj-black/80 whitespace-pre-wrap font-sans leading-relaxed">
              {textoModal.texto}
            </pre>
          </div>
        </div>
      )}
      {confirmDialog}
    </div>
  );
}
