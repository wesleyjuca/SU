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
        // ─── Identidade Visual AFJ (Almeida, Freire & Jucá) ─────────────────
        afj: {
          gold: "#B8954A",         // dourado acobreado — cor oficial da marca
          "gold-light": "#D4AC64",
          "gold-dark": "#8A6D2A",
          black: "#1A1A1A",        // preto para texto
          "black-soft": "#252B35",
          cream: "#F4F0EA",        // creme claro — fundo principal
          "cream-dark": "#EAE5D8",
          charcoal: "#353D4A",
          navy: "#1E2229",         // charcoal-navy — fundo da sidebar (marca)
        },
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "#B8954A",
          foreground: "#FFFFFF",
        },
        secondary: {
          DEFAULT: "#F4F0EA",
          foreground: "#1A1A1A",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "#F4F0EA",
          foreground: "#6B6B6B",
        },
        accent: {
          DEFAULT: "#EAE5D8",
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
        display: ["Optima", "Optima Nova", "Georgia", "serif"],
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      keyframes: {
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "slide-in": {
          "0%": { transform: "translateX(-8px)", opacity: "0" },
          "100%": { transform: "translateX(0)", opacity: "1" },
        },
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.18s ease-out",
        "slide-in": "slide-in 0.18s ease-out",
        "fade-up": "fade-up 0.22s ease-out",
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};

export default config;
