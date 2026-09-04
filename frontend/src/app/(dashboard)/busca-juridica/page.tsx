"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { BookOpen, Search, Loader2, Copy, Check, AlertTriangle, Upload, ChevronDown, ChevronUp, BarChart2 } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { useToast } from "@/components/ui/Toast";
import { useUserStore } from "@/store";

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
  // Achado real: coleção privada por tenant, populada automaticamente pela
  // sincronização do Google Drive (Integrações → Google Drive — Doutrina)
  // — distinta de "doutrina" (pública/compartilhada, manual). Antes desta
  // fase, essa coleção nunca aparecia aqui — mesmo com a sincronização
  // funcionando, o conteúdo nunca ficava buscável nem contado na tela.
  { value: "doutrina_privada", label: "Doutrina AFJ", color: "bg-fuchsia-100 text-fuchsia-700" },
  { value: "peticoes_afj", label: "Petições AFJ", color: "bg-amber-100 text-amber-700" },
  { value: "memorias_afj", label: "Memórias AFJ", color: "bg-orange-100 text-orange-700" },
  { value: "documentos_clientes", label: "Docs. Clientes", color: "bg-teal-100 text-teal-700" },
];

// Coleções sem pipeline de ingestão automática — só estas podem ser populadas manualmente.
const COLECOES_INDEXAVEIS = COLECOES.filter((c) =>
  ["jurisprudencia", "legislacao", "doutrina", "memorias_afj"].includes(c.value)
);

const CAMPOS_METADADO = [
  { key: "tribunal", label: "Tribunal" },
  { key: "numero_processo", label: "Nº do processo" },
  { key: "relator", label: "Relator" },
  { key: "data", label: "Data" },
  { key: "fonte", label: "Fonte" },
  { key: "artigo", label: "Artigo" },
] as const;

function PainelIndexacao() {
  const toast = useToast();
  const [aberto, setAberto] = useState(false);
  const [content, setContent] = useState("");
  const [collection, setCollection] = useState(COLECOES_INDEXAVEIS[0].value);
  const [metadata, setMetadata] = useState<Record<string, string>>({});
  const [enviando, setEnviando] = useState(false);

  async function indexar() {
    if (!content.trim()) return;
    setEnviando(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const metadataLimpo = Object.fromEntries(
        Object.entries(metadata).filter(([, v]) => v && v.trim())
      );
      const res = await fetch("/api/v1/rag/ingest", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ content: content.trim(), collection, metadata: metadataLimpo }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        toast.error(data.detail || "Erro ao indexar documento.");
        return;
      }
      toast.success(`Indexado (${data.chunks_created ?? 0} trecho(s)) em ${colecaoLabel(collection)}.`);
      setContent("");
      setMetadata({});
    } catch {
      toast.error("Erro de conexão ao indexar documento.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <div className="afj-card p-0 overflow-hidden">
      <button
        type="button"
        onClick={() => setAberto((v) => !v)}
        className="w-full flex items-center justify-between px-5 py-3 text-left"
      >
        <span className="flex items-center gap-2 text-sm font-medium text-afj-black">
          <Upload size={14} className="text-afj-gold" />
          Indexar documento
        </span>
        {aberto ? <ChevronUp size={15} className="text-afj-black/40" /> : <ChevronDown size={15} className="text-afj-black/40" />}
      </button>

      {aberto && (
        <div className="px-5 pb-5 space-y-3 border-t border-afj-cream-dark pt-4">
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="Cole o texto do documento a indexar..."
            rows={4}
            className="w-full px-3 py-2.5 text-sm border border-afj-cream-dark rounded-sm focus:outline-none focus:border-afj-gold resize-none"
          />

          <div>
            <p className="text-xs text-afj-black/50 mb-1.5">Base de conhecimento:</p>
            <select
              value={collection}
              onChange={(e) => setCollection(e.target.value)}
              className="w-full sm:w-64 px-3 py-2 text-sm border border-afj-cream-dark rounded-sm focus:outline-none focus:border-afj-gold"
            >
              {COLECOES_INDEXAVEIS.map((c) => (
                <option key={c.value} value={c.value}>{c.label}</option>
              ))}
            </select>
          </div>

          <div>
            <p className="text-xs text-afj-black/50 mb-1.5">Metadados (opcional):</p>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {CAMPOS_METADADO.map((campo) => (
                <input
                  key={campo.key}
                  value={metadata[campo.key] ?? ""}
                  onChange={(e) => setMetadata((prev) => ({ ...prev, [campo.key]: e.target.value }))}
                  placeholder={campo.label}
                  className="px-2.5 py-1.5 text-xs border border-afj-cream-dark rounded-sm focus:outline-none focus:border-afj-gold"
                />
              ))}
            </div>
          </div>

          <div className="flex justify-end">
            <button
              type="button"
              onClick={indexar}
              disabled={enviando || !content.trim()}
              className="btn-afj-primary rounded-sm flex items-center gap-2 disabled:opacity-40"
            >
              {enviando ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />}
              {enviando ? "Indexando..." : "Indexar"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

interface RelatorFavorabilidade {
  relator: string;
  total: number;
  favoraveis: number;
  taxa_favoravel: number;
}

interface AcordaoRelator {
  document_id: string;
  numero_processo?: string;
  data?: string;
  orgao_julgador?: string;
  area_direito?: string;
  favoravel?: boolean;
}

function PainelFavorabilidade() {
  const [aberto, setAberto] = useState(false);
  const [dados, setDados] = useState<RelatorFavorabilidade[] | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [relatorSelecionado, setRelatorSelecionado] = useState<string | null>(null);
  const [acordaos, setAcordaos] = useState<AcordaoRelator[] | null>(null);
  const [carregandoDetalhe, setCarregandoDetalhe] = useState(false);

  useEffect(() => {
    if (!aberto || dados) return;
    setCarregando(true);
    const token = localStorage.getItem("afj_access_token");
    fetch("/api/v1/rag/jurisprudencia/favorabilidade", { headers: { Authorization: `Bearer ${token}` } })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => setDados(data?.relatores ?? []))
      .catch(() => setDados([]))
      .finally(() => setCarregando(false));
  }, [aberto, dados]);

  function abrirPerfilRelator(relator: string) {
    setRelatorSelecionado(relator);
    setAcordaos(null);
    setCarregandoDetalhe(true);
    const token = localStorage.getItem("afj_access_token");
    fetch(`/api/v1/rag/jurisprudencia/favorabilidade/${encodeURIComponent(relator)}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => setAcordaos(data?.acordaos ?? []))
      .catch(() => setAcordaos([]))
      .finally(() => setCarregandoDetalhe(false));
  }

  return (
    <div className="afj-card p-0 overflow-hidden">
      <button
        type="button"
        onClick={() => setAberto((v) => !v)}
        className="w-full flex items-center justify-between px-5 py-3 text-left"
      >
        <span className="flex items-center gap-2 text-sm font-medium text-afj-black">
          <BarChart2 size={14} className="text-afj-gold" />
          Favorabilidade por relator (STJ)
        </span>
        {aberto ? <ChevronUp size={15} className="text-afj-black/40" /> : <ChevronDown size={15} className="text-afj-black/40" />}
      </button>

      {aberto && (
        <div className="px-5 pb-5 border-t border-afj-cream-dark pt-4">
          {carregando && <p className="text-xs text-afj-black/40">Carregando...</p>}
          {!carregando && dados && dados.length === 0 && (
            <p className="text-xs text-afj-black/40">
              Nenhum acórdão classificado ainda. A classificação passa a rodar automaticamente
              nos acórdãos ingeridos a partir de agora (não retroage aos já indexados).
            </p>
          )}
          {!carregando && dados && dados.length > 0 && (
            <div className="overflow-x-auto">
              <table className="afj-table w-full text-sm">
                <thead>
                  <tr>
                    <th className="text-left">Relator</th>
                    <th className="text-right">Acórdãos</th>
                    <th className="text-right">Favoráveis</th>
                    <th className="text-right">Taxa</th>
                  </tr>
                </thead>
                <tbody>
                  {dados.map((r) => (
                    <tr
                      key={r.relator}
                      onClick={() => abrirPerfilRelator(r.relator)}
                      className="cursor-pointer hover:bg-afj-cream/60"
                      title="Ver acórdãos deste relator"
                    >
                      <td className="text-afj-gold underline decoration-dotted">{r.relator}</td>
                      <td className="text-right">{r.total}</td>
                      <td className="text-right">{r.favoraveis}</td>
                      <td className="text-right">{(r.taxa_favoravel * 100).toFixed(0)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {relatorSelecionado && (
        <div
          className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
          onClick={() => setRelatorSelecionado(null)}
        >
          <div
            className="afj-card w-full max-w-2xl max-h-[80vh] overflow-y-auto p-6 space-y-3"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between gap-3">
              <h3 className="font-display text-base font-semibold text-afj-black">Perfil do relator: {relatorSelecionado}</h3>
              <button
                type="button"
                onClick={() => setRelatorSelecionado(null)}
                className="text-afj-black/40 hover:text-afj-black text-sm"
              >
                Fechar
              </button>
            </div>
            {carregandoDetalhe && <p className="text-xs text-afj-black/40">Carregando...</p>}
            {!carregandoDetalhe && acordaos && acordaos.length === 0 && (
              <p className="text-xs text-afj-black/40">Nenhum acórdão encontrado para este relator.</p>
            )}
            {!carregandoDetalhe && acordaos && acordaos.length > 0 && (
              <div className="overflow-x-auto">
                <table className="afj-table w-full text-sm">
                  <thead>
                    <tr>
                      <th className="text-left">Nº processo</th>
                      <th className="text-left">Data</th>
                      <th className="text-left">Órgão julgador</th>
                      <th className="text-left">Área</th>
                      <th className="text-right">Favorável</th>
                    </tr>
                  </thead>
                  <tbody>
                    {acordaos.map((a) => (
                      <tr key={a.document_id}>
                        <td>{a.numero_processo || "—"}</td>
                        <td>{a.data || "—"}</td>
                        <td>{a.orgao_julgador || "—"}</td>
                        <td>{a.area_direito || "—"}</td>
                        <td className="text-right">
                          {a.favoravel === true ? (
                            <span className="text-green-700">Sim</span>
                          ) : a.favoravel === false ? (
                            <span className="text-red-700">Não</span>
                          ) : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

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
  const user = useUserStore((s) => s.user);
  const [query, setQuery] = useState("");
  const [selectedCols, setSelectedCols] = useState<string[]>(["jurisprudencia", "legislacao"]);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<RagResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [needsEmbeddingProvider, setNeedsEmbeddingProvider] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const [coverage, setCoverage] = useState<Record<string, number>>({});

  useEffect(() => {
    const token = localStorage.getItem("afj_access_token");
    fetch("/api/v1/rag/coverage", { headers: { Authorization: `Bearer ${token}` } })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!data?.colecoes) return;
        const mapa: Record<string, number> = {};
        for (const c of data.colecoes) {
          if (typeof c.pontos === "number") mapa[c.collection] = c.pontos;
        }
        setCoverage(mapa);
      })
      .catch(() => {});
  }, []);

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
    setNeedsEmbeddingProvider(false);
    setResults(null);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
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
        signal: controller.signal,
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        const detail = data.detail;
        // Fase pós-260 — `detail` pode vir estruturado (503 de embeddings
        // indisponível: {message, needs_embedding_provider}) ou como string
        // simples (demais erros) — nunca mais sniffing de texto por "openai".
        if (detail && typeof detail === "object") {
          setError(detail.message || "Erro ao buscar. Verifique se a base vetorial está disponível.");
          setNeedsEmbeddingProvider(Boolean(detail.needs_embedding_provider));
        } else {
          setError(detail || "Erro ao buscar. Verifique se a base vetorial está disponível.");
        }
        return;
      }
      const data = await res.json();
      setResults(Array.isArray(data) ? data : (data.results ?? []));
    } catch (err: any) {
      if (err?.name === "AbortError") {
        setError("Busca excedeu o tempo limite (15s). Tente novamente ou refine a consulta.");
      } else {
        setError("Erro de conexão com a base vetorial.");
      }
    } finally {
      clearTimeout(timeout);
      setLoading(false);
    }
  }

  async function copiar(id: string, text: string) {
    await navigator.clipboard.writeText(text);
    setCopied(id);
    setTimeout(() => setCopied(null), 1500);
  }

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Pesquisa Jurídica" }]} />

      <div className="afj-page-header">
        <div>
          <h1 className="font-display text-2xl font-semibold text-afj-black">Pesquisa Jurídica</h1>
          <p className="text-afj-black/50 text-sm mt-0.5">
            Busca semântica em jurisprudência, legislação, doutrina e memórias do escritório
          </p>
        </div>
      </div>

      {user?.role === "ADMIN" && <PainelIndexacao />}
      <PainelFavorabilidade />

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
                {coverage[col.value] !== undefined && (
                  <span className="opacity-60"> · {coverage[col.value]}</span>
                )}
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
          <div>
            <p className="text-sm text-red-700">{error}</p>
            {needsEmbeddingProvider && (
              <Link href="/minha-ia" className="text-sm text-red-800 underline font-medium mt-1 inline-block">
                Ir para Minha IA →
              </Link>
            )}
          </div>
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
                <div key={r.id} className="afj-card p-4 hover:border-afj-gold/20 transition-colors animate-fade-in">
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
