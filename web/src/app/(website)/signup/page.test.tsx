import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import SignUpPage from "./page";

describe("sign up page", () => {
  it("shows every labelled field and the Create account button", () => {
    render(<SignUpPage />);
    for (const label of ["Company name", "Your name", "Email", "Password"]) {
      expect(screen.getByLabelText(label)).toBeTruthy();
    }
    expect((screen.getByLabelText("Password") as HTMLInputElement).type).toBe("password");
    expect(screen.getByRole("button", { name: "Create account" })).toBeTruthy();
  });

  it("has the acceptance checkbox with Terms and Privacy Policy linking to their pages", () => {
    render(<SignUpPage />);
    expect(
      screen.getByRole("checkbox", { name: /I accept the Terms and Privacy Policy/ }),
    ).toBeTruthy();
    expect(screen.getByRole("link", { name: "Terms" }).getAttribute("href")).toBe("/terms");
    expect(screen.getByRole("link", { name: "Privacy Policy" }).getAttribute("href")).toBe(
      "/privacy",
    );
  });

  it("links back to Log in", () => {
    render(<SignUpPage />);
    expect(
      screen.getByRole("link", { name: "Already have an account? Log in" }).getAttribute("href"),
    ).toBe("/login");
  });

  it("does nothing when Create account is pressed", async () => {
    render(<SignUpPage />);
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(screen.getByRole("button", { name: "Create account" })).toBeTruthy();
  });
});
