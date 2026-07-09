"use client";
import { useState, useEffect, useCallback } from "react";
import { Coins, RefreshCw, Bot, Zap, Users, Wrench } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";

interface UsuarioCusto {
  user_id: string;
  nome: string;
  email: string;
  execucoes: number;
  tokens: number;
  custo_usd: number;
  limite_usd: number | null;
  pct_limite: number | null;
}

interface CustosData {
  periodo_dias: number;
  total_execucoes: number;
  total_tokens: number;
  total_custo_usd: number;
  usuarios: UsuarioCusto[];
}

const PERIODOS = [7, 30, 90];

export default function CustosIAPage() {
  const [data, setData] = useState<CustosData | null>(null);
  const [dias, setDias] = useState(30);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [editandoLimite, setEditandoLimite] = useState<string | null>(null);
  const [novoLimite, setNovoLimite] = useState("");
  const [salvandoLimite, setSalvandoLimite] = useState(false);

  const fetchCustos = useCallback(async () => {
    setLoading(true);
    setErro(null);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/system/ai-costs?dias=${dias}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setData(await res.json());
      else {
        const d = await res.json().catch(() => ({}));
        setErro(d.detail || "Erro ao carregar custos.");
      }
    } catch {
      setErro("Falha de conexão.");
    } finally {
      setLoading(false);
    }
  }, [dias]);

  useEffect(() => { fetchCustos(); }, [fetchCustos]);

  async function salvarLimite(userId: string) {
    setSalvandoLimite(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const valor = parseFloat(novoLimite.replace(",", "."));
      const res = await fetch("/api/v1/system/ai-budgets", {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          user_id: userId,
          monthly_limit_usd: isNaN(valor) || valor <= 0 ? null : valor,
        }),
      });
      if (res.ok) { setEditandoLimite(null); setNovoLimite(""); fetchCustos(); }
      else {
        const d = await res.json().catch(() => ({}));
        setErro(d.detail || "Erro ao salvar limite.");
      }
    } catch { setErro("Falha de conexão."); }
    finally { setSalvandoLimite(false); }
  }

  const fmtUsd = (v: number) => `$ ${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 4 })}`;
  const fmtInt = (v: number) => v.toLocaleString("pt-BR");

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Custos de IA" }]} />

      <div className="afj-page-header">
        <div>
          <h1 className="afj-page-title flex items-center gap-2">
            <Coins size={20} className="text-afj-gold" /> Custos de IA por Usuário
          </h1>
          <p className="text-afj-black/45 text-sm mt-1">
            Consumo de tokens e custo das execuções de agentes, por advogado — isolado ao seu escritório.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {PERIODOS.map((p) => (
            <button key={p} onClick={() => setDias(p)}
              className={`text-xs px-3 py-1.5 rounded-sm border transition-colors ${
                dias === p ? "bg-afj-gold text-white border-afj-gold" : "bg-white text-afj-black/60 border-afj-cream-dark hover:border-afj-gold/50"
              }`}>
              {p} dias
            </button>
          ))}
          <button onClick={fetchCustos} className="btn-afj-outline rounded-sm p-2" title="Atualizar" aria-label="Atualizar">
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {erro && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-sm px-4 py-3 text-sm">{erro}</div>
      )}

      {/* KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {[
          { icon: Coins, label: "Custo total (USD)", value: data ? fmtUsd(data.total_custo_usd) : "—" },
          { icon: Zap, label: "Tokens consumidos", value: data ? fmtInt(data.total_tokens) : "—" },
          { icon: Bot, label: "Execuções de agentes", value: data ? fmtInt(data.total_execucoes) : "—" },
        ].map((k) => {
          const Icon = k.icon;
          return (
            <div key={k.label} className="afj-stat-card">
              <div className="flex items-center gap-2 text-afj-black/45 text-xs mb-1">
                <Icon size={13} className="text-afj-gold" /> {k.label}
              </div>
              <p className="text-2xl font-bold text-afj-black font-display">{k.value}</p>
            </div>
          );
        })}
      </div>

      {/* Tabela por usuário */}
      {loading && !data ? (
        <div className="afj-card p-4 space-y-3">
          {Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-10 bg-afj-cream-dark rounded animate-pulse" />)}
        </div>
      ) : data && data.usuarios.length > 0 ? (
        <div className="afj-card overflow-x-auto">
          <table className="afj-table w-full">
            <thead>
              <tr>
                <th className="text-left">Usuário</th>
                <th className="text-right">Execuções</th>
                <th className="text-right">Tokens</th>
                <th className="text-right">Custo (USD)</th>
                <th className="text-right">Limite mensal</th>
              </tr>
            </thead>
            <tbody>
              {data.usuarios.map((u) => (
                <tr key={u.user_id}>
                  <td>
                    <p className="font-medium text-afj-black text-sm">{u.nome}</p>
                    <p className="text-xs text-afj-black/40">{u.email}</p>
                    {u.limite_usd != null && u.pct_limite != null && (
                      <div className="mt-1.5 max-w-[180px]">
                        <div className="h-1.5 bg-afj-cream-dark rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all ${
                              u.pct_limite >= 100 ? "bg-red-500" : u.pct_limite >= 80 ? "bg-amber-500" : "bg-green-500"
                            }`}
                            style={{ width: `${Math.min(u.pct_limite, 100)}%` }}
                          />
                        </div>
                        <p className={`text-[10px] mt-0.5 ${
                          u.pct_limite >= 100 ? "text-red-600 font-semibold" : u.pct_limite >= 80 ? "text-amber-600" : "text-afj-black/40"
                        }`}>
                          {u.pct_limite >= 100 ? "Limite atingido — execuções bloqueadas" : `${u.pct_limite.toFixed(0)}% do limite usado`}
                        </p>
                      </div>
                    )}
                  </td>
                  <td className="text-right text-sm">{fmtInt(u.execucoes)}</td>
                  <td className="text-right text-sm">{fmtInt(u.tokens)}</td>
                  <td className="text-right text-sm font-semibold text-afj-gold">{fmtUsd(u.custo_usd)}</td>
                  <td className="text-right text-sm">
                    {editandoLimite === u.user_id ? (
                      <span className="inline-flex items-center gap-1.5">
                        <input
                          value={novoLimite}
                          onChange={(e) => setNovoLimite(e.target.value)}
                          placeholder="ex.: 50.00"
                          autoFocus
                          className="w-24 border border-afj-cream-dark rounded-sm px-2 py-1 text-xs text-right focus:outline-none focus:border-afj-gold"
                        />
                        <button onClick={() => salvarLimite(u.user_id)} disabled={salvandoLimite}
                          className="text-[11px] text-afj-gold font-semibold hover:underline disabled:opacity-40">
                          Salvar
                        </button>
                        <button onClick={() => { setEditandoLimite(null); setNovoLimite(""); }}
                          className="text-[11px] text-afj-black/40 hover:underline">
                          Cancelar
                        </button>
                      </span>
                    ) : (
                      <button
                        onClick={() => { setEditandoLimite(u.user_id); setNovoLimite(u.limite_usd != null ? String(u.limite_usd) : ""); }}
                        className="text-sm hover:text-afj-gold transition-colors"
                        title="Clique para definir/alterar o limite (vazio remove)"
                      >
                        {u.limite_usd != null ? fmtUsd(u.limite_usd) : <span className="text-afj-black/30">definir</span>}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="afj-card p-12 text-center">
          <Users size={36} className="mx-auto text-afj-black/20 mb-3" />
          <p className="font-semibold text-afj-black">Sem execuções no período</p>
          <p className="text-afj-black/40 text-sm mt-1">Os custos aparecem aqui conforme os agentes são utilizados.</p>
        </div>
      )}

      <div className="flex items-start gap-2 text-xs text-afj-black/50 bg-afj-cream/60 border border-afj-cream-dark rounded-sm p-3">
        <Wrench size={14} className="text-afj-gold flex-shrink-0 mt-0.5" />
        <span>
          <strong className="text-afj-black/70">Como funciona:</strong> clique no valor da coluna “Limite mensal” para
          definir o teto de cada usuário (vazio remove). Ao atingir 80% do teto, o usuário recebe um alerta; ao chegar
          a 100%, novas execuções de agentes são bloqueadas até o ajuste do limite ou a virada do mês. Custos de chaves
          próprias (BYOK) são pagos diretamente pelo usuário ao provedor e aparecem aqui como estimativa.
        </span>
      </div>
    </div>
  );
}
