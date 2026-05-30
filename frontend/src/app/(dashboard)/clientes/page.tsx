"use client";
import { useState, useEffect } from "react";
import { Users, Plus, Search, Phone, Mail, Pencil, Trash2, ExternalLink } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { useToast } from "@/components/ui/Toast";
import { ViewToggle } from "@/components/ui/ViewToggle";
import Link from "next/link";

interface Cliente {
  id: string;
  tipo: string;
  nome_completo: string;
  razao_social: string | null;
  email: string | null;
  telefone: string | null;
  whatsapp: string | null;
  status: string;
  origem: string | null;
  lgpd_consent: boolean;
  created_at: string;
}

const STATUS_STYLE: Record<string, string> = {
  PROSPECTO: "badge-pendente",
  ATIVO: "badge-ativo",
  INATIVO: "badge-arquivado",
};

export default function ClientesPage() {
  const toast = useToast();
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<Partial<Cliente>>({});
  const [form, setForm] = useState({ tipo: "PF", nome_completo: "", email: "", telefone: "", whatsapp: "", status: "PROSPECTO", origem: "", lgpd_consent: false });
  const [view, setView] = useState<"table" | "grid">(() => {
    if (typeof window !== "undefined") {
      return (localStorage.getItem("clientes_view") as "table" | "grid") ?? "grid";
    }
    return "grid";
  });

  useEffect(() => {
    localStorage.setItem("clientes_view", view);
  }, [view]);

  useEffect(() => { fetchClientes(); }, [status]);

  async function fetchClientes() {
    setLoading(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const params = new URLSearchParams();
      if (status) params.set("status", status);
      const res = await fetch(`/api/v1/clients?${params}`, { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) setClientes(await res.json());
    } finally { setLoading(false); }
  }

  async function salvarEdicao() {
    if (!editingId) return;
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/clients/${editingId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(editForm),
      });
      if (res.ok) { setEditingId(null); fetchClientes(); }
      else toast.error("Erro ao salvar cliente. Tente novamente.");
    } catch {
      toast.error("Erro de conexão. Tente novamente.");
    }
  }

  async function excluirCliente(id: string) {
    const token = localStorage.getItem("afj_access_token");
    const res = await fetch(`/api/v1/clients/${id}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) { setDeletingId(null); fetchClientes(); }
  }

  async function salvarCliente(e: React.FormEvent) {
    e.preventDefault();
    const token = localStorage.getItem("afj_access_token");
    const res = await fetch("/api/v1/clients", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify(form),
    });
    if (res.ok) { setShowModal(false); fetchClientes(); }
  }

  const filtrados = clientes.filter((c) =>
    !search || c.nome_completo.toLowerCase().includes(search.toLowerCase()) || c.email?.includes(search)
  );

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Clientes" }]} />
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-semibold text-afj-black">Clientes</h1>
          <p className="text-afj-black/50 text-sm">{filtrados.length} cliente(s)</p>
        </div>
        <div className="flex items-center gap-3">
          <ViewToggle view={view} onChange={setView} />
          <button onClick={() => setShowModal(true)} className="btn-afj-primary rounded-sm flex items-center gap-2">
            <Plus size={15} />Novo Cliente
          </button>
        </div>
      </div>

      {/* Filtros */}
      <div className="flex gap-3">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-afj-black/30" />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Buscar por nome ou email..." className="w-full pl-9 pr-4 py-2 text-sm border border-afj-cream-dark rounded-sm focus:outline-none focus:border-afj-gold bg-white" />
        </div>
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="border border-afj-cream-dark rounded-sm px-3 py-2 text-sm bg-white focus:outline-none focus:border-afj-gold">
          <option value="">Todos os status</option>
          <option value="PROSPECTO">Prospecto</option>
          <option value="ATIVO">Ativo</option>
          <option value="INATIVO">Inativo</option>
        </select>
      </div>

      {loading ? (
        view === "grid" ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="afj-card p-4 h-36 animate-pulse bg-afj-cream-dark/40" />
            ))}
          </div>
        ) : (
          <div className="afj-card p-4 space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-11 bg-afj-cream-dark rounded animate-pulse" />
            ))}
          </div>
        )
      ) : filtrados.length === 0 ? (
        <div className="afj-card p-12 text-center">
          <Users className="mx-auto text-afj-black/20 mb-3" size={40} />
          <p className="font-semibold text-afj-black">Nenhum cliente cadastrado</p>
          <button onClick={() => setShowModal(true)} className="btn-afj-primary rounded-sm mt-4 text-sm">Cadastrar primeiro cliente</button>
        </div>
      ) : view === "grid" ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtrados.map((c) => (
            <div key={c.id} className="afj-card p-4 hover:border-afj-gold/30 transition-colors cursor-pointer">
              <div className="flex items-start justify-between mb-2">
                <span className={`text-xs px-2 py-0.5 rounded-full ${c.tipo === "PF" ? "bg-blue-100 text-blue-700" : "bg-purple-100 text-purple-700"}`}>{c.tipo}</span>
                <span className={STATUS_STYLE[c.status] ?? "badge-arquivado"}>{c.status}</span>
              </div>
              <p className="font-semibold text-afj-black text-sm mt-2">{c.nome_completo}</p>
              {c.razao_social && <p className="text-xs text-afj-black/50">{c.razao_social}</p>}
              <div className="mt-3 space-y-1">
                {c.email && <p className="text-xs text-afj-black/60 flex items-center gap-1.5"><Mail size={11} />{c.email}</p>}
                {c.telefone && <p className="text-xs text-afj-black/60 flex items-center gap-1.5"><Phone size={11} />{c.telefone}</p>}
              </div>
              <div className="mt-3 pt-2 border-t border-afj-cream-dark flex items-center justify-between">
                <span className="text-xs text-afj-black/30">{c.origem || "Origem não informada"}</span>
                <div className="flex items-center gap-2">
                  {!c.lgpd_consent && <span className="text-xs text-amber-600">⚠ LGPD</span>}
                  <Link href={`/clientes/${c.id}`} className="text-afj-black/30 hover:text-afj-gold transition-colors" aria-label="Ver detalhes"><ExternalLink size={12} /></Link>
                  <button onClick={() => { setEditingId(c.id); setEditForm({ nome_completo: c.nome_completo, email: c.email ?? "", telefone: c.telefone ?? "", whatsapp: c.whatsapp ?? "", razao_social: c.razao_social ?? "", status: c.status, lgpd_consent: c.lgpd_consent, tipo: c.tipo }); }} className="text-afj-black/30 hover:text-afj-gold transition-colors" aria-label="Editar cliente"><Pencil size={12} /></button>
                  <button onClick={() => setDeletingId(c.id)} className="text-afj-black/30 hover:text-red-500 transition-colors" aria-label="Remover cliente"><Trash2 size={12} /></button>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="afj-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="afj-table">
              <thead>
                <tr>
                  <th>Nome</th>
                  <th>Tipo</th>
                  <th>Status</th>
                  <th>E-mail</th>
                  <th>Telefone</th>
                  <th>Origem</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {filtrados.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <div>
                        <p className="font-medium text-afj-black text-sm">{c.nome_completo}</p>
                        {c.razao_social && <p className="text-xs text-afj-black/50">{c.razao_social}</p>}
                      </div>
                    </td>
                    <td>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${c.tipo === "PF" ? "bg-blue-100 text-blue-700" : "bg-purple-100 text-purple-700"}`}>{c.tipo}</span>
                    </td>
                    <td>
                      <span className={STATUS_STYLE[c.status] ?? "badge-arquivado"}>{c.status}</span>
                    </td>
                    <td className="text-afj-black/60 text-xs">{c.email || "—"}</td>
                    <td className="text-afj-black/60 text-xs">{c.telefone || "—"}</td>
                    <td className="text-afj-black/40 text-xs">{c.origem || "—"}</td>
                    <td>
                      <div className="flex items-center gap-2">
                        {!c.lgpd_consent && <span className="text-xs text-amber-600">⚠</span>}
                        <Link href={`/clientes/${c.id}`} className="text-afj-black/30 hover:text-afj-gold transition-colors" aria-label="Ver detalhes"><ExternalLink size={12} /></Link>
                        <button onClick={() => { setEditingId(c.id); setEditForm({ nome_completo: c.nome_completo, email: c.email ?? "", telefone: c.telefone ?? "", whatsapp: c.whatsapp ?? "", razao_social: c.razao_social ?? "", status: c.status, lgpd_consent: c.lgpd_consent, tipo: c.tipo }); }} className="text-afj-black/30 hover:text-afj-gold transition-colors" aria-label="Editar cliente"><Pencil size={12} /></button>
                        <button onClick={() => setDeletingId(c.id)} className="text-afj-black/30 hover:text-red-500 transition-colors" aria-label="Remover cliente"><Trash2 size={12} /></button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Modal edição cliente */}
      {editingId && (
        <div className="fixed inset-0 bg-afj-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-sm p-6 w-full max-w-md shadow-2xl">
            <h2 className="font-display text-lg font-semibold text-afj-black mb-4">Editar Cliente</h2>
            <div className="space-y-3">
              {[
                { label: "Nome Completo", key: "nome_completo", type: "text" },
                { label: "E-mail", key: "email", type: "email" },
                { label: "Telefone", key: "telefone", type: "tel" },
                { label: "WhatsApp", key: "whatsapp", type: "tel" },
              ].map(({ label, key, type }) => (
                <div key={key}>
                  <label className="text-xs text-afj-black/60 block mb-1">{label}</label>
                  <input type={type} value={(editForm as Record<string, string>)[key] ?? ""} onChange={(e) => setEditForm({ ...editForm, [key]: e.target.value })}
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold" />
                </div>
              ))}
              {editForm.tipo === "PJ" && (
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">Razão Social</label>
                  <input type="text" value={editForm.razao_social ?? ""} onChange={(e) => setEditForm({ ...editForm, razao_social: e.target.value })}
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold" />
                </div>
              )}
              <div>
                <label className="text-xs text-afj-black/60 block mb-1">Status</label>
                <select value={editForm.status ?? ""} onChange={(e) => setEditForm({ ...editForm, status: e.target.value })}
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold">
                  <option value="PROSPECTO">Prospecto</option>
                  <option value="ATIVO">Ativo</option>
                  <option value="INATIVO">Inativo</option>
                </select>
              </div>
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" checked={!!editForm.lgpd_consent} onChange={(e) => setEditForm({ ...editForm, lgpd_consent: e.target.checked })} />
                <span className="text-afj-black/70">Consentimento LGPD coletado</span>
              </label>
            </div>
            <div className="flex gap-3 mt-5">
              <button onClick={() => setEditingId(null)} className="flex-1 btn-afj-outline rounded-sm">Cancelar</button>
              <button onClick={salvarEdicao} className="flex-1 btn-afj-primary rounded-sm">Salvar</button>
            </div>
          </div>
        </div>
      )}

      {/* Modal confirmação exclusão */}
      {deletingId && (
        <div className="fixed inset-0 bg-afj-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-sm p-6 w-full max-w-sm shadow-2xl text-center">
            <p className="font-semibold text-afj-black mb-2">Remover cliente?</p>
            <p className="text-afj-black/50 text-sm mb-5">Os dados serão anonimizados conforme a LGPD.</p>
            <div className="flex gap-3">
              <button onClick={() => setDeletingId(null)} className="flex-1 btn-afj-outline rounded-sm">Cancelar</button>
              <button onClick={() => excluirCliente(deletingId)} className="flex-1 bg-red-500 text-white rounded-sm py-2 text-sm font-medium hover:bg-red-600">Remover</button>
            </div>
          </div>
        </div>
      )}

      {/* Modal novo cliente */}
      {showModal && (
        <div className="fixed inset-0 bg-afj-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-sm p-6 w-full max-w-lg shadow-2xl">
            <h2 className="font-display text-xl font-semibold text-afj-black mb-5">Novo Cliente</h2>
            <form onSubmit={salvarCliente} className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">Tipo *</label>
                  <select value={form.tipo} onChange={(e) => setForm({...form, tipo: e.target.value})} className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold">
                    <option value="PF">Pessoa Física</option>
                    <option value="PJ">Pessoa Jurídica</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">Status</label>
                  <select value={form.status} onChange={(e) => setForm({...form, status: e.target.value})} className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold">
                    <option value="PROSPECTO">Prospecto</option>
                    <option value="ATIVO">Ativo</option>
                  </select>
                </div>
              </div>
              {[
                { label: "Nome Completo *", key: "nome_completo", type: "text" },
                { label: "E-mail", key: "email", type: "email" },
                { label: "Telefone", key: "telefone", type: "tel" },
                { label: "WhatsApp", key: "whatsapp", type: "tel" },
                { label: "Origem", key: "origem", type: "text" },
              ].map(({ label, key, type }) => (
                <div key={key}>
                  <label className="text-xs text-afj-black/60 block mb-1">{label}</label>
                  <input type={type} value={(form as any)[key]} onChange={(e) => setForm({...form, [key]: e.target.value})} className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold" required={label.includes("*")} />
                </div>
              ))}
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={form.lgpd_consent} onChange={(e) => setForm({...form, lgpd_consent: e.target.checked})} />
                <span>Consentimento LGPD coletado</span>
              </label>
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => setShowModal(false)} className="flex-1 btn-afj-outline rounded-sm">Cancelar</button>
                <button type="submit" className="flex-1 btn-afj-primary rounded-sm">Salvar</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
