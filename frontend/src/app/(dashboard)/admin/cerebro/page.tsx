"use client";
import { useState, useEffect, useCallback, useMemo } from "react";
import { useRouter } from "next/navigation";
import ReactFlow, {
  Node, Edge, Controls, Background, BackgroundVariant, MarkerType,
  useNodesState, useEdgesState,
} from "reactflow";
import "reactflow/dist/style.css";
import { Brain, RefreshCw, Cpu, Activity } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { BrainAssistant } from "@/components/cerebro/BrainAssistant";
import { useUserStore } from "@/store";

// ─── Tipos dos endpoints /system/brain/* (F1) ────────────────────────────────
interface MapaNo { id: string; label: string; grupo: string; saude_key?: string; meta?: Record<string, unknown> }
interface MapaAresta { de: string; para: string; tipo: string }
interface Mapa { nos: MapaNo[]; arestas: MapaAresta[]; resumo: { agentes: number; providers: number; routers: number } }
interface Infra {
  celery: { ok: boolean; workers: number };
  redis: { ok: boolean };
  qdrant: { ok: boolean; configured?: boolean };
  postgres_pool: { ok: boolean };
}

const GRUPO_COR: Record<string, string> = {
  api: "#1E2229", agentes: "#B8954A", infra: "#3D4557", integracoes: "#6B7280", dados: "#3D4557",
};

// Posições por grupo (layout radial simples inspirado num cérebro/rede).
function posicao(grupo: string, i: number, total: number): { x: number; y: number } {
  const raios: Record<string, number> = { api: 0, agentes: 300, infra: 300, integracoes: 300, dados: 300 };
  const centros: Record<string, number> = { agentes: -90, infra: 90, integracoes: 200, api: 0 };
  const r = raios[grupo] ?? 320;
  const base = (centros[grupo] ?? 0) * (Math.PI / 180);
  const ang = base + (i / Math.max(1, total)) * 1.4 - 0.7;
  return { x: 500 + r * Math.cos(ang), y: 320 + r * Math.sin(ang) };
}

export default function CerebroPage() {
  const router = useRouter();
  const user = useUserStore((s) => s.user);
  const [mapa, setMapa] = useState<Mapa | null>(null);
  const [infra, setInfra] = useState<Infra | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  // Cérebro é EXCLUSIVO do SUPERADMIN (o admin/layout já barra não-admin; aqui
  // barramos ADMIN também — só SUPERADMIN entra).
  useEffect(() => {
    if (user && user.role !== "SUPERADMIN") router.replace("/dashboard");
  }, [user, router]);

  const carregar = useCallback(async () => {
    try {
      const token = localStorage.getItem("afj_access_token");
      const h = { Authorization: `Bearer ${token}` };
      const [rMap, rInfra] = await Promise.all([
        fetch("/api/v1/system/brain/map", { headers: h }),
        fetch("/api/v1/system/brain/infra", { headers: h }),
      ]);
      if (!rMap.ok) { setErro(`Acesso negado (HTTP ${rMap.status}).`); return; }
      setMapa(await rMap.json());
      setInfra(rInfra.ok ? await rInfra.json() : null);
      setErro(null);
      setLastRefresh(new Date());
    } catch {
      setErro("Não foi possível contatar o servidor.");
    }
  }, []);

  useEffect(() => {
    if (user?.role === "SUPERADMIN") carregar();
  }, [user, carregar]);

  useEffect(() => {
    if (user?.role !== "SUPERADMIN") return;
    const i = setInterval(carregar, 15000);
    return () => clearInterval(i);
  }, [user, carregar]);

  // saúde de um nó (verde/âmbar/cinza) a partir do snapshot de infra
  const saudeDoNo = useCallback((no: MapaNo): "ok" | "erro" | "neutro" => {
    if (!no.saude_key || !infra) return "neutro";
    const s = (infra as unknown as Record<string, { ok?: boolean; configured?: boolean }>)[no.saude_key];
    if (!s) return "neutro";
    if (s.configured === false) return "neutro";
    return s.ok ? "ok" : "erro";
  }, [infra]);

  // Reconstrói nós/arestas do reactflow quando mapa/infra mudam
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
        id: n.id,
        position: p,
        data: { label: n.label },
        style: {
          background: cor, color: "#F4F0EA", border: `3px solid ${ring}`,
          borderRadius: 12, fontSize: 11, fontWeight: 600, padding: "6px 10px",
          width: n.id === "api" ? 130 : 108, textAlign: "center" as const,
          boxShadow: saude === "erro" ? "0 0 0 3px rgba(220,38,38,0.25)" : undefined,
        },
      };
    });

    const rfEdges: Edge[] = mapa.arestas.map((a, i) => ({
      id: `e${i}`, source: a.de, target: a.para, label: a.tipo,
      animated: true,
      style: { stroke: "#B8954A", strokeWidth: 1.2, opacity: 0.55 },
      labelStyle: { fontSize: 9, fill: "#6B7280" },
      markerEnd: { type: MarkerType.ArrowClosed, color: "#B8954A" },
    }));

    setNodes(rfNodes);
    setEdges(rfEdges);
  }, [mapa, saudeDoNo, setNodes, setEdges]);

  const resumo = mapa?.resumo;
  const infraCards = useMemo(() => infra ? [
    { label: "Celery", ok: infra.celery.ok, extra: `${infra.celery.workers} worker(s)` },
    { label: "Redis", ok: infra.redis.ok },
    { label: "Qdrant", ok: infra.qdrant.ok, extra: infra.qdrant.configured === false ? "não configurado" : undefined },
    { label: "Postgres", ok: infra.postgres_pool.ok },
  ] : [], [infra]);

  if (user && user.role !== "SUPERADMIN") return null;

  return (
    <div className="space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Cérebro" }]} />
      <div className="afj-page-header">
        <div>
          <h1 className="afj-page-title flex items-center gap-2">
            <Brain size={20} className="text-afj-gold" /> Cérebro do Sistema
          </h1>
          <p className="text-afj-black/45 text-sm mt-1">
            Mapa vivo dos módulos, integrações e infraestrutura — exclusivo do SuperAdmin.
          </p>
        </div>
        <button onClick={carregar} className="btn-afj-outline rounded-sm p-2" title="Atualizar" aria-label="Atualizar">
          <RefreshCw size={15} />
        </button>
      </div>

      {erro ? (
        <div className="afj-card p-6 text-center text-sm text-red-600">{erro}</div>
      ) : (
        <>
          {/* Resumo + infra */}
          <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
            <div className="afj-stat-card"><p className="text-2xl font-bold text-afj-black">{resumo?.agentes ?? "—"}</p><p className="text-xs text-afj-black/50 mt-0.5">Agentes IA</p></div>
            <div className="afj-stat-card"><p className="text-2xl font-bold text-afj-black">{resumo?.providers ?? "—"}</p><p className="text-xs text-afj-black/50 mt-0.5">Integrações</p></div>
            {infraCards.map((c) => (
              <div key={c.label} className="afj-stat-card">
                <p className={`text-sm font-bold flex items-center gap-1.5 ${c.ok ? "text-green-600" : "text-red-500"}`}>
                  <Cpu size={13} /> {c.label}
                </p>
                <p className="text-xs text-afj-black/50 mt-0.5">{c.ok ? (c.extra || "ok") : (c.extra || "indisponível")}</p>
              </div>
            ))}
          </div>

          {/* Mapa reactflow */}
          <div className="afj-card p-0 overflow-hidden" style={{ height: 560 }}>
            <ReactFlow
              nodes={nodes} edges={edges}
              onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
              fitView minZoom={0.3} maxZoom={1.6}
              proOptions={{ hideAttribution: true }}
              nodesDraggable nodesConnectable={false} elementsSelectable={false}
            >
              <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#e5e0d8" />
              <Controls showInteractive={false} />
            </ReactFlow>
          </div>

          <p className="text-[11px] text-afj-black/35 text-center flex items-center justify-center gap-1.5">
            <Activity size={11} /> Anel verde = saudável · vermelho = indisponível · sinais dourados = fluxos ativos
            {lastRefresh && ` · atualizado ${lastRefresh.toLocaleTimeString("pt-BR")}`}
          </p>

          {/* Assistente IA do sistema (RAG + streaming) */}
          <BrainAssistant />
        </>
      )}
    </div>
  );
}
