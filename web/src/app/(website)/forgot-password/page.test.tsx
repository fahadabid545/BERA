import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import ForgotPasswordPage from "./page";

describe("forgot password page", () => {
  it("shows a labelled Email field and the Send reset link button", () => {
    render(<ForgotPasswordPage />);
    expect((screen.getByLabelText("Email") as HTMLInputElement).type).toBe("email");
    expect(screen.getByRole("button", { name: "Send reset link" })).toBeTruthy();
  });

  it("links back to Login", () => {
    render(<ForgotPasswordPage />);
    expect(screen.getByRole("link", { name: "Back to Log in" }).getAttribute("href")).toBe(
      "/login",
    );
  });

  it("does nothing when Send reset link is pressed", async () => {
    render(<ForgotPasswordPage />);
    await userEvent.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(screen.getByRole("button", { name: "Send reset link" })).toBeTruthy();
  });
});
