"use client";
import { Plug, MessageCircle, PenTool, Clock, CheckCircle2, Smartphone } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";

// Base das integrações externas. Cada card descreve o recurso, o que já está
// pronto no sistema para recebê-lo e o que falta (credenciais/provedor).
const INTEGRACOES = [
  {
    icon: MessageCircle,
    titulo: "WhatsApp — Notificações",
    status: "planejado" as const,
    desc: "Alertas de prazos, andamentos processuais e cobranças enviados por WhatsApp para advogados e clientes.",
    prontos: [
      "Sistema de notificações interno (sino) já operacional",
      "Alertas de prazo já calculados pelo monitor de processos",
      "Portal do cliente com vínculo seguro por cliente",
    ],
    faltam: [
      "Conta WhatsApp Business API (Meta) ou provedor (ex.: Twilio)",
      "Credenciais no Railway (token + número verificado)",
      "Templates de mensagem aprovados pela Meta",
    ],
  },
  {
    icon: PenTool,
    titulo: "Assinatura Eletrônica de Contratos",
    status: "planejado" as const,
    desc: "Envio de contratos para assinatura eletrônica (ICP-Brasil ou assinatura simples) direto do fluxo de contratos.",
    prontos: [
      "Contratos com conteúdo/minuta e ciclo de vida completo",
      "Geração de PDF do documento",
      "Fila de aprovações (HITL) para envio controlado",
    ],
    faltam: [
      "Contrato com provedor (ex.: Clicksign, DocuSign, D4Sign)",
      "Credenciais/API key no Railway",
      "Webhook de retorno para atualizar o status do contrato",
    ],
  },
  {
    icon: Smartphone,
    titulo: "App Instalável (PWA)",
    status: "parcial" as const,
    desc: "Uso do AFJ CORE como aplicativo no celular/desktop, com ícone próprio e abertura em tela cheia.",
    prontos: [
      "Manifest e service worker publicados",
      "Ícones e tema configurados",
      "Instalável hoje: no navegador, use “Adicionar à tela inicial”",
    ],
    faltam: [
      "Modo offline ampliado (cache de consultas recentes)",
      "Notificações push nativas no dispositivo",
    ],
  },
];

export default function IntegracoesPage() {
  return (
    <div className="max-w-4xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Integrações" }]} />

      <div className="afj-page-header">
        <div>
          <h1 className="afj-page-title flex items-center gap-2">
            <Plug size={20} className="text-afj-gold" /> Integrações
          </h1>
          <p className="text-afj-black/45 text-sm mt-1">
            Conexões do AFJ CORE com serviços externos — o que já está pronto e o que falta para ativar.
          </p>
        </div>
      </div>

      <div className="space-y-4">
        {INTEGRACOES.map((it) => {
          const Icon = it.icon;
          const isParcial = it.status === "parcial";
          return (
            <div key={it.titulo} className="afj-card p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <span className="w-10 h-10 rounded-sm bg-afj-gold/10 flex items-center justify-center flex-shrink-0">
                    <Icon size={19} className="text-afj-gold" />
                  </span>
                  <div>
                    <p className="font-semibold text-afj-black text-sm">{it.titulo}</p>
                    <p className="text-xs text-afj-black/55 mt-0.5">{it.desc}</p>
                  </div>
                </div>
                <span className={`inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-sm border flex-shrink-0 ${
                  isParcial ? "bg-amber-50 text-amber-700 border-amber-200" : "bg-gray-50 text-gray-500 border-gray-200"
                }`}>
                  <Clock size={11} /> {isParcial ? "Em evolução" : "Planejado"}
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-4">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-green-700 mb-1.5">Já pronto no sistema</p>
                  <ul className="space-y-1">
                    {it.prontos.map((p) => (
                      <li key={p} className="flex gap-1.5 text-xs text-afj-black/60">
                        <CheckCircle2 size={12} className="text-green-500 flex-shrink-0 mt-0.5" /> {p}
                      </li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-afj-black/40 mb-1.5">Para ativar</p>
                  <ul className="space-y-1">
                    {it.faltam.map((f) => (
                      <li key={f} className="flex gap-1.5 text-xs text-afj-black/60">
                        <Clock size={12} className="text-afj-gold flex-shrink-0 mt-0.5" /> {f}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <p className="text-[11px] text-afj-black/35 text-center">
        Para ativar uma integração, providencie as credenciais do provedor e solicite a implementação da conexão.
      </p>
    </div>
  );
}
