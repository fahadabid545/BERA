import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import AdminUsersPage from "./page";

describe("Admin users page", () => {
  it("shows its buttons and nothing else", () => {
    const { container } = render(<AdminUsersPage />);
    expect(screen.getByRole("button", { name: "Invite admin" })).toBeTruthy();
    expect(container.querySelectorAll("button, a, input, select, textarea")).toHaveLength(1);
  });

  it("does nothing when a button is pressed", async () => {
    const { container } = render(<AdminUsersPage />);
    const before = container.innerHTML;
    for (const button of screen.getAllByRole("button")) await userEvent.click(button);
    expect(container.innerHTML).toBe(before);
  });
});
