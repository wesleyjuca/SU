"use client";
import { useState, useEffect, useCallback } from "react";
import { Building2, RefreshCw } from "lucide-react";
import { fetchBrain, type MetricasTenant } from "./types";

interface MetricasResp {
  ok: boolean;
  tenants: MetricasTenant[];
  totais?: { tenants: number; usuarios_ativos: number; processos: number; agent_runs_24h: number };
}

export function BrainMetrics() {
  const [data, setData] = useState<MetricasResp | null>(null);
  const [carregando, setCarregando] = useState(false);

  const carregar = useCallback(async () => {
    setCarregando(true);
    setData(await fetchBrain<MetricasResp>("metrics"));
    setCarregando(false);
  }, []);
  useEffect(() => { carregar(); }, [carregar]);

  const t = data?.totais;

  return (
    <div className="space-y-3">
      {t && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[
            { v: t.tenants, l: "Escritórios" },
            { v: t.usuarios_ativos, l: "Usuários ativos" },
            { v: t.processos, l: "Processos" },
            { v: t.agent_runs_24h, l: "Execuções (24h)" },
          ].map((c) => (
            <div key={c.l} className="afj-stat-card">
              <p className="text-2xl font-bold text-afj-black">{c.v}</p>
              <p className="text-xs text-afj-black/50 mt-0.5">{c.l}</p>
            </div>
          ))}
        </div>
      )}

      <div className="afj-card p-0 overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-afj-cream-dark">
          <h2 className="font-semibold text-afj-black text-sm flex items-center gap-2">
            <Building2 size={15} className="text-afj-gold" /> Métricas por escritório
          </h2>
          <button onClick={carregar} disabled={carregando}
            className="text-afj-black/40 hover:text-afj-black p-1 disabled:opacity-50" aria-label="Recarregar">
            <RefreshCw size={14} className={carregando ? "animate-spin" : ""} />
          </button>
        </div>
        {!data ? (
          <p className="p-6 text-center text-sm text-afj-black/40">Carregando…</p>
        ) : (data.tenants?.length ?? 0) === 0 ? (
          <p className="p-6 text-center text-sm text-afj-black/40">Sem escritórios para exibir.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="afj-table w-full text-xs">
              <thead>
                <tr>
                  <th className="text-left">Escritório</th>
                  <th className="text-left">Plano</th>
                  <th className="text-right">Usuários</th>
                  <th className="text-right">Processos</th>
                  <th className="text-right">Exec. 24h</th>
                  <th className="text-right">Syncs</th>
                  <th className="text-left">Última atividade</th>
                </tr>
              </thead>
              <tbody>
                {data.tenants.map((r) => (
                  <tr key={r.tenant_id} className={r.ativo ? "" : "opacity-50"}>
                    <td className="font-medium text-afj-black">{r.nome}</td>
                    <td className="text-afj-black/50">{r.plano ?? "—"}</td>
                    <td className="text-right">{r.usuarios_ativos}</td>
                    <td className="text-right font-medium">{r.processos}</td>
                    <td className="text-right">{r.agent_runs_24h}</td>
                    <td className="text-right">{r.sync_runs}</td>
                    <td className="text-afj-black/50 whitespace-nowrap">
                      {r.ultima_atividade ? new Date(r.ultima_atividade).toLocaleDateString("pt-BR") : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="px-4 py-2 text-[11px] text-afj-black/35 border-t border-afj-cream-dark">
          Visão de plataforma (todas as tenants) — exclusiva do SuperAdmin.
        </p>
      </div>
    </div>
  );
}
