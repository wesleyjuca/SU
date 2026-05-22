"use client";
import { useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL
  ? `${process.env.NEXT_PUBLIC_API_URL}/api/v1`
  : "/api/v1";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
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
        setError(data.detail || "Credenciais inválidas");
        return;
      }

      const data = await res.json();
      localStorage.setItem("afj_access_token", data.access_token);
      localStorage.setItem("afj_refresh_token", data.refresh_token);
      localStorage.setItem("afj_user", JSON.stringify(data.user));

      // Set session cookie via server-side route handler (reliable in all environments)
      await fetch("/api/auth/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "set" }),
      });

      window.location.href = "/dashboard";
    } catch {
      const backendLabel = process.env.NEXT_PUBLIC_API_URL || "/api/v1 (proxy)";
      setError(`Erro de conexão com o servidor (${backendLabel}). Verifique se o backend está acessível ou configure NEXT_PUBLIC_API_URL.`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-afj-black flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-afj-gold/10 border border-afj-gold/30 mb-4">
            <span className="text-afj-gold font-display text-2xl font-bold">AFJ</span>
          </div>
          <h1 className="font-display text-3xl text-afj-cream font-semibold">
            Almeida, Freire &amp; Jucá
          </h1>
          <p className="text-afj-cream/50 mt-1 text-sm">Sistema Jurídico Inteligente</p>
        </div>

        <div className="bg-afj-black-soft border border-afj-charcoal rounded-xl p-8">
          <h2 className="font-display text-xl text-afj-cream mb-6">Acesso ao sistema</h2>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="email" className="block text-sm text-afj-cream/60 mb-1.5">E-mail</label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="seu@afj.adv.br"
                className="w-full bg-afj-black border border-afj-charcoal text-afj-cream rounded-md px-4 py-2.5 text-sm
                           placeholder:text-afj-cream/30 focus:outline-none focus:border-afj-gold transition-colors"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm text-afj-cream/60 mb-1.5">Senha</label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                placeholder="••••••••"
                className="w-full bg-afj-black border border-afj-charcoal text-afj-cream rounded-md px-4 py-2.5 text-sm
                           placeholder:text-afj-cream/30 focus:outline-none focus:border-afj-gold transition-colors"
              />
            </div>

            {error && (
              <p className="text-red-400 text-sm bg-red-900/20 border border-red-800 rounded-md px-3 py-2">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full btn-afj-primary py-3 rounded-md font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? "Entrando..." : "Entrar"}
            </button>
          </form>
        </div>

        <p className="text-center text-afj-cream/20 text-xs mt-6">
          AFJ CORE SYSTEM v1.0 · Sistema interno · Acesso restrito
        </p>
      </div>
    </div>
  );
}
