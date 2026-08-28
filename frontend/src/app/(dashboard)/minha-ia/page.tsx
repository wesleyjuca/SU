"use client";
import { useEffect, useState } from "react";
import {
  Bot, KeyRound, CheckCircle2, XCircle, Loader2, Sparkles, Eye, EyeOff,
  SlidersHorizontal, ChevronDown, ChevronUp, Plus, Star, FlaskConical, Copy, Pencil, Trash2, X, Scale, Shuffle,
} from "lucide-react";
import { useConfirmDialog } from "@/hooks/useConfirmDialog";

type ProviderInfo = {
  nome: string;
  auth_methods: string[];
  base_url: string | null;
  requires_key: boolean;
  oauth_disponivel: boolean;
  modelo_sugerido: string;
  obter: string;
};

type AIConfig = {
  id: string;
  provider: string;
  display_name: string;
  auth_method: string;
  model: string;
  base_url: string | null;
  enabled: boolean;
  is_default: boolean;
  priority: number | null;
  status: string;
  has_credential: boolean;
  last_tested_at: string | null;
  last_error: string | null;
};

type AIConfigStats = {
  total_calls: number;
  success_rate: number;
  avg_latency_ms: number;
  total_cost_usd: number;
  total_tokens: number;
  last_used_at: string | null;
  last_error: string | null;
};

type CompareResult = {
  config_id: string;
  display_name: string;
  provider: string;
  model: string;
  content: string | null;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  latency_ms: number;
  error: string | null;
};

// Áreas com override de modelo (devem casar com OVERRIDABLE_TASKS do backend)
const TASK_LABELS: { task: string; label: string }[] = [
  { task: "generate_petition", label: "Gerar Petições" },
  { task: "review_document", label: "Revisão de Documentos" },
  { task: "manage_contract", label: "Contratos" },
  { task: "search_jurisprudence", label: "Pesquisa de Jurisprudência" },
  { task: "generate_strategy", label: "Estratégia" },
  { task: "analytics_report", label: "Relatórios / Analytics" },
];

function authH(): HeadersInit {
  const t = typeof window !== "undefined" ? localStorage.getItem("afj_access_token") : null;
  return { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) };
}

export default function MinhaIAPage() {
  const { ask, confirmDialog } = useConfirmDialog();
  const [configs, setConfigs] = useState<AIConfig[]>([]);
  const [stats, setStats] = useState<Record<string, AIConfigStats>>({});
  const [providers, setProviders] = useState<Record<string, ProviderInfo>>({});
  const [loading, setLoading] = useState(true);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [modal, setModal] = useState<{ mode: "add" | "edit"; config: AIConfig | null } | null>(null);
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [showOverrides, setShowOverrides] = useState(false);
  const [modoBalanceamento, setModoBalanceamento] = useState<string>("padrao");
  const [showBalanceamento, setShowBalanceamento] = useState(false);
  const [salvandoBalanceamento, setSalvandoBalanceamento] = useState(false);
  const [showComparar, setShowComparar] = useState(false);
  const [compararSelecionadas, setCompararSelecionadas] = useState<string[]>([]);
  const [compararPrompt, setCompararPrompt] = useState("");
  const [comparando, setComparando] = useState(false);
  const [compararResultados, setCompararResultados] = useState<CompareResult[] | null>(null);

  async function carregar() {
    setLoading(true);
    try {
      const [rProv, rCfg, rStats, rBalance] = await Promise.all([
        fetch("/api/v1/users/me/ai-providers", { headers: authH() }),
        fetch("/api/v1/users/me/ai-configs", { headers: authH() }),
        fetch("/api/v1/users/me/ai-configs/stats", { headers: authH() }),
        fetch("/api/v1/users/me/ai-settings/balance-mode", { headers: authH() }),
      ]);
      if (rCfg.status === 401) {
        if (typeof window !== "undefined") {
          localStorage.removeItem("afj_access_token");
          window.location.href = "/login";
        }
        return;
      }
      if (rProv.ok) setProviders((await rProv.json()).providers || {});
      if (rCfg.ok) setConfigs((await rCfg.json()).configs || []);
      if (rStats.ok) setStats((await rStats.json()).stats || {});
      if (rBalance.ok) setModoBalanceamento((await rBalance.json()).mode || "padrao");
    } catch {
      setMsg({ ok: false, text: "Falha ao carregar suas IAs." });
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    carregar();
    fetch("/api/v1/users/me/ai-settings/overrides", { headers: authH() })
      .then((r) => (r.ok ? r.json() : null))
      .then((d: { overrides: { task_type: string; provider_config_id: string | null; model: string | null }[] } | null) => {
        if (d?.overrides) {
          const map: Record<string, string> = {};
          d.overrides.forEach((o) => { if (o.provider_config_id) map[o.task_type] = o.provider_config_id; });
          setOverrides(map);
          if (d.overrides.length > 0) setShowOverrides(true);
        }
      })
      .catch(() => {});
    // Feedback do retorno OAuth do OpenRouter (?oauth=openrouter_ok|openrouter_erro), Fase 137.2
    const p = new URLSearchParams(window.location.search);
    const oauth = p.get("oauth");
    if (oauth) {
      if (oauth.endsWith("_ok")) setMsg({ ok: true, text: "OpenRouter conectado com sucesso!" });
      else setMsg({ ok: false, text: "Falha ao conectar com o OpenRouter. Tente novamente ou cole a chave manualmente." });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function testar(id: string) {
    setTestingId(id); setMsg(null);
    try {
      const res = await fetch(`/api/v1/users/me/ai-configs/${id}/test`, { method: "POST", headers: authH() });
      const data = await res.json().catch(() => ({}));
      if (res.ok && data.ok) setMsg({ ok: true, text: `Conexão OK. Resposta: "${data.sample || "…"}"` });
      else setMsg({ ok: false, text: data.error || data.detail || "Falha no teste — verifique a chave." });
      await carregar();
    } catch { setMsg({ ok: false, text: "Falha de conexão." }); }
    finally { setTestingId(null); }
  }

  async function tornarPadrao(id: string) {
    setBusyId(id); setMsg(null);
    try {
      const res = await fetch(`/api/v1/users/me/ai-configs/${id}/set-default`, { method: "POST", headers: authH() });
      if (!res.ok) { const d = await res.json().catch(() => ({})); setMsg({ ok: false, text: d.detail || "Erro ao definir como padrão" }); return; }
      await carregar();
    } catch { setMsg({ ok: false, text: "Falha de conexão." }); }
    finally { setBusyId(null); }
  }

  async function duplicar(id: string) {
    setBusyId(id); setMsg(null);
    try {
      const res = await fetch(`/api/v1/users/me/ai-configs/${id}/duplicate`, { method: "POST", headers: authH() });
      if (!res.ok) { const d = await res.json().catch(() => ({})); setMsg({ ok: false, text: d.detail || "Erro ao duplicar" }); return; }
      await carregar();
    } catch { setMsg({ ok: false, text: "Falha de conexão." }); }
    finally { setBusyId(null); }
  }

  async function moverPrioridade(id: string, direcao: "up" | "down") {
    // Ordem de fallback = tudo que não é padrão, ativo, na ordem já retornada
    // pelo backend (Fase 137.3). Reordenar normaliza a prioridade de todo mundo
    // pra posição 1..N — funciona mesmo partindo de prioridades nulas/repetidas.
    const fila = configs.filter((c) => !c.is_default && c.enabled);
    const idx = fila.findIndex((c) => c.id === id);
    const alvo = direcao === "up" ? idx - 1 : idx + 1;
    if (idx === -1 || alvo < 0 || alvo >= fila.length) return;
    setBusyId(id); setMsg(null);
    try {
      const [a, b] = [fila[idx], fila[alvo]];
      await Promise.all([
        fetch(`/api/v1/users/me/ai-configs/${a.id}`, { method: "PATCH", headers: authH(), body: JSON.stringify({ priority: alvo + 1 }) }),
        fetch(`/api/v1/users/me/ai-configs/${b.id}`, { method: "PATCH", headers: authH(), body: JSON.stringify({ priority: idx + 1 }) }),
      ]);
      await carregar();
    } catch { setMsg({ ok: false, text: "Falha de conexão." }); }
    finally { setBusyId(null); }
  }

  async function remover(id: string) {
    if ((await ask({ message: "Remover esta IA? Essa ação não pode ser desfeita.", danger: true, confirmLabel: "Remover" })) === null) return;
    setBusyId(id); setMsg(null);
    try {
      const res = await fetch(`/api/v1/users/me/ai-configs/${id}`, { method: "DELETE", headers: authH() });
      if (!res.ok && res.status !== 204) { const d = await res.json().catch(() => ({})); setMsg({ ok: false, text: d.detail || "Erro ao remover" }); return; }
      await carregar();
    } catch { setMsg({ ok: false, text: "Falha de conexão." }); }
    finally { setBusyId(null); }
  }

  async function salvarOverrides() {
    const list = Object.entries(overrides)
      .filter(([, configId]) => configId)
      .map(([task_type, provider_config_id]) => ({ task_type, provider_config_id }));
    try {
      const res = await fetch("/api/v1/users/me/ai-settings/overrides", {
        method: "PUT", headers: authH(), body: JSON.stringify({ overrides: list }),
      });
      const d = await res.json().catch(() => ({}));
      if (!res.ok) { setMsg({ ok: false, text: d.detail || "Erro ao salvar ajustes por área" }); return; }
      setMsg({ ok: true, text: "Ajustes por área salvos." });
    } catch { setMsg({ ok: false, text: "Falha de conexão." }); }
  }

  async function salvarBalanceamento(novoModo: string) {
    const anterior = modoBalanceamento;
    setModoBalanceamento(novoModo); setSalvandoBalanceamento(true); setMsg(null);
    try {
      const res = await fetch("/api/v1/users/me/ai-settings/balance-mode", {
        method: "PUT", headers: authH(), body: JSON.stringify({ mode: novoModo }),
      });
      const d = await res.json().catch(() => ({}));
      if (!res.ok) { setModoBalanceamento(anterior); setMsg({ ok: false, text: d.detail || "Erro ao salvar modo de balanceamento" }); return; }
      setMsg({ ok: true, text: "Modo de balanceamento salvo." });
    } catch { setModoBalanceamento(anterior); setMsg({ ok: false, text: "Falha de conexão." }); }
    finally { setSalvandoBalanceamento(false); }
  }

  function alternarSelecaoComparar(id: string) {
    setCompararSelecionadas((sel) => (
      sel.includes(id) ? sel.filter((x) => x !== id) : sel.length < 5 ? [...sel, id] : sel
    ));
  }

  async function compararIAs() {
    if (!compararPrompt.trim() || compararSelecionadas.length < 2) return;
    setComparando(true); setMsg(null); setCompararResultados(null);
    try {
      const res = await fetch("/api/v1/users/me/ai-configs/compare", {
        method: "POST", headers: authH(),
        body: JSON.stringify({ prompt: compararPrompt.trim(), config_ids: compararSelecionadas }),
      });
      const d = await res.json().catch(() => ({}));
      if (!res.ok) { setMsg({ ok: false, text: d.detail || "Erro ao comparar" }); return; }
      setCompararResultados(d.results || []);
    } catch { setMsg({ ok: false, text: "Falha de conexão." }); }
    finally { setComparando(false); }
  }

  if (loading) return <div className="p-8 flex justify-center"><Loader2 className="animate-spin text-afj-gold" /></div>;

  return (
    <div className="max-w-3xl mx-auto p-6">
      <div className="afj-page-header">
        <div>
          <h1 className="afj-page-title flex items-center gap-2"><Bot size={20} className="text-afj-gold" /> Minhas IAs</h1>
          <p className="text-afj-black/45 text-sm mt-1">Cadastre uma ou mais IAs (grátis ou pagas) — os tokens saem da sua conta e o crédito do sistema é preservado.</p>
        </div>
        <button onClick={() => setModal({ mode: "add", config: null })} className="btn-afj-primary py-2.5 flex items-center gap-2">
          <Plus size={16} /> Adicionar IA
        </button>
      </div>

      {msg && (
        <div className={`flex items-start gap-2 text-xs rounded-sm px-3 py-2.5 mb-4 ${msg.ok ? "text-green-700 bg-green-50 border border-green-200" : "text-red-700 bg-red-50 border border-red-200"}`}>
          {msg.ok ? <CheckCircle2 size={14} className="flex-shrink-0 mt-0.5" /> : <XCircle size={14} className="flex-shrink-0 mt-0.5" />}
          <span className="leading-relaxed">{msg.text}</span>
        </div>
      )}

      {configs.length === 0 ? (
        <div className="afj-card p-8 text-center text-sm text-afj-black/45">
          <Sparkles size={22} className="text-afj-gold mx-auto mb-2" />
          Nenhuma IA cadastrada ainda. Clique em &quot;Adicionar IA&quot; para usar sua própria chave (Anthropic, OpenAI, Gemini, Grok, DeepSeek, OpenRouter ou um modelo local via Ollama).
        </div>
      ) : (
        <div className="space-y-3">
          {modoBalanceamento !== "padrao" && (
            <p className="text-[11px] text-amber-600 -mt-1 mb-1">
              Balanceamento automático está ativo — a ordem manual abaixo é ignorada nas chamadas reais
              (veja &quot;Balanceamento automático&quot; mais abaixo para mudar).
            </p>
          )}
          {configs.filter((c) => !c.is_default && c.enabled).length > 1 && (
            <p className="text-[11px] text-afj-black/40 -mt-1 mb-1">
              Se a IA padrão falhar, o sistema tenta automaticamente a próxima desta lista, na ordem abaixo.
            </p>
          )}
          {configs.map((c) => {
            const info = providers[c.provider];
            const fila = configs.filter((x) => !x.is_default && x.enabled);
            const posicao = fila.findIndex((x) => x.id === c.id);
            const mostrarOrdem = !c.is_default && c.enabled && fila.length > 1;
            return (
              <div key={c.id} className="afj-card p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-sm text-afj-black">{c.display_name}</span>
                      {c.is_default && (
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-afj-gold/15 text-afj-gold font-semibold flex items-center gap-1">
                          <Star size={10} fill="currentColor" /> Padrão
                        </span>
                      )}
                      {mostrarOrdem && (
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-afj-cream text-afj-black/50 font-medium flex items-center gap-1.5">
                          Fallback #{posicao + 1}
                          <span className="flex items-center gap-0.5">
                            <button type="button" onClick={() => moverPrioridade(c.id, "up")} disabled={busyId === c.id || posicao === 0}
                              className="hover:text-afj-gold disabled:opacity-30 disabled:hover:text-inherit" aria-label="Subir prioridade">
                              <ChevronUp size={11} />
                            </button>
                            <button type="button" onClick={() => moverPrioridade(c.id, "down")} disabled={busyId === c.id || posicao === fila.length - 1}
                              className="hover:text-afj-gold disabled:opacity-30 disabled:hover:text-inherit" aria-label="Descer prioridade">
                              <ChevronDown size={11} />
                            </button>
                          </span>
                        </span>
                      )}
                      <span className={`text-[10px] px-2 py-0.5 rounded-full ${c.status === "ERRO" ? "bg-red-50 text-red-600" : "bg-green-50 text-green-600"}`}>
                        {c.status === "ERRO" ? "Erro" : "Ativa"}
                      </span>
                      {!c.enabled && <span className="text-[10px] px-2 py-0.5 rounded-full bg-afj-cream text-afj-black/40">Desativada</span>}
                    </div>
                    <p className="text-xs text-afj-black/45 mt-1">
                      {info?.nome || c.provider} {c.model && `· ${c.model}`}
                    </p>
                    {stats[c.id] && stats[c.id].total_calls > 0 && (
                      <p className="text-[11px] text-afj-black/40 mt-1">
                        {stats[c.id].total_calls} chamada{stats[c.id].total_calls === 1 ? "" : "s"} ·{" "}
                        {Math.round(stats[c.id].success_rate * 100)}% sucesso ·{" "}
                        ${stats[c.id].total_cost_usd.toFixed(4)} · {Math.round(stats[c.id].avg_latency_ms)}ms méd.
                      </p>
                    )}
                    {c.last_error && <p className="text-[11px] text-red-500 mt-1">{c.last_error}</p>}
                  </div>
                </div>
                <div className="flex items-center gap-2 mt-3 flex-wrap">
                  <button onClick={() => testar(c.id)} disabled={testingId === c.id || (!c.has_credential && c.auth_method !== "none")}
                    className="btn-afj-outline text-xs px-3 py-1.5 flex items-center gap-1.5 disabled:opacity-40">
                    {testingId === c.id ? <Loader2 size={12} className="animate-spin" /> : <FlaskConical size={12} />} Testar
                  </button>
                  <button onClick={() => setModal({ mode: "edit", config: c })} className="btn-afj-outline text-xs px-3 py-1.5 flex items-center gap-1.5">
                    <Pencil size={12} /> Editar
                  </button>
                  <button onClick={() => duplicar(c.id)} disabled={busyId === c.id} className="btn-afj-outline text-xs px-3 py-1.5 flex items-center gap-1.5 disabled:opacity-40">
                    <Copy size={12} /> Duplicar
                  </button>
                  {!c.is_default && (
                    <button onClick={() => tornarPadrao(c.id)} disabled={busyId === c.id} className="btn-afj-outline text-xs px-3 py-1.5 flex items-center gap-1.5 disabled:opacity-40">
                      <Star size={12} /> Tornar padrão
                    </button>
                  )}
                  <button onClick={() => remover(c.id)} disabled={busyId === c.id} className="text-xs px-3 py-1.5 flex items-center gap-1.5 text-red-500 hover:bg-red-50 rounded-sm disabled:opacity-40">
                    <Trash2 size={12} /> Remover
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Ajuste por área: uma IA diferente por tipo de tarefa (opcional) */}
      <div className="afj-card mt-4 border border-afj-cream-dark rounded-sm overflow-hidden">
        <button type="button" onClick={() => setShowOverrides((v) => !v)}
          className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-afj-cream/40 transition-colors">
          <span className="flex items-center gap-2 text-sm text-afj-black/75">
            <SlidersHorizontal size={14} className="text-afj-gold" />
            Ajuste por área <span className="text-afj-black/35 text-xs">(opcional — uma IA diferente por tarefa)</span>
          </span>
          <ChevronDown size={15} className={`text-afj-black/30 transition-transform ${showOverrides ? "rotate-180" : ""}`} />
        </button>
        {showOverrides && (
          <div className="px-4 pb-4 pt-1 border-t border-afj-cream-dark space-y-2.5">
            <p className="text-[11px] text-afj-black/45 leading-relaxed">
              Use uma IA diferente em cada área (ex.: uma premium para petições, uma rápida/barata para relatórios).
              &quot;Usar IA padrão&quot; = sem ajuste, usa a IA marcada como padrão acima.
            </p>
            {TASK_LABELS.map(({ task, label }) => (
              <div key={task} className="flex items-center gap-3">
                <span className="text-xs text-afj-black/60 w-44 flex-shrink-0">{label}</span>
                <select
                  value={overrides[task] || ""}
                  onChange={(e) => setOverrides((o) => ({ ...o, [task]: e.target.value }))}
                  name={`afj-ai-override-${task}`}
                  className="flex-1 bg-afj-cream border border-afj-cream-dark rounded-sm px-3 py-1.5 text-xs focus:outline-none focus:border-afj-gold"
                >
                  <option value="">Usar IA padrão</option>
                  {configs.filter((c) => c.enabled).map((c) => (
                    <option key={c.id} value={c.id}>{c.display_name} ({providers[c.provider]?.nome || c.provider})</option>
                  ))}
                </select>
              </div>
            ))}
            <button onClick={salvarOverrides} className="btn-afj-primary text-xs py-1.5 mt-1">Salvar ajustes por área</button>
          </div>
        )}
      </div>

      {/* Balanceamento automático: escolhe sozinho qual IA tentar primeiro (opcional) */}
      <div className="afj-card mt-4 border border-afj-cream-dark rounded-sm overflow-hidden">
        <button type="button" onClick={() => setShowBalanceamento((v) => !v)}
          className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-afj-cream/40 transition-colors">
          <span className="flex items-center gap-2 text-sm text-afj-black/75">
            <Shuffle size={14} className="text-afj-gold" />
            Balanceamento automático <span className="text-afj-black/35 text-xs">(opcional — escolhe automaticamente qual IA usar primeiro)</span>
          </span>
          <ChevronDown size={15} className={`text-afj-black/30 transition-transform ${showBalanceamento ? "rotate-180" : ""}`} />
        </button>
        {showBalanceamento && (
          <div className="px-4 pb-4 pt-1 border-t border-afj-cream-dark space-y-2.5">
            <p className="text-[11px] text-afj-black/45 leading-relaxed">
              Por padrão, a IA marcada como padrão é sempre a primeira tentativa, seguida da fila de fallback
              manual acima. Ative um modo automático para variar isso a cada chamada.
            </p>
            {[
              { v: "padrao", t: "Padrão (manual)", d: "Mantém a ordem definida acima (IA padrão + fila de fallback)." },
              { v: "round_robin", t: "Revezamento", d: "Alterna qual IA tentar primeiro a cada chamada, distribuindo o uso entre todas as IAs ativas." },
              { v: "performance", t: "Performance", d: "Prioriza automaticamente a IA com melhor taxa de sucesso, menor custo e menor latência nos últimos 7 dias." },
            ].map((op) => (
              <label key={op.v} className={`flex items-start gap-2.5 px-3 py-2 rounded-sm border cursor-pointer ${modoBalanceamento === op.v ? "border-afj-gold bg-afj-gold/10" : "border-afj-cream-dark"}`}>
                <input type="radio" name="modo-balanceamento" checked={modoBalanceamento === op.v}
                  disabled={salvandoBalanceamento} onChange={() => salvarBalanceamento(op.v)} className="accent-afj-gold mt-0.5" />
                <span>
                  <span className="text-xs font-medium text-afj-black block">{op.t}</span>
                  <span className="text-[11px] text-afj-black/45">{op.d}</span>
                </span>
              </label>
            ))}
            {configs.filter((c) => c.enabled).length < 2 && (
              <p className="text-[11px] text-afj-black/35">Cadastre pelo menos 2 IAs ativas para o balanceamento automático ter efeito.</p>
            )}
          </div>
        )}
      </div>

      {/* Comparar IAs: mesma pergunta pra 2-5 IAs em paralelo, lado a lado (opcional) */}
      {configs.filter((c) => c.enabled).length > 1 && (
        <div className="afj-card mt-4 border border-afj-cream-dark rounded-sm overflow-hidden">
          <button type="button" onClick={() => setShowComparar((v) => !v)}
            className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-afj-cream/40 transition-colors">
            <span className="flex items-center gap-2 text-sm text-afj-black/75">
              <Scale size={14} className="text-afj-gold" />
              Comparar IAs <span className="text-afj-black/35 text-xs">(opcional — mesma pergunta pra várias IAs, lado a lado)</span>
            </span>
            <ChevronDown size={15} className={`text-afj-black/30 transition-transform ${showComparar ? "rotate-180" : ""}`} />
          </button>
          {showComparar && (
            <div className="px-4 pb-4 pt-1 border-t border-afj-cream-dark space-y-2.5">
              <p className="text-[11px] text-afj-black/45 leading-relaxed">
                Escolha de 2 a 5 IAs cadastradas e faça a mesma pergunta pra todas ao mesmo tempo — útil pra
                decidir qual IA usar em cada tipo de tarefa. Não salva nada, é só uma consulta.
              </p>
              <div className="flex flex-wrap gap-2">
                {configs.filter((c) => c.enabled).map((c) => (
                  <label key={c.id} className={`flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-sm border cursor-pointer ${compararSelecionadas.includes(c.id) ? "border-afj-gold bg-afj-gold/10 text-afj-black" : "border-afj-cream-dark text-afj-black/60"}`}>
                    <input type="checkbox" checked={compararSelecionadas.includes(c.id)}
                      onChange={() => alternarSelecaoComparar(c.id)} className="accent-afj-gold" />
                    {c.display_name}
                  </label>
                ))}
              </div>
              <textarea
                value={compararPrompt} onChange={(e) => setCompararPrompt(e.target.value)}
                placeholder="Digite a pergunta que será enviada a todas as IAs selecionadas..."
                rows={3} maxLength={4000}
                className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-3 py-2 text-xs placeholder:text-afj-black/25 focus:outline-none focus:border-afj-gold resize-y"
              />
              <button onClick={compararIAs} disabled={comparando || compararSelecionadas.length < 2 || !compararPrompt.trim()}
                className="btn-afj-primary text-xs py-1.5 mt-1 flex items-center gap-2 disabled:opacity-50">
                {comparando ? <Loader2 size={12} className="animate-spin" /> : <Scale size={12} />}
                Comparar ({compararSelecionadas.length}/5)
              </button>

              {compararResultados && (
                <div className="grid gap-3 mt-3" style={{ gridTemplateColumns: `repeat(${Math.min(compararResultados.length, 2)}, minmax(0, 1fr))` }}>
                  {compararResultados.map((r) => (
                    <div key={r.config_id} className="border border-afj-cream-dark rounded-sm p-3 bg-white">
                      <div className="flex items-center justify-between gap-2 mb-1.5">
                        <span className="text-xs font-medium text-afj-black">{r.display_name}</span>
                        {!r.error && <span className="text-[10px] text-afj-black/40">{r.latency_ms}ms · ${r.cost_usd.toFixed(4)}</span>}
                      </div>
                      {r.error ? (
                        <p className="text-[11px] text-red-500">{r.error}</p>
                      ) : (
                        <p className="text-xs text-afj-black/75 whitespace-pre-wrap leading-relaxed">{r.content}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {modal && (
        <AIConfigModal
          mode={modal.mode}
          config={modal.config}
          providers={providers}
          onClose={() => setModal(null)}
          onSaved={() => { setModal(null); carregar(); }}
          onError={(text) => setMsg({ ok: false, text })}
        />
      )}
      {confirmDialog}
    </div>
  );
}

function AIConfigModal({
  mode, config, providers, onClose, onSaved, onError,
}: {
  mode: "add" | "edit";
  config: AIConfig | null;
  providers: Record<string, ProviderInfo>;
  onClose: () => void;
  onSaved: () => void;
  onError: (text: string) => void;
}) {
  const providerKeys = Object.keys(providers);
  const [provider, setProvider] = useState(config?.provider || providerKeys[0] || "anthropic");
  const [displayName, setDisplayName] = useState(config?.display_name || "");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState(config?.model || "");
  const [baseUrl, setBaseUrl] = useState(config?.base_url || "");
  const [enabled, setEnabled] = useState(config?.enabled ?? true);
  const [showKey, setShowKey] = useState(false);
  const [saving, setSaving] = useState(false);

  const info = providers[provider];
  const credencialEJson = info?.auth_methods?.includes("service_account_json"); // Fase 195 — Vertex AI
  const precisaUrlPropria = info && !info.base_url && !info.requires_key; // hoje só ollama — vertex_ai também tem base_url nulo mas usa credencial, não URL própria
  const [conectandoOAuth, setConectandoOAuth] = useState(false);
  const podeOAuth = mode === "add" && info?.oauth_disponivel;

  async function conectarComLogin() {
    setConectandoOAuth(true);
    try {
      const res = await fetch(`/api/v1/me/ai-configs/oauth/${provider}/connect`, { headers: authH() });
      const d = await res.json().catch(() => ({}));
      if (res.ok && d.auth_url) window.location.href = d.auth_url;
      else onError(d.detail || "Login por conta não disponível no momento.");
    } catch { onError("Falha de conexão."); }
    finally { setConectandoOAuth(false); }
  }

  async function salvar() {
    setSaving(true);
    try {
      const body: Record<string, unknown> = mode === "add"
        ? { provider, display_name: displayName.trim() || undefined, model: model.trim() || undefined, base_url: baseUrl.trim() || undefined, enabled }
        : { display_name: displayName.trim() || undefined, model: model.trim() || undefined, base_url: baseUrl.trim() || undefined, enabled };
      if (apiKey.trim()) body.api_key = apiKey.trim();

      const url = mode === "add" ? "/api/v1/users/me/ai-configs" : `/api/v1/users/me/ai-configs/${config!.id}`;
      const method = mode === "add" ? "POST" : "PATCH";
      const res = await fetch(url, { method, headers: authH(), body: JSON.stringify(body) });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) { onError(data.detail || "Erro ao salvar"); return; }
      onSaved();
    } catch { onError("Falha de conexão."); }
    finally { setSaving(false); }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="afj-card w-full max-w-md p-6 space-y-4" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-afj-black">{mode === "add" ? "Adicionar IA" : "Editar IA"}</h2>
          <button onClick={onClose} className="text-afj-black/40 hover:text-afj-black/70"><X size={18} /></button>
        </div>

        {/* Campos-isca ocultos: absorvem o autofill do navegador */}
        <input type="text" name="username" autoComplete="username" tabIndex={-1} aria-hidden="true"
          style={{ position: "absolute", opacity: 0, height: 0, width: 0, pointerEvents: "none" }} />
        <input type="password" name="password" autoComplete="current-password" tabIndex={-1} aria-hidden="true"
          style={{ position: "absolute", opacity: 0, height: 0, width: 0, pointerEvents: "none" }} />

        {mode === "add" && (
          <div>
            <label className="text-[10px] font-semibold text-afj-black/55 uppercase tracking-widest block mb-1.5">Provedor</label>
            <select value={provider} onChange={(e) => { setProvider(e.target.value); setModel(""); }}
              className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-3 py-2.5 text-sm focus:outline-none focus:border-afj-gold">
              {providerKeys.map((k) => <option key={k} value={k}>{providers[k].nome}</option>)}
            </select>
          </div>
        )}

        <div>
          <label className="text-[10px] font-semibold text-afj-black/55 uppercase tracking-widest block mb-1.5">Nome de exibição (opcional)</label>
          <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder={info?.nome || "ex.: minha conta pessoal"}
            name="afj-ai-display-name" autoComplete="off" data-lpignore="true" data-1p-ignore
            className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-3 py-2.5 text-sm placeholder:text-afj-black/25 focus:outline-none focus:border-afj-gold" />
        </div>

        <div>
          <label className="text-[10px] font-semibold text-afj-black/55 uppercase tracking-widest block mb-1.5">Modelo (opcional)</label>
          <input value={model} onChange={(e) => setModel(e.target.value)} placeholder={info?.modelo_sugerido || ""}
            name="afj-ai-model" autoComplete="off" data-lpignore="true" data-1p-ignore data-form-type="other"
            className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-3 py-2.5 text-sm placeholder:text-afj-black/25 focus:outline-none focus:border-afj-gold" />
        </div>

        {podeOAuth && (
          <div>
            <button type="button" onClick={conectarComLogin} disabled={conectandoOAuth}
              className="btn-afj-primary w-full py-2.5 flex items-center justify-center gap-2 disabled:opacity-50">
              {conectandoOAuth ? <Loader2 size={14} className="animate-spin" /> : <KeyRound size={14} />}
              Conectar com login ({info?.nome})
            </button>
            <div className="flex items-center gap-2 my-3">
              <div className="flex-1 h-px bg-afj-cream-dark" />
              <span className="text-[10px] text-afj-black/35 uppercase tracking-widest">ou cole a chave manualmente</span>
              <div className="flex-1 h-px bg-afj-cream-dark" />
            </div>
          </div>
        )}

        {precisaUrlPropria ? (
          <div>
            <label className="text-[10px] font-semibold text-afj-black/55 uppercase tracking-widest block mb-1.5">URL do servidor</label>
            <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="http://localhost:11434/v1"
              name="afj-ai-base-url" autoComplete="off"
              className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-3 py-2.5 text-sm placeholder:text-afj-black/25 focus:outline-none focus:border-afj-gold" />
            <p className="text-[11px] text-afj-black/40 mt-1.5">Modelo local — sem autenticação, só a URL do seu servidor Ollama.</p>
          </div>
        ) : (
          <div>
            <label className="text-[10px] font-semibold text-afj-black/55 uppercase tracking-widest flex items-center gap-1.5 mb-1.5">
              <KeyRound size={12} /> {credencialEJson ? "Conta de serviço (JSON)" : "Chave de API"} {config?.has_credential && <span className="text-green-600 normal-case tracking-normal font-normal">· chave configurada</span>}
            </label>
            {credencialEJson ? (
              <textarea value={apiKey} onChange={(e) => setApiKey(e.target.value)}
                placeholder={config?.has_credential ? "(deixe em branco para manter) cole o JSON da conta de serviço aqui" : '{"type": "service_account", "project_id": "...", ...}'}
                name="afj-ai-secret" autoComplete="off" data-lpignore="true" data-1p-ignore data-form-type="other"
                spellCheck={false} rows={6}
                className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-3 py-2.5 text-xs font-mono placeholder:text-afj-black/25 focus:outline-none focus:border-afj-gold" />
            ) : (
              <div className="relative">
                <input type={showKey ? "text" : "password"} value={apiKey} onChange={(e) => setApiKey(e.target.value)}
                  placeholder={config?.has_credential ? "•••••••••• (deixe em branco para manter)" : "cole sua chave de API aqui"}
                  name="afj-ai-secret" autoComplete="new-password" data-lpignore="true" data-1p-ignore data-form-type="other"
                  spellCheck={false}
                  className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-3 py-2.5 pr-11 text-sm placeholder:text-afj-black/25 focus:outline-none focus:border-afj-gold" />
                <button type="button" onClick={() => setShowKey((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-afj-black/30 hover:text-afj-black/60"
                  aria-label={showKey ? "Ocultar chave" : "Mostrar chave"}>
                  {showKey ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            )}
            {info?.obter && <p className="text-[11px] text-afj-black/40 mt-1.5">Obtenha a chave em {info.obter}</p>}
          </div>
        )}

        {credencialEJson && (
          <div>
            <label className="text-[10px] font-semibold text-afj-black/55 uppercase tracking-widest block mb-1.5">Região do GCP (opcional)</label>
            <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="us-central1"
              name="afj-ai-region" autoComplete="off"
              className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-3 py-2.5 text-sm placeholder:text-afj-black/25 focus:outline-none focus:border-afj-gold" />
            <p className="text-[11px] text-afj-black/40 mt-1.5">Deixe em branco para usar us-central1.</p>
          </div>
        )}

        <label className="flex items-center gap-2.5 cursor-pointer">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} className="accent-afj-gold w-4 h-4" />
          <span className="text-sm text-afj-black/75">Ativa</span>
        </label>

        <div className="flex items-center gap-3 pt-1">
          <button onClick={salvar} disabled={saving} className="btn-afj-primary py-2.5 disabled:opacity-50 flex items-center gap-2">
            {saving && <Loader2 size={14} className="animate-spin" />} Salvar
          </button>
          <button onClick={onClose} className="btn-afj-outline py-2.5">Cancelar</button>
        </div>
      </div>
    </div>
  );
}
