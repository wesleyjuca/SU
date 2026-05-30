"use client";
import { useState, useEffect, useRef } from "react";
import { FolderOpen, Search, FileText, Download, Upload, ScanLine, X } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { useToast } from "@/components/ui/Toast";

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

export default function DocumentosPage() {
  const toast = useToast();
  const [docs, setDocs] = useState<Documento[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filtroTipo, setFiltroTipo] = useState("");
  const [filtroStatus, setFiltroStatus] = useState("");
  const [uploading, setUploading] = useState(false);
  const [ocrRunning, setOcrRunning] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { fetchDocs(); }, [filtroTipo, filtroStatus]);

  async function fetchDocs() {
    setLoading(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const params = new URLSearchParams();
      if (filtroTipo) params.set("tipo", filtroTipo);
      if (filtroStatus) params.set("status", filtroStatus);
      const res = await fetch(`/api/v1/documents?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setDocs(await res.json());
    } finally { setLoading(false); }
  }

  const filtrados = docs.filter((d) =>
    !search || d.titulo.toLowerCase().includes(search.toLowerCase())
  );

  async function uploadDoc(file: File) {
    setUploading(true);
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
      if (res.ok) {
        toast.success(`"${file.name}" enviado com sucesso.`);
        fetchDocs();
      } else {
        const d = await res.json().catch(() => ({}));
        toast.error(d.detail || "Erro ao enviar arquivo.");
      }
    } catch {
      toast.error("Erro de conexão ao enviar arquivo.");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function processarOcr(docId: string) {
    setOcrRunning(docId);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/agents/trigger", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          task_type: "ocr_document",
          task_input: { document_id: docId },
        }),
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
            accept=".pdf,.png,.jpg,.jpeg,.doc,.docx"
            className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadDoc(f); }}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="btn-afj-outline rounded-sm flex items-center gap-2 disabled:opacity-50"
          >
            {uploading ? <X size={14} className="animate-spin" /> : <Upload size={14} />}
            {uploading ? "Enviando..." : "Upload"}
          </button>
        </div>
      </div>

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
        <div className="afj-card overflow-hidden">
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
                      <button
                        onClick={() => processarOcr(d.id)}
                        disabled={ocrRunning === d.id}
                        className="text-afj-black/30 hover:text-afj-gold transition-colors disabled:opacity-40"
                        title="Processar OCR"
                        aria-label="Processar OCR do documento"
                      >
                        <ScanLine size={14} />
                      </button>
                      <button
                        onClick={() => downloadDoc(d.id, d.titulo)}
                        className="text-afj-black/30 hover:text-afj-gold transition-colors"
                        title="Baixar PDF"
                        aria-label="Baixar documento como PDF"
                      >
                        <Download size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
