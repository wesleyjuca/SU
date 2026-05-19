"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, Scale, FileText, Users, FolderOpen,
  Bot, CheckSquare, DollarSign, Shield, Shapes, Settings,
  Bell, Search, ChevronRight, FileEdit
} from "lucide-react";

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

  return (
    <div className="flex h-screen overflow-hidden">
      {/* ─── Sidebar AFJ ─────────────────────────────────────────────── */}
      <aside className="afj-sidebar">
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
        <nav className="flex-1 overflow-y-auto py-3 space-y-0.5">
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
              <p className="text-afj-cream text-xs font-medium truncate">Usuário</p>
              <p className="text-afj-cream/40 text-xs">Advogado</p>
            </div>
          </div>
        </div>
      </aside>

      {/* ─── Conteúdo principal ──────────────────────────────────────── */}
      <div className="flex-1 flex flex-col ml-64 overflow-hidden">
        {/* Header */}
        <header className="h-14 bg-white border-b border-afj-cream-dark flex items-center justify-between px-6 flex-shrink-0">
          <div className="flex items-center gap-2 text-afj-black/40 text-sm">
            <Search size={14} />
            <span>Buscar processos, clientes, documentos... (⌘K)</span>
          </div>
          <div className="flex items-center gap-3">
            <button className="relative text-afj-black/60 hover:text-afj-black transition-colors">
              <Bell size={18} />
              <span className="absolute -top-1 -right-1 w-3.5 h-3.5 bg-red-500 rounded-full text-white text-[9px] flex items-center justify-center font-bold">3</span>
            </button>
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
