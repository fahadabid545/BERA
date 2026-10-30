import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import LoginPage from "./page";

describe("login page", () => {
  it("shows labelled Email and Password fields and a Log in button", () => {
    render(<LoginPage />);
    expect((screen.getByLabelText("Email") as HTMLInputElement).type).toBe("email");
    expect((screen.getByLabelText("Password") as HTMLInputElement).type).toBe("password");
    expect(screen.getByRole("button", { name: "Log in" })).toBeTruthy();
  });

  it("links to the forgot password page and to Sign up", () => {
    render(<LoginPage />);
    expect(screen.getByRole("link", { name: "Forgot password?" }).getAttribute("href")).toBe(
      "/forgot-password",
    );
    expect(screen.getByRole("link", { name: "Create an account" }).getAttribute("href")).toBe(
      "/signup",
    );
  });

  it("offers to resend the verification email", () => {
    render(<LoginPage />);
    expect(
      screen.getByRole("link", { name: "Resend verification email" }).getAttribute("href"),
    ).toBe("/verify-email");
  });

  it("does nothing when Log in is pressed", async () => {
    render(<LoginPage />);
    await userEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect(screen.getByRole("button", { name: "Log in" })).toBeTruthy();
  });
});
