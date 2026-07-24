"use client";
import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import ReactFlow, {
  Node, Edge, NodeProps, Handle, Position, Controls, MiniMap, Background, BackgroundVariant,
  MarkerType, ReactFlowInstance, useNodesState, useEdgesState,
} from "reactflow";
import "reactflow/dist/style.css";
import { Activity, X, Search, Maximize2, Minimize2 } from "lucide-react";
import { fetchBrain, type Mapa, type MapaNo, type Infra, type Camada } from "./types";

// ─── Camadas concêntricas (núcleo → inteligência → memória → execução → integrações) ─
const ORDEM_CAMADAS: Camada[] = ["inteligencia", "memoria", "execucao", "integracoes"];
const CAMADA_COR: Record<Camada, string> = {
  nucleo: "#B8954A", inteligencia: "#7C3AED", memoria: "#0EA5E9",
  execucao: "#059669", integracoes: "#6B7280",
};
const CAMADA_LABEL: Record<Camada, string> = {
  nucleo: "Núcleo", inteligencia: "Inteligência", memoria: "Memória",
  execucao: "Execução", integracoes: "Integrações",
};
const RAIO_INICIAL = 170;
const RAIO_PASSO = 150;

interface Pos { x: number; y: number }

/** Layout radial determinístico — recalculado a cada render a partir do dado
 * (nenhuma posição fixa): núcleo no centro, cada camada num anel de raio
 * crescente, nós distribuídos por ângulo uniforme. Camadas ocultas/colapsadas
 * não consomem raio — o grafo se reorganiza sozinho conforme o sistema cresce. */
function useLayout(nos: MapaNo[], visiveis: Set<Camada>, colapsadas: Set<Camada>) {
  return useMemo(() => {
    const porCamada = new Map<Camada, MapaNo[]>();
    for (const n of nos) {
      if (!visiveis.has(n.camada)) continue;
      const lista = porCamada.get(n.camada) ?? [];
      lista.push(n);
      porCamada.set(n.camada, lista);
    }
    const pos: Record<string, Pos> = {};
    const grupos: { id: string; camada: Camada; contagem: number; pos: Pos }[] = [];

    const nucleo = porCamada.get("nucleo")?.[0];
    if (nucleo) pos[nucleo.id] = { x: 0, y: 0 };

    let raio = RAIO_INICIAL;
    for (const camada of ORDEM_CAMADAS) {
      const lista = porCamada.get(camada) ?? [];
      if (!lista.length) continue;
      const raioCamada = raio + Math.max(0, lista.length - 6) * 14;
      if (colapsadas.has(camada)) {
        grupos.push({ id: `grupo_${camada}`, camada, contagem: lista.length, pos: { x: raioCamada, y: 0 } });
      } else {
        lista.forEach((n, i) => {
          const ang = (i / lista.length) * Math.PI * 2 - Math.PI / 2;
          pos[n.id] = { x: raioCamada * Math.cos(ang), y: raioCamada * Math.sin(ang) };
        });
      }
      raio = raioCamada + RAIO_PASSO;
    }
    return { pos, grupos };
  }, [nos, visiveis, colapsadas]);
}

// ─── Nós customizados ──────────────────────────────────────────────────────────
interface NoData {
  label: string; cor: string; peso: number; saude: "ok" | "erro" | "neutro";
  destacado: boolean; esmaecido: boolean;
}
interface GrupoData { camada: Camada; contagem: number; cor: string; esmaecido: boolean }

const HANDLE_STYLE = { opacity: 0, width: 1, height: 1 };

function NucleoNode({ data }: NodeProps<NoData>) {
  return (
    <div
      className={`brain-nucleo ${data.esmaecido ? "brain-esmaecido" : ""}`}
      style={{ background: data.cor, color: data.cor }}
    >
      <Handle type="target" position={Position.Top} id="t" style={HANDLE_STYLE} />
      <span className="brain-nucleo-label">{data.label}</span>
      <Handle type="source" position={Position.Bottom} id="s" style={HANDLE_STYLE} />
    </div>
  );
}

function BrainNode({ data }: NodeProps<NoData>) {
  const largura = 66 + data.peso * 16;
  const anelCor = data.saude === "ok" ? "#16a34a" : data.saude === "erro" ? "#dc2626" : "transparent";
  return (
    <div
      className={`brain-node ${data.destacado ? "brain-destacado" : ""} ${data.esmaecido ? "brain-esmaecido" : ""}`}
      style={{
        background: data.cor, width: largura, minHeight: 38,
        border: `2.5px solid ${anelCor}`,
        boxShadow: data.saude === "erro" ? "0 0 0 3px rgba(220,38,38,0.22)" : undefined,
      }}
    >
      <Handle type="target" position={Position.Top} id="t" style={HANDLE_STYLE} />
      <span className="brain-node-label">{data.label}</span>
      <Handle type="source" position={Position.Bottom} id="s" style={HANDLE_STYLE} />
    </div>
  );
}

function GrupoNode({ data }: NodeProps<GrupoData>) {
  return (
    <div
      className={`brain-grupo ${data.esmaecido ? "brain-esmaecido" : ""}`}
      style={{ borderColor: data.cor, color: data.cor }}
    >
      <Handle type="target" position={Position.Top} id="t" style={HANDLE_STYLE} />
      <Maximize2 size={12} />
      <span>{CAMADA_LABEL[data.camada]} ({data.contagem})</span>
      <Handle type="source" position={Position.Bottom} id="s" style={HANDLE_STYLE} />
    </div>
  );
}

const NODE_TYPES = { nucleo: NucleoNode, brain: BrainNode, grupo: GrupoNode };

export function BrainMap() {
  const [mapa, setMapa] = useState<Mapa | null>(null);
  const [infra, setInfra] = useState<Infra | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [selecionado, setSelecionado] = useState<MapaNo | null>(null);
  const [hoverId, setHoverId] = useState<string | null>(null);
  const [busca, setBusca] = useState("");
  const [visiveis, setVisiveis] = useState<Set<Camada>>(new Set(["nucleo", ...ORDEM_CAMADAS]));
  const [colapsadas, setColapsadas] = useState<Set<Camada>>(new Set());
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const rfInstance = useRef<ReactFlowInstance | null>(null);

  const carregar = useCallback(async () => {
    const [m, inf] = await Promise.all([fetchBrain<Mapa>("map"), fetchBrain<Infra>("infra")]);
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

  const { pos, grupos } = useLayout(mapa?.nos ?? [], visiveis, colapsadas);
  const focoId = selecionado?.id ?? hoverId;

  // Conjunto de nós conectados ao nó em foco (para destacar/esmaecer).
  const conectados = useMemo(() => {
    if (!focoId || !mapa) return null;
    const set = new Set<string>();
    for (const a of mapa.arestas) {
      if (a.de === focoId) set.add(a.para);
      if (a.para === focoId) set.add(a.de);
    }
    return set;
  }, [focoId, mapa]);

  // Resolve um id de nó para o grupo colapsado, se a camada dele estiver oculta.
  const resolverEndpoint = useCallback((id: string): string | null => {
    const no = mapa?.nos.find((n) => n.id === id);
    if (!no) return null;
    if (!visiveis.has(no.camada)) return null;
    if (colapsadas.has(no.camada)) return `grupo_${no.camada}`;
    return id;
  }, [mapa, visiveis, colapsadas]);

  useEffect(() => {
    if (!mapa) return;

    const rfNodes: Node[] = [];
    for (const n of mapa.nos) {
      const p = pos[n.id];
      if (!p) continue;
      const destacado = focoId === n.id;
      const esmaecido = !!focoId && focoId !== n.id && !conectados?.has(n.id);
      const data: NoData = {
        label: n.label, cor: CAMADA_COR[n.camada], peso: n.peso,
        saude: saudeDoNo(n), destacado, esmaecido,
      };
      rfNodes.push({
        id: n.id, type: n.camada === "nucleo" ? "nucleo" : "brain",
        position: p, data, draggable: false,
      });
    }
    for (const g of grupos) {
      const esmaecido = !!focoId && focoId !== g.id;
      const data: GrupoData = { camada: g.camada, contagem: g.contagem, cor: CAMADA_COR[g.camada], esmaecido };
      rfNodes.push({ id: g.id, type: "grupo", position: g.pos, data, draggable: false });
    }

    // Deduplica arestas cujos extremos colapsaram no mesmo grupo.
    const porChave = new Map<string, { de: string; para: string; peso: number; ativa: boolean }>();
    for (const a of mapa.arestas) {
      const de = resolverEndpoint(a.de);
      const para = resolverEndpoint(a.para);
      if (!de || !para || de === para) continue;
      const chave = `${de}->${para}`;
      const ativa = !!focoId && (a.de === focoId || a.para === focoId || de === focoId || para === focoId);
      const atual = porChave.get(chave);
      if (!atual || a.peso > atual.peso || ativa) {
        porChave.set(chave, { de, para, peso: Math.max(a.peso, atual?.peso ?? 0), ativa: ativa || !!atual?.ativa });
      }
    }
    const rfEdges: Edge[] = Array.from(porChave.entries()).map(([chave, a]) => {
      const secundaria = a.peso < 3;
      // Conexões secundárias (folha) ficam quase invisíveis até hover/clique;
      // as estruturais formam o "fluxo" sempre visível do cérebro.
      const opacidade = focoId ? (a.ativa ? 0.95 : 0.05) : (secundaria ? 0.05 : 0.5);
      return {
        id: chave, source: a.de, target: a.para,
        animated: a.ativa || (!focoId && !secundaria),
        style: { stroke: CAMADA_COR.nucleo, strokeWidth: Math.max(1, a.peso) * (a.ativa ? 1.7 : 1), opacity: opacidade },
        markerEnd: { type: MarkerType.ArrowClosed, color: CAMADA_COR.nucleo },
      };
    });

    setNodes(rfNodes);
    setEdges(rfEdges);
  }, [mapa, pos, grupos, focoId, conectados, resolverEndpoint, saudeDoNo, setNodes, setEdges]);

  const onNodeClick = useCallback((_: unknown, node: Node) => {
    if (node.type === "grupo") {
      const camada = (node.data as GrupoData).camada;
      setColapsadas((prev) => { const n = new Set(prev); n.delete(camada); return n; });
      return;
    }
    const no = mapa?.nos.find((n) => n.id === node.id) ?? null;
    setSelecionado((atual) => (atual?.id === node.id ? null : no));
  }, [mapa]);

  const toggleVisivel = useCallback((camada: Camada) => {
    setVisiveis((prev) => {
      const n = new Set(prev);
      if (n.has(camada)) n.delete(camada); else n.add(camada);
      return n;
    });
  }, []);
  const toggleColapso = useCallback((camada: Camada, e: React.MouseEvent) => {
    e.stopPropagation();
    setColapsadas((prev) => {
      const n = new Set(prev);
      if (n.has(camada)) n.delete(camada); else n.add(camada);
      return n;
    });
  }, []);

  const buscar = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    if (!mapa || !busca.trim()) return;
    const alvo = mapa.nos.find((n) => n.label.toLowerCase().includes(busca.trim().toLowerCase()));
    if (!alvo) return;
    setVisiveis((prev) => new Set(prev).add(alvo.camada));
    setColapsadas((prev) => { const n = new Set(prev); n.delete(alvo.camada); return n; });
    setSelecionado(alvo);
  }, [mapa, busca]);

  // Centraliza a viewport no nó selecionado assim que sua posição existir.
  useEffect(() => {
    if (!selecionado || !rfInstance.current) return;
    const p = pos[selecionado.id];
    if (p) rfInstance.current.setCenter(p.x, p.y, { zoom: 1.05, duration: 500 });
  }, [selecionado, pos]);

  if (erro) return <div className="afj-card p-6 text-center text-sm text-red-600">{erro}</div>;

  const resumo = mapa?.resumo;
  const camadasComNo = new Set((mapa?.nos ?? []).map((n) => n.camada));

  return (
    <div className="space-y-3">
      <style>{`
        .brain-nucleo { width: 130px; height: 62px; border-radius: 9999px; display: flex; align-items: center; justify-content: center; position: relative; cursor: pointer; transition: opacity .25s ease, transform .2s ease; }
        .brain-nucleo::before { content: ''; position: absolute; inset: -10px; border-radius: 9999px; border: 2px solid currentColor; opacity: .45; animation: brain-pulse 2.4s ease-in-out infinite; }
        .brain-nucleo-label { color: #F4F0EA; font-size: 12px; font-weight: 700; z-index: 1; }
        @keyframes brain-pulse { 0% { transform: scale(.85); opacity: .55; } 70% { transform: scale(1.4); opacity: 0; } 100% { opacity: 0; } }
        .brain-node { border-radius: 12px; display: flex; align-items: center; justify-content: center; text-align: center; padding: 5px 9px; cursor: pointer; transition: opacity .25s ease, transform .2s ease, box-shadow .25s ease; }
        .brain-node-label { color: #F4F0EA; font-size: 10.5px; font-weight: 600; line-height: 1.15; }
        .brain-node.brain-destacado { transform: scale(1.12); box-shadow: 0 0 0 3px rgba(184,149,74,.4), 0 4px 16px rgba(0,0,0,.28); }
        .brain-grupo { width: 118px; height: 46px; border-radius: 10px; border: 1.5px dashed; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px; font-size: 9.5px; font-weight: 600; cursor: pointer; background: rgba(255,255,255,.75); }
        .brain-esmaecido { opacity: .15 !important; }
      `}</style>

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

      {/* Busca + filtro/colapso por camada */}
      <div className="flex flex-wrap items-center gap-2">
        <form onSubmit={buscar} className="relative">
          <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-afj-black/30" />
          <input
            value={busca} onChange={(e) => setBusca(e.target.value)}
            placeholder="Buscar módulo..."
            className="pl-7 pr-2 py-1.5 text-xs border border-afj-cream-dark rounded-sm focus:outline-none focus:border-afj-gold bg-white w-44"
          />
        </form>
        {(["nucleo", ...ORDEM_CAMADAS] as Camada[]).filter((c) => camadasComNo.has(c)).map((c) => {
          const ativo = visiveis.has(c);
          const contagem = (mapa?.nos ?? []).filter((n) => n.camada === c).length;
          return (
            <div key={c} className="flex items-center rounded-sm border border-afj-cream-dark overflow-hidden">
              <button
                onClick={() => toggleVisivel(c)}
                className="flex items-center gap-1.5 px-2 py-1 text-[11px] font-medium"
                style={{ color: ativo ? CAMADA_COR[c] : "#9CA3AF", opacity: ativo ? 1 : 0.55 }}
                title="Mostrar/ocultar camada"
              >
                <span className="w-2 h-2 rounded-full" style={{ background: CAMADA_COR[c] }} />
                {CAMADA_LABEL[c]} ({contagem})
              </button>
              {c !== "nucleo" && ativo && (
                <button onClick={(e) => toggleColapso(c, e)} className="px-1.5 py-1 text-afj-black/35 hover:text-afj-black border-l border-afj-cream-dark"
                  title={colapsadas.has(c) ? "Expandir camada" : "Recolher camada"}>
                  {colapsadas.has(c) ? <Maximize2 size={11} /> : <Minimize2 size={11} />}
                </button>
              )}
            </div>
          );
        })}
      </div>

      <div className="relative afj-card p-0 overflow-hidden" style={{ height: 580 }}>
        <ReactFlow
          nodes={nodes} edges={edges} nodeTypes={NODE_TYPES}
          onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          onNodeMouseEnter={(_, n) => setHoverId(n.id)}
          onNodeMouseLeave={() => setHoverId(null)}
          onInit={(instance) => { rfInstance.current = instance; }}
          onPaneClick={() => setSelecionado(null)}
          fitView minZoom={0.25} maxZoom={1.8}
          proOptions={{ hideAttribution: true }}
          nodesDraggable={false} nodesConnectable={false} elementsSelectable
        >
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#e5e0d8" />
          <Controls showInteractive={false} />
          <MiniMap
            pannable zoomable
            nodeColor={(n) => (n.data as { cor?: string })?.cor || "#9CA3AF"}
            maskColor="rgba(244,240,234,0.7)"
            style={{ background: "#fff" }}
          />
        </ReactFlow>

        {/* Painel de drill-down do nó selecionado */}
        {selecionado && (
          <div className="absolute top-3 right-3 w-64 max-h-[92%] overflow-y-auto bg-white/95 backdrop-blur border border-afj-cream-dark rounded-sm shadow-lg p-3">
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="text-[10px] uppercase tracking-wider" style={{ color: CAMADA_COR[selecionado.camada] }}>
                  {CAMADA_LABEL[selecionado.camada]}
                </p>
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
            {conectados && conectados.size > 0 && (
              <div className="mt-3 pt-2 border-t border-afj-cream-dark">
                <p className="text-[10px] uppercase tracking-wider text-afj-black/40 mb-1">Conexões ({conectados.size})</p>
                <div className="flex flex-wrap gap-1">
                  {Array.from(conectados).slice(0, 12).map((id) => {
                    const n = mapa?.nos.find((x) => x.id === id);
                    return n ? (
                      <span key={id} className="text-[10px] px-1.5 py-0.5 rounded-full"
                        style={{ background: `${CAMADA_COR[n.camada]}1a`, color: CAMADA_COR[n.camada] }}>
                        {n.label}
                      </span>
                    ) : null;
                  })}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <p className="text-[11px] text-afj-black/35 text-center flex items-center justify-center gap-1.5">
        <Activity size={11} /> Clique num nó para destacar suas conexões · anel verde = saudável · vermelho = indisponível
        {lastRefresh && ` · atualizado ${lastRefresh.toLocaleTimeString("pt-BR")}`}
      </p>
    </div>
  );
}
