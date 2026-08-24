"use client";
import { useState, useEffect } from "react";
import { Scale, ChevronRight, ChevronDown, CalendarClock, AlertTriangle, Loader2 } from "lucide-react";
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

interface ProcessDetail extends PortalProcesso {
  vara: string | null;
  comarca: string | null;
  uf: string | null;
  tipo_acao: string | null;
  fase: string | null;
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

const AREA_BADGE: Record<string, string> = {
  CIVIL: "bg-blue-100 text-blue-700",
  TRABALHISTA: "bg-purple-100 text-purple-700",
  PENAL: "bg-red-100 text-red-700",
  TRIBUTARIO: "bg-orange-100 text-orange-700",
};

function formatBRL(v: number) {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(v);
}

function diasParaPrazo(dateStr: string): number {
  return Math.ceil((new Date(dateStr).getTime() - Date.now()) / (1000 * 60 * 60 * 24));
}

/** Fase 233 — seção principal do dashboard único do portal ("toda a sua
 * situação processual"). Antes eram 2 rotas separadas
 * (`/portal/processos` + `/portal/processos/[id]`); agora o detalhe
 * (dados completos + prazos + timeline de movimentações) expande inline
 * no lugar de navegar, buscado sob demanda no primeiro clique e
 * cacheado em `detalhes` pra não rebuscar. */
export function ProcessosSection() {
  const toast = useToast();
  const [processos, setProcessos] = useState<PortalProcesso[]>([]);
  const [loading, setLoading] = useState(true);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [detalhes, setDetalhes] = useState<Record<string, ProcessDetail>>({});
  const [loadingDetalhe, setLoadingDetalhe] = useState<string | null>(null);

  useEffect(() => { load(0); }, []);

  async function load(off: number) {
    try {
      const data = await portalApi.get<PortalProcesso[]>(`/portal/processes?limit=20&offset=${off}`);
      setProcessos((prev) => (off === 0 ? data : [...prev, ...data]));
      setHasMore(data.length === 20);
      setOffset(off + data.length);
    } catch {
      toast.error("Erro ao carregar processos.");
    } finally {
      setLoading(false);
    }
  }

  async function toggleExpand(id: string) {
    if (expandedId === id) { setExpandedId(null); return; }
    setExpandedId(id);
    if (!detalhes[id]) {
      setLoadingDetalhe(id);
      try {
        const detalhe = await portalApi.get<ProcessDetail>(`/portal/processes/${id}`);
        setDetalhes((prev) => ({ ...prev, [id]: detalhe }));
      } catch {
        toast.error("Erro ao carregar detalhes do processo.");
        setExpandedId(null);
      } finally {
        setLoadingDetalhe(null);
      }
    }
  }

  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-white rounded-xl border border-gray-200 p-4 h-20 animate-pulse" />
        ))}
      </div>
    );
  }

  if (processos.length === 0) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
        <Scale className="mx-auto text-gray-300 mb-3" size={36} />
        <p className="font-semibold text-gray-600">Nenhum processo encontrado</p>
        <p className="text-sm text-gray-400 mt-1">Seus processos aparecerão aqui quando forem registrados.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {processos.map((p) => {
        const dias = p.proximo_prazo_at ? diasParaPrazo(p.proximo_prazo_at) : null;
        const prazoUrgente = dias !== null && dias <= 5;
        const expandido = expandedId === p.id;
        const detalhe = detalhes[p.id];
        return (
          <div key={p.id} className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <button
              onClick={() => toggleExpand(p.id)}
              className="w-full text-left hover:bg-gray-50/60 transition-colors p-4"
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
                {expandido ? (
                  <ChevronDown size={16} className="text-gray-300 flex-shrink-0 mt-1" />
                ) : (
                  <ChevronRight size={16} className="text-gray-300 flex-shrink-0 mt-1" />
                )}
              </div>
            </button>

            {expandido && (
              <div className="border-t border-gray-100 p-4 space-y-4 bg-gray-50/40">
                {loadingDetalhe === p.id || !detalhe ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="animate-spin text-gray-400" size={20} />
                  </div>
                ) : (
                  <>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
                      {[
                        { label: "Vara", value: detalhe.vara },
                        { label: "Comarca / UF", value: [detalhe.comarca, detalhe.uf].filter(Boolean).join(" / ") || null },
                        { label: "Tipo de Ação", value: detalhe.tipo_acao },
                        { label: "Fase", value: detalhe.fase },
                        { label: "Polo", value: detalhe.polo },
                        { label: "Valor da Causa", value: detalhe.valor_causa ? formatBRL(detalhe.valor_causa) : null },
                        { label: "Distribuição", value: detalhe.distribuicao_data ? new Date(detalhe.distribuicao_data).toLocaleDateString("pt-BR") : null },
                      ].filter((row) => row.value).map(({ label, value }) => (
                        <div key={label}>
                          <p className="text-xs text-gray-400 uppercase tracking-wide">{label}</p>
                          <p className="font-medium text-gray-700 mt-0.5">{value}</p>
                        </div>
                      ))}
                    </div>

                    {detalhe.deadlines.length > 0 && (
                      <div className="bg-white rounded-lg border border-amber-200 p-4">
                        <h3 className="text-sm font-semibold text-amber-800 mb-3 flex items-center gap-2">
                          <CalendarClock size={14} className="text-amber-600" />
                          Prazos Pendentes
                        </h3>
                        <div className="space-y-2">
                          {detalhe.deadlines.map((d) => {
                            const diasD = diasParaPrazo(d.data_prazo);
                            const urgente = diasD <= 5;
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
                                    {diasD === 0 ? "Hoje" : diasD < 0 ? `${Math.abs(diasD)}d atrasado` : `em ${diasD}d`}
                                  </p>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    <div className="bg-white rounded-lg border border-gray-200 p-4">
                      <h3 className="text-sm font-semibold text-gray-700 mb-4">
                        Movimentações ({detalhe.movements.length})
                      </h3>
                      {detalhe.movements.length === 0 ? (
                        <p className="text-sm text-gray-400 text-center py-6">Nenhuma movimentação registrada</p>
                      ) : (
                        <div className="relative">
                          <div className="absolute left-3 top-0 bottom-0 w-px bg-gray-200" />
                          <div className="space-y-4">
                            {detalhe.movements.map((m) => (
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
                  </>
                )}
              </div>
            )}
          </div>
        );
      })}

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
