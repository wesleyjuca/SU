"use client";
import { AlertTriangle, AlertCircle, Info } from "lucide-react";

// Banner de aviso full-width para o topo do dashboard. Reaproveita as cores de
// aviso do Toast (amber/red). Usado para cobrança (inadimplência/suspensão) e,
// desde a Fase 199, para o aviso de "modo demonstração" (variant "info").
const VARIANTS = {
  warning: { cls: "bg-amber-50 border-amber-200 text-amber-800", Icon: AlertTriangle },
  danger: { cls: "bg-red-50 border-red-200 text-red-800", Icon: AlertCircle },
  info: { cls: "bg-blue-50 border-blue-200 text-blue-800", Icon: Info },
} as const;

export type AlertVariant = keyof typeof VARIANTS;

export function AlertBanner({
  variant, children,
}: {
  variant: AlertVariant;
  children: React.ReactNode;
}) {
  const { cls, Icon } = VARIANTS[variant];
  return (
    <div role="alert" className={`flex items-center gap-2.5 px-4 md:px-6 py-2.5 border-b text-sm ${cls}`}>
      <Icon size={16} className="flex-shrink-0" />
      <span>{children}</span>
    </div>
  );
}
