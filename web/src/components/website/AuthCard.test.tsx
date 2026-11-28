import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import VerifyEmailPage from "@/app/(website)/verify-email/page";
import SignUpPage from "@/app/(website)/signup/page";

import { AuthCard } from "./AuthCard";

describe("AuthCard", () => {
  it("shows the page title as the one heading, with the content on a tinted card", () => {
    const { container } = render(
      <AuthCard title="Log in" tint="sky">
        <p>Fake content</p>
      </AuthCard>,
    );
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Log in");
    const card = container.querySelector(".auth-card")!;
    expect(card.getAttribute("data-tint")).toBe("sky");
    expect(card.textContent).toBe("Fake content");
  });

  it("frames the sign up page", () => {
    render(<SignUpPage />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Sign up");
  });

  it("frames verify email both with and without a link token", async () => {
    render(await VerifyEmailPage({ searchParams: Promise.resolve({ token: "fake" }) }));
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Verify email");
    expect(screen.getByRole("button", { name: "Verify email" })).toBeTruthy();
  });
});
