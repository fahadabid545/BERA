import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import AiControlsPage from "./page";

describe("AI controls page", () => {
  it("shows its buttons and nothing else", () => {
    const { container } = render(<AiControlsPage />);
    expect(screen.getByRole("button", { name: "Pause all AI" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Resume AI" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save" })).toBeTruthy();
    expect(container.querySelectorAll("button, a, input, select, textarea")).toHaveLength(3);
  });

  it("does nothing when a button is pressed", async () => {
    const { container } = render(<AiControlsPage />);
    const before = container.innerHTML;
    for (const button of screen.getAllByRole("button")) await userEvent.click(button);
    expect(container.innerHTML).toBe(before);
  });
});

it("gives Pause all AI the danger style", () => {
  render(<AiControlsPage />);
  expect(screen.getByRole("button", { name: "Pause all AI" }).className).toContain(
    "ui-button--danger",
  );
});
