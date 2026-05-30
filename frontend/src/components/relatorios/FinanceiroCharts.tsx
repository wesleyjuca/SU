"use client";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell, AreaChart, Area,
} from "recharts";
import { TrendingUp, TrendingDown, DollarSign, BarChart2 } from "lucide-react";

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
    </div>
  );
}
