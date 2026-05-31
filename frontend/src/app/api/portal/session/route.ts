import { NextResponse } from "next/server";

export async function POST(request: Request) {
  const { action } = await request.json();
  const res = NextResponse.json({ ok: true });

  if (action === "set") {
    res.cookies.set("afj_portal_session", "1", {
      httpOnly: true,
      sameSite: "lax",
      maxAge: 86400,
      path: "/",
      secure: process.env.NODE_ENV === "production",
    });
  } else if (action === "clear") {
    res.cookies.delete("afj_portal_session");
  }

  return res;
}
