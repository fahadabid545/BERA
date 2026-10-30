import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import MissingAdminPage from "@/app/admin/(panel)/[...missing]/page";
import AdminNotFound from "@/app/admin/(panel)/not-found";

import { AdminFrame } from "./AdminFrame";
import {
  ADMIN_NAVIGATION,
  blockedAdminHrefs,
  visibleAdminNavigation,
  type AdminRole,
} from "./navigation";

const pathname = vi.hoisted(() => ({ current: "/admin" }));
vi.mock("next/navigation", () => ({
  usePathname: () => pathname.current,
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
}));

beforeEach(() => {
  pathname.current = "/admin";
});

function renderFrame(role: AdminRole = "super") {
  return render(
    <AdminFrame userName="Fake Admin" role={role}>
      <p>Page content</p>
    </AdminFrame>,
  );
}

const sidebar = () => screen.getByRole("navigation", { name: "Admin" });

const SUB_MENUS = {
  AI: ["Playground", "Models", "Prompts"],
  Operations: ["Jobs", "Payments", "Announcements", "Data requests"],
  Settings: ["General", "Audit log", "Admin users"],
  Advanced: [
    "Platform values",
    "Limits",
    "Rate limiting",
    "Security",
    "AI controls",
    "Maintenance",
  ],
};

describe("sidebar items", () => {
  it("shows a super admin the six main items and then Advanced, all under /admin", () => {
    renderFrame();
    expect(visibleAdminNavigation("super").map((item) => item.label)).toEqual([
      "Dashboard",
      "Companies",
      "Plans and Pricing",
      "AI",
      "Operations",
      "Settings",
      "Advanced",
    ]);
    for (const [name, href] of [
      ["Dashboard", "/admin"],
      ["Companies", "/admin/companies"],
      ["Plans and Pricing", "/admin/plans"],
    ]) {
      expect(within(sidebar()).getByRole("link", { name }).getAttribute("href")).toBe(href);
    }
    for (const name of Object.keys(SUB_MENUS)) {
      expect(within(sidebar()).getByRole("button", { name })).toBeTruthy();
    }
    for (const item of ADMIN_NAVIGATION) {
      expect(item.href.startsWith("/admin")).toBe(true);
    }
  });

  it("highlights only the current page", () => {
    pathname.current = "/admin/companies/7";
    renderFrame();
    const current = within(sidebar())
      .getAllByRole("link")
      .filter((link) => link.getAttribute("aria-current") === "page");
    expect(current.map((link) => link.textContent)).toEqual(["Companies"]);
  });

  it("shows support admins the six main items but not Advanced", () => {
    expect(visibleAdminNavigation("support").map((item) => item.label)).toEqual([
      "Dashboard",
      "Companies",
      "Plans and Pricing",
      "AI",
      "Operations",
      "Settings",
    ]);
    renderFrame("support");
    expect(within(sidebar()).queryByRole("button", { name: "Advanced" })).toBeNull();
    expect(within(sidebar()).getAllByRole("link").length).toBeGreaterThan(0);
  });
});

describe("sub-menus", () => {
  it("are closed until clicked", () => {
    renderFrame();
    for (const [name, links] of Object.entries(SUB_MENUS)) {
      expect(within(sidebar()).getByRole("button", { name }).getAttribute("aria-expanded")).toBe(
        "false",
      );
      expect(within(sidebar()).queryByRole("link", { name: links[0] })).toBeNull();
    }
  });

  it.each(Object.entries(SUB_MENUS))(
    "%s opens with its pages and closes on click",
    async (name, links) => {
      const user = userEvent.setup();
      renderFrame();
      const group = within(sidebar()).getByRole("button", { name });

      await user.click(group);
      expect(group.getAttribute("aria-expanded")).toBe("true");
      expect(
        within(sidebar())
          .getAllByRole("link")
          .map((link) => link.textContent)
          .filter((text) => links.includes(text ?? "")),
      ).toEqual(links);

      await user.click(group);
      expect(within(sidebar()).queryByRole("link", { name: links[0] })).toBeNull();
    },
  );

  it("opens one at a time", async () => {
    const user = userEvent.setup();
    renderFrame();

    await user.click(within(sidebar()).getByRole("button", { name: "AI" }));
    await user.click(within(sidebar()).getByRole("button", { name: "Operations" }));

    expect(within(sidebar()).queryByRole("link", { name: "Playground" })).toBeNull();
    expect(within(sidebar()).getByRole("link", { name: "Jobs" })).toBeTruthy();
  });

  it("mark the group and the page as current without opening on their own", async () => {
    const user = userEvent.setup();
    pathname.current = "/admin/operations/payments";
    renderFrame();
    const group = within(sidebar()).getByRole("button", { name: "Operations" });

    expect(group.getAttribute("aria-expanded")).toBe("false");
    expect(group.getAttribute("data-active")).toBe("true");
    expect(within(sidebar()).getByRole("button", { name: "AI" }).getAttribute("data-active")).toBe(
      "false",
    );

    await user.click(group);
    expect(
      within(sidebar()).getByRole("link", { name: "Payments" }).getAttribute("aria-current"),
    ).toBe("page");
  });
});

describe("Advanced section", () => {
  it("keeps only General, Audit log and Admin users in Settings", () => {
    const settings = ADMIN_NAVIGATION.find((item) => item.label === "Settings")!;
    expect(settings.children?.map((child) => child.label)).toEqual([
      "General",
      "Audit log",
      "Admin users",
    ]);
  });

  it("moves Limits and Security to /admin/advanced", () => {
    const addresses = ADMIN_NAVIGATION.flatMap((item) =>
      (item.children ?? []).map((child) => child.href),
    );
    expect(addresses).toContain("/admin/advanced/limits");
    expect(addresses).toContain("/admin/advanced/security");
    expect(addresses).not.toContain("/admin/settings/limits");
    expect(addresses).not.toContain("/admin/settings/security");
  });

  it("sits below Settings, set apart by a divider, with its own icon", () => {
    renderFrame();
    const settings = within(sidebar()).getByRole("button", { name: "Settings" }).closest("li")!;
    const advanced = within(sidebar()).getByRole("button", { name: "Advanced" });

    expect(settings.compareDocumentPosition(advanced.closest("li")!)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
    expect(advanced.closest("li")!.getAttribute("data-separated")).toBe("true");
    expect(settings.hasAttribute("data-separated")).toBe(false);
    expect(advanced.querySelector(".ui-toggle-icon__filled")).not.toBeNull();
  });

  it("lists its six pages in order, with the addresses given", async () => {
    const user = userEvent.setup();
    renderFrame();
    await user.click(within(sidebar()).getByRole("button", { name: "Advanced" }));

    const advanced = ADMIN_NAVIGATION.find((item) => item.label === "Advanced")!;
    for (const child of advanced.children!) {
      expect(within(sidebar()).getByRole("link", { name: child.label }).getAttribute("href")).toBe(
        child.href,
      );
    }
    expect(advanced.children!.map((child) => child.href)).toEqual([
      "/admin/advanced/platform-values",
      "/admin/advanced/limits",
      "/admin/advanced/rate-limits",
      "/admin/advanced/security",
      "/admin/advanced/ai-controls",
      "/admin/advanced/maintenance",
    ]);
  });

  it("highlights the current Advanced page without opening on its own", async () => {
    const user = userEvent.setup();
    pathname.current = "/admin/advanced/limits";
    renderFrame();
    const advanced = within(sidebar()).getByRole("button", { name: "Advanced" });

    expect(advanced.getAttribute("aria-expanded")).toBe("false");
    expect(advanced.getAttribute("data-active")).toBe("true");
    expect(
      within(sidebar()).getByRole("button", { name: "Settings" }).getAttribute("data-active"),
    ).toBe("false");

    await user.click(advanced);
    expect(
      within(sidebar()).getByRole("link", { name: "Limits" }).getAttribute("aria-current"),
    ).toBe("page");
    expect(
      within(sidebar()).getByRole("link", { name: "Security" }).getAttribute("aria-current"),
    ).toBeNull();
  });

  it("blocks only Advanced, and only for support admins", () => {
    expect(blockedAdminHrefs("support")).toEqual(["/admin/advanced"]);
    expect(blockedAdminHrefs("super")).toEqual([]);
  });

  it("shows a super admin the page at an Advanced address", () => {
    pathname.current = "/admin/advanced/security";
    renderFrame("super");
    expect(screen.getByRole("main").textContent).toBe("Page content");
  });

  it.each(["/admin/advanced", "/admin/advanced/limits", "/admin/advanced/maintenance"])(
    "shows a support admin who types %s the no-access page, inside the frame",
    (address) => {
      pathname.current = address;
      renderFrame("support");
      expect(screen.getByRole("heading", { name: "You do not have access" })).toBeTruthy();
      expect(screen.queryByText("Page content")).toBeNull();
      expect(screen.getByRole("navigation", { name: "Admin" })).toBeTruthy();
    },
  );

  it("still shows support admins their own pages and does not block look-alike addresses", () => {
    for (const address of ["/admin/companies", "/admin/advanced-old"]) {
      pathname.current = address;
      const { unmount } = renderFrame("support");
      expect(screen.getByRole("main").textContent).toBe("Page content");
      unmount();
    }
  });
});

describe("top bar", () => {
  it("shows a clear Admin badge, the theme switch and the admin user menu with Log out", async () => {
    const user = userEvent.setup();
    renderFrame();
    const bar = screen.getByRole("banner");

    expect(within(bar).getByText("Admin").classList.contains("ui-tag--admin")).toBe(true);
    expect(within(bar).getByRole("switch", { name: "Dark mode" })).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "User menu" }));
    expect(screen.getAllByRole("menuitem").map((item) => item.textContent)).toEqual(["Log out"]);
  });

  it("has no company-only controls", () => {
    renderFrame();
    expect(screen.queryByRole("link", { name: "New project" })).toBeNull();
  });
});

describe("frame", () => {
  it("is marked as the admin variant, not the company one", () => {
    const { container } = renderFrame();
    const frame = container.querySelector(".panel-frame")!;
    expect(frame.classList.contains("panel--admin")).toBe(true);
    expect(frame.classList.contains("panel--company")).toBe(false);
  });

  it("opens and closes the phone menu", async () => {
    const user = userEvent.setup();
    const { container } = renderFrame();
    const frame = container.querySelector(".panel-frame")!;

    await user.click(screen.getByRole("button", { name: "Menu" }));
    expect(frame.getAttribute("data-menu-open")).toBe("true");
    await user.keyboard("{Escape}");
    expect(frame.getAttribute("data-menu-open")).toBe("false");
  });

  it("shows the page and shows pages not built yet as not found, inside the frame", () => {
    renderFrame();
    expect(screen.getByRole("main").textContent).toBe("Page content");
    expect(() => MissingAdminPage()).toThrow("NEXT_NOT_FOUND");
    render(<AdminNotFound />);
    expect(screen.getAllByRole("heading", { name: "This page could not be found" }).length).toBe(1);
    expect(screen.getByRole("link", { name: "Go home" }).getAttribute("href")).toBe("/admin");
  });
});
