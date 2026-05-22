import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "@/components/providers/ThemeProvider";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "AFJ CORE SYSTEM — Almeida, Freire & Jucá Advogados",
  description: "Sistema Jurídico Inteligente com IA Multiagente",
  robots: "noindex, nofollow",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" suppressHydrationWarning className={inter.variable}>
      <body className="min-h-screen bg-afj-cream">
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
