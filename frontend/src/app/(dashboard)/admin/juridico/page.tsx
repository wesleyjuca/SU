"use client";
import { useState, useEffect } from "react";
import { Gavel, Plus, X, Save, Loader2, CalendarClock, BadgeCheck, DownloadCloud, EyeOff } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { useToast } from "@/components/ui/Toast";

interface Feriado { data: string; descricao: string | null }
interface Oab { numero: string; uf: string; nome: string | null }

const UFS = ["AC","AL","AM","AP","BA","CE","DF","ES","GO","MA","MG","MS","MT","PA","PB","PE","PI","PR","RJ","RN","RO","RR","RS","SC","SE","SP","TO"];

function authH(): HeadersInit {
  const t = typeof window !== "undefined" ? localStorage.getItem("afj_access_token") : null;
  return { "Content-Type": "application/json", Authorization: `Bearer ${t}` };
}

export default function JuridicoPage() {
  const toast = useToast();
  const [feriados, setFeriados] = useState<Feriado[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [novo, setNovo] = useState({ data: "", descricao: "" });
  const [oabs, setOabs] = useState<Oab[]>([]);
  const [loadingOabs, setLoadingOabs] = useState(true);
  const [savingOabs, setSavingOabs] = useState(false);
  const [capturando, setCapturando] = useState(false);
  const [novaOab, setNovaOab] = useState({ numero: "", uf: "SP", nome: "" });
  const [confidencial, setConfidencial] = useState(false);
  const [savingConf, setSavingConf] = useState(false);

  useEffect(() => { fetchFeriados(); fetchOabs(); fetchConfidencial(); }, []);

  async function fetchConfidencial() {
    try {
      const res = await fetch("/api/v1/tenant/confidencial", { headers: authH() });
      if (res.ok) { const d = await res.json(); setConfidencial(!!d.modo_confidencial); }
    } catch { /* opcional */ }
  }

  async function toggleConfidencial() {
    const novo = !confidencial;
    setSavingConf(true);
    try {
      const res = await fetch("/api/v1/tenant/confidencial", {
        method: "PUT", headers: authH(),
        body: JSON.stringify({ modo_confidencial: novo }),
      });
      if (res.ok) { setConfidencial(novo); toast.success(novo ? "Modo confidencial ativado." : "Modo confidencial desativado."); }
      else { const d = await res.json(); toast.error(d.detail || "Erro ao salvar."); }
    } catch { toast.error("Falha de conexão."); }
    finally { setSavingConf(false); }
  }

  async function fetchOabs() {
    setLoadingOabs(true);
    try {
      const res = await fetch("/api/v1/tenant/oabs", { headers: authH() });
      if (res.ok) { const d = await res.json(); setOabs(d.oabs || []); }
    } catch { toast.error("Falha ao carregar OABs."); }
    finally { setLoadingOabs(false); }
  }

  function adicionarOab() {
    const numero = novaOab.numero.replace(/\D/g, "");
    if (!numero) { toast.error("Informe o número da OAB."); return; }
    if (oabs.some((o) => o.numero === numero && o.uf === novaOab.uf)) { toast.error("OAB já cadastrada."); return; }
    setOabs([...oabs, { numero, uf: novaOab.uf, nome: novaOab.nome.trim() || null }]);
    setNovaOab({ numero: "", uf: novaOab.uf, nome: "" });
  }

  async function salvarOabs() {
    setSavingOabs(true);
    try {
      const res = await fetch("/api/v1/tenant/oabs", {
        method: "PUT", headers: authH(),
        body: JSON.stringify({ oabs }),
      });
      if (res.ok) toast.success("OABs monitoradas salvas.");
      else { const d = await res.json(); toast.error(d.detail || "Erro ao salvar."); }
    } catch { toast.error("Falha de conexão."); }
    finally { setSavingOabs(false); }
  }

  async function capturarProcessos() {
    setCapturando(true);
    try {
      const res = await fetch("/api/v1/tenant/oabs/capturar", { method: "POST", headers: authH() });
      const d = await res.json().catch(() => ({}));
      if (res.ok) toast.success(d.message || "Captura iniciada.");
      else toast.error(d.detail || "Erro ao iniciar captura.");
    } catch { toast.error("Falha de conexão."); }
    finally { setCapturando(false); }
  }

  async function fetchFeriados() {
    setLoading(true);
    try {
      const res = await fetch("/api/v1/tenant/feriados", { headers: authH() });
      if (res.ok) { const d = await res.json(); setFeriados(d.feriados || []); }
    } catch { toast.error("Falha ao carregar feriados."); }
    finally { setLoading(false); }
  }

  function adicionar() {
    if (!novo.data) { toast.error("Informe a data."); return; }
    if (feriados.some((f) => f.data === novo.data)) { toast.error("Data já cadastrada."); return; }
    setFeriados([...feriados, { data: novo.data, descricao: novo.descricao.trim() || null }].sort((a, b) => a.data.localeCompare(b.data)));
    setNovo({ data: "", descricao: "" });
  }

  function remover(data: string) {
    setFeriados(feriados.filter((f) => f.data !== data));
  }

  async function salvar() {
    setSaving(true);
    try {
      const res = await fetch("/api/v1/tenant/feriados", {
        method: "PUT", headers: authH(),
        body: JSON.stringify({ feriados: feriados.map((f) => ({ data: f.data, descricao: f.descricao })) }),
      });
      if (res.ok) toast.success("Feriados forenses salvos.");
      else { const d = await res.json(); toast.error(d.detail || "Erro ao salvar."); }
    } catch { toast.error("Falha de conexão."); }
    finally { setSaving(false); }
  }

  return (
    <div className="max-w-3xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Admin" }, { label: "Config. Jurídica" }]} />
      <div className="afj-page-header">
        <div>
          <h1 className="font-display text-2xl font-semibold text-afj-black flex items-center gap-2">
            <Gavel size={22} className="text-afj-gold" /> Configuração Jurídica
          </h1>
          <p className="text-afj-black/50 text-sm mt-0.5">Parâmetros que afetam o cálculo de prazos do escritório.</p>
        </div>
      </div>

      <div className="afj-card p-5">
        <div className="flex items-center gap-2 mb-1">
          <CalendarClock size={16} className="text-afj-gold" />
          <h2 className="font-semibold text-afj-black">Feriados forenses locais</h2>
        </div>
        <p className="text-xs text-afj-black/50 mb-4">
          Complementam os feriados nacionais e o recesso forense (20/12–20/01) no cálculo automático de prazos.
          Cadastre aqui os feriados da(s) comarca(s) onde o escritório atua (ex.: aniversário da cidade, feriados estaduais).
        </p>

        {/* Adicionar */}
        <div className="flex gap-2 items-end mb-4">
          <div>
            <label className="text-[11px] text-afj-black/50 block mb-0.5">Data</label>
            <input type="date" value={novo.data} onChange={(e) => setNovo({ ...novo, data: e.target.value })}
              className="border border-afj-cream-dark rounded-sm px-2 py-1.5 text-sm" />
          </div>
          <div className="flex-1">
            <label className="text-[11px] text-afj-black/50 block mb-0.5">Descrição (opcional)</label>
            <input value={novo.descricao} onChange={(e) => setNovo({ ...novo, descricao: e.target.value })}
              placeholder="Ex.: Aniversário de Rio Branco" className="w-full border border-afj-cream-dark rounded-sm px-3 py-1.5 text-sm" />
          </div>
          <button onClick={adicionar} className="btn-afj-outline rounded-sm py-1.5 px-3 text-sm flex items-center gap-1.5"><Plus size={14} /> Adicionar</button>
        </div>

        {/* Lista */}
        {loading ? (
          <div className="space-y-2">{Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-9 bg-afj-cream-dark rounded animate-pulse" />)}</div>
        ) : feriados.length === 0 ? (
          <p className="text-sm text-afj-black/40 text-center py-4">Nenhum feriado local cadastrado — o cálculo usa nacionais + recesso.</p>
        ) : (
          <div className="divide-y divide-afj-cream-dark border border-afj-cream-dark rounded-sm">
            {feriados.map((f) => (
              <div key={f.data} className="flex items-center justify-between px-3 py-2">
                <div>
                  <span className="text-sm font-medium text-afj-black">{new Date(f.data + "T00:00:00").toLocaleDateString("pt-BR")}</span>
                  {f.descricao && <span className="text-xs text-afj-black/50 ml-2">{f.descricao}</span>}
                </div>
                <button onClick={() => remover(f.data)} className="text-red-400 hover:text-red-600 p-1"><X size={16} /></button>
              </div>
            ))}
          </div>
        )}

        <button onClick={salvar} disabled={saving} className="btn-afj-primary rounded-sm py-2 px-4 text-sm mt-4 flex items-center gap-2 disabled:opacity-50">
          {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Salvar feriados
        </button>
      </div>

      {/* OABs monitoradas */}
      <div className="afj-card p-5">
        <div className="flex items-center gap-2 mb-1">
          <BadgeCheck size={16} className="text-afj-gold" />
          <h2 className="font-semibold text-afj-black">OABs monitoradas (sócios)</h2>
        </div>
        <p className="text-xs text-afj-black/50 mb-4">
          Além das OABs dos usuários com login, cadastre aqui as OABs dos sócios do escritório — mesmo sem acesso ao sistema, elas entram
          na varredura diária do DJe (intimações) e na captura de processos em massa.
        </p>

        <div className="flex gap-2 items-end mb-4 flex-wrap">
          <div>
            <label className="text-[11px] text-afj-black/50 block mb-0.5">Número</label>
            <input value={novaOab.numero} onChange={(e) => setNovaOab({ ...novaOab, numero: e.target.value })}
              placeholder="123456" className="w-28 border border-afj-cream-dark rounded-sm px-2 py-1.5 text-sm" />
          </div>
          <div>
            <label className="text-[11px] text-afj-black/50 block mb-0.5">UF</label>
            <select value={novaOab.uf} onChange={(e) => setNovaOab({ ...novaOab, uf: e.target.value })}
              className="border border-afj-cream-dark rounded-sm px-2 py-1.5 text-sm bg-white">
              {UFS.map((u) => <option key={u} value={u}>{u}</option>)}
            </select>
          </div>
          <div className="flex-1 min-w-[140px]">
            <label className="text-[11px] text-afj-black/50 block mb-0.5">Nome do sócio (opcional)</label>
            <input value={novaOab.nome} onChange={(e) => setNovaOab({ ...novaOab, nome: e.target.value })}
              placeholder="Ex.: Dr. João de Almeida" className="w-full border border-afj-cream-dark rounded-sm px-3 py-1.5 text-sm" />
          </div>
          <button onClick={adicionarOab} className="btn-afj-outline rounded-sm py-1.5 px-3 text-sm flex items-center gap-1.5"><Plus size={14} /> Adicionar</button>
        </div>

        {loadingOabs ? (
          <div className="space-y-2">{Array.from({ length: 2 }).map((_, i) => <div key={i} className="h-9 bg-afj-cream-dark rounded animate-pulse" />)}</div>
        ) : oabs.length === 0 ? (
          <p className="text-sm text-afj-black/40 text-center py-4">Nenhuma OAB cadastrada — a varredura usa só as OABs dos usuários com login.</p>
        ) : (
          <div className="divide-y divide-afj-cream-dark border border-afj-cream-dark rounded-sm">
            {oabs.map((o) => (
              <div key={`${o.numero}-${o.uf}`} className="flex items-center justify-between px-3 py-2">
                <div>
                  <span className="text-sm font-medium text-afj-black font-mono">{o.numero}/{o.uf}</span>
                  {o.nome && <span className="text-xs text-afj-black/50 ml-2">{o.nome}</span>}
                </div>
                <button onClick={() => setOabs(oabs.filter((x) => !(x.numero === o.numero && x.uf === o.uf)))} className="text-red-400 hover:text-red-600 p-1"><X size={16} /></button>
              </div>
            ))}
          </div>
        )}

        <div className="flex gap-2 mt-4 flex-wrap">
          <button onClick={salvarOabs} disabled={savingOabs} className="btn-afj-primary rounded-sm py-2 px-4 text-sm flex items-center gap-2 disabled:opacity-50">
            {savingOabs ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Salvar OABs
          </button>
          <button onClick={capturarProcessos} disabled={capturando || oabs.length === 0}
            title={oabs.length === 0 ? "Cadastre e salve as OABs primeiro" : "Busca processos nos tribunais para cada OAB salva"}
            className="btn-afj-outline rounded-sm py-2 px-4 text-sm flex items-center gap-2 disabled:opacity-50">
            {capturando ? <Loader2 size={14} className="animate-spin" /> : <DownloadCloud size={14} />} Capturar processos
          </button>
        </div>
      </div>

      {/* Modo confidencial */}
      <div className="afj-card p-5">
        <div className="flex items-center gap-2 mb-1">
          <EyeOff size={16} className="text-afj-gold" />
          <h2 className="font-semibold text-afj-black">Modo confidencial</h2>
        </div>
        <p className="text-xs text-afj-black/50 mb-4">
          Quando ligado, cada advogado vê apenas os processos em que é responsável ou faz parte da equipe — em Processos,
          Agenda, Publicações e ao abrir um processo. Sócios e gestão (ADMIN, SÓCIO, GESTOR) continuam com a visão total do escritório.
        </p>
        <div className="flex items-center justify-between border border-afj-cream-dark rounded-sm px-4 py-3">
          <div>
            <p className="text-sm font-medium text-afj-black">Restringir a visão dos advogados à sua equipe</p>
            <p className="text-xs text-afj-black/45 mt-0.5">{confidencial ? "Ativado — advogados veem só a própria carteira." : "Desativado — todos do escritório veem todos os processos."}</p>
          </div>
          <button
            onClick={toggleConfidencial}
            disabled={savingConf}
            role="switch"
            aria-checked={confidencial}
            aria-label="Alternar modo confidencial"
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors flex-shrink-0 disabled:opacity-50 ${confidencial ? "bg-afj-gold" : "bg-afj-cream-dark"}`}
          >
            <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${confidencial ? "translate-x-6" : "translate-x-1"}`} />
          </button>
        </div>
      </div>
    </div>
  );
}
