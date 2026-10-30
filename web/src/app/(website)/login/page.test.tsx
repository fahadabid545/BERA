import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LoginPage from "./page";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

type Reply = { status?: number; body: unknown };

function stubServer(replies: { login?: Reply; resend?: Reply }) {
  const fetchMock = vi.fn(async (path: string) => {
    const reply = path.endsWith("/resend/") ? replies.resend : replies.login;
    if (!reply || reply.body === "network-down") throw new TypeError("network down");
    return new Response(JSON.stringify(reply.body), { status: reply.status ?? 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function refusal(code: string, message: string, status = 400): Reply {
  return { status, body: { error: { code, message } } };
}

async function openPage(next?: string) {
  render(await LoginPage({ searchParams: Promise.resolve({ next }) }));
}

async function logIn(email = "owner@example.test", password = "the-right-password-1") {
  await userEvent.type(screen.getByLabelText("Email"), email);
  await userEvent.type(screen.getByLabelText("Password"), password);
  await userEvent.click(screen.getByRole("button", { name: "Log in" }));
}

beforeEach(() => push.mockClear());
afterEach(() => vi.unstubAllGlobals());

describe("login page", () => {
  it("shows labelled Email and Password fields and a Log in button", async () => {
    await openPage();
    expect((screen.getByLabelText("Email") as HTMLInputElement).type).toBe("email");
    expect((screen.getByLabelText("Password") as HTMLInputElement).type).toBe("password");
    expect(screen.getByRole("button", { name: "Log in" })).toBeTruthy();
  });

  it("always shows Forgot password?, and the other links", async () => {
    await openPage();
    expect(screen.getByRole("link", { name: "Forgot password?" }).getAttribute("href")).toBe(
      "/forgot-password",
    );
    expect(screen.getByRole("link", { name: "Create an account" }).getAttribute("href")).toBe(
      "/signup",
    );
    expect(
      screen.getByRole("link", { name: "Resend verification email" }).getAttribute("href"),
    ).toBe("/verify-email");
  });

  it("still shows Forgot password? after a refused attempt", async () => {
    stubServer({ login: refusal("invalid_credentials", "Email or password is incorrect.") });
    await openPage();
    await logIn();
    await screen.findByRole("alert");
    expect(screen.getByRole("link", { name: "Forgot password?" })).toBeTruthy();
  });
});

describe("signing in", () => {
  it("sends the email and password, and opens the dashboard", async () => {
    const server = stubServer({ login: { body: { status: "ok" } } });
    await openPage();
    await logIn();
    await waitFor(() => expect(push).toHaveBeenCalledWith("/company"));
    const [path, init] = server.mock.calls[0] as unknown as [string, RequestInit];
    expect(path).toBe("/api/auth/company/login/");
    expect(JSON.parse(String(init.body))).toEqual({
      email: "owner@example.test",
      password: "the-right-password-1",
    });
  });

  it("opens the page the person first wanted", async () => {
    stubServer({ login: { body: { status: "ok" } } });
    await openPage("/company/projects/abc");
    await logIn();
    await waitFor(() => expect(push).toHaveBeenCalledWith("/company/projects/abc"));
  });

  it("does not follow an address that leads elsewhere", async () => {
    stubServer({ login: { body: { status: "ok" } } });
    await openPage("https://evil.example.test/company");
    await logIn();
    await waitFor(() => expect(push).toHaveBeenCalledWith("/company"));
  });

  it("never puts the password in the address", async () => {
    const server = stubServer({ login: { body: { status: "ok" } } });
    await openPage();
    await logIn();
    await waitFor(() => expect(push).toHaveBeenCalled());
    const [path] = server.mock.calls[0] as unknown as [string];
    expect(path).not.toContain("the-right-password-1");
    expect(String(push.mock.calls[0][0])).not.toContain("password");
  });

  it("cannot be pressed again while waiting", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise<Response>(() => {})),
    );
    await openPage();
    await logIn();
    await waitFor(() =>
      expect((screen.getByRole("button", { name: "Log in" }) as HTMLButtonElement).disabled).toBe(
        true,
      ),
    );
  });
});

describe("the outcomes", () => {
  it.each([
    [
      "wrong details",
      refusal("invalid_credentials", "Email or password is incorrect."),
      "Email or password is incorrect.",
    ],
    [
      "a suspended company",
      refusal(
        "company_suspended",
        "Your company account is suspended. Please contact support.",
        403,
      ),
      "Your company account is suspended. Please contact support.",
    ],
    [
      "a paused account",
      refusal("too_many_requests", "Too many attempts. Try again in 15 minutes.", 429),
      "Too many attempts. Try again in 15 minutes.",
    ],
  ])("%s: shows the message and stays on the page", async (_, reply, message) => {
    stubServer({ login: reply });
    await openPage();
    await logIn();
    expect((await screen.findByRole("alert")).textContent).toBe(message);
    expect(push).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Resend verification email" })).toBeNull();
  });

  it("keeps the email that was typed after a refusal", async () => {
    stubServer({ login: refusal("invalid_credentials", "Email or password is incorrect.") });
    await openPage();
    await logIn();
    await screen.findByRole("alert");
    expect((screen.getByLabelText("Email") as HTMLInputElement).value).toBe("owner@example.test");
  });

  it("says so in words when the server cannot be reached", async () => {
    stubServer({ login: { body: "network-down" } });
    await openPage();
    await logIn();
    expect((await screen.findByRole("alert")).textContent).toMatch(/could not reach the server/);
  });
});

describe("an email that is not verified", () => {
  const unverified = refusal("email_not_verified", "Please verify your email", 403);

  it("shows Please verify your email with a resend button", async () => {
    stubServer({ login: unverified });
    await openPage();
    await logIn();
    expect((await screen.findByRole("alert")).textContent).toBe("Please verify your email");
    expect(screen.getByRole("button", { name: "Resend verification email" })).toBeTruthy();
    expect(push).not.toHaveBeenCalled();
  });

  it("sends the new link to the email that was typed", async () => {
    const server = stubServer({
      login: unverified,
      resend: {
        body: {
          status: "ok",
          message: "If this email still needs verifying, we have sent a new link.",
        },
      },
    });
    await openPage();
    await logIn("Owner@Example.test");
    await userEvent.click(await screen.findByRole("button", { name: "Resend verification email" }));
    const popup = await screen.findByRole("dialog");
    expect(within(popup).getByText(/we have sent a new link/)).toBeTruthy();
    const [path, init] = server.mock.calls[1] as unknown as [string, RequestInit];
    expect(path).toBe("/api/auth/company/verify-email/resend/");
    expect(JSON.parse(String(init.body))).toEqual({ email: "Owner@Example.test" });
  });

  it("says when resending is limited", async () => {
    stubServer({
      login: unverified,
      resend: refusal("too_many_requests", "Too many attempts. Try again in 40 minutes.", 429),
    });
    await openPage();
    await logIn();
    await userEvent.click(await screen.findByRole("button", { name: "Resend verification email" }));
    await waitFor(() => expect(screen.getAllByRole("alert")).toHaveLength(2));
    expect(screen.getAllByRole("alert")[1].textContent).toBe(
      "Too many attempts. Try again in 40 minutes.",
    );
  });

  it("goes away when the next attempt gives a different answer", async () => {
    const fetchMock = stubServer({ login: unverified });
    await openPage();
    await logIn();
    await screen.findByRole("button", { name: "Resend verification email" });
    fetchMock.mockImplementation(
      async () =>
        new Response(
          JSON.stringify(refusal("invalid_credentials", "Email or password is incorrect.").body),
          {
            status: 400,
          },
        ),
    );
    await userEvent.click(screen.getByRole("button", { name: "Log in" }));
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Resend verification email" })).toBeNull(),
    );
  });
});
