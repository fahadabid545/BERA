import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import VerifyEmailPage from "./page";

const RESEND_MESSAGE = "If this email still needs verifying, we have sent a new link.";

type Reply = { status?: number; body: unknown };

function stubServer(replies: { verify?: Reply; resend?: Reply }) {
  const fetchMock = vi.fn(async (path: string) => {
    const reply = path.endsWith("/resend/") ? replies.resend : replies.verify;
    if (!reply || reply.body === "network-down") throw new TypeError("network down");
    return new Response(JSON.stringify(reply.body), { status: reply.status ?? 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function openPage(token?: string | string[]) {
  render(await VerifyEmailPage({ searchParams: Promise.resolve({ token }) }));
}

function refusal(code: string, message: string): Reply {
  return { status: 400, body: { error: { code, message } } };
}

afterEach(() => vi.unstubAllGlobals());

describe("opening the link", () => {
  it("changes nothing until the button is pressed", async () => {
    const server = stubServer({});
    await openPage("good-token");
    expect(screen.getByRole("button", { name: "Verify email" })).toBeTruthy();
    expect(server).not.toHaveBeenCalled();
  });

  it("sends the token from the link when the button is pressed", async () => {
    const server = stubServer({ verify: { body: { status: "verified" } } });
    await openPage("good-token");
    await userEvent.click(screen.getByRole("button", { name: "Verify email" }));
    await waitFor(() => expect(server).toHaveBeenCalledTimes(1));
    const [path, init] = server.mock.calls[0] as unknown as [string, RequestInit];
    expect(path).toBe("/api/auth/company/verify-email/");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ token: "good-token" });
  });

  it("takes the first token when the address has several", async () => {
    const server = stubServer({ verify: { body: { status: "verified" } } });
    await openPage(["first", "second"]);
    await userEvent.click(screen.getByRole("button", { name: "Verify email" }));
    await waitFor(() => expect(server).toHaveBeenCalled());
    expect(
      JSON.parse(String((server.mock.calls[0] as unknown as [string, RequestInit])[1].body)),
    ).toEqual({
      token: "first",
    });
  });

  it("says the email is verified and offers Log in", async () => {
    stubServer({ verify: { body: { status: "verified" } } });
    await openPage("good-token");
    await userEvent.click(screen.getByRole("button", { name: "Verify email" }));
    expect((await screen.findByRole("status")).textContent).toBe("Your email is verified.");
    expect(screen.getByRole("link", { name: "Log in" }).getAttribute("href")).toBe("/login");
    expect(screen.queryByRole("button", { name: "Verify email" })).toBeNull();
  });

  it("cannot be pressed twice while waiting", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => {})),
    );
    await openPage("good-token");
    await userEvent.click(screen.getByRole("button", { name: "Verify email" }));
    await waitFor(() =>
      expect(
        (screen.getByRole("button", { name: "Verify email" }) as HTMLButtonElement).disabled,
      ).toBe(true),
    );
  });
});

describe.each([
  ["expired", "link_expired", "This link has expired."],
  ["used", "link_used", "This link has already been used."],
  ["not valid", "link_invalid", "This link is not valid."],
])("a link that is %s", (_, code, message) => {
  it("shows the message and a way to ask for a new link", async () => {
    stubServer({ verify: refusal(code, message) });
    await openPage("old-token");
    await userEvent.click(screen.getByRole("button", { name: "Verify email" }));
    expect((await screen.findByRole("alert")).textContent).toBe(message);
    expect(screen.getByLabelText("Email")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Resend verification email" })).toBeTruthy();
    expect(screen.queryByRole("status")).toBeNull();
  });
});

describe("a failed attempt", () => {
  it("says so in words when the server cannot be reached, and still offers a resend", async () => {
    stubServer({ verify: { body: "network-down" } });
    await openPage("good-token");
    await userEvent.click(screen.getByRole("button", { name: "Verify email" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/could not reach the server/);
    expect(screen.getByRole("button", { name: "Resend verification email" })).toBeTruthy();
  });
});

describe("asking for a new link", () => {
  it("is what the page shows when there is no token (from the login page)", async () => {
    await openPage(undefined);
    expect(screen.getByLabelText("Email")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Resend verification email" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Verify email" })).toBeNull();
  });

  it("sends the email address and shows the answer in a popup", async () => {
    const server = stubServer({ resend: { body: { status: "ok", message: RESEND_MESSAGE } } });
    await openPage(undefined);
    await userEvent.type(screen.getByLabelText("Email"), "owner@example.test");
    await userEvent.click(screen.getByRole("button", { name: "Resend verification email" }));
    const popup = await screen.findByRole("dialog");
    expect(within(popup).getByText(RESEND_MESSAGE)).toBeTruthy();
    const [path, init] = server.mock.calls[0] as unknown as [string, RequestInit];
    expect(path).toBe("/api/auth/company/verify-email/resend/");
    expect(JSON.parse(String(init.body))).toEqual({ email: "owner@example.test" });
  });

  it("tells the person to wait when 3 per hour is reached", async () => {
    stubServer({
      resend: refusal("too_many_requests", "Too many attempts. Try again in 40 minutes."),
    });
    await openPage(undefined);
    await userEvent.type(screen.getByLabelText("Email"), "owner@example.test");
    await userEvent.click(screen.getByRole("button", { name: "Resend verification email" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Too many attempts. Try again in 40 minutes.",
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("shows a mistake in the email next to the field", async () => {
    stubServer({
      resend: {
        status: 400,
        body: {
          error: {
            code: "validation_error",
            message: "x",
            fields: { email: "Enter a valid email address." },
          },
        },
      },
    });
    await openPage(undefined);
    await userEvent.type(screen.getByLabelText("Email"), "nonsense");
    await userEvent.click(screen.getByRole("button", { name: "Resend verification email" }));
    await waitFor(() =>
      expect(screen.getByLabelText("Email").getAttribute("aria-invalid")).toBe("true"),
    );
    expect(screen.getByText("Enter a valid email address.")).toBeTruthy();
  });
});
