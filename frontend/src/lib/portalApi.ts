// Sempre relativo (mesma origem) — rewrite server-side, sem CORS.
const BASE = "/api/v1";

function getPortalToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("afj_portal_token");
}

async function clearPortalSession() {
  try {
    await fetch("/api/portal/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "clear" }),
    });
  } catch {}
  localStorage.removeItem("afj_portal_token");
  localStorage.removeItem("afj_portal_refresh_token");
  localStorage.removeItem("afj_portal_user");
}

// Fase 234 — o portal deixou de ter login por senha (só o link temporário
// gera sessão), então um 401 por token de acesso expirado (30 min,
// ACCESS_TOKEN_EXPIRE_MINUTES) não tem mais como "relogar" — sem isto o
// cliente seria expulso a cada 30 min de uso. Tenta renovar 1x via
// /auth/refresh (mesmo endpoint genérico já usado pelo app inteiro) antes
// de desistir e mandar pra página informativa.
let refreshEmAndamento: Promise<boolean> | null = null;

async function tentarRenovarSessao(): Promise<boolean> {
  if (refreshEmAndamento) return refreshEmAndamento;
  refreshEmAndamento = (async () => {
    const refreshToken = typeof window !== "undefined" ? localStorage.getItem("afj_portal_refresh_token") : null;
    if (!refreshToken) return false;
    try {
      const res = await fetch(`${BASE}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (!res.ok) return false;
      const data = await res.json();
      localStorage.setItem("afj_portal_token", data.access_token);
      localStorage.setItem("afj_portal_refresh_token", data.refresh_token);
      localStorage.setItem("afj_portal_user", JSON.stringify(data.user));
      return true;
    } catch {
      return false;
    }
  })();
  const ok = await refreshEmAndamento;
  refreshEmAndamento = null;
  return ok;
}

async function portalRequest<T>(path: string, options: RequestInit = {}, tentouRenovar = false): Promise<T> {
  const token = getPortalToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> || {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  if (res.status === 401) {
    if (!tentouRenovar && (await tentarRenovarSessao())) {
      return portalRequest<T>(path, options, true);
    }
    await clearPortalSession();
    window.location.href = "/portal/login";
    throw new Error("Sessão expirada");
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `Erro ${res.status}` }));
    throw new Error(err.detail || `Erro ${res.status}`);
  }
  const text = await res.text();
  return text ? (JSON.parse(text) as T) : ({} as T);
}

export const portalApi = {
  get: <T>(path: string) => portalRequest<T>(path, { method: "GET" }),
  post: <T>(path: string, body?: unknown) =>
    portalRequest<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
};

export { getPortalToken, clearPortalSession };
