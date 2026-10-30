import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import NotFound from "@/app/not-found";

import { SiteFrame } from "./SiteFrame";

const pathname = vi.hoisted(() => ({ current: "/" }));
vi.mock("next/navigation", () => ({ usePathname: () => pathname.current }));

beforeEach(() => {
  pathname.current = "/";
});

function renderFrame() {
  return render(
    <SiteFrame>
      <p>Page content</p>
    </SiteFrame>,
  );
}

describe("header", () => {
  it("shows the product name linking home, the five links and the two buttons", () => {
    renderFrame();
    const main = screen.getByRole("navigation", { name: "Main" });

    expect(screen.getByRole("link", { name: "Bera" }).getAttribute("href")).toBe("/");
    const expected = {
      Features: "/features",
      "How it works": "/how-it-works",
      Pricing: "/pricing",
      FAQ: "/faq",
      Contact: "/contact",
      "Log in": "/login",
      "Sign up": "/signup",
    };
    for (const [name, href] of Object.entries(expected)) {
      expect(within(main).getByRole("link", { name }).getAttribute("href")).toBe(href);
    }
  });

  it("highlights only the page the visitor is on", () => {
    pathname.current = "/pricing";
    renderFrame();
    const main = screen.getByRole("navigation", { name: "Main" });

    const current = within(main)
      .getAllByRole("link")
      .filter((link) => link.getAttribute("aria-current") === "page");
    expect(current.map((link) => link.textContent)).toEqual(["Pricing"]);
  });

  it("gives every main link an outline and a filled icon for the current-page swap", () => {
    renderFrame();
    const main = screen.getByRole("navigation", { name: "Main" });
    expect(main.querySelectorAll(".ui-toggle-icon__outline")).toHaveLength(5);
    expect(main.querySelectorAll(".ui-toggle-icon__filled")).toHaveLength(5);
  });

  it("highlights nothing on the home page", () => {
    renderFrame();
    expect(document.querySelector('[aria-current="page"]')).toBeNull();
  });

  it("opens and closes the phone menu from the menu button", async () => {
    const user = userEvent.setup();
    renderFrame();
    const button = screen.getByRole("button", { name: "Menu" });
    const menu = screen.getByRole("navigation", { name: "Main" });

    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(menu.getAttribute("data-open")).toBe("false");
    await user.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    expect(menu.getAttribute("data-open")).toBe("true");
    await user.click(button);
    expect(menu.getAttribute("data-open")).toBe("false");
  });

  it("closes the phone menu with Escape", async () => {
    const user = userEvent.setup();
    renderFrame();
    const button = screen.getByRole("button", { name: "Menu" });

    await user.click(button);
    await user.keyboard("{Escape}");
    expect(button.getAttribute("aria-expanded")).toBe("false");
  });
});

describe("footer", () => {
  it("shows Terms, Privacy, Contact, the Avennex line and the current year", () => {
    renderFrame();
    const footer = screen.getByRole("contentinfo");

    for (const [name, href] of [
      ["Terms", "/terms"],
      ["Privacy", "/privacy"],
      ["Contact", "/contact"],
    ]) {
      expect(within(footer).getByRole("link", { name }).getAttribute("href")).toBe(href);
    }
    expect(footer.textContent).toContain("A product of Avennex");
    expect(footer.textContent).toContain(String(new Date().getFullYear()));
  });
});

describe("frame", () => {
  it("keeps the page content in the same column as the header and footer", () => {
    renderFrame();
    expect(screen.getByRole("main").querySelector(".site-container")).toBeTruthy();
  });

  it("puts the page content between the header and the footer", () => {
    renderFrame();
    const main = screen.getByRole("main");
    expect(main.textContent).toBe("Page content");
    expect(screen.getByRole("banner").compareDocumentPosition(main)).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
    expect(main.compareDocumentPosition(screen.getByRole("contentinfo"))).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });

  it("shows the not-found page inside the same frame", () => {
    render(<NotFound />);
    expect(screen.getByRole("heading", { name: "Page not found" })).toBeTruthy();
    expect(screen.getByRole("banner")).toBeTruthy();
    expect(screen.getByRole("contentinfo")).toBeTruthy();
  });
});
