"use client";
import { useEffect, useRef, useState, useCallback } from "react";

const STATUS_MAP: Record<string, string> = {
  RUNNING: "running",
  SUCCESS: "success",
  FAILED: "error",
  AWAITING_APPROVAL: "approval",
  IDLE: "idle",
};

export function useAgentWebSocket() {
  const [agentStatus, setAgentStatus] = useState<Record<string, string>>({});
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    const token = typeof window !== "undefined"
      ? localStorage.getItem("afj_access_token")
      : null;
    if (!token) return;

    // Close any existing connection
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
    }

    try {
      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(
        `${protocol}://${window.location.host}/api/v1/ws?token=${token}`
      );

      ws.onopen = () => {
        if (reconnectTimer.current) {
          clearTimeout(reconnectTimer.current);
          reconnectTimer.current = null;
        }
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.agent_name && data.status) {
            const normalized = STATUS_MAP[data.status.toUpperCase()] ?? "idle";
            setAgentStatus((prev) => ({ ...prev, [data.agent_name]: normalized }));
          }
        } catch {
          // Ignore malformed messages
        }
      };

      ws.onerror = () => {
        // Silently handle errors; onclose will trigger reconnect
      };

      ws.onclose = () => {
        if (!mountedRef.current) return;
        // Auto-reconnect after 5 seconds
        reconnectTimer.current = setTimeout(connect, 5000);
      };

      wsRef.current = ws;
    } catch {
      // WebSocket not available (SSR, etc.) — reconnect later
      reconnectTimer.current = setTimeout(connect, 5000);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
      }
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
      }
    };
  }, [connect]);

  return agentStatus;
}
