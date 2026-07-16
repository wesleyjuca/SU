"use client";
import { useEffect, useState } from "react";
import { Download, RefreshCw, X } from "lucide-react";

// Evento não tipado pelo TS (spec do Chrome/Edge/Android).
interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

const INSTALL_DISMISSED_KEY = "afj_install_dismissed";

export function ServiceWorkerProvider({ children }: { children: React.ReactNode }) {
  const [updateReady, setUpdateReady] = useState(false);
  const [installEvent, setInstallEvent] = useState<BeforeInstallPromptEvent | null>(null);

  useEffect(() => {
    if (
      typeof window !== "undefined" &&
      "serviceWorker" in navigator &&
      process.env.NODE_ENV === "production"
    ) {
      navigator.serviceWorker
        .register("/sw.js", { scope: "/" })
        .then((reg) => {
          console.log("[SW] Registered:", reg.scope);
          // Nova versão instalada com uma antiga controlando → avisa o usuário
          reg.addEventListener("updatefound", () => {
            const nw = reg.installing;
            nw?.addEventListener("statechange", () => {
              if (nw.state === "installed" && navigator.serviceWorker.controller) {
                setUpdateReady(true);
              }
            });
          });
        })
        .catch((err) => {
          console.warn("[SW] Registration failed:", err);
        });

      // O sw.js também emite SW_UPDATED ao ativar uma versão nova
      navigator.serviceWorker.addEventListener("message", (e) => {
        if (e.data?.type === "SW_UPDATED") setUpdateReady(true);
      });
    }
  }, []);

  // CTA de instalação do PWA — o navegador só dispara beforeinstallprompt
  // quando o app é instalável; sem o handler o usuário dependia do menu do browser.
  useEffect(() => {
    function onBeforeInstall(e: Event) {
      e.preventDefault();
      if (localStorage.getItem(INSTALL_DISMISSED_KEY)) return;
      setInstallEvent(e as BeforeInstallPromptEvent);
    }
    window.addEventListener("beforeinstallprompt", onBeforeInstall);
    return () => window.removeEventListener("beforeinstallprompt", onBeforeInstall);
  }, []);

  async function install() {
    if (!installEvent) return;
    await installEvent.prompt();
    const { outcome } = await installEvent.userChoice;
    if (outcome === "dismissed") localStorage.setItem(INSTALL_DISMISSED_KEY, "1");
    setInstallEvent(null);
  }

  return (
    <>
      {children}

      {installEvent && (
        <div className="fixed bottom-20 md:bottom-4 left-1/2 -translate-x-1/2 z-[60] flex items-center gap-3 bg-white border border-afj-cream-dark shadow-lg rounded-sm px-4 py-3">
          <Download size={16} className="text-afj-gold flex-shrink-0" />
          <span className="text-sm text-afj-black">Instale o AFJ CORE no seu dispositivo</span>
          <button onClick={install} className="btn-afj-primary text-xs px-3 py-1.5 rounded-sm">
            Instalar aplicativo
          </button>
          <button
            onClick={() => { localStorage.setItem(INSTALL_DISMISSED_KEY, "1"); setInstallEvent(null); }}
            className="tap-target text-afj-black/30 hover:text-afj-black"
            aria-label="Dispensar"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {updateReady && (
        <div className="fixed bottom-4 right-4 z-[60] flex items-center gap-3 bg-afj-black text-white shadow-lg rounded-sm px-4 py-3">
          <RefreshCw size={14} className="text-afj-gold flex-shrink-0" />
          <span className="text-sm">Nova versão disponível</span>
          <button
            onClick={() => window.location.reload()}
            className="text-xs font-semibold uppercase tracking-wider text-afj-gold hover:text-white transition-colors"
          >
            Atualizar
          </button>
        </div>
      )}
    </>
  );
}
