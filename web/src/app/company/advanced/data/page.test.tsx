import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import DataPage from "./page";

describe("data and export page", () => {
  it("shows Export data and Delete company and nothing else", () => {
    const { container } = render(<DataPage />);
    expect(screen.getByRole("button", { name: "Export data" })).toBeTruthy();
    expect(container.querySelectorAll("button, a, input, select, textarea")).toHaveLength(2);
  });

  it("gives Delete company the danger style", () => {
    render(<DataPage />);
    expect(screen.getByRole("button", { name: "Delete company" }).className).toContain(
      "ui-button--danger",
    );
  });

  it("does nothing when a button is pressed", async () => {
    const { container } = render(<DataPage />);
    const before = container.innerHTML;
    for (const button of screen.getAllByRole("button")) await userEvent.click(button);
    expect(container.innerHTML).toBe(before);
  });
});
