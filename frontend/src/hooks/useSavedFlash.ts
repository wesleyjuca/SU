"use client";
import { useCallback, useState } from "react";
import { useToast } from "@/components/ui/Toast";

// Fase 256 — padroniza o padrão "botão salvar com spinner/checkmark +
// confirmação" que estava reimplementado à mão ~10+ vezes entre
// PersonalZone.tsx e EscritorioZone.tsx, com 2 mecanismos de feedback
// diferentes (uns só trocavam o texto do botão, outros usavam toast,
// alguns misturavam os dois na mesma tela). `run()` sempre dispara o
// toast — sucesso com a mensagem passada, erro com `err.message` (que
// os call sites devem popular com o `detail` real da API quando
// existir, não um texto genérico) — e o hook mantém `saving`/`saved`
// pro botão mostrar o estado visual junto.
export function useSavedFlash(durationMs = 2500) {
  const toast = useToast();
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const run = useCallback(
    async (action: () => Promise<void>, successMessage?: string) => {
      setSaving(true);
      try {
        await action();
        setSaved(true);
        if (successMessage) toast.success(successMessage);
        setTimeout(() => setSaved(false), durationMs);
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Erro ao salvar. Tente novamente.");
        throw err;
      } finally {
        setSaving(false);
      }
    },
    [toast, durationMs]
  );

  return { saving, saved, run };
}
