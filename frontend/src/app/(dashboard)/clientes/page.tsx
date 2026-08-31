"use client";
import { useState, useEffect, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { Users, Plus, Search, Phone, Mail, Pencil, Trash2, ExternalLink, Filter, ShieldAlert, ChevronDown, ChevronUp, ShieldCheck, Upload, X, CheckCircle } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { useToast } from "@/components/ui/Toast";
import { ViewToggle } from "@/components/ui/ViewToggle";
import { useUserStore } from "@/store";
import { ClienteFormFields, statusLocalizacaoDe, type ClienteFormValues, type Endereco } from "@/components/clientes/ClienteFormFields";
import { ClientPortalAccessPanel } from "@/components/clientes/ClientPortalAccessPanel";
import Link from "next/link";

type Aba = "clientes" | "controle-portal";

interface Cliente {
  id: string;
  tipo: string;
  nome_completo: string;
  razao_social: string | null;
  email: string | null;
  telefone: string | null;
  whatsapp: string | null;
  cpf: string | null;
  cnpj: string | null;
  endereco_json: Endereco | null;
  observacoes: string | null;
  status: string;
  origem: string | null;
  lgpd_consent: boolean;
  created_at: string;
}

const ENDERECO_VAZIO: Endereco = { cep: "", logradouro: "", bairro: "", cidade: "", uf: "" };
const FORM_VAZIO: ClienteFormValues = {
  tipo: "PF", nome_completo: "", razao_social: "", email: "", telefone: "", whatsapp: "",
  origem: "", cpf: "", cnpj: "", status: "PROSPECTO", lgpd_consent: false, observacoes: "",
};

const STATUS_STYLE: Record<string, string> = {
  PROSPECTO: "badge-pendente",
  ATIVO: "badge-ativo",
  INATIVO: "badge-arquivado",
};

const PAGE_SIZE = 50;

interface LgpdQualidade {
  total_clientes: number;
  score_conformidade: number;
  taxa_consentimento: number | null;
  lacunas: {
    sem_consentimento_ativo: { total: number };
    consentimento_sem_data: { total: number };
    sem_documento_identificacao: { total: number };
  };
}

export default function ClientesPage() {
  const toast = useToast();
  const searchParams = useSearchParams();
  const [aba, setAba] = useState<Aba>("clientes");
  useEffect(() => {
    const daUrl = searchParams.get("aba");
    if (daUrl === "controle-portal") setAba("controle-portal");
  }, [searchParams]);
  const userRole = useUserStore((s) => s.user?.role);
  const canSeeLgpd = ["ADMIN", "SOCIO", "SUPERADMIN"].includes(userRole ?? "");
  // Reformulação — o botão de excluir agora aciona o esquecimento LGPD de
  // verdade (ver excluirCliente), que no backend exige ADMIN
  // (require_role("ADMIN"), lgpd.py — SUPERADMIN passa como superconjunto,
  // dependencies.py) — antes não tinha gate nenhum aqui.
  //
  // Fase 236 — achado real: esta comparação estrita excluía SUPERADMIN,
  // ao contrário de TODO outro gate "ADMIN" do frontend (inclusive
  // canSeeLgpd 4 linhas acima, no mesmo arquivo) e do próprio backend
  // (require_role trata SUPERADMIN como superconjunto de ADMIN). Um
  // SUPERADMIN clicando "Portal" no Cliente 360 nunca via a aba Controle
  // de Clientes aparecer — o useEffect de defesa logo abaixo revertia a
  // navegação, reproduzido ao vivo via Playwright antes deste fix.
  const isAdmin = userRole === "ADMIN" || userRole === "SUPERADMIN";
  // Fase 245 (achado do diagnóstico de cadastros) — mesmo gate do backend
  // pra POST /clients/importar-csv (ADMIN/SOCIO/GESTOR).
  const canImportar = ["ADMIN", "SOCIO", "GESTOR", "SUPERADMIN"].includes(userRole ?? "");
  const importInputRef = useRef<HTMLInputElement>(null);
  const [importando, setImportando] = useState(false);
  const [importResultado, setImportResultado] = useState<{
    total_linhas: number; criados: number; duplicados: number; erros: number;
    detalhes: { linha: number; nome?: string; status: string; detalhe?: string }[];
  } | null>(null);
  // Defesa: link antigo/query param forçado apontando pra Controle de
  // Clientes sem ser ADMIN nunca deixa a aba restrita "vazar".
  useEffect(() => {
    if (aba === "controle-portal" && !isAdmin) setAba("clientes");
  }, [aba, isAdmin]);
  const [lgpdQualidade, setLgpdQualidade] = useState<LgpdQualidade | null>(null);
  const [showLgpdDetalhes, setShowLgpdDetalhes] = useState(false);
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [showModal, setShowModal] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [editForm, setEditForm] = useState<Partial<Cliente>>({});
  const [editEndereco, setEditEndereco] = useState<Endereco>(ENDERECO_VAZIO);
  const [form, setForm] = useState<ClienteFormValues>(FORM_VAZIO);
  const [endereco, setEndereco] = useState<Endereco>(ENDERECO_VAZIO);
  // Fase 253 — CEP do cliente no instante em que o modal de edição foi
  // aberto, pra `statusLocalizacaoDe` saber distinguir "coordenada
  // capturada pro endereço atual" de "usuário trocou o CEP nesta edição,
  // ainda não salvou" (mostra "será recalculada ao salvar" em vez de
  // reafirmar uma confirmação que já não é mais verdadeira pro CEP novo).
  const editEnderecoCepOriginalRef = useRef("");
  const [recalculando, setRecalculando] = useState(false);
  const [docSugestao, setDocSugestao] = useState<string | null>(null);
  const [editDocSugestao, setEditDocSugestao] = useState<string | null>(null);
  const [view, setView] = useState<"table" | "grid">(() => {
    if (typeof window !== "undefined") {
      return (localStorage.getItem("clientes_view") as "table" | "grid") ?? "grid";
    }
    return "grid";
  });

  useEffect(() => {
    localStorage.setItem("clientes_view", view);
  }, [view]);

  useEffect(() => { fetchClientes(0, false); }, [status]);

  useEffect(() => {
    if (!canSeeLgpd) return;
    const token = localStorage.getItem("afj_access_token");
    fetch("/api/v1/system/analytics/lgpd-qualidade", { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.json() : null))
      .then(setLgpdQualidade)
      .catch(() => {});
  }, [canSeeLgpd]);

  async function fetchClientes(newOffset = 0, append = false) {
    if (append) setLoadingMore(true);
    else setLoading(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const params = new URLSearchParams();
      if (status) params.set("status", status);
      params.set("limit", String(PAGE_SIZE));
      params.set("offset", String(newOffset));
      const res = await fetch(`/api/v1/clients?${params}`, { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) {
        const data: Cliente[] = await res.json();
        setClientes((prev) => append ? [...prev, ...data] : data);
        setHasMore(data.length === PAGE_SIZE);
        setOffset(newOffset + data.length);
      }
    } finally {
      if (append) setLoadingMore(false);
      else setLoading(false);
    }
  }

  async function importarCsv(f: File) {
    setImportando(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const formData = new FormData();
      formData.append("file", f);
      const res = await fetch("/api/v1/clients/importar-csv", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      const d = await res.json().catch(() => ({}));
      if (res.ok) {
        setImportResultado(d);
        fetchClientes();
      } else {
        toast.error(d.detail || "Erro ao importar CSV.");
      }
    } catch {
      toast.error("Erro de conexão ao importar CSV.");
    } finally {
      setImportando(false);
      if (importInputRef.current) importInputRef.current.value = "";
    }
  }

  function abrirEdicao(c: Cliente) {
    setEditingId(c.id);
    setEditForm({
      nome_completo: c.nome_completo, email: c.email ?? "", telefone: c.telefone ?? "",
      whatsapp: c.whatsapp ?? "", razao_social: c.razao_social ?? "", cpf: c.cpf ?? "",
      cnpj: c.cnpj ?? "", origem: c.origem ?? "", observacoes: c.observacoes ?? "",
      status: c.status, lgpd_consent: c.lgpd_consent, tipo: c.tipo,
    });
    setEditEndereco({ ...ENDERECO_VAZIO, ...(c.endereco_json ?? {}) });
    editEnderecoCepOriginalRef.current = c.endereco_json?.cep ?? "";
    setEditDocSugestao(null);
  }

  async function recalcularLocalizacao() {
    if (!editingId) return;
    setRecalculando(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/clients/${editingId}/recalcular-localizacao`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const d = await res.json().catch(() => ({}));
      if (res.ok) {
        const novoEndereco = { ...ENDERECO_VAZIO, ...(d.endereco_json ?? {}) };
        setEditEndereco(novoEndereco);
        editEnderecoCepOriginalRef.current = novoEndereco.cep ?? "";
        const geocodificado = novoEndereco.latitude != null && novoEndereco.longitude != null;
        if (geocodificado) toast.success("Localização recalculada.");
        else toast.warning("Não foi possível geocodificar este CEP agora — tente novamente mais tarde.");
      } else {
        toast.error(d.detail || "Erro ao recalcular localização.");
      }
    } catch {
      toast.error("Erro de conexão.");
    } finally {
      setRecalculando(false);
    }
  }

  async function salvarEdicao() {
    if (!editingId) return;
    setSalvando(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/clients/${editingId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ ...editForm, endereco_json: editEndereco }),
      });
      if (res.ok) {
        const saved = await res.json();
        const geocodificado = saved.endereco_json?.latitude != null && saved.endereco_json?.longitude != null;
        toast.success(geocodificado ? "Cliente salvo — localização geográfica capturada." : "Cliente salvo.");
        setEditingId(null);
        fetchClientes(0, false);
      } else {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail || "Erro ao salvar cliente. Tente novamente.");
      }
    } catch {
      toast.error("Erro de conexão. Tente novamente.");
    } finally {
      setSalvando(false);
    }
  }

  // Reformulação — antes chamava DELETE /clients/{id}, que só limpa
  // cpf/cnpj/email/telefone/whatsapp e marca INATIVO (`nome_completo`,
  // observações, contatos, interações, oportunidades e o log de auditoria
  // SERPRO continuavam intactos) — desalinhado com o texto do próprio
  // modal de confirmação, que já prometia esquecimento LGPD completo.
  // Agora aciona o mesmo endpoint que a página de detalhe do cliente já
  // usa corretamente (clientes/[id]/page.tsx::apagarDados).
  async function excluirCliente(id: string) {
    setSalvando(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch(`/api/v1/lgpd/clients/${id}/data`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) { setDeletingId(null); fetchClientes(0, false); }
      else toast.error("Erro ao remover cliente. Tente novamente.");
    } catch {
      toast.error("Erro de conexão. Tente novamente.");
    } finally {
      setSalvando(false);
    }
  }

  // Fase 217 — valida/enriquece CPF ou CNPJ contra a Loja SERPRO no blur do
  // campo. Nunca bloqueia o cadastro: `data.valido` pode vir `null` quando a
  // validação está indisponível, e a mensagem (formato inválido, indisponível
  // ou nome/situação encontrados) vem sempre de `data.mensagem`/dados da
  // SERPRO — o backend (Fase 220) já valida formato antes de bater SERPRO.
  async function validarDocumento(tipo: "cpf" | "cnpj", valor: string, setSugestao: (s: string | null) => void) {
    if (!valor.trim()) { setSugestao(null); return; }
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/clients/validar-documento", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ tipo, valor }),
      });
      if (!res.ok) { setSugestao(null); return; }
      const data = await res.json();
      if (data.valido && data.nome_ou_razao_social) {
        setSugestao(`${data.nome_ou_razao_social}${data.situacao_cadastral ? ` — ${data.situacao_cadastral}` : ""}`);
      } else {
        setSugestao(data.mensagem ?? null);
      }
    } catch { setSugestao(null); }
  }

  // Fase 217 — autofill de endereço a partir do CEP (BrasilAPI, fonte
  // pública gratuita, não-governamental). Só preenche campos ainda vazios,
  // nunca sobrescreve o que o usuário já digitou.
  async function autofillCep(cep: string, atual: Endereco, setEnd: (e: Endereco) => void) {
    if (!cep || cep.replace(/\D/g, "").length !== 8) return;
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/clients/consultar-cep", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ cep }),
      });
      if (!res.ok) return;
      const data = await res.json();
      if (data.logradouro || data.cidade) {
        setEnd({
          ...atual,
          logradouro: atual.logradouro || data.logradouro || "",
          bairro: atual.bairro || data.bairro || "",
          cidade: atual.cidade || data.cidade || "",
          uf: atual.uf || data.uf || "",
        });
      }
    } catch { /* fail-soft — endereço continua editável manualmente */ }
  }

  async function salvarCliente(e: React.FormEvent) {
    e.preventDefault();
    setSalvando(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/clients", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ ...form, endereco_json: endereco }),
      });
      if (res.ok) {
        const saved = await res.json();
        const geocodificado = saved.endereco_json?.latitude != null && saved.endereco_json?.longitude != null;
        toast.success(geocodificado ? "Cliente criado — localização geográfica capturada." : "Cliente criado.");
        setShowModal(false);
        setForm(FORM_VAZIO);
        setEndereco(ENDERECO_VAZIO);
        fetchClientes(0, false);
      } else {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail || "Erro ao criar cliente. Tente novamente.");
      }
    } catch {
      toast.error("Erro de conexão. Tente novamente.");
    } finally {
      setSalvando(false);
    }
  }

  const filtrados = clientes.filter((c) =>
    !search || c.nome_completo.toLowerCase().includes(search.toLowerCase()) || c.email?.includes(search)
  );

  const editValues: ClienteFormValues = {
    tipo: editForm.tipo ?? "PF",
    nome_completo: editForm.nome_completo ?? "",
    razao_social: editForm.razao_social ?? "",
    email: editForm.email ?? "",
    telefone: editForm.telefone ?? "",
    whatsapp: editForm.whatsapp ?? "",
    origem: editForm.origem ?? "",
    cpf: editForm.cpf ?? "",
    cnpj: editForm.cnpj ?? "",
    status: editForm.status ?? "PROSPECTO",
    lgpd_consent: editForm.lgpd_consent ?? false,
    observacoes: editForm.observacoes ?? "",
  };

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Clientes" }]} />
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-semibold text-afj-black">Clientes</h1>
          <p className="text-afj-black/50 text-sm">
            {aba === "clientes" ? `${filtrados.length} cliente(s)` : "Gerencie o acesso dos clientes ao Portal"}
          </p>
        </div>
        {aba === "clientes" && (
          <div className="flex items-center gap-3">
            <Link href="/clientes/funil" className="btn-afj-outline rounded-sm flex items-center gap-2" title="Funil de vendas">
              <Filter size={15} />Funil
            </Link>
            <ViewToggle view={view} onChange={setView} />
            {canImportar && (
              <>
                <input
                  ref={importInputRef}
                  type="file"
                  accept=".csv"
                  className="hidden"
                  onChange={(e) => { const f = e.target.files?.[0]; if (f) importarCsv(f); }}
                />
                <button
                  onClick={() => importInputRef.current?.click()}
                  disabled={importando}
                  className="btn-afj-outline rounded-sm flex items-center gap-2 disabled:opacity-50"
                  title="Importar clientes de um arquivo CSV"
                >
                  <Upload size={15} />{importando ? "Importando..." : "Importar CSV"}
                </button>
              </>
            )}
            <button onClick={() => { setShowModal(true); setDocSugestao(null); }} className="btn-afj-primary rounded-sm flex items-center gap-2">
              <Plus size={15} />Novo Cliente
            </button>
          </div>
        )}
      </div>

      {/* Fase 234 — Controle de Clientes: acesso ao Portal via link temporário */}
      {isAdmin && (
        <div className="flex items-center gap-1 border-b border-afj-cream-dark">
          <button
            onClick={() => setAba("clientes")}
            className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              aba === "clientes" ? "border-afj-gold text-afj-gold" : "border-transparent text-afj-black/50 hover:text-afj-black"
            }`}
          >
            Clientes
          </button>
          <button
            onClick={() => setAba("controle-portal")}
            className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px flex items-center gap-1.5 transition-colors ${
              aba === "controle-portal" ? "border-afj-gold text-afj-gold" : "border-transparent text-afj-black/50 hover:text-afj-black"
            }`}
          >
            <ShieldCheck size={13} />
            Controle de Clientes
          </button>
        </div>
      )}

      {aba === "controle-portal" && isAdmin && <ClientPortalAccessPanel />}

      {aba === "clientes" && (
      <>
      {/* Qualidade LGPD (Fase 212 — proposta de evolução da Fase 209) */}
      {canSeeLgpd && lgpdQualidade && lgpdQualidade.total_clientes > 0 && (
        <div className="afj-card p-3">
          <button
            onClick={() => setShowLgpdDetalhes((v) => !v)}
            className="w-full flex items-center justify-between gap-2 text-sm"
          >
            <span className="flex items-center gap-2 font-medium text-afj-black">
              <ShieldAlert size={14} className="text-afj-gold" />
              Qualidade de dado LGPD
              <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                lgpdQualidade.score_conformidade >= 80 ? "bg-green-50 text-green-700" :
                lgpdQualidade.score_conformidade >= 50 ? "bg-amber-50 text-amber-700" : "bg-red-50 text-red-700"
              }`}>
                {lgpdQualidade.score_conformidade}/100
              </span>
            </span>
            {showLgpdDetalhes ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
          {showLgpdDetalhes && (
            <div className="mt-3 grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs text-afj-black/60">
              <div className="flex justify-between border-l-2 border-afj-cream-dark pl-2">
                <span>Ativos sem consentimento</span>
                <span className="font-semibold text-afj-black">{lgpdQualidade.lacunas.sem_consentimento_ativo.total}</span>
              </div>
              <div className="flex justify-between border-l-2 border-afj-cream-dark pl-2">
                <span>Consentimento sem data</span>
                <span className="font-semibold text-afj-black">{lgpdQualidade.lacunas.consentimento_sem_data.total}</span>
              </div>
              <div className="flex justify-between border-l-2 border-afj-cream-dark pl-2">
                <span>Sem CPF/CNPJ</span>
                <span className="font-semibold text-afj-black">{lgpdQualidade.lacunas.sem_documento_identificacao.total}</span>
              </div>
            </div>
          )}
        </div>
      )}

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
                  <button onClick={() => abrirEdicao(c)} className="text-afj-black/30 hover:text-afj-gold transition-colors" aria-label="Editar cliente"><Pencil size={12} /></button>
                  {isAdmin && (
                    <button onClick={() => setDeletingId(c.id)} className="text-afj-black/30 hover:text-red-500 transition-colors" aria-label="Remover cliente"><Trash2 size={12} /></button>
                  )}
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
                        <button onClick={() => abrirEdicao(c)} className="text-afj-black/30 hover:text-afj-gold transition-colors" aria-label="Editar cliente"><Pencil size={12} /></button>
                        {isAdmin && (
                          <button onClick={() => setDeletingId(c.id)} className="text-afj-black/30 hover:text-red-500 transition-colors" aria-label="Remover cliente"><Trash2 size={12} /></button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Carregar mais */}
      {hasMore && !loading && (
        <div className="flex justify-center">
          <button
            onClick={() => fetchClientes(offset, true)}
            disabled={loadingMore}
            className="btn-afj-outline rounded-sm text-sm disabled:opacity-50"
          >
            {loadingMore ? "Carregando..." : `Carregar mais clientes`}
          </button>
        </div>
      )}
      </>
      )}

      {/* Modal edição cliente */}
      {editingId && (
        <div className="fixed inset-0 bg-afj-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-sm p-6 w-full max-w-md shadow-2xl max-h-[85vh] overflow-y-auto">
            <h2 className="font-display text-lg font-semibold text-afj-black mb-4">Editar Cliente</h2>
            <form onSubmit={(e) => { e.preventDefault(); salvarEdicao(); }} className="space-y-3">
              <ClienteFormFields
                mode="edit"
                values={editValues}
                onChange={(patch) => setEditForm((f) => ({ ...f, ...patch }))}
                endereco={editEndereco}
                onEnderecoChange={setEditEndereco}
                docSugestao={editDocSugestao}
                onDocumentoBlur={(tipo, valor) => validarDocumento(tipo, valor, setEditDocSugestao)}
                onCepBlur={(cep) => autofillCep(cep, editEndereco, setEditEndereco)}
                statusLocalizacao={statusLocalizacaoDe(
                  editEndereco,
                  (editEndereco.cep ?? "").replace(/\D/g, "") !== editEnderecoCepOriginalRef.current.replace(/\D/g, ""),
                )}
                onRecalcularLocalizacao={recalcularLocalizacao}
                recalculando={recalculando}
              />
              <div className="flex gap-3 mt-5">
                <button type="button" onClick={() => setEditingId(null)} className="flex-1 btn-afj-outline rounded-sm">Cancelar</button>
                <button type="submit" disabled={salvando} className="flex-1 btn-afj-primary rounded-sm disabled:opacity-50">{salvando ? "Salvando..." : "Salvar"}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal confirmação exclusão */}
      {deletingId && (
        <div className="fixed inset-0 bg-afj-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-sm p-6 w-full max-w-sm shadow-2xl text-center max-h-[85vh] overflow-y-auto">
            <p className="font-semibold text-afj-black mb-2">Remover cliente?</p>
            <p className="text-afj-black/50 text-sm mb-5">Os dados serão anonimizados conforme a LGPD.</p>
            <div className="flex gap-3">
              <button onClick={() => setDeletingId(null)} className="flex-1 btn-afj-outline rounded-sm">Cancelar</button>
              <button onClick={() => excluirCliente(deletingId)} disabled={salvando} className="flex-1 bg-red-500 text-white rounded-sm py-2 text-sm font-medium hover:bg-red-600 disabled:opacity-50">{salvando ? "Removendo..." : "Remover"}</button>
            </div>
          </div>
        </div>
      )}

      {/* Modal novo cliente */}
      {showModal && (
        <div className="fixed inset-0 bg-afj-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-sm p-6 w-full max-w-lg shadow-2xl max-h-[85vh] overflow-y-auto">
            <h2 className="font-display text-xl font-semibold text-afj-black mb-5">Novo Cliente</h2>
            <form onSubmit={salvarCliente} className="space-y-4">
              <ClienteFormFields
                mode="create"
                values={form}
                onChange={(patch) => setForm((f) => ({ ...f, ...patch }))}
                endereco={endereco}
                onEnderecoChange={setEndereco}
                docSugestao={docSugestao}
                onDocumentoBlur={(tipo, valor) => validarDocumento(tipo, valor, setDocSugestao)}
                onCepBlur={(cep) => autofillCep(cep, endereco, setEndereco)}
                statusLocalizacao={statusLocalizacaoDe(endereco, false)}
              />
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => setShowModal(false)} className="flex-1 btn-afj-outline rounded-sm">Cancelar</button>
                <button type="submit" disabled={salvando} className="flex-1 btn-afj-primary rounded-sm disabled:opacity-50">{salvando ? "Salvando..." : "Salvar"}</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal resultado da importação CSV — Fase 245 */}
      {importResultado && (
        <div className="fixed inset-0 bg-afj-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-sm p-6 w-full max-w-lg shadow-2xl max-h-[85vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display text-xl font-semibold text-afj-black flex items-center gap-2">
                <CheckCircle size={20} className="text-green-600" /> Importação concluída
              </h2>
              <button onClick={() => setImportResultado(null)} className="text-afj-black/40 hover:text-afj-black"><X size={18} /></button>
            </div>
            <div className="grid grid-cols-3 gap-3 mb-4 text-center">
              <div className="afj-stat-card"><p className="text-xl font-bold text-green-600">{importResultado.criados}</p><p className="text-xs text-afj-black/50 mt-0.5">Criados</p></div>
              <div className="afj-stat-card"><p className="text-xl font-bold text-amber-600">{importResultado.duplicados}</p><p className="text-xs text-afj-black/50 mt-0.5">Duplicados</p></div>
              <div className="afj-stat-card"><p className="text-xl font-bold text-red-500">{importResultado.erros}</p><p className="text-xs text-afj-black/50 mt-0.5">Erros</p></div>
            </div>
            {importResultado.detalhes.some((d) => d.status !== "criado") && (
              <div className="divide-y divide-afj-cream-dark border border-afj-cream-dark rounded-sm max-h-60 overflow-y-auto">
                {importResultado.detalhes.filter((d) => d.status !== "criado").map((d) => (
                  <div key={d.linha} className="flex items-center justify-between px-3 py-2 text-xs">
                    <span className="text-afj-black/60">Linha {d.linha}{d.nome ? ` — ${d.nome}` : ""}</span>
                    <span className={d.status === "erro" ? "text-red-500" : "text-amber-600"}>{d.detalhe}</span>
                  </div>
                ))}
              </div>
            )}
            <button onClick={() => setImportResultado(null)} className="w-full btn-afj-primary rounded-sm mt-4">Fechar</button>
          </div>
        </div>
      )}
    </div>
  );
}
