"use client";
import { useState } from "react";
import { Settings, User, Bell, Shield, Palette, Save, CheckCircle } from "lucide-react";

const TABS = [
  { id: "perfil", label: "Perfil", icon: User },
  { id: "notificacoes", label: "Notificações", icon: Bell },
  { id: "seguranca", label: "Segurança", icon: Shield },
  { id: "aparencia", label: "Aparência", icon: Palette },
];

export default function ConfiguracoesPage() {
  const [activeTab, setActiveTab] = useState("perfil");
  const [saved, setSaved] = useState(false);
  const [perfil, setPerfil] = useState({
    full_name: "",
    email: "",
    oab_number: "",
    oab_uf: "",
  });
  const [notifs, setNotifs] = useState({
    novos_prazos: true,
    novas_aprovacoes: true,
    agente_concluiu: true,
    publicacoes_dj: true,
    email_diario: false,
  });

  function handleSave() {
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  }

  return (
    <div className="max-w-4xl mx-auto space-y-5">
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
              <h2 className="font-semibold text-afj-black">Aparência</h2>
              <div className="space-y-4">
                <div>
                  <label className="text-xs text-afj-black/60 block mb-2">Tema</label>
                  <div className="grid grid-cols-2 gap-3">
                    {[
                      { id: "light", label: "Claro", preview: "bg-white border-2 border-afj-gold" },
                      { id: "system", label: "Sistema", preview: "bg-gradient-to-r from-white to-gray-800 border-2 border-afj-cream-dark" },
                    ].map((t) => (
                      <button key={t.id} className={`p-4 rounded-md ${t.preview} text-center text-sm font-medium`}>
                        {t.label}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="text-xs text-afj-black/60 block mb-2">Densidade da Interface</label>
                  <div className="flex gap-3">
                    {["Compacta", "Normal", "Espaçada"].map((d) => (
                      <button key={d} className="flex-1 py-2 border border-afj-cream-dark rounded-md text-sm text-afj-black hover:border-afj-gold first:border-afj-gold first:bg-afj-gold/5 first:text-afj-gold">
                        {d}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </>
          )}

          {/* Botão salvar */}
          <div className="flex justify-end pt-3 border-t border-afj-cream-dark">
            <button
              onClick={handleSave}
              className="btn-afj-primary rounded-md flex items-center gap-2"
            >
              {saved ? <CheckCircle size={14} /> : <Save size={14} />}
              {saved ? "Salvo!" : "Salvar Alterações"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
