/** @type {import('next').NextConfig} */
const nextConfig = {
  // TS agora É gate no build (tsc roda no CI e aqui) — só o eslint fica fora.
  typescript: { ignoreBuildErrors: false },
  eslint: { ignoreDuringBuilds: true },
  // "standalone" is for Docker; Vercel sets VERCEL=1 and handles output itself
  ...(process.env.VERCEL ? {} : { output: "standalone" }),
  async rewrites() {
    // Um override explícito sempre vence.
    // Em preview de PR no Vercel, aponta para o backend do PR (Railway cria
    // su-su-pr-{N}) — evita testar features novas contra o backend de produção
    // (que ainda não tem os endpoints do PR → "NOT FOUND"). Caso contrário,
    // produção.
    const prNumber = process.env.VERCEL_GIT_PULL_REQUEST_ID;
    const previewBackend =
      process.env.VERCEL_ENV === "preview" && prNumber
        ? `https://su-su-pr-${prNumber}.up.railway.app`
        : null;
    const apiBase =
      process.env.API_URL ||
      process.env.NEXT_PUBLIC_API_URL ||
      previewBackend ||
      "https://su-production-4561.up.railway.app";
    return [
      {
        source: "/api/v1/:path*",
        destination: `${apiBase}/api/v1/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
