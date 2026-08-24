"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Scale, Loader2, AlertCircle } from "lucide-react";

const API_BASE = "/api/v1";

/** Fase 234 — entrada do Portal do Cliente via link temporário gerado
 * pelo admin em Controle de Clientes (`/clientes?aba=controle-portal`),
 * substituindo o login por e-mail/senha. Troca o token da URL por uma
 * sessão real em `POST /portal/access/redeem`. */
export default function PortalAcessoPage() {
  const { token } = useParams<{ token: string }>();
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/auth/portal-redeem`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token }),
        });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          setErro(data.detail || "Link inválido ou expirado.");
          return;
        }
        const data = await res.json();
        localStorage.setItem("afj_portal_token", data.access_token);
        localStorage.setItem("afj_portal_refresh_token", data.refresh_token);
        localStorage.setItem("afj_portal_user", JSON.stringify(data.user));

        await fetch("/api/portal/session", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "set" }),
        });

        window.location.href = "/portal/dashboard";
      } catch {
        setErro("Erro ao conectar ao servidor. Verifique sua conexão.");
      }
    })();
  }, [token]);

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="w-full max-w-sm text-center">
        <div className="inline-flex items-center justify-center w-14 h-14 rounded-xl bg-[#B8954A]/10 mb-4">
          <Scale size={28} className="text-[#B8954A]" />
        </div>

        {erro ? (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
            <div className="flex items-start gap-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2.5 text-sm text-red-700 text-left">
              <AlertCircle size={15} className="mt-0.5 flex-shrink-0" />
              <span>{erro}</span>
            </div>
            <p className="text-xs text-gray-400 mt-4">
              Peça um novo link ao escritório.
            </p>
          </div>
        ) : (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8">
            <Loader2 className="animate-spin text-[#B8954A] mx-auto mb-3" size={24} />
            <p className="text-sm text-gray-500">Validando seu acesso...</p>
          </div>
        )}
      </div>
    </div>
  );
}
