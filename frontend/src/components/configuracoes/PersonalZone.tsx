"use client";
import { useState, useEffect } from "react";
import { User, Bell, Shield, Save, CheckCircle, Loader2, Eye, EyeOff } from "lucide-react";
import { usePushSubscription } from "@/hooks/usePushSubscription";

const TABS = [
  { id: "perfil", label: "Perfil", icon: User },
  { id: "notificacoes", label: "Notificações", icon: Bell },
  { id: "seguranca", label: "Segurança", icon: Shield },
];

/** Fase 224 — zona "Pessoal" de Configurações (todo mundo). Perfil/
 * Notificações/Segurança, extraídos sem mudança de lógica do antigo
 * `configuracoes/page.tsx`. A antiga aba "Aparência" NÃO foi trazida pra cá
 * de propósito — era visível a todo papel mas o backend (`PUT /tenant/
 * branding`) exige ADMIN, causando 403 silencioso pra quem não fosse; a
 * versão completa e correta dessa configuração já existe na zona
 * "Escritório & Jurídico" (aba Aparência de `EscritorioZone`). */
export function PersonalZone() {
  const [activeTab, setActiveTab] = useState("perfil");
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const { subscribed, subscribe, unsubscribe, loading: pushLoading } = usePushSubscription();

  // Perfil
  const [perfil, setPerfil] = useState({ full_name: "", email: "", oab_number: "", oab_uf: "", telefone: "" });
  const [perfilLoaded, setPerfilLoaded] = useState(false);

  // Notificações
  const [notifs, setNotifs] = useState({
    novos_prazos: true, novas_aprovacoes: true, agente_concluiu: true,
    publicacoes_dj: true, email_diario: false,
  });

  // Segurança
  const [pwdForm, setPwdForm] = useState({ current_password: "", new_password: "", confirm: "" });
  const [showPwds, setShowPwds] = useState({ current: false, new: false, confirm: false });
  const [pwdError, setPwdError] = useState("");
  const [pwdSuccess, setPwdSuccess] = useState(false);
  const [changingPwd, setChangingPwd] = useState(false);

  useEffect(() => {
    if (!perfilLoaded) loadPerfil();
    loadNotifPrefs();
  }, []);

  async function loadNotifPrefs() {
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/users/me/notification-preferences", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        if (data.prefs && Object.keys(data.prefs).length > 0) {
          setNotifs((prev) => ({ ...prev, ...data.prefs }));
          return;
        }
      }
    } catch {}
    // Fase 206.2 — antes da persistência no backend, essas preferências só
    // existiam no localStorage do navegador. Migra pro backend no próximo save.
    try {
      const local = localStorage.getItem("afj_notif_prefs");
      if (local) setNotifs((prev) => ({ ...prev, ...JSON.parse(local) }));
    } catch {}
  }

  async function loadPerfil() {
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/users/me", { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) {
        const data = await res.json();
        setPerfil((p) => ({
          ...p,
          full_name: data.full_name ?? "",
          email: data.email ?? "",
          telefone: data.telefone ?? "",
        }));
        setPerfilLoaded(true);
      }
    } catch {}
  }

  async function savePerfil() {
    setSaving(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      await fetch("/api/v1/users/me", {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          full_name: perfil.full_name,
          telefone: perfil.telefone,
          oab_number: perfil.oab_number || null,
          oab_uf: perfil.oab_uf || null,
        }),
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
      // Update localStorage user
      try {
        const stored = localStorage.getItem("afj_user");
        if (stored) {
          const u = JSON.parse(stored);
          localStorage.setItem("afj_user", JSON.stringify({ ...u, full_name: perfil.full_name }));
        }
      } catch {}
    } finally {
      setSaving(false);
    }
  }

  async function saveNotifs() {
    setSaving(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      await fetch("/api/v1/users/me/notification-preferences", {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ prefs: notifs }),
      });
      // Fase 206.2 — persistido no backend agora; mantém o localStorage como
      // cache instantâneo (evita flash de "tudo ligado" no próximo carregamento).
      localStorage.setItem("afj_notif_prefs", JSON.stringify(notifs));
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } finally {
      setSaving(false);
    }
  }

  async function changePassword(e: React.FormEvent) {
    e.preventDefault();
    setPwdError("");
    if (pwdForm.new_password !== pwdForm.confirm) {
      setPwdError("As senhas não conferem.");
      return;
    }
    if (pwdForm.new_password.length < 8) {
      setPwdError("A nova senha deve ter ao menos 8 caracteres.");
      return;
    }
    setChangingPwd(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/auth/password", {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ current_password: pwdForm.current_password, new_password: pwdForm.new_password }),
      });
      const data = await res.json();
      if (res.ok) {
        setPwdSuccess(true);
        setPwdForm({ current_password: "", new_password: "", confirm: "" });
        setTimeout(() => setPwdSuccess(false), 4000);
      } else {
        setPwdError(data.detail || "Erro ao alterar senha.");
      }
    } finally {
      setChangingPwd(false);
    }
  }

  const inputCls = "w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold bg-white";

  return (
    <div className="flex gap-5">
      {/* Tabs laterais */}
      <div className="afj-card p-2 h-fit w-48 flex-shrink-0">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-sm text-sm transition-colors ${
                activeTab === tab.id
                  ? "bg-afj-gold/10 text-afj-gold font-medium"
                  : "text-afj-black/60 hover:bg-afj-cream"
              }`}
            >
              <Icon size={15} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Conteúdo */}
      <div className="flex-1 afj-card p-6 space-y-5">

        {/* ── Tab: Perfil ──────────────────────────────────────────────── */}
        {activeTab === "perfil" && (
          <>
            <h2 className="font-semibold text-afj-black">Dados do Perfil</h2>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-xs text-afj-black/60 block mb-1">Nome Completo</label>
                <input
                  type="text"
                  value={perfil.full_name}
                  onChange={(e) => setPerfil({ ...perfil, full_name: e.target.value })}
                  className={inputCls}
                  placeholder="Dr. Nome Sobrenome"
                />
              </div>
              <div>
                <label className="text-xs text-afj-black/60 block mb-1">E-mail</label>
                <input
                  type="email"
                  value={perfil.email}
                  disabled
                  className={`${inputCls} opacity-50 cursor-not-allowed`}
                  placeholder="seu@email.com"
                />
                <p className="text-[10px] text-afj-black/35 mt-0.5">E-mail não pode ser alterado aqui.</p>
              </div>
              <div>
                <label className="text-xs text-afj-black/60 block mb-1">WhatsApp</label>
                <input
                  type="tel"
                  value={perfil.telefone}
                  onChange={(e) => setPerfil({ ...perfil, telefone: e.target.value })}
                  className={inputCls}
                  placeholder="(68) 99999-9999"
                />
                <p className="text-[10px] text-afj-black/35 mt-0.5">
                  Recebe alertas de prazo e intimações se o escritório conectar o WhatsApp em Integrações.
                </p>
              </div>
              <div>
                <label className="text-xs text-afj-black/60 block mb-1">Número OAB</label>
                <input
                  type="text"
                  value={perfil.oab_number}
                  onChange={(e) => setPerfil({ ...perfil, oab_number: e.target.value })}
                  className={inputCls}
                  placeholder="000000"
                />
              </div>
              <div>
                <label className="text-xs text-afj-black/60 block mb-1">UF da OAB</label>
                <input
                  type="text"
                  value={perfil.oab_uf}
                  onChange={(e) => setPerfil({ ...perfil, oab_uf: e.target.value.toUpperCase().slice(0, 2) })}
                  className={inputCls}
                  placeholder="SP"
                  maxLength={2}
                />
              </div>
            </div>
            <div className="flex justify-end pt-3 border-t border-afj-cream-dark">
              <button
                onClick={savePerfil}
                disabled={saving}
                className="btn-afj-primary rounded-sm flex items-center gap-2 disabled:opacity-60"
              >
                {saving ? <Loader2 size={14} className="animate-spin" /> : saved ? <CheckCircle size={14} /> : <Save size={14} />}
                {saving ? "Salvando..." : saved ? "Salvo!" : "Salvar Perfil"}
              </button>
            </div>
          </>
        )}

        {/* ── Tab: Notificações ────────────────────────────────────────── */}
        {activeTab === "notificacoes" && (
          <>
            <h2 className="font-semibold text-afj-black">Preferências de Notificação</h2>

            {/* Push */}
            {"PushManager" in (typeof window !== "undefined" ? window : {}) && (
              <div className="p-4 bg-afj-gold/5 border border-afj-gold/20 rounded-sm flex items-start gap-3">
                <div className="flex-1">
                  <p className="text-sm font-medium text-afj-black">Notificações Push</p>
                  <p className="text-xs text-afj-black/50 mt-0.5">
                    {subscribed ? "Ativas — você receberá alertas mesmo com o sistema fechado." : "Receba alertas mesmo com o sistema fechado."}
                  </p>
                </div>
                <button
                  onClick={() => subscribed ? unsubscribe() : subscribe()}
                  disabled={pushLoading}
                  className={`text-xs px-3 py-1.5 rounded-sm font-semibold uppercase tracking-wider disabled:opacity-50 ${
                    subscribed
                      ? "border border-red-300 text-red-600 hover:bg-red-50"
                      : "btn-afj-primary"
                  }`}
                >
                  {pushLoading ? "..." : subscribed ? "Desativar" : "Ativar"}
                </button>
              </div>
            )}

            <div className="space-y-2.5">
              {[
                { key: "novos_prazos", label: "Novos prazos processuais", desc: "Alertas quando prazos se aproximam (3, 7, 15 dias)" },
                { key: "novas_aprovacoes", label: "Aprovações pendentes", desc: "Quando um agente gerar item para revisão" },
                { key: "agente_concluiu", label: "Agente concluiu tarefa", desc: "Quando uma execução de agente terminar" },
                { key: "publicacoes_dj", label: "Publicações no Diário de Justiça", desc: "Quando uma publicação for encontrada" },
                { key: "email_diario", label: "Resumo diário por e-mail", desc: "Sumário matinal das atividades e prazos" },
              ].map(({ key, label, desc }) => (
                <label key={key} className="flex items-start gap-3 p-3 border border-afj-cream-dark rounded-sm cursor-pointer hover:bg-afj-cream/30 transition-colors">
                  <input
                    type="checkbox"
                    checked={(notifs as Record<string, boolean>)[key]}
                    onChange={(e) => setNotifs({ ...notifs, [key]: e.target.checked })}
                    className="mt-0.5 accent-afj-gold"
                  />
                  <div>
                    <p className="text-sm font-medium text-afj-black">{label}</p>
                    <p className="text-xs text-afj-black/45 mt-0.5">{desc}</p>
                  </div>
                </label>
              ))}
            </div>
            <div className="flex justify-end pt-3 border-t border-afj-cream-dark">
              <button
                onClick={saveNotifs}
                disabled={saving}
                className="btn-afj-primary rounded-sm flex items-center gap-2 disabled:opacity-60"
              >
                {saved ? <CheckCircle size={14} /> : <Save size={14} />}
                {saved ? "Salvo!" : "Salvar Preferências"}
              </button>
            </div>
          </>
        )}

        {/* ── Tab: Segurança ───────────────────────────────────────────── */}
        {activeTab === "seguranca" && (
          <>
            <h2 className="font-semibold text-afj-black">Segurança da Conta</h2>
            <div className="space-y-5">
              {/* Alterar senha */}
              <div className="p-5 border border-afj-cream-dark rounded-sm">
                <h3 className="text-sm font-semibold text-afj-black mb-4">Alterar Senha</h3>
                <form onSubmit={changePassword} className="space-y-3">
                  {[
                    { label: "Senha atual", key: "current_password", showKey: "current" as const },
                    { label: "Nova senha", key: "new_password", showKey: "new" as const },
                    { label: "Confirmar nova senha", key: "confirm", showKey: "confirm" as const },
                  ].map(({ label, key, showKey }) => (
                    <div key={key}>
                      <label className="text-xs text-afj-black/60 block mb-1">{label}</label>
                      <div className="relative">
                        <input
                          type={showPwds[showKey] ? "text" : "password"}
                          value={(pwdForm as Record<string, string>)[key]}
                          onChange={(e) => setPwdForm((f) => ({ ...f, [key]: e.target.value }))}
                          className={`${inputCls} pr-10`}
                          placeholder="••••••••"
                          required
                        />
                        <button
                          type="button"
                          onClick={() => setShowPwds((s) => ({ ...s, [showKey]: !s[showKey] }))}
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-afj-black/30 hover:text-afj-black/60"
                          aria-label={showPwds[showKey] ? "Ocultar" : "Mostrar"}
                        >
                          {showPwds[showKey] ? <EyeOff size={14} /> : <Eye size={14} />}
                        </button>
                      </div>
                    </div>
                  ))}

                  {pwdError && <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-sm px-3 py-2">{pwdError}</p>}
                  {pwdSuccess && <p className="text-xs text-green-700 bg-green-50 border border-green-200 rounded-sm px-3 py-2">Senha alterada com sucesso!</p>}

                  <button type="submit" disabled={changingPwd} className="btn-afj-primary rounded-sm flex items-center gap-2 disabled:opacity-60">
                    {changingPwd ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                    {changingPwd ? "Alterando..." : "Alterar Senha"}
                  </button>
                </form>
              </div>

              {/* MFA */}
              <div className="p-5 border border-afj-cream-dark rounded-sm">
                <h3 className="text-sm font-semibold text-afj-black mb-1">Autenticação em Dois Fatores (MFA)</h3>
                <p className="text-xs text-afj-black/50 mb-4">Adicione uma camada extra de segurança com TOTP (Google Authenticator, Authy).</p>
                <button className="btn-afj-outline rounded-sm">Configurar MFA</button>
              </div>

              {/* LGPD */}
              <div className="p-4 bg-amber-50 border border-amber-200 rounded-sm">
                <h3 className="text-sm font-semibold text-amber-800 mb-1">Conformidade LGPD</h3>
                <p className="text-xs text-amber-700">
                  Suas ações são registradas para fins de auditoria conforme a LGPD. Dados pessoais de clientes são criptografados em repouso.
                </p>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
