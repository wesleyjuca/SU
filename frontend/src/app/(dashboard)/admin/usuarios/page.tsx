"use client";
import { useState, useEffect } from "react";
import { Users, Plus, Pencil, UserCheck, UserX, Copy, Check } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { useUserStore } from "@/store";

const ROLES = ["ADMIN", "SOCIO", "ADVOGADO", "ASSISTENTE"];

const ROLE_STYLE: Record<string, string> = {
  ADMIN: "bg-afj-gold/15 text-afj-gold-dark border border-afj-gold/30",
  SOCIO: "bg-blue-50 text-blue-800 border border-blue-200",
  ADVOGADO: "bg-purple-50 text-purple-800 border border-purple-200",
  ASSISTENTE: "bg-gray-100 text-gray-700 border border-gray-200",
  SUPERADMIN: "bg-red-50 text-red-700 border border-red-200",
};

interface UserItem {
  id: string;
  full_name: string;
  email: string;
  role: string;
  is_active: boolean;
}

export default function UsuariosPage() {
  const { user: me } = useUserStore();
  const [users, setUsers] = useState<UserItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showInvite, setShowInvite] = useState(false);
  const [editUser, setEditUser] = useState<UserItem | null>(null);
  const [invite, setInvite] = useState({ email: "", full_name: "", role: "ADVOGADO" });
  const [inviting, setInviting] = useState(false);
  const [tempPwd, setTempPwd] = useState("");
  const [copied, setCopied] = useState(false);
  const [apiError, setApiError] = useState("");

  useEffect(() => { fetchUsers(); }, []);

  async function fetchUsers() {
    setLoading(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/users", { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) setUsers(await res.json());
    } finally {
      setLoading(false);
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
        fetchUsers();
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
    fetchUsers();
  }

  function copyPwd() {
    navigator.clipboard.writeText(tempPwd);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Admin" }, { label: "Usuários" }]} />
      <div className="afj-page-header">
        <div>
          <h1 className="font-display text-2xl font-semibold text-afj-black">Usuários</h1>
          <p className="text-afj-black/50 text-sm">Gerencie membros do escritório</p>
        </div>
        <button
          onClick={() => { setShowInvite(true); setTempPwd(""); setApiError(""); }}
          className="btn-afj-primary rounded-sm flex items-center gap-2"
        >
          <Plus size={14} />
          Convidar Usuário
        </button>
      </div>

      {loading ? (
        <div className="afj-card p-4 space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-14 bg-afj-cream-dark rounded animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="afj-card divide-y divide-afj-cream-dark">
          {users.map((u) => (
            <div key={u.id} className="flex items-center gap-4 px-5 py-4 hover:bg-afj-cream/30 transition-colors">
              <div className="w-9 h-9 rounded-full bg-afj-gold/15 border border-afj-gold/30 flex items-center justify-center flex-shrink-0">
                <span className="text-afj-gold text-sm font-bold">{u.full_name.slice(0, 1).toUpperCase()}</span>
              </div>
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
                </div>
                <p className="text-xs text-afj-black/40 truncate mt-0.5">{u.email}</p>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setEditUser(u)}
                  className="text-afj-black/35 hover:text-afj-gold transition-colors p-2 rounded-sm hover:bg-afj-gold/5"
                  aria-label="Editar usuário"
                >
                  <Pencil size={14} />
                </button>
                {u.id !== me?.id && (
                  <button
                    onClick={() => handleUpdate(u.id, { is_active: !u.is_active })}
                    className={`transition-colors p-2 rounded-sm ${
                      u.is_active
                        ? "text-afj-black/35 hover:text-red-500 hover:bg-red-50"
                        : "text-afj-black/35 hover:text-green-600 hover:bg-green-50"
                    }`}
                    aria-label={u.is_active ? "Desativar usuário" : "Reativar usuário"}
                    title={u.is_active ? "Desativar" : "Reativar"}
                  >
                    {u.is_active ? <UserX size={14} /> : <UserCheck size={14} />}
                  </button>
                )}
              </div>
            </div>
          ))}
          {users.length === 0 && (
            <div className="p-12 text-center">
              <Users size={28} className="mx-auto text-afj-black/15 mb-2" />
              <p className="text-sm text-afj-black/40">Nenhum usuário encontrado</p>
            </div>
          )}
        </div>
      )}

      {/* Modal — Convidar Usuário */}
      {showInvite && (
        <div
          className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
          onClick={(e) => { if (e.target === e.currentTarget) { setShowInvite(false); setTempPwd(""); } }}
        >
          <div className="bg-white rounded-sm shadow-xl max-w-md w-full p-6 space-y-4 animate-fade-in">
            <h3 className="font-display text-lg font-semibold text-afj-black">Convidar Usuário</h3>

            {tempPwd ? (
              <div className="space-y-4">
                <div className="p-4 bg-green-50 border border-green-200 rounded-sm">
                  <p className="text-sm font-semibold text-green-800 mb-1">Usuário criado!</p>
                  <p className="text-xs text-green-700 mb-3">
                    Compartilhe esta senha temporária. O usuário deverá alterá-la no primeiro acesso.
                  </p>
                  <div className="flex items-center gap-2 bg-white border border-green-200 rounded-sm px-3 py-2.5">
                    <code className="flex-1 text-sm font-mono text-afj-black select-all">{tempPwd}</code>
                    <button onClick={copyPwd} className="text-green-600 hover:text-green-700 flex-shrink-0" aria-label="Copiar senha">
                      {copied ? <Check size={14} /> : <Copy size={14} />}
                    </button>
                  </div>
                </div>
                <button onClick={() => { setShowInvite(false); setTempPwd(""); }} className="w-full btn-afj-primary rounded-sm">
                  Concluir
                </button>
              </div>
            ) : (
              <form onSubmit={handleInvite} className="space-y-4">
                {[
                  { label: "Nome Completo", key: "full_name", type: "text", placeholder: "Dr. João Silva" },
                  { label: "E-mail", key: "email", type: "email", placeholder: "joao@afj.adv.br" },
                ].map(({ label, key, type, placeholder }) => (
                  <div key={key}>
                    <label className="text-[10px] text-afj-black/55 block mb-1 uppercase tracking-widest font-semibold">{label}</label>
                    <input
                      type={type}
                      required
                      placeholder={placeholder}
                      value={(invite as Record<string, string>)[key]}
                      onChange={(e) => setInvite((i) => ({ ...i, [key]: e.target.value }))}
                      className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                    />
                  </div>
                ))}
                <div>
                  <label className="text-[10px] text-afj-black/55 block mb-1 uppercase tracking-widest font-semibold">Papel</label>
                  <select
                    value={invite.role}
                    onChange={(e) => setInvite((i) => ({ ...i, role: e.target.value }))}
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                  >
                    {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                </div>
                {apiError && <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-sm px-3 py-2">{apiError}</p>}
                <div className="flex gap-2 pt-1">
                  <button type="button" onClick={() => setShowInvite(false)} className="flex-1 btn-afj-outline rounded-sm">
                    Cancelar
                  </button>
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
        <div
          className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
          onClick={(e) => { if (e.target === e.currentTarget) setEditUser(null); }}
        >
          <div className="bg-white rounded-sm shadow-xl max-w-sm w-full p-6 space-y-4 animate-fade-in">
            <h3 className="font-display text-lg font-semibold text-afj-black">Editar Usuário</h3>
            <div>
              <label className="text-[10px] text-afj-black/55 block mb-1 uppercase tracking-widest font-semibold">Nome Completo</label>
              <input
                type="text"
                value={editUser.full_name}
                onChange={(e) => setEditUser((u) => u ? { ...u, full_name: e.target.value } : u)}
                className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
              />
            </div>
            <div>
              <label className="text-[10px] text-afj-black/55 block mb-1 uppercase tracking-widest font-semibold">Papel</label>
              <select
                value={editUser.role}
                onChange={(e) => setEditUser((u) => u ? { ...u, role: e.target.value } : u)}
                className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
              >
                {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>
            <div className="flex gap-2 pt-1">
              <button onClick={() => setEditUser(null)} className="flex-1 btn-afj-outline rounded-sm">Cancelar</button>
              <button
                onClick={() => handleUpdate(editUser.id, { full_name: editUser.full_name, role: editUser.role })}
                className="flex-1 btn-afj-primary rounded-sm"
              >
                Salvar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
