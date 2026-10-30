import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import CompanyDetailPage from "./page";

const DANGER = ["Suspend", "Terminate subscription", "Block member"];
const OTHER = ["Grant free subscription", "Change limits"];

describe("company detail page", () => {
  it("shows the five buttons and nothing else", () => {
    const { container } = render(<CompanyDetailPage />);
    for (const name of [...DANGER, ...OTHER]) {
      expect(screen.getByRole("button", { name })).toBeTruthy();
    }
    expect(container.querySelectorAll("button, a, input, select, textarea")).toHaveLength(5);
  });

  it("gives the destructive buttons the danger style and the others not", () => {
    render(<CompanyDetailPage />);
    for (const name of DANGER) {
      expect(screen.getByRole("button", { name }).className).toContain("ui-button--danger");
    }
    for (const name of OTHER) {
      expect(screen.getByRole("button", { name }).className).not.toContain("ui-button--danger");
    }
  });

  it("does nothing when a button is pressed", async () => {
    const { container } = render(<CompanyDetailPage />);
    const before = container.innerHTML;
    for (const button of screen.getAllByRole("button")) await userEvent.click(button);
    expect(container.innerHTML).toBe(before);
  });
});
