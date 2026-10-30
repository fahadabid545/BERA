import { describe, expect, it } from "vitest";

import { areaOf, contentSecurityPolicy, securityHeaders } from "./headers";

const nonce = "abc123";

describe("areaOf", () => {
  it.each([
    ["/", "website"],
    ["/pricing", "website"],
    ["/login", "website"],
    ["/r/some-token", "website"],
    ["/company", "company"],
    ["/company/projects/p1", "company"],
    ["/admin", "admin"],
    ["/admin/login", "admin"],
    ["/administrators", "website"],
    ["/companyfoo", "website"],
  ])("puts %s in the %s area", (pathname, area) => {
    expect(areaOf(pathname)).toBe(area);
  });
});

describe("content security policy", () => {
  const policy = contentSecurityPolicy({ nonce, development: false });

  it("only runs scripts that carry the page's code, and never inline or eval in production", () => {
    expect(policy).toContain(`script-src 'self' 'nonce-${nonce}' 'strict-dynamic'`);
    expect(policy).not.toMatch(/script-src[^;]*('unsafe-inline'|'unsafe-eval')/);
  });

  it("refuses framing, plugins, other base addresses and other form targets", () => {
    for (const rule of [
      "frame-ancestors 'none'",
      "object-src 'none'",
      "base-uri 'self'",
      "form-action 'self'",
      "default-src 'self'",
      "connect-src 'self'",
    ]) {
      expect(policy).toContain(rule);
    }
  });

  it("loads nothing from other sites", () => {
    expect(policy).not.toMatch(/https?:|\*/);
  });

  it("differs in development: eval for the refresh tool and no forced https", () => {
    const development = contentSecurityPolicy({ nonce, development: true });
    expect(development).toContain("'unsafe-eval'");
    expect(development).not.toContain("upgrade-insecure-requests");
    expect(policy).toContain("upgrade-insecure-requests");
    expect(policy).not.toContain("'unsafe-eval'");
  });
});

describe("security headers", () => {
  const forAll = ["website", "company", "admin"] as const;

  it.each(forAll)("on the %s area include the standard protections", (area) => {
    const headers = securityHeaders({ area, nonce, development: false });
    expect(headers["X-Frame-Options"]).toBe("DENY");
    expect(headers["X-Content-Type-Options"]).toBe("nosniff");
    expect(headers["Cross-Origin-Opener-Policy"]).toBe("same-origin");
    expect(headers["Cross-Origin-Resource-Policy"]).toBe("same-origin");
    expect(headers["Permissions-Policy"]).toContain("camera=()");
    expect(headers["Content-Security-Policy"]).toContain("frame-ancestors 'none'");
    expect(headers["Strict-Transport-Security"]).toBe("max-age=31536000; includeSubDomains");
  });

  it("keeps the public website findable and cacheable", () => {
    const headers = securityHeaders({ area: "website", nonce, development: false });
    expect(headers["Referrer-Policy"]).toBe("strict-origin-when-cross-origin");
    expect(headers["Cache-Control"]).toBeUndefined();
    expect(headers["X-Robots-Tag"]).toBeUndefined();
  });

  it.each(["company", "admin"] as const)(
    "keeps the %s panel private: no referrer, no caching, no indexing",
    (area) => {
      const headers = securityHeaders({ area, nonce, development: false });
      expect(headers["Referrer-Policy"]).toBe("no-referrer");
      expect(headers["Cache-Control"]).toBe("no-store");
      expect(headers["X-Robots-Tag"]).toBe("noindex, nofollow");
    },
  );

  it.each(forAll)("leaves out https-only rules in development on the %s area", (area) => {
    const headers = securityHeaders({ area, nonce, development: true });
    expect(headers["Strict-Transport-Security"]).toBeUndefined();
    expect(headers["X-Frame-Options"]).toBe("DENY");
  });
});
