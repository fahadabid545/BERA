import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import CompaniesPage from "./page";

describe("companies page", () => {
  it("shows a Search box and a Filters button and nothing else", () => {
    const { container } = render(<CompaniesPage />);
    expect((screen.getByLabelText("Search") as HTMLInputElement).type).toBe("search");
    expect(screen.getByRole("button", { name: "Filters" })).toBeTruthy();
    expect(container.querySelectorAll("button, a, input, select, textarea")).toHaveLength(2);
  });

  it("does nothing when a button is pressed", async () => {
    const { container } = render(<CompaniesPage />);
    const before = container.innerHTML;
    for (const button of screen.getAllByRole("button")) await userEvent.click(button);
    expect(container.innerHTML).toBe(before);
  });
});
