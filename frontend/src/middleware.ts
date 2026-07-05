import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Deixa passar assets do Next, a API e qualquer arquivo estático (com extensão:
  // .png/.svg/.json/.js/.woff...). Sem isto, o guard abaixo redireciona o request
  // de /logo-afj-mark.png (e outros estáticos) para /login e a imagem quebra.
  if (
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api") ||
    /\.[a-zA-Z0-9]+$/.test(pathname)
  ) {
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
