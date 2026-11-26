import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AdminAccess } from "./AdminAccess";

const fetchMock = vi.fn();
const reply = (body: unknown, status = 200) => ({
  ok: status < 400,
  status,
  json: async () => body,
});
const grant = (over: object = {}) => ({
  id: "g1",
  kind: "beta",
  status: "active",
  company: { id: "c1", name: "Fake Beta Co" },
  owner: { name: "Fake Owner", email: "owner@example.com" },
  invite: { id: 1, label: "Spring group", kind: "beta_code" },
  plan: null,
  started_at: "2026-11-01T00:00:00Z",
  ends_at: "2026-12-01T00:00:00Z",
  revoked_at: null,
  ...over,
});
const invite = (over: object = {}) => ({
  id: 1,
  kind: "beta_code",
  label: "Spring group",
  email: null,
  plan: null,
  access_days: 30,
  max_uses: 5,
  uses: 2,
  redeem_until: null,
  enabled: true,
  created_at: "2026-11-01T00:00:00Z",
  ...over,
});
const days = Array.from({ length: 14 }, (_, index) => ({
  day: `2026-11-${String(index + 1).padStart(2, "0")}`,
  cvs: index === 13 ? 4 : 0,
}));
const detail = {
  ...grant(),
  usage: {
    cvs_today: 4,
    cvs_per_day_limit: 5,
    cvs_this_period: 9,
    cvs_per_month_limit: 1000,
    tokens_in: 1200,
    tokens_out: 300,
    estimated_cost: "0.012000",
    projects: 3,
  },
  daily_cvs: days,
  activity: [
    { id: 1, kind: "download", actor_name: "Fake Owner", created_at: "2026-11-10T00:00:00Z" },
  ],
  feedback: [
    {
      id: "f1",
      kind: "idea",
      status: "new",
      message: "Please add dark mode",
      user: "Fake Owner",
      created_at: "2026-11-11T00:00:00Z",
    },
  ],
};
const paid = (over: object = {}) => ({
  id: "p1",
  name: "Fake Paying Co",
  plan_name: "Fake Starter",
  state: "active",
  period_end: "2026-12-15T00:00:00Z",
  cvs_used: 10,
  cvs_limit: 100,
  users: 2,
  also_free_access: ["beta"],
  ...over,
});
let grants: object[];
let invites: object[];
let paidPage: object;

const sent = () =>
  fetchMock.mock.calls
    .filter((call) => call[1]?.method && call[1].method !== "GET")
    .map((call) => [call[1].method, call[0], call[1].body ? JSON.parse(call[1].body) : null]);

beforeEach(() => {
  grants = [grant()];
  invites = [invite(), invite({ id: 2, label: "Unused", uses: 0 })];
  paidPage = { total: 11, page: 1, page_size: 10, items: [paid()] };
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (path: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    if (method === "POST" && path.endsWith("/invites/"))
      return reply({ ...invite({ id: 9 }), code: "BETA-AAAA-BBBB-CCCC" }, 201);
    if (method !== "GET") return reply({});
    if (path.includes("/access/g1/")) return reply(detail);
    if (path.includes("/access/")) {
      const kind = new URL(path, "http://x").searchParams.get("kind");
      const items = grants.filter((each) => (each as { kind: string }).kind === kind);
      return reply({ total: items.length, page: 1, page_size: 50, items });
    }
    if (path.includes("/overview/"))
      return reply({ active: 3, ended: 1, revoked: 2, feedback: 7, daily_cvs: days });
    if (path.includes("/invites/")) return reply({ invites });
    if (path.includes("/paid/")) return reply(paidPage);
    if (path.includes("/api/admin/plans/"))
      return reply([{ id: 3, name: "Fake Starter", status: "active" }]);
    if (path.includes("/api/admin/settings/"))
      return reply({
        items: [
          {
            key: "beta.cvs_per_day",
            group: "beta",
            kind: "number",
            value: 5,
            default: 5,
            is_default: true,
          },
        ],
      });
    return reply({});
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function open(user: ReturnType<typeof userEvent.setup>, section: string, sub?: string) {
  render(<AdminAccess />);
  await user.click(await screen.findByRole("tab", { name: section }));
  if (sub) await user.click(await screen.findByRole("tab", { name: sub }));
}

describe("access tab", () => {
  it("has the three sections", async () => {
    render(<AdminAccess />);
    for (const name of ["Beta users", "Admin-permitted users", "Paid users"]) {
      expect(await screen.findByRole("tab", { name })).toBeTruthy();
    }
  });

  it("shows the beta overview with the CVs a day", async () => {
    render(<AdminAccess />);
    const table = await screen.findByRole("region", { name: "Beta overview" });
    expect(within(table).getByText("Feedback sent").nextElementSibling?.textContent).toBe("7");
    expect(screen.getByRole("list", { name: "Beta CVs a day" }).children).toHaveLength(14);
  });

  it("revokes all beta users only after a confirmation", async () => {
    const user = userEvent.setup();
    render(<AdminAccess />);
    await user.click(await screen.findByRole("button", { name: "Revoke all beta users" }));
    expect(sent()).toEqual([]);
    const dialog = await screen.findByRole("dialog", { name: "Revoke all beta users" });
    await user.click(within(dialog).getByRole("button", { name: "Revoke all" }));
    await waitFor(() =>
      expect(sent()).toEqual([["POST", "/api/admin/free-access/access/revoke-all-beta/", {}]]),
    );
  });

  it("lists the beta users and revokes one after a confirmation", async () => {
    const user = userEvent.setup();
    await open(user, "Beta users", "Users");
    const table = await screen.findByRole("region", { name: "Beta accesses" });
    expect(within(table).getByText("Fake Beta Co")).toBeTruthy();
    await user.click(within(table).getByRole("button", { name: "Revoke Fake Beta Co" }));
    expect(sent()).toEqual([]);
    const dialog = await screen.findByRole("dialog", { name: "Revoke access" });
    await user.click(within(dialog).getByRole("button", { name: "Revoke access" }));
    await waitFor(() =>
      expect(sent()).toEqual([["DELETE", "/api/admin/free-access/access/g1/", null]]),
    );
  });

  it("extends one beta user by the days typed", async () => {
    const user = userEvent.setup();
    await open(user, "Beta users", "Users");
    await user.click(await screen.findByRole("button", { name: "Extend Fake Beta Co" }));
    const dialog = await screen.findByRole("dialog", { name: "Extend access" });
    await user.type(within(dialog).getByLabelText("Days to add"), "7");
    await user.click(within(dialog).getByRole("button", { name: "Extend access" }));
    await waitFor(() =>
      expect(sent()).toEqual([["POST", "/api/admin/free-access/access/g1/extend/", { days: 7 }]]),
    );
  });

  it("shows a beta user's usage, activity and feedback", async () => {
    const user = userEvent.setup();
    await open(user, "Beta users", "Users");
    await user.click(await screen.findByRole("button", { name: "Details of Fake Beta Co" }));
    const usage = await screen.findByRole("region", { name: "Usage" });
    expect(within(usage).getByText("CVs today").nextElementSibling?.textContent).toBe("4 of 5");
    expect(screen.getByRole("list", { name: "CVs a day" })).toBeTruthy();
    await user.click(screen.getByRole("tab", { name: "Activity" }));
    expect(await screen.findByText("download")).toBeTruthy();
    await user.click(screen.getByRole("tab", { name: "Feedback" }));
    expect(await screen.findByText("Please add dark mode")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Back to the list" }));
    expect(await screen.findByRole("region", { name: "Beta accesses" })).toBeTruthy();
  });

  it("makes a code and shows it once", async () => {
    const user = userEvent.setup();
    await open(user, "Beta users", "Codes and emails");
    await user.click(await screen.findByRole("button", { name: "New code" }));
    const dialog = await screen.findByRole("dialog", { name: "New code" });
    await user.type(within(dialog).getByLabelText("Label"), "Autumn");
    await user.type(within(dialog).getByLabelText("Access days"), "20");
    await user.type(within(dialog).getByLabelText("Most companies"), "8");
    await user.click(within(dialog).getByRole("button", { name: "Create code" }));
    expect(await screen.findByText("BETA-AAAA-BBBB-CCCC")).toBeTruthy();
    expect(sent()[0]).toEqual([
      "POST",
      "/api/admin/free-access/invites/",
      { kind: "beta_code", label: "Autumn", access_days: 20, max_uses: 8 },
    ]);
  });

  it("switches a code off and can also take back the access it gave", async () => {
    const user = userEvent.setup();
    await open(user, "Beta users", "Codes and emails");
    await user.click(await screen.findByRole("button", { name: "Switch off Spring group" }));
    const dialog = await screen.findByRole("dialog", { name: "Switch off" });
    await user.click(within(dialog).getByLabelText("Also revoke the people who joined with it"));
    await user.click(within(dialog).getByRole("button", { name: "Switch off" }));
    await waitFor(() =>
      expect(sent()).toEqual([
        ["PATCH", "/api/admin/free-access/invites/1/", { enabled: false, also_revoke_users: true }],
      ]),
    );
  });

  it("deletes only a code nobody has used", async () => {
    const user = userEvent.setup();
    await open(user, "Beta users", "Codes and emails");
    expect(await screen.findByRole("button", { name: "Delete Unused" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Delete Spring group" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Delete Unused" }));
    const dialog = await screen.findByRole("dialog", { name: "Delete invite" });
    await user.click(within(dialog).getByRole("button", { name: "Delete" }));
    await waitFor(() =>
      expect(sent()).toEqual([["DELETE", "/api/admin/free-access/invites/2/", null]]),
    );
  });

  it("lists the beta limits as settings", async () => {
    const user = userEvent.setup();
    await open(user, "Beta users", "Settings");
    expect(await screen.findByText("Cvs per day")).toBeTruthy();
  });

  it("gives a permitted email a plan and changes it later", async () => {
    grants = [
      grant({
        id: "g2",
        kind: "permitted",
        plan: { id: 3, name: "Fake Starter" },
        ends_at: null,
        invite: { id: 4, label: "Tester", kind: "permitted_email" },
      }),
    ];
    invites = [
      invite({
        id: 4,
        kind: "permitted_email",
        label: "Tester",
        email: "t@example.com",
        plan: { id: 3, name: "Fake Starter" },
        max_uses: null,
        access_days: null,
      }),
    ];
    const user = userEvent.setup();
    await open(user, "Admin-permitted users", "Emails");
    await user.click(await screen.findByRole("button", { name: "Add email" }));
    const dialog = await screen.findByRole("dialog", { name: "Add email" });
    await user.type(within(dialog).getByLabelText("Email"), "new@example.com");
    await user.click(within(dialog).getByRole("button", { name: "Add email" }));
    await waitFor(() =>
      expect(sent()[0][2]).toEqual({
        kind: "permitted_email",
        email: "new@example.com",
        label: "",
        plan_id: 3,
      }),
    );
    await user.click(screen.getByRole("tab", { name: "Users" }));
    await user.click(await screen.findByRole("button", { name: "Change plan of Fake Beta Co" }));
    const change = await screen.findByRole("dialog", { name: "Change plan" });
    await user.click(within(change).getByRole("button", { name: "Change plan" }));
    await waitFor(() =>
      expect(sent()[1]).toEqual(["PATCH", "/api/admin/free-access/access/g2/", { plan_id: 3 }]),
    );
  });

  it("pages through the paying companies and names their other access", async () => {
    const user = userEvent.setup();
    await open(user, "Paid users");
    const table = await screen.findByRole("region", { name: "Paid users" });
    expect(within(table).getByText("Fake Paying Co")).toBeTruthy();
    expect(within(table).getByText("Beta")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() =>
      expect(fetchMock.mock.calls.some((call) => String(call[0]).includes("paid/?page=2"))).toBe(
        true,
      ),
    );
  });
});
