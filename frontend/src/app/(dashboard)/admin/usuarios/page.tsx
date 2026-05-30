"use client";
import { useState, useEffect } from "react";
import {
  Users, Plus, Pencil, UserCheck, UserX, Copy, Check, Search,
  KeyRound, History, ChevronRight, X, Filter,
} from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { useUserStore } from "@/store";

const ROLES = ["ADMIN", "SOCIO", "ADVOGADO", "PARALEGAL", "ASSISTENTE", "GESTOR"];

const ROLE_STYLE: Record<string, string> = {
  ADMIN: "bg-afj-gold/15 text-afj-gold-dark border border-afj-gold/30",
  SOCIO: "bg-blue-50 text-blue-800 border border-blue-200",
  ADVOGADO: "bg-purple-50 text-purple-800 border border-purple-200",
  PARALEGAL: "bg-indigo-50 text-indigo-700 border border-indigo-200",
  ASSISTENTE: "bg-gray-100 text-gray-700 border border-gray-200",
  GESTOR: "bg-teal-50 text-teal-700 border border-teal-200",
  SUPERADMIN: "bg-red-50 text-red-700 border border-red-200",
};

interface UserItem {
  id: string;
  full_name: string;
  email: string;
  role: string;
  is_active: boolean;
  oab_number: string | null;
  oab_uf: string | null;
  last_login_at: string | null;
  created_at: string;
}

interface ActivityItem {
  timestamp: string;
  action: string;
  resource_type: string | null;
  success: boolean;
  error_detail: string | null;
  ip_address: string | null;
}

function timeAgo(iso: string | null): string {
  if (!iso) return "Nunca";
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "Agora";
  if (m < 60) return `há ${m}min`;
  const h = Math.floor(m / 60);
  if (h < 24) return `há ${h}h`;
  const d = Math.floor(h / 24);
  if (d < 30) return `há ${d}d`;
  return new Date(iso).toLocaleDateString("pt-BR");
}

const PAGE_SIZE = 50;

export default function UsuariosPage() {
  const { user: me } = useUserStore();
  const [users, setUsers] = useState<UserItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [offset, setOffset] = useState(0);

  // Filtros
  const [search, setSearch] = useState("");
  const [filterRole, setFilterRole] = useState("");
  const [filterActive, setFilterActive] = useState<string>("");

  // Modais
  const [showInvite, setShowInvite] = useState(false);
  const [editUser, setEditUser] = useState<UserItem | null>(null);
  const [resetUser, setResetUser] = useState<UserItem | null>(null);
  const [activityUser, setActivityUser] = useState<UserItem | null>(null);
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [activityLoading, setActivityLoading] = useState(false);

  // Formulário convite
  const [invite, setInvite] = useState({ email: "", full_name: "", role: "ADVOGADO" });
  const [inviting, setInviting] = useState(false);
  const [tempPwd, setTempPwd] = useState("");
  const [copied, setCopied] = useState(false);
  const [apiError, setApiError] = useState("");

  // Reset senha
  const [resetting, setResetting] = useState(false);
  const [newTempPwd, setNewTempPwd] = useState("");
  const [resetCopied, setResetCopied] = useState(false);

  useEffect(() => {
    fetchUsers(0, false);
  }, [search, filterRole, filterActive]);

  async function fetchUsers(newOffset = 0, append = false) {
    if (append) setLoadingMore(true);
    else setLoading(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const params = new URLSearchParams();
      if (search) params.set("search", search);
      if (filterRole) params.set("role", filterRole);
      if (filterActive !== "") params.set("is_active", filterActive);
      params.set("limit", String(PAGE_SIZE));
      params.set("offset", String(newOffset));
      const res = await fetch(`/api/v1/users?${params}`, { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) {
        const data: UserItem[] = await res.json();
        setUsers((prev) => append ? [...prev, ...data] : data);
        setHasMore(data.length === PAGE_SIZE);
        setOffset(newOffset + data.length);
      }
    } finally {
      if (append) setLoadingMore(false);
      else setLoading(false);
    }
  }

  async function handleInvite(e: React.FormEvent) {
    e.preventDefault();
    setInviting(true);
    setApiError("");
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/users/invite", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(invite),
      });
      const data = await res.json();
      if (res.ok) {
        setTempPwd(data.temp_password);
        setInvite({ email: "", full_name: "", role: "ADVOGADO" });
        fetchUsers(0, false);
      } else {
        setApiError(data.detail || "Erro ao convidar usuário.");
      }
    } finally {
      setInviting(false);
    }
  }

  async function handleUpdate(id: string, changes: Partial<UserItem>) {
    const token = localStorage.getItem("afj_access_token");
    await fetch(`/api/v1/users/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify(changes),
    });
    setEditUser(null);
    fetchUsers(0, false);
  }

  async function handleResetPassword() {
    if (!resetUser) return;
    setResetting(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/users/${resetUser.id}/reset-password`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setNewTempPwd(data.temp_password);
      }
    } finally {
      setResetting(false);
    }
  }

  async function openActivity(u: UserItem) {
    setActivityUser(u);
    setActivity([]);
    setActivityLoading(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/users/${u.id}/activity`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setActivity(await res.json());
    } finally {
      setActivityLoading(false);
    }
  }

  function copyText(text: string, setter: (v: boolean) => void) {
    navigator.clipboard.writeText(text);
    setter(true);
    setTimeout(() => setter(false), 2000);
  }

  const initials = (name: string) => name.split(" ").map((n) => n[0]).slice(0, 2).join("").toUpperCase();

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Admin" }, { label: "Usuários" }]} />

      {/* Header */}
      <div className="afj-page-header">
        <div>
          <h1 className="font-display text-2xl font-semibold text-afj-black">Usuários</h1>
          <p className="text-afj-black/50 text-sm">{users.length} membro(s) do escritório</p>
        </div>
        <button
          onClick={() => { setShowInvite(true); setTempPwd(""); setApiError(""); }}
          className="btn-afj-primary rounded-sm flex items-center gap-2"
        >
          <Plus size={14} />
          Convidar Usuário
        </button>
      </div>

      {/* Filtros */}
      <div className="flex gap-3 flex-wrap">
        <div className="relative flex-1 min-w-48">
          <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-afj-black/30" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por nome ou e-mail..."
            className="w-full pl-9 pr-4 py-2 text-sm border border-afj-cream-dark rounded-sm focus:outline-none focus:border-afj-gold bg-white"
          />
        </div>
        <select
          value={filterRole}
          onChange={(e) => setFilterRole(e.target.value)}
          className="border border-afj-cream-dark rounded-sm px-3 py-2 text-sm bg-white focus:outline-none focus:border-afj-gold"
        >
          <option value="">Todos os perfis</option>
          {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
        <select
          value={filterActive}
          onChange={(e) => setFilterActive(e.target.value)}
          className="border border-afj-cream-dark rounded-sm px-3 py-2 text-sm bg-white focus:outline-none focus:border-afj-gold"
        >
          <option value="">Todos os status</option>
          <option value="true">Ativos</option>
          <option value="false">Inativos</option>
        </select>
        {(search || filterRole || filterActive) && (
          <button
            onClick={() => { setSearch(""); setFilterRole(""); setFilterActive(""); }}
            className="flex items-center gap-1 text-xs text-afj-black/50 hover:text-afj-black px-2"
          >
            <X size={12} /> Limpar
          </button>
        )}
      </div>

      {/* Lista de usuários */}
      {loading ? (
        <div className="afj-card p-4 space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-16 bg-afj-cream-dark rounded animate-pulse" />
          ))}
        </div>
      ) : users.length === 0 ? (
        <div className="afj-card p-12 text-center">
          <Users size={28} className="mx-auto text-afj-black/15 mb-2" />
          <p className="text-sm text-afj-black/40">
            {search || filterRole || filterActive ? "Nenhum usuário encontrado com esses filtros." : "Nenhum usuário cadastrado."}
          </p>
        </div>
      ) : (
        <div className="afj-card divide-y divide-afj-cream-dark">
          {users.map((u) => (
            <div key={u.id} className="flex items-center gap-4 px-5 py-4 hover:bg-afj-cream/30 transition-colors">
              {/* Avatar */}
              <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 text-white text-sm font-bold ${
                u.is_active ? "bg-afj-gold" : "bg-afj-black/20"
              }`}>
                {initials(u.full_name)}
              </div>

              {/* Info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className={`font-medium text-sm ${u.is_active ? "text-afj-black" : "text-afj-black/35 line-through"}`}>
                    {u.full_name}
                  </span>
                  <span className={`text-[9px] font-semibold uppercase px-2 py-0.5 rounded-sm ${ROLE_STYLE[u.role] ?? "bg-gray-100 text-gray-700"}`}>
                    {u.role}
                  </span>
                  {!u.is_active && <span className="text-[10px] text-red-500 font-medium">Inativo</span>}
                  {u.id === me?.id && <span className="text-[10px] text-afj-gold font-medium">Você</span>}
                  {u.oab_number && (
                    <span className="text-[10px] text-afj-black/35 font-mono">
                      OAB {u.oab_number}/{u.oab_uf}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-3 mt-0.5">
                  <p className="text-xs text-afj-black/40 truncate">{u.email}</p>
                  <span className="text-afj-black/20 text-xs">·</span>
                  <p className="text-[10px] text-afj-black/30 whitespace-nowrap">
                    Acesso: {timeAgo(u.last_login_at)}
                  </p>
                </div>
              </div>

              {/* Ações */}
              <div className="flex items-center gap-1 flex-shrink-0">
                <button
                  onClick={() => setEditUser(u)}
                  className="text-afj-black/35 hover:text-afj-gold transition-colors p-2 rounded-sm hover:bg-afj-gold/5"
                  aria-label="Editar usuário"
                  title="Editar"
                >
                  <Pencil size={13} />
                </button>
                <button
                  onClick={() => { setResetUser(u); setNewTempPwd(""); setResetCopied(false); }}
                  className="text-afj-black/35 hover:text-amber-600 transition-colors p-2 rounded-sm hover:bg-amber-50"
                  aria-label="Resetar senha"
                  title="Resetar senha"
                >
                  <KeyRound size={13} />
                </button>
                <button
                  onClick={() => openActivity(u)}
                  className="text-afj-black/35 hover:text-blue-600 transition-colors p-2 rounded-sm hover:bg-blue-50"
                  aria-label="Ver atividade"
                  title="Histórico de ações"
                >
                  <History size={13} />
                </button>
                {u.id !== me?.id && (
                  <button
                    onClick={() => handleUpdate(u.id, { is_active: !u.is_active })}
                    className={`transition-colors p-2 rounded-sm ${
                      u.is_active
                        ? "text-afj-black/35 hover:text-red-500 hover:bg-red-50"
                        : "text-afj-black/35 hover:text-green-600 hover:bg-green-50"
                    }`}
                    aria-label={u.is_active ? "Desativar" : "Reativar"}
                    title={u.is_active ? "Desativar" : "Reativar"}
                  >
                    {u.is_active ? <UserX size={13} /> : <UserCheck size={13} />}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Carregar mais */}
      {hasMore && !loading && (
        <div className="flex justify-center">
          <button
            onClick={() => fetchUsers(offset, true)}
            disabled={loadingMore}
            className="btn-afj-outline rounded-sm text-sm disabled:opacity-50"
          >
            {loadingMore ? "Carregando..." : "Carregar mais usuários"}
          </button>
        </div>
      )}

      {/* Modal — Convidar Usuário */}
      {showInvite && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={(e) => { if (e.target === e.currentTarget) { setShowInvite(false); setTempPwd(""); } }}>
          <div className="bg-white rounded-sm shadow-xl max-w-md w-full p-6 space-y-4">
            <h3 className="font-display text-lg font-semibold text-afj-black">Convidar Usuário</h3>
            {tempPwd ? (
              <div className="space-y-4">
                <div className="p-4 bg-green-50 border border-green-200 rounded-sm">
                  <p className="text-sm font-semibold text-green-800 mb-1">Usuário criado!</p>
                  <p className="text-xs text-green-700 mb-3">Compartilhe esta senha temporária com o usuário.</p>
                  <div className="flex items-center gap-2 bg-white border border-green-200 rounded-sm px-3 py-2.5">
                    <code className="flex-1 text-sm font-mono text-afj-black select-all">{tempPwd}</code>
                    <button onClick={() => copyText(tempPwd, setCopied)} className="text-green-600" aria-label="Copiar senha">
                      {copied ? <Check size={14} /> : <Copy size={14} />}
                    </button>
                  </div>
                </div>
                <button onClick={() => { setShowInvite(false); setTempPwd(""); }} className="w-full btn-afj-primary rounded-sm">Concluir</button>
              </div>
            ) : (
              <form onSubmit={handleInvite} className="space-y-4">
                {[
                  { label: "Nome Completo", key: "full_name", type: "text", placeholder: "Dr. João Silva" },
                  { label: "E-mail", key: "email", type: "email", placeholder: "joao@afj.adv.br" },
                ].map(({ label, key, type, placeholder }) => (
                  <div key={key}>
                    <label className="text-[10px] text-afj-black/55 block mb-1 uppercase tracking-widest font-semibold">{label}</label>
                    <input type={type} required placeholder={placeholder} value={(invite as Record<string, string>)[key]}
                      onChange={(e) => setInvite((i) => ({ ...i, [key]: e.target.value }))}
                      className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold" />
                  </div>
                ))}
                <div>
                  <label className="text-[10px] text-afj-black/55 block mb-1 uppercase tracking-widest font-semibold">Perfil</label>
                  <select value={invite.role} onChange={(e) => setInvite((i) => ({ ...i, role: e.target.value }))}
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold">
                    {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                </div>
                {apiError && <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-sm px-3 py-2">{apiError}</p>}
                <div className="flex gap-2 pt-1">
                  <button type="button" onClick={() => setShowInvite(false)} className="flex-1 btn-afj-outline rounded-sm">Cancelar</button>
                  <button type="submit" disabled={inviting} className="flex-1 btn-afj-primary rounded-sm disabled:opacity-50">
                    {inviting ? "Convidando..." : "Convidar"}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      {/* Modal — Editar Usuário */}
      {editUser && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={(e) => { if (e.target === e.currentTarget) setEditUser(null); }}>
          <div className="bg-white rounded-sm shadow-xl max-w-sm w-full p-6 space-y-4">
            <h3 className="font-display text-lg font-semibold text-afj-black">Editar Usuário</h3>
            <div>
              <label className="text-[10px] text-afj-black/55 block mb-1 uppercase tracking-widest font-semibold">Nome Completo</label>
              <input type="text" value={editUser.full_name} onChange={(e) => setEditUser((u) => u ? { ...u, full_name: e.target.value } : u)}
                className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold" />
            </div>
            <div>
              <label className="text-[10px] text-afj-black/55 block mb-1 uppercase tracking-widest font-semibold">Perfil</label>
              <select value={editUser.role} onChange={(e) => setEditUser((u) => u ? { ...u, role: e.target.value } : u)}
                className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold">
                {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[10px] text-afj-black/55 block mb-1 uppercase tracking-widest font-semibold">OAB</label>
                <input type="text" value={editUser.oab_number ?? ""} onChange={(e) => setEditUser((u) => u ? { ...u, oab_number: e.target.value } : u)}
                  placeholder="123456"
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold" />
              </div>
              <div>
                <label className="text-[10px] text-afj-black/55 block mb-1 uppercase tracking-widest font-semibold">UF</label>
                <input type="text" value={editUser.oab_uf ?? ""} onChange={(e) => setEditUser((u) => u ? { ...u, oab_uf: e.target.value.toUpperCase().slice(0, 2) } : u)}
                  placeholder="SP" maxLength={2}
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold" />
              </div>
            </div>
            <div className="flex gap-2 pt-1">
              <button onClick={() => setEditUser(null)} className="flex-1 btn-afj-outline rounded-sm">Cancelar</button>
              <button onClick={() => handleUpdate(editUser.id, { full_name: editUser.full_name, role: editUser.role, oab_number: editUser.oab_number ?? undefined, oab_uf: editUser.oab_uf ?? undefined })}
                className="flex-1 btn-afj-primary rounded-sm">
                Salvar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal — Reset Senha */}
      {resetUser && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={(e) => { if (e.target === e.currentTarget) { setResetUser(null); setNewTempPwd(""); } }}>
          <div className="bg-white rounded-sm shadow-xl max-w-sm w-full p-6 space-y-4">
            <h3 className="font-display text-lg font-semibold text-afj-black flex items-center gap-2">
              <KeyRound size={18} className="text-amber-500" /> Resetar Senha
            </h3>
            {newTempPwd ? (
              <div className="space-y-4">
                <div className="p-4 bg-amber-50 border border-amber-200 rounded-sm">
                  <p className="text-sm font-semibold text-amber-800 mb-1">Nova senha gerada!</p>
                  <p className="text-xs text-amber-700 mb-3">Compartilhe com {resetUser.full_name}.</p>
                  <div className="flex items-center gap-2 bg-white border border-amber-200 rounded-sm px-3 py-2.5">
                    <code className="flex-1 text-sm font-mono text-afj-black select-all">{newTempPwd}</code>
                    <button onClick={() => copyText(newTempPwd, setResetCopied)} className="text-amber-600" aria-label="Copiar senha">
                      {resetCopied ? <Check size={14} /> : <Copy size={14} />}
                    </button>
                  </div>
                </div>
                <button onClick={() => { setResetUser(null); setNewTempPwd(""); }} className="w-full btn-afj-primary rounded-sm">Fechar</button>
              </div>
            ) : (
              <div className="space-y-4">
                <p className="text-sm text-afj-black/60">
                  Gerar nova senha temporária para <strong>{resetUser.full_name}</strong>?
                  A senha atual será invalidada imediatamente.
                </p>
                <div className="flex gap-2">
                  <button onClick={() => setResetUser(null)} className="flex-1 btn-afj-outline rounded-sm">Cancelar</button>
                  <button onClick={handleResetPassword} disabled={resetting}
                    className="flex-1 bg-amber-500 text-white rounded-sm py-2 text-sm font-medium hover:bg-amber-600 disabled:opacity-50">
                    {resetting ? "Gerando..." : "Gerar Nova Senha"}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Modal — Atividade do Usuário */}
      {activityUser && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={(e) => { if (e.target === e.currentTarget) setActivityUser(null); }}>
          <div className="bg-white rounded-sm shadow-xl max-w-lg w-full p-6 space-y-4 max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between">
              <h3 className="font-display text-lg font-semibold text-afj-black">
                Atividade — {activityUser.full_name}
              </h3>
              <button onClick={() => setActivityUser(null)} className="text-afj-black/40 hover:text-afj-black"><X size={16} /></button>
            </div>
            <div className="flex-1 overflow-y-auto space-y-2">
              {activityLoading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <div key={i} className="h-10 bg-afj-cream-dark rounded animate-pulse" />
                ))
              ) : activity.length === 0 ? (
                <p className="text-sm text-afj-black/40 text-center py-8">Nenhuma ação registrada.</p>
              ) : (
                activity.map((a, i) => (
                  <div key={i} className="flex items-start gap-3 text-xs py-2 border-b border-afj-cream-dark last:border-0">
                    <div className={`mt-0.5 w-1.5 h-1.5 rounded-full flex-shrink-0 ${a.success ? "bg-green-500" : "bg-red-500"}`} />
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-afj-black">{a.action}</span>
                        {a.resource_type && <span className="text-afj-black/40">{a.resource_type}</span>}
                      </div>
                      {a.error_detail && <p className="text-red-600 text-[10px] mt-0.5">{a.error_detail}</p>}
                    </div>
                    <span className="text-afj-black/30 font-mono whitespace-nowrap">
                      {new Date(a.timestamp).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}
                    </span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
