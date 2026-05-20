import Link from "next/link";

export default function RootNotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-afj-black p-4">
      <div className="text-center">
        <p className="text-afj-gold font-display text-6xl font-bold mb-4">404</p>
        <p className="text-afj-cream/60 mb-6">Página não encontrada.</p>
        <Link href="/dashboard" className="btn-afj-primary rounded-md px-6 py-2">
          Ir para o Dashboard
        </Link>
      </div>
    </div>
  );
}
