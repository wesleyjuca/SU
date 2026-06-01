"use client";

import { useEffect } from "react";
import { AlertCircle } from "lucide-react";

export default function AuthError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // eslint-disable-next-line no-console
    console.error("auth_error_boundary", error);
  }, [error]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-afj-cream p-6">
      <div className="w-full max-w-sm bg-white border-t-2 border-afj-gold border border-afj-cream-dark rounded-sm shadow-sm p-8 text-center">
        <div className="flex justify-center mb-4 text-red-600">
          <AlertCircle size={32} />
        </div>
        <h2 className="font-display text-xl font-semibold text-afj-black mb-1">
          Algo deu errado
        </h2>
        <p className="text-afj-black/50 text-sm mb-6">
          Não foi possível carregar a página de acesso. Tente novamente em instantes.
        </p>
        <button
          onClick={reset}
          className="w-full btn-afj-primary py-3 rounded-sm"
        >
          Tentar novamente
        </button>
      </div>
    </div>
  );
}
