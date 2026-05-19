"use client";
import { useCallback } from "react";
import ReactFlow, {
  Node,
  Edge,
  Controls,
  MiniMap,
  Background,
  BackgroundVariant,
  useNodesState,
  useEdgesState,
  addEdge,
  Connection,
  MarkerType,
} from "reactflow";
import "reactflow/dist/style.css";

export interface VisualLawNode {
  id: string;
  label: string;
  type?: "processo" | "prazo" | "parte" | "decisao" | "acao" | "default";
  description?: string;
}

export interface VisualLawEdge {
  id: string;
  source: string;
  target: string;
  label?: string;
}

interface VisualLawCanvasProps {
  nodes: VisualLawNode[];
  edges: VisualLawEdge[];
  onNodeClick?: (nodeId: string) => void;
}

const NODE_STYLES: Record<string, React.CSSProperties> = {
  processo: {
    background: "#EFF6FF",
    border: "1.5px solid #3B82F6",
    color: "#1D4ED8",
    borderRadius: "8px",
    fontSize: "12px",
    fontWeight: 600,
    padding: "8px 12px",
  },
  prazo: {
    background: "#FEF2F2",
    border: "1.5px solid #EF4444",
    color: "#B91C1C",
    borderRadius: "8px",
    fontSize: "12px",
    fontWeight: 600,
    padding: "8px 12px",
  },
  parte: {
    background: "#F8FAFC",
    border: "1.5px solid #94A3B8",
    color: "#334155",
    borderRadius: "8px",
    fontSize: "12px",
    padding: "8px 12px",
  },
  decisao: {
    background: "#FFF7ED",
    border: "1.5px solid #C9A84C",
    color: "#92400E",
    borderRadius: "8px",
    fontSize: "12px",
    fontWeight: 600,
    padding: "8px 12px",
  },
  acao: {
    background: "#F0FDF4",
    border: "1.5px solid #22C55E",
    color: "#15803D",
    borderRadius: "8px",
    fontSize: "12px",
    padding: "8px 12px",
  },
  default: {
    background: "#FFFFFF",
    border: "1.5px solid #E2E8F0",
    color: "#1A1A1A",
    borderRadius: "8px",
    fontSize: "12px",
    padding: "8px 12px",
  },
};

function buildLayout(
  inputNodes: VisualLawNode[],
  inputEdges: VisualLawEdge[]
): { nodes: Node[]; edges: Edge[] } {
  const COLS = 3;
  const H_GAP = 220;
  const V_GAP = 120;

  const nodes: Node[] = inputNodes.map((n, idx) => ({
    id: n.id,
    data: { label: n.label },
    position: {
      x: (idx % COLS) * H_GAP + 40,
      y: Math.floor(idx / COLS) * V_GAP + 40,
    },
    style: NODE_STYLES[n.type ?? "default"] ?? NODE_STYLES.default,
  }));

  const edges: Edge[] = inputEdges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    label: e.label,
    markerEnd: { type: MarkerType.ArrowClosed, color: "#C9A84C" },
    style: { stroke: "#C9A84C", strokeWidth: 1.5 },
    labelStyle: { fontSize: 10, fill: "#666" },
    labelBgStyle: { fill: "#fff", fillOpacity: 0.9 },
  }));

  return { nodes, edges };
}

export function VisualLawCanvas({ nodes: inputNodes, edges: inputEdges, onNodeClick }: VisualLawCanvasProps) {
  const { nodes: layoutNodes, edges: layoutEdges } = buildLayout(inputNodes, inputEdges);
  const [nodes, , onNodesChange] = useNodesState(layoutNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(layoutEdges);

  const onConnect = useCallback(
    (params: Connection) => setEdges((eds) => addEdge(params, eds)),
    [setEdges]
  );

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => onNodeClick?.(node.id),
    [onNodeClick]
  );

  return (
    <div style={{ width: "100%", height: "500px", borderRadius: "8px", overflow: "hidden" }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={handleNodeClick}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.3}
        maxZoom={2}
        attributionPosition="bottom-right"
      >
        <Controls showInteractive={false} />
        <MiniMap
          nodeColor={(n) => {
            const style = n.style as React.CSSProperties | undefined;
            return (style?.border as string | undefined)?.split(" ")[2] ?? "#C9A84C";
          }}
          maskColor="rgba(245, 240, 232, 0.6)"
          style={{ background: "#F5F0E8", border: "1px solid #e2d9c8" }}
        />
        <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="#e2d9c8" />
      </ReactFlow>
    </div>
  );
}

export function parseMermaidToNodes(mermaidText: string): {
  nodes: VisualLawNode[];
  edges: VisualLawEdge[];
} {
  const nodes: VisualLawNode[] = [];
  const edges: VisualLawEdge[] = [];
  const nodeSet = new Set<string>();

  const edgeRegex = /(\w+)(?:\[([^\]]+)\])?\s*--?>(?:\|([^|]+)\|)?\s*(\w+)(?:\[([^\]]+)\])?/g;
  let match;

  while ((match = edgeRegex.exec(mermaidText)) !== null) {
    const [, srcId, srcLabel, edgeLabel, tgtId, tgtLabel] = match;

    if (!nodeSet.has(srcId)) {
      nodes.push({ id: srcId, label: srcLabel ?? srcId });
      nodeSet.add(srcId);
    }
    if (!nodeSet.has(tgtId)) {
      nodes.push({ id: tgtId, label: tgtLabel ?? tgtId });
      nodeSet.add(tgtId);
    }

    edges.push({
      id: `${srcId}-${tgtId}-${edges.length}`,
      source: srcId,
      target: tgtId,
      label: edgeLabel,
    });
  }

  return { nodes, edges };
}
