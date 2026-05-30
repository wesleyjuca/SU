"use client";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

interface FinanceiroMes {
  mes: string;
  receitas: number;
  despesas: number;
}

export default function MiniFinancialChart({ data }: { data: FinanceiroMes[] }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} barCategoryGap="30%">
        <XAxis
          dataKey="mes"
          tickFormatter={(v) => {
            try { return new Date(v + "-01").toLocaleDateString("pt-BR", { month: "short" }); }
            catch { return v; }
          }}
          tick={{ fontSize: 11, fill: "#6B7280" }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis hide />
        <Tooltip
          formatter={(v: number, name: string) => [
            `R$ ${v.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`,
            name === "receitas" ? "Receitas" : "Despesas",
          ]}
          contentStyle={{ fontSize: 12, borderRadius: 4, border: "1px solid #EAE5D8" }}
        />
        <Bar dataKey="receitas" fill="#B8954A" radius={[3, 3, 0, 0]} />
        <Bar dataKey="despesas" fill="#DC2626" radius={[3, 3, 0, 0]} opacity={0.7} />
      </BarChart>
    </ResponsiveContainer>
  );
}
