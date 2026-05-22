"use client";
import Link from "next/link";
import { useState, useEffect } from "react";
import { usePathname } from "next/navigation";
import { useUserStore } from "@/store";
import {
  LayoutDashboard, Scale, FileText, Users, FolderOpen,
  Bot, CheckSquare, DollarSign, Shield, Shapes, Settings,
  Bell, Search, ChevronRight, FileEdit, Menu, X, LogOut
} from "lucide-react";
import { useApprovalCount } from "@/hooks/useApprovals";
import { useNotifications } from "@/hooks/useNotifications";
import { NotificationDropdown } from "@/components/layout/NotificationDropdown";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/processos", label: "Processos", icon: Scale },
  { href: "/peticoes", label: "Petições", icon: FileEdit },
  { href: "/clientes", label: "Clientes", icon: Users },
  { href: "/documentos", label: "Documentos", icon: FolderOpen },
  { href: "/contratos", label: "Contratos", icon: FileText },
  { href: "/agentes", label: "Agentes IA", icon: Bot },
  { href: "/aprovacoes", label: "Aprovações", icon: CheckSquare },
  { href: "/financeiro", label: "Financeiro", icon: DollarSign },
  { href: "/visual-law", label: "Visual Law", icon: Shapes },
  { href: "/auditoria", label: "Auditoria", icon: Shield },
  { href: "/configuracoes", label: "Configurações", icon: Settings },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { count: approvalCount } = useApprovalCount();
  const { unreadCount } = useNotifications();
  const [notifOpen, setNotifOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { user, setUser } = useUserStore();

  useEffect(() => {
    if (!user) {
      try {
        const stored = localStorage.getItem("afj_user");
        if (stored) setUser(JSON.parse(stored));
      } catch {}
    }
  }, []);

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-20 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* ─── Sidebar AFJ ─────────────────────────────────────────────── */}
      <aside aria-label="Menu lateral" className={`afj-sidebar fixed md:static inset-y-0 left-0 z-30 transform transition-transform duration-200 ${sidebarOpen ? "translate-x-0" : "-translate-x-full"} md:translate-x-0`}>
        {/* Logo */}
        <div className="afj-sidebar-logo">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-afj-gold/10 border border-afj-gold/30 flex items-center justify-center">
              <span className="text-afj-gold font-display font-bold text-sm">AFJ</span>
            </div>
            <div>
              <p className="text-afj-cream text-sm font-semibold font-display">AFJ CORE</p>
              <p className="text-afj-cream/40 text-xs">Sistema Jurídico IA</p>
            </div>
          </div>
        </div>

        {/* Navegação */}
        <nav aria-label="Navegação principal" className="flex-1 overflow-y-auto py-3 space-y-0.5">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href || pathname.startsWith(item.href + "/");
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`afj-sidebar-nav-item ${isActive ? "active" : ""}`}
              >
                <Icon size={16} />
                <span>{item.label}</span>
                {isActive && <ChevronRight size={12} className="ml-auto text-afj-gold/60" />}
              </Link>
            );
          })}
        </nav>

        {/* Rodapé do sidebar */}
        <div className="border-t border-afj-charcoal px-4 py-4">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 rounded-full bg-afj-gold/20 border border-afj-gold/30 flex items-center justify-center">
              <span className="text-afj-gold text-xs font-bold">U</span>
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
              className="text-afj-cream/30 hover:text-red-400 transition-colors"
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
            <div className="hidden sm:flex items-center gap-2 text-afj-black/40 text-sm">
              <Search size={14} />
              <span>Buscar processos, clientes, documentos... (⌘K)</span>
            </div>
          </div>
          <div className="flex items-center gap-3">
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

        {/* Área de conteúdo com scroll */}
        <main className="flex-1 overflow-y-auto p-6 bg-afj-cream">
          {children}
        </main>
      </div>
    </div>
  );
}
