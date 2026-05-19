"use client";
import { useState } from "react";
import { Bot, Play, CheckCircle, XCircle, Clock, DollarSign, AlertCircle, Pause } from "lucide-react";
import type { AgentStatus } from "@/types";

export interface AgentCardData {
  name: string;
  label: string;
  desc: string;
  category: string;
  status?: AgentStatus;
  lastRun?: string | null;
  costToday?: number;
  successRate?: number;
}

interface AgentStatusCardProps {
  agent: AgentCardData;
  categoryColor: string;
  onTrigger?: (agentName: string) => Promise<void>;
}

const STATUS_CONFIG: Record<AgentStatus, { icon: React.ReactNode; label: string; dotClass: string }> = {
  idle: {
    icon: <Clock size={10} />,
    label: "idle",
    dotClass: "agent-idle",
  },
  running: {
    icon: <span className="w-2 h-2 rounded-full bg-blue-500 animate-ping absolute" />,
    label: "rodando",
    dotClass: "bg-blue-500",
  },
  success: {
    icon: <CheckCircle size={10} className="text-green-600" />,
    label: "sucesso",
    dotClass: "bg-green-500",
  },
  failed: {
    icon: <XCircle size={10} className="text-red-600" />,
    label: "falhou",
    dotClass: "bg-red-500",
  },
  awaiting_approval: {
    icon: <AlertCircle size={10} className="text-amber-500" />,
    label: "aguardando",
    dotClass: "bg-amber-500 animate-pulse",
  },
  paused: {
    icon: <Pause size={10} className="text-gray-400" />,
    label: "pausado",
    dotClass: "bg-gray-400",
  },
};

export function AgentStatusCard({ agent, categoryColor, onTrigger }: AgentStatusCardProps) {
  const [triggering, setTriggering] = useState(false);
  const status = agent.status ?? "idle";
  const statusCfg = STATUS_CONFIG[status];
  const isRunning = status === "running";

  async function handleTrigger() {
    if (!onTrigger || triggering || isRunning) return;
    setTriggering(true);
    try {
      await onTrigger(agent.name);
    } finally {
      setTriggering(false);
    }
  }

  return (
    <div
      className={`afj-card p-4 flex flex-col gap-3 transition-all ${
        isRunning ? "border-blue-200 bg-blue-50/30 shadow-sm shadow-blue-100" : "hover:border-afj-gold/30"
      }`}
    >
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="relative w-8 h-8 rounded-lg bg-afj-gold/10 flex items-center justify-center flex-shrink-0">
          <Bot size={14} className={isRunning ? "text-blue-500" : "text-afj-gold"} />
          {isRunning && (
            <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-blue-500 border-2 border-white animate-pulse" />
          )}
        </div>
        <span className={`text-xs px-2 py-0.5 rounded-full border ${categoryColor}`}>
          {agent.category}
        </span>
      </div>

      {/* Info */}
      <div className="flex-1">
        <p className="font-semibold text-sm text-afj-black">{agent.label}</p>
        <p className="text-xs text-afj-black/50 mt-0.5 line-clamp-2">{agent.desc}</p>
      </div>

      {/* Status bar */}
      <div className="flex items-center justify-between text-xs text-afj-black/40 border-t border-afj-cream-dark pt-2">
        <span className="flex items-center gap-1.5">
          <span className={`relative w-1.5 h-1.5 rounded-full flex-shrink-0 ${statusCfg.dotClass}`} />
          <span className={isRunning ? "text-blue-600 font-medium" : ""}>{statusCfg.label}</span>
        </span>
        <span className="flex items-center gap-1">
          <DollarSign size={10} />
          {(agent.costToday ?? 0).toFixed(3)}
        </span>
      </div>

      {/* Last run */}
      {agent.lastRun && (
        <p className="text-xs text-afj-black/30 -mt-1">
          Último run: {new Date(agent.lastRun).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}
        </p>
      )}

      {/* Trigger button */}
      {onTrigger && (
        <button
          onClick={handleTrigger}
          disabled={triggering || isRunning}
          className={`w-full flex items-center justify-center gap-1.5 py-1.5 rounded text-xs font-medium transition-colors
            ${isRunning
              ? "bg-blue-50 text-blue-400 cursor-not-allowed"
              : "bg-afj-cream hover:bg-afj-gold/10 text-afj-black/60 hover:text-afj-gold disabled:opacity-50"
            }`}
        >
          <Play size={10} />
          {triggering ? "Iniciando..." : isRunning ? "Rodando..." : "Disparar"}
        </button>
      )}
    </div>
  );
}
