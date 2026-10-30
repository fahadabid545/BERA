import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import ProjectSettingsPage from "./page";

describe("ProjectSettingsPage", () => {
  it("shows its buttons and nothing else", () => {
    const { container } = render(<ProjectSettingsPage />);
    expect(screen.getByRole("button", { name: "Save" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Archive project" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Delete project" })).toBeTruthy();
    expect(container.querySelectorAll("button, a, input, select, textarea")).toHaveLength(3);
  });

  it("does nothing when a button is pressed", async () => {
    const { container } = render(<ProjectSettingsPage />);
    const before = container.innerHTML;
    for (const button of screen.getAllByRole("button")) await userEvent.click(button);
    expect(container.innerHTML).toBe(before);
  });
});

it("gives Delete project the danger style", () => {
  render(<ProjectSettingsPage />);
  expect(screen.getByRole("button", { name: "Delete project" }).className).toContain(
    "ui-button--danger",
  );
});
