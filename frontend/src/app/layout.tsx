import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "@/components/providers/ThemeProvider";
import { ServiceWorkerProvider } from "@/components/providers/ServiceWorkerProvider";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "AFJ CORE SYSTEM — Almeida, Freire & Jucá Advogados",
  description: "Sistema Jurídico Inteligente com IA Multiagente",
  robots: "noindex, nofollow",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "AFJ CORE",
  },
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "any" },
      { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180" }],
    shortcut: ["/favicon.ico"],
  },
};

export const viewport: Viewport = {
  themeColor: "#B8954A",
  width: "device-width",
  initialScale: 1,
  // Necessário para env(safe-area-inset-*) funcionar em iPhones com notch —
  // sem isto o BottomNav fica sob o indicador de home.
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" suppressHydrationWarning className={inter.variable}>
      <body className="min-h-screen bg-afj-cream">
        <ServiceWorkerProvider>
          <ThemeProvider>{children}</ThemeProvider>
        </ServiceWorkerProvider>
      </body>
    </html>
  );
}
