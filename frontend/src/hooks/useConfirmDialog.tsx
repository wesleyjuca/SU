"use client";
import { useCallback, useState } from "react";

// Fase 241 (achado do diagnóstico de cadastros) — `window.confirm()`/
// `window.prompt()` eram usados em 11 pontos sensíveis do produto
// (revogar acesso ao portal, rejeitar agente de IA, desconectar
// integração, arquivar/restaurar documento, excluir parte de processo,
// ativar modo produção do tenant, excluir usuário, motivo de oportunidade
// perdida...) — inconsistente com o resto do design system, que usa
// modais próprios pra tudo. Hook único, baseado em Promise, pra manter o
// fluxo `if (!(await ask(...))) return;` bem parecido com o `confirm()`
// nativo que substitui, minimizando o diff em cada call site.

interface AskOptions {
  title?: string;
  message: string;
  danger?: boolean;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Quando definido, mostra um textarea — o valor digitado (ou "" se
   * opcional e deixado em branco) é devolvido junto da confirmação. */
  reasonLabel?: string;
  reasonRequired?: boolean;
}

interface AskState extends AskOptions {
  resolve: (value: string | null) => void;
}

export function useConfirmDialog() {
  const [state, setState] = useState<AskState | null>(null);
  const [reasonValue, setReasonValue] = useState("");

  /** Devolve `null` se cancelado, ou uma string (vazia quando não há
   * `reasonLabel`) se confirmado. */
  const ask = useCallback((opts: AskOptions) => {
    return new Promise<string | null>((resolve) => {
      setReasonValue("");
      setState({ ...opts, resolve });
    });
  }, []);

  function handleConfirm() {
    if (!state) return;
    if (state.reasonRequired && !reasonValue.trim()) return;
    state.resolve(state.reasonLabel ? reasonValue.trim() : "");
    setState(null);
  }

  function handleCancel() {
    if (!state) return;
    state.resolve(null);
    setState(null);
  }

  const confirmDialog = state ? (
    <div className="fixed inset-0 bg-black/50 z-[60] flex items-center justify-center p-4">
      <div className="bg-white rounded-sm shadow-xl w-full max-w-md">
        <div className="p-5 space-y-3">
          <h2 className="font-semibold text-afj-black">{state.title ?? "Confirmar ação"}</h2>
          <p className="text-sm text-afj-black/70 whitespace-pre-line">{state.message}</p>
          {state.reasonLabel && (
            <div>
              <label className="text-xs text-afj-black/60 block mb-1">
                {state.reasonLabel}{state.reasonRequired ? " *" : " (opcional)"}
              </label>
              <textarea
                autoFocus
                rows={3}
                value={reasonValue}
                onChange={(e) => setReasonValue(e.target.value)}
                className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
              />
            </div>
          )}
        </div>
        <div className="flex gap-2 justify-end px-5 pb-5">
          <button onClick={handleCancel} className="btn-afj-outline text-sm py-2 px-4 rounded-sm">
            {state.cancelLabel ?? "Cancelar"}
          </button>
          <button
            onClick={handleConfirm}
            disabled={Boolean(state.reasonRequired) && !reasonValue.trim()}
            className={`text-sm py-2 px-4 rounded-sm disabled:opacity-50 ${
              state.danger ? "bg-red-600 hover:bg-red-700 text-white" : "btn-afj-primary"
            }`}
          >
            {state.confirmLabel ?? "Confirmar"}
          </button>
        </div>
      </div>
    </div>
  ) : null;

  return { ask, confirmDialog };
}
