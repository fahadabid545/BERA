import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import FeaturesPage from "./page";

describe("features page", () => {
  it("has one Get started button going to Sign up", () => {
    render(<FeaturesPage />);
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(1);
    expect(links[0].getAttribute("href")).toBe("/signup");
    expect(links[0].textContent).toBe("Get started");
  });

  it("has no other text, headings or images", () => {
    const { container } = render(<FeaturesPage />);
    expect(container.textContent).toBe("Get started");
    expect(container.querySelector("img, h1, h2, p, section")).toBeNull();
  });
});
