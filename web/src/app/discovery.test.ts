// @vitest-environment node
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PUBLIC_PAGES } from "@/lib/seo";
import { middleware } from "@/middleware";

import robots from "./robots";
import sitemap from "./sitemap";

afterEach(() => vi.unstubAllEnvs());

const APP = path.join(process.cwd(), "src", "app");

/** Every page of the app as (its address, the files that can set its metadata). */
function pages(directory = APP, parents: string[] = [], layouts: string[] = []) {
  const found: { route: string; files: string[] }[] = [];
  const own = path.join(directory, "layout.tsx");
  const chain = [...layouts, ...(exists(own) ? [own] : [])];
  for (const name of readdirSync(directory)) {
    const full = path.join(directory, name);
    if (statSync(full).isDirectory()) {
      const segment = /^\(.*\)$/.test(name) ? [] : [name];
      found.push(...pages(full, [...parents, ...segment], chain));
    } else if (name === "page.tsx") {
      found.push({ route: "/" + parents.join("/"), files: [...chain, full] });
    }
  }
  return found;
}
const exists = (file: string) => {
  try {
    return statSync(file).isFile();
  } catch {
    return false;
  }
};

const PUBLIC_ROUTES = new Set<string>(Object.values(PUBLIC_PAGES).map((page) => page.path));
const PRIVATE = pages().filter((page) => !PUBLIC_ROUTES.has(page.route));
const concrete = (route: string) => route.replace(/\[[^\]]+\]/g, "fake-token");

describe("search engines and private pages", () => {
  it("finds the pages (so the checks below cannot pass by checking nothing)", () => {
    expect(PRIVATE.length).toBeGreaterThan(30);
    expect(pages().filter((page) => PUBLIC_ROUTES.has(page.route))).toHaveLength(10);
  });

  it.each(PRIVATE.map((page) => [page.route, page]))("%s is sent with noindex", (_route, page) => {
    vi.stubEnv("NODE_ENV", "production");
    const response = middleware(new NextRequest(`https://bera.example.com${concrete(page.route)}`));
    expect(response.headers.get("X-Robots-Tag")).toBe("noindex, nofollow");
  });

  it.each(
    PRIVATE.filter(
      (page) => !page.route.startsWith("/company") && !page.route.startsWith("/admin"),
    ).map((page) => [page.route, page]),
  )("%s also says noindex in its own page tag", (_route, page) => {
    expect(
      page.files.some((file) => /privatePage|tokenLinkPage/.test(readFileSync(file, "utf8"))),
    ).toBe(true);
  });

  it.each(
    PRIVATE.filter(
      (page) => page.route.startsWith("/company") || page.route.startsWith("/admin"),
    ).map((page) => [page.route, page]),
  )("the panel page %s says noindex in its layout tag", (_route, page) => {
    expect(
      page.files.some(
        (file) => file.endsWith("layout.tsx") && /privatePage/.test(readFileSync(file, "utf8")),
      ),
    ).toBe(true);
  });

  it("sends no referrer from the links that carry a secret", () => {
    for (const route of [
      "/r/x",
      "/reset-password",
      "/verify-email",
      "/accept-invite",
      "/confirm-email-change",
      "/undo-company-deletion",
    ]) {
      const response = middleware(new NextRequest(`https://bera.example.com${route}`));
      expect(response.headers.get("Referrer-Policy"), route).toBe("no-referrer");
    }
  });

  it("does not hide the public pages", () => {
    for (const route of PUBLIC_ROUTES) {
      const response = middleware(new NextRequest(`https://bera.example.com${route}`));
      expect(response.headers.get("X-Robots-Tag"), route).toBeNull();
    }
  });
});

describe("sitemap and robots", () => {
  vi.stubEnv("NEXT_PUBLIC_SITE_URL", "https://bera.example.com");

  it("lists exactly the ten public pages, with no dates", () => {
    vi.stubEnv("NEXT_PUBLIC_SITE_URL", "https://bera.example.com");
    const entries = sitemap();
    expect(entries.map((entry) => entry.url)).toEqual(
      [
        "/",
        "/features",
        "/how-it-works",
        "/pricing",
        "/faq",
        "/contact",
        "/terms",
        "/privacy",
        "/login",
        "/signup",
      ].map((route) => `https://bera.example.com${route}`),
    );
    expect(entries.every((entry) => entry.lastModified === undefined)).toBe(true);
  });

  it("allows the public pages, points to the sitemap and names no private path", () => {
    vi.stubEnv("NEXT_PUBLIC_SITE_URL", "https://bera.example.com");
    const result = robots();
    expect(result.sitemap).toBe("https://bera.example.com/sitemap.xml");
    const text = JSON.stringify(result);
    for (const secret of [
      "/admin",
      "/company",
      "/r/",
      "reset-password",
      "verify-email",
      "disallow",
    ]) {
      expect(text.toLowerCase()).not.toContain(secret.toLowerCase());
    }
  });
});
