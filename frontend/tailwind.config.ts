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
        // gold/cream/navy vêm das variáveis --brand-* (canais RGB), então a
        // Personalização por escritório repinta o sistema em runtime. Os tons
        // neutros de texto (black/charcoal) permanecem fixos.
        afj: {
          gold: "rgb(var(--brand-primary) / <alpha-value>)",         // cor oficial da marca (customizável)
          "gold-light": "rgb(var(--brand-primary-light) / <alpha-value>)",
          "gold-dark": "rgb(var(--brand-primary-dark) / <alpha-value>)",
          black: "#1A1A1A",        // preto para texto (fixo)
          "black-soft": "#252B35",
          cream: "rgb(var(--brand-accent) / <alpha-value>)",         // fundo principal (customizável)
          "cream-dark": "rgb(var(--brand-accent-dark) / <alpha-value>)",
          charcoal: "#353D4A",
          navy: "rgb(var(--brand-secondary) / <alpha-value>)",       // sidebar/dark (customizável)
        },
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "rgb(var(--brand-primary) / <alpha-value>)",
          foreground: "#FFFFFF",
        },
        secondary: {
          DEFAULT: "rgb(var(--brand-accent) / <alpha-value>)",
          foreground: "#1A1A1A",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "rgb(var(--brand-accent) / <alpha-value>)",
          foreground: "#6B6B6B",
        },
        accent: {
          DEFAULT: "rgb(var(--brand-accent-dark) / <alpha-value>)",
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
