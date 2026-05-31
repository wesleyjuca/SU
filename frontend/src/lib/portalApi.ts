const BASE = process.env.NEXT_PUBLIC_API_URL
  ? `${process.env.NEXT_PUBLIC_API_URL}/api/v1`
  : "/api/v1";

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
  localStorage.removeItem("afj_portal_user");
}

async function portalRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getPortalToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> || {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
  const res = await fetch(`${BASE}${path}`, { ...options, headers });
  if (res.status === 401) {
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
};

export { getPortalToken, clearPortalSession };
