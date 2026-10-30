import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import ForgotPasswordPage from "./page";

const MESSAGE = "If an account exists, we sent a reset link";

function stubServer(status: number, body: unknown) {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

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

  it("sends the email and always shows the same answer in a popup", async () => {
    const server = stubServer(200, { status: "ok", message: MESSAGE });
    render(<ForgotPasswordPage />);
    await userEvent.type(screen.getByLabelText("Email"), "owner@example.test");
    await userEvent.click(screen.getByRole("button", { name: "Send reset link" }));
    const popup = await screen.findByRole("dialog");
    expect(within(popup).getByText(MESSAGE)).toBeTruthy();
    const [path, init] = server.mock.calls[0] as unknown as [string, RequestInit];
    expect(path).toBe("/api/auth/company/forgot-password/");
    expect(JSON.parse(String(init.body))).toEqual({ email: "owner@example.test" });
  });

  it("says when 5 per hour is reached", async () => {
    stubServer(429, {
      error: { code: "too_many_requests", message: "Too many attempts. Try again in 40 minutes." },
    });
    render(<ForgotPasswordPage />);
    await userEvent.type(screen.getByLabelText("Email"), "owner@example.test");
    await userEvent.click(screen.getByRole("button", { name: "Send reset link" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Too many attempts. Try again in 40 minutes.",
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("shows a mistake in the email next to the field", async () => {
    stubServer(400, {
      error: {
        code: "validation_error",
        message: "x",
        fields: { email: "Enter a valid email address." },
      },
    });
    render(<ForgotPasswordPage />);
    await userEvent.type(screen.getByLabelText("Email"), "nonsense");
    await userEvent.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(await screen.findByText("Enter a valid email address.")).toBeTruthy();
    expect(screen.getByLabelText("Email").getAttribute("aria-invalid")).toBe("true");
  });

  it("cannot be pressed again while waiting", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => {})),
    );
    render(<ForgotPasswordPage />);
    await userEvent.click(screen.getByRole("button", { name: "Send reset link" }));
    expect(
      (await screen.findByRole("button", { name: "Send reset link" })).hasAttribute("disabled"),
    ).toBe(true);
  });
});
