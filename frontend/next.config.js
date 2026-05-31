/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: { ignoreBuildErrors: true },
  eslint: { ignoreDuringBuilds: true },
  // "standalone" is for Docker; Vercel sets VERCEL=1 and handles output itself
  ...(process.env.VERCEL ? {} : { output: "standalone" }),
  async rewrites() {
    const apiBase = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "https://su-production-5a83.up.railway.app";
    return [
      {
        source: "/api/v1/:path*",
        destination: `${apiBase}/api/v1/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
