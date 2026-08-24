"use client";
import { useState, useEffect } from "react";
import { Loader2, Link2, RefreshCw, Ban, Copy, Check as CheckIcon, ShieldOff } from "lucide-react";
import { useToast } from "@/components/ui/Toast";

interface PortalAccessRow {
  client_id: string;
  nome: string;
  tipo: string;
  status: "SEM_ACESSO" | "ATIVO" | "EXPIRADO" | "REVOGADO";
  created_at: string | null;
  expires_at: string | null;
}

const STATUS_BADGE: Record<string, string> = {
  SEM_ACESSO: "bg-afj-cream text-afj-black/50",
  ATIVO: "badge-ativo",
  EXPIRADO: "badge-pendente",
  REVOGADO: "bg-red-50 text-red-600",
};

const STATUS_LABEL: Record<string, string> = {
  SEM_ACESSO: "Sem acesso",
  ATIVO: "Ativo",
  EXPIRADO: "Expirado",
  REVOGADO: "Revogado",
};

const VALIDADES = [1, 3, 7, 15, 30];

function fmtData(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

/** Fase 234 — Controle de Clientes: gerar/regerar/revogar o link de acesso
 * ao Portal do Cliente, separado do cadastro de usuários internos (o
 * `User` técnico por trás do link nunca aparece aqui nem em /Usuários). */
export function ClientPortalAccessPanel() {
  const toast = useToast();
  const [rows, setRows] = useState<PortalAccessRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [validadeEscolhida, setValidadeEscolhida] = useState<Record<string, number>>({});
  const [gerando, setGerando] = useState<string | null>(null);
  const [revogando, setRevogando] = useState<string | null>(null);
  const [linkGerado, setLinkGerado] = useState<{ nome: string; url: string; expires_at: string } | null>(null);
  const [copiado, setCopiado] = useState(false);

  useEffect(() => { fetchRows(); }, []);

  async function fetchRows() {
    setLoading(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/clients/portal-access", { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) setRows(await res.json());
      else toast.error("Erro ao carregar Controle de Clientes.");
    } catch {
      toast.error("Erro de conexão.");
    } finally {
      setLoading(false);
    }
  }

  async function gerarAcesso(row: PortalAccessRow) {
    setGerando(row.client_id);
    try {
      const token = localStorage.getItem("afj_access_token");
      const validade_dias = validadeEscolhida[row.client_id] ?? 7;
      const res = await fetch(`/api/v1/clients/${row.client_id}/portal-access`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ validade_dias }),
      });
      const data = await res.json();
      if (!res.ok) {
        toast.error(data.detail || "Erro ao gerar acesso.");
        return;
      }
      setLinkGerado({ nome: row.nome, url: `${window.location.origin}${data.path}`, expires_at: data.expires_at });
      await fetchRows();
    } catch {
      toast.error("Erro de conexão.");
    } finally {
      setGerando(null);
    }
  }

  async function revogarAcesso(row: PortalAccessRow) {
    if (!confirm(`Revogar o acesso ao portal de "${row.nome}"? O link atual deixa de funcionar imediatamente.`)) return;
    setRevogando(row.client_id);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/clients/${row.client_id}/portal-access`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        toast.success("Acesso revogado.");
        await fetchRows();
      } else {
        const data = await res.json().catch(() => ({}));
        toast.error(data.detail || "Erro ao revogar acesso.");
      }
    } catch {
      toast.error("Erro de conexão.");
    } finally {
      setRevogando(null);
    }
  }

  async function copiarLink() {
    if (!linkGerado) return;
    await navigator.clipboard.writeText(linkGerado.url);
    setCopiado(true);
    setTimeout(() => setCopiado(false), 2000);
  }

  if (loading) {
    return <div className="flex justify-center py-12"><Loader2 className="animate-spin text-afj-gold" size={22} /></div>;
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-afj-black/50">
        Gere um link temporário e seguro pra cada cliente acessar o Portal — sem precisar criar um usuário interno.
      </p>

      <div className="afj-card overflow-x-auto">
        <table className="afj-table w-full">
          <thead>
            <tr>
              <th>Cliente</th>
              <th>Status</th>
              <th>Criado em</th>
              <th>Expira em</th>
              <th>Ações</th>
            </tr>
          </thead>
          <tbody>
            {(rows ?? []).map((row) => (
              <tr key={row.client_id}>
                <td className="font-medium text-afj-black">{row.nome}</td>
                <td>
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${STATUS_BADGE[row.status]}`}>
                    {STATUS_LABEL[row.status]}
                  </span>
                </td>
                <td className="text-sm text-afj-black/60">{fmtData(row.created_at)}</td>
                <td className="text-sm text-afj-black/60">{fmtData(row.expires_at)}</td>
                <td>
                  <div className="flex items-center gap-2">
                    <select
                      value={validadeEscolhida[row.client_id] ?? 7}
                      onChange={(e) => setValidadeEscolhida((v) => ({ ...v, [row.client_id]: Number(e.target.value) }))}
                      className="border border-afj-cream-dark rounded-sm px-2 py-1 text-xs bg-white focus:outline-none focus:border-afj-gold"
                    >
                      {VALIDADES.map((v) => <option key={v} value={v}>{v} dia{v > 1 ? "s" : ""}</option>)}
                    </select>
                    <button
                      onClick={() => gerarAcesso(row)}
                      disabled={gerando === row.client_id}
                      className="btn-afj-outline rounded-sm text-xs py-1.5 px-2.5 flex items-center gap-1.5 disabled:opacity-60"
                      title={row.status === "SEM_ACESSO" ? "Gerar acesso" : "Regerar acesso"}
                    >
                      {gerando === row.client_id ? <Loader2 size={12} className="animate-spin" /> : row.status === "SEM_ACESSO" ? <Link2 size={12} /> : <RefreshCw size={12} />}
                      {row.status === "SEM_ACESSO" ? "Gerar" : "Regerar"}
                    </button>
                    {(row.status === "ATIVO" || row.status === "EXPIRADO") && (
                      <button
                        onClick={() => revogarAcesso(row)}
                        disabled={revogando === row.client_id}
                        className="text-xs py-1.5 px-2.5 rounded-sm border border-red-200 text-red-600 hover:bg-red-50 flex items-center gap-1.5 disabled:opacity-60"
                        title="Revogar acesso"
                      >
                        {revogando === row.client_id ? <Loader2 size={12} className="animate-spin" /> : <Ban size={12} />}
                        Revogar
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {(rows ?? []).length === 0 && (
          <div className="text-center py-12">
            <ShieldOff className="mx-auto text-afj-black/20 mb-2" size={28} />
            <p className="text-sm text-afj-black/40">Nenhum cliente cadastrado ainda.</p>
          </div>
        )}
      </div>

      {/* Modal: link gerado */}
      {linkGerado && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-sm shadow-xl w-full max-w-md p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-9 h-9 rounded bg-green-100 flex items-center justify-center flex-shrink-0">
                <Link2 size={16} className="text-green-600" />
              </div>
              <h2 className="font-semibold text-afj-black">Link de Acesso Gerado</h2>
            </div>
            <p className="text-sm text-afj-black/60 mb-1">
              Compartilhe o link abaixo com <strong>{linkGerado.nome}</strong> de forma segura.
            </p>
            <p className="text-xs text-afj-black/40 mb-4">
              Válido até {fmtData(linkGerado.expires_at)}. O link não é recuperável depois de fechar esta janela — gere um novo se precisar.
            </p>
            <div className="flex items-center gap-2 bg-afj-cream rounded-sm p-3 mb-4">
              <code className="flex-1 text-xs font-mono break-all">{linkGerado.url}</code>
              <button
                onClick={copiarLink}
                className="p-1.5 text-afj-black/40 hover:text-afj-gold transition-colors flex-shrink-0"
                title="Copiar link"
              >
                {copiado ? <CheckIcon size={16} className="text-green-600" /> : <Copy size={16} />}
              </button>
            </div>
            <button onClick={() => setLinkGerado(null)} className="w-full btn-afj-primary rounded-sm">
              Fechar
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
