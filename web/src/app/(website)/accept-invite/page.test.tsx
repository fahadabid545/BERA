import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import AcceptInvitePage from "./page";

const HINTS = {
  rules: [{ id: "min_length", text: "At least 12 characters", met: false }],
  ok: false,
};
const ACCEPT = "/api/auth/company/accept-invite/";

type Reply = { status?: number; body: unknown };

function stubServer(replies: { me?: Reply; accept?: Reply; logout?: Reply } = {}) {
  const fetchMock = vi.fn(async (path: string) => {
    let reply: Reply = { body: HINTS };
    if (path.endsWith("/password-check/")) reply = { body: HINTS };
    else if (path.endsWith("/me/"))
      reply = replies.me ?? {
        status: 401,
        body: { error: { code: "not_signed_in", message: "x" } },
      };
    else if (path === ACCEPT) reply = replies.accept ?? { body: { status: "ok" } };
    else if (path.endsWith("/logout/")) reply = replies.logout ?? { body: { status: "ok" } };
    return new Response(JSON.stringify(reply.body), { status: reply.status ?? 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function openPage(token: string | null = "invite-token-value") {
  render(await AcceptInvitePage({ searchParams: Promise.resolve({ token: token ?? undefined }) }));
}

async function fillIn(name = "Fake Invitee", password = "brand-new-password-1") {
  await userEvent.type(await screen.findByLabelText("Your name"), name);
  await userEvent.type(screen.getByLabelText("Password"), password);
  await userEvent.type(screen.getByLabelText("Confirm password"), password);
  await userEvent.click(screen.getByRole("button", { name: "Join team" }));
}

const acceptCalls = (server: ReturnType<typeof stubServer>) =>
  server.mock.calls.filter(([path]) => path === ACCEPT);

const refusal = (code: string, message: string, status = 400): Reply => ({
  status,
  body: { error: { code, message } },
});

afterEach(() => vi.unstubAllGlobals());

describe("accept invite page", () => {
  it("shows labelled Your name, Password and Confirm password fields and the Join team button", async () => {
    stubServer();
    await openPage();
    expect(await screen.findByLabelText("Your name")).toBeTruthy();
    expect((screen.getByLabelText("Password") as HTMLInputElement).type).toBe("password");
    expect((screen.getByLabelText("Confirm password") as HTMLInputElement).type).toBe("password");
    expect(screen.getByRole("button", { name: "Join team" })).toBeTruthy();
  });

  it("applies the same password rules while typing: live hints and a live match check", async () => {
    stubServer();
    await openPage();
    expect(await screen.findByText("At least 12 characters: not met")).toBeTruthy();
    await userEvent.type(screen.getByLabelText("Password"), "abc");
    await userEvent.type(screen.getByLabelText("Confirm password"), "abd");
    expect(screen.getByRole("status").textContent).toBe("The passwords do not match.");
  });

  it("sends the link's token with the name and password, then offers to log in", async () => {
    const server = stubServer();
    await openPage("the-token-from-the-link");
    await fillIn();
    await screen.findByText("You have joined the team. Log in to continue.");
    const [, init] = acceptCalls(server)[0] as unknown as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({
      token: "the-token-from-the-link",
      name: "Fake Invitee",
      password: "brand-new-password-1",
      confirm_password: "brand-new-password-1",
    });
    expect(screen.getByRole("link", { name: "Log in" }).getAttribute("href")).toBe("/login");
  });

  it.each([
    ["link_expired", "This link has expired."],
    ["link_used", "This link has already been used."],
    ["link_invalid", "This link is not valid."],
  ])("says plainly when the link is %s", async (code, message) => {
    stubServer({ accept: refusal(code, message) });
    await openPage();
    await fillIn();
    expect((await screen.findByRole("alert")).textContent).toBe(message);
    expect(screen.queryByRole("button", { name: "Join team" })).toBeNull();
  });

  it("says the link is not valid when the address has no token, without asking the server", async () => {
    const server = stubServer();
    await openPage(null);
    expect((await screen.findByRole("alert")).textContent).toBe("This link is not valid.");
    expect(acceptCalls(server)).toHaveLength(0);
  });

  it("shows the account limit and an existing account in words and keeps the form", async () => {
    stubServer({
      accept: refusal(
        "team_limit_reached",
        "Your company can have at most 3 accounts, including the owner.",
        409,
      ),
    });
    await openPage();
    await fillIn();
    expect((await screen.findByRole("alert")).textContent).toContain("at most 3 accounts");
    expect(screen.getByRole("button", { name: "Join team" })).toBeTruthy();
  });

  it("shows a refused password under its field", async () => {
    stubServer({
      accept: {
        status: 400,
        body: {
          error: {
            code: "validation_error",
            message: "x",
            fields: { password: "Use at least 12 characters." },
          },
        },
      },
    });
    await openPage();
    await fillIn();
    expect(await screen.findByText("Use at least 12 characters.")).toBeTruthy();
  });
});

describe("an invitee who is logged in as someone else", () => {
  const signedIn = { body: { name: "Fake Other", company_name: "Other Ltd", role: "member" } };

  it("is asked to log out first and sees no form", async () => {
    stubServer({ me: signedIn });
    await openPage();
    expect(
      await screen.findByText(
        "You are logged in as Fake Other. Log out first to accept this invitation.",
      ),
    ).toBeTruthy();
    expect(screen.queryByLabelText("Your name")).toBeNull();
    expect(screen.queryByRole("button", { name: "Join team" })).toBeNull();
  });

  it("gets the form after logging out, on the same page", async () => {
    const server = stubServer({ me: signedIn });
    await openPage();
    await userEvent.click(await screen.findByRole("button", { name: "Log out" }));
    expect(await screen.findByLabelText("Your name")).toBeTruthy();
    await waitFor(() =>
      expect(server.mock.calls.some(([path]) => path === "/api/auth/company/logout/")).toBe(true),
    );
  });
});
