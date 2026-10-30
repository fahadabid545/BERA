import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import PlanEditorPage from "./page";

describe("plan editor page", () => {
  it("shows Save plan and Archive plan and nothing else", () => {
    const { container } = render(<PlanEditorPage />);
    expect(screen.getByRole("button", { name: "Save plan" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Archive plan" })).toBeTruthy();
    expect(container.querySelectorAll("button, a, input, select, textarea")).toHaveLength(2);
  });

  it("does nothing when a button is pressed", async () => {
    const { container } = render(<PlanEditorPage />);
    const before = container.innerHTML;
    for (const button of screen.getAllByRole("button")) await userEvent.click(button);
    expect(container.innerHTML).toBe(before);
  });
});
