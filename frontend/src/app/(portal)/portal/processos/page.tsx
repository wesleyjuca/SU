"use client";
import { useState, useEffect } from "react";
import { Scale, ChevronRight, CalendarClock, AlertTriangle } from "lucide-react";
import Link from "next/link";
import { portalApi } from "@/lib/portalApi";
import { useToast } from "@/components/ui/Toast";

interface PortalProcesso {
  id: string;
  numero_cnj: string | null;
  tribunal: string;
  area_direito: string | null;
  situacao: string;
  proximo_prazo_at: string | null;
  ultimo_andamento_at: string | null;
  parte_contraria: string | null;
  polo: string | null;
}

const SITUACAO_BADGE: Record<string, string> = {
  ATIVO: "bg-green-100 text-green-700",
  SUSPENSO: "bg-amber-100 text-amber-700",
  ARQUIVADO: "bg-gray-100 text-gray-500",
  ENCERRADO: "bg-gray-100 text-gray-500",
};

const AREA_BADGE: Record<string, string> = {
  CIVIL: "bg-blue-100 text-blue-700",
  TRABALHISTA: "bg-purple-100 text-purple-700",
  PENAL: "bg-red-100 text-red-700",
  TRIBUTARIO: "bg-orange-100 text-orange-700",
};

function diasParaPrazo(dateStr: string): number {
  const prazo = new Date(dateStr);
  const hoje = new Date();
  return Math.ceil((prazo.getTime() - hoje.getTime()) / (1000 * 60 * 60 * 24));
}

export default function PortalProcessosPage() {
  const toast = useToast();
  const [processos, setProcessos] = useState<PortalProcesso[]>([]);
  const [loading, setLoading] = useState(true);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);

  useEffect(() => { load(0); }, []);

  async function load(off: number) {
    try {
      const data = await portalApi.get<PortalProcesso[]>(`/portal/processes?limit=20&offset=${off}`);
      if (off === 0) {
        setProcessos(data);
      } else {
        setProcessos((prev) => [...prev, ...data]);
      }
      setHasMore(data.length === 20);
      setOffset(off + data.length);
    } catch {
      toast.error("Erro ao carregar processos.");
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-7 w-48 bg-gray-200 rounded animate-pulse" />
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-white rounded-xl border border-gray-200 p-4 h-20 animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">Meus Processos</h1>
        <span className="text-sm text-gray-500">{processos.length} processo{processos.length !== 1 ? "s" : ""}</span>
      </div>

      {processos.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
          <Scale className="mx-auto text-gray-300 mb-3" size={36} />
          <p className="font-semibold text-gray-600">Nenhum processo encontrado</p>
          <p className="text-sm text-gray-400 mt-1">Seus processos aparecerão aqui quando forem registrados.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {processos.map((p) => {
            const dias = p.proximo_prazo_at ? diasParaPrazo(p.proximo_prazo_at) : null;
            const prazoUrgente = dias !== null && dias <= 5;
            return (
              <Link
                key={p.id}
                href={`/portal/processos/${p.id}`}
                className="block bg-white rounded-xl border border-gray-200 hover:border-[#B8954A]/40 hover:shadow-sm transition-all p-4"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap mb-1.5">
                      <span className="font-mono text-sm font-semibold text-gray-800">
                        {p.numero_cnj ?? "Sem número CNJ"}
                      </span>
                      <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${SITUACAO_BADGE[p.situacao] ?? "bg-gray-100 text-gray-500"}`}>
                        {p.situacao}
                      </span>
                      {p.area_direito && (
                        <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${AREA_BADGE[p.area_direito] ?? "bg-gray-100 text-gray-500"}`}>
                          {p.area_direito}
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-gray-600">{p.tribunal}</p>
                    {p.parte_contraria && (
                      <p className="text-xs text-gray-400 mt-0.5">vs. {p.parte_contraria}</p>
                    )}
                    <div className="flex items-center gap-4 mt-2">
                      {dias !== null && (
                        <div className={`flex items-center gap-1 text-xs ${prazoUrgente ? "text-red-600 font-medium" : "text-gray-400"}`}>
                          {prazoUrgente && <AlertTriangle size={11} />}
                          <CalendarClock size={11} />
                          Prazo: {dias === 0 ? "Hoje" : dias < 0 ? `${Math.abs(dias)}d atrasado` : `em ${dias}d`}
                        </div>
                      )}
                      {p.ultimo_andamento_at && (
                        <p className="text-xs text-gray-400">
                          Atualizado {new Date(p.ultimo_andamento_at).toLocaleDateString("pt-BR")}
                        </p>
                      )}
                    </div>
                  </div>
                  <ChevronRight size={16} className="text-gray-300 flex-shrink-0 mt-1" />
                </div>
              </Link>
            );
          })}
        </div>
      )}

      {hasMore && (
        <button
          onClick={() => load(offset)}
          className="w-full py-2.5 border border-gray-200 rounded-xl text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors"
        >
          Carregar mais
        </button>
      )}
    </div>
  );
}
