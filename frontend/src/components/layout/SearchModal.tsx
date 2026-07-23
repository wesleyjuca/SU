"use client";
import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Search, Scale, Users, FolderOpen, X, Loader2, Compass } from "lucide-react";
import api from "@/lib/api";
import { useUserStore } from "@/store";
import { flatNavForRole } from "@/lib/nav";

interface Result {
  id: string;
  label: string;
  sub: string;
  href: string;
  type: "processo" | "cliente" | "documento" | "pagina";
  newTab?: boolean;
}

interface SearchModalProps {
  open: boolean;
  onClose: () => void;
}

export function SearchModal({ open, onClose }: SearchModalProps) {
  const router = useRouter();
  const { user } = useUserStore();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Result[]>([]);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (open) {
      setQuery("");
      setResults([]);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  // Rotas/itens de menu que o papel pode ver e cujo rótulo casa com a busca —
  // permite ir a Financeiro/Configurações/Integrações/etc. por busca (menos cliques).
  const paginasMatch = useCallback((q: string): Result[] => {
    const termo = q.trim().toLowerCase();
    if (!termo) return [];
    return flatNavForRole(user?.role)
      .filter((i) => i.label.toLowerCase().includes(termo))
      .slice(0, 6)
      .map((i) => ({ id: i.href, label: i.label, sub: "Ir para a página", href: i.href, type: "pagina" as const, newTab: i.newTab }));
  }, [user?.role]);

  const search = useCallback(async (q: string) => {
    if (!q.trim()) { setResults([]); return; }
    const paginas = paginasMatch(q);
    setResults(paginas);   // páginas aparecem instantâneas (sem esperar a rede)
    setLoading(true);
    try {
      const [procs, clients, docs] = await Promise.allSettled([
        api.get<{ id: string; numero_cnj: string; tribunal: string; area_direito: string }[]>(`/processes?search=${encodeURIComponent(q)}&limit=5`),
        api.get<{ id: string; nome_completo: string; email: string | null }[]>(`/clients?search=${encodeURIComponent(q)}&limit=5`),
        api.get<{ id: string; titulo: string; tipo: string }[]>(`/documents?search=${encodeURIComponent(q)}&limit=5`),
      ]);
      const combined: Result[] = [...paginas];
      if (procs.status === "fulfilled") {
        procs.value.forEach((p) => combined.push({ id: p.id, label: p.numero_cnj, sub: `${p.tribunal} · ${p.area_direito}`, href: `/processos/${p.id}`, type: "processo" }));
      }
      if (clients.status === "fulfilled") {
        clients.value.forEach((c) => combined.push({ id: c.id, label: c.nome_completo, sub: c.email ?? "Cliente", href: `/clientes`, type: "cliente" }));
      }
      if (docs.status === "fulfilled") {
        docs.value.forEach((d) => combined.push({ id: d.id, label: d.titulo, sub: d.tipo, href: `/documentos`, type: "documento" }));
      }
      setResults(combined);
    } finally {
      setLoading(false);
    }
  }, [paginasMatch]);

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const v = e.target.value;
    setQuery(v);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => search(v), 300);
  }

  function navigate(href: string, newTab?: boolean) {
    if (newTab) { window.open(href, "_blank", "noopener,noreferrer"); onClose(); return; }
    router.push(href);
    onClose();
  }

  if (!open) return null;

  const icon = { processo: <Scale size={14} className="text-afj-gold" />, cliente: <Users size={14} className="text-blue-500" />, documento: <FolderOpen size={14} className="text-green-500" />, pagina: <Compass size={14} className="text-afj-black/40" /> };

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-start justify-center pt-16 px-4" onClick={onClose}>
      <div className="w-full max-w-xl bg-white rounded-xl shadow-2xl overflow-hidden" onClick={(e) => e.stopPropagation()}>
        {/* Input */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-afj-cream-dark">
          <Search size={16} className="text-afj-black/40 flex-shrink-0" />
          <input
            ref={inputRef}
            value={query}
            onChange={handleChange}
            placeholder="Buscar processos, clientes, documentos..."
            className="flex-1 text-sm text-afj-black outline-none placeholder:text-afj-black/30"
          />
          {loading ? (
            <Loader2 size={14} className="text-afj-black/30 animate-spin flex-shrink-0" />
          ) : (
            <button onClick={onClose} className="text-afj-black/30 hover:text-afj-black transition-colors">
              <X size={14} />
            </button>
          )}
        </div>

        {/* Results */}
        <div className="max-h-80 overflow-y-auto">
          {query && results.length === 0 && !loading && (
            <p className="px-4 py-6 text-center text-sm text-afj-black/40">Nenhum resultado para &ldquo;{query}&rdquo;</p>
          )}
          {!query && (
            <p className="px-4 py-6 text-center text-sm text-afj-black/30">Digite para buscar</p>
          )}
          {results.map((r) => (
            <button
              key={`${r.type}-${r.id}`}
              onClick={() => navigate(r.href, r.newTab)}
              className="w-full flex items-center gap-3 px-4 py-3 hover:bg-afj-cream/60 transition-colors text-left"
            >
              <span className="flex-shrink-0">{icon[r.type]}</span>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-afj-black truncate">{r.label}</p>
                <p className="text-xs text-afj-black/40 truncate">{r.sub}</p>
              </div>
            </button>
          ))}
        </div>

        {/* Footer hint */}
        <div className="px-4 py-2 border-t border-afj-cream-dark flex items-center gap-3 text-xs text-afj-black/30">
          <span><kbd className="font-mono">↵</kbd> selecionar</span>
          <span><kbd className="font-mono">esc</kbd> fechar</span>
        </div>
      </div>
    </div>
  );
}
