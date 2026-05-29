"use client";
import { useState } from "react";
import { AlertCircle, Eye, EyeOff } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL
  ? `${process.env.NEXT_PUBLIC_API_URL}/api/v1`
  : "/api/v1";

function AfjMonogram({ size = 80 }: { size?: number }) {
  return (
    <svg viewBox="0 0 80 80" width={size} height={size} fill="currentColor" aria-hidden="true">
      <rect x="2" y="2" width="76" height="76" fill="none" stroke="currentColor" strokeWidth="3.5" />
      <rect x="10" y="10" width="6" height="60" />
      <rect x="29" y="10" width="6" height="60" />
      <rect x="10" y="37" width="25" height="5" />
      <rect x="43" y="10" width="6" height="42" />
      <rect x="43" y="10" width="25" height="5" />
      <rect x="43" y="27" width="19" height="5" />
      <rect x="62" y="10" width="6" height="46" />
      <path d="M68,56 Q68,70 55,70 Q49,70 49,63" fill="none" stroke="currentColor" strokeWidth="6" strokeLinecap="round" />
    </svg>
  );
}

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      if (!res.ok) {
        const data = await res.json();
        setError(data.detail || "Credenciais inválidas. Verifique e-mail e senha.");
        return;
      }

      const data = await res.json();
      localStorage.setItem("afj_access_token", data.access_token);
      localStorage.setItem("afj_refresh_token", data.refresh_token);
      localStorage.setItem("afj_user", JSON.stringify(data.user));

      await fetch("/api/auth/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "set" }),
      });

      window.location.href = "/dashboard";
    } catch {
      setError("Erro de conexão com o servidor. Verifique a disponibilidade do backend.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex">
      {/* Painel esquerdo — identidade visual AFJ (desktop only) */}
      <div className="hidden lg:flex lg:w-2/5 bg-afj-navy flex-col items-center justify-center p-12 relative overflow-hidden select-none">
        <div
          className="absolute inset-0 opacity-[0.035]"
          style={{ backgroundImage: `repeating-linear-gradient(45deg, #B8954A 0px, #B8954A 1px, transparent 1px, transparent 14px)` }}
        />
        <div className="absolute right-0 top-0 bottom-0 w-px bg-gradient-to-b from-transparent via-afj-gold/30 to-transparent" />

        <div className="relative z-10 flex flex-col items-center text-center">
          <div className="text-afj-gold mb-8">
            <AfjMonogram size={96} />
          </div>

          <p className="font-display text-afj-cream/30 text-[9px] tracking-[0.4em] uppercase mb-3">
            Escritório de Advocacia
          </p>
          <h1 className="font-display text-afj-cream font-semibold tracking-[0.1em] uppercase leading-snug text-[1.6rem]">
            Almeida, Freire<br />&amp; Jucá
          </h1>
          <p className="text-afj-cream/35 tracking-[0.28em] uppercase text-[10px] mt-1.5 font-display">
            Advogados
          </p>

          <div className="w-20 h-px bg-gradient-to-r from-transparent via-afj-gold to-transparent my-8" />

          <p className="text-afj-cream/45 text-sm text-center max-w-[220px] leading-relaxed">
            Sistema Jurídico com<br />Inteligência Artificial
          </p>

          <div className="mt-12 flex flex-col items-center gap-1.5 text-afj-cream/20 text-[9px] tracking-widest uppercase">
            <span>AFJ CORE SYSTEM v1.0</span>
            <span>Sistema Interno · Acesso Restrito</span>
          </div>
        </div>
      </div>

      {/* Painel direito — formulário */}
      <div className="flex-1 flex items-center justify-center p-6 bg-afj-cream">
        <div className="w-full max-w-sm">
          {/* Logo mobile */}
          <div className="lg:hidden flex flex-col items-center mb-8">
            <div className="text-afj-gold mb-4">
              <AfjMonogram size={56} />
            </div>
            <p className="font-display text-afj-black font-semibold tracking-[0.1em] uppercase text-lg">
              Almeida, Freire &amp; Jucá
            </p>
            <p className="text-afj-black/40 text-[10px] tracking-widest uppercase mt-0.5">Advogados</p>
          </div>

          <div className="bg-white border border-afj-cream-dark rounded-sm shadow-sm p-8 animate-fade-in">
            <h2 className="font-display text-2xl font-semibold text-afj-black mb-1">
              Acesso ao Sistema
            </h2>
            <p className="text-afj-black/40 text-sm mb-6">
              Bem-vindo de volta. Insira suas credenciais.
            </p>

            <div className="h-px bg-gradient-to-r from-afj-gold/60 via-afj-gold/20 to-transparent mb-6" />

            <form onSubmit={handleSubmit} className="space-y-4" noValidate>
              <div>
                <label htmlFor="email" className="block text-[10px] font-semibold text-afj-black/55 mb-1.5 uppercase tracking-widest">
                  E-mail
                </label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoComplete="email"
                  placeholder="seu@afj.adv.br"
                  className="w-full bg-afj-cream border border-afj-cream-dark text-afj-black rounded-sm px-4 py-2.5 text-sm placeholder:text-afj-black/25 focus:outline-none focus:border-afj-gold focus:bg-white transition-colors"
                />
              </div>

              <div>
                <label htmlFor="password" className="block text-[10px] font-semibold text-afj-black/55 mb-1.5 uppercase tracking-widest">
                  Senha
                </label>
                <div className="relative">
                  <input
                    id="password"
                    type={showPwd ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    autoComplete="current-password"
                    placeholder="••••••••"
                    className="w-full bg-afj-cream border border-afj-cream-dark text-afj-black rounded-sm px-4 py-2.5 pr-11 text-sm placeholder:text-afj-black/25 focus:outline-none focus:border-afj-gold focus:bg-white transition-colors"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPwd((v) => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-afj-black/30 hover:text-afj-black/60 transition-colors"
                    aria-label={showPwd ? "Ocultar senha" : "Mostrar senha"}
                  >
                    {showPwd ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </div>

              {error && (
                <div className="flex items-start gap-2.5 text-red-700 bg-red-50 border border-red-200 rounded-sm px-3 py-2.5 animate-fade-in">
                  <AlertCircle size={14} className="flex-shrink-0 mt-0.5" />
                  <p className="text-xs leading-relaxed">{error}</p>
                </div>
              )}

              <button
                type="submit"
                disabled={loading || !email || !password}
                className="w-full btn-afj-primary py-3 rounded-sm mt-2 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {loading ? (
                  <>
                    <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Entrando...
                  </>
                ) : (
                  "Entrar"
                )}
              </button>
            </form>
          </div>

          <p className="text-center text-afj-black/20 text-[9px] mt-5 tracking-widest uppercase">
            Sistema Interno · Acesso Restrito
          </p>
        </div>
      </div>
    </div>
  );
}
