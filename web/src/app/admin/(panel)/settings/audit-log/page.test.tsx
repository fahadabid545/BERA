import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import AuditLogPage from "./page";

describe("Audit log page", () => {
  it("shows its buttons and nothing else", () => {
    const { container } = render(<AuditLogPage />);
    expect(screen.getByRole("button", { name: "Filters" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Export" })).toBeTruthy();
    expect(container.querySelectorAll("button, a, input, select, textarea")).toHaveLength(2);
  });

  it("does nothing when a button is pressed", async () => {
    const { container } = render(<AuditLogPage />);
    const before = container.innerHTML;
    for (const button of screen.getAllByRole("button")) await userEvent.click(button);
    expect(container.innerHTML).toBe(before);
  });
});
