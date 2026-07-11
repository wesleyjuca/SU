"use client";
import { useEffect, useState, useCallback } from "react";

export interface BillingStatus {
  status: string;              // ATIVO | INADIMPLENTE | SUSPENSO | ISENTO | NAO_CONFIGURADO
  valor_mensal: number | null;
  proximo_vencimento: string | null;
  dias_para_vencimento: number | null;
}

// Situação de cobrança do escritório do usuário logado. Alimenta o banner
// global (todos os usuários) e o bloco de assinatura no Plano & Uso.
export function useBilling() {
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchBilling = useCallback(async () => {
    try {
      const token = typeof window !== "undefined" ? localStorage.getItem("afj_access_token") : null;
      if (!token) return;
      const res = await fetch("/api/v1/tenant/billing", { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) setBilling(await res.json());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchBilling(); }, [fetchBilling]);

  return { billing, loading, refetch: fetchBilling };
}
