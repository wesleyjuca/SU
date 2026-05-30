"use client";
import Link from "next/link";
import { useState, useEffect } from "react";
import { usePathname } from "next/navigation";
import { useUserStore } from "@/store";
import {
  LayoutDashboard, Scale, FileText, Users, FolderOpen,
  Bot, CheckSquare, DollarSign, Shield, Shapes, Settings,
  Bell, Search, ChevronRight, FileEdit, Menu, X, LogOut, BarChart2, CalendarClock, BookOpen,
  Moon, Sun, Activity, Users2
} from "lucide-react";
import { useApprovalCount } from "@/hooks/useApprovals";
import { useNotifications } from "@/hooks/useNotifications";
import { NotificationDropdown } from "@/components/layout/NotificationDropdown";
import { SearchModal } from "@/components/layout/SearchModal";
import { BottomNav } from "@/components/layout/BottomNav";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, roles: null },
  { href: "/processos", label: "Processos", icon: Scale, roles: null },
  { href: "/agenda", label: "Agenda", icon: CalendarClock, roles: null },
  { href: "/peticoes", label: "Petições", icon: FileEdit, roles: null },
  { href: "/clientes", label: "Clientes", icon: Users, roles: null },
  { href: "/documentos", label: "Documentos", icon: FolderOpen, roles: null },
  { href: "/contratos", label: "Contratos", icon: FileText, roles: null },
  { href: "/agentes", label: "Agentes IA", icon: Bot, roles: null },
  { href: "/aprovacoes", label: "Aprovações", icon: CheckSquare, roles: null },
  { href: "/financeiro", label: "Financeiro", icon: DollarSign, roles: null },
  { href: "/relatorios", label: "Relatórios", icon: BarChart2, roles: null },
  { href: "/visual-law", label: "Visual Law", icon: Shapes, roles: null },
  { href: "/busca-juridica", label: "Pesquisa Jurídica", icon: BookOpen, roles: null },
  { href: "/auditoria", label: "Auditoria", icon: Shield, roles: ["ADMIN", "SOCIO"] },
  { href: "/admin/health", label: "Monitoramento", icon: Activity, roles: ["ADMIN"] },
  { href: "/admin/usuarios", label: "Usuários", icon: Users2, roles: ["ADMIN"] },
  { href: "/configuracoes", label: "Configurações", icon: Settings, roles: null },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { count: approvalCount } = useApprovalCount();
  const { unreadCount } = useNotifications();
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
      if (e.key === "Escape") setSearchOpen(false);
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, []);
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
        {/* Logo — monograma geométrico AFJ */}
        <div className="afj-sidebar-logo">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 flex-shrink-0 text-afj-gold">
              <svg viewBox="0 0 80 80" className="w-9 h-9" fill="currentColor" aria-hidden="true">
                <path d="M 4,4 L 76,4 L 76,56 Q 76,78 40,78 Q 4,78 4,56 Z"
                      fill="none" stroke="currentColor" strokeWidth="3.5"/>
                <rect x="10" y="11" width="6" height="57"/>
                <rect x="29" y="11" width="6" height="57"/>
                <rect x="10" y="38" width="25" height="5"/>
                <rect x="43" y="11" width="6" height="41"/>
                <rect x="43" y="11" width="25" height="5"/>
                <rect x="43" y="27" width="18" height="5"/>
                <rect x="62" y="11" width="6" height="44"/>
                <path d="M 68,55 Q 68,68 55,68 Q 49,68 49,62"
                      fill="none" stroke="currentColor" strokeWidth="6" strokeLinecap="round"/>
              </svg>
            </div>
            <div>
              <p className="text-afj-cream text-[11px] font-bold tracking-[0.18em] uppercase font-display">
                AFJ CORE
              </p>
              <p className="text-afj-cream/35 text-[9px] tracking-widest uppercase mt-0.5">
                Sistema Jurídico IA
              </p>
            </div>
          </div>
        </div>

        {/* Navegação */}
        <nav aria-label="Navegação principal" className="flex-1 overflow-y-auto py-3 space-y-0.5">
          {navItems
            .filter((item) => !item.roles || item.roles.includes(user?.role ?? ""))
            .map((item) => {
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
        <div className="border-t border-white/10 px-4 py-4">
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

        {/* Área de conteúdo com scroll — pb-16 evita sobreposição da bottom nav no mobile */}
        <main className="flex-1 overflow-y-auto p-6 pb-20 md:pb-6 bg-afj-cream">
          {children}
        </main>
      </div>

      {/* Bottom navigation — apenas mobile */}
      <BottomNav approvalCount={approvalCount} />

      <SearchModal open={searchOpen} onClose={() => setSearchOpen(false)} />
    </div>
  );
}
