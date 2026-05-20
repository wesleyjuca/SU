"use client";

export default function RootError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-afj-black p-4">
      <div className="text-center max-w-md">
        <p className="text-afj-gold font-display text-4xl font-bold mb-4">Erro</p>
        <p className="text-afj-cream/60 mb-6">{error.message || "Algo deu errado. Tente novamente."}</p>
        <button
          onClick={reset}
          className="btn-afj-primary rounded-md px-6 py-2"
        >
          Tentar novamente
        </button>
      </div>
    </div>
  );
}
