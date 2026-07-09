"use client";
import {
  ShieldCheck, CheckCircle2, Clock, Scale, Shield, Users2, FileSearch,
  Lock, AlertTriangle, BookOpenCheck, Megaphone, GraduationCap, ClipboardCheck,
} from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";

// ─── Pilares já ativos no sistema (controles reais em produção) ───────────────
const PILARES_ATIVOS = [
  {
    icon: Users2, titulo: "Supervisão Humana (HITL)",
    desc: "Nenhuma ação crítica da IA (protocolar petição, assinar contrato, enviar email) é executada sem aprovação humana. Rejeições exigem justificativa registrada.",
  },
  {
    icon: FileSearch, titulo: "Auditoria Imutável",
    desc: "Todas as ações relevantes do sistema geram registro de auditoria com autor, data e resultado — base para prestação de contas e investigações internas.",
  },
  {
    icon: Lock, titulo: "Isolamento entre Escritórios",
    desc: "Dados de processos, clientes, finanças e conhecimento (RAG) são estritamente separados por escritório em todas as consultas.",
  },
  {
    icon: Shield, titulo: "LGPD e Consentimento",
    desc: "Controle de consentimento por cliente, com monitoramento de pendências pelo agente de compliance.",
  },
  {
    icon: Scale, titulo: "Ética OAB no Marketing",
    desc: "O agente de compliance verifica materiais de marketing jurídico contra o Código de Ética da OAB antes da veiculação.",
  },
  {
    icon: BookOpenCheck, titulo: "Citações Verificáveis",
    desc: "Petições geradas por IA usam apenas jurisprudência das bases verificadas; citações não confirmadas são marcadas e bloqueiam aprovação automática.",
  },
];

// ─── Programa de Integridade — plano futuro ───────────────────────────────────
const PROGRAMA_PLANEJADO = [
  {
    icon: BookOpenCheck, titulo: "Código de Conduta",
    desc: "Documento formal com padrões de comportamento, conflitos de interesse e uso responsável de IA, com aceite registrado por usuário.",
  },
  {
    icon: Megaphone, titulo: "Canal de Denúncias",
    desc: "Canal confidencial (com opção anônima) para relatos de violações éticas, com fluxo de tratamento e prazos.",
  },
  {
    icon: AlertTriangle, titulo: "Matriz de Riscos de Integridade",
    desc: "Mapeamento periódico de riscos (corrupção, vazamento de dados, conflito de interesses, mau uso de IA) com controles e responsáveis.",
  },
  {
    icon: GraduationCap, titulo: "Treinamentos Obrigatórios",
    desc: "Trilhas de ética, LGPD e uso responsável de IA, com registro de conclusão e reciclagem anual.",
  },
  {
    icon: Users2, titulo: "Comitê de Integridade",
    desc: "Instância responsável por avaliar casos, aprovar políticas e reportar à sociedade de advogados.",
  },
  {
    icon: ClipboardCheck, titulo: "Revisão Periódica de Acessos",
    desc: "Recertificação trimestral de permissões e papéis, com desativação automática de acessos ociosos.",
  },
];

export default function EticaPage() {
  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Ética & Integridade" }]} />

      <div className="afj-page-header">
        <div>
          <h1 className="afj-page-title flex items-center gap-2">
            <ShieldCheck size={22} className="text-afj-gold" /> Plano de Ética, Controle e Integridade
          </h1>
          <p className="text-afj-black/45 text-sm mt-1">
            Programa de integridade do escritório: os controles já ativos no sistema e o plano de evolução.
          </p>
        </div>
      </div>

      {/* Pilares ativos */}
      <div>
        <h2 className="afj-section-header flex items-center gap-2">
          <CheckCircle2 size={15} className="text-green-600" /> Controles em operação
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
          {PILARES_ATIVOS.map((p) => {
            const Icon = p.icon;
            return (
              <div key={p.titulo} className="afj-card p-4 border-l-2 border-green-400/60">
                <p className="font-semibold text-afj-black text-sm flex items-center gap-2">
                  <Icon size={15} className="text-afj-gold" /> {p.titulo}
                </p>
                <p className="text-xs text-afj-black/55 mt-1.5 leading-relaxed">{p.desc}</p>
              </div>
            );
          })}
        </div>
      </div>

      {/* Programa planejado */}
      <div>
        <h2 className="afj-section-header flex items-center gap-2">
          <Clock size={15} className="text-afj-gold" /> Programa de Integridade — plano futuro
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
          {PROGRAMA_PLANEJADO.map((p) => {
            const Icon = p.icon;
            return (
              <div key={p.titulo} className="afj-card p-4 border-l-2 border-afj-gold/40">
                <p className="font-semibold text-afj-black text-sm flex items-center gap-2">
                  <Icon size={15} className="text-afj-gold" /> {p.titulo}
                  <span className="text-[10px] uppercase tracking-wider text-afj-black/35 font-normal">Planejado</span>
                </p>
                <p className="text-xs text-afj-black/55 mt-1.5 leading-relaxed">{p.desc}</p>
              </div>
            );
          })}
        </div>
      </div>

      <p className="text-[11px] text-afj-black/35 text-center">
        Este plano evolui por fases. Sugestões de novos controles podem ser encaminhadas ao administrador do escritório.
      </p>
    </div>
  );
}
