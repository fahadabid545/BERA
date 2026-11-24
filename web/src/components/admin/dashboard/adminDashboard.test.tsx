import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AdminDashboard, type AdminSection } from "./AdminDashboard";
import { AdminDetailDialog } from "./AdminDetailDialog";
import { AdminPrintableReport } from "./AdminPrintableReport";
import type { AdminData } from "./types";

let query = "";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => "/admin",
  useSearchParams: () => new URLSearchParams(query),
}));

const fetchMock = vi.fn();
beforeEach(() => {
  query = "";
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
const json = (body: unknown, ok = true) => ({ ok, status: ok ? 200 : 403, json: async () => body });

const card = (value: number | null, change: number | null) => ({
  value,
  previous: 1,
  change,
  series: [1, 2, 3],
});
const company = (id: string, over: object = {}) => ({
  type: "company" as const,
  id,
  name: `Company ${id}`,
  country: "PK",
  status: "active",
  plan: "Gold",
  state: "active",
  ...over,
});
const trend = {
  days: 30,
  start: "2026-10-18",
  metrics: {
    cvs_scored: {
      current: [1, 2],
      previous: [1, 1],
      total: 3,
      previous_total: 2,
      change_percent: 50,
    },
    ai_calls: {
      current: [2, 4],
      previous: [1, 1],
      total: 6,
      previous_total: 2,
      change_percent: 200,
    },
  },
};
const superData = (over: Partial<AdminData> = {}): AdminData => ({
  refresh_seconds: 3,
  role: "super",
  days: 30,
  choices: [1, 7, 30],
  cards: { companies: card(3, 200), cvs_scored: card(40, 10), ai_cost: card(12.5, -5) },
  totals: { companies: 128, suspended: 2, paying: 104 },
  usage: {
    trend,
    top_companies: [company("a", { cvs_scored: 30, tokens: 1500, cost: 4.25 })],
  },
  pending: { past_due: 4, grants_expiring: 0, suspended: 2, failed_ai_calls: 9, failed_jobs: 3 },
  recent: [{ ...company("n"), created_at: new Date().toISOString() }],
  revenue: {
    received: 12900,
    ai_cost: 3870,
    margin_days: 30,
    margin_percent: 70,
    plans: [
      { id: 1, name: "Gold", subscribers: 3, received: 120, share: 60 },
      { id: 2, name: "Silver", subscribers: 2, received: 80, share: 40 },
    ],
    states: { active: 5, past_due: 1, cancelled: 0, expired: 2, granted_free: 1, no_plan: 3 },
    history: [
      { month: "2026-10", received: 800, ai_cost: 200, margin_percent: 75 },
      { month: "2026-11", received: 0, ai_cost: 5, margin_percent: null },
    ],
  },
  ai: {
    calls: { total: 20, failed: 2, failure_percent: 10 },
    by_purpose: [
      { purpose: "reading", count: 8 },
      { purpose: "scoring", count: 12 },
      { purpose: "requirement_extraction", count: 0 },
      { purpose: "playground", count: 0 },
    ],
    by_model: [{ model: "big-model", calls: 20, tokens: 5000, cost: 6.5 }],
    tokens: { used: 5000, cap: 10_000, percent: 50, days: 30 },
    control: { paused: false, paused_by_admin: false, paused_automatically: false },
  },
  ...over,
});
const supportData = (): AdminData => {
  const { revenue, ai, ...rest } = superData();
  void revenue;
  void ai;
  return {
    ...rest,
    role: "support",
    cards: { companies: card(3, 200), cvs_scored: card(40, 10) },
    pending: { past_due: 4, grants_expiring: 0, suspended: 2, failed_jobs: 3 },
    usage: {
      trend: { ...trend, metrics: { cvs_scored: trend.metrics.cvs_scored } },
      top_companies: [company("a", { cvs_scored: 30 })],
    },
  };
};
const serve = (data: AdminData) =>
  fetchMock.mockImplementation(async (url: string) =>
    url.includes("/detail/") ? json({ total: 0, items: [] }) : json(data),
  );
const show = (tab: AdminSection = "overview") =>
  render(<AdminDashboard tab={tab} onTab={vi.fn()} />);

describe("AdminDashboard tabs", () => {
  it("gives a super admin five tabs", async () => {
    serve(superData());
    show();
    await screen.findByRole("tab", { name: "Revenue" });
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual([
      "Overview",
      "Revenue",
      "Usage",
      "AI",
      "Attention",
    ]);
  });

  it("gives support no Revenue or AI tab, and no money or AI figures anywhere", async () => {
    serve(supportData());
    const { container } = show();
    expect((await screen.findAllByRole("tab")).map((tab) => tab.textContent)).toEqual([
      "Overview",
      "Usage",
      "Attention",
    ]);
    expect(container.textContent).not.toMatch(/\$|AI cost|Revenue received/);
    expect(screen.getByText("128")).toBeTruthy();
  });

  it("falls back to the first tab when this role does not have the one in the address", async () => {
    serve(supportData());
    show("revenue");
    expect(await screen.findByRole("heading", { name: "Platform" })).toBeTruthy();
  });

  it("keeps the tabs and says why when the numbers cannot be read", async () => {
    fetchMock.mockResolvedValue(
      json({ error: { code: "forbidden", message: "No access." } }, false),
    );
    show();
    expect((await screen.findByRole("alert")).textContent).toBe("No access.");
    expect(screen.getAllByRole("tab").length).toBeGreaterThan(2);
  });

  it("asks again for the chosen period and shows the period everywhere", async () => {
    serve(superData());
    show();
    await screen.findByRole("heading", { name: "Platform" });
    expect(screen.getByRole("button", { name: "This month" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    await userEvent.click(screen.getByRole("button", { name: "This week" }));
    await vi.waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => url === "/api/admin/dashboard/?days=7")).toBe(
        true,
      ),
    );
  });
});

describe("Overview", () => {
  it("shows the platform, the figures with their change and the newest companies", async () => {
    serve(superData());
    show("overview");
    expect(await screen.findByText("104")).toBeTruthy();
    expect(screen.getByText("$12,900")).toBeTruthy();
    expect(screen.getByText("+200%")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Company n" }).getAttribute("href")).toBe(
      "/admin/companies/n",
    );
    expect(screen.getByText("Just now")).toBeTruthy();
  });

  it("opens the suspended companies, new companies and the busiest companies", async () => {
    serve(superData());
    const user = userEvent.setup();
    show("overview");
    await screen.findByRole("heading", { name: "Platform" });
    const asked = () => String(fetchMock.mock.calls.at(-1)?.[0]);
    await user.click(screen.getByRole("button", { name: /Suspended/ }));
    await vi.waitFor(() => expect(asked()).toContain("kind=pending&key=suspended"));
    await user.click(await screen.findByRole("button", { name: "Close" }));
    await user.click(screen.getByRole("button", { name: /^New companies/ }));
    await vi.waitFor(() => expect(asked()).toContain("kind=metric&key=companies&days=30"));
    await user.click(await screen.findByRole("button", { name: "Close" }));
    await user.click(screen.getByRole("button", { name: /^CVs scored/ }));
    await vi.waitFor(() => expect(asked()).toContain("kind=metric&key=cvs_scored&days=30"));
  });

  it("says so when there are no companies", async () => {
    serve(superData({ recent: [] }));
    show("overview");
    expect(await screen.findByText("No companies yet.")).toBeTruthy();
  });
});

describe("Revenue", () => {
  it("sets revenue against the AI cost and shows the margin", async () => {
    serve(superData());
    show("revenue");
    expect(await screen.findByText("Margin 70%")).toBeTruthy();
    expect(screen.getByText("$12,900")).toBeTruthy();
    expect(screen.getByText("$3,870")).toBeTruthy();
  });

  it("shows a negative margin as a loss and says so without any revenue", async () => {
    const base = superData();
    serve({ ...base, revenue: { ...base.revenue!, margin_percent: -20 } });
    show("revenue");
    expect(await screen.findByText("Margin -20%")).toBeTruthy();
    cleanup();
    serve({ ...base, revenue: { ...base.revenue!, margin_percent: null, plans: [] } });
    show("revenue");
    expect(await screen.findByText("No revenue yet")).toBeTruthy();
    expect(screen.getByText("No paying subscriptions yet.")).toBeTruthy();
  });

  it("opens a plan and a subscription state", async () => {
    serve(superData());
    const user = userEvent.setup();
    show("revenue");
    await screen.findByText("Margin 70%");
    const asked = () => String(fetchMock.mock.calls.at(-1)?.[0]);
    await user.click(screen.getByRole("button", { name: /Gold/ }));
    await vi.waitFor(() => expect(asked()).toContain("kind=plan&key=1"));
    await user.click(await screen.findByRole("button", { name: "Close" }));
    await user.click(screen.getByRole("button", { name: /Past due/ }));
    await vi.waitFor(() => expect(asked()).toContain("kind=state&key=past_due"));
  });
});

describe("Usage", () => {
  it("shows the pace and the busiest companies as links, with cost for super admins", async () => {
    serve(superData());
    show("usage");
    const table = await screen.findByRole("region", { name: "Companies by CVs scored" });
    expect(within(table).getByRole("link", { name: "Company a" }).getAttribute("href")).toBe(
      "/admin/companies/a",
    );
    expect(within(table).getByText("$4.25")).toBeTruthy();
    expect(within(table).getByText("1,500")).toBeTruthy();
    expect(screen.getByLabelText("Count")).toBeTruthy();
    expect(screen.queryByRole("combobox", { name: "Period" })).toBeNull();
  });

  it("leaves tokens and cost out for support and offers only what it may count", async () => {
    serve(supportData());
    show("usage");
    const table = await screen.findByRole("region", { name: "Companies by CVs scored" });
    expect(within(table).queryByText("AI cost")).toBeNull();
    expect(within(screen.getByLabelText("Count")).queryByText("AI calls")).toBeNull();
  });

  it("says so when nothing was scored", async () => {
    const base = superData();
    serve({ ...base, usage: { ...base.usage, top_companies: [] } });
    show("usage");
    expect(await screen.findByText("No CVs scored in this period.")).toBeTruthy();
  });
});

describe("AI", () => {
  it("shows the token budget, the failure rate and the cost by model", async () => {
    serve(superData());
    show("ai");
    expect(await screen.findByText("10% failed")).toBeTruthy();
    expect(screen.getByText("AI work running")).toBeTruthy();
    expect(screen.getByText("50%")).toBeTruthy();
    expect(screen.getByText("$6.50")).toBeTruthy();
  });

  it("says when AI work is paused, and when there were no calls", async () => {
    const base = superData();
    serve({
      ...base,
      ai: {
        ...base.ai!,
        calls: { total: 0, failed: 0, failure_percent: null },
        by_model: [],
        tokens: { used: 0, cap: 0, percent: null, days: 30 },
        control: { paused: true, paused_by_admin: true, paused_automatically: false },
      },
    });
    show("ai");
    expect(await screen.findByText("AI work paused")).toBeTruthy();
    expect(screen.getByText("No calls")).toBeTruthy();
    expect(screen.getByText("No AI calls in this period.")).toBeTruthy();
  });

  it("opens the calls behind a purpose and a model", async () => {
    serve(superData());
    const user = userEvent.setup();
    show("ai");
    await screen.findByText("10% failed");
    const asked = () => String(fetchMock.mock.calls.at(-1)?.[0]);
    await user.click(screen.getByRole("button", { name: /Scoring/ }));
    await vi.waitFor(() => expect(asked()).toContain("kind=ai_purpose&key=scoring"));
    await user.click(await screen.findByRole("button", { name: "Close" }));
    await user.click(screen.getByRole("button", { name: /big-model/ }));
    await vi.waitFor(() => expect(asked()).toContain("kind=ai_model&key=big-model"));
  });
});

describe("Attention", () => {
  it("shows what waits with its counts and opens a row; an empty row cannot be opened", async () => {
    serve(superData());
    const user = userEvent.setup();
    show("attention");
    expect(await screen.findByText("18 pending")).toBeTruthy();
    const buttons = screen.getAllByRole("button", { name: "Review" });
    expect(buttons).toHaveLength(5);
    expect((buttons[1] as HTMLButtonElement).disabled).toBe(true);
    await user.click(buttons[3]);
    await vi.waitFor(() =>
      expect(String(fetchMock.mock.calls.at(-1)?.[0])).toContain(
        "kind=pending&key=failed_ai_calls",
      ),
    );
  });

  it("lists failed jobs as a row of its own and opens it", async () => {
    serve(superData());
    const user = userEvent.setup();
    show("attention");
    expect(await screen.findByText("Failed jobs")).toBeTruthy();
    await user.click(screen.getAllByRole("button", { name: "Review" })[4]);
    await vi.waitFor(() =>
      expect(String(fetchMock.mock.calls.at(-1)?.[0])).toContain("kind=pending&key=failed_jobs"),
    );
  });

  it("lists open data requests as a row of its own and opens it", async () => {
    const data = superData();
    serve({ ...data, pending: { ...data.pending, data_requests: 2 } });
    const user = userEvent.setup();
    show("attention");
    expect(await screen.findByText("Open data requests")).toBeTruthy();
    await user.click(screen.getAllByRole("button", { name: "Review" })[5]);
    await vi.waitFor(() =>
      expect(String(fetchMock.mock.calls.at(-1)?.[0])).toContain("kind=pending&key=data_requests"),
    );
  });

  it("shows a data request with its type, status and due date, and marks an overdue one", async () => {
    fetchMock.mockResolvedValue(
      json({
        total: 1,
        items: [
          {
            type: "data_request",
            id: 4,
            company_id: 7,
            company: "Fake Company",
            request_type: "deletion",
            status: "in_progress",
            due_on: "2026-11-01",
            overdue: true,
          },
        ],
      }),
    );
    render(
      <AdminDetailDialog
        detail={{ kind: "pending", key: "data_requests", title: "Open data requests" }}
        onClose={vi.fn()}
      />,
    );
    expect((await screen.findByRole("link", { name: "Fake Company" })).getAttribute("href")).toBe(
      "/admin/companies/7",
    );
    for (const words of ["Deletion", "In progress", "Due 2026-11-01", "Overdue"]) {
      expect(screen.getByText(words)).toBeTruthy();
    }
  });

  it("leaves the AI row out for support", async () => {
    serve(supportData());
    show("attention");
    expect(await screen.findByText("9 pending")).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "Review" })).toHaveLength(4);
    expect(screen.getByText("Failed jobs")).toBeTruthy();
    expect(screen.queryByText("Failed AI calls")).toBeNull();
  });
});

describe("AdminDetailDialog", () => {
  const detail = { kind: "state", key: "active", title: "Companies: Active" };
  it("lists a failed job with its company, its reason and the day", async () => {
    fetchMock.mockResolvedValue(
      json({
        total: 1,
        items: [
          {
            type: "job",
            id: "j1",
            company_id: "7",
            company: "Fake Company",
            reason: "We could not read this file.",
            at: "2026-11-15T10:00:00Z",
          },
        ],
      }),
    );
    render(
      <AdminDetailDialog
        detail={{ kind: "pending", key: "failed_jobs", title: "Failed jobs" }}
        onClose={vi.fn()}
      />,
    );
    expect((await screen.findByRole("link", { name: "Fake Company" })).getAttribute("href")).toBe(
      "/admin/companies/7",
    );
    expect(screen.getByText("We could not read this file.")).toBeTruthy();
    expect(screen.getByText("Failed")).toBeTruthy();
    expect(screen.getByText("2026-11-15")).toBeTruthy();
  });

  it("lists companies as links with their plan, state and usage", async () => {
    fetchMock.mockResolvedValue(
      json({
        total: 3,
        items: [
          company("a", { cvs_scored: 5, tokens: 100, cost: 1.5, status: "suspended" }),
          {
            type: "ai_call",
            id: "c1",
            company_id: "a",
            model: "m",
            purpose: "scoring",
            result: "failed",
            failure: "provider_error",
            tokens: 20,
            cost: 0.1,
            at: "2026-11-15T10:00:00Z",
          },
        ],
      }),
    );
    render(<AdminDetailDialog detail={detail} days={7} onClose={vi.fn()} />);
    expect(await screen.findByRole("link", { name: "Company a" })).toBeTruthy();
    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/admin/dashboard/detail/?kind=state&key=active&days=7",
    );
    expect(screen.getByText("Suspended")).toBeTruthy();
    expect(screen.getByText("CVs scored 5")).toBeTruthy();
    expect(screen.getByText("AI cost $1.50")).toBeTruthy();
    expect(screen.getByText("Failed")).toBeTruthy();
    expect(screen.getByText("provider_error")).toBeTruthy();
    expect(screen.getByText("Showing 2 of 3")).toBeTruthy();
  });

  it("says so when empty, shows the server's message, and asks nothing while closed", async () => {
    fetchMock.mockResolvedValue(json({ total: 0, items: [] }));
    const { unmount } = render(<AdminDetailDialog detail={detail} onClose={vi.fn()} />);
    expect(await screen.findByText("Nothing here yet.")).toBeTruthy();
    unmount();
    fetchMock.mockResolvedValue(
      json({ error: { code: "forbidden", message: "No access." } }, false),
    );
    const close = vi.fn();
    render(<AdminDetailDialog detail={detail} onClose={close} />);
    expect((await screen.findByRole("alert")).textContent).toBe("No access.");
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(close).toHaveBeenCalled();
    cleanup();
    fetchMock.mockClear();
    render(<AdminDetailDialog detail={null} onClose={vi.fn()} />);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("AdminPrintableReport", () => {
  const report = {
    days: 7,
    generated_on: "2026-11-15",
    summary: [{ metric: "New companies", current: 2, previous: null, change: null }],
    companies: [{ company: "Acme", plan: null, state: "no_plan", cvs_scored: 3, cost: 1.25 }],
    revenue: {
      received: 100,
      ai_cost: 20,
      margin_percent: 80,
      plans: [{ plan: "Gold", subscribers: 2, received: 100 }],
      history: [{ month: "2026-11", received: 100, ai_cost: 20, margin_percent: 80 }],
    },
  };
  it("shows the tables and prints on request", async () => {
    query = "days=7";
    fetchMock.mockResolvedValue(json(report));
    const print = vi.fn();
    vi.stubGlobal("print", print);
    render(<AdminPrintableReport />);
    expect(
      await screen.findByRole("heading", { name: /Platform report for the last 7 days/ }),
    ).toBeTruthy();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/admin/dashboard/report/?days=7");
    expect(screen.getByRole("region", { name: "Revenue" })).toBeTruthy();
    expect(screen.getByText("Acme")).toBeTruthy();
    expect(screen.getByText("No plan")).toBeTruthy();
    expect(screen.getByText("$1.25")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Print" }));
    expect(print).toHaveBeenCalled();
  });

  it("leaves revenue and cost out when the report has none, and shows errors", async () => {
    const { revenue, ...support } = report;
    void revenue;
    fetchMock.mockResolvedValue(
      json({
        ...support,
        companies: [{ company: "Acme", plan: "Gold", state: "active", cvs_scored: 1 }],
      }),
    );
    render(<AdminPrintableReport />);
    await screen.findByRole("heading", { name: /Platform report/ });
    expect(screen.queryByRole("region", { name: "Revenue" })).toBeNull();
    expect(screen.queryByText("AI cost")).toBeNull();
    cleanup();
    fetchMock.mockResolvedValue(json({ error: { code: "x", message: "Choose one." } }, false));
    render(<AdminPrintableReport />);
    expect((await screen.findByRole("alert")).textContent).toBe("Choose one.");
  });
});
