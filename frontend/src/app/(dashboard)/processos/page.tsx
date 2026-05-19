"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { Scale, Plus, AlertTriangle, Search, Filter } from "lucide-react";

interface Processo {
  id: string;
  numero_cnj: string | null;
  tribunal: string;
  vara: string | null;
  area_direito: string | null;
  situacao: string;
  valor_causa: number | null;
  proximo_prazo_at: string | null;
  monitoring_active: boolean;
  created_at: string;
}

const SITUACAO_STYLE: Record<string, string> = {
  ATIVO: "badge-ativo",
  SUSPENSO: "badge-pendente",
  ARQUIVADO: "badge-arquivado",
  ENCERRADO: "badge-arquivado",
};

const AREA_COLORS: Record<string, string> = {
  CIVIL: "bg-blue-100 text-blue-700",
  TRABALHISTA: "bg-purple-100 text-purple-700",
  TRIBUTARIO: "bg-orange-100 text-orange-700",
  PENAL: "bg-red-100 text-red-700",
  PREVIDENCIARIO: "bg-green-100 text-green-700",
  CONSUMIDOR: "bg-teal-100 text-teal-700",
};

function diasParaPrazo(prazo: string | null): { dias: number; classe: string } | null {
  if (!prazo) return null;
  const diff = Math.ceil((new Date(prazo).getTime() - Date.now()) / 86400000);
  if (diff < 0) return { dias: diff, classe: "text-red-600 font-bold" };
  if (diff <= 3) return { dias: diff, classe: "text-red-500 font-semibold" };
  if (diff <= 7) return { dias: diff, classe: "text-amber-600" };
  return { dias: diff, classe: "text-afj-black/50" };
}

export default function ProcessosPage() {
  const [processos, setProcessos] = useState<Processo[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filtroArea, setFiltroArea] = useState("");

  useEffect(() => {
    fetchProcessos();
  }, [filtroArea]);

  async function fetchProcessos() {
    setLoading(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const params = new URLSearchParams();
      if (filtroArea) params.set("area_direito", filtroArea);
      const res = await fetch(`/api/v1/processes?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setProcessos(await res.json());
    } finally {
      setLoading(false);
    }
  }

  const filtrados = processos.filter((p) =>
    !search || p.numero_cnj?.includes(search) || p.tribunal.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-semibold text-afj-black">Processos</h1>
          <p className="text-afj-black/50 text-sm">{filtrados.length} processo(s) encontrado(s)</p>
        </div>
        <Link href="/processos/novo" className="btn-afj-primary rounded-md flex items-center gap-2">
          <Plus size={15} />
          Novo Processo
        </Link>
      </div>

      {/* Filtros */}
      <div className="flex gap-3 flex-wrap">
        <div className="relative flex-1 min-w-48">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-afj-black/30" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por número CNJ ou tribunal..."
            className="w-full pl-9 pr-4 py-2 text-sm border border-afj-cream-dark rounded-md focus:outline-none focus:border-afj-gold bg-white"
          />
        </div>
        <select
          value={filtroArea}
          onChange={(e) => setFiltroArea(e.target.value)}
          className="border border-afj-cream-dark rounded-md px-3 py-2 text-sm text-afj-black bg-white focus:outline-none focus:border-afj-gold"
        >
          <option value="">Todas as áreas</option>
          {["CIVIL", "TRABALHISTA", "TRIBUTARIO", "PENAL", "PREVIDENCIARIO", "CONSUMIDOR"].map((a) => (
            <option key={a} value={a}>{a}</option>
          ))}
        </select>
      </div>

      {/* Tabela */}
      {loading ? (
        <div className="afj-card p-8 text-center text-afj-black/40">Carregando processos...</div>
      ) : filtrados.length === 0 ? (
        <div className="afj-card p-12 text-center">
          <Scale className="mx-auto text-afj-black/20 mb-3" size={40} />
          <p className="font-semibold text-afj-black">Nenhum processo cadastrado</p>
          <p className="text-afj-black/40 text-sm mt-1">Adicione o primeiro processo para iniciar o monitoramento</p>
          <Link href="/processos/novo" className="btn-afj-primary rounded-md inline-flex items-center gap-2 mt-4 text-sm">
            <Plus size={14} />
            Adicionar Processo
          </Link>
        </div>
      ) : (
        <div className="afj-card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-afj-cream-dark bg-afj-cream/50">
                <th className="text-left px-4 py-3 text-afj-black/50 font-medium">Número CNJ</th>
                <th className="text-left px-4 py-3 text-afj-black/50 font-medium">Tribunal</th>
                <th className="text-left px-4 py-3 text-afj-black/50 font-medium">Área</th>
                <th className="text-left px-4 py-3 text-afj-black/50 font-medium">Situação</th>
                <th className="text-left px-4 py-3 text-afj-black/50 font-medium">Próximo Prazo</th>
                <th className="text-left px-4 py-3 text-afj-black/50 font-medium">Valor da Causa</th>
              </tr>
            </thead>
            <tbody>
              {filtrados.map((p) => {
                const prazo = diasParaPrazo(p.proximo_prazo_at);
                return (
                  <tr key={p.id} className="border-b border-afj-cream-dark hover:bg-afj-cream/30 transition-colors">
                    <td className="px-4 py-3">
                      <Link href={`/processos/${p.id}`} className="text-afj-gold hover:underline font-mono text-xs">
                        {p.numero_cnj || "Sem CNJ"}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-afj-black/80">{p.tribunal}</td>
                    <td className="px-4 py-3">
                      {p.area_direito && (
                        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${AREA_COLORS[p.area_direito] ?? "bg-gray-100 text-gray-700"}`}>
                          {p.area_direito}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className={SITUACAO_STYLE[p.situacao] ?? "badge-arquivado"}>{p.situacao}</span>
                    </td>
                    <td className="px-4 py-3">
                      {prazo ? (
                        <span className={`flex items-center gap-1 text-xs ${prazo.classe}`}>
                          {prazo.dias < 0 ? <AlertTriangle size={12} /> : null}
                          {prazo.dias < 0 ? `Venceu há ${Math.abs(prazo.dias)}d` : `${prazo.dias}d`}
                        </span>
                      ) : (
                        <span className="text-afj-black/30 text-xs">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-afj-black/60 text-xs">
                      {p.valor_causa ? `R$ ${p.valor_causa.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}` : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
