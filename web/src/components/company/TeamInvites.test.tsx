import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TeamInvites } from "./TeamInvites";

const BASE = "/api/company/team/invites/";
type Invite = { id: string; email: string; status: string; expires_at: string | null };
const PENDING: Invite = {
  id: "a1",
  email: "new@example.test",
  status: "pending",
  expires_at: null,
};
const EXPIRED: Invite = {
  id: "b2",
  email: "old@example.test",
  status: "expired",
  expires_at: null,
};

type Reply = { status?: number; body: unknown };

function stubServer(initial: Invite[], replies: Record<string, Reply> = {}) {
  let invites = initial;
  const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const reply = replies[`${method} ${path}`];
    if (reply) {
      if (method === "DELETE" && !reply.status) invites = [];
      return new Response(JSON.stringify(reply.body), { status: reply.status ?? 200 });
    }
    return new Response(JSON.stringify(invites), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const callsTo = (server: ReturnType<typeof stubServer>, method: string, path: string) =>
  server.mock.calls.filter(([url, init]) => url === path && (init?.method ?? "GET") === method);

const refusal = (code: string, message: string, status = 409) => ({
  status,
  body: { error: { code, message } },
});

afterEach(() => vi.unstubAllGlobals());

describe("team invites", () => {
  it("lists pending and expired invitations in words", async () => {
    stubServer([PENDING, EXPIRED]);
    render(<TeamInvites />);
    const table = await screen.findByRole("region", { name: "Pending invitations" });
    expect(within(table).getByText("new@example.test")).toBeTruthy();
    expect(within(table).getByText("Pending")).toBeTruthy();
    expect(within(table).getByText("Expired")).toBeTruthy();
  });

  it("shows no table when nothing is waiting", async () => {
    stubServer([]);
    render(<TeamInvites />);
    await screen.findByRole("button", { name: "Invite member" });
    expect(screen.queryByRole("region", { name: "Pending invitations" })).toBeNull();
  });

  it("sends an invitation for the typed email and says it was sent", async () => {
    const server = stubServer([], { [`POST ${BASE}`]: { status: 201, body: { id: "x" } } });
    render(<TeamInvites />);
    await userEvent.click(await screen.findByRole("button", { name: "Invite member" }));
    await userEvent.type(screen.getByLabelText("Email"), "colleague@example.test");
    await userEvent.click(screen.getByRole("button", { name: "Send invitation" }));
    await screen.findByRole("heading", { name: "Invitation sent" });
    const [, init] = callsTo(server, "POST", BASE)[0] as unknown as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({ email: "colleague@example.test" });
  });

  it.each([
    [
      "an address that already has an account",
      "account_exists",
      "This email already has an account.",
    ],
    [
      "the account limit",
      "team_limit_reached",
      "Your company can have at most 3 accounts, including the owner.",
    ],
  ])("shows %s in plain words and keeps the popup open", async (_, code, message) => {
    stubServer([], { [`POST ${BASE}`]: refusal(code, message) });
    render(<TeamInvites />);
    await userEvent.click(await screen.findByRole("button", { name: "Invite member" }));
    await userEvent.type(screen.getByLabelText("Email"), "colleague@example.test");
    await userEvent.click(screen.getByRole("button", { name: "Send invitation" }));
    expect((await screen.findByRole("alert")).textContent).toBe(message);
    expect(screen.queryByRole("heading", { name: "Invitation sent" })).toBeNull();
    expect(screen.getByLabelText("Email")).toBeTruthy();
  });

  it("shows a field error for a badly typed email", async () => {
    stubServer([], {
      [`POST ${BASE}`]: {
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
    render(<TeamInvites />);
    await userEvent.click(await screen.findByRole("button", { name: "Invite member" }));
    await userEvent.type(screen.getByLabelText("Email"), "nope");
    await userEvent.click(screen.getByRole("button", { name: "Send invitation" }));
    expect(await screen.findByText("Enter a valid email address.")).toBeTruthy();
  });

  it("resends an invitation and says it was sent", async () => {
    const server = stubServer([PENDING], {
      [`POST ${BASE}a1/resend/`]: { body: { status: "ok" } },
    });
    render(<TeamInvites />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Resend invitation to new@example.test" }),
    );
    await screen.findByRole("heading", { name: "Invitation sent" });
    expect(callsTo(server, "POST", `${BASE}a1/resend/`)).toHaveLength(1);
  });

  it("shows why a resend was refused", async () => {
    stubServer([PENDING], {
      [`POST ${BASE}a1/resend/`]: refusal(
        "too_many_requests",
        "Too many attempts. Try again later.",
        429,
      ),
    });
    render(<TeamInvites />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Resend invitation to new@example.test" }),
    );
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Too many attempts. Try again later.",
    );
  });

  it("revokes only after a confirmation and then drops it from the list", async () => {
    const server = stubServer([PENDING], { [`DELETE ${BASE}a1/`]: { body: null } });
    render(<TeamInvites />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Revoke invitation to new@example.test" }),
    );
    expect(callsTo(server, "DELETE", `${BASE}a1/`)).toHaveLength(0);
    await userEvent.click(await screen.findByRole("button", { name: "Revoke" }));
    await waitFor(() => expect(callsTo(server, "DELETE", `${BASE}a1/`)).toHaveLength(1));
    await waitFor(() => expect(screen.queryByText("new@example.test")).toBeNull());
  });

  it("does not revoke when the confirmation is cancelled", async () => {
    const server = stubServer([PENDING]);
    render(<TeamInvites />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Revoke invitation to new@example.test" }),
    );
    await userEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(callsTo(server, "DELETE", `${BASE}a1/`)).toHaveLength(0);
  });
});
