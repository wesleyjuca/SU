"use client";
export default function Error({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="afj-card p-8 text-center">
      <p className="text-red-600 font-semibold mb-3">Algo deu errado</p>
      <p className="text-afj-black/50 text-sm mb-4">{error.message}</p>
      <button onClick={reset} className="btn-afj-primary rounded-md text-sm px-4 py-2">
        Tentar novamente
      </button>
    </div>
  );
}
