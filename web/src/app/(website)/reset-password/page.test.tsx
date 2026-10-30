import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import ResetPasswordPage from "./page";

describe("reset password page", () => {
  it("shows labelled New password and Confirm password fields and the Save password button", () => {
    render(<ResetPasswordPage />);
    expect((screen.getByLabelText("New password") as HTMLInputElement).type).toBe("password");
    expect((screen.getByLabelText("Confirm password") as HTMLInputElement).type).toBe("password");
    expect(screen.getByRole("button", { name: "Save password" })).toBeTruthy();
  });

  it("does nothing when Save password is pressed", async () => {
    render(<ResetPasswordPage />);
    await userEvent.click(screen.getByRole("button", { name: "Save password" }));
    expect(screen.getByRole("button", { name: "Save password" })).toBeTruthy();
  });
});
