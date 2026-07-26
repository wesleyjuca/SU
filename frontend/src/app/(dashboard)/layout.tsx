"use client";
import Link from "next/link";
import { useState, useEffect } from "react";
import { usePathname } from "next/navigation";
import { useUserStore, useThemeStore } from "@/store";
import { fetchAndApplyTheme } from "@/lib/theme";
import {
  Bell, Search, ChevronRight, Menu, X, LogOut, Moon, Sun, ExternalLink
} from "lucide-react";
import { navSections } from "@/lib/nav";
import { useApprovalCount } from "@/hooks/useApprovals";
import { useNotifications } from "@/hooks/useNotifications";
import { useAgentStatus } from "@/hooks/useAgentStatus";
import { useBilling } from "@/hooks/useBilling";
import { AlertBanner } from "@/components/ui/AlertBanner";
import { NotificationDropdown } from "@/components/layout/NotificationDropdown";
import { SearchModal } from "@/components/layout/SearchModal";
import { BottomNav } from "@/components/layout/BottomNav";
import { ToastProvider } from "@/components/ui/Toast";

// Menu único em @/lib/nav (consumido também por BottomNav e SearchModal).

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { count: approvalCount } = useApprovalCount();
  const { unreadCount } = useNotifications();
  // Ativa a conexão WS compartilhada (afjWS) pra toda a área logada — sem
  // isso, os handlers de useNotifications/useApprovalCount nunca recebiam
  // evento nenhum (a conexão nunca era aberta em lugar nenhum do app).
  useAgentStatus();
  const { billing } = useBilling();
  const [notifOpen, setNotifOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem("afj_dark");
    if (saved === "1") { document.documentElement.classList.add("dark"); setDark(true); }
  }, []);

  function toggleDark() {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("afj_dark", next ? "1" : "0");
  }

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setSearchOpen((o) => !o);
      }
      if (e.key === "Escape") {
        setSearchOpen(false);
        setSidebarOpen(false); // fecha o menu overlay no mobile/teclado/remoto
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, []);
  const { user, setUser } = useUserStore();
  const { theme, setTheme } = useThemeStore();

  useEffect(() => {
    if (!user) {
      try {
        const stored = localStorage.getItem("afj_user");
        if (stored) setUser(JSON.parse(stored));
      } catch {}
    }
  }, []);

  useEffect(() => {
    fetchAndApplyTheme().then((t) => setTheme(t)).catch(() => {});
  }, []);

  return (
    <ToastProvider>
    <div className="flex h-screen overflow-hidden">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-20 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* ─── Sidebar AFJ ─────────────────────────────────────────────── */}
      {/* A barra é sempre `fixed` (ver .afj-sidebar); o conteúdo compensa com md:ml-64.
          Antes tinha md:static aqui → a barra entrava no fluxo E o conteúdo mantinha
          a margem, gerando ~256px de vão vazio ("conteúdo na lateral"). */}
      <aside id="sidebar" aria-label="Menu lateral" className={`afj-sidebar fixed inset-y-0 left-0 z-30 transform transition-transform duration-200 ${sidebarOpen ? "translate-x-0" : "-translate-x-full"} md:translate-x-0`}>
        {/* Logo — dinâmico ou monograma AFJ como fallback */}
        <div className="afj-sidebar-logo">
          <div className="flex items-center gap-3">
            {theme.logoUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={theme.logoUrl}
                alt={theme.appName}
                className="h-9 w-auto max-w-[140px] object-contain"
              />
            ) : (
              <>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src="/logo-afj-mark.png"
                  alt="AFJ Advogados"
                  className="h-9 w-auto flex-shrink-0 object-contain"
                />
                <div>
                  <p className="text-afj-cream text-[11px] font-bold tracking-[0.18em] uppercase font-display">
                    {theme.appName || "AFJ CORE"}
                  </p>
                  <p className="text-afj-cream/35 text-[9px] tracking-widest uppercase mt-0.5">
                    Sistema Jurídico IA
                  </p>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Navegação */}
        <nav aria-label="Navegação principal" className="flex-1 overflow-y-auto py-3">
          {navSections.map((section) => {
            const visibleItems = section.items.filter(
              (item) => !item.roles || item.roles.includes(user?.role ?? "")
            );
            if (visibleItems.length === 0) return null;
            return (
              <div key={section.title ?? "core"}>
                {section.title && (
                  <p className="px-4 pt-4 pb-1 text-[9px] font-bold text-white/25 uppercase tracking-[0.18em]">
                    {section.title}
                  </p>
                )}
                <div className="space-y-0.5">
                  {visibleItems.map((item) => {
                    const Icon = item.icon;
                    const newTab = "newTab" in item && item.newTab === true;
                    const isActive = !newTab && (pathname === item.href || pathname.startsWith(item.href + "/"));
                    return (
                      <Link
                        key={item.href}
                        href={item.href}
                        target={newTab ? "_blank" : undefined}
                        rel={newTab ? "noopener noreferrer" : undefined}
                        className={`afj-sidebar-nav-item ${isActive ? "active" : ""}`}
                      >
                        <Icon size={16} />
                        <span>{item.label}</span>
                        {newTab && <ExternalLink size={11} className="ml-auto text-afj-cream/30" />}
                        {isActive && <ChevronRight size={12} className="ml-auto text-afj-gold/60" />}
                      </Link>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </nav>

        {/* Rodapé do sidebar */}
        <div className="border-t border-white/10 px-4 py-4">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 rounded-full bg-afj-gold/20 border border-afj-gold/30 flex items-center justify-center">
              <span className="text-afj-gold text-xs font-bold">
                {user?.full_name ? user.full_name.charAt(0).toUpperCase() : "U"}
              </span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-afj-cream text-xs font-medium truncate">{user?.full_name || "Usuário"}</p>
              <p className="text-afj-cream/40 text-xs">{user?.role || "Advogado"}</p>
            </div>
            <button
              onClick={async () => {
                try {
                  const token = localStorage.getItem("afj_access_token");
                  const refresh = localStorage.getItem("afj_refresh_token");
                  if (refresh) {
                    await fetch("/api/v1/auth/logout", {
                      method: "POST",
                      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
                      body: JSON.stringify({ refresh_token: refresh }),
                    });
                  }
                  await fetch("/api/auth/session", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ action: "clear" }),
                  });
                } catch {}
                localStorage.removeItem("afj_access_token");
                localStorage.removeItem("afj_refresh_token");
                localStorage.removeItem("afj_user");
                window.location.href = "/login";
              }}
              className="tap-target text-afj-cream/30 hover:text-red-400 transition-colors"
              aria-label="Sair do sistema"
              title="Sair"
            >
              <LogOut size={14} />
            </button>
          </div>
        </div>
      </aside>

      {/* ─── Conteúdo principal ──────────────────────────────────────── */}
      <div className="flex-1 flex flex-col md:ml-64 overflow-hidden">
        {/* Header */}
        <header className="h-14 bg-white border-b border-afj-cream-dark flex items-center justify-between px-4 md:px-6 flex-shrink-0">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setSidebarOpen((o) => !o)}
              className="md:hidden text-afj-black/60 hover:text-afj-black transition-colors p-1"
              aria-label={sidebarOpen ? "Fechar menu" : "Abrir menu"}
              aria-expanded={sidebarOpen}
              aria-controls="sidebar"
            >
              {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
            <span className="hidden xl:block text-[9px] tracking-[0.22em] uppercase text-afj-black/25 font-display mr-1 select-none">
              Almeida, Freire & Jucá
            </span>
            <button
              onClick={() => setSearchOpen(true)}
              className="hidden sm:flex items-center gap-2 text-afj-black/35 text-sm hover:text-afj-black/55 transition-colors px-3 py-1.5 rounded-sm hover:bg-afj-cream-dark border border-transparent hover:border-afj-cream-dark"
            >
              <Search size={13} />
              <span className="text-xs">Buscar processos, clientes, documentos...</span>
              <kbd className="ml-2 text-[10px] font-mono bg-afj-cream-dark px-1.5 py-0.5 rounded-sm text-afj-black/30">⌘K</kbd>
            </button>
            {/* No celular a busca era inacessível (botão hidden + só ⌘K) */}
            <button
              onClick={() => setSearchOpen(true)}
              className="sm:hidden tap-target text-afj-black/50 hover:text-afj-black transition-colors"
              aria-label="Buscar"
            >
              <Search size={18} />
            </button>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={toggleDark}
              className="text-afj-black/40 hover:text-afj-black transition-colors p-1"
              aria-label={dark ? "Modo claro" : "Modo escuro"}
              title={dark ? "Modo claro" : "Modo escuro"}
            >
              {dark ? <Sun size={16} /> : <Moon size={16} />}
            </button>
            <div className="relative">
              <button
                onClick={() => setNotifOpen((o) => !o)}
                className="relative text-afj-black/60 hover:text-afj-black transition-colors p-1"
                aria-label="Notificações"
                aria-haspopup="true"
                aria-expanded={notifOpen}
              >
                <Bell size={18} />
                {(unreadCount > 0 || approvalCount > 0) && (
                  <span className="absolute -top-0.5 -right-0.5 min-w-[14px] h-3.5 bg-red-500 rounded-full text-white text-[9px] flex items-center justify-center font-bold px-0.5">
                    {Math.min(unreadCount + approvalCount, 99)}
                    {unreadCount + approvalCount > 99 ? "+" : ""}
                  </span>
                )}
              </button>
              <NotificationDropdown open={notifOpen} onClose={() => setNotifOpen(false)} />
            </div>
          </div>
        </header>

        {/* Banner global de cobrança — inadimplência (aviso) / suspensão (bloqueio) */}
        {billing?.status === "SUSPENSO" && (
          <AlertBanner variant="danger">
            Escritório suspenso por pendência financeira — as alterações estão bloqueadas até a regularização. Entre em contato com o administrador da plataforma.
          </AlertBanner>
        )}
        {billing?.status === "INADIMPLENTE" && (
          <AlertBanner variant="warning">
            Mensalidade vencida{typeof billing.dias_para_vencimento === "number" ? ` há ${Math.abs(billing.dias_para_vencimento)} dia(s)` : ""}. Regularize o pagamento para evitar a suspensão do acesso.
          </AlertBanner>
        )}

        {/* Área de conteúdo com scroll — pb-16 evita sobreposição da bottom nav no mobile */}
        <main className="flex-1 overflow-y-auto p-6 pb-20 md:pb-6 bg-afj-cream">
          {children}
        </main>
      </div>

      {/* Bottom navigation — apenas mobile */}
      <BottomNav approvalCount={approvalCount} />

      <SearchModal open={searchOpen} onClose={() => setSearchOpen(false)} />
    </div>
    </ToastProvider>
  );
}
