import { describe, expect, it } from "vitest";

import { readSiteUrl } from "./siteUrl";

describe("the public site address", () => {
  it("accepts an https address in production", () => {
    expect(readSiteUrl("https://bera.example.com", "production")).toBe("https://bera.example.com");
  });

  it("refuses to start in production without it", () => {
    expect(() => readSiteUrl(undefined, "production")).toThrow(/must be set/);
    expect(() => readSiteUrl("", "production")).toThrow(/must be set/);
  });

  it("refuses a plain http address in production", () => {
    expect(() => readSiteUrl("http://bera.example.com", "production")).toThrow(/https/);
  });

  it.each([
    "https://bera.example.com/",
    "https://bera.example.com/app",
    "https://bera.example.com?x=1",
    "https://user@bera.example.com",
    "bera.example.com",
    "javascript:alert(1)",
  ])("refuses %s", (value) => {
    expect(() => readSiteUrl(value, "production")).toThrow();
    expect(() => readSiteUrl(value, "development")).toThrow();
  });

  it("falls back to the local address in development and allows http there", () => {
    expect(readSiteUrl(undefined, "development")).toBe("http://localhost:3000");
    expect(readSiteUrl("http://localhost:3000", "development")).toBe("http://localhost:3000");
  });
});
