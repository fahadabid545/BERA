import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import MissingCompanyPage from "@/app/company/[...missing]/page";
import CompanyNotFound from "@/app/company/not-found";

import { CompanyFrame } from "./CompanyFrame";
import type { CompanyRole } from "./navigation";

const pathname = vi.hoisted(() => ({ current: "/company" }));
vi.mock("next/navigation", () => ({
  usePathname: () => pathname.current,
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
}));

beforeEach(() => {
  pathname.current = "/company";
});

function renderFrame(role: CompanyRole = "owner") {
  return render(
    <CompanyFrame companyName="Fake Test Company" userName="Fake Owner" role={role}>
      <p>Page content</p>
    </CompanyFrame>,
  );
}

const sidebar = () => screen.getByRole("navigation", { name: "Company" });

describe("sidebar items", () => {
  it("shows the owner all five main items linking under /company", () => {
    renderFrame();
    const expected = {
      Dashboard: "/company",
      Projects: "/company/projects",
      Team: "/company/team",
      "Usage and Billing": "/company/billing",
    };
    for (const [name, href] of Object.entries(expected)) {
      expect(within(sidebar()).getByRole("link", { name }).getAttribute("href")).toBe(href);
    }
    expect(within(sidebar()).getByRole("button", { name: "Settings" })).toBeTruthy();
    expect(within(sidebar()).getByRole("button", { name: "Advanced" })).toBeTruthy();
  });

  it("hides Team, Usage and Billing, Settings and Advanced from members", () => {
    renderFrame("member");
    expect(within(sidebar()).getByRole("link", { name: "Dashboard" })).toBeTruthy();
    expect(within(sidebar()).getByRole("link", { name: "Projects" })).toBeTruthy();
    for (const name of ["Team", "Usage and Billing", "Settings", "Advanced"]) {
      expect(within(sidebar()).queryByRole("link", { name })).toBeNull();
      expect(within(sidebar()).queryByRole("button", { name })).toBeNull();
    }
  });

  it("highlights only the current page", () => {
    pathname.current = "/company/projects/42";
    renderFrame();
    const current = within(sidebar())
      .getAllByRole("link")
      .filter((link) => link.getAttribute("aria-current") === "page");
    expect(current.map((link) => link.textContent)).toEqual(["Projects"]);
  });

  it("highlights the Dashboard on its own address", () => {
    renderFrame();
    expect(
      within(sidebar()).getByRole("link", { name: "Dashboard" }).getAttribute("aria-current"),
    ).toBe("page");
  });
});

describe("Settings sub-menu", () => {
  it("is closed until clicked, then opens and closes on click", async () => {
    const user = userEvent.setup();
    renderFrame();
    const settings = within(sidebar()).getByRole("button", { name: "Settings" });

    expect(settings.getAttribute("aria-expanded")).toBe("false");
    expect(within(sidebar()).queryByRole("link", { name: "Profile" })).toBeNull();

    await user.click(settings);
    expect(settings.getAttribute("aria-expanded")).toBe("true");
    for (const name of ["Profile", "Company"]) {
      expect(within(sidebar()).getByRole("link", { name }).getAttribute("href")).toBe(
        `/company/settings/${name.toLowerCase()}`,
      );
    }
    for (const name of ["Retention", "Scoring defaults", "Security", "Defaults"]) {
      expect(within(sidebar()).queryByRole("link", { name })).toBeNull();
    }

    await user.click(settings);
    expect(within(sidebar()).queryByRole("link", { name: "Profile" })).toBeNull();
  });

  it("stays closed on a settings page, but marks Settings and the page as current", async () => {
    const user = userEvent.setup();
    pathname.current = "/company/settings/company";
    renderFrame();
    const settings = within(sidebar()).getByRole("button", { name: "Settings" });

    expect(settings.getAttribute("aria-expanded")).toBe("false");
    expect(settings.getAttribute("data-active")).toBe("true");

    await user.click(settings);
    expect(
      within(sidebar()).getByRole("link", { name: "Company" }).getAttribute("aria-current"),
    ).toBe("page");
    expect(
      within(sidebar()).getByRole("link", { name: "Profile" }).getAttribute("aria-current"),
    ).toBeNull();
  });

  it("is not marked current away from the settings pages", () => {
    renderFrame();
    expect(
      within(sidebar()).getByRole("button", { name: "Settings" }).getAttribute("data-active"),
    ).toBe("false");
  });
});

describe("Advanced section", () => {
  const advancedPages = {
    "Scoring defaults": "/company/advanced/defaults",
    Retention: "/company/advanced/retention",
    Security: "/company/advanced/security",
    Notifications: "/company/advanced/notifications",
    "Data and export": "/company/advanced/data",
  };

  it("sits below Settings, set apart by a divider", () => {
    renderFrame();
    const settings = within(sidebar()).getByRole("button", { name: "Settings" }).closest("li")!;
    const advanced = within(sidebar()).getByRole("button", { name: "Advanced" }).closest("li")!;

    expect(settings.compareDocumentPosition(advanced)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
    expect(advanced.getAttribute("data-separated")).toBe("true");
    expect(settings.hasAttribute("data-separated")).toBe(false);
  });

  it("has its own outline and filled icon", () => {
    renderFrame();
    const advanced = within(sidebar()).getByRole("button", { name: "Advanced" });
    expect(advanced.querySelector(".ui-toggle-icon__outline")).not.toBeNull();
    expect(advanced.querySelector(".ui-toggle-icon__filled")).not.toBeNull();
  });

  it("opens only on click, with its five pages, and closes on click", async () => {
    const user = userEvent.setup();
    renderFrame();
    const advanced = within(sidebar()).getByRole("button", { name: "Advanced" });

    expect(advanced.getAttribute("aria-expanded")).toBe("false");
    expect(within(sidebar()).queryByRole("link", { name: "Retention" })).toBeNull();

    await user.click(advanced);
    for (const [name, href] of Object.entries(advancedPages)) {
      expect(within(sidebar()).getByRole("link", { name }).getAttribute("href")).toBe(href);
    }

    await user.click(advanced);
    expect(within(sidebar()).queryByRole("link", { name: "Retention" })).toBeNull();
  });

  it("opens one sub-menu at a time", async () => {
    const user = userEvent.setup();
    renderFrame();

    await user.click(within(sidebar()).getByRole("button", { name: "Settings" }));
    await user.click(within(sidebar()).getByRole("button", { name: "Advanced" }));

    expect(within(sidebar()).queryByRole("link", { name: "Profile" })).toBeNull();
    expect(within(sidebar()).getByRole("link", { name: "Retention" })).toBeTruthy();
  });

  it("highlights the current Advanced page and marks Advanced as current", async () => {
    const user = userEvent.setup();
    pathname.current = "/company/advanced/retention";
    renderFrame();
    const advanced = within(sidebar()).getByRole("button", { name: "Advanced" });

    expect(advanced.getAttribute("data-active")).toBe("true");
    expect(
      within(sidebar()).getByRole("button", { name: "Settings" }).getAttribute("data-active"),
    ).toBe("false");

    await user.click(advanced);
    expect(
      within(sidebar()).getByRole("link", { name: "Retention" }).getAttribute("aria-current"),
    ).toBe("page");
    expect(
      within(sidebar()).getByRole("link", { name: "Security" }).getAttribute("aria-current"),
    ).toBeNull();
  });

  it("shows the page to an owner who opens an Advanced address", () => {
    pathname.current = "/company/advanced/retention";
    renderFrame("owner");
    expect(screen.getByRole("main").textContent).toBe("Page content");
  });

  it.each(["/company/advanced", "/company/advanced/retention", "/company/advanced/data"])(
    "shows a member who types %s the no-access page, inside the frame",
    (address) => {
      pathname.current = address;
      renderFrame("member");
      expect(screen.getByRole("heading", { name: "You do not have access" })).toBeTruthy();
      expect(screen.queryByText("Page content")).toBeNull();
      expect(screen.getByRole("navigation", { name: "Company" })).toBeTruthy();
    },
  );

  it("still shows members their own pages and does not block look-alike addresses", () => {
    for (const address of ["/company/projects", "/company/advanced-old"]) {
      pathname.current = address;
      const { unmount } = renderFrame("member");
      expect(screen.getByRole("main").textContent).toBe("Page content");
      unmount();
    }
  });
});

describe("top bar", () => {
  it("shows the company name and a New project link, with no theme switch", () => {
    renderFrame();
    const bar = screen.getByRole("banner");
    expect(within(bar).getByText("Fake Test Company")).toBeTruthy();
    expect(within(bar).queryByRole("switch")).toBeNull();
    expect(within(bar).getByRole("link", { name: "New project" }).getAttribute("href")).toBe(
      "/company/projects/new",
    );
  });

  it("opens the user menu with Profile and Log out", async () => {
    const user = userEvent.setup();
    renderFrame();
    expect(screen.queryByRole("menuitem")).toBeNull();

    await user.click(screen.getByRole("button", { name: "User menu" }));
    expect(screen.getByRole("menuitem", { name: "Profile" }).getAttribute("href")).toBe(
      "/company/settings/profile",
    );
    expect(screen.getByRole("menuitem", { name: "Log out" })).toBeTruthy();
  });

  it("shows the New project button and user menu to members too", () => {
    renderFrame("member");
    expect(screen.getByRole("link", { name: "New project" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "User menu" })).toBeTruthy();
  });
});

describe("phone slide-out menu", () => {
  it("opens and closes from the menu button", async () => {
    const user = userEvent.setup();
    const { container } = renderFrame();
    const button = screen.getByRole("button", { name: "Menu" });
    const frame = container.querySelector(".panel-frame")!;

    expect(frame.getAttribute("data-menu-open")).toBe("false");
    await user.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    expect(frame.getAttribute("data-menu-open")).toBe("true");
    await user.click(button);
    expect(frame.getAttribute("data-menu-open")).toBe("false");
  });

  it("closes with Escape and when the dimmed area is clicked", async () => {
    const user = userEvent.setup();
    const { container } = renderFrame();
    const frame = container.querySelector(".panel-frame")!;
    const button = screen.getByRole("button", { name: "Menu" });

    await user.click(button);
    await user.keyboard("{Escape}");
    expect(frame.getAttribute("data-menu-open")).toBe("false");

    await user.click(button);
    await user.click(container.querySelector(".panel-scrim")!);
    expect(frame.getAttribute("data-menu-open")).toBe("false");
  });

  it("closes after the user moves to another page", async () => {
    const user = userEvent.setup();
    const { container, rerender } = renderFrame();
    await user.click(screen.getByRole("button", { name: "Menu" }));

    pathname.current = "/company/projects";
    rerender(
      <CompanyFrame companyName="Fake Test Company" userName="Fake Owner" role="owner">
        <p>Page content</p>
      </CompanyFrame>,
    );
    expect(container.querySelector(".panel-frame")!.getAttribute("data-menu-open")).toBe("false");
  });
});

describe("frame", () => {
  it("shows the page between the sidebar and the top bar", () => {
    renderFrame();
    expect(screen.getByRole("main").textContent).toBe("Page content");
  });

  it("shows pages that are not built yet as not found, inside the frame", () => {
    expect(() => MissingCompanyPage()).toThrow("NEXT_NOT_FOUND");
    render(<CompanyNotFound />);
    expect(screen.getByRole("heading", { name: "This page could not be found" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Go home" }).getAttribute("href")).toBe("/company");
  });
});
