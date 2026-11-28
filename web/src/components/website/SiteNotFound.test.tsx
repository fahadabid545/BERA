import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SiteNotFound } from "./SiteNotFound";

describe("SiteNotFound", () => {
  it("shows the heading and a Go home button, with the big 404 as decoration", () => {
    const { container } = render(<SiteNotFound homeHref="/" />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(
      "This page could not be found",
    );
    expect(screen.getByRole("link", { name: "Go home" }).getAttribute("href")).toBe("/");
    expect(container.querySelector(".site-not-found__code")?.getAttribute("aria-hidden")).toBe(
      "true",
    );
  });
});
