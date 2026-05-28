"use client";
import { useState, useEffect } from "react";
import { Bell, X } from "lucide-react";
import { usePushSubscription } from "@/hooks/usePushSubscription";

export function PushPermissionBanner() {
  const { permissionStatus, subscribed, subscribe, loading } = usePushSubscription();
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!("PushManager" in window) || !("Notification" in window)) return;
    // Show only if permission is default and not yet shown this session
    if (permissionStatus === "default" && !localStorage.getItem("afj_push_prompt_shown")) {
      setVisible(true);
    }
  }, [permissionStatus]);

  // Hide if already subscribed or permission resolved
  if (!visible || subscribed || permissionStatus === "granted" || permissionStatus === "denied") {
    return null;
  }

  function dismiss() {
    localStorage.setItem("afj_push_prompt_shown", "1");
    setVisible(false);
  }

  async function handleActivate() {
    const ok = await subscribe();
    localStorage.setItem("afj_push_prompt_shown", "1");
    if (ok) setVisible(false);
    else setVisible(false); // dismiss regardless
  }

  return (
    <div className="bg-afj-navy/5 border border-afj-gold/20 rounded-sm px-4 py-3 flex items-center gap-3 mb-4 animate-fade-in">
      <Bell size={15} className="text-afj-gold flex-shrink-0" />
      <p className="text-sm text-afj-black/70 flex-1">
        Ative notificações push para receber alertas de prazos mesmo com o app fechado.
      </p>
      <button
        onClick={handleActivate}
        disabled={loading}
        className="btn-afj-primary text-xs py-1.5 px-3 rounded-sm flex-shrink-0 disabled:opacity-50"
      >
        {loading ? "Ativando…" : "Ativar"}
      </button>
      <button
        onClick={dismiss}
        aria-label="Dispensar banner de notificações"
        className="text-afj-black/30 hover:text-afj-black transition-colors flex-shrink-0 ml-1"
      >
        <X size={14} />
      </button>
    </div>
  );
}
