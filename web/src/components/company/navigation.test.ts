import { describe, expect, it } from "vitest";

import { blockedCompanyHrefs, NAVIGATION, visibleNavigation } from "./navigation";

describe("visibleNavigation", () => {
  it("shows the owner the five main items and then Advanced, in order", () => {
    expect(visibleNavigation("owner").map((item) => item.label)).toEqual([
      "Dashboard",
      "Projects",
      "Team",
      "Usage and Billing",
      "Settings",
      "Advanced",
    ]);
  });

  it("hides Team, Usage and Billing, Settings and Advanced from members", () => {
    expect(visibleNavigation("member").map((item) => item.label)).toEqual([
      "Dashboard",
      "Projects",
    ]);
  });

  it("keeps only Profile and Company in Settings", () => {
    const settings = NAVIGATION.find((item) => item.label === "Settings")!;
    expect(settings.children?.map((child) => child.label)).toEqual(["Profile", "Company"]);
  });

  it("gives Advanced its five pages, with Retention and Scoring defaults moved there", () => {
    const advanced = NAVIGATION.find((item) => item.label === "Advanced")!;
    expect(advanced.children).toEqual([
      { label: "Scoring defaults", href: "/company/advanced/defaults" },
      { label: "Retention", href: "/company/advanced/retention" },
      { label: "Security", href: "/company/advanced/security" },
      { label: "Notifications", href: "/company/advanced/notifications" },
      { label: "Data and export", href: "/company/advanced/data-and-export" },
    ]);
  });

  it("keeps every address under /company and none of the moved ones under settings", () => {
    const addresses = NAVIGATION.flatMap((item) => [
      item.href,
      ...(item.children ?? []).map((child) => child.href),
    ]);
    for (const address of addresses) {
      expect(address.startsWith("/company")).toBe(true);
    }
    expect(addresses).not.toContain("/company/settings/retention");
    expect(addresses).not.toContain("/company/settings/defaults");
  });

  it("sets Advanced apart, below Settings, and guards its addresses", () => {
    const labels = NAVIGATION.map((item) => item.label);
    expect(labels.indexOf("Advanced")).toBe(labels.indexOf("Settings") + 1);
    const advanced = NAVIGATION.find((item) => item.label === "Advanced")!;
    expect(advanced.separated).toBe(true);
    expect(advanced.guarded).toBe(true);
  });

  it("blocks only Advanced for members and nothing for owners", () => {
    expect(blockedCompanyHrefs("member")).toEqual(["/company/advanced"]);
    expect(blockedCompanyHrefs("owner")).toEqual([]);
  });
});
