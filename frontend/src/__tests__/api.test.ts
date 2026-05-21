import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

const mockFetch = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", mockFetch);
  vi.stubGlobal("localStorage", {
    getItem: vi.fn().mockReturnValue("test-token"),
    setItem: vi.fn(),
    removeItem: vi.fn(),
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api retry logic", () => {
  it("retries on 500 and eventually fails", async () => {
    mockFetch.mockResolvedValue({ status: 500, ok: false });

    const { api } = await import("@/lib/api");
    await expect(api.get("/test")).rejects.toThrow();
    expect(mockFetch).toHaveBeenCalledTimes(3);
  });

  it("succeeds on first try when response is ok", async () => {
    mockFetch.mockResolvedValueOnce({
      status: 200,
      ok: true,
      text: async () => JSON.stringify({ id: "123" }),
    });

    const { api } = await import("@/lib/api");
    const result = await api.get<{ id: string }>("/test");
    expect(result.id).toBe("123");
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("handles empty response body", async () => {
    mockFetch.mockResolvedValueOnce({
      status: 200,
      ok: true,
      text: async () => "",
    });

    const { api } = await import("@/lib/api");
    const result = await api.delete("/test");
    expect(result).toEqual({});
  });
});
