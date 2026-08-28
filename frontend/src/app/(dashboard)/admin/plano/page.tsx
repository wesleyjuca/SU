"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { Gauge, Users2, HardDrive, Coins, Bot, RefreshCw, Crown, Receipt, Building2, Plus, Loader2, KeyRound, History } from "lucide-react";
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
  const ilimitado = limite <= 0;
  const pct = !ilimitado ? Math.min((atual / limite) * 100, 100) : 0;
  return (
    <div className="afj-card p-5">
      <div className="flex items-center justify-between mb-2">
        <p className="text-sm font-semibold text-afj-black flex items-center gap-2">
          <Icon size={15} className="text-afj-gold" /> {label}
        </p>
        <p className="text-xs text-afj-black/50">
          <span className="font-semibold text-afj-black">{atual.toLocaleString("pt-BR")}</span> / {ilimitado ? "Ilimitado" : `${limite.toLocaleString("pt-BR")} ${unidade}`}
        </p>
      </div>
      <div className="h-2.5 bg-afj-cream-dark rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${ilimitado ? "bg-afj-gold/40" : barColor(pct)}`} style={{ width: ilimitado ? "100%" : `${pct}%` }} />
      </div>
      <p className={`text-[11px] mt-1.5 ${!ilimitado && pct >= 90 ? "text-red-600 font-semibold" : !ilimitado && pct >= 70 ? "text-amber-600" : "text-afj-black/40"}`}>
        {ilimitado ? "Sem limite no seu plano" : `${pct.toFixed(0)}% do limite do plano${pct >= 90 ? " — considere ampliar o plano" : ""}`}
      </p>
    </div>
  );
}

interface Unit { id: string; name: string; unit_label: string | null; is_active: boolean; users: number }
interface UnitsData { plano_permite_filiais: boolean; units: Unit[] }
// Fase 245 (achado do diagnóstico de cadastros) — antes o escritório só via
// o status ATUAL da assinatura ("Assinatura & Cobrança" acima), sem nenhum
// histórico do que já foi pago (isso só existia numa tela SUPERADMIN-only,
// de gestão de TODOS os escritórios).
interface Pagamento { id: string; valor: number; competencia: string; pago_em: string | null; metodo: string; observacao: string | null }

export default function PlanoUsoPage() {
  const [data, setData] = useState<Usage | null>(null);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [unitsData, setUnitsData] = useState<UnitsData | null>(null);
  const [novaUnidade, setNovaUnidade] = useState(false);
  const [unitForm, setUnitForm] = useState({ name: "", unit_label: "", admin_email: "", admin_name: "" });
  const [criandoUnidade, setCriandoUnidade] = useState(false);
  const [credenciais, setCredenciais] = useState<{ admin_email: string; temp_password: string; name: string } | null>(null);
  const [pagamentos, setPagamentos] = useState<Pagamento[] | null>(null);

  async function fetchPagamentos() {
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/tenant/billing/historico", { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) setPagamentos(await res.json());
    } catch { /* seção opcional — silencioso, ADVOGADO/GESTOR recebem 403 aqui */ }
  }

  async function fetchUnits() {
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/tenant/units", { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) setUnitsData(await res.json());
    } catch { /* seção opcional — silencioso */ }
  }

  async function criarUnidade() {
    if (!unitForm.name || !unitForm.unit_label || !unitForm.admin_email || !unitForm.admin_name) return;
    setCriandoUnidade(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/tenant/units", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(unitForm),
      });
      const d = await res.json().catch(() => ({}));
      if (res.ok) {
        setCredenciais({ admin_email: d.admin_email, temp_password: d.temp_password, name: d.name });
        setNovaUnidade(false);
        setUnitForm({ name: "", unit_label: "", admin_email: "", admin_name: "" });
        fetchUnits();
      } else {
        setErro(d.detail || "Erro ao criar a unidade.");
      }
    } catch { setErro("Falha de conexão ao criar a unidade."); }
    finally { setCriandoUnidade(false); }
  }

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

  useEffect(() => { fetchUsage(); fetchUnits(); fetchPagamentos(); }, []);

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

          {/* Histórico de faturamento — Fase 245 */}
          {pagamentos && pagamentos.length > 0 && (
            <div className="afj-card p-5">
              <p className="text-sm font-semibold text-afj-black flex items-center gap-2 mb-3">
                <History size={15} className="text-afj-gold" /> Histórico de faturamento
              </p>
              <div className="overflow-x-auto">
                <table className="afj-table">
                  <thead>
                    <tr><th>Competência</th><th>Valor</th><th>Pago em</th><th>Método</th></tr>
                  </thead>
                  <tbody>
                    {pagamentos.map((p) => (
                      <tr key={p.id}>
                        <td>{p.competencia}</td>
                        <td>R$ {p.valor.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}</td>
                        <td>{p.pago_em ? new Date(p.pago_em).toLocaleDateString("pt-BR") : "—"}</td>
                        <td className="text-afj-black/60 text-xs">{p.metodo}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

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

          {/* Minhas unidades (filiais) */}
          {unitsData && (
            <div className="afj-card p-5">
              <div className="flex items-center justify-between flex-wrap gap-2 mb-1">
                <p className="text-sm font-semibold text-afj-black flex items-center gap-2">
                  <Building2 size={15} className="text-afj-gold" /> Minhas unidades (filiais)
                </p>
                {unitsData.plano_permite_filiais && (
                  <button onClick={() => { setNovaUnidade(!novaUnidade); setCredenciais(null); }}
                    className="btn-afj-outline rounded-sm py-1.5 px-3 text-xs flex items-center gap-1.5">
                    <Plus size={13} /> Nova unidade
                  </button>
                )}
              </div>
              <p className="text-xs text-afj-black/45 mb-3">
                Cada filial é um ambiente isolado da banca, com seus próprios usuários e dados.
                {!unitsData.plano_permite_filiais && " Disponível no plano ENTERPRISE — fale com a plataforma para upgrade."}
              </p>

              {credenciais && (
                <div className="bg-amber-50 border border-amber-200 rounded-sm px-4 py-3 mb-3 text-sm">
                  <p className="font-semibold text-amber-800 flex items-center gap-1.5"><KeyRound size={14} /> Unidade “{credenciais.name}” criada</p>
                  <p className="text-amber-700 text-xs mt-1">
                    Admin: <span className="font-mono">{credenciais.admin_email}</span> · Senha temporária:{" "}
                    <span className="font-mono font-bold">{credenciais.temp_password}</span>
                  </p>
                  <p className="text-amber-600 text-[11px] mt-1">Anote agora — a senha não será exibida novamente.</p>
                </div>
              )}

              {novaUnidade && (
                <div className="border border-afj-cream-dark rounded-sm p-4 mb-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {[
                    { k: "name", label: "Nome da unidade", ph: "Ex.: AFJ Advogados — Fortaleza" },
                    { k: "unit_label", label: "Identificação (cidade/região)", ph: "Ex.: Fortaleza/CE" },
                    { k: "admin_name", label: "Nome do administrador", ph: "Ex.: Maria Freire" },
                    { k: "admin_email", label: "E-mail do administrador", ph: "admin@filial.com.br" },
                  ].map((f) => (
                    <div key={f.k}>
                      <label className="text-[11px] text-afj-black/50 block mb-0.5">{f.label}</label>
                      <input
                        value={unitForm[f.k as keyof typeof unitForm]}
                        onChange={(e) => setUnitForm({ ...unitForm, [f.k]: e.target.value })}
                        placeholder={f.ph}
                        type={f.k === "admin_email" ? "email" : "text"}
                        className="w-full border border-afj-cream-dark rounded-sm px-3 py-1.5 text-sm focus:outline-none focus:border-afj-gold"
                      />
                    </div>
                  ))}
                  <div className="sm:col-span-2 flex justify-end gap-2">
                    <button onClick={() => setNovaUnidade(false)} className="btn-afj-outline rounded-sm py-1.5 px-3 text-xs">Cancelar</button>
                    <button onClick={criarUnidade} disabled={criandoUnidade}
                      className="btn-afj-primary rounded-sm py-1.5 px-3 text-xs flex items-center gap-1.5 disabled:opacity-50">
                      {criandoUnidade ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />} Criar unidade
                    </button>
                  </div>
                </div>
              )}

              {unitsData.units.length === 0 ? (
                <p className="text-sm text-afj-black/40 text-center py-3">Nenhuma filial cadastrada.</p>
              ) : (
                <div className="divide-y divide-afj-cream-dark border border-afj-cream-dark rounded-sm">
                  {unitsData.units.map((u) => (
                    <div key={u.id} className="flex items-center justify-between px-3 py-2.5">
                      <div>
                        <p className="text-sm font-medium text-afj-black">{u.name}</p>
                        <p className="text-xs text-afj-black/45">{u.unit_label || "—"} · {u.users} usuário(s)</p>
                      </div>
                      <span className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-sm border ${u.is_active ? "bg-green-50 text-green-700 border-green-200" : "bg-gray-50 text-gray-500 border-gray-200"}`}>
                        {u.is_active ? "Ativa" : "Inativa"}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

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
