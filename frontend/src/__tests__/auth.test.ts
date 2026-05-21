import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const mockFetch = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", mockFetch);
  vi.stubGlobal("localStorage", {
    getItem: vi.fn().mockReturnValue(null),
    setItem: vi.fn(),
    removeItem: vi.fn(),
  });
  vi.stubGlobal("document", { cookie: "" });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("login flow", () => {
  it("posts credentials to /api/v1/auth/login", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        access_token: "access-abc",
        refresh_token: "refresh-xyz",
        user: { id: "1", email: "admin@test.com", full_name: "Admin", role: "ADMIN" },
      }),
    });

    const res = await fetch("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: "admin@test.com", password: "secret" }),
    });

    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data.access_token).toBe("access-abc");
    expect(data.user.role).toBe("ADMIN");
  });

  it("returns 401 for wrong credentials", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: async () => ({ detail: "E-mail ou senha incorretos" }),
    });

    const res = await fetch("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: "wrong@test.com", password: "wrong" }),
    });

    expect(res.status).toBe(401);
  });
});
