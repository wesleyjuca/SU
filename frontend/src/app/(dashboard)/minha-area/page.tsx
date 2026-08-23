"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import {
  Briefcase, Scale, CalendarClock, Newspaper, AlertTriangle,
  ChevronRight, Loader2, Users2, ShieldCheck, Bell,
} from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { useUserStore, useNotificationStore } from "@/store";
import { useNotifications } from "@/hooks/useNotifications";
import { PriorityBadge } from "@/components/approvals/ApprovalCard";
import type { Processo } from "@/types";

// Fase 218 — ecos de ProcessDeadline/Approval já mostrados nos cards de
// prazos/aprovações desta mesma página; sem excluir, apareceriam 2-3x.
const TIPOS_NOTIFICACAO_ECO = ["PRAZO_VENCENDO", "APROVACAO_PENDENTE"];

interface MeuPrazo {
  id: string;
  descricao: string;
  tipo: string | null;
  status: string;
  data_prazo: string | null;
  data_fatal: string | null;
  process_id: string;
  numero_cnj: string | null;
  tribunal: string;
  area_direito: string | null;
}

interface MinhaIntimacao {
  id: string;
  process_id: string | null;
  numero_cnj: string | null;
  texto: string;
  data_disponibilizacao: string | null;
  tribunal: string | null;
  tipo_comunicacao: string | null;
  status: string;
}

interface MinhaAprovacao {
  id: string;
  titulo: string;
  descricao: string | null;
  prioridade: string;
  expires_at: string | null;
  created_at: string;
}


function diasPara(data: string | null): number | null {
  if (!data) return null;
  return Math.ceil((new Date(data).getTime() - Date.now()) / 86400000);
}

function prazoBadge(dias: number | null) {
  if (dias === null) return { text: "sem data", cls: "text-afj-black/40" };
  if (dias < 0) return { text: `${Math.abs(dias)}d em atraso`, cls: "text-red-600 font-bold" };
  if (dias === 0) return { text: "Hoje!", cls: "text-red-600 font-bold" };
  if (dias === 1) return { text: "Amanhã", cls: "text-red-500 font-semibold" };
  return { text: `${dias} dias`, cls: dias <= 7 ? "text-amber-600 font-semibold" : "text-afj-black/40" };
}

const SITUACAO_BADGE: Record<string, string> = {
  ATIVO: "bg-green-50 text-green-700 border-green-200",
  SUSPENSO: "bg-amber-50 text-amber-700 border-amber-200",
  ARQUIVADO: "bg-gray-50 text-gray-500 border-gray-200",
  ENCERRADO: "bg-gray-50 text-gray-500 border-gray-200",
};

export default function MinhaAreaPage() {
  const { user } = useUserStore();
  const [prazos, setPrazos] = useState<MeuPrazo[]>([]);
  const [processos, setProcessos] = useState<Processo[]>([]);
  const [intimacoes, setIntimacoes] = useState<MinhaIntimacao[]>([]);
  const [aprovacoes, setAprovacoes] = useState<MinhaAprovacao[]>([]);
  const [loading, setLoading] = useState(true);

  // Fase 218 — o store global já é mantido fresco por useNotifications()
  // no layout do dashboard; não precisa de fetch próprio aqui.
  const { notifications } = useNotificationStore();
  const { markNotificationRead } = useNotifications();
  const notificacoesRelevantes = notifications.filter(
    (n) => !TIPOS_NOTIFICACAO_ECO.includes(n.tipo ?? "")
  );

  useEffect(() => {
    const token = localStorage.getItem("afj_access_token");
    const headers = { Authorization: `Bearer ${token}` };
    async function fetchAll() {
      setLoading(true);
      try {
        const [rP, rProc, rInt, rApr] = await Promise.all([
          fetch("/api/v1/processes/agenda?dias=7&mine=true", { headers }),
          fetch("/api/v1/processes?mine=true", { headers }),
          fetch("/api/v1/publicacoes?status=NOVA&mine=true", { headers }),
          fetch("/api/v1/approvals?status=PENDENTE&limit=50", { headers }),
        ]);
        if (rP.ok) setPrazos(await rP.json());
        if (rProc.ok) setProcessos(await rProc.json());
        if (rInt.ok) setIntimacoes(await rInt.json());
        if (rApr.ok) setAprovacoes(await rApr.json());
      } finally {
        setLoading(false);
      }
    }
    fetchAll();
  }, []);

  const hoje = prazos.filter((p) => {
    const d = diasPara(p.data_prazo);
    return d !== null && d <= 0;
  });
  const primeiroNome = (user?.full_name || "").split(" ")[0];

  return (
    <div className="max-w-[1600px] mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Minha Área" }]} />
      <div className="afj-page-header">
        <div>
          <h1 className="afj-page-title flex items-center gap-2">
            <Briefcase size={22} className="text-afj-gold" /> Minha Área{primeiroNome ? ` — ${primeiroNome}` : ""}
          </h1>
          <p className="text-afj-black/45 text-sm mt-1">
            Seu dia de trabalho: prazos da semana, processos sob sua responsabilidade e intimações a triar (somente o que é seu, responsável ou equipe), além das aprovações pendentes do escritório e suas notificações recentes.
          </p>
        </div>
      </div>

      {/* Resumo */}
      <div className="grid grid-cols-2 lg:grid-cols-6 gap-4">
        <div className="afj-stat-card">
          <p className="text-[11px] uppercase tracking-wider text-afj-black/45 font-semibold">Prazos hoje/atraso</p>
          <p className={`text-2xl font-display font-bold mt-1 ${hoje.length > 0 ? "text-red-600" : "text-afj-black"}`}>{loading ? "—" : hoje.length}</p>
        </div>
        <div className="afj-stat-card">
          <p className="text-[11px] uppercase tracking-wider text-afj-black/45 font-semibold">Prazos em 7 dias</p>
          <p className="text-2xl font-display font-bold text-afj-black mt-1">{loading ? "—" : prazos.length}</p>
        </div>
        <div className="afj-stat-card">
          <p className="text-[11px] uppercase tracking-wider text-afj-black/45 font-semibold">Meus processos</p>
          <p className="text-2xl font-display font-bold text-afj-black mt-1">{loading ? "—" : processos.length}</p>
        </div>
        <div className="afj-stat-card">
          <p className="text-[11px] uppercase tracking-wider text-afj-black/45 font-semibold">Intimações a triar</p>
          <p className={`text-2xl font-display font-bold mt-1 ${intimacoes.length > 0 ? "text-amber-600" : "text-afj-black"}`}>{loading ? "—" : intimacoes.length}</p>
        </div>
        <div className="afj-stat-card">
          <p className="text-[11px] uppercase tracking-wider text-afj-black/45 font-semibold">Aprovações pendentes</p>
          <p className={`text-2xl font-display font-bold mt-1 ${aprovacoes.length > 0 ? "text-amber-600" : "text-afj-black"}`}>{loading ? "—" : aprovacoes.length}</p>
        </div>
        <div className="afj-stat-card">
          <p className="text-[11px] uppercase tracking-wider text-afj-black/45 font-semibold">Notificações não lidas</p>
          <p className="text-2xl font-display font-bold text-afj-black mt-1">{notificacoesRelevantes.filter((n) => !n.lida).length}</p>
        </div>
      </div>

      {loading ? (
        <div className="afj-card p-12 flex items-center justify-center text-afj-black/40 gap-2">
          <Loader2 size={18} className="animate-spin" /> Carregando seu dia...
        </div>
      ) : (
        <div className="grid lg:grid-cols-2 gap-5 items-start">
          {/* Meus prazos (7 dias) */}
          <div className="afj-card p-0 overflow-hidden">
            <div className="afj-section-header flex items-center justify-between px-4 pt-4">
              <span className="flex items-center gap-2"><CalendarClock size={16} className="text-afj-gold" /> Meus prazos — próximos 7 dias</span>
              <Link href="/agenda" className="text-xs text-afj-gold hover:underline flex items-center gap-0.5">Agenda <ChevronRight size={12} /></Link>
            </div>
            {prazos.length === 0 ? (
              <p className="text-sm text-afj-black/40 px-4 pb-5">Nenhum prazo seu nos próximos 7 dias. ✓</p>
            ) : (
              <ul className="divide-y divide-afj-cream-dark/60">
                {prazos.slice(0, 8).map((p) => {
                  const d = diasPara(p.data_prazo);
                  const badge = prazoBadge(d);
                  return (
                    <li key={p.id}>
                      <Link href={`/processos/${p.process_id}`} className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-afj-cream/60 transition-colors">
                        <div className="min-w-0">
                          <p className="text-sm text-afj-black/80 truncate">{p.descricao}</p>
                          <p className="text-xs text-afj-black/40 mt-0.5">{p.numero_cnj || "s/ CNJ"} · {p.tribunal}{p.data_prazo ? ` · ${new Date(p.data_prazo).toLocaleDateString("pt-BR")}` : ""}</p>
                        </div>
                        <span className={`text-xs shrink-0 ${badge.cls}`}>{d !== null && d <= 1 && <AlertTriangle size={12} className="inline mr-1 -mt-0.5" />}{badge.text}</span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {/* Intimações a triar */}
          <div className="afj-card p-0 overflow-hidden">
            <div className="afj-section-header flex items-center justify-between px-4 pt-4">
              <span className="flex items-center gap-2"><Newspaper size={16} className="text-afj-gold" /> Minhas intimações a triar</span>
              <Link href="/publicacoes" className="text-xs text-afj-gold hover:underline flex items-center gap-0.5">Publicações <ChevronRight size={12} /></Link>
            </div>
            {intimacoes.length === 0 ? (
              <p className="text-sm text-afj-black/40 px-4 pb-5">Nenhuma intimação pendente nos seus processos. ✓</p>
            ) : (
              <ul className="divide-y divide-afj-cream-dark/60">
                {intimacoes.slice(0, 6).map((i) => (
                  <li key={i.id}>
                    <Link href="/publicacoes" className="block px-4 py-3 hover:bg-afj-cream/60 transition-colors">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-sm border bg-amber-50 text-amber-700 border-amber-200">NOVA</span>
                        <span className="text-xs text-afj-black/50">{i.numero_cnj || "sem CNJ"}</span>
                        {i.tribunal && <span className="text-xs text-afj-black/40">· {i.tribunal}</span>}
                        {i.data_disponibilizacao && <span className="text-xs text-afj-black/40">· {new Date(i.data_disponibilizacao + "T00:00:00").toLocaleDateString("pt-BR")}</span>}
                      </div>
                      <p className="text-sm text-afj-black/70 mt-1.5 line-clamp-2">{i.texto}</p>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Aprovações pendentes — Fase 218 */}
          <div className="afj-card p-0 overflow-hidden">
            <div className="afj-section-header flex items-center justify-between px-4 pt-4">
              <span className="flex items-center gap-2"><ShieldCheck size={16} className="text-afj-gold" /> Aprovações pendentes</span>
              <Link href="/aprovacoes" className="text-xs text-afj-gold hover:underline flex items-center gap-0.5">Ver todas <ChevronRight size={12} /></Link>
            </div>
            {aprovacoes.length === 0 ? (
              <p className="text-sm text-afj-black/40 px-4 pb-5">Nenhuma aprovação pendente no escritório. ✓</p>
            ) : (
              <ul className="divide-y divide-afj-cream-dark/60">
                {aprovacoes.slice(0, 8).map((a) => (
                  <li key={a.id}>
                    <Link href="/aprovacoes" className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-afj-cream/60 transition-colors">
                      <div className="min-w-0">
                        <p className="text-sm text-afj-black/80 truncate">{a.titulo}</p>
                        {a.descricao && <p className="text-xs text-afj-black/40 mt-0.5 truncate">{a.descricao}</p>}
                      </div>
                      <span className="shrink-0"><PriorityBadge prioridade={a.prioridade} /></span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Notificações recentes — Fase 218 */}
          <div className="afj-card p-0 overflow-hidden">
            <div className="afj-section-header flex items-center px-4 pt-4">
              <span className="flex items-center gap-2"><Bell size={16} className="text-afj-gold" /> Notificações recentes</span>
            </div>
            {notificacoesRelevantes.length === 0 ? (
              <p className="text-sm text-afj-black/40 px-4 pb-5">Nenhuma notificação recente. ✓</p>
            ) : (
              <ul className="divide-y divide-afj-cream-dark/60">
                {notificacoesRelevantes.slice(0, 8).map((n) => {
                  const conteudo = (
                    <div className="min-w-0">
                      <p className={`text-sm truncate ${n.lida ? "text-afj-black/60" : "text-afj-black font-medium"}`}>{n.titulo}</p>
                      {n.corpo && <p className="text-xs text-afj-black/40 mt-0.5 truncate">{n.corpo}</p>}
                    </div>
                  );
                  return (
                    <li key={n.id}>
                      {n.link ? (
                        <Link
                          href={n.link}
                          onClick={() => !n.lida && markNotificationRead(n.id)}
                          className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-afj-cream/60 transition-colors"
                        >
                          {conteudo}
                        </Link>
                      ) : (
                        <button
                          onClick={() => !n.lida && markNotificationRead(n.id)}
                          className="w-full text-left flex items-center justify-between gap-3 px-4 py-3 hover:bg-afj-cream/60 transition-colors"
                        >
                          {conteudo}
                        </button>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {/* Meus processos */}
          <div className="afj-card p-0 overflow-hidden lg:col-span-2">
            <div className="afj-section-header flex items-center justify-between px-4 pt-4">
              <span className="flex items-center gap-2"><Scale size={16} className="text-afj-gold" /> Meus processos ({processos.length})</span>
              <Link href="/processos" className="text-xs text-afj-gold hover:underline flex items-center gap-0.5">Todos os processos <ChevronRight size={12} /></Link>
            </div>
            {processos.length === 0 ? (
              <div className="px-4 pb-6 text-center">
                <Users2 className="mx-auto text-afj-black/20 mb-2" size={32} />
                <p className="text-sm text-afj-black/50 font-medium">Você ainda não é responsável ou membro da equipe de nenhum processo.</p>
                <p className="text-xs text-afj-black/35 mt-1">Peça ao responsável para incluí-lo na equipe pelo detalhe do processo (card &quot;Equipe do Processo&quot;).</p>
              </div>
            ) : (
              <div className="table-responsive">
                <table className="afj-table w-full">
                  <thead>
                    <tr>
                      <th>Processo</th>
                      <th>Área</th>
                      <th>Situação</th>
                      <th>Meu papel</th>
                      <th className="hidden md:table-cell">Próximo prazo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {processos.slice(0, 15).map((p) => {
                      const souResp = p.responsavel_id === user?.id;
                      return (
                        <tr key={p.id}>
                          <td>
                            <Link href={`/processos/${p.id}`} className="text-afj-gold hover:underline font-medium">
                              {p.numero_cnj || p.numero_original || "Sem número"}
                            </Link>
                            <p className="text-xs text-afj-black/40 mt-0.5">{p.tribunal}{p.parte_contraria ? ` · vs ${p.parte_contraria}` : ""}</p>
                          </td>
                          <td className="text-sm text-afj-black/60">{p.area_direito || "—"}</td>
                          <td>
                            <span className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-sm border ${SITUACAO_BADGE[p.situacao] ?? "bg-gray-50 text-gray-500 border-gray-200"}`}>{p.situacao}</span>
                          </td>
                          <td>
                            <span className={`text-xs ${souResp ? "text-afj-gold font-semibold" : "text-afj-black/50"}`}>{souResp ? "Responsável" : "Colaborador"}</span>
                          </td>
                          <td className="hidden md:table-cell text-sm text-afj-black/60">
                            {p.proximo_prazo_at ? new Date(p.proximo_prazo_at).toLocaleDateString("pt-BR") : "—"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
