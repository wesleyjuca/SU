import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AFJ CORE SYSTEM — Almeida, Freire & Jucá Advogados",
  description: "Sistema Jurídico Inteligente com IA Multiagente",
  robots: "noindex, nofollow", // sistema interno
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" suppressHydrationWarning>
      <body className="min-h-screen bg-afj-cream">{children}</body>
    </html>
  );
}
