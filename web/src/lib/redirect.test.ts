import { describe, expect, it } from "vitest";

import { pageAfterLogin } from "./redirect";

describe("the page after logging in", () => {
  it("is the dashboard when no page was asked for", () => {
    for (const value of [undefined, null, "", []])
      expect(pageAfterLogin(value as never)).toBe("/company");
  });

  it.each([
    "/company",
    "/company/projects",
    "/company/projects/abc/candidates?tab=2",
    "/company/team#top",
  ])("is the page that was asked for: %s", (page) => {
    expect(pageAfterLogin(page)).toBe(page);
  });

  it("takes the first when several are given", () => {
    expect(pageAfterLogin(["/company/team", "/company/billing"])).toBe("/company/team");
  });

  it.each([
    "https://evil.example.test/company",
    "//evil.example.test/company",
    "/\\evil.example.test",
    "/company/../../evil",
    "/admin",
    "/companyx",
    "/login",
    "javascript:alert(1)",
    "company/projects",
    "/company\nSet-Cookie: x=1",
    "/company?next=https://evil.example.test",
  ])("is the dashboard for an unsafe or foreign address: %s", (page) => {
    expect(pageAfterLogin(page)).toBe("/company");
  });
});
