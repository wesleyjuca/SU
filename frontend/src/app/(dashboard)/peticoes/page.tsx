"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { FileText, Plus, Search, Clock, CheckCircle, XCircle, AlertCircle } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";

interface Peticao {
  id: string;
  titulo: string;
  tipo: string;
  status: string;
  review_status: string | null;
  process_id: string | null;
  gerado_por_ia: boolean;
  created_at: string;
}

const STATUS_STYLE: Record<string, string> = {
  RASCUNHO: "badge-pendente",
  REVISAO: "badge-pendente",
  APROVADO: "badge-ativo",
  PROTOCOLADO: "badge-ativo",
  REJEITADO: "badge-arquivado",
};

const STATUS_ICON: Record<string, React.ReactNode> = {
  RASCUNHO: <Clock size={11} />,
  REVISAO: <AlertCircle size={11} />,
  APROVADO: <CheckCircle size={11} />,
  REJEITADO: <XCircle size={11} />,
};

export default function PeticoesPage() {
  const [peticoes, setPeticoes] = useState<Peticao[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filtroStatus, setFiltroStatus] = useState("");

  useEffect(() => { fetchPeticoes(); }, [filtroStatus]);

  async function fetchPeticoes() {
    setLoading(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const params = new URLSearchParams();
      if (filtroStatus) params.set("status", filtroStatus);
      const res = await fetch(`/api/v1/documents?tipo=PETICAO&${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setPeticoes(await res.json());
    } finally { setLoading(false); }
  }

  const filtrados = peticoes.filter((p) =>
    !search || p.titulo.toLowerCase().includes(search.toLowerCase())
  );

  const totais = {
    todas: peticoes.length,
    aguardando: peticoes.filter((p) => p.status === "REVISAO").length,
    aprovadas: peticoes.filter((p) => p.status === "APROVADO").length,
    rascunhos: peticoes.filter((p) => p.status === "RASCUNHO").length,
  };

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Petições" }]} />
      <div className="afj-page-header">
        <div>
          <h1 className="font-display text-2xl font-semibold text-afj-black">Petições</h1>
          <p className="text-afj-black/50 text-sm">{filtrados.length} petição(ões)</p>
        </div>
        <Link href="/peticoes/nova" className="btn-afj-primary rounded-sm flex items-center gap-2">
          <Plus size={15} />
          Nova Petição com IA
        </Link>
      </div>

      {/* KPIs rápidos */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: "Total", value: totais.todas, cls: "" },
          { label: "Em Revisão", value: totais.aguardando, cls: "!text-amber-600" },
          { label: "Aprovadas", value: totais.aprovadas, cls: "!text-green-600" },
          { label: "Rascunhos", value: totais.rascunhos, cls: "!text-afj-black/40" },
        ].map(({ label, value, cls }) => (
          <div key={label} className="afj-stat-card">
            <span className="stat-label">{label}</span>
            <span className={`stat-value ${cls}`}>{value}</span>
          </div>
        ))}
      </div>

      {/* Filtros */}
      <div className="flex gap-3">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-afj-black/30" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por título..."
            className="w-full pl-9 pr-4 py-2 text-sm border border-afj-cream-dark rounded-sm focus:outline-none focus:border-afj-gold bg-white"
          />
        </div>
        <select
          value={filtroStatus}
          onChange={(e) => setFiltroStatus(e.target.value)}
          className="border border-afj-cream-dark rounded-sm px-3 py-2 text-sm bg-white focus:outline-none focus:border-afj-gold"
        >
          <option value="">Todos os status</option>
          <option value="RASCUNHO">Rascunho</option>
          <option value="REVISAO">Em Revisão</option>
          <option value="APROVADO">Aprovado</option>
          <option value="PROTOCOLADO">Protocolado</option>
        </select>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="afj-card p-5 h-28 animate-pulse bg-afj-cream-dark/40" />
          ))}
        </div>
      ) : filtrados.length === 0 ? (
        <div className="afj-card p-12 text-center">
          <FileText className="mx-auto text-afj-black/20 mb-3" size={40} />
          <p className="font-semibold text-afj-black">Nenhuma petição encontrada</p>
          <p className="text-afj-black/40 text-sm mt-1">Use o assistente de IA para gerar sua primeira petição</p>
          <Link href="/peticoes/nova" className="btn-afj-primary rounded-sm inline-flex items-center gap-2 mt-4 text-sm">
            <Plus size={14} />
            Gerar Petição com IA
          </Link>
        </div>
      ) : (
        <div className="afj-card overflow-hidden">
          <table className="afj-table">
            <thead>
              <tr>
                <th>Título</th>
                <th>Tipo</th>
                <th>Status</th>
                <th>Gerada por IA</th>
                <th>Data</th>
              </tr>
            </thead>
            <tbody>
              {filtrados.map((p) => (
                <tr key={p.id}>
                  <td className="px-4 py-3">
                    <span className="font-medium text-afj-black">{p.titulo}</span>
                  </td>
                  <td className="px-4 py-3 text-afj-black/60 text-xs">{p.tipo}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center gap-1 ${STATUS_STYLE[p.status] ?? "badge-arquivado"}`}>
                      {STATUS_ICON[p.status]}
                      {p.status}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {p.gerado_por_ia ? (
                      <span className="text-xs bg-purple-100 text-purple-700 px-2 py-0.5 rounded-full">IA</span>
                    ) : (
                      <span className="text-xs text-afj-black/30">Manual</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-afj-black/40 text-xs">
                    {new Date(p.created_at).toLocaleDateString("pt-BR")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
