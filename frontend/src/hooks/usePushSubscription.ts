"use client";
import { useState, useEffect } from "react";

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = window.atob(base64);
  const output = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) output[i] = raw.charCodeAt(i);
  return output;
}

function authHeader(): Record<string, string> {
  const token = localStorage.getItem("afj_access_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function usePushSubscription() {
  const [permissionStatus, setPermissionStatus] = useState<NotificationPermission | "unsupported">("unsupported");
  const [subscribed, setSubscribed] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || !("PushManager" in window) || !("Notification" in window)) return;
    setPermissionStatus(Notification.permission);

    // Check if already subscribed
    navigator.serviceWorker.ready
      .then((reg) => reg.pushManager.getSubscription())
      .then((sub) => setSubscribed(!!sub))
      .catch(() => {});
  }, []);

  async function subscribe(): Promise<boolean> {
    if (typeof window === "undefined" || !("PushManager" in window)) return false;
    setLoading(true);
    try {
      const permission = await Notification.requestPermission();
      setPermissionStatus(permission);
      if (permission !== "granted") return false;

      // Get VAPID public key from backend
      const keyRes = await fetch("/api/v1/push/vapid-public-key", {
        headers: authHeader(),
      });
      if (!keyRes.ok) return false;
      const { public_key } = await keyRes.json();

      // Subscribe to push manager
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(public_key),
      });

      const json = sub.toJSON();
      if (!json.endpoint || !json.keys) return false;

      // Register subscription with backend
      const subRes = await fetch("/api/v1/push/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify({
          endpoint: json.endpoint,
          p256dh: json.keys.p256dh,
          auth: json.keys.auth,
          user_agent: navigator.userAgent.substring(0, 200),
        }),
      });

      if (subRes.ok) {
        setSubscribed(true);
        return true;
      }
      return false;
    } catch {
      return false;
    } finally {
      setLoading(false);
    }
  }

  async function unsubscribe(): Promise<void> {
    if (typeof window === "undefined") return;
    setLoading(true);
    try {
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.getSubscription();
      if (!sub) return;

      await fetch("/api/v1/push/unsubscribe", {
        method: "DELETE",
        headers: { "Content-Type": "application/json", ...authHeader() },
        body: JSON.stringify({ endpoint: sub.endpoint }),
      });
      await sub.unsubscribe();
      setSubscribed(false);
    } finally {
      setLoading(false);
    }
  }

  return { permissionStatus, subscribed, subscribe, unsubscribe, loading };
}
