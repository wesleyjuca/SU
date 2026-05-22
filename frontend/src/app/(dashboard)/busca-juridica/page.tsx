"use client";
import { useState } from "react";
import { BookOpen, Search, Loader2, Copy, Check, AlertTriangle } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";

interface RagResult {
  id: string;
  score: number;
  collection: string;
  content: string;
  metadata: Record<string, string | undefined>;
}

const COLECOES = [
  { value: "jurisprudencia", label: "Jurisprudência", color: "bg-blue-100 text-blue-700" },
  { value: "legislacao", label: "Legislação", color: "bg-green-100 text-green-700" },
  { value: "doutrina", label: "Doutrina", color: "bg-purple-100 text-purple-700" },
  { value: "peticoes_afj", label: "Petições AFJ", color: "bg-amber-100 text-amber-700" },
  { value: "memorias_afj", label: "Memórias AFJ", color: "bg-orange-100 text-orange-700" },
  { value: "documentos_clientes", label: "Docs. Clientes", color: "bg-teal-100 text-teal-700" },
];

function scoreColor(score: number): string {
  if (score >= 0.85) return "bg-green-100 text-green-700";
  if (score >= 0.70) return "bg-amber-100 text-amber-700";
  return "bg-gray-100 text-gray-500";
}

function colecaoColor(col: string): string {
  return COLECOES.find((c) => c.value === col)?.color ?? "bg-gray-100 text-gray-600";
}

function colecaoLabel(col: string): string {
  return COLECOES.find((c) => c.value === col)?.label ?? col;
}

export default function BuscaJuridicaPage() {
  const [query, setQuery] = useState("");
  const [selectedCols, setSelectedCols] = useState<string[]>(["jurisprudencia", "legislacao"]);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<RagResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  function toggleColecao(val: string) {
    setSelectedCols((prev) =>
      prev.includes(val) ? prev.filter((c) => c !== val) : [...prev, val]
    );
  }

  async function buscar(e?: React.FormEvent) {
    if (e) e.preventDefault();
    if (!query.trim() || selectedCols.length === 0) return;
    setLoading(true);
    setError(null);
    setResults(null);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/rag/search", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          query: query.trim(),
          collections: selectedCols,
          k: 8,
          score_threshold: 0.5,
        }),
      });
      if (!res.ok) {
        setError("Erro ao buscar. Verifique se a base vetorial está disponível.");
        return;
      }
      const data = await res.json();
      setResults(Array.isArray(data) ? data : (data.results ?? []));
    } catch {
      setError("Erro de conexão com a base vetorial.");
    } finally {
      setLoading(false); }
  }

  async function copiar(id: string, text: string) {
    await navigator.clipboard.writeText(text);
    setCopied(id);
    setTimeout(() => setCopied(null), 1500);
  }

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Pesquisa Jurídica" }]} />

      <div>
        <h1 className="font-display text-2xl font-semibold text-afj-black">Pesquisa Jurídica</h1>
        <p className="text-afj-black/50 text-sm mt-0.5">
          Busca semântica em jurisprudência, legislação, doutrina e memórias do escritório
        </p>
      </div>

      {/* Formulário de busca */}
      <form onSubmit={buscar} className="afj-card p-5 space-y-4">
        <div className="relative">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-afj-black/30" />
          <textarea
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); buscar(); }
            }}
            placeholder="Ex: rescisão contratual por inadimplemento, prazo recursal, dano moral..."
            rows={2}
            className="w-full pl-9 pr-4 py-2.5 text-sm border border-afj-cream-dark rounded-sm focus:outline-none focus:border-afj-gold resize-none"
          />
        </div>

        <div>
          <p className="text-xs text-afj-black/50 mb-2">Bases de conhecimento:</p>
          <div className="flex flex-wrap gap-2">
            {COLECOES.map((col) => (
              <button
                key={col.value}
                type="button"
                onClick={() => toggleColecao(col.value)}
                className={`text-xs px-3 py-1.5 rounded-sm border transition-colors ${
                  selectedCols.includes(col.value)
                    ? "border-afj-gold bg-afj-gold/5 text-afj-gold font-medium"
                    : "border-afj-cream-dark text-afj-black/50 hover:border-afj-gold/50"
                }`}
              >
                {col.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center justify-between">
          <p className="text-xs text-afj-black/30">
            Enter para buscar · Shift+Enter para nova linha
          </p>
          <button
            type="submit"
            disabled={loading || !query.trim() || selectedCols.length === 0}
            className="btn-afj-primary rounded-sm flex items-center gap-2 disabled:opacity-40"
          >
            {loading ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />}
            {loading ? "Buscando..." : "Buscar"}
          </button>
        </div>
      </form>

      {/* Estado de erro */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-sm p-4 flex items-start gap-3">
          <AlertTriangle size={16} className="text-red-500 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {/* Skeleton loader */}
      {loading && (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="afj-card p-5 space-y-2 animate-pulse">
              <div className="h-4 bg-afj-cream-dark rounded w-3/4" />
              <div className="h-3 bg-afj-cream-dark rounded w-full" />
              <div className="h-3 bg-afj-cream-dark rounded w-5/6" />
            </div>
          ))}
        </div>
      )}

      {/* Resultados */}
      {results !== null && !loading && (
        <>
          {results.length === 0 ? (
            <div className="afj-card p-10 text-center">
              <BookOpen className="mx-auto text-afj-black/20 mb-3" size={36} />
              <p className="font-semibold text-afj-black">Nenhum resultado encontrado</p>
              <p className="text-afj-black/40 text-sm mt-1">
                Tente ampliar a busca ou selecionar outras bases de conhecimento.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-xs text-afj-black/40">{results.length} resultado(s)</p>

              {results.map((r) => (
                <div key={r.id} className="afj-card p-4 hover:border-afj-gold/20 transition-colors">
                  <div className="flex items-start justify-between gap-3 mb-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${colecaoColor(r.collection)}`}>
                        {colecaoLabel(r.collection)}
                      </span>
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${scoreColor(r.score)}`}>
                        {(r.score * 100).toFixed(0)}% relevância
                      </span>
                    </div>
                    <button
                      onClick={() => copiar(r.id, r.content)}
                      title="Copiar trecho"
                      aria-label="Copiar trecho do resultado"
                      className="text-afj-black/30 hover:text-afj-gold transition-colors flex-shrink-0"
                    >
                      {copied === r.id ? <Check size={14} className="text-green-500" /> : <Copy size={14} />}
                    </button>
                  </div>

                  <p className="text-sm text-afj-black/80 leading-relaxed">{r.content}</p>

                  {/* Metadados disponíveis */}
                  {r.metadata && Object.keys(r.metadata).length > 0 && (
                    <div className="mt-2 pt-2 border-t border-afj-cream-dark flex flex-wrap gap-x-4 gap-y-1">
                      {[
                        ["Tribunal", r.metadata.tribunal],
                        ["Processo", r.metadata.numero_processo],
                        ["Relator", r.metadata.relator],
                        ["Data", r.metadata.data],
                        ["Fonte", r.metadata.fonte],
                        ["Artigo", r.metadata.artigo],
                      ].map(([label, value]) => value && (
                        <span key={label} className="text-xs text-afj-black/40">
                          <span className="font-medium">{label}:</span> {value}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}

              <div className="bg-amber-50 border border-amber-200 rounded-sm p-3 flex items-start gap-2">
                <AlertTriangle size={14} className="text-amber-600 flex-shrink-0 mt-0.5" />
                <p className="text-xs text-amber-800">
                  Verifique sempre a fonte antes de citar em peça processual. Resultados são trechos de documentos indexados e podem estar desatualizados.
                </p>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
