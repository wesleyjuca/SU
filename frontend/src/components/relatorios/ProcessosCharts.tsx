"use client";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, AreaChart, Area, Legend,
} from "recharts";
import { Scale } from "lucide-react";

const GOLD = "#B8954A";
const NAVY = "#1E2229";
const GREEN = "#16A34A";
const AMBER = "#D97706";
const MUTED = "#9CA3AF";
const SITUACAO_COLORS: Record<string, string> = {
  ATIVO: GREEN, SUSPENSO: AMBER, ARQUIVADO: MUTED, ENCERRADO: NAVY,
};

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
        <p key={i} style={{ color: p.color }}>{p.name}: {p.value.toLocaleString("pt-BR")}</p>
      ))}
    </div>
  );
}

function EmptyState({ msg }: { msg: string }) {
  return <div className="h-40 flex items-center justify-center text-afj-black/30 text-sm">{msg}</div>;
}

export interface ProcessoData {
  por_situacao: { situacao: string; count: number }[];
  por_area: { area: string; count: number }[];
  criados_por_mes: { mes: string; count: number }[];
  total: number;
}

export default function ProcessosCharts({ data }: { data: ProcessoData }) {
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="afj-card p-4">
          <div className="flex items-center gap-2 mb-1"><Scale size={15} className="text-afj-gold" /><span className="text-xs text-afj-black/50">Total de Processos</span></div>
          <p className="text-2xl font-bold font-display text-afj-black">{data.total}</p>
        </div>
        <div className="afj-card p-4">
          <div className="flex items-center gap-2 mb-1"><Scale size={15} className="text-green-600" /><span className="text-xs text-afj-black/50">Ativos</span></div>
          <p className="text-2xl font-bold font-display text-green-600">
            {data.por_situacao.find(s => s.situacao === "ATIVO")?.count ?? 0}
          </p>
        </div>
        <div className="afj-card p-4">
          <div className="flex items-center gap-2 mb-1"><Scale size={15} className="text-afj-black/40" /><span className="text-xs text-afj-black/50">Áreas distintas</span></div>
          <p className="text-2xl font-bold font-display text-afj-black">{data.por_area.length}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="afj-card p-5">
          <h3 className="font-semibold text-sm text-afj-black mb-4">Distribuição por Situação</h3>
          {data.por_situacao.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie
                  data={data.por_situacao} dataKey="count" nameKey="situacao"
                  cx="50%" cy="50%" innerRadius={50} outerRadius={80} paddingAngle={3}
                >
                  {data.por_situacao.map((entry, i) => (
                    <Cell key={i} fill={SITUACAO_COLORS[entry.situacao] ?? MUTED} />
                  ))}
                </Pie>
                <Tooltip formatter={(v: number) => [v, "processos"]} />
                <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11 }} />
              </PieChart>
            </ResponsiveContainer>
          ) : <EmptyState msg="Nenhum processo cadastrado" />}
        </div>

        <div className="afj-card p-5">
          <h3 className="font-semibold text-sm text-afj-black mb-4">Por Área do Direito</h3>
          {data.por_area.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={data.por_area} layout="vertical" margin={{ left: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#EAE5D8" horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 10, fill: "#6B6B6B" }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="area" width={110} tick={{ fontSize: 10, fill: "#6B6B6B" }} axisLine={false} tickLine={false} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="count" name="Processos" fill={GOLD} radius={[0, 2, 2, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : <EmptyState msg="Sem classificação por área" />}
        </div>
      </div>

      <div className="afj-card p-5">
        <h3 className="font-semibold text-sm text-afj-black mb-4">Processos Criados por Mês (últimos 6 meses)</h3>
        {data.criados_por_mes.length > 0 ? (
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={data.criados_por_mes.map(d => ({ ...d, mes: fmtMes(d.mes) }))}>
              <defs>
                <linearGradient id="procGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={NAVY} stopOpacity={0.15} />
                  <stop offset="95%" stopColor={NAVY} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#EAE5D8" vertical={false} />
              <XAxis dataKey="mes" tick={{ fontSize: 11, fill: "#6B6B6B" }} axisLine={false} tickLine={false} />
              <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "#6B6B6B" }} axisLine={false} tickLine={false} />
              <Tooltip content={<CustomTooltip />} />
              <Area type="monotone" dataKey="count" name="Processos" stroke={NAVY} fill="url(#procGrad)" strokeWidth={2} dot={{ fill: NAVY, r: 3 }} />
            </AreaChart>
          </ResponsiveContainer>
        ) : <EmptyState msg="Sem dados de criação no período" />}
      </div>
    </div>
  );
}
