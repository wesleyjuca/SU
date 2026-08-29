// Fase 248.3 — extrai só a peça de fato idêntica entre os 2 usos de
// status de integração (`integracoes/page.tsx` e `admin/health/page.tsx`):
// o mapeamento tom → cor. O resto (card do hub inteiro com connect/test/
// disconnect vs. `ModuleCard` de 6 linhas do health) não tem equivalente
// entre as 2 páginas — forçar um `<IntegrationCard>` genérico exigiria
// 10+ props opcionais de comportamento, a abstração não-usada que este
// projeto evita. Cada página mantém seu próprio vocabulário de status
// (`CONECTADA/ERRO/DESCONECTADA` no hub; os 6 valores de `ModuleStatus`
// no health) e só troca a marcação de cor duplicada por este componente.
//
// 2 variantes visuais, porque as 2 páginas já usavam 2 estilos genuinamente
// diferentes antes desta fase (não uma escolha nova) — unificar a cor sem
// forçar a mesma marcação evita uma regressão visual em qualquer uma delas:
//   - "pill": chip com borda+fundo+ícone (mesmo markup que já existia em
//     integracoes/page.tsx).
//   - "label": só o texto em caixa alta colorido (mesmo markup que já
//     existia no rodapé do ModuleCard em admin/health/page.tsx).
import type { LucideIcon } from "lucide-react";

export type StatusTone = "green" | "red" | "amber" | "gray" | "blue";

const TONE_CLASSES: Record<StatusTone, { bg: string; text: string; border: string }> = {
  green: { bg: "bg-green-50", text: "text-green-700", border: "border-green-200" },
  red: { bg: "bg-red-50", text: "text-red-700", border: "border-red-200" },
  amber: { bg: "bg-amber-50", text: "text-amber-700", border: "border-amber-200" },
  gray: { bg: "bg-gray-50", text: "text-gray-500", border: "border-gray-200" },
  blue: { bg: "bg-blue-50", text: "text-blue-700", border: "border-blue-200" },
};

interface StatusBadgeProps {
  tone: StatusTone;
  label: string;
  icon?: LucideIcon;
  variant?: "pill" | "label";
}

export function StatusBadge({ tone, label, icon: Icon, variant = "pill" }: StatusBadgeProps) {
  const c = TONE_CLASSES[tone];

  if (variant === "label") {
    return (
      <span className={`text-[10px] font-semibold uppercase tracking-wider ${c.text} inline-flex items-center gap-1`}>
        {Icon && <Icon size={11} />}
        {label}
      </span>
    );
  }

  return (
    <span
      className={`inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-sm border flex-shrink-0 ${c.bg} ${c.text} ${c.border}`}
    >
      {Icon && <Icon size={11} />}
      {label}
    </span>
  );
}
