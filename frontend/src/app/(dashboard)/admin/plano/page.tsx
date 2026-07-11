"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { Gauge, Users2, HardDrive, Coins, Bot, RefreshCw, Crown, Receipt } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";

interface BillingInfo {
  status: string;
  valor_mensal: number | null;
  proximo_vencimento: string | null;
  dias_para_vencimento: number | null;
}

interface Usage {
  plan: string;
  tenant_name: string;
  max_users: number;
  usuarios_ativos: number;
  max_storage_gb: number;
  storage_mb_estimado: number;
  custo_ia_mes_usd: number;
  tokens_mes: number;
  execucoes_mes: number;
  billing?: BillingInfo;
}

const BILLING_STYLE: Record<string, { cls: string; label: string }> = {
  ATIVO: { cls: "border-green-500", label: "Em dia" },
  INADIMPLENTE: { cls: "border-amber-500", label: "Mensalidade vencida" },
  SUSPENSO: { cls: "border-red-500", label: "Suspenso — escrita bloqueada" },
  ISENTO: { cls: "border-afj-gold", label: "Isento" },
  NAO_CONFIGURADO: { cls: "border-afj-cream-dark", label: "Sem cobrança configurada" },
};

function barColor(pct: number): string {
  if (pct >= 90) return "bg-red-500";
  if (pct >= 70) return "bg-amber-500";
  return "bg-green-500";
}

function UsageBar({ label, icon: Icon, atual, limite, unidade }: {
  label: string; icon: React.ElementType; atual: number; limite: number; unidade: string;
}) {
  const pct = limite > 0 ? Math.min((atual / limite) * 100, 100) : 0;
  return (
    <div className="afj-card p-5">
      <div className="flex items-center justify-between mb-2">
        <p className="text-sm font-semibold text-afj-black flex items-center gap-2">
          <Icon size={15} className="text-afj-gold" /> {label}
        </p>
        <p className="text-xs text-afj-black/50">
          <span className="font-semibold text-afj-black">{atual.toLocaleString("pt-BR")}</span> / {limite.toLocaleString("pt-BR")} {unidade}
        </p>
      </div>
      <div className="h-2.5 bg-afj-cream-dark rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${barColor(pct)}`} style={{ width: `${pct}%` }} />
      </div>
      <p className={`text-[11px] mt-1.5 ${pct >= 90 ? "text-red-600 font-semibold" : pct >= 70 ? "text-amber-600" : "text-afj-black/40"}`}>
        {pct.toFixed(0)}% do limite do plano{pct >= 90 ? " — considere ampliar o plano" : ""}
      </p>
    </div>
  );
}

export default function PlanoUsoPage() {
  const [data, setData] = useState<Usage | null>(null);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  async function fetchUsage() {
    setLoading(true);
    setErro(null);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/tenant/usage", { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) setData(await res.json());
      else {
        const d = await res.json().catch(() => ({}));
        setErro(d.detail || "Erro ao carregar o uso do plano.");
      }
    } catch { setErro("Falha de conexão."); }
    finally { setLoading(false); }
  }

  useEffect(() => { fetchUsage(); }, []);

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Plano & Uso" }]} />

      <div className="afj-page-header">
        <div>
          <h1 className="afj-page-title flex items-center gap-2">
            <Gauge size={20} className="text-afj-gold" /> Plano & Uso
          </h1>
          <p className="text-afj-black/45 text-sm mt-1">
            Limites do plano do escritório e consumo real — usuários, armazenamento e IA.
          </p>
        </div>
        <button onClick={fetchUsage} className="btn-afj-outline rounded-sm p-2" title="Atualizar" aria-label="Atualizar">
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {erro && <div className="bg-red-50 border border-red-200 text-red-700 rounded-sm px-4 py-3 text-sm">{erro}</div>}

      {loading && !data ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-24 bg-afj-cream-dark rounded animate-pulse" />)}
        </div>
      ) : data ? (
        <>
          {/* Plano atual */}
          <div className="afj-card p-5 flex items-center gap-4 border-l-4 border-afj-gold">
            <Crown size={26} className="text-afj-gold flex-shrink-0" />
            <div className="flex-1">
              <p className="text-lg font-bold text-afj-black font-display">Plano {data.plan}</p>
              <p className="text-xs text-afj-black/45">{data.tenant_name}</p>
            </div>
            <div className="text-right text-xs text-afj-black/50">
              <p>Para alterar o plano ou limites,</p>
              <p>contate o suporte da plataforma.</p>
            </div>
          </div>

          {/* Assinatura & Cobrança */}
          {data.billing && (() => {
            const st = BILLING_STYLE[data.billing.status] || BILLING_STYLE.NAO_CONFIGURADO;
            const venc = data.billing.proximo_vencimento
              ? new Date(data.billing.proximo_vencimento + "T00:00:00").toLocaleDateString("pt-BR")
              : "—";
            return (
              <div className={`afj-card p-5 border-l-4 ${st.cls}`}>
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <p className="text-sm font-semibold text-afj-black flex items-center gap-2">
                    <Receipt size={15} className="text-afj-gold" /> Assinatura & Cobrança
                  </p>
                  <span className="text-xs font-medium text-afj-black/70">{st.label}</span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-3 text-sm">
                  <div>
                    <p className="text-[11px] text-afj-black/40">Mensalidade</p>
                    <p className="font-semibold text-afj-black">
                      {data.billing.valor_mensal != null ? `R$ ${data.billing.valor_mensal.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}` : "—"}
                    </p>
                  </div>
                  <div>
                    <p className="text-[11px] text-afj-black/40">Próximo vencimento</p>
                    <p className="font-semibold text-afj-black">{venc}</p>
                  </div>
                  <div>
                    <p className="text-[11px] text-afj-black/40">Situação</p>
                    <p className="font-semibold text-afj-black">{st.label}</p>
                  </div>
                </div>
              </div>
            );
          })()}

          {/* Barras de uso */}
          <div className="grid grid-cols-1 gap-4">
            <UsageBar label="Usuários ativos" icon={Users2} atual={data.usuarios_ativos} limite={data.max_users} unidade="usuários" />
            <UsageBar label="Armazenamento (documentos no sistema)" icon={HardDrive}
              atual={Math.round(data.storage_mb_estimado)} limite={data.max_storage_gb * 1024} unidade="MB" />
          </div>

          {/* IA do mês */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {[
              { icon: Coins, label: "Custo de IA no mês", value: `$ ${data.custo_ia_mes_usd.toLocaleString("en-US", { minimumFractionDigits: 2 })}` },
              { icon: Bot, label: "Execuções de agentes no mês", value: data.execucoes_mes.toLocaleString("pt-BR") },
              { icon: Gauge, label: "Tokens no mês", value: data.tokens_mes.toLocaleString("pt-BR") },
            ].map((k) => {
              const Icon = k.icon;
              return (
                <div key={k.label} className="afj-stat-card">
                  <div className="flex items-center gap-2 text-afj-black/45 text-xs mb-1">
                    <Icon size={13} className="text-afj-gold" /> {k.label}
                  </div>
                  <p className="text-xl font-bold text-afj-black font-display">{k.value}</p>
                </div>
              );
            })}
          </div>

          <p className="text-[11px] text-afj-black/35 text-center">
            Detalhe do consumo de IA por usuário em{" "}
            <Link href="/custos-ia" className="text-afj-gold hover:underline">Custos de IA</Link>.
            Armazenamento é uma estimativa do conteúdo guardado no banco (arquivos e textos).
          </p>
        </>
      ) : null}
    </div>
  );
}
