"use client";
import { useState, useEffect, useCallback } from "react";
import { ShieldCheck, RefreshCw, CheckCircle2, XCircle } from "lucide-react";
import { fetchBrain, type AuditEvento } from "./types";

interface AuditResp { ok: boolean; eventos: AuditEvento[] }

export function BrainAudit() {
  const [eventos, setEventos] = useState<AuditEvento[] | null>(null);
  const [carregando, setCarregando] = useState(false);

  const carregar = useCallback(async () => {
    setCarregando(true);
    const r = await fetchBrain<AuditResp>("audit?limit=80");
    setEventos(r?.eventos ?? []);
    setCarregando(false);
  }, []);
  useEffect(() => { carregar(); }, [carregar]);

  return (
    <div className="afj-card p-0 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-afj-cream-dark">
        <h2 className="font-semibold text-afj-black text-sm flex items-center gap-2">
          <ShieldCheck size={15} className="text-afj-gold" /> Trilha de auditoria (plataforma)
        </h2>
        <button onClick={carregar} disabled={carregando}
          className="text-afj-black/40 hover:text-afj-black p-1 disabled:opacity-50" aria-label="Recarregar">
          <RefreshCw size={14} className={carregando ? "animate-spin" : ""} />
        </button>
      </div>

      {eventos === null ? (
        <p className="p-6 text-center text-sm text-afj-black/40">Carregando…</p>
      ) : eventos.length === 0 ? (
        <p className="p-6 text-center text-sm text-afj-black/40">Nenhum evento de auditoria registrado ainda.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="afj-table w-full text-xs">
            <thead>
              <tr>
                <th className="text-left">Quando</th>
                <th className="text-left">Ação</th>
                <th className="text-left">Recurso</th>
                <th className="text-center">OK</th>
                <th className="text-left">Origem</th>
              </tr>
            </thead>
            <tbody>
              {eventos.map((e) => (
                <tr key={e.id}>
                  <td className="whitespace-nowrap text-afj-black/60">
                    {e.timestamp ? new Date(e.timestamp).toLocaleString("pt-BR") : "—"}
                  </td>
                  <td className="font-medium text-afj-black">{e.action}</td>
                  <td className="text-afj-black/60">
                    {e.resource_type ?? "—"}
                    {e.legal_basis && <span className="text-afj-black/30"> · {e.legal_basis}</span>}
                  </td>
                  <td className="text-center">
                    {e.success
                      ? <CheckCircle2 size={13} className="inline text-green-600" />
                      : <XCircle size={13} className="inline text-red-500" />}
                  </td>
                  <td className="text-afj-black/45 whitespace-nowrap">{e.ip_address ?? "sistema"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="px-4 py-2 text-[11px] text-afj-black/35 border-t border-afj-cream-dark">
        Registro imutável (audit_logs) — visão de todas as tenants, exclusiva do SuperAdmin.
      </p>
    </div>
  );
}
