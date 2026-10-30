import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import WebsiteHome from "./page";

describe("website home page", () => {
  it("has Get started going to Sign up and See pricing going to Pricing", () => {
    render(<WebsiteHome />);
    expect(screen.getByRole("link", { name: "Get started" }).getAttribute("href")).toBe("/signup");
    expect(screen.getByRole("link", { name: "See pricing" }).getAttribute("href")).toBe("/pricing");
  });

  it("has no text, headings or images besides the two buttons", () => {
    const { container } = render(<WebsiteHome />);
    expect(within(container).getAllByRole("link")).toHaveLength(2);
    expect(container.textContent).toBe("Get startedSee pricing");
    expect(container.querySelector("img, h1, h2, p, section")).toBeNull();
  });
});
