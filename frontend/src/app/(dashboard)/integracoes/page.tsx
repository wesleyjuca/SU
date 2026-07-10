"use client";
import { useState, useEffect } from "react";
import { Plug, MessageCircle, PenTool, Clock, CheckCircle2, Smartphone, Loader2, LogOut, Link2 } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { useToast } from "@/components/ui/Toast";

// Base das integrações externas. Cada card descreve o recurso, o que já está
// pronto no sistema para recebê-lo e o que falta (credenciais/provedor).
const INTEGRACOES = [
  {
    icon: MessageCircle,
    titulo: "WhatsApp — Notificações",
    status: "planejado" as const,
    desc: "Alertas de prazos, andamentos processuais e cobranças enviados por WhatsApp para advogados e clientes.",
    prontos: [
      "Sistema de notificações interno (sino) já operacional",
      "Alertas de prazo já calculados pelo monitor de processos",
      "Portal do cliente com vínculo seguro por cliente",
    ],
    faltam: [
      "Conta WhatsApp Business API (Meta) ou provedor (ex.: Twilio)",
      "Credenciais no Railway (token + número verificado)",
      "Templates de mensagem aprovados pela Meta",
    ],
  },
  {
    icon: PenTool,
    titulo: "Assinatura Eletrônica de Contratos",
    status: "planejado" as const,
    desc: "Envio de contratos para assinatura eletrônica (ICP-Brasil ou assinatura simples) direto do fluxo de contratos.",
    prontos: [
      "Contratos com conteúdo/minuta e ciclo de vida completo",
      "Geração de PDF do documento",
      "Fila de aprovações (HITL) para envio controlado",
    ],
    faltam: [
      "Contrato com provedor (ex.: Clicksign, DocuSign, D4Sign)",
      "Credenciais/API key no Railway",
      "Webhook de retorno para atualizar o status do contrato",
    ],
  },
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

interface GoogleStatus { enabled: boolean; configured: boolean; connected: boolean; google_email: string | null }

function GoogleWorkspaceCard() {
  const toast = useToast();
  const [status, setStatus] = useState<GoogleStatus | null>(null);
  const [working, setWorking] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);

  async function fetchStatus() {
    try {
      const res = await fetch("/api/v1/integrations/google/status", { headers: authH() });
      if (res.ok) setStatus(await res.json());
    } catch { /* card mostra estado padrão */ }
  }

  useEffect(() => {
    fetchStatus();
    fetch("/api/v1/users/me", { headers: authH() })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setIsAdmin(d?.role === "ADMIN" || d?.role === "SUPERADMIN"))
      .catch(() => {});
    // Feedback do retorno OAuth (?google=ok|erro)
    const p = new URLSearchParams(window.location.search);
    if (p.get("google") === "ok") toast.success("Conta Google conectada com sucesso!");
    if (p.get("google") === "erro") toast.error("Falha ao conectar a conta Google. Tente novamente.");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function conectar() {
    setWorking(true);
    try {
      const res = await fetch("/api/v1/integrations/google/connect", { method: "POST", headers: authH() });
      const d = await res.json().catch(() => ({}));
      if (res.ok && d.auth_url) window.location.href = d.auth_url;
      else toast.error(d.detail || "Integração Google não configurada no servidor.");
    } catch { toast.error("Falha de conexão."); }
    finally { setWorking(false); }
  }

  async function desconectar() {
    setWorking(true);
    try {
      const res = await fetch("/api/v1/integrations/google/disconnect", { method: "DELETE", headers: authH() });
      if (res.ok) { toast.success("Conta Google desconectada."); fetchStatus(); }
      else toast.error("Erro ao desconectar.");
    } catch { toast.error("Falha de conexão."); }
    finally { setWorking(false); }
  }

  // Opt-in por escritório: o ADMIN decide se o módulo Google fica disponível
  async function alternarModulo(habilitar: boolean) {
    setWorking(true);
    try {
      const res = await fetch("/api/v1/tenant/modules", {
        method: "PUT", headers: authH(),
        body: JSON.stringify({ google_workspace: habilitar }),
      });
      if (res.ok) {
        toast.success(habilitar ? "Google Workspace habilitado para o escritório." : "Google Workspace desabilitado para o escritório.");
        fetchStatus();
      } else toast.error("Erro ao atualizar o módulo.");
    } catch { toast.error("Falha de conexão."); }
    finally { setWorking(false); }
  }

  const enabled = Boolean(status?.enabled);
  const connected = Boolean(status?.connected);
  const configured = Boolean(status?.configured);

  return (
    <div className="afj-card p-5 border-l-4 border-afj-gold">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <span className="w-10 h-10 rounded-sm bg-afj-gold/10 flex items-center justify-center flex-shrink-0">
            <Link2 size={19} className="text-afj-gold" />
          </span>
          <div>
            <p className="font-semibold text-afj-black text-sm">Google Workspace</p>
            <p className="text-xs text-afj-black/55 mt-0.5">
              Agenda, Drive e Gmail integrados às ações do sistema — prazos no Google Agenda,
              PDFs no Drive e e-mails pela sua conta.
            </p>
          </div>
        </div>
        <span className={`inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-sm border flex-shrink-0 ${
          !enabled ? "bg-gray-50 text-gray-500 border-gray-200"
          : connected ? "bg-green-50 text-green-700 border-green-200"
          : configured ? "bg-amber-50 text-amber-700 border-amber-200"
          : "bg-gray-50 text-gray-500 border-gray-200"
        }`}>
          {connected ? <CheckCircle2 size={11} /> : <Clock size={11} />}
          {!enabled ? "Desabilitado" : connected ? "Conectado" : configured ? "Pronto p/ conectar" : "Aguarda credenciais"}
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-green-700 mb-1.5">Já funciona</p>
          <ul className="space-y-1 text-xs text-afj-black/60">
            <li className="flex gap-1.5"><CheckCircle2 size={12} className="text-green-500 flex-shrink-0 mt-0.5" /> Agenda: botão “Adicionar ao Google Agenda” em cada prazo (sem precisar conectar)</li>
            <li className="flex gap-1.5"><CheckCircle2 size={12} className="text-green-500 flex-shrink-0 mt-0.5" /> Base OAuth completa com tokens cifrados e renovação automática</li>
          </ul>
        </div>
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wider text-afj-black/40 mb-1.5">Com a conta conectada</p>
          <ul className="space-y-1 text-xs text-afj-black/60">
            <li className="flex gap-1.5"><Clock size={12} className="text-afj-gold flex-shrink-0 mt-0.5" /> Salvar documentos (PDF timbrado) direto no seu Drive</li>
            <li className="flex gap-1.5"><Clock size={12} className="text-afj-gold flex-shrink-0 mt-0.5" /> E-mails do sistema enviados pela sua conta Gmail</li>
            <li className="flex gap-1.5"><Clock size={12} className="text-afj-gold flex-shrink-0 mt-0.5" /> Criação de eventos direto no calendário (API)</li>
            <li className="flex gap-1.5"><Clock size={12} className="text-afj-gold flex-shrink-0 mt-0.5" /> Próximas etapas: Docs, Meet e Contatos</li>
          </ul>
        </div>
      </div>

      {/* Opt-in do escritório: só o ADMIN habilita/desabilita o módulo */}
      {isAdmin && (
        <label className="flex items-center gap-2.5 cursor-pointer mt-4">
          <input type="checkbox" checked={enabled} disabled={working}
            onChange={(e) => alternarModulo(e.target.checked)} className="accent-afj-gold w-4 h-4" />
          <span className="text-sm text-afj-black/75">
            Habilitar Google Workspace para este escritório
            <span className="text-afj-black/40"> — escritórios sem o serviço podem manter desligado</span>
          </span>
        </label>
      )}

      <div className="flex items-center gap-3 mt-3 flex-wrap">
        {!enabled ? (
          <p className="text-xs text-afj-black/45">
            {isAdmin
              ? "Módulo desligado — marque a opção acima para disponibilizar aos usuários deste escritório."
              : "Integração não habilitada pelo administrador deste escritório."}
          </p>
        ) : connected ? (
          <>
            <span className="text-xs text-afj-black/55">Conectado como <strong>{status?.google_email || "—"}</strong></span>
            <button onClick={desconectar} disabled={working}
              className="btn-afj-outline text-xs py-1.5 px-3 rounded-sm flex items-center gap-1.5 disabled:opacity-50">
              {working ? <Loader2 size={12} className="animate-spin" /> : <LogOut size={12} />} Desconectar
            </button>
          </>
        ) : (
          <button onClick={conectar} disabled={working || !configured}
            title={!configured ? "O administrador precisa configurar as credenciais no Railway" : "Conectar sua conta Google"}
            className="btn-afj-primary text-sm py-2 px-4 rounded-sm flex items-center gap-2 disabled:opacity-50">
            {working ? <Loader2 size={14} className="animate-spin" /> : <Link2 size={14} />} Conectar com Google
          </button>
        )}
      </div>

      {enabled && !configured && (
        <div className="mt-4 text-[11px] text-afj-black/50 bg-afj-cream/60 border border-afj-cream-dark rounded-sm p-3 leading-relaxed">
          <strong className="text-afj-black/70">Para ativar (ADMIN):</strong> Google Cloud Console → criar projeto →
          ativar as APIs <em>Calendar, Drive e Gmail</em> → tela de consentimento OAuth (tipo interno) → credencial
          “Aplicativo da Web” com redirect <code className="bg-white px-1 rounded">https://su-production-4561.up.railway.app/api/v1/integrations/google/callback</code> →
          colar <code className="bg-white px-1 rounded">GOOGLE_CLIENT_ID</code>, <code className="bg-white px-1 rounded">GOOGLE_CLIENT_SECRET</code> e{" "}
          <code className="bg-white px-1 rounded">GOOGLE_REDIRECT_URI</code> nas Variables do Railway.
        </div>
      )}
    </div>
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
        <GoogleWorkspaceCard />
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
