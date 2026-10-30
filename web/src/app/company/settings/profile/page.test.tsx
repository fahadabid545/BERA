import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import ProfilePage from "./page";
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
