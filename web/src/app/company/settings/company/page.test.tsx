import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import CompanySettingsPage from "./page";
describe("company settings page", () => {
  it("shows the Company name field and Save", () => {
    render(<CompanySettingsPage />);
    expect(screen.getByLabelText("Company name")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save" })).toBeTruthy();
  });

  it("does nothing when a button is pressed", async () => {
    const { container } = render(<CompanySettingsPage />);
    const before = container.innerHTML;
    for (const button of screen.getAllByRole("button")) await userEvent.click(button);
    expect(container.innerHTML).toBe(before);
  });
});
