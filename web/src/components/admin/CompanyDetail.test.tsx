import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CompanyDetail } from "./CompanyDetail";

const fetchMock = vi.fn();

const DETAIL = {
  company: {
    id: "7",
    name: "Fake Alpha Ltd",
    country: "GB",
    status: "suspended",
    created_at: "2026-11-02T10:00:00Z",
    deletion_due_at: null,
  },
  users: [
    { id: "1", name: "Fake Owner", email: "owner@example.test", role: "owner", status: "active" },
    {
      id: "2",
      name: "Fake Member",
      email: "member@example.test",
      role: "member",
      status: "blocked",
    },
  ],
  subscription: {
    plan_name: "Fake Plan",
    state: "past_due",
    renewal: true,
    grace_ends_at: "2026-11-20T10:00:00Z",
    period_start: "2026-11-01T10:00:00Z",
    period_end: "2026-12-01T10:00:00Z",
  },
  usage: {
    cvs: { used: 3, limit: 10 },
    tokens: { used: 1200, limit: 5000 },
    projects: { used: 1, limit: 5 },
  },
  project_counts: { active: 1, archived: 2 },
  projects: [
    {
      id: "p1",
      title: "Fake Open Role",
      status: "active",
      reading_model: "fake-reader",
      reading_prompt_version: 7,
      created_at: "2026-11-03T10:00:00Z",
    },
  ],
  history: [
    {
      id: 1,
      kind: "admin.company_suspended",
      actor_kind: "admin",
      reason: "Fake reason",
      created_at: "2026-11-04T10:00:00Z",
    },
    {
      id: 2,
      kind: "auth.login",
      actor_kind: "none",
      reason: "",
      created_at: "2026-11-05T10:00:00Z",
    },
  ],
};

function answer(body: unknown, status = 200) {
  fetchMock.mockResolvedValue({ ok: status < 400, status, json: async () => body });
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("company detail", () => {
  it("asks for the company named in the address", async () => {
    answer(DETAIL);
    render(<CompanyDetail companyId="7" />);
    await screen.findByText("Fake Alpha Ltd");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/admin/companies/7/");
  });

  it("shows the company, its subscription and its usage", async () => {
    answer(DETAIL);
    render(<CompanyDetail companyId="7" />);
    await screen.findByText("Fake Alpha Ltd");
    expect(screen.getByText("Suspended")).toBeTruthy();
    expect(screen.getByText("Past due")).toBeTruthy();
    expect(screen.getByText("Fake Plan")).toBeTruthy();
    expect(screen.getByText("3 of 10")).toBeTruthy();
    expect(screen.getByText("1,200 of 5,000")).toBeTruthy();
    expect(screen.getByText("1 active, 2 archived")).toBeTruthy();
  });

  it("lists the users", async () => {
    answer(DETAIL);
    render(<CompanyDetail companyId="7" />);
    const table = await screen.findByRole("region", { name: "Users" });
    expect(within(table).getByText("owner@example.test")).toBeTruthy();
    expect(within(table).getByText("Blocked")).toBeTruthy();
  });

  it("shows each project's pinned reading model and prompt version", async () => {
    answer(DETAIL);
    render(<CompanyDetail companyId="7" />);
    const table = await screen.findByRole("region", { name: "Projects" });
    expect(within(table).getByText("Fake Open Role")).toBeTruthy();
    expect(within(table).getByText("fake-reader")).toBeTruthy();
    expect(within(table).getByText("7")).toBeTruthy();
  });

  it("shows the history in plain words", async () => {
    answer(DETAIL);
    render(<CompanyDetail companyId="7" />);
    const table = await screen.findByRole("region", { name: "History" });
    expect(within(table).getByText("Admin company suspended")).toBeTruthy();
    expect(within(table).getByText("Fake reason")).toBeTruthy();
    expect(within(table).getByText("System")).toBeTruthy();
  });

  it("says so when there is no history or project", async () => {
    answer({ ...DETAIL, history: [], projects: [] });
    render(<CompanyDetail companyId="7" />);
    expect(await screen.findByText("No history yet.")).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Projects" })).toBeNull();
  });

  it("shows a company with no plan", async () => {
    answer({
      ...DETAIL,
      subscription: { ...DETAIL.subscription, plan_name: null, state: "no_plan", period_end: null },
    });
    render(<CompanyDetail companyId="7" />);
    expect(await screen.findByText("No plan")).toBeTruthy();
    expect(screen.getAllByText("None").length).toBeGreaterThan(0);
  });

  it("shows the AI cost only when the server sends it", async () => {
    answer(DETAIL);
    const first = render(<CompanyDetail companyId="7" />);
    await screen.findByText("Fake Alpha Ltd");
    expect(screen.queryByText("AI cost")).toBeNull();
    first.unmount();
    answer({ ...DETAIL, usage: { ...DETAIL.usage, estimated_cost: "1.500000" } });
    render(<CompanyDetail companyId="7" />);
    expect(await screen.findByText("$1.50")).toBeTruthy();
  });

  it("keeps the five action buttons, which do nothing yet", async () => {
    answer(DETAIL);
    const { container } = render(<CompanyDetail companyId="7" />);
    await screen.findByText("Fake Alpha Ltd");
    const names = [
      "Suspend",
      "Terminate subscription",
      "Grant free subscription",
      "Change limits",
      "Block member",
    ];
    for (const name of names) expect(screen.getByRole("button", { name })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Suspend" }).className).toContain(
      "ui-button--danger",
    );
    expect(screen.getByRole("button", { name: "Change limits" }).className).not.toContain(
      "ui-button--danger",
    );
    const before = container.innerHTML;
    for (const button of screen.getAllByRole("button")) await userEvent.click(button);
    expect(container.innerHTML).toBe(before);
  });

  it("shows an error when the company cannot be opened", async () => {
    answer({ error: { code: "not_found", message: "Not found." } }, 404);
    render(<CompanyDetail companyId="7" />);
    expect((await screen.findByRole("alert")).textContent).toBe("Not found.");
  });
});
