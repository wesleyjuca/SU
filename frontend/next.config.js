/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: { ignoreBuildErrors: true },
  eslint: { ignoreDuringBuilds: true },
  // "standalone" is for Docker; Vercel sets VERCEL=1 and handles output itself
  ...(process.env.VERCEL ? {} : { output: "standalone" }),
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
