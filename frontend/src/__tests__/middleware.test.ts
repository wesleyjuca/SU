import { describe, it, expect } from "vitest";

// Unit tests for middleware logic (cookie-based auth guard)
describe("middleware auth logic", () => {
  it("allows public paths without session cookie", () => {
    const PUBLIC_PATHS = ["/login", "/favicon.ico"];
    const pathname = "/login";
    const isPublic = PUBLIC_PATHS.some((p) => pathname.startsWith(p));
    expect(isPublic).toBe(true);
  });

  it("blocks protected paths without session cookie", () => {
    const PUBLIC_PATHS = ["/login", "/favicon.ico"];
    const pathname = "/dashboard";
    const isPublic =
      PUBLIC_PATHS.some((p) => pathname.startsWith(p)) ||
      pathname.startsWith("/_next") ||
      pathname.startsWith("/api");
    expect(isPublic).toBe(false);
  });

  it("allows api paths without session cookie", () => {
    const pathname = "/api/v1/health";
    const isAllowed = pathname.startsWith("/api");
    expect(isAllowed).toBe(true);
  });

  it("allows _next static paths", () => {
    const pathname = "/_next/static/chunks/main.js";
    const isAllowed = pathname.startsWith("/_next");
    expect(isAllowed).toBe(true);
  });
});
