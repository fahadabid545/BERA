import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import PlansPage from "./page";

describe("plans page", () => {
  it("shows the New plan button and nothing else", () => {
    const { container } = render(<PlansPage />);
    expect(screen.getByRole("button", { name: "New plan" })).toBeTruthy();
    expect(container.querySelectorAll("button, a, input, select, textarea")).toHaveLength(1);
  });

  it("does nothing when a button is pressed", async () => {
    const { container } = render(<PlansPage />);
    const before = container.innerHTML;
    for (const button of screen.getAllByRole("button")) await userEvent.click(button);
    expect(container.innerHTML).toBe(before);
  });
});
