"use client";
import { Scale, Link2 } from "lucide-react";

/** Fase 234 — o Portal do Cliente deixou de usar e-mail/senha (nenhum
 * caminho no sistema dá mais uma senha usável a um cliente): o acesso
 * agora é só via link temporário gerado pelo escritório em Controle de
 * Clientes. Esta rota é mantida (não apagada) porque `(portal)/
 * layout.tsx` (logout) e `portalApi.ts` (sessão expirada) já redirecionam
 * pra cá — vira só uma página informativa, sem formulário. */
export default function PortalLoginPage() {
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="w-full max-w-sm text-center">
        <div className="inline-flex items-center justify-center w-14 h-14 rounded-xl bg-[#B8954A]/10 mb-4">
          <Scale size={28} className="text-[#B8954A]" />
        </div>
        <h1 className="text-xl font-bold text-gray-900 mb-1">Portal do Cliente</h1>
        <p className="text-sm text-gray-500 mb-6">Sua sessão encerrou ou o link expirou.</p>

        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <Link2 size={22} className="text-[#B8954A] mx-auto mb-3" />
          <p className="text-sm text-gray-700 leading-relaxed">
            O acesso ao portal é feito por um link de acesso temporário,
            enviado pelo seu advogado — não existe mais login por senha.
          </p>
          <p className="text-sm text-gray-500 mt-3">
            Peça um novo link ao escritório.
          </p>
        </div>
      </div>
    </div>
  );
}
