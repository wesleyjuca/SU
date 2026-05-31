"use client";
import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Scale, CalendarClock, AlertTriangle } from "lucide-react";
import { portalApi } from "@/lib/portalApi";
import { useToast } from "@/components/ui/Toast";

interface Movement {
  id: string;
  data_movimento: string | null;
  descricao: string;
  tipo: string | null;
  ai_summary: string | null;
}

interface Deadline {
  id: string;
  descricao: string;
  data_prazo: string;
  data_fatal: string | null;
  tipo: string | null;
}

interface ProcessDetail {
  id: string;
  numero_cnj: string | null;
  tribunal: string;
  vara: string | null;
  comarca: string | null;
  uf: string | null;
  area_direito: string | null;
  tipo_acao: string | null;
  fase: string | null;
  situacao: string;
  polo: string | null;
  parte_contraria: string | null;
  valor_causa: number | null;
  distribuicao_data: string | null;
  movements: Movement[];
  deadlines: Deadline[];
}

const SITUACAO_BADGE: Record<string, string> = {
  ATIVO: "bg-green-100 text-green-700",
  SUSPENSO: "bg-amber-100 text-amber-700",
  ARQUIVADO: "bg-gray-100 text-gray-500",
  ENCERRADO: "bg-gray-100 text-gray-500",
};

function formatBRL(v: number) {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(v);
}

function diasParaPrazo(dateStr: string): number {
  return Math.ceil((new Date(dateStr).getTime() - Date.now()) / (1000 * 60 * 60 * 24));
}

export default function PortalProcessoDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const toast = useToast();
  const [processo, setProcesso] = useState<ProcessDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    portalApi.get<ProcessDetail>(`/portal/processes/${id}`)
      .then(setProcesso)
      .catch(() => toast.error("Processo não encontrado."))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-6 w-32 bg-gray-200 rounded animate-pulse" />
        <div className="bg-white rounded-xl border border-gray-200 p-5 h-32 animate-pulse" />
        <div className="bg-white rounded-xl border border-gray-200 p-5 h-48 animate-pulse" />
      </div>
    );
  }

  if (!processo) {
    return (
      <div className="text-center py-16">
        <Scale className="mx-auto text-gray-300 mb-3" size={36} />
        <p className="font-semibold text-gray-600">Processo não encontrado</p>
        <button onClick={() => router.back()} className="mt-4 text-sm text-[#B8954A] hover:underline">
          Voltar
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <button
        onClick={() => router.back()}
        className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-800"
      >
        <ArrowLeft size={14} /> Voltar para Processos
      </button>

      {/* Process info card */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <div className="flex items-start justify-between gap-3 mb-4">
          <div>
            <p className="font-mono text-lg font-bold text-gray-900">{processo.numero_cnj ?? "Sem número CNJ"}</p>
            {processo.tipo_acao && <p className="text-sm text-gray-500 mt-0.5">{processo.tipo_acao}</p>}
          </div>
          <span className={`text-xs font-medium px-2.5 py-1 rounded-full flex-shrink-0 ${SITUACAO_BADGE[processo.situacao] ?? "bg-gray-100 text-gray-500"}`}>
            {processo.situacao}
          </span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
          {[
            { label: "Tribunal", value: processo.tribunal },
            { label: "Vara", value: processo.vara },
            { label: "Comarca / UF", value: [processo.comarca, processo.uf].filter(Boolean).join(" / ") || null },
            { label: "Área", value: processo.area_direito },
            { label: "Fase", value: processo.fase },
            { label: "Polo", value: processo.polo },
            { label: "Parte Contrária", value: processo.parte_contraria },
            { label: "Valor da Causa", value: processo.valor_causa ? formatBRL(processo.valor_causa) : null },
            { label: "Distribuição", value: processo.distribuicao_data ? new Date(processo.distribuicao_data).toLocaleDateString("pt-BR") : null },
          ].filter((row) => row.value).map(({ label, value }) => (
            <div key={label}>
              <p className="text-xs text-gray-400 uppercase tracking-wide">{label}</p>
              <p className="font-medium text-gray-700 mt-0.5">{value}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Pending deadlines */}
      {processo.deadlines.length > 0 && (
        <div className="bg-white rounded-xl border border-amber-200 p-5">
          <h2 className="text-sm font-semibold text-amber-800 mb-3 flex items-center gap-2">
            <CalendarClock size={15} className="text-amber-600" />
            Prazos Pendentes
          </h2>
          <div className="space-y-2">
            {processo.deadlines.map((d) => {
              const dias = diasParaPrazo(d.data_prazo);
              const urgente = dias <= 5;
              return (
                <div key={d.id} className={`flex items-start justify-between gap-3 p-3 rounded-lg border ${urgente ? "border-red-200 bg-red-50" : "border-amber-100 bg-amber-50/50"}`}>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-800">{d.descricao}</p>
                    {d.tipo && <p className="text-xs text-gray-500 mt-0.5">{d.tipo}</p>}
                  </div>
                  <div className="text-right flex-shrink-0">
                    <p className="text-xs font-semibold text-gray-700">
                      {new Date(d.data_prazo).toLocaleDateString("pt-BR")}
                    </p>
                    <p className={`text-xs mt-0.5 flex items-center gap-1 justify-end ${urgente ? "text-red-600 font-medium" : "text-amber-600"}`}>
                      {urgente && <AlertTriangle size={10} />}
                      {dias === 0 ? "Hoje" : dias < 0 ? `${Math.abs(dias)}d atrasado` : `em ${dias}d`}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Movements timeline */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h2 className="text-sm font-semibold text-gray-700 mb-4">
          Movimentações ({processo.movements.length})
        </h2>
        {processo.movements.length === 0 ? (
          <p className="text-sm text-gray-400 text-center py-6">Nenhuma movimentação registrada</p>
        ) : (
          <div className="relative">
            <div className="absolute left-3 top-0 bottom-0 w-px bg-gray-200" />
            <div className="space-y-4">
              {processo.movements.map((m) => (
                <div key={m.id} className="pl-8 relative">
                  <div className="absolute left-2 top-1 w-2.5 h-2.5 rounded-full bg-[#B8954A] border-2 border-white ring-1 ring-[#B8954A]/30" />
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      {m.ai_summary ? (
                        <>
                          <p className="text-sm text-gray-800">{m.ai_summary}</p>
                          <p className="text-xs text-gray-400 mt-1 line-clamp-1">{m.descricao}</p>
                        </>
                      ) : (
                        <p className="text-sm text-gray-700">{m.descricao}</p>
                      )}
                      {m.tipo && (
                        <span className="inline-block mt-1 text-[10px] font-medium px-1.5 py-0.5 rounded bg-gray-100 text-gray-500">
                          {m.tipo}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-gray-400 flex-shrink-0 mt-0.5">
                      {m.data_movimento ? new Date(m.data_movimento).toLocaleDateString("pt-BR") : "—"}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
