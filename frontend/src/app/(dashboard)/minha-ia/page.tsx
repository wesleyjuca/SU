"use client";
import { useEffect, useState } from "react";
import { Bot, KeyRound, CheckCircle2, XCircle, Loader2, Sparkles, Eye, EyeOff } from "lucide-react";

type Settings = { provider: string; model: string; enabled: boolean; has_key: boolean };

const MODEL_HINTS: Record<string, string> = {
  gemini: "ex.: gemini-2.0-flash (grátis) · gemini-1.5-pro",
  anthropic: "ex.: claude-sonnet-4-6 · claude-opus-4-7",
};
const KEY_HELP: Record<string, { label: string; url: string }> = {
  gemini: { label: "Google AI Studio", url: "https://aistudio.google.com/apikey" },
  anthropic: { label: "Anthropic Console", url: "https://console.anthropic.com" },
};

export default function MinhaIAPage() {
  const [provider, setProvider] = useState("gemini");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [hasKey, setHasKey] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    fetch("/api/v1/users/me/ai-settings", { headers: authH() })
      .then((r) => (r.ok ? r.json() : null))
      .then((d: Settings | null) => {
        if (d) {
          setProvider(d.provider || "gemini");
          setModel(d.model || "");
          setEnabled(d.enabled);
          setHasKey(d.has_key);
        }
      })
      .finally(() => setLoading(false));
  }, []);

  function authH(): HeadersInit {
    const t = typeof window !== "undefined" ? localStorage.getItem("afj_access_token") : null;
    return { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) };
  }

  async function save() {
    setSaving(true); setMsg(null);
    try {
      const body: Record<string, unknown> = { provider, model, enabled };
      if (apiKey.trim()) body.api_key = apiKey.trim();
      const res = await fetch("/api/v1/users/me/ai-settings", { method: "PUT", headers: authH(), body: JSON.stringify(body) });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) { setMsg({ ok: false, text: data.detail || "Erro ao salvar" }); return; }
      setHasKey(data.has_key); setApiKey("");
      setMsg({ ok: true, text: "Configuração salva com sucesso." });
    } catch { setMsg({ ok: false, text: "Falha de conexão." }); }
    finally { setSaving(false); }
  }

  async function test() {
    setTesting(true); setMsg(null);
    try {
      const res = await fetch("/api/v1/users/me/ai-settings/test", { method: "POST", headers: authH() });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.ok) setMsg({ ok: true, text: `Conexão OK com ${provider}. Resposta: "${data.sample || "…"}"` });
      else setMsg({ ok: false, text: data.error || data.detail || "Falha no teste — verifique a chave." });
    } catch { setMsg({ ok: false, text: "Falha de conexão." }); }
    finally { setTesting(false); }
  }

  if (loading) return <div className="p-8 flex justify-center"><Loader2 className="animate-spin text-afj-gold" /></div>;

  const help = KEY_HELP[provider];

  return (
    <div className="max-w-2xl mx-auto p-6">
      <div className="afj-page-header">
        <div>
          <h1 className="afj-page-title flex items-center gap-2"><Bot size={20} className="text-afj-gold" /> Minha IA</h1>
          <p className="text-afj-black/45 text-sm mt-1">Use sua própria IA (grátis ou paga) — os tokens saem da sua conta e o crédito do sistema é preservado.</p>
        </div>
      </div>

      <div className="afj-card p-6 space-y-5">
        {/* Campos-isca ocultos: absorvem o autofill do navegador (email/senha de login)
            para que ele não preencha os campos reais de modelo/chave. */}
        <input type="text" name="username" autoComplete="username" tabIndex={-1} aria-hidden="true"
          style={{ position: "absolute", opacity: 0, height: 0, width: 0, pointerEvents: "none" }} />
        <input type="password" name="password" autoComplete="current-password" tabIndex={-1} aria-hidden="true"
          style={{ position: "absolute", opacity: 0, height: 0, width: 0, pointerEvents: "none" }} />

        <div className="flex items-start gap-2 text-xs text-afj-black/55 bg-afj-cream/60 border border-afj-cream-dark rounded-sm p-3">
          <Sparkles size={14} className="text-afj-gold flex-shrink-0 mt-0.5" />
          <span>Quando ativado, seus agentes usam a chave configurada aqui. Se desativar, o sistema usa a IA padrão do escritório.</span>
        </div>

        <div>
          <label className="text-[10px] font-semibold text-afj-black/55 uppercase tracking-widest block mb-1.5">Provedor</label>
          <select value={provider} onChange={(e) => setProvider(e.target.value)}
            className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-3 py-2.5 text-sm focus:outline-none focus:border-afj-gold">
            <option value="gemini">Google Gemini</option>
            <option value="anthropic">Anthropic Claude</option>
          </select>
        </div>

        <div>
          <label className="text-[10px] font-semibold text-afj-black/55 uppercase tracking-widest block mb-1.5">Modelo (opcional)</label>
          <input value={model} onChange={(e) => setModel(e.target.value)} placeholder={MODEL_HINTS[provider]}
            name="afj-ai-model" autoComplete="off" data-lpignore="true" data-1p-ignore data-form-type="other"
            className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-3 py-2.5 text-sm placeholder:text-afj-black/25 focus:outline-none focus:border-afj-gold" />
        </div>

        <div>
          <label className="text-[10px] font-semibold text-afj-black/55 uppercase tracking-widest flex items-center gap-1.5 mb-1.5">
            <KeyRound size={12} /> Chave de API {hasKey && <span className="text-green-600 normal-case tracking-normal font-normal">· chave configurada</span>}
          </label>
          <div className="relative">
            <input type={showKey ? "text" : "password"} value={apiKey} onChange={(e) => setApiKey(e.target.value)}
              placeholder={hasKey ? "•••••••••• (deixe em branco para manter)" : "cole sua chave de API aqui"}
              name="afj-ai-secret" autoComplete="new-password" data-lpignore="true" data-1p-ignore data-form-type="other"
              spellCheck={false}
              className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-3 py-2.5 pr-11 text-sm placeholder:text-afj-black/25 focus:outline-none focus:border-afj-gold" />
            <button type="button" onClick={() => setShowKey((v) => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-afj-black/30 hover:text-afj-black/60"
              aria-label={showKey ? "Ocultar chave" : "Mostrar chave"}>
              {showKey ? <EyeOff size={15} /> : <Eye size={15} />}
            </button>
          </div>
          {help && (
            <p className="text-[11px] text-afj-black/40 mt-1.5">
              Obtenha a chave em{" "}
              <a href={help.url} target="_blank" rel="noreferrer" className="text-afj-gold hover:underline">{help.label}</a>.
            </p>
          )}
        </div>

        <label className="flex items-center gap-2.5 cursor-pointer">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} className="accent-afj-gold w-4 h-4" />
          <span className="text-sm text-afj-black/75">Usar minha IA nas execuções dos agentes</span>
        </label>

        {msg && (
          <div className={`flex items-start gap-2 text-xs rounded-sm px-3 py-2.5 ${msg.ok ? "text-green-700 bg-green-50 border border-green-200" : "text-red-700 bg-red-50 border border-red-200"}`}>
            {msg.ok ? <CheckCircle2 size={14} className="flex-shrink-0 mt-0.5" /> : <XCircle size={14} className="flex-shrink-0 mt-0.5" />}
            <span className="leading-relaxed">{msg.text}</span>
          </div>
        )}

        <div className="flex items-center gap-3 pt-1">
          <button onClick={save} disabled={saving} className="btn-afj-primary py-2.5 disabled:opacity-50 flex items-center gap-2">
            {saving && <Loader2 size={14} className="animate-spin" />} Salvar
          </button>
          <button onClick={test} disabled={testing || !hasKey} className="btn-afj-outline py-2.5 disabled:opacity-40 flex items-center gap-2" title={!hasKey ? "Salve uma chave primeiro" : "Testar conexão"}>
            {testing && <Loader2 size={14} className="animate-spin" />} Testar conexão
          </button>
        </div>
      </div>
    </div>
  );
}
