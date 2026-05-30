"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Scale, CalendarClock, CheckSquare, Bot } from "lucide-react";

const ITEMS = [
  { href: "/dashboard", icon: LayoutDashboard, label: "Início" },
  { href: "/processos", icon: Scale, label: "Processos" },
  { href: "/agenda", icon: CalendarClock, label: "Agenda" },
  { href: "/aprovacoes", icon: CheckSquare, label: "Aprovações", showBadge: true },
  { href: "/agentes", icon: Bot, label: "Agentes" },
];

interface BottomNavProps {
  approvalCount?: number;
}

export function BottomNav({ approvalCount = 0 }: BottomNavProps) {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Navegação rápida mobile"
      className="fixed bottom-0 inset-x-0 h-16 md:hidden bg-white/95 backdrop-blur-md border-t border-afj-cream-dark flex z-20 safe-area-inset-bottom"
    >
      {ITEMS.map(({ href, icon: Icon, label, showBadge }) => {
        const isActive = pathname === href || pathname.startsWith(href + "/");
        return (
          <Link
            key={href}
            href={href}
            className={`relative flex-1 flex flex-col items-center justify-center gap-0.5 min-h-[44px] transition-colors ${
              isActive ? "text-afj-gold" : "text-afj-black/40 hover:text-afj-black/60"
            }`}
          >
            {isActive && (
              <span className="absolute top-0 left-1/2 -translate-x-1/2 w-6 h-0.5 bg-afj-gold rounded-full" />
            )}
            <div className="relative">
              <Icon size={20} />
              {showBadge && approvalCount > 0 && (
                <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-red-500 text-white text-[9px] font-bold flex items-center justify-center leading-none">
                  {approvalCount > 9 ? "9+" : approvalCount}
                </span>
              )}
            </div>
            <span className={`text-[10px] font-medium leading-none ${isActive ? "text-afj-gold" : "text-afj-black/40"}`}>
              {label}
            </span>
          </Link>
        );
      })}
    </nav>
  );
}
