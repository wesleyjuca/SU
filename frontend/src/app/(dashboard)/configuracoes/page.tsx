"use client";
import { useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { useUserStore } from "@/store";
import { PersonalZone } from "@/components/configuracoes/PersonalZone";
import { EscritorioZone } from "@/components/configuracoes/EscritorioZone";

type Zona = "pessoal" | "admin";

/** Fase 224 — Configurações fundida: antes 3 páginas separadas
 * (`/configuracoes`, `/admin/personalizacao`, `/admin/juridico`), agora um
 * único ponto de entrada com 2 zonas internas. "Pessoal" (Perfil/
 * Notificações/Segurança) é aberta a todo mundo, como sempre foi. "Escritório
 * & Jurídico" (as 8 abas de Personalização + a nova aba Jurídico) só aparece
 * pra ADMIN/SUPERADMIN — mesmo espírito de `admin/layout.tsx`/`admin/cerebro`,
 * mas gateando só uma zona interna, não a rota inteira (todo mundo continua
 * acessando /configuracoes). Mesmo padrão de estado de aba do Cérebro
 * (`?zona=`/localStorage), aplicado aqui uma camada acima (zona) além da
 * camada de aba que já existe dentro de cada zona. */
export default function ConfiguracoesPage() {
  const searchParams = useSearchParams();
  const user = useUserStore((s) => s.user);
  const isAdmin = user?.role === "ADMIN" || user?.role === "SUPERADMIN";
  const [zona, setZona] = useState<Zona>("pessoal");

  useEffect(() => {
    const daUrl = searchParams.get("zona");
    if (daUrl === "admin" || daUrl === "pessoal") {
      setZona(daUrl);
      return;
    }
    const salva = typeof window !== "undefined" ? localStorage.getItem("afj_configuracoes_zona") : null;
    if (salva === "admin" || salva === "pessoal") setZona(salva);
  }, [searchParams]);

  // Defesa: sessão trocou de papel, ou link antigo apontando pra zona admin
  // — nunca deixa a zona restrita "vazar" pra quem não é admin.
  useEffect(() => {
    if (zona === "admin" && !isAdmin) setZona("pessoal");
  }, [zona, isAdmin]);

  function trocarZona(z: Zona) {
    setZona(z);
    try { localStorage.setItem("afj_configuracoes_zona", z); } catch { /* noop */ }
  }

  return (
    <div className="max-w-6xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Configurações" }]} />
      <div>
        <h1 className="font-display text-2xl font-semibold text-afj-black">Configurações</h1>
        <p className="text-afj-black/50 text-sm">Gerencie seu perfil, notificações, e — se for admin — a identidade e os parâmetros do escritório</p>
      </div>

      <div role="tablist" aria-label="Zonas de Configurações" className="flex gap-1 bg-afj-cream border border-afj-cream-dark rounded-sm p-1 w-fit">
        <button
          onClick={() => trocarZona("pessoal")}
          className={`px-4 py-2 rounded-sm text-xs font-semibold uppercase tracking-wider transition-colors ${
            zona === "pessoal" ? "bg-white text-afj-black shadow-sm" : "text-afj-black/45 hover:text-afj-black"
          }`}
        >
          Pessoal
        </button>
        {isAdmin && (
          <button
            onClick={() => trocarZona("admin")}
            className={`px-4 py-2 rounded-sm text-xs font-semibold uppercase tracking-wider transition-colors ${
              zona === "admin" ? "bg-white text-afj-black shadow-sm" : "text-afj-black/45 hover:text-afj-black"
            }`}
          >
            Escritório &amp; Jurídico
          </button>
        )}
      </div>

      {zona === "admin" && isAdmin ? <EscritorioZone /> : <PersonalZone />}
    </div>
  );
}
