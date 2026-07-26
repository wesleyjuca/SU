"use client";
import { useEffect, useState, useCallback } from "react";
import afjWS from "@/lib/websocket";

export interface AgentEvent {
  type: string;
  run_id?: string;
  status?: string;
  task_type?: string;
  agent_name?: string;
  step?: string;
  timestamp: number;
}

const STATUS_MAP: Record<string, string> = {
  RUNNING: "running",
  SUCCESS: "success",
  FAILED: "error",
  AWAITING_APPROVAL: "approval",
  IDLE: "idle",
};

export function useAgentStatus() {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [lastEvent, setLastEvent] = useState<AgentEvent | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [agentStatusMap, setAgentStatusMap] = useState<Record<string, string>>({});

  useEffect(() => {
    // O login grava o usuário como JSON em "afj_user" — a chave "afj_user_id"
    // nunca existiu, então o WS jamais conectava e tudo degradava p/ polling.
    let userId: string | null = null;
    if (typeof window !== "undefined") {
      try {
        userId = JSON.parse(localStorage.getItem("afj_user") || "null")?.id ?? null;
      } catch {
        userId = null;
      }
    }

    if (!userId) return;

    afjWS.connect(userId);
    setIsConnected(true);

    const handleAgentEvent = (data: Record<string, unknown>) => {
      const event: AgentEvent = { ...(data as any), timestamp: Date.now() };
      setEvents((prev) => [event, ...prev].slice(0, 50));
      setLastEvent(event);
      if (data.agent_name && data.status) {
        const normalized = STATUS_MAP[String(data.status).toUpperCase()] ?? "idle";
        setAgentStatusMap((prev) => ({ ...prev, [data.agent_name as string]: normalized }));
      }
    };

    const unsubConnected = afjWS.on("CONNECTED", () => setIsConnected(true));
    const unsubStart = afjWS.on("AGENT_RUN_STARTED", handleAgentEvent);
    const unsubUpdate = afjWS.on("AGENT_STEP_UPDATE", handleAgentEvent);
    const unsubDone = afjWS.on("AGENT_RUN_COMPLETED", handleAgentEvent);

    return () => {
      unsubConnected();
      unsubStart();
      unsubUpdate();
      unsubDone();
    };
  }, []);

  const clearEvents = useCallback(() => setEvents([]), []);

  return { events, lastEvent, isConnected, clearEvents, agentStatusMap };
}
