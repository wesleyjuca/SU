"use client";
import { useState, useEffect } from "react";
import { ShieldCheck, Search, CheckCircle, XCircle, AlertTriangle } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";

interface AuditLog {
  id: number;
  event_id: string;
  timestamp: string;
  user_id: string | null;
  agent_name: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  ip_address: string | null;
  success: boolean;
  contains_pii: boolean;
  legal_basis: string | null;
}

export default function AuditoriaPage() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filtroSucesso, setFiltroSucesso] = useState("");

  useEffect(() => { fetchLogs(); }, []);

  async function fetchLogs() {
    setLoading(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const logsRes = await fetch("/api/v1/audit?limit=100", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (logsRes.ok) setLogs(await logsRes.json());
    } finally { setLoading(false); }
  }

  const filtrados = logs.filter((l) => {
    const matchSearch = !search || l.action.toLowerCase().includes(search.toLowerCase()) ||
      l.resource_type?.toLowerCase().includes(search.toLowerCase()) ||
      l.agent_name?.toLowerCase().includes(search.toLowerCase());
    const matchSucesso = !filtroSucesso ||
      (filtroSucesso === "true" && l.success) ||
      (filtroSucesso === "false" && !l.success);
    return matchSearch && matchSucesso;
  });

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Auditoria" }]} />
      <div className="afj-page-header">
        <div>
          <h1 className="font-display text-2xl font-semibold text-afj-black">Auditoria</h1>
          <p className="text-afj-black/50 text-sm">Registro imutável de todas as ações do sistema</p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="afj-card p-4 flex items-center gap-3">
          <ShieldCheck size={24} className="text-afj-gold flex-shrink-0" />
          <div>
            <p className="text-lg font-bold text-afj-black">{logs.length}</p>
            <p className="text-xs text-afj-black/50">Total de eventos</p>
          </div>
        </div>
        <div className="afj-card p-4 flex items-center gap-3">
          <CheckCircle size={24} className="text-green-500 flex-shrink-0" />
          <div>
            <p className="text-lg font-bold text-afj-black">{logs.filter((l) => l.success).length}</p>
            <p className="text-xs text-afj-black/50">Bem-sucedidos</p>
          </div>
        </div>
        <div className="afj-card p-4 flex items-center gap-3">
          <XCircle size={24} className="text-red-500 flex-shrink-0" />
          <div>
            <p className="text-lg font-bold text-afj-black">{logs.filter((l) => !l.success).length}</p>
            <p className="text-xs text-afj-black/50">Com falhas</p>
          </div>
        </div>
      </div>

      <div className="flex gap-3">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-afj-black/30" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por ação, recurso ou agente..."
            className="w-full pl-9 pr-4 py-2 text-sm border border-afj-cream-dark rounded-sm focus:outline-none focus:border-afj-gold bg-white"
          />
        </div>
        <select
          value={filtroSucesso}
          onChange={(e) => setFiltroSucesso(e.target.value)}
          className="border border-afj-cream-dark rounded-sm px-3 py-2 text-sm bg-white focus:outline-none focus:border-afj-gold"
        >
          <option value="">Todos</option>
          <option value="true">Sucesso</option>
          <option value="false">Falha</option>
        </select>
      </div>

      {loading ? (
        <div className="afj-card p-4 space-y-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-10 bg-afj-cream-dark rounded animate-pulse" />
          ))}
        </div>
      ) : filtrados.length === 0 ? (
        <div className="afj-card p-12 text-center">
          <ShieldCheck className="mx-auto text-afj-black/20 mb-3" size={40} />
          <p className="font-semibold text-afj-black">Nenhum evento registrado</p>
          <p className="text-afj-black/40 text-sm mt-1">Todas as ações do sistema são registradas aqui automaticamente</p>
        </div>
      ) : (
        <div className="afj-card overflow-hidden">
          <table className="afj-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Ação</th>
                <th>Recurso</th>
                <th>Agente / IP</th>
                <th>PII</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {filtrados.map((l) => (
                <tr key={l.event_id}>
                  <td className="px-4 py-2.5 font-mono text-afj-black/50">
                    {new Date(l.timestamp).toLocaleString("pt-BR")}
                  </td>
                  <td className="px-4 py-2.5 font-medium text-afj-black">{l.action}</td>
                  <td className="px-4 py-2.5 text-afj-black/60">
                    {l.resource_type && <span className="bg-afj-cream px-1.5 py-0.5 rounded">{l.resource_type}</span>}
                    {l.resource_id && <span className="ml-1 font-mono text-afj-black/30">{l.resource_id.substring(0, 8)}…</span>}
                  </td>
                  <td className="px-4 py-2.5 text-afj-black/50">
                    {l.agent_name ? (
                      <span className="bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded">{l.agent_name}</span>
                    ) : l.ip_address}
                  </td>
                  <td className="px-4 py-2.5">
                    {l.contains_pii && (
                      <span className="flex items-center gap-1 text-amber-600">
                        <AlertTriangle size={10} />
                        PII
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    {l.success ? (
                      <CheckCircle size={14} className="text-green-500" />
                    ) : (
                      <XCircle size={14} className="text-red-500" />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
