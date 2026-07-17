"use client";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  PieChart, Pie, Cell,
} from "recharts";
import { Trophy, Users, Scale, Gauge } from "lucide-react";

const GOLD = "#B8954A";
const GREEN = "#16A34A";
const RED = "#DC2626";
const NAVY = "#1E2229";
const DESF_COLORS: Record<string, string> = { EXITO: GREEN, ACORDO: GOLD, PARCIAL: "#D4AC64", DERROTA: RED };

const fmtBRL = (v: number) => `R$ ${v.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`;

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

function Empty({ msg }: { msg: string }) {
  return <div className="h-40 flex items-center justify-center text-afj-black/30 text-sm">{msg}</div>;
}

export interface GestaoData {
  rentabilidade_clientes: { cliente: string; receita: number; despesa: number; resultado: number }[];
  rentabilidade_processos: { processo: string; resultado: number }[];
  produtividade_advogados: { advogado: string; processos: number; processos_ativos: number; prazos_pendentes: number; documentos: number; prazos_cumpridos: number }[];
  taxa_exito: {
    por_desfecho: Record<string, number>;
    total_com_desfecho: number;
    win_rate: number;
    por_area: { area: string; win_rate: number; total: number }[];
  };
}

export default function GestaoCharts({ data }: { data: GestaoData }) {
  const clientes = data.rentabilidade_clientes.map((c) => ({
    ...c, nome: c.cliente.length > 16 ? c.cliente.slice(0, 15) + "…" : c.cliente,
  }));
  const desfData = Object.entries(data.taxa_exito.por_desfecho).map(([k, v]) => ({ name: k, value: v }));
  // Distribuição de carga: só quem tem processos ativos ou prazos pendentes, mais carregado no topo
  const carga = data.produtividade_advogados
    .filter((a) => a.processos_ativos > 0 || a.prazos_pendentes > 0)
    .map((a) => ({
      nome: a.advogado.length > 18 ? a.advogado.slice(0, 17) + "…" : a.advogado,
      ativos: a.processos_ativos,
      prazos: a.prazos_pendentes,
    }))
    .sort((a, b) => b.ativos - a.ativos || b.prazos - a.prazos)
    .slice(0, 12);

  return (
    <div className="space-y-5">
      {/* Taxa de êxito — destaque */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="afj-card p-5 flex items-center gap-5">
          <div className="w-20 h-20 rounded-full flex items-center justify-center bg-afj-gold/10 flex-shrink-0">
            <Trophy size={30} className="text-afj-gold" />
          </div>
          <div>
            <p className="text-3xl font-bold text-afj-black font-display">{data.taxa_exito.win_rate}%</p>
            <p className="text-sm text-afj-black/60">Taxa de êxito (êxito + acordo)</p>
            <p className="text-xs text-afj-black/40 mt-0.5">{data.taxa_exito.total_com_desfecho} processos com desfecho registrado</p>
          </div>
        </div>
        <div className="afj-card p-5">
          <h3 className="font-semibold text-sm text-afj-black mb-3 flex items-center gap-2"><Scale size={15} className="text-afj-gold" /> Desfechos</h3>
          {desfData.length > 0 ? (
            <ResponsiveContainer width="100%" height={150}>
              <PieChart>
                <Pie data={desfData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={38} outerRadius={65} paddingAngle={2}>
                  {desfData.map((d, i) => <Cell key={i} fill={DESF_COLORS[d.name] || NAVY} />)}
                </Pie>
                <Tooltip />
                <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 10 }} />
              </PieChart>
            </ResponsiveContainer>
          ) : <Empty msg="Registre o desfecho ao arquivar processos" />}
        </div>
      </div>

      {/* Rentabilidade por cliente */}
      <div className="afj-card p-5">
        <h3 className="font-semibold text-sm text-afj-black mb-4">Rentabilidade por cliente (resultado, pagos)</h3>
        {clientes.length > 0 ? (
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={clientes} margin={{ bottom: 30 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#EAE5D8" vertical={false} />
              <XAxis dataKey="nome" tick={{ fontSize: 10, fill: "#6B6B6B" }} axisLine={false} tickLine={false} interval={0} angle={-20} textAnchor="end" height={40} />
              <YAxis tickFormatter={(v) => `R$${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 11, fill: "#6B6B6B" }} axisLine={false} tickLine={false} width={55} />
              <Tooltip content={<MoneyTooltip />} />
              <Bar dataKey="resultado" name="Resultado" radius={[2, 2, 0, 0]}>
                {clientes.map((c, i) => <Cell key={i} fill={c.resultado >= 0 ? GREEN : RED} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : <Empty msg="Sem lançamentos financeiros vinculados a clientes" />}
      </div>

      {/* Distribuição de carga por advogado (carga atual, para equilibrar/reatribuir) */}
      <div className="afj-card p-5">
        <div className="flex items-start justify-between gap-3 flex-wrap mb-4">
          <h3 className="font-semibold text-sm text-afj-black flex items-center gap-2"><Gauge size={15} className="text-afj-gold" /> Distribuição de carga (processos ativos + prazos pendentes)</h3>
          <p className="text-[10px] text-afj-black/35 max-w-xs text-right">Carga atual por advogado. Para reequilibrar, use “Transferir carteira” em Admin → Usuários.</p>
        </div>
        {carga.length > 0 ? (
          <ResponsiveContainer width="100%" height={Math.max(160, carga.length * 34)}>
            <BarChart data={carga} layout="vertical" margin={{ left: 10, right: 16 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#EAE5D8" horizontal={false} />
              <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11, fill: "#6B6B6B" }} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="nome" tick={{ fontSize: 11, fill: "#6B6B6B" }} axisLine={false} tickLine={false} width={110} />
              <Tooltip />
              <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="ativos" name="Processos ativos" fill={GOLD} radius={[0, 2, 2, 0]} />
              <Bar dataKey="prazos" name="Prazos pendentes" fill={NAVY} radius={[0, 2, 2, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : <Empty msg="Sem processos ativos ou prazos pendentes atribuídos" />}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Produtividade por advogado */}
        <div className="afj-card p-5">
          <h3 className="font-semibold text-sm text-afj-black mb-3 flex items-center gap-2"><Users size={15} className="text-afj-gold" /> Produtividade por advogado</h3>
          {data.produtividade_advogados.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="afj-table w-full">
                <thead><tr><th>Advogado</th><th className="text-right">Ativos</th><th className="text-right">Prazos pend.</th><th className="text-right">Documentos</th><th className="text-right">Prazos ✓</th></tr></thead>
                <tbody>
                  {data.produtividade_advogados.map((a) => (
                    <tr key={a.advogado}>
                      <td className="font-medium text-afj-black">{a.advogado}</td>
                      <td className="text-right text-afj-black/70">{a.processos_ativos}</td>
                      <td className="text-right text-afj-black/70">{a.prazos_pendentes}</td>
                      <td className="text-right text-afj-black/70">{a.documentos}</td>
                      <td className="text-right text-afj-black/70">{a.prazos_cumpridos}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="text-[10px] text-afj-black/35 mt-2">Ativos = processos ATIVO/SUSPENSO como responsável; prazos pendentes = ainda não cumpridos. Métricas proxy — não incluem horas trabalhadas.</p>
            </div>
          ) : <Empty msg="Sem dados de produtividade" />}
        </div>

        {/* Taxa de êxito por área */}
        <div className="afj-card p-5">
          <h3 className="font-semibold text-sm text-afj-black mb-4">Taxa de êxito por área</h3>
          {data.taxa_exito.por_area.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={data.taxa_exito.por_area} layout="vertical" margin={{ left: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#EAE5D8" horizontal={false} />
                <XAxis type="number" domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={{ fontSize: 11, fill: "#6B6B6B" }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="area" tick={{ fontSize: 11, fill: "#6B6B6B" }} axisLine={false} tickLine={false} width={90} />
                <Tooltip formatter={(v: number) => [`${v}%`, "Êxito"]} />
                <Bar dataKey="win_rate" name="Êxito" fill={GOLD} radius={[0, 2, 2, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : <Empty msg="Sem processos com desfecho por área" />}
        </div>
      </div>
    </div>
  );
}
