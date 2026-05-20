import Link from "next/link";

export default function DashboardNotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4 text-center">
      <p className="text-afj-black font-display text-5xl font-bold">404</p>
      <p className="text-afj-black/50 text-sm">Página não encontrada.</p>
      <Link href="/dashboard" className="btn-afj-primary rounded-md px-5 py-2 text-sm">
        Voltar ao Dashboard
      </Link>
    </div>
  );
}
