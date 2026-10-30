import { describe, expect, it } from "vitest";

import { isCurrentPath, visibleItems, type NavigationItem } from "./navigation";

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

describe("visibleItems", () => {
  const items: NavigationItem<"full" | "limited">[] = [
    { label: "One", href: "/one", icon: "dashboard", roles: ["full", "limited"] },
    { label: "Two", href: "/two", icon: "team", roles: ["full"] },
  ];

  it("keeps only the items the role may open", () => {
    expect(visibleItems(items, "full").map((item) => item.label)).toEqual(["One", "Two"]);
    expect(visibleItems(items, "limited").map((item) => item.label)).toEqual(["One"]);
  });

  it("does not pass the roles on to the sidebar", () => {
    expect(visibleItems(items, "full")[0]).not.toHaveProperty("roles");
  });
});
