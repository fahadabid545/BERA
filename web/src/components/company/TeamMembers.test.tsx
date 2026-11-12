import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TeamMembers } from "./TeamMembers";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const BASE = "/api/company/team/";
const OWNER = {
  id: 1,
  name: "Olive Owner",
  email: "owner@example.test",
  role: "owner",
  status: "active",
};
const MEMBER = {
  id: 2,
  name: "Mia Member",
  email: "member@example.test",
  role: "member",
  status: "active",
};
const BLOCKED = {
  id: 3,
  name: "Ben Blocked",
  email: "blocked@example.test",
  role: "member",
  status: "blocked",
};

type Reply = { status?: number; body: unknown };

function stubServer(people = [OWNER, MEMBER, BLOCKED], replies: Record<string, Reply> = {}) {
  let list = people;
  const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const reply = replies[`${method} ${path}`];
    if (reply) {
      if (!reply.status && method === "DELETE")
        list = list.filter((p) => path !== `${BASE}members/${p.id}/`);
      return new Response(reply.status === 204 ? null : JSON.stringify(reply.body), {
        status: reply.status ?? 200,
      });
    }
    return new Response(JSON.stringify(list), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const callsTo = (server: ReturnType<typeof stubServer>, method: string, path: string) =>
  server.mock.calls.filter(([url, init]) => url === path && (init?.method ?? "GET") === method);

beforeEach(() => refresh.mockClear());
afterEach(() => vi.unstubAllGlobals());

describe("team members", () => {
  it("lists name, email, role and status in words", async () => {
    stubServer();
    render(<TeamMembers />);
    const table = await screen.findByRole("region", { name: "Members" });
    await within(table).findByText("Olive Owner");
    expect(within(table).getByText("owner@example.test")).toBeTruthy();
    expect(within(table).getByText("Owner")).toBeTruthy();
    expect(within(table).getByText("Blocked")).toBeTruthy();
    expect(within(table).getAllByText("Member")).toHaveLength(2);
  });

  it("offers no actions on the owner row", async () => {
    stubServer();
    render(<TeamMembers />);
    await screen.findByText("Olive Owner");
    expect(screen.queryByRole("button", { name: "Remove Olive Owner" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Make Olive Owner the owner" })).toBeNull();
  });

  it("removes a member only after the confirmation popup", async () => {
    const server = stubServer([OWNER, MEMBER], { [`DELETE ${BASE}members/2/`]: { body: null } });
    render(<TeamMembers />);
    await userEvent.click(await screen.findByRole("button", { name: "Remove Mia Member" }));
    expect(callsTo(server, "DELETE", `${BASE}members/2/`)).toHaveLength(0);
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Remove" }),
    );
    await waitFor(() => expect(callsTo(server, "DELETE", `${BASE}members/2/`)).toHaveLength(1));
    await waitFor(() => expect(screen.queryByText("Mia Member")).toBeNull());
  });

  it("does not remove anyone when the popup is cancelled", async () => {
    const server = stubServer();
    render(<TeamMembers />);
    await userEvent.click(await screen.findByRole("button", { name: "Remove Mia Member" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(server.mock.calls.filter(([, init]) => init?.method === "DELETE")).toHaveLength(0);
  });

  it("shows a refusal in plain words", async () => {
    stubServer([OWNER, MEMBER], {
      [`DELETE ${BASE}members/2/`]: {
        status: 409,
        body: {
          error: { code: "already_removed", message: "This person has already been removed." },
        },
      },
    });
    render(<TeamMembers />);
    await userEvent.click(await screen.findByRole("button", { name: "Remove Mia Member" }));
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Remove" }),
    );
    expect(await screen.findByText("This person has already been removed.")).toBeTruthy();
  });

  it("hands the company over with the password and reads the page again", async () => {
    const server = stubServer([OWNER, MEMBER], {
      [`POST ${BASE}transfer-ownership/`]: { body: { status: "ok" } },
    });
    render(<TeamMembers />);
    await userEvent.click(await screen.findByRole("button", { name: "Make Mia Member the owner" }));
    await userEvent.type(screen.getByLabelText("Your password"), "my-password-1234");
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Make owner" }),
    );
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const [, init] = callsTo(server, "POST", `${BASE}transfer-ownership/`)[0];
    expect(JSON.parse(String(init?.body))).toEqual({ member_id: 2, password: "my-password-1234" });
  });

  it("shows a wrong password next to the field and keeps the popup open", async () => {
    stubServer([OWNER, MEMBER], {
      [`POST ${BASE}transfer-ownership/`]: {
        status: 400,
        body: {
          error: {
            code: "wrong_password",
            message: "Your password is incorrect.",
            fields: { password: "Your password is incorrect." },
          },
        },
      },
    });
    render(<TeamMembers />);
    await userEvent.click(await screen.findByRole("button", { name: "Make Mia Member the owner" }));
    await userEvent.type(screen.getByLabelText("Your password"), "wrong");
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Make owner" }),
    );
    expect(await screen.findByText("Your password is incorrect.")).toBeTruthy();
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(refresh).not.toHaveBeenCalled();
  });

  it("does not offer to hand the company to a blocked person", async () => {
    stubServer();
    render(<TeamMembers />);
    await screen.findByText("Ben Blocked");
    expect(screen.queryByRole("button", { name: "Make Ben Blocked the owner" })).toBeNull();
    expect(screen.getByRole("button", { name: "Remove Ben Blocked" })).toBeTruthy();
  });
});
