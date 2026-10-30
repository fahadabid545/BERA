import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ProfilePage from "./page";
beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify({ rules: [], ok: false }), { status: 200 })),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("profile settings page", () => {
  it("shows the profile fields, the password section and Save", () => {
    render(<ProfilePage />);
    expect(screen.getByLabelText("Name")).toBeTruthy();
    expect((screen.getByLabelText("Email") as HTMLInputElement).type).toBe("email");
    const section = screen.getByRole("region", { name: "Change password" });
    for (const label of ["Current password", "New password", "Confirm new password"]) {
      const field = screen.getByLabelText(label) as HTMLInputElement;
      expect(field.type).toBe("password");
      expect(section.contains(field)).toBe(true);
    }
    expect(screen.getByRole("button", { name: "Save" })).toBeTruthy();
  });

  it("has a button of its own to change the password", () => {
    render(<ProfilePage />);
    const section = screen.getByRole("region", { name: "Change password" });
    expect(section.querySelector("button")?.textContent).toBe("Change password");
  });

  it("offers to sign out of all devices", () => {
    render(<ProfilePage />);
    expect(screen.getByRole("button", { name: "Sign out of all devices" })).toBeTruthy();
  });

  it("does nothing when Save is pressed", async () => {
    const { container } = render(<ProfilePage />);
    const before = container.innerHTML;
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(container.innerHTML).toBe(before);
  });
});
