import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AdminAcceptInviteForm } from "./AdminAcceptInviteForm";

const GOOD = "copper-meadow-lantern-58"; // nosecret: fake test value
const answers: { status: number; body: unknown }[] = [];
const reply = (status: number, body: unknown) => answers.push({ status, body });
// The password hints ask the server too; those questions are answered with nothing to show.
const fetchMock = vi.fn(async (path: string) => {
  if (path.endsWith("/password-check/")) return new Response(JSON.stringify({ rules: [] }));
  const next = answers.shift() ?? { status: 500, body: {} };
  return new Response(JSON.stringify(next.body), { status: next.status });
});
const accepts = () => fetchMock.mock.calls.filter(([path]) => path.endsWith("/accept-invite/"));

async function fill(password: string, confirm: string) {
  await userEvent.type(screen.getByLabelText("Password"), password);
  await userEvent.type(screen.getByLabelText("Confirm password"), confirm);
  await userEvent.click(screen.getByRole("button", { name: "Set password" }));
}

beforeEach(() => {
  fetchMock.mockClear();
  answers.length = 0;
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Admin invitation page", () => {
  it("sets the password and then points to the admin sign-in", async () => {
    reply(200, { status: "ok" });
    render(<AdminAcceptInviteForm token="fake-token" />);
    await fill(GOOD, GOOD);
    expect((await screen.findByRole("status")).textContent).toBe(
      "Your account is ready. Sign in to continue.",
    );
    expect(screen.getByRole("link", { name: "Sign in" }).getAttribute("href")).toBe("/admin/login");
    const [path, init] = accepts()[0] as unknown as [string, RequestInit];
    expect(path).toBe("/api/auth/admin/accept-invite/");
    expect(JSON.parse(String(init.body))).toEqual({
      token: "fake-token",
      password: GOOD,
      confirm_password: GOOD,
    });
  });

  it("shows the password message and keeps the form so the link can be tried again", async () => {
    reply(400, {
      error: {
        code: "validation_error",
        message: "Please check the form and try again.",
        fields: { password: "Use at least 12 characters." },
      },
    });
    render(<AdminAcceptInviteForm token="fake-token" />);
    await fill("short", "short");
    expect(await screen.findByText("Use at least 12 characters.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Set password" })).toBeTruthy();
  });

  it.each(["link_used", "link_expired", "link_invalid"])(
    "says so in words when the link is %s",
    async (code) => {
      reply(400, { error: { code, message: "This link cannot be used." } });
      render(<AdminAcceptInviteForm token="fake-token" />);
      await fill(GOOD, GOOD);
      expect((await screen.findByRole("alert")).textContent).toBe("This link cannot be used.");
      expect(screen.queryByRole("button", { name: "Set password" })).toBeNull();
    },
  );

  it("refuses at once when the address has no link", () => {
    render(<AdminAcceptInviteForm token={null} />);
    expect(screen.getByRole("alert").textContent).toBe("This link is not valid.");
    expect(accepts()).toHaveLength(0);
  });
});
