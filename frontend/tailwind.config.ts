import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // ─── Identidade Visual AFJ ───────────────────────────────────────────
        afj: {
          gold: "#C9A84C",      // dourado principal
          "gold-light": "#E8C96A",
          "gold-dark": "#A07830",
          black: "#1A1A1A",     // preto principal
          "black-soft": "#2A2A2A",
          cream: "#F5F0E8",     // creme claro
          "cream-dark": "#EDE5D0",
          charcoal: "#3D3D3D",
        },
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "#C9A84C",   // dourado AFJ
          foreground: "#1A1A1A",
        },
        secondary: {
          DEFAULT: "#F5F0E8",
          foreground: "#1A1A1A",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "#F5F0E8",
          foreground: "#6B6B6B",
        },
        accent: {
          DEFAULT: "#EDE5D0",
          foreground: "#1A1A1A",
        },
        // Status badges
        status: {
          active: "#16A34A",
          pending: "#D97706",
          critical: "#DC2626",
          archived: "#6B7280",
          approved: "#059669",
          rejected: "#DC2626",
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "Inter", "system-ui", "sans-serif"],
        display: ["var(--font-playfair)", "Playfair Display", "Georgia", "serif"],
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};

export default config;
