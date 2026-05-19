"use client";
import { useEffect, useCallback } from "react";
import afjWS from "@/lib/websocket";
import { useNotificationStore } from "@/store";
import type { NotificationItem } from "@/store";

const POLL_INTERVAL_MS = 60_000;

export function useNotifications() {
  const { setNotifications, markRead, markAllRead, addNotification, setLoading, unreadCount } =
    useNotificationStore();

  const fetchNotifications = useCallback(async () => {
    const token = typeof window !== "undefined" ? localStorage.getItem("afj_access_token") : null;
    if (!token) return;

    setLoading(true);
    try {
      const res = await fetch("/api/v1/notifications?limit=30", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setNotifications(data.items as NotificationItem[], data.unread_count);
      }
    } catch {}
    finally {
      setLoading(false);
    }
  }, [setNotifications, setLoading]);

  const markNotificationRead = useCallback(
    async (id: string) => {
      const token = localStorage.getItem("afj_access_token");
      markRead(id);
      try {
        await fetch(`/api/v1/notifications/${id}/read`, {
          method: "PATCH",
          headers: { Authorization: `Bearer ${token}` },
        });
      } catch {}
    },
    [markRead]
  );

  const markAllNotificationsRead = useCallback(async () => {
    const token = localStorage.getItem("afj_access_token");
    markAllRead();
    try {
      await fetch("/api/v1/notifications/mark-all-read", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
    } catch {}
  }, [markAllRead]);

  useEffect(() => {
    fetchNotifications();

    const interval = setInterval(fetchNotifications, POLL_INTERVAL_MS);

    const unsubWS = afjWS.on("NOTIFICATION", (data) => {
      const item: NotificationItem = {
        id: (data.id as string) ?? crypto.randomUUID(),
        tipo: (data.tipo as string) ?? "SISTEMA",
        titulo: (data.titulo as string) ?? "Nova notificação",
        corpo: (data.corpo as string) ?? null,
        lida: false,
        priority: (data.priority as string) ?? "NORMAL",
        link: (data.link as string) ?? null,
        created_at: new Date().toISOString(),
      };
      addNotification(item);
    });

    const unsubAgent = afjWS.on("AGENT_RUN_COMPLETED", () => {
      fetchNotifications();
    });

    const unsubApproval = afjWS.on("NEW_APPROVAL_PENDING", () => {
      fetchNotifications();
    });

    return () => {
      clearInterval(interval);
      unsubWS();
      unsubAgent();
      unsubApproval();
    };
  }, [fetchNotifications, addNotification]);

  return {
    unreadCount,
    fetchNotifications,
    markNotificationRead,
    markAllNotificationsRead,
  };
}
