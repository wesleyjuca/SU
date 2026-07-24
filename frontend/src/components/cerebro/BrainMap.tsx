"use client";
import { useState, useEffect, useCallback } from "react";
import ReactFlow, {
  Node, Edge, Controls, Background, BackgroundVariant, MarkerType,
  useNodesState, useEdgesState,
} from "reactflow";
import "reactflow/dist/style.css";
import { Activity, X } from "lucide-react";
import { fetchBrain, type Mapa, type MapaNo, type Infra } from "./types";

const GRUPO_COR: Record<string, string> = {
  api: "#1E2229", agentes: "#B8954A", infra: "#3D4557", integracoes: "#6B7280", dados: "#3D4557",
};
const GRUPO_LABEL: Record<string, string> = {
  api: "Núcleo/API", agentes: "IA/Agentes", infra: "Infraestrutura", integracoes: "Integrações/Fontes", dados: "Dados",
};

// Layout radial simples inspirado num cérebro/rede.
function posicao(grupo: string, i: number, total: number): { x: number; y: number } {
  const raios: Record<string, number> = { api: 0, agentes: 300, infra: 300, integracoes: 300, dados: 300 };
  const centros: Record<string, number> = { agentes: -90, infra: 90, integracoes: 200, api: 0 };
  const r = raios[grupo] ?? 320;
  const base = (centros[grupo] ?? 0) * (Math.PI / 180);
  const ang = base + (i / Math.max(1, total)) * 1.4 - 0.7;
  return { x: 500 + r * Math.cos(ang), y: 320 + r * Math.sin(ang) };
}

export function BrainMap() {
  const [mapa, setMapa] = useState<Mapa | null>(null);
  const [infra, setInfra] = useState<Infra | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [selecionado, setSelecionado] = useState<MapaNo | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  const carregar = useCallback(async () => {
    const [m, inf] = await Promise.all([
      fetchBrain<Mapa>("map"),
      fetchBrain<Infra>("infra"),
    ]);
    if (!m) { setErro("Acesso negado ou servidor indisponível."); return; }
    setMapa(m); setInfra(inf); setErro(null); setLastRefresh(new Date());
  }, []);

  useEffect(() => { carregar(); }, [carregar]);
  useEffect(() => { const i = setInterval(carregar, 15000); return () => clearInterval(i); }, [carregar]);

  const saudeDoNo = useCallback((no: MapaNo): "ok" | "erro" | "neutro" => {
    if (!no.saude_key || !infra) return "neutro";
    const s = (infra as unknown as Record<string, { ok?: boolean; configured?: boolean }>)[no.saude_key];
    if (!s || s.configured === false) return "neutro";
    return s.ok ? "ok" : "erro";
  }, [infra]);

  useEffect(() => {
    if (!mapa) return;
    const porGrupo: Record<string, MapaNo[]> = {};
    mapa.nos.forEach((n) => { (porGrupo[n.grupo] ??= []).push(n); });

    const rfNodes: Node[] = mapa.nos.map((n) => {
      const grupoLista = porGrupo[n.grupo];
      const idx = grupoLista.indexOf(n);
      const p = n.id === "api" ? { x: 470, y: 300 } : posicao(n.grupo, idx, grupoLista.length);
      const saude = saudeDoNo(n);
      const cor = GRUPO_COR[n.grupo] ?? "#3D4557";
      const ring = saude === "ok" ? "#16a34a" : saude === "erro" ? "#dc2626" : "transparent";
      return {
        id: n.id, position: p, data: { label: n.label },
        style: {
          background: cor, color: "#F4F0EA", border: `3px solid ${ring}`,
          borderRadius: 12, fontSize: 11, fontWeight: 600, padding: "6px 10px",
          width: n.id === "api" ? 130 : 108, textAlign: "center" as const, cursor: "pointer",
          boxShadow: saude === "erro" ? "0 0 0 3px rgba(220,38,38,0.25)" : undefined,
        },
      };
    });
    const rfEdges: Edge[] = mapa.arestas.map((a, i) => ({
      id: `e${i}`, source: a.de, target: a.para, label: a.tipo, animated: true,
      style: { stroke: "#B8954A", strokeWidth: 1.2, opacity: 0.55 },
      labelStyle: { fontSize: 9, fill: "#6B7280" },
      markerEnd: { type: MarkerType.ArrowClosed, color: "#B8954A" },
    }));
    setNodes(rfNodes); setEdges(rfEdges);
  }, [mapa, saudeDoNo, setNodes, setEdges]);

  const onNodeClick = useCallback((_: unknown, node: Node) => {
    setSelecionado(mapa?.nos.find((n) => n.id === node.id) ?? null);
  }, [mapa]);

  if (erro) return <div className="afj-card p-6 text-center text-sm text-red-600">{erro}</div>;

  const resumo = mapa?.resumo;

  return (
    <div className="space-y-3">
      {/* Resumo compacto */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-5 gap-3">
        {[
          { k: "agentes", label: "Agentes IA" },
          { k: "providers", label: "Integrações" },
          { k: "fontes", label: "Fontes captura" },
          { k: "tribunais", label: "Tribunais" },
          { k: "routers", label: "Rotas API" },
        ].map(({ k, label }) => (
          <div key={k} className="afj-stat-card">
            <p className="text-2xl font-bold text-afj-black">{resumo?.[k] ?? "—"}</p>
            <p className="text-xs text-afj-black/50 mt-0.5">{label}</p>
          </div>
        ))}
      </div>

      <div className="relative afj-card p-0 overflow-hidden" style={{ height: 560 }}>
        <ReactFlow
          nodes={nodes} edges={edges}
          onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          fitView minZoom={0.3} maxZoom={1.6}
          proOptions={{ hideAttribution: true }}
          nodesDraggable nodesConnectable={false} elementsSelectable
        >
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#e5e0d8" />
          <Controls showInteractive={false} />
        </ReactFlow>

        {/* Painel de drill-down do nó selecionado */}
        {selecionado && (
          <div className="absolute top-3 right-3 w-64 max-h-[92%] overflow-y-auto bg-white/95 backdrop-blur border border-afj-cream-dark rounded-sm shadow-lg p-3">
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="text-[10px] uppercase tracking-wider text-afj-gold">{GRUPO_LABEL[selecionado.grupo] ?? selecionado.grupo}</p>
                <h3 className="font-semibold text-afj-black text-sm">{selecionado.label}</h3>
              </div>
              <button onClick={() => setSelecionado(null)} className="text-afj-black/40 hover:text-afj-black" aria-label="Fechar">
                <X size={14} />
              </button>
            </div>
            {selecionado.meta && Object.keys(selecionado.meta).length > 0 ? (
              <dl className="mt-2 space-y-1.5 text-xs">
                {Object.entries(selecionado.meta).map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-2">
                    <dt className="text-afj-black/45 capitalize flex-shrink-0">{k}</dt>
                    <dd className="text-afj-black text-right break-words">
                      {Array.isArray(v) ? (v.length ? v.join(", ") : "—") : String(v)}
                    </dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="mt-2 text-xs text-afj-black/40">Sem detalhes adicionais para este nó.</p>
            )}
          </div>
        )}
      </div>

      <p className="text-[11px] text-afj-black/35 text-center flex items-center justify-center gap-1.5">
        <Activity size={11} /> Clique num nó para detalhes · anel verde = saudável · vermelho = indisponível
        {lastRefresh && ` · atualizado ${lastRefresh.toLocaleTimeString("pt-BR")}`}
      </p>
    </div>
  );
}
