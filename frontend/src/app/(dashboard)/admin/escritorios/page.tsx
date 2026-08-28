"use client";
import { useState, useEffect } from "react";
import {
  Building2, Plus, X, Copy, Check, Power, PowerOff, GitBranch, Loader2, ShieldCheck, ShieldOff,
} from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { useToast } from "@/components/ui/Toast";
import { useConfirmDialog } from "@/hooks/useConfirmDialog";

const PLANOS = ["STANDARD", "PRO", "ENTERPRISE"];

interface TenantItem {
  id: string;
  name: string;
  slug: string;
  plan: string;
  isento: boolean;
  is_active: boolean;
  em_producao: boolean;
  max_users: number;
  users: number;
  is_unit: boolean;
  unit_label: string | null;
  parent_name: string | null;
  is_root: boolean;
}

interface NovoForm {
  name: string;
  plan: string;
  max_users: number;
  admin_email: string;
  admin_name: string;
  unit_label: string;
}

const EMPTY: NovoForm = { name: "", plan: "STANDARD", max_users: 10, admin_email: "", admin_name: "", unit_label: "" };

function authH(): HeadersInit {
  const token = typeof window !== "undefined" ? localStorage.getItem("afj_access_token") : null;
  return { "Content-Type": "application/json", Authorization: `Bearer ${token}` };
}

export default function EscritoriosPage() {
  const toast = useToast();
  const { ask, confirmDialog } = useConfirmDialog();
  const [tenants, setTenants] = useState<TenantItem[]>([]);
  const [loading, setLoading] = useState(true);

  // Modal de criação (escritório novo OU unidade de uma banca)
  const [modal, setModal] = useState<{ mode: "office" | "unit"; parent?: TenantItem } | null>(null);
  const [form, setForm] = useState<NovoForm>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [apiError, setApiError] = useState("");
  const [cred, setCred] = useState<{ email: string; pwd: string | null } | null>(null);
  const [copied, setCopied] = useState(false);
  const [toggling, setToggling] = useState<string | null>(null);

  useEffect(() => { fetchTenants(); }, []);

  async function fetchTenants() {
    setLoading(true);
    try {
      const res = await fetch("/api/v1/tenants", { headers: authH() });
      if (res.ok) setTenants(await res.json());
      else if (res.status === 403) toast.error("Acesso restrito ao super administrador da plataforma.");
    } catch {
      toast.error("Falha ao carregar escritórios.");
    } finally { setLoading(false); }
  }

  function openModal(mode: "office" | "unit", parent?: TenantItem) {
    setForm({ ...EMPTY, plan: parent?.plan || "STANDARD" });
    setApiError("");
    setCred(null);
    setModal({ mode, parent });
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!modal) return;
    setSaving(true);
    setApiError("");
    try {
      const isUnit = modal.mode === "unit";
      const url = isUnit ? `/api/v1/tenants/${modal.parent!.id}/units` : "/api/v1/tenants";
      const payload: Record<string, unknown> = {
        name: form.name,
        plan: form.plan,
        max_users: form.max_users,
        admin_email: form.admin_email,
        admin_name: form.admin_name,
      };
      if (isUnit) payload.unit_label = form.unit_label;
      const res = await fetch(url, { method: "POST", headers: authH(), body: JSON.stringify(payload) });
      const data = await res.json();
      if (res.ok) {
        setCred({ email: data.admin_email, pwd: data.temp_password ?? null });
        toast.success(isUnit ? "Unidade criada." : "Escritório criado.");
        fetchTenants();
      } else {
        setApiError(data.detail || "Erro ao criar.");
      }
    } catch {
      setApiError("Falha de conexão.");
    } finally { setSaving(false); }
  }

  async function toggleActive(t: TenantItem) {
    setToggling(t.id);
    try {
      const res = await fetch(`/api/v1/tenants/${t.id}`, {
        method: "PATCH", headers: authH(), body: JSON.stringify({ is_active: !t.is_active }),
      });
      if (res.ok) { toast.success(t.is_active ? "Escritório desativado." : "Escritório reativado."); fetchTenants(); }
      else { const d = await res.json(); toast.error(d.detail || "Erro ao atualizar."); }
    } catch { toast.error("Falha de conexão."); }
    finally { setToggling(null); }
  }

  // Fase 180 — trava de segurança: em produção, os endpoints de exclusão
  // permanente (processo/usuário) recusam e orientam usar arquivar/desativar.
  async function toggleProducao(t: TenantItem) {
    const ligando = !t.em_producao;
    if (ligando && (await ask({
      title: "Marcar como em produção",
      message: `Marcar "${t.name}" como em produção?\n\nDepois disso, o SUPERADMIN não consegue mais excluir processos/usuários de verdade deste escritório — só arquivar/desativar.`,
    })) === null) return;
    setToggling(t.id);
    try {
      const res = await fetch(`/api/v1/tenants/${t.id}`, {
        method: "PATCH", headers: authH(), body: JSON.stringify({ em_producao: ligando }),
      });
      if (res.ok) { toast.success(ligando ? "Escritório marcado como em produção." : "Trava de produção removida."); fetchTenants(); }
      else { const d = await res.json(); toast.error(d.detail || "Erro ao atualizar."); }
    } catch { toast.error("Falha de conexão."); }
    finally { setToggling(null); }
  }

  function copyCred() {
    if (!cred || !cred.pwd) return;
    navigator.clipboard.writeText(`${cred.email} / ${cred.pwd}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const total = tenants.length;
  const ativos = tenants.filter((t) => t.is_active).length;
  const unidades = tenants.filter((t) => t.is_unit).length;

  return (
    <div className="max-w-6xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Admin" }, { label: "Escritórios" }]} />

      <div className="afj-page-header">
        <div>
          <h1 className="font-display text-2xl font-semibold text-afj-black flex items-center gap-2">
            <Building2 size={22} className="text-afj-gold" /> Escritórios & Unidades
          </h1>
          <p className="text-afj-black/50 text-sm mt-0.5">
            Provisionamento SaaS — cada escritório é isolado; unidades da mesma banca ficam agrupadas.
          </p>
        </div>
        <button onClick={() => openModal("office")} className="btn-afj-primary text-sm py-2 px-4 rounded-sm flex items-center gap-2">
          <Plus size={15} /> Novo escritório
        </button>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="afj-stat-card"><p className="text-2xl font-bold text-afj-black">{loading ? "..." : total}</p><p className="text-xs text-afj-black/50 mt-0.5">Escritórios</p></div>
        <div className="afj-stat-card"><p className="text-2xl font-bold text-green-600">{loading ? "..." : ativos}</p><p className="text-xs text-afj-black/50 mt-0.5">Ativos</p></div>
        <div className="afj-stat-card"><p className="text-2xl font-bold text-afj-black">{loading ? "..." : unidades}</p><p className="text-xs text-afj-black/50 mt-0.5">Unidades</p></div>
      </div>

      {loading ? (
        <div className="afj-card p-8 space-y-3">
          {Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-10 bg-afj-cream-dark rounded animate-pulse" />)}
        </div>
      ) : tenants.length === 0 ? (
        <div className="afj-card p-10 text-center">
          <Building2 size={36} className="mx-auto text-afj-black/20 mb-3" />
          <p className="font-semibold text-afj-black">Nenhum escritório cadastrado</p>
          <p className="text-afj-black/40 text-sm mt-1">Clique em “Novo escritório” para provisionar o primeiro cliente.</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="afj-table w-full">
            <thead>
              <tr>
                <th>Escritório</th><th>Slug</th><th>Plano</th><th>Usuários</th><th>Vínculo</th><th>Status</th><th className="text-right">Ações</th>
              </tr>
            </thead>
            <tbody>
              {tenants.map((t) => (
                <tr key={t.id}>
                  <td>
                    <div className="flex items-center gap-2">
                      {t.is_unit && <GitBranch size={13} className="text-afj-black/30 flex-shrink-0" />}
                      <span className="font-medium text-afj-black">{t.name}</span>
                      {t.is_root && <span className="text-[10px] uppercase tracking-wide bg-afj-gold/15 text-afj-gold-dark px-1.5 py-0.5 rounded-sm">raiz</span>}
                      {t.isento && <span className="text-[10px] uppercase tracking-wide bg-afj-gold/15 text-afj-gold-dark px-1.5 py-0.5 rounded-sm">isento</span>}
                      {t.em_producao && <span className="text-[10px] uppercase tracking-wide bg-blue-50 text-blue-700 border border-blue-200 px-1.5 py-0.5 rounded-sm">em produção</span>}
                    </div>
                    {t.unit_label && <span className="text-xs text-afj-black/40">{t.unit_label}</span>}
                  </td>
                  <td className="font-mono text-xs text-afj-black/50">{t.slug}</td>
                  <td><span className="text-xs bg-afj-cream px-2 py-0.5 rounded">{t.plan}</span></td>
                  <td className="text-afj-black/70">{t.users}/{t.max_users}</td>
                  <td className="text-xs text-afj-black/55">{t.is_unit ? `Unidade de ${t.parent_name}` : "Banca / independente"}</td>
                  <td>
                    <span className={`inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-sm border ${
                      t.is_active ? "bg-green-50 text-green-700 border-green-200" : "bg-gray-50 text-gray-500 border-gray-200"
                    }`}>{t.is_active ? "Ativo" : "Inativo"}</span>
                  </td>
                  <td>
                    <div className="flex items-center justify-end gap-1">
                      {!t.is_unit && (
                        <button onClick={() => openModal("unit", t)} title="Adicionar unidade"
                          className="text-afj-black/40 hover:text-afj-gold p-1.5 rounded hover:bg-afj-cream">
                          <GitBranch size={15} />
                        </button>
                      )}
                      <button onClick={() => toggleProducao(t)} disabled={toggling === t.id}
                        title={t.em_producao ? "Remover trava de produção (permite exclusão permanente pelo SUPERADMIN)" : "Marcar como em produção (bloqueia exclusão permanente)"}
                        className={`p-1.5 rounded hover:bg-afj-cream disabled:opacity-40 ${t.em_producao ? "text-blue-600 hover:text-blue-700" : "text-afj-black/30 hover:text-blue-600"}`}>
                        {toggling === t.id ? <Loader2 size={15} className="animate-spin" /> : t.em_producao ? <ShieldCheck size={15} /> : <ShieldOff size={15} />}
                      </button>
                      {!t.is_root && (
                        <button onClick={() => toggleActive(t)} disabled={toggling === t.id}
                          title={t.is_active ? "Desativar" : "Reativar"}
                          className={`p-1.5 rounded hover:bg-afj-cream disabled:opacity-40 ${t.is_active ? "text-red-500 hover:text-red-600" : "text-green-600 hover:text-green-700"}`}>
                          {toggling === t.id ? <Loader2 size={15} className="animate-spin" /> : t.is_active ? <PowerOff size={15} /> : <Power size={15} />}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Modal criação */}
      {modal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => !saving && setModal(null)}>
          <div className="bg-white rounded-sm shadow-xl w-full max-w-md max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-4 border-b border-afj-cream-dark">
              <h2 className="font-semibold text-afj-black">
                {modal.mode === "unit" ? `Nova unidade de ${modal.parent?.name}` : "Novo escritório"}
              </h2>
              <button onClick={() => !saving && setModal(null)} className="text-afj-black/40 hover:text-afj-black"><X size={18} /></button>
            </div>

            {cred ? (
              <div className="p-5 space-y-4">
                <div className="bg-green-50 border border-green-200 rounded-sm p-4 text-sm">
                  <p className="font-semibold text-green-800 mb-2">Escritório provisionado ✓</p>
                  {cred.pwd ? (
                    <>
                      <p className="text-afj-black/60 text-xs mb-3">Entregue estas credenciais ao administrador do escritório com segurança. A senha temporária não será exibida novamente.</p>
                      <div className="bg-white border border-afj-cream-dark rounded-sm p-3 font-mono text-xs break-all">
                        <div><span className="text-afj-black/40">E-mail: </span>{cred.email}</div>
                        <div><span className="text-afj-black/40">Senha: </span>{cred.pwd}</div>
                      </div>
                      <button onClick={copyCred} className="btn-afj-outline text-xs py-1.5 px-3 rounded-sm flex items-center gap-1.5 mt-3">
                        {copied ? <Check size={12} /> : <Copy size={12} />} {copied ? "Copiado" : "Copiar credenciais"}
                      </button>
                    </>
                  ) : (
                    <p className="text-afj-black/60 text-xs">A senha temporária foi enviada por e-mail a <strong>{cred.email}</strong> — o administrador precisará trocá-la no primeiro acesso.</p>
                  )}
                </div>
                <button onClick={() => setModal(null)} className="btn-afj-primary w-full text-sm py-2 rounded-sm">Concluir</button>
              </div>
            ) : (
              <form onSubmit={handleCreate} className="p-5 space-y-3">
                {apiError && <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-sm p-2">{apiError}</p>}
                <div>
                  <label className="text-xs text-afj-black/60">{modal.mode === "unit" ? "Nome da unidade" : "Nome do escritório"}</label>
                  <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                    className="w-full mt-1 border border-afj-cream-dark rounded-sm px-3 py-2 text-sm" placeholder={modal.mode === "unit" ? "Ex.: AFJ — Cruzeiro do Sul" : "Ex.: Silva & Associados"} />
                </div>
                {modal.mode === "unit" && (
                  <div>
                    <label className="text-xs text-afj-black/60">Rótulo da unidade</label>
                    <input required value={form.unit_label} onChange={(e) => setForm({ ...form, unit_label: e.target.value })}
                      className="w-full mt-1 border border-afj-cream-dark rounded-sm px-3 py-2 text-sm" placeholder="Ex.: Filial Cruzeiro do Sul" />
                  </div>
                )}
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs text-afj-black/60">Plano</label>
                    <select value={form.plan} onChange={(e) => setForm({ ...form, plan: e.target.value })}
                      className="w-full mt-1 border border-afj-cream-dark rounded-sm px-3 py-2 text-sm bg-white">
                      {PLANOS.map((p) => <option key={p} value={p}>{p}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="text-xs text-afj-black/60">Máx. usuários</label>
                    <input type="number" min={1} value={form.max_users} onChange={(e) => setForm({ ...form, max_users: parseInt(e.target.value) || 1 })}
                      className="w-full mt-1 border border-afj-cream-dark rounded-sm px-3 py-2 text-sm" />
                  </div>
                </div>
                <div className="border-t border-afj-cream-dark pt-3">
                  <p className="text-xs font-semibold text-afj-black/60 mb-2">Administrador inicial</p>
                  <input required value={form.admin_name} onChange={(e) => setForm({ ...form, admin_name: e.target.value })}
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm mb-2" placeholder="Nome completo" />
                  <input required type="email" value={form.admin_email} onChange={(e) => setForm({ ...form, admin_email: e.target.value })}
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm" placeholder="email@escritorio.com" />
                </div>
                <button type="submit" disabled={saving} className="btn-afj-primary w-full text-sm py-2 rounded-sm flex items-center justify-center gap-2 disabled:opacity-50">
                  {saving ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />} {modal.mode === "unit" ? "Criar unidade" : "Criar escritório"}
                </button>
              </form>
            )}
          </div>
        </div>
      )}
      {confirmDialog}
    </div>
  );
}
