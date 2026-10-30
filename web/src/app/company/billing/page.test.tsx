import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import BillingPage from "./page";describe("usage and billing page", () => {
  it("shows Upgrade plan and Manage billing and nothing else", () => {
    const { container } = render(<BillingPage />);
    expect(screen.getByRole("button", { name: "Upgrade plan" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Manage billing" })).toBeTruthy();
    expect(container.querySelectorAll("button, a, input, select, textarea")).toHaveLength(2);
  });

  it("does nothing when a button is pressed", async () => {
    const { container } = render(<BillingPage />);
    const before = container.innerHTML;
    for (const button of screen.getAllByRole("button")) await userEvent.click(button);
    expect(container.innerHTML).toBe(before);
  });
});
