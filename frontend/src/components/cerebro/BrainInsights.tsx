"use client";
import { useState } from "react";
import { Sparkles, Wrench, AlertCircle, AlertTriangle, Rocket, Loader2, RefreshCw } from "lucide-react";
import { postBrain, type Insight } from "./types";

interface InsightsResp { ok: boolean; insights: Insight[]; custo_usd?: number; detail?: string }

const TIPO_CFG: Record<Insight["tipo"], { label: string; icon: React.ElementType; cor: string }> = {
  erro: { label: "Erro", icon: AlertCircle, cor: "#dc2626" },
  risco: { label: "Risco", icon: AlertTriangle, cor: "#d97706" },
  melhoria: { label: "Melhoria", icon: Wrench, cor: "#0EA5E9" },
  evolucao: { label: "Evolução", icon: Rocket, cor: "#7C3AED" },
};
const PRIORIDADE_CFG: Record<Insight["prioridade"], { label: string; cls: string }> = {
  alta: { label: "Alta", cls: "bg-red-100 text-red-700" },
  media: { label: "Média", cls: "bg-amber-100 text-amber-700" },
  baixa: { label: "Baixa", cls: "bg-gray-100 text-gray-600" },
};
const ORDEM_PRIORIDADE: Record<Insight["prioridade"], number> = { alta: 0, media: 1, baixa: 2 };

export function BrainInsights() {
  const [insights, setInsights] = useState<Insight[] | null>(null);
  const [custoUsd, setCustoUsd] = useState<number | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function analisar() {
    setCarregando(true);
    setErro(null);
    try {
      const r = await postBrain<InsightsResp>("insights");
      if (r?.ok) {
        setInsights(r.insights);
        setCustoUsd(typeof r.custo_usd === "number" ? r.custo_usd : null);
        if (r.insights.length === 0) setErro("Nenhum achado relevante no momento — sistema aparenta estar saudável.");
      } else {
        setInsights(null);
        setErro(r?.detail || "Não foi possível gerar os insights agora.");
      }
    } catch {
      setErro("Falha de conexão.");
    } finally {
      setCarregando(false);
    }
  }

  const ordenados = insights ? [...insights].sort((a, b) => ORDEM_PRIORIDADE[a.prioridade] - ORDEM_PRIORIDADE[b.prioridade]) : [];

  return (
    <div className="space-y-3">
      <div className="afj-card p-4">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <h2 className="font-semibold text-afj-black text-sm flex items-center gap-2">
              <Sparkles size={15} className="text-afj-gold" /> Insights proativos
            </h2>
            <p className="text-xs text-afj-black/50 mt-1">
              O Cérebro analisa o mapa do sistema, logs recentes, métricas por escritório e a saúde da
              infraestrutura, e propõe melhorias, riscos e próximos passos — só com base no que observa.
            </p>
          </div>
          <button onClick={analisar} disabled={carregando}
            className="btn-afj-primary rounded-sm flex items-center gap-1.5 text-xs disabled:opacity-50 flex-shrink-0">
            {carregando ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
            {insights ? "Analisar novamente" : "Analisar sistema"}
          </button>
        </div>
        {typeof custoUsd === "number" && (
          <p className="text-[11px] text-afj-black/35 mt-2">Custo desta análise: ${custoUsd.toFixed(4)}</p>
        )}
      </div>

      {erro && (
        <div className="afj-card p-4 text-sm text-afj-black/60 text-center">{erro}</div>
      )}

      {insights === null && !erro && !carregando && (
        <div className="afj-card p-8 text-center">
          <Sparkles size={28} className="mx-auto mb-2 text-afj-gold/40" />
          <p className="text-sm text-afj-black/50">Clique em &quot;Analisar sistema&quot; para o Cérebro diagnosticar a plataforma agora.</p>
        </div>
      )}

      {ordenados.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {ordenados.map((ins, i) => {
            const tipoCfg = TIPO_CFG[ins.tipo] ?? TIPO_CFG.melhoria;
            const Icon = tipoCfg.icon;
            const prioCfg = PRIORIDADE_CFG[ins.prioridade] ?? PRIORIDADE_CFG.media;
            return (
              <div key={i} className="afj-card p-4 border-l-4" style={{ borderLeftColor: tipoCfg.cor }}>
                <div className="flex items-start justify-between gap-2 mb-1.5">
                  <span className="text-[10px] font-semibold uppercase tracking-wider flex items-center gap-1" style={{ color: tipoCfg.cor }}>
                    <Icon size={11} /> {tipoCfg.label} · {ins.area}
                  </span>
                  <span className={`text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded-full flex-shrink-0 ${prioCfg.cls}`}>
                    {prioCfg.label}
                  </span>
                </div>
                <h3 className="font-semibold text-afj-black text-sm mb-1">{ins.titulo}</h3>
                <p className="text-xs text-afj-black/60 leading-relaxed">{ins.descricao}</p>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
