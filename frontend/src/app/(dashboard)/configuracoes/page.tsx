"use client";
import { useState } from "react";
import { Settings, User, Bell, Shield, Palette, Save, CheckCircle, Loader2 } from "lucide-react";
import { applyTheme } from "@/lib/theme";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { useThemeStore } from "@/store";

const TABS = [
  { id: "perfil", label: "Perfil", icon: User },
  { id: "notificacoes", label: "Notificações", icon: Bell },
  { id: "seguranca", label: "Segurança", icon: Shield },
  { id: "aparencia", label: "Aparência", icon: Palette },
];

export default function ConfiguracoesPage() {
  const [activeTab, setActiveTab] = useState("perfil");
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const { theme, setTheme } = useThemeStore();

  const [perfil, setPerfil] = useState({ full_name: "", email: "", oab_number: "", oab_uf: "" });
  const [notifs, setNotifs] = useState({
    novos_prazos: true, novas_aprovacoes: true, agente_concluiu: true,
    publicacoes_dj: true, email_diario: false,
  });

  // Aparência state (local copy for live preview)
  const [branding, setBranding] = useState({
    primaryColor: theme.primaryColor,
    appName: theme.appName,
    logoUrl: theme.logoUrl ?? "",
  });

  function handleSave() {
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  }

  async function saveBranding() {
    setSaving(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/tenant/branding", {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          primary_color: branding.primaryColor,
          app_name: branding.appName,
          logo_url: branding.logoUrl || null,
        }),
      });
      if (res.ok) {
        const updated = await res.json();
        const newTheme = {
          ...theme,
          primaryColor: updated.primary_color,
          appName: updated.app_name,
          logoUrl: updated.logo_url,
        };
        setTheme(newTheme);
        applyTheme(newTheme);
        setSaved(true);
        setTimeout(() => setSaved(false), 3000);
      }
    } finally {
      setSaving(false);
    }
  }

  function previewColor(color: string) {
    applyTheme({ ...theme, primaryColor: color });
    setBranding((b) => ({ ...b, primaryColor: color }));
  }

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Configurações" }]} />
      <div>
        <h1 className="font-display text-2xl font-semibold text-afj-black">Configurações</h1>
        <p className="text-afj-black/50 text-sm">Gerencie seu perfil, notificações e preferências do sistema</p>
      </div>

      <div className="flex gap-5">
        {/* Sidebar de tabs */}
        <div className="afj-card p-2 h-fit w-48 flex-shrink-0">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-md text-sm transition-colors ${
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
        <div className="flex-1 afj-card p-5 space-y-5">
          {activeTab === "perfil" && (
            <>
              <h2 className="font-semibold text-afj-black">Dados do Perfil</h2>
              <div className="grid grid-cols-2 gap-4">
                {[
                  { label: "Nome Completo", key: "full_name", type: "text" },
                  { label: "E-mail", key: "email", type: "email" },
                  { label: "Número OAB", key: "oab_number", type: "text" },
                  { label: "UF da OAB", key: "oab_uf", type: "text" },
                ].map(({ label, key, type }) => (
                  <div key={key}>
                    <label className="text-xs text-afj-black/60 block mb-1">{label}</label>
                    <input
                      type={type}
                      value={(perfil as any)[key]}
                      onChange={(e) => setPerfil({ ...perfil, [key]: e.target.value })}
                      className="w-full border border-afj-cream-dark rounded-md px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                      placeholder={label}
                    />
                  </div>
                ))}
              </div>
            </>
          )}

          {activeTab === "notificacoes" && (
            <>
              <h2 className="font-semibold text-afj-black">Preferências de Notificação</h2>
              <div className="space-y-3">
                {[
                  { key: "novos_prazos", label: "Novos prazos processuais", desc: "Alertas quando prazos se aproximam (3, 7, 15 dias)" },
                  { key: "novas_aprovacoes", label: "Novas aprovações pendentes", desc: "Quando um agente gerar item para revisão" },
                  { key: "agente_concluiu", label: "Agente concluiu tarefa", desc: "Quando uma execução de agente terminar" },
                  { key: "publicacoes_dj", label: "Publicações no Diário de Justiça", desc: "Quando uma publicação for encontrada para seus processos" },
                  { key: "email_diario", label: "Resumo diário por e-mail", desc: "Sumário matinal das atividades e prazos" },
                ].map(({ key, label, desc }) => (
                  <label key={key} className="flex items-start gap-3 p-3 border border-afj-cream-dark rounded-md cursor-pointer hover:bg-afj-cream/30 transition-colors">
                    <input
                      type="checkbox"
                      checked={(notifs as any)[key]}
                      onChange={(e) => setNotifs({ ...notifs, [key]: e.target.checked })}
                      className="mt-0.5 accent-afj-gold"
                    />
                    <div>
                      <p className="text-sm font-medium text-afj-black">{label}</p>
                      <p className="text-xs text-afj-black/50 mt-0.5">{desc}</p>
                    </div>
                  </label>
                ))}
              </div>
            </>
          )}

          {activeTab === "seguranca" && (
            <>
              <h2 className="font-semibold text-afj-black">Segurança da Conta</h2>
              <div className="space-y-4">
                <div className="p-4 border border-afj-cream-dark rounded-md">
                  <h3 className="text-sm font-semibold text-afj-black mb-3">Alterar Senha</h3>
                  <div className="space-y-3">
                    {["Senha atual", "Nova senha", "Confirmar nova senha"].map((label) => (
                      <div key={label}>
                        <label className="text-xs text-afj-black/60 block mb-1">{label}</label>
                        <input
                          type="password"
                          className="w-full border border-afj-cream-dark rounded-md px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                          placeholder="••••••••"
                        />
                      </div>
                    ))}
                  </div>
                </div>
                <div className="p-4 border border-afj-cream-dark rounded-md">
                  <h3 className="text-sm font-semibold text-afj-black mb-1">Autenticação em Dois Fatores (MFA)</h3>
                  <p className="text-xs text-afj-black/50 mb-3">Adicione uma camada extra de segurança com TOTP (Google Authenticator, Authy, etc.)</p>
                  <button className="btn-afj-outline rounded-md text-sm">Configurar MFA</button>
                </div>
                <div className="p-4 bg-amber-50 border border-amber-200 rounded-md">
                  <h3 className="text-sm font-semibold text-amber-800 mb-1">Conformidade LGPD</h3>
                  <p className="text-xs text-amber-700">Suas ações no sistema são registradas para fins de auditoria conforme a LGPD. Dados pessoais de clientes são criptografados em repouso.</p>
                </div>
              </div>
            </>
          )}

          {activeTab === "aparencia" && (
            <>
              <h2 className="font-semibold text-afj-black">Aparência do Sistema</h2>
              <p className="text-xs text-afj-black/50">Alterações aplicadas instantaneamente e salvas para todos os usuários do escritório.</p>
              <div className="space-y-5">
                {/* Nome do sistema */}
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">Nome do Sistema</label>
                  <input
                    type="text"
                    value={branding.appName}
                    onChange={(e) => setBranding((b) => ({ ...b, appName: e.target.value }))}
                    className="w-full border border-afj-cream-dark rounded-md px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                    placeholder="AFJ CORE"
                  />
                </div>

                {/* Cor primária */}
                <div>
                  <label className="text-xs text-afj-black/60 block mb-2">Cor Primária (dourado, acento)</label>
                  <div className="flex items-center gap-3">
                    <input
                      type="color"
                      value={branding.primaryColor}
                      onChange={(e) => previewColor(e.target.value)}
                      className="w-12 h-10 rounded border border-afj-cream-dark cursor-pointer"
                    />
                    <input
                      type="text"
                      value={branding.primaryColor}
                      onChange={(e) => {
                        setBranding((b) => ({ ...b, primaryColor: e.target.value }));
                        if (/^#[0-9A-Fa-f]{6}$/.test(e.target.value)) {
                          previewColor(e.target.value);
                        }
                      }}
                      className="flex-1 border border-afj-cream-dark rounded-md px-3 py-2 text-sm font-mono focus:outline-none focus:border-afj-gold"
                      placeholder="#C9A84C"
                    />
                    <div
                      className="w-10 h-10 rounded border border-afj-cream-dark"
                      style={{ backgroundColor: branding.primaryColor }}
                    />
                  </div>
                  <div className="flex gap-2 mt-2">
                    {["#C9A84C", "#1A6EAB", "#4CAF50", "#9C27B0", "#E91E63", "#FF5722"].map((c) => (
                      <button
                        key={c}
                        onClick={() => previewColor(c)}
                        className="w-7 h-7 rounded-full border-2 border-white shadow-sm hover:scale-110 transition-transform"
                        style={{ backgroundColor: c }}
                        title={c}
                      />
                    ))}
                  </div>
                </div>

                {/* URL do logo */}
                <div>
                  <label className="text-xs text-afj-black/60 block mb-1">URL do Logo (opcional)</label>
                  <input
                    type="url"
                    value={branding.logoUrl}
                    onChange={(e) => setBranding((b) => ({ ...b, logoUrl: e.target.value }))}
                    className="w-full border border-afj-cream-dark rounded-md px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
                    placeholder="https://..."
                  />
                  {branding.logoUrl && (
                    <img src={branding.logoUrl} alt="Logo preview" className="mt-2 h-10 object-contain" />
                  )}
                </div>

                {/* Preview */}
                <div className="p-4 rounded-lg border border-afj-cream-dark bg-afj-cream/30">
                  <p className="text-xs text-afj-black/50 mb-2">Pré-visualização</p>
                  <div className="flex items-center gap-3">
                    <div
                      className="w-9 h-9 rounded-lg flex items-center justify-center"
                      style={{ backgroundColor: `${branding.primaryColor}20`, border: `1px solid ${branding.primaryColor}50` }}
                    >
                      <span className="font-bold text-sm" style={{ color: branding.primaryColor }}>
                        {branding.appName.slice(0, 2).toUpperCase()}
                      </span>
                    </div>
                    <div>
                      <p className="text-sm font-semibold" style={{ color: "#1A1A1A" }}>{branding.appName}</p>
                      <p className="text-xs text-afj-black/40">Sistema Jurídico IA</p>
                    </div>
                  </div>
                </div>
              </div>

              <div className="flex justify-end pt-3 border-t border-afj-cream-dark">
                <button
                  onClick={saveBranding}
                  disabled={saving}
                  className="btn-afj-primary rounded-md flex items-center gap-2 disabled:opacity-60"
                >
                  {saving ? <Loader2 size={14} className="animate-spin" /> : saved ? <CheckCircle size={14} /> : <Save size={14} />}
                  {saving ? "Salvando..." : saved ? "Salvo!" : "Salvar Aparência"}
                </button>
              </div>
            </>
          )}

          {/* Botão salvar (outros tabs) */}
          {activeTab !== "aparencia" && (
            <div className="flex justify-end pt-3 border-t border-afj-cream-dark">
              <button
                onClick={handleSave}
                className="btn-afj-primary rounded-md flex items-center gap-2"
              >
                {saved ? <CheckCircle size={14} /> : <Save size={14} />}
                {saved ? "Salvo!" : "Salvar Alterações"}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
