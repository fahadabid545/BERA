import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import TeamPage from "./page";

describe("team page", () => {
  it("shows the Invite member button and nothing else", () => {
    const { container } = render(<TeamPage />);
    expect(screen.getByRole("button", { name: "Invite member" })).toBeTruthy();
    expect(container.querySelectorAll("button, a, input, select, textarea")).toHaveLength(1);
  });

  it("does nothing when pressed", async () => {
    const { container } = render(<TeamPage />);
    const before = container.innerHTML;
    await userEvent.click(screen.getByRole("button", { name: "Invite member" }));
    expect(container.innerHTML).toBe(before);
  });
});
