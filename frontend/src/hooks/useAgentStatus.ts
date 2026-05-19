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

export function useAgentStatus() {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [lastEvent, setLastEvent] = useState<AgentEvent | null>(null);
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    const userId = typeof window !== "undefined"
      ? localStorage.getItem("afj_user_id")
      : null;

    if (!userId) return;

    afjWS.connect(userId);
    setIsConnected(true);

    const unsubConnected = afjWS.on("CONNECTED", () => setIsConnected(true));

    const unsubStart = afjWS.on("AGENT_RUN_STARTED", (data) => {
      const event: AgentEvent = { ...data as any, timestamp: Date.now() };
      setEvents((prev) => [event, ...prev].slice(0, 50));
      setLastEvent(event);
    });

    const unsubUpdate = afjWS.on("AGENT_STEP_UPDATE", (data) => {
      const event: AgentEvent = { ...data as any, timestamp: Date.now() };
      setEvents((prev) => [event, ...prev].slice(0, 50));
      setLastEvent(event);
    });

    const unsubDone = afjWS.on("AGENT_RUN_COMPLETED", (data) => {
      const event: AgentEvent = { ...data as any, timestamp: Date.now() };
      setEvents((prev) => [event, ...prev].slice(0, 50));
      setLastEvent(event);
    });

    return () => {
      unsubConnected();
      unsubStart();
      unsubUpdate();
      unsubDone();
    };
  }, []);

  const clearEvents = useCallback(() => setEvents([]), []);

  return { events, lastEvent, isConnected, clearEvents };
}
