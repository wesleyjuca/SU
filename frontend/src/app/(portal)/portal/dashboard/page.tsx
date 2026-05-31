"use client";
import { useState, useEffect } from "react";
import { Scale, FileText, DollarSign, Clock, ArrowRight } from "lucide-react";
import Link from "next/link";
import { portalApi } from "@/lib/portalApi";
import { useToast } from "@/components/ui/Toast";

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
  }, []);

  const today = new Date().toLocaleDateString("pt-BR", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
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

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-9 h-9 rounded-lg bg-blue-50 flex items-center justify-center">
              <Scale size={18} className="text-blue-600" />
            </div>
            <p className="text-sm font-medium text-gray-600">Processos Ativos</p>
          </div>
          <p className="text-3xl font-bold text-gray-900">{summary?.active_processes ?? 0}</p>
          <Link href="/portal/processos" className="text-xs text-blue-600 hover:underline flex items-center gap-1 mt-2">
            Ver processos <ArrowRight size={11} />
          </Link>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-9 h-9 rounded-lg bg-green-50 flex items-center justify-center">
              <FileText size={18} className="text-green-600" />
            </div>
            <p className="text-sm font-medium text-gray-600">Documentos</p>
          </div>
          <p className="text-3xl font-bold text-gray-900">{summary?.available_docs ?? 0}</p>
          <Link href="/portal/documentos" className="text-xs text-green-600 hover:underline flex items-center gap-1 mt-2">
            Ver documentos <ArrowRight size={11} />
          </Link>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-9 h-9 rounded-lg bg-amber-50 flex items-center justify-center">
              <DollarSign size={18} className="text-amber-600" />
            </div>
            <p className="text-sm font-medium text-gray-600">Saldo Pendente</p>
          </div>
          <p className="text-2xl font-bold text-gray-900">{formatBRL(summary?.outstanding_total ?? 0)}</p>
          <Link href="/portal/financeiro" className="text-xs text-amber-600 hover:underline flex items-center gap-1 mt-2">
            Ver financeiro <ArrowRight size={11} />
          </Link>
        </div>
      </div>

      {/* Quick actions */}
      <div>
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-3">Acesso Rápido</h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { href: "/portal/processos", label: "Meus Processos", icon: Scale, color: "text-blue-600 bg-blue-50" },
            { href: "/portal/documentos", label: "Documentos", icon: FileText, color: "text-green-600 bg-green-50" },
            { href: "/portal/financeiro", label: "Financeiro", icon: DollarSign, color: "text-amber-600 bg-amber-50" },
            { href: "/portal/processos", label: "Próximos Prazos", icon: Clock, color: "text-purple-600 bg-purple-50" },
          ].map(({ href, label, icon: Icon, color }) => (
            <Link
              key={label}
              href={href}
              className="bg-white rounded-xl border border-gray-200 p-4 flex flex-col items-center gap-2 text-center hover:border-[#B8954A]/40 hover:shadow-sm transition-all"
            >
              <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${color}`}>
                <Icon size={20} />
              </div>
              <span className="text-xs font-medium text-gray-700">{label}</span>
            </Link>
          ))}
        </div>
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
