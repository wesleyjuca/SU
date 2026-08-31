"use client";
import { Save, CheckCircle, Loader2 } from "lucide-react";

interface SettingsSaveButtonProps {
  onClick?: () => void;
  saving: boolean;
  saved: boolean;
  label?: string;
  savingLabel?: string;
  savedLabel?: string;
  disabled?: boolean;
  type?: "button" | "submit";
}

// Fase 256 — componente único de botão "salvar" pra área de
// Configurações (ver useSavedFlash.ts). Antes, cada aba de
// PersonalZone.tsx/EscritorioZone.tsx tinha sua própria versão à mão
// desse mesmo spinner→checkmark, cada uma ligeiramente diferente.
export function SettingsSaveButton({
  onClick,
  saving,
  saved,
  label = "Salvar",
  savingLabel = "Salvando...",
  savedLabel = "Salvo!",
  disabled,
  type = "button",
}: SettingsSaveButtonProps) {
  return (
    <button
      type={type}
      onClick={type === "button" ? onClick : undefined}
      disabled={saving || disabled}
      className="btn-afj-primary rounded-sm flex items-center gap-2 disabled:opacity-60"
    >
      {saving ? (
        <Loader2 size={14} className="animate-spin" />
      ) : saved ? (
        <CheckCircle size={14} />
      ) : (
        <Save size={14} />
      )}
      {saving ? savingLabel : saved ? savedLabel : label}
    </button>
  );
}
