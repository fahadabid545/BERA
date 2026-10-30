import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import PlatformValuesPage from "./page";

describe("Platform values page", () => {
  it("shows its buttons and nothing else", () => {
    const { container } = render(<PlatformValuesPage />);
    expect(screen.getByRole("button", { name: "Save" })).toBeTruthy();
    expect(container.querySelectorAll("button, a, input, select, textarea")).toHaveLength(1);
  });

  it("does nothing when a button is pressed", async () => {
    const { container } = render(<PlatformValuesPage />);
    const before = container.innerHTML;
    for (const button of screen.getAllByRole("button")) await userEvent.click(button);
    expect(container.innerHTML).toBe(before);
  });
});
