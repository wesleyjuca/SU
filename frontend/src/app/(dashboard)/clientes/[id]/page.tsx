"use client";
import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft, Users, Plus, MessageSquare, Phone, Mail, Scale,
  Loader2, X, AlertTriangle, Download, Trash2
} from "lucide-react";
import Link from "next/link";
import { Breadcrumb } from "@/components/layout/Breadcrumb";

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
  lgpd_consent_at: string | null;
  created_at: string;
}

interface Interaction {
  id: string;
  tipo: string;
  descricao: string;
  created_at: string;
}

interface Processo {
  id: string;
  numero_cnj: string | null;
  tribunal: string;
  area_direito: string | null;
  situacao: string;
}

const TIPO_ICONS: Record<string, string> = {
  EMAIL: "✉", LIGACAO: "📞", REUNIAO: "🤝", WHATSAPP: "💬", SISTEMA: "⚙",
};

const TIPO_INTERACAO = ["EMAIL", "LIGACAO", "REUNIAO", "WHATSAPP", "SISTEMA"];

const STATUS_STYLE: Record<string, string> = {
  PROSPECTO: "badge-pendente",
  ATIVO: "badge-ativo",
  INATIVO: "badge-arquivado",
};

const SITUACAO_STYLE: Record<string, string> = {
  ATIVO: "badge-ativo",
  SUSPENSO: "badge-pendente",
  ARQUIVADO: "badge-arquivado",
  ENCERRADO: "badge-arquivado",
};

export default function ClienteDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [cliente, setCliente] = useState<Cliente | null>(null);
  const [interactions, setInteractions] = useState<Interaction[]>([]);
  const [processos, setProcessos] = useState<Processo[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [saving, setSaving] = useState(false);
  const [confirmErase, setConfirmErase] = useState(false);
  const [interForm, setInterForm] = useState({ tipo: "EMAIL", descricao: "" });

  useEffect(() => { if (id) fetchAll(); }, [id]);

  async function fetchAll() {
    const token = localStorage.getItem("afj_access_token");
    const headers = { Authorization: `Bearer ${token}` };
    setLoading(true);
    try {
      const [cRes, iRes, pRes] = await Promise.all([
        fetch(`/api/v1/clients/${id}`, { headers }),
        fetch(`/api/v1/clients/${id}/interactions?limit=50`, { headers }),
        fetch(`/api/v1/processes?client_id=${id}`, { headers }),
      ]);
      if (cRes.ok) setCliente(await cRes.json());
      if (iRes.ok) setInteractions(await iRes.json());
      if (pRes.ok) setProcessos(await pRes.json());
    } finally { setLoading(false); }
  }

  async function registrarInteracao(e: React.FormEvent) {
    e.preventDefault();
    if (!interForm.descricao.trim()) return;
    setSaving(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/clients/${id}/interactions`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ tipo: interForm.tipo, descricao: interForm.descricao }),
      });
      if (res.ok) {
        setShowModal(false);
        setInterForm({ tipo: "EMAIL", descricao: "" });
        fetchAll();
      }
    } finally { setSaving(false); }
  }

  async function exportarDados() {
    const token = localStorage.getItem("afj_access_token");
    const res = await fetch(`/api/v1/lgpd/clients/${id}/export`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      const blob = await res.blob();
      const a = Object.assign(document.createElement("a"), {
        href: URL.createObjectURL(blob),
        download: `cliente_${id}_dados.json`,
      });
      a.click();
    }
  }

  async function apagarDados() {
    const token = localStorage.getItem("afj_access_token");
    const res = await fetch(`/api/v1/lgpd/clients/${id}/data`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      setConfirmErase(false);
      router.push("/clientes");
    }
  }

  if (loading) return (
    <div className="max-w-7xl mx-auto space-y-4">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Clientes", href: "/clientes" }, { label: "..." }]} />
      <div className="h-8 bg-afj-cream-dark rounded animate-pulse w-64" />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {[1, 2].map((i) => <div key={i} className="afj-card p-6 h-64 animate-pulse bg-afj-cream-dark/40" />)}
      </div>
    </div>
  );

  if (!cliente) return (
    <div className="max-w-7xl mx-auto">
      <div className="afj-card p-12 text-center">
        <Users className="mx-auto text-afj-black/20 mb-3" size={40} />
        <p className="font-semibold text-afj-black">Cliente não encontrado</p>
        <button onClick={() => router.back()} className="btn-afj-outline rounded-sm mt-4 text-sm">Voltar</button>
      </div>
    </div>
  );

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <Breadcrumb crumbs={[
        { label: "Dashboard", href: "/dashboard" },
        { label: "Clientes", href: "/clientes" },
        { label: cliente.nome_completo },
      ]} />

      {/* Header */}
      <div>
        <button onClick={() => router.back()} className="flex items-center gap-2 text-sm text-afj-black/50 hover:text-afj-black mb-3">
          <ArrowLeft size={14} />
          Voltar para Clientes
        </button>
        <div className="flex items-start justify-between">
          <div>
            <h1 className="font-display text-2xl font-semibold text-afj-black">{cliente.nome_completo}</h1>
            {cliente.razao_social && (
              <p className="text-afj-black/50 text-sm mt-0.5">{cliente.razao_social}</p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs bg-afj-cream px-2 py-0.5 rounded">{cliente.tipo}</span>
            <span className={STATUS_STYLE[cliente.status] ?? "badge-arquivado"}>{cliente.status}</span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Coluna esquerda: dados + processos */}
        <div className="space-y-4">
          {/* Dados cadastrais */}
          <div className="afj-card p-4">
            <h2 className="font-semibold text-afj-black text-sm mb-3">Dados Cadastrais</h2>
            <div className="space-y-2 text-sm">
              {cliente.email && (
                <div className="flex items-center gap-2">
                  <Mail size={13} className="text-afj-black/40 flex-shrink-0" />
                  <a href={`mailto:${cliente.email}`} className="text-afj-gold hover:underline">{cliente.email}</a>
                </div>
              )}
              {cliente.telefone && (
                <div className="flex items-center gap-2">
                  <Phone size={13} className="text-afj-black/40 flex-shrink-0" />
                  <span className="text-afj-black/70">{cliente.telefone}</span>
                </div>
              )}
              {cliente.whatsapp && (
                <div className="flex items-center gap-2">
                  <MessageSquare size={13} className="text-afj-black/40 flex-shrink-0" />
                  <span className="text-afj-black/70">{cliente.whatsapp}</span>
                </div>
              )}
              {[
                { label: "Origem", value: cliente.origem },
                {
                  label: "LGPD",
                  value: cliente.lgpd_consent
                    ? `Consentido${cliente.lgpd_consent_at ? " em " + new Date(cliente.lgpd_consent_at).toLocaleDateString("pt-BR") : ""}`
                    : "Não consentido",
                },
                {
                  label: "Cadastrado em",
                  value: new Date(cliente.created_at).toLocaleDateString("pt-BR"),
                },
              ].map(({ label, value }) => value && (
                <div key={label} className="flex justify-between gap-2 pt-1 border-t border-afj-cream-dark/50">
                  <span className="text-afj-black/50">{label}</span>
                  <span className="text-afj-black text-right text-xs font-medium">{value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Processos vinculados */}
          <div className="afj-card p-4">
            <h2 className="font-semibold text-afj-black text-sm mb-3 flex items-center gap-2">
              <Scale size={13} />
              Processos Vinculados ({processos.length})
            </h2>
            {processos.length === 0 ? (
              <p className="text-xs text-afj-black/40">Nenhum processo vinculado</p>
            ) : (
              <div className="space-y-2">
                {processos.map((p) => (
                  <Link
                    key={p.id}
                    href={`/processos/${p.id}`}
                    className="flex items-center justify-between text-xs p-2 rounded-sm border border-afj-cream-dark hover:border-afj-gold/40 hover:bg-afj-cream/30 transition-colors"
                  >
                    <div>
                      <p className="font-mono font-medium text-afj-black">{p.numero_cnj || "Sem CNJ"}</p>
                      <p className="text-afj-black/50">{p.tribunal}{p.area_direito ? ` · ${p.area_direito}` : ""}</p>
                    </div>
                    <span className={SITUACAO_STYLE[p.situacao] ?? "badge-arquivado"}>{p.situacao}</span>
                  </Link>
                ))}
              </div>
            )}
          </div>

          {/* Ações LGPD */}
          <div className="afj-card p-4 border border-red-100">
            <h2 className="font-semibold text-afj-black text-sm mb-2">Direitos LGPD</h2>
            <p className="text-xs text-afj-black/50 mb-3">
              Conforme arts. 18 e 20 da LGPD — Lei 13.709/2018
            </p>
            <div className="flex gap-2">
              <button
                onClick={exportarDados}
                className="btn-afj-outline rounded-sm flex items-center gap-1.5 text-xs"
              >
                <Download size={12} />
                Exportar Dados
              </button>
              <button
                onClick={() => setConfirmErase(true)}
                className="text-xs px-3 py-2 border border-red-200 text-red-600 rounded-sm hover:bg-red-50 flex items-center gap-1.5 transition-colors"
              >
                <Trash2 size={12} />
                Apagar Dados
              </button>
            </div>
          </div>
        </div>

        {/* Coluna direita: histórico de interações */}
        <div className="afj-card p-4 flex flex-col">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-afj-black text-sm flex items-center gap-2">
              <MessageSquare size={14} />
              Histórico de Interações ({interactions.length})
            </h2>
            <button
              onClick={() => setShowModal(true)}
              className="btn-afj-primary rounded-sm flex items-center gap-1.5 text-xs"
            >
              <Plus size={12} />
              Registrar
            </button>
          </div>

          {interactions.length === 0 ? (
            <div className="flex-1 flex items-center justify-center text-center py-8">
              <div>
                <MessageSquare className="mx-auto text-afj-black/20 mb-2" size={28} />
                <p className="text-sm text-afj-black/40">Nenhuma interação registrada</p>
              </div>
            </div>
          ) : (
            <div className="space-y-3 overflow-y-auto">
              {interactions.map((i) => (
                <div key={i.id} className="flex gap-3 text-sm">
                  <div className="w-7 h-7 rounded-full bg-afj-cream flex items-center justify-center flex-shrink-0 text-base">
                    {TIPO_ICONS[i.tipo] ?? "•"}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-medium text-afj-black/60 uppercase tracking-wide">{i.tipo}</span>
                      <span className="text-xs text-afj-black/30 flex-shrink-0">
                        {new Date(i.created_at).toLocaleDateString("pt-BR", { day: "2-digit", month: "short" })}
                      </span>
                    </div>
                    <p className="text-afj-black/80 mt-0.5 leading-snug">{i.descricao}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Modal: Registrar Interação */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-sm shadow-xl w-full max-w-md">
            <div className="flex items-center justify-between px-5 py-4 border-b border-afj-cream-dark">
              <h2 className="font-semibold text-afj-black">Registrar Interação</h2>
              <button onClick={() => setShowModal(false)} className="text-afj-black/40 hover:text-afj-black">
                <X size={18} />
              </button>
            </div>
            <form onSubmit={registrarInteracao} className="p-5 space-y-4">
              <div>
                <label className="text-xs text-afj-black/60 block mb-1">Tipo</label>
                <select
                  value={interForm.tipo}
                  onChange={(e) => setInterForm({ ...interForm, tipo: e.target.value })}
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                >
                  {TIPO_INTERACAO.map((t) => (
                    <option key={t} value={t}>{TIPO_ICONS[t]} {t}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs text-afj-black/60 block mb-1">Descrição *</label>
                <textarea
                  required
                  value={interForm.descricao}
                  onChange={(e) => setInterForm({ ...interForm, descricao: e.target.value })}
                  rows={4}
                  placeholder="Descreva o contato realizado..."
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold resize-none"
                />
              </div>
              <div className="flex gap-3">
                <button type="button" onClick={() => setShowModal(false)} className="flex-1 btn-afj-outline rounded-sm">
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={saving || !interForm.descricao.trim()}
                  className="flex-1 btn-afj-primary rounded-sm flex items-center justify-center gap-2 disabled:opacity-40"
                >
                  {saving ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
                  Registrar
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Confirmação apagar dados LGPD */}
      {confirmErase && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-sm shadow-xl w-full max-w-sm p-6">
            <div className="flex items-center gap-3 mb-4">
              <AlertTriangle className="text-red-500 flex-shrink-0" size={22} />
              <h2 className="font-semibold text-afj-black">Ação Irreversível</h2>
            </div>
            <p className="text-sm text-afj-black/70 mb-4">
              Todos os dados pessoais deste cliente serão anonimizados permanentemente (LGPD art. 18 §3).
              Esta ação <strong>não pode ser desfeita</strong>.
            </p>
            <div className="flex gap-3">
              <button onClick={() => setConfirmErase(false)} className="flex-1 btn-afj-outline rounded-sm">
                Cancelar
              </button>
              <button
                onClick={apagarDados}
                className="flex-1 bg-red-600 text-white text-xs uppercase tracking-wider rounded-sm py-2 hover:bg-red-700 transition-colors"
              >
                Confirmar Exclusão
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
