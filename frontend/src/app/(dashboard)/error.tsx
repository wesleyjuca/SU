"use client";

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4 text-center">
      <p className="text-afj-black font-display text-2xl font-semibold">Algo deu errado</p>
      <p className="text-afj-black/50 text-sm max-w-sm">{error.message || "Ocorreu um erro inesperado."}</p>
      <button onClick={reset} className="btn-afj-primary rounded-md px-5 py-2 text-sm">
        Recarregar
      </button>
    </div>
  );
}
