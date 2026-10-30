import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import ResetPasswordPage from "./page";

function stubServer(status: number, body: unknown) {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function refusal(code: string, message: string, extra: object = {}) {
  return { error: { code, message, ...extra } };
}

async function openPage(token?: string | string[]) {
  render(await ResetPasswordPage({ searchParams: Promise.resolve({ token }) }));
}

const NEW_PASSWORD = "copper-meadow-lantern-58"; // nosecret: fake test value

async function fillIn(password = NEW_PASSWORD, confirm = password) {
  await userEvent.type(screen.getByLabelText("New password"), password);
  await userEvent.type(screen.getByLabelText("Confirm password"), confirm);
  await userEvent.click(screen.getByRole("button", { name: "Save password" }));
}

afterEach(() => vi.unstubAllGlobals());

describe("reset password page", () => {
  it("asks for the new password twice", async () => {
    await openPage("good-token");
    expect((screen.getByLabelText("New password") as HTMLInputElement).type).toBe("password");
    expect((screen.getByLabelText("Confirm password") as HTMLInputElement).type).toBe("password");
    expect(screen.getByRole("button", { name: "Save password" })).toBeTruthy();
  });

  it("sends the token from the link with both entries", async () => {
    const server = stubServer(200, { status: "ok" });
    await openPage("good-token");
    await fillIn(NEW_PASSWORD, NEW_PASSWORD);
    await waitFor(() => expect(server).toHaveBeenCalled());
    const [path, init] = server.mock.calls[0] as unknown as [string, RequestInit];
    expect(path).toBe("/api/auth/company/reset-password/");
    expect(JSON.parse(String(init.body))).toEqual({
      token: "good-token",
      password: NEW_PASSWORD,
      confirm_password: NEW_PASSWORD,
    });
  });

  it("says the password was changed and sends the person to log in again", async () => {
    stubServer(200, { status: "ok" });
    await openPage("good-token");
    await fillIn();
    expect((await screen.findByRole("status")).textContent).toBe(
      "Your password was changed. Log in with your new password.",
    );
    expect(screen.getByRole("link", { name: "Log in" }).getAttribute("href")).toBe("/login");
    expect(screen.queryByLabelText("New password")).toBeNull();
  });

  it.each([
    ["expired", "link_expired", "This link has expired."],
    ["used", "link_used", "This link has already been used."],
    ["not valid", "link_invalid", "This link is not valid."],
  ])("a link that is %s shows the message and a way to ask again", async (_, code, message) => {
    stubServer(400, refusal(code, message));
    await openPage("old-token");
    await fillIn();
    expect((await screen.findByRole("alert")).textContent).toBe(message);
    expect(screen.getByRole("link", { name: "Request a new link" }).getAttribute("href")).toBe(
      "/forgot-password",
    );
    expect(screen.queryByLabelText("New password")).toBeNull();
  });

  it("shows a missing link as not valid, with a way to ask again", async () => {
    const server = stubServer(200, {});
    await openPage(undefined);
    expect(screen.getByRole("alert").textContent).toBe("This link is not valid.");
    expect(screen.getByRole("link", { name: "Request a new link" })).toBeTruthy();
    expect(server).not.toHaveBeenCalled();
  });

  it("shows every reason a password was refused, next to the field, and keeps the form", async () => {
    stubServer(
      400,
      refusal("validation_error", "x", {
        fields: { password: "Use at least 12 characters. This password is too common." },
      }),
    );
    await openPage("good-token");
    await fillIn("password");
    expect(
      await screen.findByText(/Use at least 12 characters\. This password is too common\./),
    ).toBeTruthy();
    expect(screen.getByLabelText("New password").getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByRole("button", { name: "Save password" })).toBeTruthy();
  });

  it("shows that the new password cannot be the old one", async () => {
    stubServer(
      400,
      refusal("validation_error", "x", {
        fields: { password: "Your new password must be different from your old one." },
      }),
    );
    await openPage("good-token");
    await fillIn();
    expect(
      await screen.findByText("Your new password must be different from your old one."),
    ).toBeTruthy();
  });

  it("shows when the two entries do not match, under the second", async () => {
    stubServer(
      400,
      refusal("validation_error", "x", {
        fields: { confirm_password: "The passwords do not match." },
      }),
    );
    await openPage("good-token");
    await fillIn(NEW_PASSWORD, `${NEW_PASSWORD}x`);
    expect(await screen.findByText("The passwords do not match.")).toBeTruthy();
    expect(screen.getByLabelText("Confirm password").getAttribute("aria-invalid")).toBe("true");
  });

  it("says so in words when the server cannot be reached", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Promise.reject(new TypeError("down"))),
    );
    await openPage("good-token");
    await fillIn();
    expect((await screen.findByRole("alert")).textContent).toMatch(/could not reach the server/);
  });

  it("takes the first token when the address has several", async () => {
    const server = stubServer(200, { status: "ok" });
    await openPage(["first", "second"]);
    await fillIn();
    await waitFor(() => expect(server).toHaveBeenCalled());
    const init = (server.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(JSON.parse(String(init.body)).token).toBe("first");
  });
});
