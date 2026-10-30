// @vitest-environment node
import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { middleware } from "./middleware";

afterEach(() => vi.unstubAllEnvs());

const get = (path: string) => middleware(new NextRequest(`https://bera.example.com${path}`));

describe("middleware", () => {
  it.each(["/", "/company/projects", "/admin/login", "/does-not-exist"])(
    "adds the protections to %s",
    (path) => {
      vi.stubEnv("NODE_ENV", "production");
      const response = get(path);
      expect(response.headers.get("X-Frame-Options")).toBe("DENY");
      expect(response.headers.get("X-Content-Type-Options")).toBe("nosniff");
      expect(response.headers.get("Content-Security-Policy")).toContain("frame-ancestors 'none'");
    },
  );

  it("treats the three areas differently", () => {
    vi.stubEnv("NODE_ENV", "production");
    expect(get("/pricing").headers.get("Cache-Control")).toBeNull();
    expect(get("/company").headers.get("Cache-Control")).toBe("no-store");
    expect(get("/admin").headers.get("Referrer-Policy")).toBe("no-referrer");
  });

  it("gives every response its own one-time script code, matching the policy", () => {
    vi.stubEnv("NODE_ENV", "production");
    const code = (response: Response) =>
      /'nonce-([^']+)'/.exec(response.headers.get("Content-Security-Policy") ?? "")?.[1];
    const first = code(get("/"));
    expect(first).toBeTruthy();
    expect(first).not.toBe(code(get("/")));
  });

  it("does not force https in development", () => {
    vi.stubEnv("NODE_ENV", "development");
    expect(get("/").headers.get("Strict-Transport-Security")).toBeNull();
  });
});
