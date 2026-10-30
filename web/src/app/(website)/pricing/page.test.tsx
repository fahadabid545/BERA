import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import PricingPage from "./page";

describe("pricing page", () => {
  it("has one Choose plan button that does nothing yet", () => {
    const { container } = render(<PricingPage />);
    const button = screen.getByRole("button", { name: "Choose plan" });
    expect(button.getAttribute("type")).toBe("button");
    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(container.textContent).toBe("Choose plan");
  });

  it("has no plan cards, headings or links", () => {
    const { container } = render(<PricingPage />);
    expect(container.querySelector("a, h1, h2, p, section, img")).toBeNull();
  });
});
