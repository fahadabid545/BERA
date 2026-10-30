import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import RateLimitsPage from "./page";

describe("Rate limiting page", () => {
  it("shows its buttons and nothing else", () => {
    const { container } = render(<RateLimitsPage />);
    expect(screen.getByRole("button", { name: "Save" })).toBeTruthy();
    expect(container.querySelectorAll("button, a, input, select, textarea")).toHaveLength(1);
  });

  it("does nothing when a button is pressed", async () => {
    const { container } = render(<RateLimitsPage />);
    const before = container.innerHTML;
    for (const button of screen.getAllByRole("button")) await userEvent.click(button);
    expect(container.innerHTML).toBe(before);
  });
});
