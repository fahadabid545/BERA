import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import RetentionPage from "./page";describe("retention settings page", () => {
  it("offers 30, 90, 180 and 365 days and a Save button", () => {
    render(<RetentionPage />);
    const selector = screen.getByLabelText("Retention") as HTMLSelectElement;
    expect(Array.from(selector.options).map((option) => option.text)).toEqual([
      "30 days",
      "90 days",
      "180 days",
      "365 days",
    ]);
    expect(screen.getByRole("button", { name: "Save" })).toBeTruthy();
  });

  it("lets the choice change", async () => {
    render(<RetentionPage />);
    const selector = screen.getByLabelText("Retention") as HTMLSelectElement;
    await userEvent.selectOptions(selector, "180 days");
    expect(selector.value).toBe("180");
  });

  it("does nothing when a button is pressed", async () => {
    const { container } = render(<RetentionPage />);
    const before = container.innerHTML;
    for (const button of screen.getAllByRole("button")) await userEvent.click(button);
    expect(container.innerHTML).toBe(before);
  });
});
