"use client";
// Fase 258 — seletor real de pastas do Google Drive, via Drive API (usando
// só a permissão já concedida na conexão OAuth) — substitui o fluxo antigo
// de colar link/ID de uma pasta pública/compartilhada. Reusado tanto pra
// `google_drive_doutrina` (pasta de pesquisa, alimenta a sincronização
// diária que indexa doutrina no RAG) quanto `google_workspace` (pasta de
// salvamento, nova nesta fase — documentos gerados deixam de cair sempre
// na raiz do Drive). Mesmo esqueleto visual dos 2 modais já existentes em
// `integracoes/page.tsx` (overlay + card branco), mesmo espírito de busca
// assíncrona (loading/erro/vazio) de `components/layout/SearchModal.tsx`.
import { useEffect, useState } from "react";
import { FolderOpen, Loader2, X } from "lucide-react";

interface DriveFolderPickerProps {
  provider: "google_drive_doutrina" | "google_workspace";
  onSelect: (folderId: string, folderName: string) => void;
  onClose: () => void;
}

interface DrivePasta {
  id: string;
  name: string;
  parents?: string[] | null;
}

function authH(): HeadersInit {
  const t = typeof window !== "undefined" ? localStorage.getItem("afj_access_token") : null;
  return { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) };
}

export function DriveFolderPicker({ provider, onSelect, onClose }: DriveFolderPickerProps) {
  const [pastas, setPastas] = useState<DrivePasta[]>([]);
  // breadcrumb: pilha de pastas visitadas — vazia = raiz ("Meu Drive").
  const [caminho, setCaminho] = useState<{ id: string; name: string }[]>([]);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const parentAtual = caminho.length ? caminho[caminho.length - 1].id : undefined;

  useEffect(() => {
    carregar(parentAtual);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [parentAtual]);

  async function carregar(parentId?: string) {
    setCarregando(true);
    setErro(null);
    try {
      const qs = parentId ? `?parent_id=${encodeURIComponent(parentId)}` : "";
      const res = await fetch(`/api/v1/integrations/hub/${provider}/folders${qs}`, { headers: authH() });
      const d = await res.json().catch(() => ({}));
      if (res.ok) {
        setPastas(d.pastas || []);
      } else if (res.status === 401) {
        setErro("O token expirou ou foi revogado — reconecte a integração antes de escolher a pasta.");
      } else if (res.status === 403) {
        setErro(d.detail || "Permissão negada — pode ser necessário reconectar para conceder acesso a pastas.");
      } else if (res.status === 404) {
        setErro(d.detail || "Pasta não encontrada — pode ter sido removida.");
      } else {
        setErro(d.detail || "Não foi possível carregar as pastas.");
      }
    } catch {
      setErro("Falha de conexão.");
    } finally {
      setCarregando(false);
    }
  }

  function entrarNaPasta(p: DrivePasta) {
    setCaminho((prev) => [...prev, { id: p.id, name: p.name }]);
  }

  function voltarAte(index: number) {
    // index === -1 volta pra raiz.
    setCaminho((prev) => prev.slice(0, index + 1));
  }

  function selecionarAtual() {
    const nomeAtual = caminho.length ? caminho[caminho.length - 1].name : "Meu Drive";
    const idAtual = parentAtual ?? "root";
    onSelect(idAtual, nomeAtual);
  }

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-white rounded-sm shadow-xl w-full max-w-md p-5 max-h-[85vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-1">
          <h3 className="font-semibold text-afj-black text-sm">Escolher pasta do Drive</h3>
          <button onClick={onClose} className="text-afj-black/40 hover:text-afj-black p-1">
            <X size={16} />
          </button>
        </div>

        {/* Breadcrumb */}
        <div className="flex items-center gap-1 text-xs text-afj-black/55 flex-wrap mb-3">
          <button onClick={() => voltarAte(-1)} className="hover:text-afj-gold underline underline-offset-2">
            Meu Drive
          </button>
          {caminho.map((c, i) => (
            <span key={c.id} className="flex items-center gap-1">
              <span>/</span>
              <button onClick={() => voltarAte(i)} className="hover:text-afj-gold underline underline-offset-2">
                {c.name}
              </button>
            </span>
          ))}
        </div>

        {/* Lista de subpastas */}
        <div className="flex-1 overflow-y-auto border border-afj-cream-dark rounded-sm min-h-[160px]">
          {carregando ? (
            <div className="p-4 flex justify-center">
              <Loader2 size={16} className="animate-spin text-afj-gold" />
            </div>
          ) : erro ? (
            <p className="p-4 text-xs text-red-600">{erro}</p>
          ) : pastas.length === 0 ? (
            <p className="p-4 text-xs text-afj-black/45">Nenhuma subpasta aqui.</p>
          ) : (
            pastas.map((p) => (
              <button
                key={p.id}
                onClick={() => entrarNaPasta(p)}
                className="w-full text-left px-3 py-2 text-sm hover:bg-afj-cream flex items-center gap-2 border-b border-afj-cream-dark last:border-0"
              >
                <FolderOpen size={14} className="text-afj-gold flex-shrink-0" /> {p.name}
              </button>
            ))
          )}
        </div>

        <div className="flex justify-end gap-2 mt-4">
          <button onClick={onClose} className="btn-afj-outline text-xs py-1.5 px-3 rounded-sm">
            Cancelar
          </button>
          <button
            onClick={selecionarAtual}
            className="btn-afj-primary text-xs py-1.5 px-4 rounded-sm flex items-center gap-1.5"
          >
            <FolderOpen size={12} /> Selecionar esta pasta
          </button>
        </div>
      </div>
    </div>
  );
}
