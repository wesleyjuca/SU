"use client";
import { useState } from "react";
import { GitBranch, Loader2, Download, RefreshCw } from "lucide-react";
import dynamic from "next/dynamic";
import { parseMermaidToNodes } from "@/components/visual-law/VisualLawCanvas";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import type { VisualLawNode, VisualLawEdge } from "@/components/visual-law/VisualLawCanvas";
const VisualLawCanvas = dynamic(
  () => import("@/components/visual-law/VisualLawCanvas").then((m) => ({ default: m.VisualLawCanvas })),
  { ssr: false, loading: () => <div className="h-96 afj-card flex items-center justify-center text-afj-black/40 animate-pulse">Carregando canvas...</div> }
);

const TIPOS_VISUALIZACAO = [
  { value: "fluxograma", label: "Fluxograma Processual", desc: "Etapas e decisões do processo" },
  { value: "timeline", label: "Timeline de Movimentações", desc: "Linha do tempo cronológica" },
  { value: "quadro_comparativo", label: "Quadro Comparativo", desc: "Comparação de estratégias" },
];

export default function VisualLawPage() {
  const [tipo, setTipo] = useState("fluxograma");
  const [contexto, setContexto] = useState("");
  const [loading, setLoading] = useState(false);
  const [resultado, setResultado] = useState<{ tipo: string; conteudo: string; mermaid?: string } | null>(null);
  const [flowData, setFlowData] = useState<{ nodes: VisualLawNode[]; edges: VisualLawEdge[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function gerar() {
    if (!contexto.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/agents/trigger", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          task_type: "visual_law",
          task_input: { tipo_visualizacao: tipo, contexto },
        }),
      });
      if (!res.ok) {
        setError("Erro ao iniciar agente Visual Law");
        return;
      }
      const data = await res.json();
      const runId = data.run_id;

      // Poll for result
      for (let i = 0; i < 30; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const runRes = await fetch(`/api/v1/agents/runs/${runId}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (runRes.ok) {
          const run = await runRes.json();
          if (run.status === "SUCCESS" && run.output_data?.output) {
            const out = run.output_data.output;
            setResultado(out);
            if (out.nodes && out.edges) {
              setFlowData({ nodes: out.nodes, edges: out.edges });
            } else if (out.mermaid) {
              setFlowData(parseMermaidToNodes(out.mermaid));
            }
            break;
          } else if (run.status === "FAILED") {
            setError("O agente falhou ao gerar a visualização.");
            break;
          }
        }
      }
    } catch {
      setError("Erro de conexão");
    } finally {
      setLoading(false);
    }
  }

  function copiarMermaid() {
    if (resultado?.mermaid) {
      navigator.clipboard.writeText(resultado.mermaid);
    }
  }

  function limpar() {
    setResultado(null);
    setFlowData(null);
  }

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Visual Law" }]} />
      <div>
        <h1 className="font-display text-2xl font-semibold text-afj-black">Visual Law</h1>
        <p className="text-afj-black/50 text-sm">Visualizações jurídicas geradas por IA — fluxogramas, timelines, comparativos</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Painel de controle */}
        <div className="afj-card p-5 space-y-4">
          <h2 className="font-semibold text-afj-black">Configurar Visualização</h2>

          <div>
            <label className="text-xs text-afj-black/60 block mb-2">Tipo de Visualização</label>
            <div className="space-y-2">
              {TIPOS_VISUALIZACAO.map((t) => (
                <button
                  key={t.value}
                  onClick={() => setTipo(t.value)}
                  className={`w-full text-left p-3 rounded-md border text-sm transition-colors ${
                    tipo === t.value
                      ? "border-afj-gold bg-afj-gold/5 text-afj-gold"
                      : "border-afj-cream-dark hover:border-afj-gold/50 text-afj-black"
                  }`}
                >
                  <p className="font-medium">{t.label}</p>
                  <p className="text-xs opacity-60 mt-0.5">{t.desc}</p>
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-xs text-afj-black/60 block mb-1">Contexto / Descrição</label>
            <textarea
              value={contexto}
              onChange={(e) => setContexto(e.target.value)}
              rows={6}
              placeholder="Descreva o processo, as partes, fases, movimentações ou o que deseja visualizar..."
              className="w-full border border-afj-cream-dark rounded-md px-3 py-2 text-sm focus:outline-none focus:border-afj-gold resize-none"
            />
          </div>

          {error && (
            <div className="bg-red-50 border border-red-200 rounded-md p-3 text-sm text-red-700">
              {error}
            </div>
          )}

          <button
            onClick={gerar}
            disabled={loading || !contexto.trim()}
            className="w-full btn-afj-primary rounded-md flex items-center justify-center gap-2 disabled:opacity-40"
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : <GitBranch size={14} />}
            {loading ? "Gerando..." : "Gerar Visualização"}
          </button>
        </div>

        {/* Resultado */}
        <div className="lg:col-span-2">
          {loading && (
            <div className="afj-card p-12 text-center">
              <Loader2 className="mx-auto animate-spin text-afj-gold mb-3" size={32} />
              <p className="text-afj-black/60">Agente Visual Law processando...</p>
              <p className="text-xs text-afj-black/40 mt-1">Isso pode levar alguns segundos</p>
            </div>
          )}

          {!loading && !resultado && (
            <div className="afj-card p-12 text-center">
              <GitBranch className="mx-auto text-afj-black/20 mb-3" size={40} />
              <p className="font-semibold text-afj-black">Nenhuma visualização gerada</p>
              <p className="text-afj-black/40 text-sm mt-1">Configure e gere uma visualização usando o painel ao lado</p>
            </div>
          )}

          {resultado && (
            <div className="afj-card overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 border-b border-afj-cream-dark bg-afj-cream/50">
                <h3 className="font-semibold text-afj-black text-sm">
                  {TIPOS_VISUALIZACAO.find((t) => t.value === resultado.tipo)?.label || resultado.tipo}
                </h3>
                <div className="flex gap-2">
                  {resultado.mermaid && (
                    <button
                      onClick={copiarMermaid}
                      className="text-xs text-afj-black/50 hover:text-afj-gold flex items-center gap-1"
                    >
                      <Download size={12} />
                      Copiar Mermaid
                    </button>
                  )}
                  <button
                    onClick={limpar}
                    className="text-xs text-afj-black/50 hover:text-afj-gold flex items-center gap-1"
                  >
                    <RefreshCw size={12} />
                    Limpar
                  </button>
                </div>
              </div>
              <div className="p-0">
                {flowData && (flowData.nodes.length > 0) ? (
                  <VisualLawCanvas nodes={flowData.nodes} edges={flowData.edges} />
                ) : resultado.mermaid ? (
                  <div className="p-5 space-y-4">
                    <div className="bg-afj-cream rounded-md p-4">
                      <p className="text-xs font-mono text-afj-black/50 mb-2">Código Mermaid (cole em mermaid.live):</p>
                      <pre className="text-xs font-mono text-afj-black whitespace-pre-wrap overflow-auto max-h-64">
                        {resultado.mermaid}
                      </pre>
                    </div>
                    {resultado.conteudo && (
                      <p className="text-sm text-afj-black/80">{resultado.conteudo}</p>
                    )}
                  </div>
                ) : (
                  <div
                    className="p-5 prose prose-sm max-w-none text-afj-black/80"
                    dangerouslySetInnerHTML={{ __html: resultado.conteudo?.replace(/\n/g, "<br/>") || "" }}
                  />
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
