"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useUserStore } from "@/store";

// Alinhado ao backend (_require_admin permite ADMIN/SUPERADMIN). SOCIO não é admin —
// deixá-lo entrar aqui só renderizava o shell e depois estourava 403 nas chamadas.
const ADMIN_ROLES = ["ADMIN", "SUPERADMIN"];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const user = useUserStore((s) => s.user);
  const router = useRouter();

  useEffect(() => {
    if (user && !ADMIN_ROLES.includes(user.role)) {
      router.replace("/dashboard");
    }
  }, [user, router]);

  // Enquanto o usuário não resolve, não renderiza os filhos (evita que páginas admin
  // montem e disparem fetches antes do redirect para não-admins).
  if (!user || !ADMIN_ROLES.includes(user.role)) {
    return null;
  }

  return <>{children}</>;
}
