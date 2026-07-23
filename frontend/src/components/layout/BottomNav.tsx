"use client";
import Link from "next/link";
import { useState } from "react";
import { usePathname } from "next/navigation";
import { Menu, X } from "lucide-react";
import { useUserStore } from "@/store";
import { navForRole, flatNavForRole, MOBILE_PRIMARY_HREFS, type NavItem } from "@/lib/nav";

interface BottomNavProps {
  approvalCount?: number;
}

export function BottomNav({ approvalCount = 0 }: BottomNavProps) {
  const pathname = usePathname();
  const { user } = useUserStore();
  const [maisOpen, setMaisOpen] = useState(false);
  const role = user?.role;

  // Atalhos primários = os primeiros hrefs preferidos que ESTE papel pode ver
  // (antes a barra era fixa e mostrava itens proibidos ao papel — bug corrigido).
  const acessiveis = flatNavForRole(role);
  const porHref = new Map(acessiveis.map((i) => [i.href, i]));
  const primarios: NavItem[] = MOBILE_PRIMARY_HREFS
    .map((h) => porHref.get(h))
    .filter((i): i is NavItem => !!i)
    .slice(0, 4);

  const isActive = (href: string) => pathname === href || pathname.startsWith(href + "/");

  return (
    <>
      <nav
        aria-label="Navegação rápida mobile"
        className="fixed bottom-0 inset-x-0 h-16 md:hidden bg-white/95 backdrop-blur-md border-t border-afj-cream-dark flex z-20 safe-area-inset-bottom"
      >
        {primarios.map(({ href, icon: Icon, label }) => {
          const active = isActive(href);
          const showBadge = href === "/aprovacoes" && approvalCount > 0;
          return (
            <Link key={href} href={href}
              className={`relative flex-1 flex flex-col items-center justify-center gap-0.5 min-h-[44px] transition-colors ${
                active ? "text-afj-gold" : "text-afj-black/40 hover:text-afj-black/60"}`}>
              {active && <span className="absolute top-0 left-1/2 -translate-x-1/2 w-6 h-0.5 bg-afj-gold rounded-full" />}
              <div className="relative">
                <Icon size={20} />
                {showBadge && (
                  <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-red-500 text-white text-[9px] font-bold flex items-center justify-center leading-none">
                    {approvalCount > 9 ? "9+" : approvalCount}
                  </span>
                )}
              </div>
              <span className={`text-[10px] font-medium leading-none ${active ? "text-afj-gold" : "text-afj-black/40"}`}>{label}</span>
            </Link>
          );
        })}
        {/* "Mais" — abre uma folha com TODO o menu do papel (nada fica inacessível) */}
        <button onClick={() => setMaisOpen(true)}
          className="relative flex-1 flex flex-col items-center justify-center gap-0.5 min-h-[44px] text-afj-black/40 hover:text-afj-black/60 transition-colors"
          aria-label="Mais opções do menu">
          <Menu size={20} />
          <span className="text-[10px] font-medium leading-none">Mais</span>
        </button>
      </nav>

      {/* Bottom-sheet com o menu completo (filtrado por papel) */}
      {maisOpen && (
        <div className="fixed inset-0 z-40 md:hidden" role="dialog" aria-label="Menu completo">
          <div className="absolute inset-0 bg-black/50" onClick={() => setMaisOpen(false)} />
          <div className="absolute inset-x-0 bottom-0 max-h-[80vh] overflow-y-auto bg-white rounded-t-2xl safe-area-inset-bottom">
            <div className="sticky top-0 bg-white flex items-center justify-between px-4 py-3 border-b border-afj-cream-dark">
              <span className="font-semibold text-afj-black text-sm">Menu</span>
              <button onClick={() => setMaisOpen(false)} className="text-afj-black/40 hover:text-afj-black p-1" aria-label="Fechar"><X size={18} /></button>
            </div>
            <div className="p-2">
              {navForRole(role).map((section) => (
                <div key={section.title ?? "root"} className="mb-1">
                  {section.title && (
                    <p className="px-3 pt-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-afj-black/35">{section.title}</p>
                  )}
                  {section.items.map((item) => {
                    const active = isActive(item.href);
                    const Icon = item.icon;
                    return (
                      <Link key={item.href} href={item.href}
                        target={item.newTab ? "_blank" : undefined}
                        rel={item.newTab ? "noopener noreferrer" : undefined}
                        onClick={() => setMaisOpen(false)}
                        className={`flex items-center gap-3 px-3 py-2.5 rounded-sm text-sm ${
                          active ? "bg-afj-gold/10 text-afj-gold font-medium" : "text-afj-black/75 hover:bg-afj-cream/60"}`}>
                        <Icon size={16} className="flex-shrink-0" />
                        {item.label}
                      </Link>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
