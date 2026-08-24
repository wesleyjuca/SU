"use client";
import { useState, useEffect } from "react";
import { Scale, FileText, DollarSign } from "lucide-react";
import { portalApi } from "@/lib/portalApi";
import { useToast } from "@/components/ui/Toast";
import { ProcessosSection } from "@/components/portal/ProcessosSection";
import { DocumentosSection } from "@/components/portal/DocumentosSection";
import { FinanceiroSection } from "@/components/portal/FinanceiroSection";
import { MensagensSection } from "@/components/portal/MensagensSection";

interface PortalSummary {
  active_processes: number;
  available_docs: number;
  outstanding_total: number;
}

interface PortalMe {
  full_name: string;
  client: { nome_completo: string; tipo: string; status: string } | null;
}

function formatBRL(value: number) {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);
}

/** Fase 233 — usuário pediu "o portal do cliente deve conter somente um
 * dashboard com toda a sua situação processual". O portal virou uma
 * única tela: processos (sempre visível, seção principal) + documentos/
 * financeiro/mensagens (cartões colapsáveis abaixo) — sem navegação por
 * abas separadas. As 5 rotas antigas (`/portal/processos[/id]`,
 * `/portal/documentos`, `/portal/financeiro`, `/portal/mensagens`)
 * deixaram de existir; os mesmos endpoints de `portal.py` seguem sendo
 * usados, só que por componentes desta página em vez de páginas soltas. */
export default function PortalDashboardPage() {
  const toast = useToast();
  const [me, setMe] = useState<PortalMe | null>(null);
  const [summary, setSummary] = useState<PortalSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [meData, sumData] = await Promise.all([
          portalApi.get<PortalMe>("/portal/me"),
          portalApi.get<PortalSummary>("/portal/summary"),
        ]);
        setMe(meData);
        setSummary(sumData);
      } catch {
        toast.error("Erro ao carregar dados do portal.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [toast]);

  const today = new Date().toLocaleDateString("pt-BR", {
    weekday: "long", day: "numeric", month: "long", year: "numeric",
  });

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-64 bg-gray-200 rounded animate-pulse" />
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-white rounded-xl border border-gray-200 p-5 h-24 animate-pulse bg-gray-100/50" />
          ))}
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-5 h-40 animate-pulse" />
      </div>
    );
  }

  const clientName = me?.client?.nome_completo ?? me?.full_name ?? "Cliente";

  return (
    <div className="space-y-8">
      {/* Welcome */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Olá, {clientName.split(" ")[0]}</h1>
        <p className="text-sm text-gray-500 mt-0.5 capitalize">{today}</p>
      </div>

      {/* Stats — resumo visual, sem link (só 1 página no portal agora) */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-9 h-9 rounded-lg bg-blue-50 flex items-center justify-center">
              <Scale size={18} className="text-blue-600" />
            </div>
            <p className="text-sm font-medium text-gray-600">Processos Ativos</p>
          </div>
          <p className="text-3xl font-bold text-gray-900">{summary?.active_processes ?? 0}</p>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-9 h-9 rounded-lg bg-green-50 flex items-center justify-center">
              <FileText size={18} className="text-green-600" />
            </div>
            <p className="text-sm font-medium text-gray-600">Documentos</p>
          </div>
          <p className="text-3xl font-bold text-gray-900">{summary?.available_docs ?? 0}</p>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-9 h-9 rounded-lg bg-amber-50 flex items-center justify-center">
              <DollarSign size={18} className="text-amber-600" />
            </div>
            <p className="text-sm font-medium text-gray-600">Saldo Pendente</p>
          </div>
          <p className="text-2xl font-bold text-gray-900">{formatBRL(summary?.outstanding_total ?? 0)}</p>
        </div>
      </div>

      {/* Situação processual — seção principal, sempre visível */}
      <div>
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-3">Situação Processual</h2>
        <ProcessosSection />
      </div>

      {/* Demais seções — colapsáveis, fechadas por padrão */}
      <div className="space-y-3">
        <DocumentosSection />
        <FinanceiroSection />
        <MensagensSection />
      </div>

      {/* Client info */}
      {me?.client && (
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-3">Seus Dados</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
            <div>
              <p className="text-xs text-gray-400 uppercase tracking-wide">Nome</p>
              <p className="font-medium text-gray-800 mt-0.5">{me.client.nome_completo}</p>
            </div>
            <div>
              <p className="text-xs text-gray-400 uppercase tracking-wide">Tipo</p>
              <p className="font-medium text-gray-800 mt-0.5">{me.client.tipo === "PF" ? "Pessoa Física" : "Pessoa Jurídica"}</p>
            </div>
            <div>
              <p className="text-xs text-gray-400 uppercase tracking-wide">Status</p>
              <span className={`inline-block text-xs font-medium px-2 py-0.5 rounded-full mt-0.5 ${
                me.client.status === "ATIVO" ? "bg-green-100 text-green-700" :
                me.client.status === "PROSPECTO" ? "bg-blue-100 text-blue-700" :
                "bg-gray-100 text-gray-600"
              }`}>
                {me.client.status}
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
