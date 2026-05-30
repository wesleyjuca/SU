import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PUBLIC_PATHS = ["/", "/login", "/favicon.ico"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (
    PUBLIC_PATHS.some((p) => pathname.startsWith(p)) ||
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api")
  ) {
    return NextResponse.next();
  }

  const session = request.cookies.get("afj_session");
  if (!session?.value) {
    const loginUrl = new URL("/login", request.url);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
