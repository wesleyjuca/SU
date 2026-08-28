"use client";
import { useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell, AreaChart, Area,
} from "recharts";
import { TrendingUp, TrendingDown, DollarSign, BarChart2, Calculator } from "lucide-react";
import { AREAS_DIREITO } from "@/lib/constants";

const GOLD = "#B8954A";
const GOLD_LIGHT = "#D4AC64";
const NAVY = "#1E2229";
const RED_SOFT = "#DC2626";
const AREA_COLORS = [GOLD, GOLD_LIGHT, "#C09A5A", "#8A6D2A", NAVY, "#353D4A", "#4B5563", "#9CA3AF"];

const fmt = (v: number) => `R$ ${v.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`;
const fmtMes = (mes: string) => {
  try { return new Date(mes + "-15").toLocaleDateString("pt-BR", { month: "short", year: "2-digit" }); }
  catch { return mes; }
};

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-afj-cream-dark rounded-sm shadow-lg px-3 py-2 text-xs">
      <p className="font-semibold text-afj-black mb-1">{label}</p>
      {payload.map((p: any, i: number) => (
        <p key={i} style={{ color: p.color }}>{p.name}: {fmt(p.value)}</p>
      ))}
    </div>
  );
}

function EmptyState({ msg }: { msg: string }) {
  return <div className="h-40 flex items-center justify-center text-afj-black/30 text-sm">{msg}</div>;
}

export interface FinancialData {
  mensal: { mes: string; receitas: number; despesas: number; saldo: number }[];
  por_categoria: { categoria: string; tipo: string; total: number }[];
  summary: { receitas_pagas: number; receitas_pendentes: number; despesas_pagas: number; despesas_pendentes: number };
}

interface HonorariosHistorico {
  area_direito: string;
  n: number;
  media: number | null;
  mediana: number | null;
  minimo: number | null;
  maximo: number | null;
  amostra_pequena: boolean;
  mensagem: string | null;
}

// Fase 215 — comparação de um valor de honorários pretendido contra o que o
// escritório efetivamente recebeu historicamente na mesma área do direito.
// Puramente client-side: o valor pretendido nunca é enviado ao backend, só
// a média/mediana já devolvidas são usadas pra calcular a diferença aqui.
function SimulacaoHonorarios() {
  const [area, setArea] = useState("");
  const [tipoAcao, setTipoAcao] = useState("");
  const [desfecho, setDesfecho] = useState("");
  const [pretendido, setPretendido] = useState("");
  const [resultado, setResultado] = useState<HonorariosHistorico | null>(null);
  const [loading, setLoading] = useState(false);

  async function buscar(novaArea: string, novoTipoAcao: string, novoDesfecho: string) {
    if (!novaArea) { setResultado(null); return; }
    setLoading(true);
    const token = localStorage.getItem("afj_access_token");
    const params = new URLSearchParams({ area_direito: novaArea });
    if (novoTipoAcao) params.set("tipo_acao", novoTipoAcao);
    if (novoDesfecho) params.set("desfecho", novoDesfecho);
    const res = await fetch(`/api/v1/financial/honorarios-historico?${params}`, {
      headers: { Authorization: `Bearer ${token}` },
    }).then((r) => (r.ok ? r.json() : null)).catch(() => null);
    setResultado(res);
    setLoading(false);
  }

  const valorPretendido = parseFloat(pretendido.replace(",", "."));
  const temComparacao = resultado?.media != null && !isNaN(valorPretendido);
  const diferenca = temComparacao ? valorPretendido - (resultado!.media as number) : 0;
  const percentual = temComparacao && resultado!.media ? (diferenca / (resultado!.media as number)) * 100 : 0;

  return (
    <div className="afj-card p-5">
      <h3 className="font-semibold text-sm text-afj-black mb-1 flex items-center gap-2">
        <Calculator size={15} className="text-afj-gold" /> Simulação de honorários vs. histórico real
      </h3>
      <p className="text-[10px] text-afj-black/35 mb-3">
        Compare um valor de honorários pretendido com a média efetivamente recebida pelo escritório nesta área.
      </p>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 mb-4">
        <select
          value={area}
          onChange={(e) => { setArea(e.target.value); buscar(e.target.value, tipoAcao, desfecho); }}
          className="text-xs border border-afj-cream-dark rounded-sm px-2 py-1.5"
        >
          <option value="">Área do direito…</option>
          {AREAS_DIREITO.map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
        <input
          type="text" placeholder="Tipo de ação (opcional)" value={tipoAcao}
          onChange={(e) => { setTipoAcao(e.target.value); buscar(area, e.target.value, desfecho); }}
          className="text-xs border border-afj-cream-dark rounded-sm px-2 py-1.5"
        />
        <input
          type="text" placeholder="Desfecho (opcional)" value={desfecho}
          onChange={(e) => { setDesfecho(e.target.value); buscar(area, tipoAcao, e.target.value); }}
          className="text-xs border border-afj-cream-dark rounded-sm px-2 py-1.5"
        />
        <input
          type="text" placeholder="Valor pretendido (R$)" value={pretendido}
          onChange={(e) => setPretendido(e.target.value)}
          className="text-xs border border-afj-cream-dark rounded-sm px-2 py-1.5"
        />
      </div>

      {!area ? (
        <EmptyState msg="Escolha uma área do direito pra ver o histórico" />
      ) : loading ? (
        <EmptyState msg="Carregando…" />
      ) : !resultado || resultado.n === 0 ? (
        <EmptyState msg={resultado?.mensagem ?? "Sem histórico pra esta área"} />
      ) : (
        <div>
          {resultado.amostra_pequena && (
            <p className="text-[11px] text-afj-gold mb-2">{resultado.mensagem}</p>
          )}
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
            {[
              { label: "Registros", value: String(resultado.n) },
              { label: "Média", value: fmt(resultado.media as number) },
              { label: "Mediana", value: fmt(resultado.mediana as number) },
              { label: "Mínimo", value: fmt(resultado.minimo as number) },
              { label: "Máximo", value: fmt(resultado.maximo as number) },
            ].map(({ label, value }) => (
              <div key={label}>
                <p className="text-[10px] text-afj-black/40 uppercase">{label}</p>
                <p className="text-sm font-semibold text-afj-black">{value}</p>
              </div>
            ))}
          </div>
          {temComparacao && (
            <p className={`text-xs mt-3 font-medium ${diferenca >= 0 ? "text-green-600" : "text-red-500"}`}>
              Valor pretendido está {Math.abs(percentual).toFixed(0)}%{" "}
              {diferenca >= 0 ? "acima" : "abaixo"} da média histórica.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export default function FinanceiroCharts({ data }: { data: FinancialData }) {
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          { label: "Receitas Pagas", value: data.summary.receitas_pagas, icon: TrendingUp, color: "text-green-600" },
          { label: "A Receber", value: data.summary.receitas_pendentes, icon: DollarSign, color: "text-afj-gold" },
          { label: "Despesas Pagas", value: data.summary.despesas_pagas, icon: TrendingDown, color: "text-red-500" },
          {
            label: "Saldo (rec. - desp.)",
            value: data.summary.receitas_pagas - data.summary.despesas_pagas,
            icon: BarChart2,
            color: (data.summary.receitas_pagas - data.summary.despesas_pagas) >= 0 ? "text-green-600" : "text-red-500",
          },
        ].map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="afj-card p-4">
            <div className="flex items-center gap-2 mb-2">
              <Icon size={15} className={color} />
              <span className="text-xs text-afj-black/50">{label}</span>
            </div>
            <p className={`text-lg font-bold font-display ${color}`}>{fmt(value)}</p>
          </div>
        ))}
      </div>

      <div className="afj-card p-5">
        <h3 className="font-semibold text-sm text-afj-black mb-4">Receitas vs Despesas por Mês</h3>
        {data.mensal.length > 0 ? (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={data.mensal.map(d => ({ ...d, mes: fmtMes(d.mes) }))} barGap={4}>
              <CartesianGrid strokeDasharray="3 3" stroke="#EAE5D8" vertical={false} />
              <XAxis dataKey="mes" tick={{ fontSize: 11, fill: "#6B6B6B" }} axisLine={false} tickLine={false} />
              <YAxis tickFormatter={(v) => `R$${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 11, fill: "#6B6B6B" }} axisLine={false} tickLine={false} width={55} />
              <Tooltip content={<CustomTooltip />} />
              <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="receitas" name="Receitas" fill={GOLD} radius={[2, 2, 0, 0]} />
              <Bar dataKey="despesas" name="Despesas" fill={RED_SOFT} radius={[2, 2, 0, 0]} opacity={0.75} />
            </BarChart>
          </ResponsiveContainer>
        ) : <EmptyState msg="Nenhum dado financeiro no período" />}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="afj-card p-5">
          <h3 className="font-semibold text-sm text-afj-black mb-4">Saldo Acumulado</h3>
          {data.mensal.length > 0 ? (
            <ResponsiveContainer width="100%" height={180}>
              <AreaChart data={data.mensal.map(d => ({ ...d, mes: fmtMes(d.mes) }))}>
                <defs>
                  <linearGradient id="saldoGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={GOLD} stopOpacity={0.2} />
                    <stop offset="95%" stopColor={GOLD} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#EAE5D8" vertical={false} />
                <XAxis dataKey="mes" tick={{ fontSize: 10, fill: "#6B6B6B" }} axisLine={false} tickLine={false} />
                <YAxis tickFormatter={(v) => `R$${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 10, fill: "#6B6B6B" }} axisLine={false} tickLine={false} width={50} />
                <Tooltip content={<CustomTooltip />} />
                <Area type="monotone" dataKey="saldo" name="Saldo" stroke={GOLD} fill="url(#saldoGrad)" strokeWidth={2} dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          ) : <EmptyState msg="Sem dados" />}
        </div>

        <div className="afj-card p-5">
          <h3 className="font-semibold text-sm text-afj-black mb-4">Por Categoria (pagos)</h3>
          {data.por_categoria.filter(c => c.tipo === "RECEITA").length > 0 ? (
            <ResponsiveContainer width="100%" height={180}>
              <PieChart>
                <Pie
                  data={data.por_categoria.filter(c => c.tipo === "RECEITA")}
                  dataKey="total" nameKey="categoria"
                  cx="50%" cy="50%" innerRadius={45} outerRadius={75} paddingAngle={2}
                >
                  {data.por_categoria.filter(c => c.tipo === "RECEITA").map((_, i) => (
                    <Cell key={i} fill={AREA_COLORS[i % AREA_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(v: number) => fmt(v)} />
                <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 10 }} />
              </PieChart>
            </ResponsiveContainer>
          ) : <EmptyState msg="Sem receitas pagas por categoria" />}
        </div>
      </div>

      <SimulacaoHonorarios />
    </div>
  );
}
