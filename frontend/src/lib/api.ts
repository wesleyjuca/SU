const BASE = process.env.NEXT_PUBLIC_API_URL
  ? `${process.env.NEXT_PUBLIC_API_URL}/api/v1`
  : "/api/v1";
const TIMEOUT_MS = 30_000;
const MAX_RETRIES = 3;

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("afj_access_token");
}

function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("afj_refresh_token");
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function clearSession() {
  try {
    await fetch("/api/auth/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "clear" }),
    });
  } catch {}
}

async function refreshTokens(): Promise<boolean> {
  const refresh = getRefreshToken();
  if (!refresh) return false;
  try {
    const res = await fetch(`${BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    if (res.ok) {
      const data = await res.json();
      localStorage.setItem("afj_access_token", data.access_token);
      localStorage.setItem("afj_refresh_token", data.refresh_token);
      return true;
    }
  } catch {}
  return false;
}

async function fetchWithRetry(url: string, options: RequestInit): Promise<Response> {
  let lastError: unknown;
  for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
    try {
      const res = await fetch(url, {
        ...options,
        signal: AbortSignal.timeout(TIMEOUT_MS),
      });
      if (res.status >= 500 && attempt < MAX_RETRIES - 1) {
        await sleep(Math.pow(2, attempt) * 500);
        continue;
      }
      return res;
    } catch (e) {
      lastError = e;
      if (attempt < MAX_RETRIES - 1) await sleep(Math.pow(2, attempt) * 500);
    }
  }
  throw lastError;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  let res = await fetchWithRetry(`${BASE}${path}`, { ...options, headers });

  // Auto-refresh on 401
  if (res.status === 401) {
    const refreshed = await refreshTokens();
    if (refreshed) {
      const newToken = getToken();
      res = await fetchWithRetry(`${BASE}${path}`, {
        ...options,
        headers: { ...headers, Authorization: `Bearer ${newToken}` },
      });
    } else {
      localStorage.removeItem("afj_access_token");
      localStorage.removeItem("afj_refresh_token");
      localStorage.removeItem("afj_user");
      await clearSession();
      window.location.href = "/login";
      throw new Error("Sessão expirada");
    }
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  const text = await res.text();
  return text ? JSON.parse(text) : ({} as T);
}

export const api = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body !== undefined ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: body !== undefined ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body !== undefined ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};

export default api;
