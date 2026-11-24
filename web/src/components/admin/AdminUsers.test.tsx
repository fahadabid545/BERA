import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AdminUsers } from "./AdminUsers";

const fetchMock = vi.fn();
const TEAM = {
  admins: [
    {
      id: 1,
      name: "Fake Boss",
      email: "boss@example.test",
      role: "super",
      status: "active",
      two_step_enabled: true,
    },
    {
      id: 2,
      name: "Fake Helper",
      email: "helper@example.test",
      role: "support",
      status: "blocked",
      two_step_enabled: false,
    },
  ],
  invitations: [
    {
      id: 7,
      name: "Fake Invitee",
      email: "invitee@example.test",
      role: "support",
      status: "pending",
    },
    { id: 8, name: "Fake Late", email: "late@example.test", role: "super", status: "expired" },
  ],
};
const reply = (status: number, body: unknown) =>
  fetchMock.mockResolvedValueOnce({ ok: status < 400, status, json: async () => body });
const rowsOf = (name: string) =>
  Array.from(screen.getByRole("region", { name }).querySelectorAll("tbody tr"));
const cells = (row: Element) =>
  Array.from(row.querySelectorAll("th, td")).map((cell) => cell.textContent);
const last = () => fetchMock.mock.calls.at(-1) as [string, RequestInit];

async function show() {
  reply(200, TEAM);
  render(<AdminUsers />);
  await screen.findByRole("region", { name: "Admins" });
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Admin users", () => {
  it("lists the admins with role, status in words and two-step state", async () => {
    await show();
    expect(rowsOf("Admins").map((row) => cells(row).slice(0, 5))).toEqual([
      ["Fake Boss", "boss@example.test", "Super admin", "Active", "On"],
      ["Fake Helper", "helper@example.test", "Support", "Disabled", "Not set up yet"],
    ]);
  });

  it("lists the waiting invitations, an expired one in words", async () => {
    await show();
    expect(rowsOf("Invitations").map((row) => cells(row).slice(0, 4))).toEqual([
      ["Fake Invitee", "invitee@example.test", "Support", "Pending"],
      ["Fake Late", "late@example.test", "Super admin", "Expired"],
    ]);
  });

  it("has no switch for two-step verification", async () => {
    await show();
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.queryByRole("switch")).toBeNull();
  });

  it("invites an admin with a reason", async () => {
    await show();
    await userEvent.click(screen.getByRole("button", { name: "Invite admin" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Name"), "Fake New");
    await userEvent.type(within(dialog).getByLabelText("Email"), "new@example.test");
    await userEvent.selectOptions(within(dialog).getByLabelText("Role"), "super");
    await userEvent.type(within(dialog).getByLabelText("Reason"), "Fake reason");
    reply(201, TEAM);
    await userEvent.click(within(dialog).getByRole("button", { name: "Send invitation" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [path, init] = last();
    expect([path, init.method]).toEqual(["/api/admin/admin-users/invitations/", "POST"]);
    expect(JSON.parse(String(init.body))).toEqual({
      name: "Fake New",
      email: "new@example.test",
      role: "super",
      reason: "Fake reason",
    });
  });

  it("brings the invite form back with the server's message when it is refused", async () => {
    await show();
    await userEvent.click(screen.getByRole("button", { name: "Invite admin" }));
    await userEvent.type(screen.getByLabelText("Name"), "Fake New");
    reply(409, {
      error: { code: "account_exists", message: "This email already has an admin account." },
    });
    await userEvent.click(screen.getByRole("button", { name: "Send invitation" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "This email already has an admin account.",
    );
    expect((screen.getByLabelText("Name") as HTMLInputElement).value).toBe("Fake New");
  });

  it("shows field messages, such as a missing reason", async () => {
    await show();
    await userEvent.click(screen.getByRole("button", { name: "Invite admin" }));
    reply(400, {
      error: {
        code: "validation_error",
        message: "Please check the form and try again.",
        fields: { reason: "Enter text." },
      },
    });
    await userEvent.click(screen.getByRole("button", { name: "Send invitation" }));
    expect(await screen.findByText("Enter text.")).toBeTruthy();
  });

  it("changes a role with a reason", async () => {
    await show();
    await userEvent.click(
      within(rowsOf("Admins")[1] as HTMLElement).getByRole("button", { name: "Change role" }),
    );
    const dialog = screen.getByRole("dialog");
    await userEvent.selectOptions(within(dialog).getByLabelText("Role"), "super");
    await userEvent.type(within(dialog).getByLabelText("Reason"), "Fake reason");
    reply(200, TEAM);
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [path, init] = last();
    expect([path, init.method]).toEqual(["/api/admin/admin-users/2/role/", "POST"]);
    expect(JSON.parse(String(init.body))).toEqual({ role: "super", reason: "Fake reason" });
  });

  it("disables an active admin and enables a disabled one, each with a reason", async () => {
    await show();
    await userEvent.click(
      within(rowsOf("Admins")[0] as HTMLElement).getByRole("button", { name: "Disable" }),
    );
    await userEvent.type(screen.getByLabelText("Reason"), "Fake reason");
    reply(200, TEAM);
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect([last()[0], JSON.parse(String(last()[1].body))]).toEqual([
      "/api/admin/admin-users/1/status/",
      { status: "blocked", reason: "Fake reason" },
    ]);

    await userEvent.click(
      within(rowsOf("Admins")[1] as HTMLElement).getByRole("button", { name: "Enable" }),
    );
    await userEvent.type(screen.getByLabelText("Reason"), "Fake again");
    reply(200, TEAM);
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(JSON.parse(String(last()[1].body))).toEqual({ status: "active", reason: "Fake again" });
  });

  it("says in plain words that the last super admin cannot be disabled", async () => {
    await show();
    await userEvent.click(
      within(rowsOf("Admins")[0] as HTMLElement).getByRole("button", { name: "Disable" }),
    );
    await userEvent.type(screen.getByLabelText("Reason"), "Fake reason");
    reply(409, {
      error: {
        code: "last_super_admin",
        message: "There must always be one active super admin, so this cannot be done.",
      },
    });
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Save" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "There must always be one active super admin, so this cannot be done.",
    );
  });

  it("resends an invitation without a popup", async () => {
    await show();
    reply(200, TEAM);
    await userEvent.click(
      within(rowsOf("Invitations")[0] as HTMLElement).getByRole("button", { name: "Resend" }),
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(last()[0]).toBe("/api/admin/admin-users/invitations/7/resend/");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("asks in a popup before revoking, and revokes only when confirmed", async () => {
    await show();
    await userEvent.click(
      within(rowsOf("Invitations")[0] as HTMLElement).getByRole("button", { name: "Revoke" }),
    );
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }),
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await userEvent.click(
      within(rowsOf("Invitations")[0] as HTMLElement).getByRole("button", { name: "Revoke" }),
    );
    reply(200, { ...TEAM, invitations: [] });
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Revoke" }),
    );
    await waitFor(() => expect(last()[0]).toBe("/api/admin/admin-users/invitations/7/revoke/"));
    await waitFor(() => expect(screen.queryByRole("region", { name: "Invitations" })).toBeNull());
  });

  it("shows the server's message when the page cannot load", async () => {
    reply(403, {
      error: { code: "not_allowed", message: "You do not have permission to do this." },
    });
    render(<AdminUsers />);
    expect((await screen.findByRole("alert")).textContent).toBe(
      "You do not have permission to do this.",
    );
  });
});
