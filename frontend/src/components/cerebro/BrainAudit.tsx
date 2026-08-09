"use client";
import { useState, useEffect, useCallback, useMemo } from "react";
import { ShieldCheck, RefreshCw, CheckCircle2, XCircle, Search, AlertTriangle } from "lucide-react";
import { fetchBrain, type AuditEvento, type TenantResumo } from "./types";

interface AuditResp { ok: boolean; total: number; limit: number; offset: number; eventos: AuditEvento[] }

const PAGE_SIZE = 100;

export function BrainAudit() {
  const [eventos, setEventos] = useState<AuditEvento[] | null>(null);
  const [totalGeral, setTotalGeral] = useState(0);
  const [carregando, setCarregando] = useState(false);
  const [carregandoMais, setCarregandoMais] = useState(false);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [busca, setBusca] = useState("");
  const [filtroSucesso, setFiltroSucesso] = useState("");
  const [filtroTenant, setFiltroTenant] = useState("");
  const [tenants, setTenants] = useState<TenantResumo[]>([]);

  // Fase 162 — GET /brain/audit ganhou offset/tenant_id/success server-side
  // (antes só devolvia os últimos 300 eventos da PLATAFORMA INTEIRA, sem
  // forma de buscar um tenant/período específico).
  const carregar = useCallback(async (novoOffset = 0, append = false) => {
    if (append) setCarregandoMais(true); else setCarregando(true);
    const params = new URLSearchParams();
    params.set("limit", String(PAGE_SIZE));
    params.set("offset", String(novoOffset));
    if (filtroSucesso) params.set("success", filtroSucesso);
    if (filtroTenant) params.set("tenant_id", filtroTenant);
    const r = await fetchBrain<AuditResp>(`audit?${params}`);
    const novos = r?.eventos ?? [];
    setEventos((prev) => (append && prev ? [...prev, ...novos] : novos));
    setTotalGeral(r?.total ?? 0);
    setHasMore(novos.length === PAGE_SIZE);
    setOffset(novoOffset + novos.length);
    if (append) setCarregandoMais(false); else setCarregando(false);
  }, [filtroSucesso, filtroTenant]);

  useEffect(() => { carregar(0, false); }, [carregar]);

  useEffect(() => {
    const token = typeof window !== "undefined" ? localStorage.getItem("afj_access_token") : null;
    if (!token) return;
    fetch("/api/v1/tenants", { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.json() : []))
      .then((d) => setTenants(Array.isArray(d) ? d : []))
      .catch(() => {});
  }, []);

  const filtrados = useMemo(() => (eventos ?? []).filter((e) => {
    const q = busca.toLowerCase();
    return !q ||
      e.action.toLowerCase().includes(q) ||
      e.resource_type?.toLowerCase().includes(q) ||
      e.agent_name?.toLowerCase().includes(q);
  }), [eventos, busca]);

  const carregados = eventos?.length ?? 0;
  const sucessos = eventos?.filter((e) => e.success).length ?? 0;
  const falhas = carregados - sucessos;

  return (
    <div className="space-y-3">
      {/* Cards de contagem (paridade com a antiga página /auditoria) */}
      <div className="grid grid-cols-3 gap-3">
        <div className="afj-stat-card flex items-center gap-3">
          <ShieldCheck size={20} className="text-afj-gold flex-shrink-0" />
          <div><p className="text-lg font-bold text-afj-black">{totalGeral}</p><p className="text-xs text-afj-black/50">Total de eventos (com os filtros ativos)</p></div>
        </div>
        <div className="afj-stat-card flex items-center gap-3">
          <CheckCircle2 size={20} className="text-green-500 flex-shrink-0" />
          <div><p className="text-lg font-bold text-afj-black">{sucessos}</p><p className="text-xs text-afj-black/50">Bem-sucedidos ({carregados} carregados)</p></div>
        </div>
        <div className="afj-stat-card flex items-center gap-3">
          <XCircle size={20} className="text-red-500 flex-shrink-0" />
          <div><p className="text-lg font-bold text-afj-black">{falhas}</p><p className="text-xs text-afj-black/50">Com falhas ({carregados} carregados)</p></div>
        </div>
      </div>

      <div className="afj-card p-0 overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-afj-cream-dark gap-3 flex-wrap">
          <h2 className="font-semibold text-afj-black text-sm flex items-center gap-2">
            <ShieldCheck size={15} className="text-afj-gold" /> Trilha de auditoria (plataforma)
          </h2>
          <div className="flex items-center gap-2 flex-wrap">
            <div className="relative">
              <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-afj-black/30" />
              <input
                value={busca} onChange={(e) => setBusca(e.target.value)}
                placeholder="Buscar ação, recurso ou agente..."
                className="pl-7 pr-2 py-1.5 text-xs border border-afj-cream-dark rounded-sm focus:outline-none focus:border-afj-gold bg-white w-52"
              />
            </div>
            <select value={filtroTenant} onChange={(e) => setFiltroTenant(e.target.value)}
              className="border border-afj-cream-dark rounded-sm px-2 py-1.5 text-xs bg-white focus:outline-none focus:border-afj-gold max-w-40">
              <option value="">Todos os tenants</option>
              {tenants.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
            <select value={filtroSucesso} onChange={(e) => setFiltroSucesso(e.target.value)}
              className="border border-afj-cream-dark rounded-sm px-2 py-1.5 text-xs bg-white focus:outline-none focus:border-afj-gold">
              <option value="">Todos</option>
              <option value="true">Sucesso</option>
              <option value="false">Falha</option>
            </select>
            <button onClick={() => carregar(0, false)} disabled={carregando}
              className="text-afj-black/40 hover:text-afj-black p-1 disabled:opacity-50" aria-label="Recarregar">
              <RefreshCw size={14} className={carregando ? "animate-spin" : ""} />
            </button>
          </div>
        </div>

        {eventos === null ? (
          <p className="p-6 text-center text-sm text-afj-black/40">Carregando…</p>
        ) : filtrados.length === 0 ? (
          <p className="p-6 text-center text-sm text-afj-black/40">
            {totalGeral === 0 ? "Nenhum evento de auditoria registrado ainda." : "Nenhum evento corresponde à busca/filtro."}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="afj-table w-full text-xs">
              <thead>
                <tr>
                  <th className="text-left">Quando</th>
                  <th className="text-left">Ação</th>
                  <th className="text-left">Recurso</th>
                  <th className="text-left">Agente / Origem</th>
                  <th className="text-center">PII</th>
                  <th className="text-center">OK</th>
                </tr>
              </thead>
              <tbody>
                {filtrados.map((e) => (
                  <tr key={e.id}>
                    <td className="whitespace-nowrap text-afj-black/60 font-mono">
                      {e.timestamp ? new Date(e.timestamp).toLocaleString("pt-BR") : "—"}
                    </td>
                    <td className="font-medium text-afj-black">{e.action}</td>
                    <td className="text-afj-black/60">
                      {e.resource_type ?? "—"}
                      {e.legal_basis && <span className="text-afj-black/30"> · {e.legal_basis}</span>}
                    </td>
                    <td className="text-afj-black/50">
                      {e.agent_name ? (
                        <span className="bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded">{e.agent_name}</span>
                      ) : (e.ip_address ?? "sistema")}
                    </td>
                    <td className="text-center">
                      {e.contains_pii && (
                        <span className="inline-flex items-center gap-1 text-amber-600" title="Contém dado pessoal">
                          <AlertTriangle size={11} />
                        </span>
                      )}
                    </td>
                    <td className="text-center">
                      {e.success
                        ? <CheckCircle2 size={13} className="inline text-green-600" />
                        : <XCircle size={13} className="inline text-red-500" />}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {hasMore && (
          <div className="flex justify-center py-3 border-t border-afj-cream-dark">
            <button
              onClick={() => carregar(offset, true)}
              disabled={carregandoMais}
              className="btn-afj-outline rounded-sm text-xs disabled:opacity-50"
            >
              {carregandoMais ? "Carregando..." : `Carregar mais (${carregados} de ${totalGeral})`}
            </button>
          </div>
        )}
        <p className="px-4 py-2 text-[11px] text-afj-black/35 border-t border-afj-cream-dark">
          Registro imutável (audit_logs) — visão de todas as tenants, exclusiva do SuperAdmin.
        </p>
      </div>
    </div>
  );
}
