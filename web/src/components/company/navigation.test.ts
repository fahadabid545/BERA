import { describe, expect, it } from "vitest";

import { isCurrentPath, NAVIGATION, visibleNavigation } from "./navigation";

describe("visibleNavigation", () => {
  it("shows the owner all five main items in order", () => {
    expect(visibleNavigation("owner").map((item) => item.label)).toEqual([
      "Dashboard",
      "Projects",
      "Team",
      "Usage and Billing",
      "Settings",
    ]);
  });

  it("hides Team, Usage and Billing and Settings from members", () => {
    expect(visibleNavigation("member").map((item) => item.label)).toEqual([
      "Dashboard",
      "Projects",
    ]);
  });

  it("gives Settings its four sub-pages, all under /company", () => {
    const settings = NAVIGATION.find((item) => item.label === "Settings")!;
    expect(settings.children?.map((child) => child.label)).toEqual([
      "Profile",
      "Company",
      "Retention",
      "Defaults",
    ]);
    for (const item of NAVIGATION) {
      expect(item.href.startsWith("/company")).toBe(true);
    }
  });
});

describe("isCurrentPath", () => {
  it("matches the page itself and pages below it", () => {
    expect(isCurrentPath("/company/projects", "/company/projects")).toBe(true);
    expect(isCurrentPath("/company/projects/42", "/company/projects")).toBe(true);
  });

  it("does not match a different page that only starts with the same letters", () => {
    expect(isCurrentPath("/company/projects-old", "/company/projects")).toBe(false);
  });

  it("matches an exact-only item on its own address only", () => {
    expect(isCurrentPath("/company", "/company", true)).toBe(true);
    expect(isCurrentPath("/company/projects", "/company", true)).toBe(false);
  });
});
