import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import MissingAdminPage from "@/app/admin/[...missing]/page";
import AdminNotFound from "@/app/admin/not-found";

import { AdminFrame } from "./AdminFrame";
import { ADMIN_NAVIGATION, visibleAdminNavigation, type AdminRole } from "./navigation";

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

function renderFrame(role: AdminRole = "admin") {
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
  Settings: ["General", "Limits", "Security", "Audit log", "Admin users"],
};

describe("sidebar items", () => {
  it("shows the six main items in order, all under /admin", () => {
    renderFrame();
    expect(visibleAdminNavigation("admin").map((item) => item.label)).toEqual([
      "Dashboard",
      "Companies",
      "Plans and Pricing",
      "AI",
      "Operations",
      "Settings",
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

  it("shows support admins every item until the Admin roles ticket decides otherwise", () => {
    expect(visibleAdminNavigation("support")).toHaveLength(6);
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
    expect(screen.getAllByRole("heading", { name: "Page not found" }).length).toBe(1);
  });
});
