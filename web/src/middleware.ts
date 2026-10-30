import { NextResponse, type NextRequest } from "next/server";

import { areaOf, contentSecurityPolicy, securityHeaders } from "@/security/headers";

export function middleware(request: NextRequest) {
  const development = process.env.NODE_ENV === "development";
  const nonce = btoa(crypto.randomUUID());
  const area = areaOf(request.nextUrl.pathname);

  // Next.js reads the nonce from the request's policy and puts it on its own scripts;
  // the layout reads x-nonce for the one inline script it adds.
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", contentSecurityPolicy({ nonce, development }));

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  for (const [name, value] of Object.entries(securityHeaders({ area, nonce, development }))) {
    response.headers.set(name, value);
  }
  return response;
}

export const config = {
  matcher: [{ source: "/((?!_next/static|_next/image|favicon.ico).*)" }],
};
