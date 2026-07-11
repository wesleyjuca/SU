"use client";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";

const GOLD = "#B8954A";
const RED_SOFT = "#DC2626";
const NAVY = "#1E2229";

const fmtBRL = (v: number) => `R$ ${v.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`;
const fmtMes = (mes: string) => {
  try { return new Date(mes.slice(0, 7) + "-15").toLocaleDateString("pt-BR", { month: "short", year: "2-digit" }); }
  catch { return mes; }
};

function MoneyTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-afj-cream-dark rounded-sm shadow-lg px-3 py-2 text-xs">
      <p className="font-semibold text-afj-black mb-1">{label}</p>
      {payload.map((p: any, i: number) => (
        <p key={i} style={{ color: p.color }}>{p.name}: {fmtBRL(p.value)}</p>
      ))}
    </div>
  );
}

function EmptyState({ msg }: { msg: string }) {
  return <div className="h-40 flex items-center justify-center text-afj-black/30 text-sm">{msg}</div>;
}

export interface ConsolidadoLinha {
  unidade: string;
  receita_mes: number;
  despesa_mes: number;
  processos_ativos: number;
}
export interface ConsolidadoSerie { mes: string; receita: number; despesa: number }

export default function ConsolidadoCharts({ linhas, series }: {
  linhas: ConsolidadoLinha[];
  series: ConsolidadoSerie[];
}) {
  const porUnidade = linhas.map((l) => ({ ...l, unidade: l.unidade.length > 18 ? l.unidade.slice(0, 17) + "…" : l.unidade }));
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
      {/* Receita × Despesa por unidade */}
      <div className="afj-card p-5">
        <h3 className="font-semibold text-sm text-afj-black mb-4">Receita × Despesa por unidade (mês)</h3>
        {porUnidade.length > 0 ? (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={porUnidade} barGap={4}>
              <CartesianGrid strokeDasharray="3 3" stroke="#EAE5D8" vertical={false} />
              <XAxis dataKey="unidade" tick={{ fontSize: 10, fill: "#6B6B6B" }} axisLine={false} tickLine={false} interval={0} angle={-15} textAnchor="end" height={50} />
              <YAxis tickFormatter={(v) => `R$${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 11, fill: "#6B6B6B" }} axisLine={false} tickLine={false} width={55} />
              <Tooltip content={<MoneyTooltip />} />
              <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="receita_mes" name="Receita" fill={GOLD} radius={[2, 2, 0, 0]} />
              <Bar dataKey="despesa_mes" name="Despesa" fill={RED_SOFT} radius={[2, 2, 0, 0]} opacity={0.75} />
            </BarChart>
          </ResponsiveContainer>
        ) : <EmptyState msg="Sem dados financeiros no mês" />}
      </div>

      {/* Processos ativos por unidade */}
      <div className="afj-card p-5">
        <h3 className="font-semibold text-sm text-afj-black mb-4">Processos ativos por unidade</h3>
        {porUnidade.length > 0 ? (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={porUnidade}>
              <CartesianGrid strokeDasharray="3 3" stroke="#EAE5D8" vertical={false} />
              <XAxis dataKey="unidade" tick={{ fontSize: 10, fill: "#6B6B6B" }} axisLine={false} tickLine={false} interval={0} angle={-15} textAnchor="end" height={50} />
              <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "#6B6B6B" }} axisLine={false} tickLine={false} width={35} />
              <Tooltip />
              <Bar dataKey="processos_ativos" name="Ativos" fill={NAVY} radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : <EmptyState msg="Sem processos" />}
      </div>

      {/* Tendência mensal consolidada */}
      <div className="afj-card p-5 lg:col-span-2">
        <h3 className="font-semibold text-sm text-afj-black mb-4">Receita × Despesa consolidada (últimos meses)</h3>
        {series.length > 0 ? (
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={series.map((s) => ({ ...s, mes: fmtMes(s.mes) }))} barGap={4}>
              <CartesianGrid strokeDasharray="3 3" stroke="#EAE5D8" vertical={false} />
              <XAxis dataKey="mes" tick={{ fontSize: 11, fill: "#6B6B6B" }} axisLine={false} tickLine={false} />
              <YAxis tickFormatter={(v) => `R$${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 11, fill: "#6B6B6B" }} axisLine={false} tickLine={false} width={55} />
              <Tooltip content={<MoneyTooltip />} />
              <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="receita" name="Receita" fill={GOLD} radius={[2, 2, 0, 0]} />
              <Bar dataKey="despesa" name="Despesa" fill={RED_SOFT} radius={[2, 2, 0, 0]} opacity={0.75} />
            </BarChart>
          </ResponsiveContainer>
        ) : <EmptyState msg="Sem histórico financeiro no período" />}
      </div>
    </div>
  );
}
