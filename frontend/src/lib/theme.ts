export interface TenantTheme {
  primaryColor: string;
  secondaryColor: string;
  accentColor: string;
  appName: string;
  logoUrl: string | null;
  logoDarkUrl: string | null;
  faviconUrl: string | null;
}

const STORAGE_KEY = "afj_theme";

const DEFAULT_THEME: TenantTheme = {
  primaryColor: "#B8954A",
  secondaryColor: "#1E2229",
  accentColor: "#F4F0EA",
  appName: "AFJ CORE",
  logoUrl: null,
  logoDarkUrl: null,
  faviconUrl: null,
};

export function applyTheme(theme: TenantTheme): void {
  const root = document.documentElement;
  root.style.setProperty("--brand-primary", theme.primaryColor);
  root.style.setProperty("--brand-secondary", theme.secondaryColor);
  root.style.setProperty("--brand-accent", theme.accentColor);

  // Derived shades (lighten/darken approximation)
  root.style.setProperty("--brand-primary-light", _lighten(theme.primaryColor, 20));
  root.style.setProperty("--brand-primary-dark", _darken(theme.primaryColor, 20));

  if (theme.faviconUrl) {
    try {
      const link = (document.querySelector("link[rel='icon']") as HTMLLinkElement)
        ?? Object.assign(document.createElement("link"), { rel: "icon" });
      link.href = theme.faviconUrl;
      if (!link.parentNode) document.head.appendChild(link);
    } catch {}
  }

  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(theme));
  } catch {}
}

export function getStoredTheme(): TenantTheme | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as TenantTheme;
  } catch {
    return null;
  }
}

export async function fetchAndApplyTheme(): Promise<TenantTheme> {
  try {
    const token = localStorage.getItem("afj_access_token");
    if (!token) return applyAndReturn(getStoredTheme() ?? DEFAULT_THEME);

    const res = await fetch("/api/v1/tenant/theme", {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) return applyAndReturn(getStoredTheme() ?? DEFAULT_THEME);

    const data = await res.json();
    const theme: TenantTheme = {
      primaryColor: data.primary_color ?? DEFAULT_THEME.primaryColor,
      secondaryColor: data.secondary_color ?? DEFAULT_THEME.secondaryColor,
      accentColor: data.accent_color ?? DEFAULT_THEME.accentColor,
      appName: data.app_name ?? DEFAULT_THEME.appName,
      logoUrl: data.logo_url ?? null,
      logoDarkUrl: data.logo_dark_url ?? null,
      faviconUrl: data.favicon_url ?? null,
    };
    return applyAndReturn(theme);
  } catch {
    return applyAndReturn(getStoredTheme() ?? DEFAULT_THEME);
  }
}

function applyAndReturn(theme: TenantTheme): TenantTheme {
  applyTheme(theme);
  return theme;
}

function _hexToRgb(hex: string): [number, number, number] | null {
  const clean = hex.replace("#", "");
  if (clean.length !== 6) return null;
  const r = parseInt(clean.slice(0, 2), 16);
  const g = parseInt(clean.slice(2, 4), 16);
  const b = parseInt(clean.slice(4, 6), 16);
  return [r, g, b];
}

function _rgbToHex(r: number, g: number, b: number): string {
  return "#" + [r, g, b].map((v) => Math.max(0, Math.min(255, v)).toString(16).padStart(2, "0")).join("");
}

function _lighten(hex: string, amount: number): string {
  const rgb = _hexToRgb(hex);
  if (!rgb) return hex;
  return _rgbToHex(rgb[0] + amount, rgb[1] + amount, rgb[2] + amount);
}

function _darken(hex: string, amount: number): string {
  const rgb = _hexToRgb(hex);
  if (!rgb) return hex;
  return _rgbToHex(rgb[0] - amount, rgb[1] - amount, rgb[2] - amount);
}
