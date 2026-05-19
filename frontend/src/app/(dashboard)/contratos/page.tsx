"use client";
import { useState, useEffect } from "react";
import { FileSignature, Plus, Search, Calendar } from "lucide-react";

interface Contrato {
  id: string;
  titulo: string;
  tipo: string;
  status: string;
  valor_total: number | null;
  data_inicio: string | null;
  data_fim: string | null;
  renovacao_auto: boolean;
  client_id: string | null;
  created_at: string;
}

const STATUS_STYLE: Record<string, string> = {
  RASCUNHO: "badge-pendente",
  ATIVO: "badge-ativo",
  ENCERRADO: "badge-arquivado",
  CANCELADO: "badge-arquivado",
};

export default function ContratosPage() {
  const [contratos, setContratos] = useState<Contrato[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  useEffect(() => { fetchContratos(); }, []);

  async function fetchContratos() {
    setLoading(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/documents?tipo=CONTRATO", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const docs = await res.json();
        setContratos(docs);
      }
    } finally { setLoading(false); }
  }

  const filtrados = contratos.filter((c) =>
    !search || c.titulo?.toLowerCase().includes(search.toLowerCase())
  );

  const fmt = (v: number) => `R$ ${v.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`;

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-semibold text-afj-black">Contratos</h1>
          <p className="text-afj-black/50 text-sm">{filtrados.length} contrato(s)</p>
        </div>
      </div>

      <div className="flex gap-3">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-afj-black/30" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por título..."
            className="w-full pl-9 pr-4 py-2 text-sm border border-afj-cream-dark rounded-md focus:outline-none focus:border-afj-gold bg-white"
          />
        </div>
      </div>

      {loading ? (
        <div className="afj-card p-8 text-center text-afj-black/40">Carregando contratos...</div>
      ) : filtrados.length === 0 ? (
        <div className="afj-card p-12 text-center">
          <FileSignature className="mx-auto text-afj-black/20 mb-3" size={40} />
          <p className="font-semibold text-afj-black">Nenhum contrato encontrado</p>
          <p className="text-afj-black/40 text-sm mt-1">Contratos gerados pelo agente de contratos aparecerão aqui</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtrados.map((c) => (
            <div key={c.id} className="afj-card p-4 hover:border-afj-gold/30 transition-colors">
              <div className="flex items-start justify-between mb-3">
                <span className={STATUS_STYLE[c.status] ?? "badge-arquivado"}>{c.status}</span>
                {c.renovacao_auto && (
                  <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full">Auto-renovação</span>
                )}
              </div>
              <p className="font-semibold text-afj-black text-sm">{c.titulo}</p>
              <p className="text-xs text-afj-black/50 mt-1">{c.tipo}</p>
              {(c.valor_total !== null && c.valor_total !== undefined) && (
                <p className="text-sm font-semibold text-afj-gold mt-2">{fmt(c.valor_total)}</p>
              )}
              {(c.data_inicio || c.data_fim) && (
                <div className="mt-3 pt-2 border-t border-afj-cream-dark flex items-center gap-2 text-xs text-afj-black/50">
                  <Calendar size={11} />
                  {c.data_inicio && new Date(c.data_inicio).toLocaleDateString("pt-BR")}
                  {c.data_inicio && c.data_fim && " → "}
                  {c.data_fim && new Date(c.data_fim).toLocaleDateString("pt-BR")}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
