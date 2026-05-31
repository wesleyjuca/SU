import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (pathname.startsWith("/_next") || pathname.startsWith("/api") || pathname === "/favicon.ico") {
    return NextResponse.next();
  }

  // Portal routes — protected by afj_portal_session cookie
  if (pathname.startsWith("/portal")) {
    if (pathname === "/portal/login" || pathname === "/portal") {
      return NextResponse.next();
    }
    const portalSession = request.cookies.get("afj_portal_session");
    if (!portalSession?.value) {
      return NextResponse.redirect(new URL("/portal/login", request.url));
    }
    return NextResponse.next();
  }

  // Internal dashboard — protected by afj_session cookie
  if (pathname === "/" || pathname === "/login") {
    return NextResponse.next();
  }
  const session = request.cookies.get("afj_session");
  if (!session?.value) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
