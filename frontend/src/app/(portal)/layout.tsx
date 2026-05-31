"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LogOut, Scale, LayoutDashboard, FolderOpen, DollarSign, Menu, X } from "lucide-react";
import { ToastProvider } from "@/components/ui/Toast";

const NAV = [
  { href: "/portal/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/portal/processos", label: "Meus Processos", icon: Scale },
  { href: "/portal/documentos", label: "Documentos", icon: FolderOpen },
  { href: "/portal/financeiro", label: "Financeiro", icon: DollarSign },
];

export default function PortalLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [clientName, setClientName] = useState("");
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    try {
      const user = JSON.parse(localStorage.getItem("afj_portal_user") ?? "{}");
      setClientName(user.full_name ?? "Cliente");
    } catch {}
  }, []);

  async function handleLogout() {
    try {
      await fetch("/api/portal/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "clear" }),
      });
    } finally {
      localStorage.removeItem("afj_portal_token");
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

          {/* Desktop nav */}
          <nav className="hidden md:flex items-center gap-1 flex-1 justify-center">
            {NAV.map(({ href, label, icon: Icon }) => (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                  pathname === href || pathname.startsWith(href + "/")
                    ? "bg-[#B8954A]/10 text-[#B8954A]"
                    : "text-gray-500 hover:text-gray-800 hover:bg-gray-100"
                }`}
              >
                <Icon size={14} />
                {label}
              </Link>
            ))}
          </nav>

          <div className="flex items-center gap-2 ml-auto">
            <span className="hidden sm:block text-sm text-gray-600 truncate max-w-[160px]">{clientName}</span>
            <button
              onClick={handleLogout}
              className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-800 border border-gray-200 rounded px-2.5 py-1.5 transition-colors"
            >
              <LogOut size={13} />
              <span className="hidden sm:inline">Sair</span>
            </button>
            <button
              onClick={() => setMobileOpen((v) => !v)}
              className="md:hidden p-1.5 text-gray-500 hover:text-gray-800"
              aria-label="Menu"
            >
              {mobileOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </header>

        {/* Mobile nav dropdown */}
        {mobileOpen && (
          <div className="md:hidden bg-white border-b border-gray-200 px-4 py-3 space-y-1 z-20">
            <p className="text-xs text-gray-400 mb-2 px-2">{clientName}</p>
            {NAV.map(({ href, label, icon: Icon }) => (
              <Link
                key={href}
                href={href}
                onClick={() => setMobileOpen(false)}
                className={`flex items-center gap-2 px-3 py-2 rounded text-sm font-medium transition-colors ${
                  pathname === href || pathname.startsWith(href + "/")
                    ? "bg-[#B8954A]/10 text-[#B8954A]"
                    : "text-gray-600 hover:bg-gray-100"
                }`}
              >
                <Icon size={15} />
                {label}
              </Link>
            ))}
          </div>
        )}

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
