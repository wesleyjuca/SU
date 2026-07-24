"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Brain, Network, Cpu, ShieldCheck, Sparkles, Building2, ScrollText } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { BrainMap } from "@/components/cerebro/BrainMap";
import { BrainInfra } from "@/components/cerebro/BrainInfra";
import { BrainAudit } from "@/components/cerebro/BrainAudit";
import { BrainAssistant } from "@/components/cerebro/BrainAssistant";
import { BrainMetrics } from "@/components/cerebro/BrainMetrics";
import { BrainLogs } from "@/components/cerebro/BrainLogs";
import { useUserStore } from "@/store";

type AbaKey = "mapa" | "infra" | "plataforma" | "logs" | "auditoria" | "assistente";
const ABAS: { key: AbaKey; label: string; icon: React.ElementType }[] = [
  { key: "mapa", label: "Mapa", icon: Network },
  { key: "infra", label: "Infraestrutura", icon: Cpu },
  { key: "plataforma", label: "Plataforma", icon: Building2 },
  { key: "logs", label: "Logs", icon: ScrollText },
  { key: "auditoria", label: "Auditoria", icon: ShieldCheck },
  { key: "assistente", label: "Assistente", icon: Sparkles },
];

export default function CerebroPage() {
  const router = useRouter();
  const user = useUserStore((s) => s.user);
  const [aba, setAba] = useState<AbaKey>("mapa");

  // Cérebro é EXCLUSIVO do SUPERADMIN (o admin/layout já barra não-admin; aqui
  // barramos ADMIN também — só SUPERADMIN entra).
  useEffect(() => {
    if (user && user.role !== "SUPERADMIN") router.replace("/dashboard");
  }, [user, router]);

  // Restaura a última aba escolhida.
  useEffect(() => {
    const salva = typeof window !== "undefined" ? localStorage.getItem("cerebro_aba") : null;
    if (salva && ABAS.some((a) => a.key === salva)) setAba(salva as AbaKey);
  }, []);
  const trocarAba = (k: AbaKey) => { setAba(k); try { localStorage.setItem("cerebro_aba", k); } catch { /* noop */ } };

  if (user && user.role !== "SUPERADMIN") return null;

  return (
    <div className="space-y-4">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Cérebro" }]} />
      <div className="afj-page-header">
        <div>
          <h1 className="afj-page-title flex items-center gap-2">
            <Brain size={20} className="text-afj-gold" /> Cérebro do Sistema
          </h1>
          <p className="text-afj-black/45 text-sm mt-1">
            Mapa vivo, infraestrutura, auditoria e assistente — exclusivo do SuperAdmin.
          </p>
        </div>
      </div>

      {/* Barra de abas */}
      <div role="tablist" aria-label="Seções do Cérebro" className="flex flex-wrap gap-1 border-b border-afj-cream-dark">
        {ABAS.map(({ key, label, icon: Icon }) => {
          const ativa = aba === key;
          return (
            <button
              key={key} role="tab" aria-selected={ativa}
              onClick={() => trocarAba(key)}
              className={`flex items-center gap-1.5 px-3.5 py-2 text-sm font-medium rounded-t-sm -mb-px border-b-2 transition-colors ${
                ativa
                  ? "border-afj-gold text-afj-black bg-afj-gold/5"
                  : "border-transparent text-afj-black/45 hover:text-afj-black hover:bg-afj-cream/50"}`}
            >
              <Icon size={15} className={ativa ? "text-afj-gold" : ""} /> {label}
            </button>
          );
        })}
      </div>

      {/* Conteúdo da aba ativa (só a ativa monta/atualiza) */}
      <div>
        {aba === "mapa" && <BrainMap />}
        {aba === "infra" && <BrainInfra />}
        {aba === "plataforma" && <BrainMetrics />}
        {aba === "logs" && <BrainLogs />}
        {aba === "auditoria" && <BrainAudit />}
        {aba === "assistente" && <BrainAssistant />}
      </div>
    </div>
  );
}
