import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import SecurityPage from "./page";
describe("security page", () => {
  it("shows both buttons and nothing else", () => {
    const { container } = render(<SecurityPage />);
    expect(screen.getByRole("button", { name: "Set up two-step verification" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sign out of all devices" })).toBeTruthy();
    expect(container.querySelectorAll("button, a, input, select, textarea")).toHaveLength(2);
  });

  it("does nothing when a button is pressed", async () => {
    const { container } = render(<SecurityPage />);
    const before = container.innerHTML;
    for (const button of screen.getAllByRole("button")) await userEvent.click(button);
    expect(container.innerHTML).toBe(before);
  });
});
