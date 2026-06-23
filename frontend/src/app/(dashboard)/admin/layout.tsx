"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useUserStore } from "@/store";

const ADMIN_ROLES = ["ADMIN", "SOCIO"];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const user = useUserStore((s) => s.user);
  const router = useRouter();

  useEffect(() => {
    if (user && !ADMIN_ROLES.includes(user.role)) {
      router.replace("/dashboard");
    }
  }, [user, router]);

  if (user && !ADMIN_ROLES.includes(user.role)) {
    return null;
  }

  return <>{children}</>;
}
