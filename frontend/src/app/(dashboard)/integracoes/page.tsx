"use client";
import { useState, useEffect } from "react";
import { Plug, MessageCircle, PenTool, Clock, CheckCircle2, Smartphone, Loader2, LogOut, Link2, CreditCard, Wallet, X, RefreshCw, AlertTriangle, Scale, Search, ScrollText, FolderOpen } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { useToast } from "@/components/ui/Toast";
import { useConfirmDialog } from "@/hooks/useConfirmDialog";
import { StatusBadge, type StatusTone } from "@/components/integrations/StatusBadge";

// Cards estáticos (recursos que não são "conectar conta" — hoje só o PWA).
const INTEGRACOES = [
  {
    icon: Smartphone,
    titulo: "App Instalável (PWA)",
    status: "parcial" as const,
    desc: "Uso do AFJ CORE como aplicativo no celular/desktop, com ícone próprio e abertura em tela cheia.",
    prontos: [
      "Manifest e service worker publicados",
      "Ícones e tema configurados",
      "Instalável hoje: no navegador, use “Adicionar à tela inicial”",
    ],
    faltam: [
      "Modo offline ampliado (cache de consultas recentes)",
      "Notificações push nativas no dispositivo",
    ],
  },
];

function authH(): HeadersInit {
  const t = typeof window !== "undefined" ? localStorage.getItem("afj_access_token") : null;
  return { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) };
}

// ─── Hub de integrações (conectar conta por escritório) ───────────────────────
interface HubField { key: string; label: string; secret: boolean }
interface HubIntegracao {
  provider: string; nome: string; desc: string; tipo: string;
  fields: HubField[]; ativa: string[]; obter: string;
  status: string; connected_at: string | null;
  // Fase 165 — antes só o clique manual em "Testar conexão" atualizava o
  // status; estes campos refletem o último uso REAL da credencial.
  last_success_at: string | null; last_error_at: string | null; last_error_detail: string | null;
  // Fase 248.3 — tradução curada de last_error_detail, sempre presente
  // (pode ser null quando não há erro ou quando a mensagem já é amigável).
  last_error_friendly: string | null;
  oauth_disponivel: boolean;
  extra_data: Record<string, string>;
}

// Fase 117 — nomes curtos pro toast de retorno do OAuth (?hub_oauth=stripe_ok etc.),
// antes mesmo da lista de integrações carregar.
const HUB_OAUTH_LABELS: Record<string, string> = {
  stripe: "Stripe", mercadopago: "Mercado Pago", google_drive_doutrina: "Google Drive",
  google_workspace: "Google Workspace",
};

const HUB_ICONS: Record<string, typeof CreditCard> = {
  stripe: CreditCard,
  mercadopago: Wallet,
  clicksign: PenTool,
  whatsapp: MessageCircle,
  pdpj: Scale,
  escavador: Search,
  judit: ScrollText,
  google_drive_doutrina: FolderOpen,
  google_workspace: Link2,
};

// Provedores do hub com opt-in por módulo (Fase 138.2 Drive doutrina, Fase
// 139 Google Workspace do escritório) — chave de `modules_enabled` sempre
// igual ao nome do provider, zero tradução.
const MODULOS_HUB: Record<string, string> = {
  google_drive_doutrina: "google_drive_doutrina",
  google_workspace: "google_workspace",
};

// Provedores com teste de credencial automático (fontes credenciadas +
// WhatsApp, Fase 168 — antes o botão nem aparecia pra jusbrasil, apesar do
// backend já testar essa fonte desde a Fase 88, nem pra WhatsApp; stripe/
// mercadopago entraram na Fase 242; clicksign/google_drive_doutrina/
// google_workspace entraram na Fase 248.1 — todos com sonda GET
// read-only contra o provedor real, `_GET_TEST_PROBE` no backend).
const TESTAVEIS = new Set([
  "pdpj", "escavador", "judit", "jusbrasil", "whatsapp", "stripe", "mercadopago",
  "clicksign", "google_drive_doutrina", "google_workspace",
]);

function HubCards() {
  const toast = useToast();
  const { ask, confirmDialog } = useConfirmDialog();
  const [itens, setItens] = useState<HubIntegracao[]>([]);
  const [isAdmin, setIsAdmin] = useState(false);
  const [conectando, setConectando] = useState<HubIntegracao | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [working, setWorking] = useState(false);
  const [testando, setTestando] = useState<string | null>(null);
  const [oauthConectando, setOauthConectando] = useState<string | null>(null);
  // Fase 177.1 — login direto do PDPJ (CNJ Corporativo): grant_type=password,
  // sem redirect, então não cabe no fluxo genérico de conectarOAuth() abaixo
  // (que abre uma aba pro site do provedor).
  const [pdpjLogin, setPdpjLogin] = useState<HubIntegracao | null>(null);
  const [pdpjForm, setPdpjForm] = useState({ username: "", password: "" });
  const [pdpjWorking, setPdpjWorking] = useState(false);
  const [modulos, setModulos] = useState<Record<string, boolean>>({});
  const [folderInputs, setFolderInputs] = useState<Record<string, string>>({});
  const [salvandoPasta, setSalvandoPasta] = useState<string | null>(null);
  // Fase 188.2 — achado da Fase 186: a tela não mostrava nenhum resultado
  // da sincronização de doutrina (processados/pulados/falhas/erro).
  const [driveLastSync, setDriveLastSync] = useState<{
    status: string; stats: Record<string, unknown>; started_at: string | null; finished_at: string | null;
  } | null>(null);

  async function fetchHub() {
    try {
      const res = await fetch("/api/v1/integrations/hub", { headers: authH() });
      if (res.ok) setItens((await res.json()).integracoes || []);
    } catch { /* mantém lista vazia */ }
  }

  async function fetchModulos() {
    try {
      const res = await fetch("/api/v1/tenant/config", { headers: authH() });
      if (res.ok) setModulos((await res.json()).modules_enabled || {});
    } catch { /* mantém estado padrão (desligado) */ }
  }

  async function fetchDriveLastSync() {
    try {
      const res = await fetch("/api/v1/integrations/hub/google_drive_doutrina/last-sync", { headers: authH() });
      if (res.ok) setDriveLastSync((await res.json()).ultima_sincronizacao || null);
    } catch { /* mantém estado vazio */ }
  }

  useEffect(() => {
    fetchHub();
    fetchModulos();
    fetchDriveLastSync();
    fetch("/api/v1/users/me", { headers: authH() })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setIsAdmin(d?.role === "ADMIN" || d?.role === "SUPERADMIN"))
      .catch(() => {});
    // Feedback do retorno OAuth do hub (?hub_oauth=stripe_ok|stripe_erro etc.)
    const p = new URLSearchParams(window.location.search);
    const hubOauth = p.get("hub_oauth");
    if (hubOauth) {
      const ok = hubOauth.endsWith("_ok");
      const provider = hubOauth.replace(/_ok$|_erro$/, "");
      const nome = HUB_OAUTH_LABELS[provider] || provider;
      if (ok) toast.success(`${nome} conectado com sucesso!`);
      else toast.error(`Falha ao conectar ${nome}. Tente novamente ou cole a chave manualmente.`);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function abrirConectar(it: HubIntegracao) {
    setForm({});
    setConectando(it);
  }

  async function conectarOAuth(it: HubIntegracao) {
    setOauthConectando(it.provider);
    try {
      const res = await fetch(`/api/v1/integrations/hub/${it.provider}/oauth/connect`, { headers: authH() });
      const d = await res.json().catch(() => ({}));
      if (res.ok && d.auth_url) window.location.href = d.auth_url;
      else toast.error(d.detail || "Login por conta não disponível no momento.");
    } catch { toast.error("Falha de conexão."); }
    finally { setOauthConectando(null); }
  }

  async function loginPdpj() {
    if (!pdpjLogin) return;
    setPdpjWorking(true);
    try {
      const res = await fetch("/api/v1/integrations/hub/pdpj/oauth/login", {
        method: "POST", headers: authH(),
        body: JSON.stringify(pdpjForm),
      });
      const d = await res.json().catch(() => ({}));
      if (res.ok) {
        toast.success(d.message || "PDPJ conectado.");
        setPdpjLogin(null);
        setPdpjForm({ username: "", password: "" });
        fetchHub();
      } else {
        toast.error(d.detail || "Erro ao entrar com o CNJ Corporativo.");
      }
    } catch { toast.error("Falha de conexão."); }
    finally { setPdpjWorking(false); }
  }

  async function conectar() {
    if (!conectando) return;
    setWorking(true);
    try {
      const res = await fetch(`/api/v1/integrations/hub/${conectando.provider}/connect`, {
        method: "POST", headers: authH(),
        body: JSON.stringify({ credentials: form }),
      });
      const d = await res.json().catch(() => ({}));
      if (res.ok) { toast.success(d.message || "Integração conectada."); setConectando(null); fetchHub(); }
      else toast.error(d.detail || "Erro ao conectar.");
    } catch { toast.error("Falha de conexão."); }
    finally { setWorking(false); }
  }

  async function testar(it: HubIntegracao) {
    setTestando(it.provider);
    try {
      const res = await fetch(`/api/v1/integrations/hub/${it.provider}/test`, { method: "POST", headers: authH() });
      const d = await res.json().catch(() => ({}));
      // Fase 248.3 — `detail_friendly` (quando existe) é a mensagem curada;
      // `detail` cru fica só como fallback pros poucos casos sem tradução.
      if (res.ok && d.ok) toast.success(`Conexão OK — ${d.detail || "credencial válida"}.`);
      else if (res.ok) toast.error(d.detail_friendly || `Falha na credencial: ${d.detail || "verifique o token"}.`);
      else toast.error(d.detail || "Erro ao testar a conexão.");
      fetchHub();
    } catch { toast.error("Falha de conexão."); }
    finally { setTestando(null); }
  }

  async function alternarModuloHub(provider: string, chave: string, habilitar: boolean) {
    setWorking(true);
    try {
      const res = await fetch("/api/v1/tenant/modules", {
        method: "PUT", headers: authH(),
        body: JSON.stringify({ [chave]: habilitar }),
      });
      if (res.ok) { toast.success(habilitar ? "Módulo habilitado para o escritório." : "Módulo desabilitado para o escritório."); fetchModulos(); }
      else toast.error("Erro ao atualizar o módulo.");
    } catch { toast.error("Falha de conexão."); }
    finally { setWorking(false); }
  }

  async function salvarPasta(it: HubIntegracao) {
    const valor = (folderInputs[it.provider] ?? it.extra_data?.folder_id ?? "").trim();
    if (!valor) return;
    setSalvandoPasta(it.provider);
    try {
      const res = await fetch(`/api/v1/integrations/hub/${it.provider}/folder`, {
        method: "PUT", headers: authH(),
        body: JSON.stringify({ folder: valor }),
      });
      const d = await res.json().catch(() => ({}));
      if (res.ok) { toast.success(d.message || "Pasta configurada."); fetchHub(); }
      else toast.error(d.detail || "Erro ao configurar a pasta.");
    } catch { toast.error("Falha de conexão."); }
    finally { setSalvandoPasta(null); }
  }

  async function desconectar(it: HubIntegracao) {
    if ((await ask({ message: `Desconectar ${it.nome}? As credenciais salvas serão removidas.` })) === null) return;
    setWorking(true);
    try {
      const res = await fetch(`/api/v1/integrations/hub/${it.provider}`, { method: "DELETE", headers: authH() });
      if (res.ok) { toast.success("Integração desconectada."); fetchHub(); }
      else toast.error("Erro ao desconectar.");
    } catch { toast.error("Falha de conexão."); }
    finally { setWorking(false); }
  }

  return (
    <>
      {itens.map((it) => {
        const Icon = HUB_ICONS[it.provider] || Plug;
        const conectada = it.status === "CONECTADA";
        const comErro = it.status === "ERRO";
        const temCredencial = it.status !== "DESCONECTADA";
        return (
          <div key={it.provider} className="afj-card p-5">
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <div className="flex items-center gap-3">
                <span className="w-10 h-10 rounded-sm bg-afj-gold/10 flex items-center justify-center flex-shrink-0">
                  <Icon size={19} className="text-afj-gold" />
                </span>
                <div>
                  <p className="font-semibold text-afj-black text-sm">{it.nome}</p>
                  <p className="text-xs text-afj-black/55 mt-0.5">{it.desc}</p>
                </div>
              </div>
              <StatusBadge
                tone={(comErro ? "red" : conectada ? "green" : "gray") as StatusTone}
                icon={comErro ? AlertTriangle : conectada ? CheckCircle2 : Clock}
                label={comErro ? "Com erro" : conectada ? "Conectada" : "Desconectada"}
              />
            </div>

            <div className="mt-4">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-afj-black/40 mb-1.5">
                {temCredencial ? "Habilitado com a conexão" : "O que a conexão habilita"}
              </p>
              <ul className="space-y-1">
                {it.ativa.map((a) => (
                  <li key={a} className="flex gap-1.5 text-xs text-afj-black/60">
                    {conectada
                      ? <CheckCircle2 size={12} className="text-green-500 flex-shrink-0 mt-0.5" />
                      : <Clock size={12} className="text-afj-gold flex-shrink-0 mt-0.5" />} {a}
                  </li>
                ))}
              </ul>
            </div>

            {/* Fase 248.4 — disclosure de dado acessado, distinto do checklist
                de FEATURES acima ("O que a conexão habilita"). Só o Workspace
                agrupa 3 escopos (Gmail+Agenda+Drive) numa única autorização —
                vale deixar explícito antes de conectar o que isso realmente
                significa em termos de acesso, não só de funcionalidade. */}
            {it.provider === "google_workspace" && !temCredencial && (
              <p className="mt-2 text-[11px] text-afj-black/45 leading-relaxed">
                A conexão concede ao AFJ CORE permissão para: enviar e-mails em nome dessa conta
                (Gmail), criar/editar eventos na Agenda do Google, e salvar arquivos no Drive dessa
                conta. Nenhum e-mail ou arquivo existente é lido — só o necessário pra essas 3 ações.
              </p>
            )}

            {comErro && (
              <p className="mt-3 text-[11px] text-red-600 bg-red-50 border border-red-200 rounded-sm px-2.5 py-1.5">
                {/* Fase 248.3 — mensagem curada (last_error_friendly) em vez do
                    detail cru (exceção httpx truncada) que estava aqui antes. */}
                {it.last_error_friendly || "A última verificação falhou (credencial inválida/expirada)."} Teste a conexão ou reconecte.
                {it.last_error_at && ` (${new Date(it.last_error_at).toLocaleString("pt-BR")})`}
              </p>
            )}

            {/* Opt-in por módulo (Fase 138.2 — hoje só Google Drive Doutrina) */}
            {MODULOS_HUB[it.provider] && isAdmin && (
              <div className="mt-3">
                <label className="flex items-center gap-2.5 cursor-pointer">
                  <input type="checkbox" checked={Boolean(modulos[MODULOS_HUB[it.provider]])} disabled={working}
                    onChange={(e) => alternarModuloHub(it.provider, MODULOS_HUB[it.provider], e.target.checked)}
                    className="accent-afj-gold w-4 h-4" />
                  <span className="text-sm text-afj-black/75">Habilitar {it.nome} para este escritório</span>
                </label>
                {/* Fase 256 (Alteração 2) — o mesmo toggle também aparece em
                    Configurações → Módulos (que antes só cobria os 6
                    módulos "core", sem os 2 do Google — ficava incompleta
                    como "lugar único" de módulos). */}
                <p className="text-[10px] text-afj-black/35 mt-1">
                  Também editável em Configurações → Módulos.
                </p>
              </div>
            )}
            {MODULOS_HUB[it.provider] && !isAdmin && !modulos[MODULOS_HUB[it.provider]] && (
              <p className="mt-3 text-xs text-afj-black/45">Integração não habilitada pelo administrador deste escritório.</p>
            )}

            {/* Pasta do Drive a sincronizar — só depois de conectado (Fase 138.2) */}
            {it.provider === "google_drive_doutrina" && it.status === "CONECTADA" && (
              <div className="mt-3 pt-3 border-t border-afj-cream-dark">
                <label className="block text-xs font-medium text-afj-black/70 mb-1">Pasta do Drive a sincronizar</label>
                <div className="flex items-center gap-2">
                  <input type="text" value={folderInputs[it.provider] ?? it.extra_data?.folder_id ?? ""}
                    onChange={(e) => setFolderInputs((prev) => ({ ...prev, [it.provider]: e.target.value }))}
                    placeholder="Cole a URL ou o ID da pasta do Drive"
                    disabled={!isAdmin}
                    className="flex-1 border border-afj-cream-dark rounded-sm px-3 py-1.5 text-xs focus:outline-none focus:border-afj-gold disabled:opacity-60" />
                  {isAdmin && (
                    <button onClick={() => salvarPasta(it)} disabled={salvandoPasta === it.provider}
                      className="btn-afj-outline text-xs py-1.5 px-3 rounded-sm flex items-center gap-1.5 disabled:opacity-50 flex-shrink-0">
                      {salvandoPasta === it.provider ? <Loader2 size={12} className="animate-spin" /> : <FolderOpen size={12} />} Salvar
                    </button>
                  )}
                </div>
                {it.extra_data?.folder_id && (
                  <p className="text-[11px] text-afj-black/40 mt-1">
                    Pasta atual: <code className="bg-afj-cream px-1 rounded">{it.extra_data.folder_id}</code>
                  </p>
                )}
                {driveLastSync && (
                  <div className={`mt-2.5 text-[11px] rounded-sm px-2.5 py-1.5 border ${
                    driveLastSync.status === "ERRO" ? "bg-red-50 border-red-200 text-red-700" : "bg-afj-cream border-afj-cream-dark text-afj-black/60"
                  }`}>
                    <p className="font-medium">
                      Última sincronização: {driveLastSync.status === "ERRO" ? "com erro" : driveLastSync.status === "OK" ? "concluída" : "em andamento"}
                      {driveLastSync.started_at && ` — ${new Date(driveLastSync.started_at).toLocaleString("pt-BR")}`}
                    </p>
                    {driveLastSync.status !== "ERRO" && (
                      <p className="mt-0.5">
                        {String(driveLastSync.stats?.processados ?? 0)} processados, {String(driveLastSync.stats?.pulados ?? 0)} pulados, {String(driveLastSync.stats?.falhas ?? 0)} falhas
                      </p>
                    )}
                    {driveLastSync.status === "ERRO" && driveLastSync.stats?.erro ? (
                      <p className="mt-0.5">{String(driveLastSync.stats.erro)}</p>
                    ) : null}
                  </div>
                )}
              </div>
            )}

            <div className="flex items-center gap-3 mt-4 flex-wrap">
              {temCredencial ? (
                <>
                  {it.connected_at && (
                    <span className="text-xs text-afj-black/55">
                      Conectada em {new Date(it.connected_at).toLocaleDateString("pt-BR")}
                    </span>
                  )}
                  {it.last_success_at && !comErro && (
                    <span className="text-xs text-afj-black/40">
                      · último uso OK em {new Date(it.last_success_at).toLocaleString("pt-BR")}
                    </span>
                  )}
                  {isAdmin && TESTAVEIS.has(it.provider) && (
                    <button onClick={() => testar(it)} disabled={testando === it.provider}
                      className="btn-afj-outline text-xs py-1.5 px-3 rounded-sm flex items-center gap-1.5 disabled:opacity-50">
                      {testando === it.provider ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />} Testar conexão
                    </button>
                  )}
                  {isAdmin && (
                    <button onClick={() => desconectar(it)} disabled={working}
                      className="btn-afj-outline text-xs py-1.5 px-3 rounded-sm flex items-center gap-1.5 disabled:opacity-50">
                      <LogOut size={12} /> Desconectar
                    </button>
                  )}
                </>
              ) : MODULOS_HUB[it.provider] && !modulos[MODULOS_HUB[it.provider]] ? (
                <p className="text-xs text-afj-black/45">
                  {isAdmin ? "Habilite o módulo acima antes de conectar." : "Aguardando o administrador habilitar o módulo."}
                </p>
              ) : isAdmin && it.oauth_disponivel ? (
                <>
                  <button onClick={() => it.provider === "pdpj" ? setPdpjLogin(it) : conectarOAuth(it)} disabled={oauthConectando === it.provider}
                    className="btn-afj-primary text-sm py-2 px-4 rounded-sm flex items-center gap-2 disabled:opacity-50">
                    {oauthConectando === it.provider ? <Loader2 size={14} className="animate-spin" /> : <Link2 size={14} />}
                    {it.provider === "pdpj" ? "Entrar com CNJ Corporativo" : "Conectar com login"}
                  </button>
                  {it.fields.length > 0 && (
                    <button onClick={() => abrirConectar(it)} disabled={working}
                      className="text-xs text-afj-black/45 hover:text-afj-black/70 underline underline-offset-2">
                      ou colar token manualmente
                    </button>
                  )}
                </>
              ) : isAdmin && it.fields.length > 0 ? (
                <button onClick={() => abrirConectar(it)} disabled={working}
                  className="btn-afj-primary text-sm py-2 px-4 rounded-sm flex items-center gap-2 disabled:opacity-50">
                  <Link2 size={14} /> Conectar
                </button>
              ) : isAdmin ? (
                <p className="text-xs text-afj-black/45">Login por conta não configurado no servidor.</p>
              ) : (
                <p className="text-xs text-afj-black/45">Somente o administrador do escritório pode conectar.</p>
              )}
            </div>
          </div>
        );
      })}

      {/* Modal de conexão (credenciais do provedor) */}
      {conectando && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => !working && setConectando(null)}>
          <div className="bg-white rounded-sm shadow-xl w-full max-w-md p-5 max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-1">
              <h3 className="font-semibold text-afj-black text-sm">Conectar {conectando.nome}</h3>
              <button onClick={() => setConectando(null)} disabled={working} className="text-afj-black/40 hover:text-afj-black p-1"><X size={16} /></button>
            </div>
            <p className="text-xs text-afj-black/50 mb-4">{conectando.obter}</p>
            <div className="space-y-3">
              {conectando.fields.map((f) => (
                <div key={f.key}>
                  <label className="block text-xs font-medium text-afj-black/70 mb-1">{f.label}</label>
                  <input
                    type={f.secret ? "password" : "text"}
                    value={form[f.key] || ""}
                    onChange={(e) => setForm((prev) => ({ ...prev, [f.key]: e.target.value }))}
                    className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                    autoComplete="off"
                  />
                </div>
              ))}
            </div>
            <p className="text-[11px] text-afj-black/45 mt-3">
              As credenciais são cifradas em repouso e valem só para este escritório.
            </p>
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => setConectando(null)} disabled={working} className="btn-afj-outline text-xs py-1.5 px-3 rounded-sm">Cancelar</button>
              <button onClick={conectar} disabled={working}
                className="btn-afj-primary text-xs py-1.5 px-4 rounded-sm flex items-center gap-1.5 disabled:opacity-50">
                {working ? <Loader2 size={12} className="animate-spin" /> : <Link2 size={12} />} Conectar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Login direto do PDPJ (usuário/senha do CNJ Corporativo) — Fase 177.1 */}
      {pdpjLogin && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={() => !pdpjWorking && setPdpjLogin(null)}>
          <div className="bg-white rounded-sm shadow-xl w-full max-w-md p-5" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-1">
              <h3 className="font-semibold text-afj-black text-sm">Entrar com CNJ Corporativo</h3>
              <button onClick={() => setPdpjLogin(null)} disabled={pdpjWorking} className="text-afj-black/40 hover:text-afj-black p-1"><X size={16} /></button>
            </div>
            <p className="text-xs text-afj-black/50 mb-4">
              Use o mesmo usuário e senha do acesso ao CNJ Corporativo/PDPJ. O token de acesso
              gerado se renova sozinho depois — sem precisar colar um novo token manualmente.
            </p>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-afj-black/70 mb-1">Usuário do CNJ Corporativo</label>
                <input type="text" value={pdpjForm.username}
                  onChange={(e) => setPdpjForm((prev) => ({ ...prev, username: e.target.value }))}
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                  autoComplete="off" />
              </div>
              <div>
                <label className="block text-xs font-medium text-afj-black/70 mb-1">Senha</label>
                <input type="password" value={pdpjForm.password}
                  onChange={(e) => setPdpjForm((prev) => ({ ...prev, password: e.target.value }))}
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                  autoComplete="off" />
              </div>
            </div>
            <p className="text-[11px] text-afj-black/45 mt-3">
              Sua senha é usada só nesta troca com o CNJ e nunca é guardada — só o token de
              acesso resultante fica salvo, cifrado.
            </p>
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => setPdpjLogin(null)} disabled={pdpjWorking} className="btn-afj-outline text-xs py-1.5 px-3 rounded-sm">Cancelar</button>
              <button onClick={loginPdpj} disabled={pdpjWorking || !pdpjForm.username || !pdpjForm.password}
                className="btn-afj-primary text-xs py-1.5 px-4 rounded-sm flex items-center gap-1.5 disabled:opacity-50">
                {pdpjWorking ? <Loader2 size={12} className="animate-spin" /> : <Link2 size={12} />} Entrar
              </button>
            </div>
          </div>
        </div>
      )}
      {confirmDialog}
    </>
  );
}

export default function IntegracoesPage() {
  return (
    <div className="max-w-4xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Integrações" }]} />

      <div className="afj-page-header">
        <div>
          <h1 className="afj-page-title flex items-center gap-2">
            <Plug size={20} className="text-afj-gold" /> Integrações
          </h1>
          <p className="text-afj-black/45 text-sm mt-1">
            Conexões do AFJ CORE com serviços externos — o que já está pronto e o que falta para ativar.
          </p>
        </div>
      </div>

      <div className="space-y-4">
        <HubCards />
        {INTEGRACOES.map((it) => {
          const Icon = it.icon;
          const isParcial = it.status === "parcial";
          return (
            <div key={it.titulo} className="afj-card p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <span className="w-10 h-10 rounded-sm bg-afj-gold/10 flex items-center justify-center flex-shrink-0">
                    <Icon size={19} className="text-afj-gold" />
                  </span>
                  <div>
                    <p className="font-semibold text-afj-black text-sm">{it.titulo}</p>
                    <p className="text-xs text-afj-black/55 mt-0.5">{it.desc}</p>
                  </div>
                </div>
                <span className={`inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-sm border flex-shrink-0 ${
                  isParcial ? "bg-amber-50 text-amber-700 border-amber-200" : "bg-gray-50 text-gray-500 border-gray-200"
                }`}>
                  <Clock size={11} /> {isParcial ? "Em evolução" : "Planejado"}
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-4">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-green-700 mb-1.5">Já pronto no sistema</p>
                  <ul className="space-y-1">
                    {it.prontos.map((p) => (
                      <li key={p} className="flex gap-1.5 text-xs text-afj-black/60">
                        <CheckCircle2 size={12} className="text-green-500 flex-shrink-0 mt-0.5" /> {p}
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-afj-black/40 mb-1.5">Para ativar</p>
                  <ul className="space-y-1">
                    {it.faltam.map((f) => (
                      <li key={f} className="flex gap-1.5 text-xs text-afj-black/60">
                        <Clock size={12} className="text-afj-gold flex-shrink-0 mt-0.5" /> {f}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <p className="text-[11px] text-afj-black/35 text-center">
        Para ativar uma integração, providencie as credenciais do provedor e solicite a implementação da conexão.
      </p>
    </div>
  );
}
