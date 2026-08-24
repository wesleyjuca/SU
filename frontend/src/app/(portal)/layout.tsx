"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { LogOut, Scale } from "lucide-react";
import { ToastProvider } from "@/components/ui/Toast";

/** Fase 233 — o portal virou uma única tela (dashboard consolidado),
 * então a nav de 5 rotas (Dashboard/Meus Processos/Documentos/
 * Financeiro/Mensagens) deixou de fazer sentido — removida. */
export default function PortalLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [clientName, setClientName] = useState("");

  useEffect(() => {
    try {
      const user = JSON.parse(localStorage.getItem("afj_portal_user") ?? "{}");
      setClientName(user.full_name ?? "Cliente");
    } catch {}
  }, []);

  async function handleLogout() {
    try {
      const token = localStorage.getItem("afj_portal_token");
      const refreshToken = localStorage.getItem("afj_portal_refresh_token");
      if (refreshToken) {
        // Invalida a Session/refresh no backend (mesmo endpoint genérico de
        // sempre) — sem isto o token continua tecnicamente válido até expirar.
        await fetch("/api/v1/auth/logout", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ refresh_token: refreshToken }),
        }).catch(() => {});
      }
      await fetch("/api/portal/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "clear" }),
      });
    } finally {
      localStorage.removeItem("afj_portal_token");
      localStorage.removeItem("afj_portal_refresh_token");
      localStorage.removeItem("afj_portal_user");
      router.push("/portal/login");
    }
  }

  return (
    <ToastProvider>
      <div className="min-h-screen bg-gray-50 flex flex-col">
        {/* Header */}
        <header className="bg-white border-b border-gray-200 h-14 flex items-center px-4 sm:px-6 gap-4 z-30 relative">
          <div className="flex items-center gap-2 min-w-0">
            <div className="w-7 h-7 rounded bg-[#B8954A] flex items-center justify-center flex-shrink-0">
              <Scale size={14} className="text-white" />
            </div>
            <div className="hidden sm:block">
              <p className="text-[11px] font-bold tracking-widest uppercase text-gray-800 leading-none">AFJ CORE</p>
              <p className="text-[9px] text-gray-400 tracking-widest uppercase">Portal do Cliente</p>
            </div>
          </div>

          <div className="flex items-center gap-2 ml-auto">
            <span className="text-sm text-gray-600 truncate max-w-[160px]">{clientName}</span>
            <button
              onClick={handleLogout}
              className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-800 border border-gray-200 rounded px-2.5 py-1.5 transition-colors"
            >
              <LogOut size={13} />
              <span className="hidden sm:inline">Sair</span>
            </button>
          </div>
        </header>

        <main className="flex-1 max-w-5xl mx-auto w-full px-4 py-6">
          {children}
        </main>

        <footer className="text-center text-[10px] text-gray-400 py-4 border-t border-gray-100">
          AFJ CORE — Portal Seguro do Cliente
        </footer>
      </div>
    </ToastProvider>
  );
}
