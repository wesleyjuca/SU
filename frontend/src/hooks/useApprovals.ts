"use client";
import { useEffect, useState, useCallback } from "react";
import afjWS from "@/lib/websocket";

export function useApprovalCount() {
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);

  const fetchCount = useCallback(async () => {
    try {
      const token = typeof window !== "undefined"
        ? localStorage.getItem("afj_access_token")
        : null;
      if (!token) return;

      const res = await fetch("/api/v1/approvals?status=PENDENTE", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setCount(Array.isArray(data) ? data.length : 0);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCount();

    // Re-fetch when a new approval arrives via WebSocket
    const unsub = afjWS.on("NEW_APPROVAL_PENDING", () => {
      fetchCount();
    });

    // Also refresh when an agent completes (may have created an approval)
    const unsubDone = afjWS.on("AGENT_RUN_COMPLETED", () => {
      fetchCount();
    });

    return () => {
      unsub();
      unsubDone();
    };
  }, [fetchCount]);

  return { count, loading, refetch: fetchCount };
}
