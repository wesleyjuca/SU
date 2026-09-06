"use client";
import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useUserStore } from "@/store";
import { rolesPermitidosPara } from "@/lib/nav";

// O guard consulta o MESMO registro que monta o menu (`nav.ts`), em vez de
// manter uma lista própria. A lista fixa anterior (`["ADMIN","SUPERADMIN"]`)
// divergia em duas telas: `/admin/relatorios-banca` é `["SUPERADMIN","ADMIN",
// "SOCIO"]` no menu e o backend (`reports_admin.py`) aceita SOCIO; e as rotas
// de `/admin/plano` (`tenant.py`) também aceitam SOCIO. O sócio via o item no
// menu e era redirecionado ao clicar.
//
// Rota fora do registro cai no padrão restritivo de antes — uma tela admin
// nova não nasce aberta por esquecimento.
const PADRAO_ADMIN = ["ADMIN", "SUPERADMIN"];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const user = useUserStore((s) => s.user);
  const pathname = usePathname();
  const router = useRouter();

  const permitidos = rolesPermitidosPara(pathname ?? "") ?? PADRAO_ADMIN;
  const autorizado = !!user && permitidos.includes(user.role);

  useEffect(() => {
    if (user && !autorizado) {
      router.replace("/dashboard");
    }
  }, [user, autorizado, router]);

  // Enquanto o usuário não resolve, não renderiza os filhos (evita que páginas
  // admin montem e disparem fetches antes do redirect para não-autorizados).
  if (!autorizado) {
    return null;
  }

  return <>{children}</>;
}
