export type Area = "website" | "company" | "admin";

export function areaOf(pathname: string): Area {
  if (pathname === "/admin" || pathname.startsWith("/admin/")) return "admin";
  if (pathname === "/company" || pathname.startsWith("/company/")) return "company";
  return "website";
}

/** Website pages that are not for search engines. Those reached from an emailed or shared link carry
 * a one-time secret in the address, so they also send no referrer. They are matched here by
 * prefix, never listed in robots.txt (which would publish them). */
const TOKEN_LINK_PREFIXES = [
  "/r",
  "/reset-password",
  "/verify-email",
  "/accept-invite",
  "/confirm-email-change",
  "/undo-company-deletion",
];
const OTHER_PRIVATE_PREFIXES = ["/forgot-password", "/design"];

const isUnder = (pathname: string, prefix: string) =>
  pathname === prefix || pathname.startsWith(`${prefix}/`);

export function isTokenLink(pathname: string) {
  return TOKEN_LINK_PREFIXES.some((prefix) => isUnder(pathname, prefix));
}

/** True for the panels and for the website pages that search engines must not list. */
export function isPrivatePage(pathname: string) {
  return (
    areaOf(pathname) !== "website" ||
    isTokenLink(pathname) ||
    OTHER_PRIVATE_PREFIXES.some((prefix) => isUnder(pathname, prefix))
  );
}

type Context = { development: boolean };

/** Scripts must carry this page's one-time code; nothing else may run, however it got into the page. */
export function contentSecurityPolicy({ nonce, development }: Context & { nonce: string }) {
  const directives = [
    "default-src 'self'",
    // 'strict-dynamic' lets the approved scripts load their own chunks. Development also
    // needs eval for React's refresh.
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${development ? " 'unsafe-eval'" : ""}`,
    // Components such as the popup set inline styles; scripts are the real risk.
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self'",
    // The browser only talks to this app; /api requests are forwarded to the server.
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ];
  if (!development) directives.push("upgrade-insecure-requests");
  return directives.join("; ");
}

const ONE_YEAR_SECONDS = 31_536_000;

/** Every response gets these; the panels are stricter than the public website. */
export function securityHeaders({
  area,
  nonce,
  development,
  pathname = "/",
}: Context & { area: Area; nonce: string; pathname?: string }): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Security-Policy": contentSecurityPolicy({ nonce, development }),
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Referrer-Policy":
      area === "website" && !isTokenLink(pathname)
        ? "strict-origin-when-cross-origin"
        : "no-referrer",
  };
  if (area !== "website") {
    // Signed-in pages are never stored by shared caches or found by search engines.
    headers["Cache-Control"] = "no-store";
  }
  if (isPrivatePage(pathname) || area !== "website") headers["X-Robots-Tag"] = "noindex, nofollow";
  // Browsers ignore this over plain http, and development runs on http.
  if (!development) {
    headers["Strict-Transport-Security"] = `max-age=${ONE_YEAR_SECONDS}; includeSubDomains`;
  }
  return headers;
}
