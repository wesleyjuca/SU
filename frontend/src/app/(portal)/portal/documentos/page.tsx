"use client";
import { useState, useEffect } from "react";
import { FileText, Download, Loader2 } from "lucide-react";
import { portalApi, getPortalToken } from "@/lib/portalApi";
import { useToast } from "@/components/ui/Toast";

interface PortalDocumento {
  id: string;
  titulo: string;
  tipo: string | null;
  status: string;
  versao: number;
  created_at: string;
}

const TIPO_LABEL: Record<string, string> = {
  PETICAO: "Petição",
  CONTRATO: "Contrato",
  PROCURACAO: "Procuração",
  SENTENCA: "Sentença",
};

const STATUS_BADGE: Record<string, string> = {
  APROVADO: "bg-green-100 text-green-700",
  PROTOCOLADO: "bg-blue-100 text-blue-700",
};

const TIPO_FILTER = ["TODOS", "PETICAO", "CONTRATO", "PROCURACAO", "SENTENCA"];

export default function PortalDocumentosPage() {
  const toast = useToast();
  const [docs, setDocs] = useState<PortalDocumento[]>([]);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [filter, setFilter] = useState("TODOS");

  useEffect(() => { loadDocs(); }, []);

  async function loadDocs() {
    try {
      const data = await portalApi.get<PortalDocumento[]>("/portal/documents");
      setDocs(data);
    } catch {
      toast.error("Erro ao carregar documentos.");
    } finally {
      setLoading(false);
    }
  }

  async function downloadDoc(docId: string, titulo: string) {
    setDownloading(docId);
    try {
      const token = getPortalToken();
      const apiBase = process.env.NEXT_PUBLIC_API_URL
        ? `${process.env.NEXT_PUBLIC_API_URL}/api/v1`
        : "/api/v1";
      const res = await fetch(`${apiBase}/portal/documents/${docId}/content`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) { toast.error("Erro ao baixar documento."); return; }
      const data = await res.json();
      const content = data.conteudo_html ?? data.conteudo_texto ?? "";
      if (!content) { toast.error("Documento sem conteúdo disponível."); return; }
      const blob = new Blob([content], { type: "text/html;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = Object.assign(document.createElement("a"), {
        href: url,
        download: `${titulo}.html`,
      });
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Erro ao baixar documento.");
    } finally {
      setDownloading(null);
    }
  }

  const filtered = filter === "TODOS" ? docs : docs.filter((d) => d.tipo === filter);

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-7 w-48 bg-gray-200 rounded animate-pulse" />
        <div className="bg-white rounded-xl border border-gray-200 h-48 animate-pulse" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">Documentos</h1>
        <span className="text-sm text-gray-500">{filtered.length} documento{filtered.length !== 1 ? "s" : ""}</span>
      </div>

      {/* Filter chips */}
      <div className="flex gap-2 flex-wrap">
        {TIPO_FILTER.map((t) => (
          <button
            key={t}
            onClick={() => setFilter(t)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors border ${
              filter === t
                ? "bg-[#B8954A] text-white border-[#B8954A]"
                : "bg-white text-gray-600 border-gray-200 hover:border-[#B8954A]/40"
            }`}
          >
            {t === "TODOS" ? "Todos" : TIPO_LABEL[t] ?? t}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
          <FileText className="mx-auto text-gray-300 mb-3" size={36} />
          <p className="font-semibold text-gray-600">Nenhum documento disponível</p>
          <p className="text-sm text-gray-400 mt-1">Documentos aprovados aparecerão aqui.</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Título</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider hidden sm:table-cell">Tipo</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider hidden md:table-cell">Data</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider hidden sm:table-cell">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {filtered.map((d) => (
                <tr key={d.id} className="hover:bg-gray-50/50 transition-colors">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <FileText size={14} className="text-gray-400 flex-shrink-0" />
                      <span className="font-medium text-gray-800 truncate max-w-[180px]">{d.titulo}</span>
                    </div>
                    {d.tipo && (
                      <span className="sm:hidden text-[10px] text-gray-400 ml-5">{TIPO_LABEL[d.tipo] ?? d.tipo}</span>
                    )}
                  </td>
                  <td className="px-4 py-3 hidden sm:table-cell">
                    <span className="text-xs text-gray-600">{d.tipo ? (TIPO_LABEL[d.tipo] ?? d.tipo) : "—"}</span>
                  </td>
                  <td className="px-4 py-3 hidden md:table-cell">
                    <span className="text-xs text-gray-500">{new Date(d.created_at).toLocaleDateString("pt-BR")}</span>
                  </td>
                  <td className="px-4 py-3 hidden sm:table-cell">
                    <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${STATUS_BADGE[d.status] ?? "bg-gray-100 text-gray-500"}`}>
                      {d.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => downloadDoc(d.id, d.titulo)}
                      disabled={downloading === d.id}
                      className="flex items-center gap-1.5 text-xs font-medium text-[#B8954A] hover:text-[#a07d3a] disabled:opacity-50 ml-auto"
                    >
                      {downloading === d.id ? (
                        <Loader2 size={13} className="animate-spin" />
                      ) : (
                        <Download size={13} />
                      )}
                      Baixar
                    </button>
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
