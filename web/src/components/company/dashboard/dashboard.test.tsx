import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DetailDialog } from "@/components/charts/DetailDialog";
import { timeAgo } from "@/lib/timeAgo";

import { CompanyDashboard, type DashboardSection } from "./CompanyDashboard";
import { Donut } from "./Donut";
import { ExportDialog } from "./ExportDialog";
import { Gauge } from "./Gauge";
import { KpiCard } from "./KpiCard";
import { PrintableReport } from "./PrintableReport";
import type { DashboardData } from "./types";

const push = vi.fn();
let query = "";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(query),
  usePathname: () => "/company",
}));

const fetchMock = vi.fn();
beforeEach(() => {
  query = "";
  push.mockReset();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
const json = (body: unknown, ok = true) => ({
  ok,
  status: ok ? 200 : 404,
  json: async () => body,
});

const card = (value: number | null, change: number | null) => ({
  value,
  previous: 10,
  change,
  series: [1, 2, 3],
});

describe("KpiCard", () => {
  it("takes its pastel from its chart colour", () => {
    render(<KpiCard label="Y" card={card(1, 1)} colour="violet" period="today" onOpen={vi.fn()} />);
    expect(screen.getByRole("button").getAttribute("data-tint")).toBe("lilac");
  });

  it("shows the figure and the change in words and opens on click", async () => {
    const open = vi.fn();
    render(
      <KpiCard
        label="CVs uploaded"
        card={card(12, 20)}
        colour="blue"
        period="today"
        onOpen={open}
      />,
    );
    expect(screen.getByText("12")).toBeTruthy();
    expect(screen.getByText("+20%")).toBeTruthy();
    await userEvent.click(screen.getByRole("button"));
    expect(open).toHaveBeenCalledOnce();
  });

  it("writes a drop with its sign, says New with no earlier period and No data with no figure", () => {
    const { rerender } = render(
      <KpiCard
        label="X"
        card={card(5, -3.5)}
        colour="amber"
        unit=" pts"
        period="today"
        onOpen={vi.fn()}
      />,
    );
    expect(screen.getByText("-3.5 pts")).toBeTruthy();
    rerender(
      <KpiCard label="X" card={card(5, null)} colour="amber" period="today" onOpen={vi.fn()} />,
    );
    expect(screen.getByText("New")).toBeTruthy();
    rerender(
      <KpiCard label="X" card={card(null, null)} colour="amber" period="today" onOpen={vi.fn()} />,
    );
    expect(screen.getAllByText("No data").length).toBeGreaterThan(0);
  });

  it("gives both periods in its tooltip", async () => {
    render(<KpiCard label="X" card={card(12, 20)} colour="blue" period="today" onOpen={vi.fn()} />);
    await userEvent.hover(screen.getByRole("button"));
    const tip = await screen.findByRole("tooltip");
    expect(tip.textContent).toContain("12 in today");
    expect(tip.textContent).toContain("10 in the period before");
  });
});

describe("Donut", () => {
  const parts = [
    { key: "a", label: "Alpha", count: 3, colour: "green" },
    { key: "b", label: "Beta", count: 1, colour: "blue" },
  ];
  it("lists every part with its count, opens a part and gives shares on hover", async () => {
    const open = vi.fn();
    render(<Donut parts={parts} total={4} centreLabel="things" noun="items" onOpen={open} />);
    expect(screen.getByText("things")).toBeTruthy();
    await userEvent.hover(screen.getByRole("button", { name: /Alpha/ }));
    expect((await screen.findByRole("tooltip")).textContent).toContain("75% of 4");
    await userEvent.click(screen.getByRole("button", { name: /Beta/ }));
    expect(open).toHaveBeenCalledWith("b");
  });

  it("draws an empty ring without breaking", () => {
    const { container } = render(
      <Donut
        parts={parts.map((part) => ({ ...part, count: 0 }))}
        total={0}
        centreLabel="x"
        noun="y"
        onOpen={vi.fn()}
      />,
    );
    expect(container.querySelectorAll(".donut__slice")).toHaveLength(0);
    expect(container.innerHTML).not.toContain("NaN");
  });
});

describe("Gauge", () => {
  it("writes the percentage, fills that many segments and opens on click", async () => {
    const open = vi.fn();
    const { container } = render(<Gauge percent={50} scored={5} uploaded={10} onOpen={open} />);
    expect(screen.getByText("50%")).toBeTruthy();
    expect(container.querySelectorAll(".gauge__segment--on")).toHaveLength(6);
    await userEvent.click(screen.getByRole("button"));
    expect(open).toHaveBeenCalledOnce();
  });
  it("says so when nothing was uploaded", () => {
    const { container } = render(<Gauge percent={null} scored={0} uploaded={0} onOpen={vi.fn()} />);
    expect(screen.getByText("No CVs")).toBeTruthy();
    expect(container.querySelectorAll(".gauge__segment--on")).toHaveLength(0);
  });
});

describe("ExportDialog", () => {
  it("offers both formats for the chosen period", async () => {
    render(<ExportDialog days={7} trigger={<button>Open export</button>} />);
    await userEvent.click(screen.getByRole("button", { name: "Open export" }));
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByRole("link", { name: "Download CSV file" }).getAttribute("href"),
    ).toBe("/api/company/dashboard/report/?as=csv&days=7");
    expect(
      within(dialog).getByRole("link", { name: "Open printable page" }).getAttribute("href"),
    ).toBe("/company/dashboard/print?days=7");
  });
});

describe("timeAgo", () => {
  const now = new Date("2026-11-15T12:00:00Z").getTime();
  it.each([
    ["2026-11-15T11:59:50Z", "Just now"],
    ["2026-11-15T11:55:00Z", "5 min ago"],
    ["2026-11-15T09:00:00Z", "3 h ago"],
    ["2026-11-12T12:00:00Z", "3 d ago"],
    ["2026-11-16T12:00:00Z", "Just now"],
  ])("%s is %s", (iso, words) => {
    expect(timeAgo(iso, now)).toBe(words);
  });
});

describe("DetailDialog", () => {
  const detail = { kind: "funnel", key: "scored", title: "Funnel: Scored" };
  const body = {
    total: 5,
    items: [
      {
        type: "candidate",
        id: "c1",
        project_id: "p1",
        project_title: "Proj",
        name: "A. B.",
        file_name: "a.pdf",
        score: "90.0",
        grade: "A",
        stage: "interviewed",
      },
      {
        type: "cv",
        id: "v1",
        project_id: "p1",
        project_title: "Proj",
        file_name: "x.pdf",
        status: "failed",
      },
      { type: "project", id: "p1", title: "Proj", cvs: 4, scored: 3, pending: 1, failed: 0 },
      {
        type: "report",
        id: "r1",
        project_id: "p1",
        project_title: "Proj",
        expires_at: "2026-11-20T00:00:00Z",
        views: 2,
      },
    ],
  };

  it("asks the server and lists every kind of item with links", async () => {
    fetchMock.mockResolvedValue(json(body));
    render(<DetailDialog detail={detail} days={7} onClose={vi.fn()} />);
    expect(await screen.findByRole("link", { name: "A. B." })).toBeTruthy();
    expect(fetchMock.mock.calls[0][0]).toBe(
      "/api/company/dashboard/detail/?kind=funnel&key=scored&days=7",
    );
    expect(screen.getByRole("link", { name: "A. B." }).getAttribute("href")).toBe(
      "/company/projects/p1/candidates/c1",
    );
    expect(screen.getByText("x.pdf")).toBeTruthy();
    expect(screen.getByText("Failed")).toBeTruthy();
    expect(screen.getByText("CVs 4")).toBeTruthy();
    expect(screen.getByText("Ends 2026-11-20")).toBeTruthy();
    expect(screen.getByText("Showing 4 of 5")).toBeTruthy();
  });

  it("names the project when the funnel belongs to one", async () => {
    fetchMock.mockResolvedValue(json({ total: 0, items: [] }));
    render(<DetailDialog detail={{ ...detail, project: "p9" }} onClose={vi.fn()} />);
    expect(await screen.findByText("Nothing here yet.")).toBeTruthy();
    expect(fetchMock.mock.calls[0][0]).toContain("project=p9");
  });

  it("shows the server's message when it cannot be read, and closes", async () => {
    fetchMock.mockResolvedValue(
      json({ error: { code: "not_found", message: "Not found." } }, false),
    );
    const close = vi.fn();
    render(<DetailDialog detail={detail} onClose={close} />);
    expect((await screen.findByRole("alert")).textContent).toBe("Not found.");
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(close).toHaveBeenCalled();
  });

  it("asks nothing while closed", () => {
    render(<DetailDialog detail={null} onClose={vi.fn()} />);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

const data = (over: Partial<DashboardData> = {}): DashboardData => ({
  refresh_seconds: 3,
  days: 30,
  choices: [1, 7, 30, 90, 180],
  counts: {
    projects: 5,
    scored: 198,
    shortlisted: 64,
    interviewed: 12,
    on_hold: 3,
    selected: 4,
    rejected: 20,
  },
  recommendations: {
    total: 198,
    parts: [
      { label: "strong_match", count: 31 },
      { label: "possible", count: 98 },
      { label: "not_recommended", count: 69 },
    ],
  },
  projects: { not_started: 54, in_progress: 14, ready: 32 },
  screening: { uploaded: 215, scored: 198, percent: 92.1 },
  project_rows: [
    {
      id: "p1",
      title: "Python Developer",
      cvs: 12,
      failed: 0,
      capacity: 50,
      scored: 10,
      best_score: 94.5,
      average_score: 71.2,
      ats_average: 64,
      shortlisted: 3,
      interviewed: 2,
      selected: 1,
      updated_at: "2026-11-20T10:00:00Z",
    },
  ],
  attention: [
    { id: "p1", title: "Python Developer", capacity: 50, reason: "failed", count: 2 },
    { id: "p1", title: "Python Developer", capacity: 50, reason: "almost_full", count: 48 },
  ],
  uploads_per_day: { start: "2026-11-01", values: [1, 0, 4] },
  flag_split: [
    { flag: "new", count: 5 },
    { flag: "shortlisted", count: 3 },
    { flag: "interviewed", count: 2 },
    { flag: "on_hold", count: 0 },
    { flag: "selected", count: 1 },
    { flag: "rejected", count: 4 },
  ],
  missed_requirements: [
    {
      requirement: "5+ years of Python",
      kind: "must",
      project_id: "p1",
      project_title: "Python Developer",
      missing: 7,
      judged: 10,
    },
  ],
  top: [
    {
      id: "c1",
      project_id: "p1",
      project_title: "Python Developer",
      name: "A. H.",
      file_name: "a.pdf",
      score: "94.5",
      grade: "A",
      stage: "interviewed",
      rank: 1,
      ats_score: 92,
    },
  ],
  ...over,
});
const charts = {
  refresh_seconds: 3,
  funnel: [
    { step: "uploaded", count: 10 },
    { step: "read", count: 8 },
    { step: "scored", count: 4 },
    { step: "shortlisted", count: 2 },
    { step: "interviewed", count: 1 },
    { step: "selected", count: 0 },
  ],
  distribution: ["A", "B", "C", "D", "E"].map((grade) => ({ grade, count: 1 })),
  trend: {
    days: 7,
    choices: [7, 30, 90],
    start: "2026-11-01",
    metrics: {
      uploaded: {
        current: [1, 2],
        previous: [1, 1],
        total: 3,
        previous_total: 2,
        change_percent: 50,
      },
      scored: {
        current: [0, 5],
        previous: [0, 0],
        total: 5,
        previous_total: 0,
        change_percent: null,
      },
    },
  },
};
const route = (dashboard: DashboardData, extra: Record<string, unknown> = {}) =>
  fetchMock.mockImplementation(async (url: string) => {
    if (url.includes("/dashboard/detail/")) return json(extra.detail ?? { total: 0, items: [] });
    if (url.includes("/api/company/dashboard/")) return json(dashboard);
    if (url.includes("/api/company/charts/")) return json(charts);
    if (url.includes("/api/company/activity/"))
      return json(
        extra.log ?? {
          entries: [
            {
              id: "e1",
              kind: "upload",
              actor_name: "Olu Owner",
              target_kind: "",
              target_id: "",
              details: {},
              created_at: "2030-01-05T09:30:12Z",
            },
          ],
          next_before: null,
          people: [{ id: 1, name: "Olu Owner" }],
        },
      );
    return json({});
  });

const onTab = vi.fn();
const show = (tab: DashboardSection = "overview") =>
  render(<CompanyDashboard tab={tab} onTab={onTab} />);

describe("CompanyDashboard", () => {
  it("has four tabs and shows only the chosen one", async () => {
    route(data());
    const user = userEvent.setup();
    show("overview");
    expect((await screen.findAllByRole("tab")).map((tab) => tab.textContent)).toEqual([
      "Overview",
      "Projects",
      "Candidates",
      "Usage",
    ]);
    for (const other of ["Top candidates", "Projects overview", "Funnel"]) {
      expect(screen.queryByRole("heading", { name: other })).toBeNull();
    }
    await user.click(screen.getByRole("tab", { name: "Candidates" }));
    expect(onTab).toHaveBeenCalledWith("candidates");
  });

  it("offers today, this week, this month, 3 months and 6 months", async () => {
    route(data());
    show("overview");
    await screen.findByRole("button", { name: "This month" });
    expect(
      screen.getAllByRole("button", { pressed: false }).map((button) => button.textContent),
    ).toEqual(expect.arrayContaining(["Today", "This week", "3 months", "6 months"]));
    expect(screen.getByRole("button", { name: "This month" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
  });

  it("Overview shows only a name and a number in each card, with no comparison", async () => {
    route(data());
    const { container } = show("overview");
    expect(await screen.findByText("CVs scored")).toBeTruthy();
    const cards = [...container.querySelectorAll(".count-card")].map((item) => item.textContent);
    const tints = [...container.querySelectorAll(".count-card")].map((item) =>
      item.getAttribute("data-tint"),
    );
    expect(new Set(tints.slice(0, 5)).size).toBe(5);
    expect(cards).toEqual([
      "Projects5",
      "CVs scored198",
      "Shortlisted64",
      "Interviewed12",
      "On hold3",
      "Selected4",
      "Rejected20",
    ]);
    expect(container.textContent).not.toMatch(/before|previous|Activity|Quick actions/i);
  });

  it("the projects number goes to the projects page", async () => {
    route(data());
    show("overview");
    const link = await screen.findByRole("link", { name: "5" });
    expect(link.getAttribute("href")).toBe("/company/projects");
  });

  it("a flag number opens the candidates behind it, and a row's flag can be changed", async () => {
    const row = {
      type: "candidate",
      id: "c1",
      project_id: "p1",
      project_title: "Python Developer",
      name: "A. H.",
      file_name: "a.pdf",
      score: "94.5",
      grade: "A",
      stage: "shortlisted",
    };
    route(data(), { detail: { total: 1, items: [row] } });
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url.includes("/candidates/stage/")) return json({});
      if (url.includes("/dashboard/detail/")) return json({ total: 1, items: [row] });
      return json(data());
    });
    const user = userEvent.setup();
    show("overview");
    await user.click(await screen.findByRole("button", { name: "Shortlisted: 64" }));
    const dialog = await screen.findByRole("dialog");
    expect(
      fetchMock.mock.calls.some(([url]) =>
        String(url).includes("kind=stage&key=shortlisted&days=30"),
      ),
    ).toBe(true);
    expect(await within(dialog).findByText("94.5")).toBeTruthy();
    await user.selectOptions(within(dialog).getByLabelText("Flag for A. H."), "interviewed");
    await vi.waitFor(() => {
      const call = fetchMock.mock.calls.find(([url]) => String(url).includes("/candidates/stage/"));
      expect(call?.[0]).toBe("/api/company/projects/p1/candidates/stage/");
      expect(JSON.parse(call?.[1].body)).toEqual({ candidate_ids: ["c1"], stage: "interviewed" });
    });
    await user.click(within(dialog).getByRole("link", { name: "A. H." }));
  });

  it("clicking a row opens the candidate, and CVs scored uses the metric list", async () => {
    const row = {
      type: "candidate",
      id: "c1",
      project_id: "p1",
      project_title: "Python Developer",
      name: "A. H.",
      file_name: "a.pdf",
      score: "94.5",
      grade: "A",
      stage: "new",
    };
    fetchMock.mockImplementation(async (url: string) =>
      url.includes("/dashboard/detail/") ? json({ total: 1, items: [row] }) : json(data()),
    );
    const user = userEvent.setup();
    show("overview");
    await user.click(await screen.findByRole("button", { name: "CVs scored: 198" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(await within(dialog).findByText("Python Developer"));
    expect(push).toHaveBeenCalledWith("/company/projects/p1/candidates/c1");
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).includes("kind=metric&key=scored")),
    ).toBe(true);
  });

  it("Projects shows how the projects stand and how much is scored", async () => {
    route(data());
    show("projects");
    for (const title of ["Projects overview", "Screening progress"]) {
      expect(await screen.findByRole("heading", { name: title })).toBeTruthy();
    }
    expect(screen.getByText("92.1%")).toBeTruthy();
  });

  it("Candidates shows the top ten with project, AI score and ATS score", async () => {
    route(data());
    show("candidates");
    const table = await screen.findByRole("region", { name: "Top candidates" });
    expect(within(table).getByRole("link", { name: "A. H." }).getAttribute("href")).toBe(
      "/company/projects/p1/candidates/c1",
    );
    expect(within(table).getByText("Python Developer")).toBeTruthy();
    expect(within(table).getByText("94.5")).toBeTruthy();
    expect(within(table).getByText("92")).toBeTruthy();
    expect(screen.getByRole("link", { name: "View all" }).getAttribute("href")).toBe(
      "/company/candidates",
    );
  });

  it("Candidates also shows the split by recommendation, the funnel and the grades", async () => {
    route(data());
    show("candidates");
    for (const title of [
      "Top candidates",
      "CVs by recommendation",
      "Funnel",
      "Score distribution",
    ]) {
      expect(await screen.findByRole("heading", { name: title })).toBeTruthy();
    }
    expect(screen.queryByRole("heading", { name: "Trend" })).toBeNull();
  });

  it("Usage shows the plan's limits and the pace, and leaves the limits out without a plan", async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (url.includes("/api/company/dashboard/")) return json(data());
      if (url.includes("/api/company/charts/")) return json(charts);
      if (url.includes("/api/company/usage/history/")) {
        return json({
          periods: [
            {
              id: "p1",
              start: "2026-11-01T00:00:00Z",
              end: "2026-12-01T00:00:00Z",
              cvs: 4,
              tokens_in: 1,
              tokens_out: 2,
              tokens: 3,
              estimated_cost: "0.100000",
            },
          ],
          selected: "p1",
          projects: [],
          uploads: [],
        });
      }
      if (url.includes("/api/company/usage/")) {
        return json({
          plan_name: "Growth",
          state: "active",
          period_start: "2026-11-01",
          period_end: "2026-11-30",
          cvs: { used: 90, limit: 100, left: 10, warning: 90 },
          estimated_cost: "0.00",
          projects: { used: 3, limit: 10 },
          refresh_seconds: 3,
        });
      }
      return json({});
    });
    show("usage");
    expect(await screen.findByRole("heading", { name: "Usage this period" })).toBeTruthy();
    expect(screen.getByRole("meter", { name: "CVs" }).getAttribute("aria-valuenow")).toBe("90");
    expect(screen.getByText("90% used")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Usage and billing" }).getAttribute("href")).toBe(
      "/company/billing",
    );
    expect(await screen.findByRole("heading", { name: "Usage by period" })).toBeTruthy();
    expect(await screen.findByRole("heading", { name: "Trend" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Funnel" })).toBeNull();
    cleanup();
    fetchMock.mockImplementation(async (url: string) =>
      url.includes("/api/company/usage/")
        ? json({ error: { code: "forbidden", message: "No." } }, false)
        : url.includes("/api/company/charts/")
          ? json(charts)
          : json(data()),
    );
    show("usage");
    expect(await screen.findByRole("heading", { name: "Trend" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Usage this period" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Usage by period" })).toBeNull();
  });

  it("asks again for the chosen period, on any tab", async () => {
    route(data());
    show("overview");
    await userEvent.click(await screen.findByRole("button", { name: "This week" }));
    await vi.waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => url === "/api/company/dashboard/?days=7")).toBe(
        true,
      ),
    );
  });

  it("Projects also shows what needs attention, every project, the daily CVs and the averages", async () => {
    route(data());
    show("projects");
    expect(await screen.findByRole("heading", { name: "Needs attention" })).toBeTruthy();
    expect(screen.getByText("2 CVs failed to process")).toBeTruthy();
    expect(screen.getByText("48 of 50 CVs held, nearly full")).toBeTruthy();
    const table = screen.getByRole("region", { name: "All projects" });
    expect(within(table).getByRole("link", { name: "Python Developer" }).getAttribute("href")).toBe(
      "/company/projects/p1",
    );
    expect(within(table).getByText("12 of 50")).toBeTruthy();
    expect(within(table).getByText("94.5")).toBeTruthy();
    expect(screen.getByRole("list", { name: "CVs added each day" }).children).toHaveLength(3);
    const averages = screen.getByRole("region", { name: "Average score per project" });
    expect(
      within(averages)
        .getByRole("meter", { name: "AI score of Python Developer" })
        .getAttribute("aria-valuenow"),
    ).toBe("71.2");
    expect(within(averages).getByText("64")).toBeTruthy();
  });

  it("Projects says so when nothing needs attention", async () => {
    route(data({ attention: [], project_rows: [] }));
    show("projects");
    expect(await screen.findByText("Nothing needs attention.")).toBeTruthy();
    expect(screen.getAllByText("No projects yet.").length).toBe(2);
  });

  it("Candidates shows the flag split and the most missed requirements", async () => {
    route(data());
    const user = userEvent.setup();
    show("candidates");
    expect(await screen.findByRole("heading", { name: "Candidates by flag" })).toBeTruthy();
    const missed = screen.getByRole("region", { name: "Most missed requirements" });
    expect(within(missed).getByText("5+ years of Python")).toBeTruthy();
    expect(within(missed).getByText("Must-have")).toBeTruthy();
    expect(within(missed).getByText("7 of 10")).toBeTruthy();
    const split = screen.getByRole("heading", { name: "Candidates by flag" }).closest("section")!;
    await user.click(within(split).getByRole("button", { name: /Interviewed/ }));
    await vi.waitFor(() =>
      expect(String(fetchMock.mock.calls.at(-1)?.[0])).toContain("kind=flag&key=interviewed"),
    );
  });

  it("Candidates says so when no requirement is missing", async () => {
    route(data({ missed_requirements: [] }));
    show("candidates");
    expect(await screen.findByText("No requirement is missing yet.")).toBeTruthy();
  });

  it("opens a part of a donut and the gauge (Projects)", async () => {
    route(data());
    const user = userEvent.setup();
    show("projects");
    await screen.findByRole("heading", { name: "Projects overview" });
    const asked = () => String(fetchMock.mock.calls.at(-1)?.[0]);
    await user.click(screen.getByRole("button", { name: /Not started/ }));
    await vi.waitFor(() => expect(asked()).toContain("kind=project_status&key=not_started"));
    await user.click(await screen.findByRole("button", { name: "Close" }));
    await user.click(screen.getByRole("button", { name: /92.1%/ }));
    await vi.waitFor(() => expect(asked()).toContain("kind=screening"));
  });

  it("opens a recommendation, a funnel step and a grade (Candidates)", async () => {
    route(data());
    const user = userEvent.setup();
    show("candidates");
    await screen.findByRole("heading", { name: "Score distribution" });
    const asked = () => String(fetchMock.mock.calls.at(-1)?.[0]);
    await user.click(screen.getByRole("button", { name: /Possible/ }));
    await vi.waitFor(() => expect(asked()).toContain("kind=recommendation&key=possible"));
    await user.click(await screen.findByRole("button", { name: "Close" }));
    const funnel = screen.getByRole("heading", { name: "Funnel" }).closest("section")!;
    await user.click(within(funnel).getByRole("button", { name: /Interview/ }));
    await vi.waitFor(() => expect(asked()).toContain("kind=funnel&key=interview"));
    await user.click(await screen.findByRole("button", { name: "Close" }));
    await user.click(await screen.findByRole("button", { name: /Grade C/ }));
    await vi.waitFor(() => expect(asked()).toContain("kind=grade&key=C"));
  });

  it("copes with a company that has nothing yet", async () => {
    route(
      data({
        counts: {
          projects: 0,
          scored: 0,
          shortlisted: 0,
          interviewed: 0,
          on_hold: 0,
          selected: 0,
          rejected: 0,
        },
        recommendations: { total: 0, parts: [] },
        projects: { not_started: 0, in_progress: 0, ready: 0 },
        screening: { uploaded: 0, scored: 0, percent: null },
        top: [],
      }),
    );
    const { container } = show("overview");
    expect(await screen.findByRole("button", { name: "Selected: 0" })).toBeTruthy();
    cleanup();
    const projects = show("projects");
    expect(await screen.findByText("No CVs")).toBeTruthy();
    projects.unmount();
    const candidates = show("candidates");
    expect(await screen.findByText("No scored candidates yet.")).toBeTruthy();
    expect(container.innerHTML).not.toContain("NaN");
    candidates.unmount();
  });

  it("keeps the tabs and says why when the numbers cannot be read", async () => {
    fetchMock.mockResolvedValue(
      json({ error: { code: "not_found", message: "Not found." } }, false),
    );
    show("overview");
    expect((await screen.findByRole("alert")).textContent).toBe("Not found.");
    expect(screen.getAllByRole("tab")).toHaveLength(4);
  });
});

describe("PrintableReport", () => {
  const report = {
    days: 7,
    generated_on: "2026-11-15",
    summary: [{ metric: "Shortlisted", count: 5 }],
    recommendations: [{ label: "strong_match", count: 2 }],
    projects: [{ project: "Alpha", cvs: 5, scored: 4, strong_matches: 2, average_score: null }],
  };
  it("shows the three tables for the chosen period and prints on request", async () => {
    query = "days=7";
    fetchMock.mockResolvedValue(json(report));
    const print = vi.fn();
    vi.stubGlobal("print", print);
    render(<PrintableReport />);
    expect(await screen.findByRole("heading", { name: /Report for the last 7 days/ })).toBeTruthy();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/company/dashboard/report/?days=7");
    expect(screen.getByRole("region", { name: "Summary" })).toBeTruthy();
    expect(screen.getByText("Strong match")).toBeTruthy();
    expect(screen.getByText("Alpha")).toBeTruthy();
    expect(screen.getAllByText("No data").length).toBe(1);
    await userEvent.click(screen.getByRole("button", { name: "Print" }));
    expect(print).toHaveBeenCalled();
  });
  it("shows the server's message when it cannot be read", async () => {
    fetchMock.mockResolvedValue(json({ error: { code: "bad", message: "Choose one." } }, false));
    render(<PrintableReport />);
    expect((await screen.findByRole("alert")).textContent).toBe("Choose one.");
  });
});
