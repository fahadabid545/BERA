import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DetailDialog } from "@/components/charts/DetailDialog";
import { timeAgo } from "@/lib/timeAgo";

import { ActivityFeed } from "./ActivityFeed";
import { CompanyDashboard, type DashboardSection } from "./CompanyDashboard";
import { Donut } from "./Donut";
import { ExportDialog } from "./ExportDialog";
import { Gauge } from "./Gauge";
import { InsightCard } from "./InsightCard";
import { KpiCard } from "./KpiCard";
import { PendingActions } from "./PendingActions";
import { PrintableReport } from "./PrintableReport";
import { QuickActions } from "./QuickActions";
import { TopCandidates } from "./TopCandidates";
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

describe("InsightCard", () => {
  it("sets this period next to the one before and opens on click", async () => {
    const open = vi.fn();
    render(
      <InsightCard
        title="Hiring pace"
        headline="+20%"
        tag={{ text: "More than before", variant: "success" }}
        now={12}
        before={10}
        unit=""
        tipLines={["a", "b"]}
        onOpen={open}
      />,
    );
    expect(screen.getByText("More than before")).toBeTruthy();
    expect(screen.getByText("12")).toBeTruthy();
    expect(screen.getByText("10")).toBeTruthy();
    await userEvent.click(screen.getByRole("button"));
    expect(open).toHaveBeenCalledOnce();
  });

  it("says No data for a missing figure", () => {
    render(
      <InsightCard
        title="T"
        headline="No data"
        tag={{ text: "No earlier period", variant: "neutral" }}
        now={null}
        before={null}
        unit="%"
        tipLines={[]}
        onOpen={vi.fn()}
      />,
    );
    expect(screen.getAllByText("No data").length).toBe(3);
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

const person = (index: number) => ({
  id: `c${index}`,
  project_id: "p1",
  project_title: "Project",
  name: `N${index}`,
  file_name: `f${index}.pdf`,
  score: String(90 - index),
  grade: "A",
  stage: "new",
  rank: index + 1,
  strengths: ["Strong"],
  ats_score: 80,
});
const top = (count = 3): DashboardData["top"] => ({
  projects: [
    { id: "p1", title: "Project" },
    { id: "p2", title: "Second" },
  ],
  project_id: "p1",
  compare_limits: { min: 2, max: 3 },
  candidates: Array.from({ length: count }, (_, index) => person(index)),
});

describe("TopCandidates", () => {
  it("links each name to the candidate and shows score, grade and strengths", () => {
    render(<TopCandidates top={top()} onProject={vi.fn()} />);
    expect(screen.getByRole("link", { name: "N0" }).getAttribute("href")).toBe(
      "/company/projects/p1/candidates/c0",
    );
    expect(screen.getAllByText("Grade A")).toHaveLength(3);
    expect(screen.getAllByText("Strong")).toHaveLength(3);
    expect(screen.getByRole("link", { name: "View all" }).getAttribute("href")).toBe(
      "/company/projects/p1/candidates",
    );
  });

  it("compares two to the limit, going to the comparison page", async () => {
    const user = userEvent.setup();
    render(<TopCandidates top={top(4)} onProject={vi.fn()} />);
    const compare = screen.getByRole("button", { name: "Compare selected (0)" });
    expect((compare as HTMLButtonElement).disabled).toBe(true);
    const boxes = screen.getAllByRole("checkbox");
    await user.click(boxes[0]);
    expect(
      (screen.getByRole("button", { name: "Compare selected (1)" }) as HTMLButtonElement).disabled,
    ).toBe(true);
    await user.click(boxes[1]);
    await user.click(screen.getByRole("button", { name: "Compare selected (2)" }));
    expect(push).toHaveBeenCalledWith("/company/projects/p1/compare?ids=c0,c1");
    await user.click(boxes[2]);
    await user.click(boxes[3]);
    expect(
      (screen.getByRole("button", { name: "Compare selected (4)" }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("asks for another project and clears the picks", async () => {
    const onProject = vi.fn();
    const user = userEvent.setup();
    render(<TopCandidates top={top()} onProject={onProject} />);
    await user.click(screen.getAllByRole("checkbox")[0]);
    await user.selectOptions(screen.getByLabelText("Project"), "p2");
    expect(onProject).toHaveBeenCalledWith("p2");
    expect(screen.getByRole("button", { name: "Compare selected (0)" })).toBeTruthy();
  });

  it("says so when nothing is scored yet", () => {
    render(
      <TopCandidates top={{ ...top(0), project_id: null, projects: [] }} onProject={vi.fn()} />,
    );
    expect(screen.getByText("No scored candidates yet.")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "View all" })).toBeNull();
  });
});

describe("QuickActions and export", () => {
  it("goes to the project for upload and sharing, and to the list without one", () => {
    const { rerender } = render(<QuickActions projectId="p1" days={7} />);
    expect(screen.getByRole("link", { name: "Upload CVs" }).getAttribute("href")).toBe(
      "/company/projects/p1",
    );
    expect(screen.getByRole("link", { name: "Share report" }).getAttribute("href")).toBe(
      "/company/projects/p1/candidates",
    );
    expect(screen.getByRole("link", { name: "New project" }).getAttribute("href")).toBe(
      "/company/projects/new",
    );
    rerender(<QuickActions projectId={null} days={7} />);
    expect(screen.getByRole("link", { name: "Upload CVs" }).getAttribute("href")).toBe(
      "/company/projects",
    );
  });

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

describe("PendingActions", () => {
  it("shows the counts, the total and opens a row; an empty row cannot be opened", async () => {
    const open = vi.fn();
    render(
      <PendingActions
        pending={{ awaiting_confirmation: 2, failed: 0, links_expiring: 1 }}
        onOpen={open}
      />,
    );
    expect(screen.getByText("3 pending")).toBeTruthy();
    const buttons = screen.getAllByRole("button", { name: "Review" });
    expect((buttons[1] as HTMLButtonElement).disabled).toBe(true);
    await userEvent.click(buttons[0]);
    expect(open).toHaveBeenCalledWith("awaiting_confirmation", "CVs awaiting confirmation");
  });
});

describe("ActivityFeed", () => {
  const at = new Date().toISOString();
  it("writes each event as a sentence with links", () => {
    render(
      <ActivityFeed
        events={[
          {
            kind: "scored",
            id: "c1",
            project_id: "p1",
            project_title: "Proj",
            name: "A. B.",
            file_name: "a.pdf",
            score: "90.0",
            at,
          },
          {
            kind: "moved",
            id: "c2",
            project_id: "p1",
            project_title: "Proj",
            name: "",
            file_name: "b.pdf",
            score: null,
            to_stage: "interviewed",
            at,
          },
          { kind: "shared", id: "r1", project_id: "p1", project_title: "Proj", views: 3, at },
        ]}
      />,
    );
    expect(screen.getByRole("link", { name: "A. B." }).getAttribute("href")).toBe(
      "/company/projects/p1/candidates/c1",
    );
    expect(screen.getByRole("link", { name: "b.pdf" })).toBeTruthy();
    expect(screen.getByText(/scored 90.0 in/)).toBeTruthy();
    expect(screen.getByText(/moved to Interviewed in/)).toBeTruthy();
    expect(screen.getByText(/opened 3 times/)).toBeTruthy();
    expect(screen.getAllByText("Just now")).toHaveLength(3);
  });
  it("says so when nothing happened", () => {
    render(<ActivityFeed events={[]} />);
    expect(screen.getByText("Nothing has happened yet.")).toBeTruthy();
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
  choices: [1, 7, 30],
  cards: {
    uploaded: card(212, 18),
    scored: card(198, 24),
    shortlisted: card(64, 10),
    average_score: card(72.4, -1.2),
  },
  insights: {
    hiring_pace: { current: 212, previous: 180, change: 17.8 },
    match_quality: { share: 31, previous_share: 26, change: 5 },
    time_to_shortlist: { hours: 57.6, previous_hours: 80.2 },
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
  top: top(),
  pending: { awaiting_confirmation: 12, failed: 3, links_expiring: 2 },
  activity: [],
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
  it("has five tabs and shows only the chosen one", async () => {
    route(data());
    const user = userEvent.setup();
    show("overview");
    expect((await screen.findAllByRole("tab")).map((tab) => tab.textContent)).toEqual([
      "Overview",
      "Projects",
      "Candidates",
      "Usage",
      "Activity",
    ]);
    expect(screen.getByRole("heading", { name: "Quick actions" })).toBeTruthy();
    for (const other of ["Top candidates", "Projects overview", "Live activity", "Funnel"]) {
      expect(screen.queryByRole("heading", { name: other })).toBeNull();
    }
    await user.click(screen.getByRole("tab", { name: "Candidates" }));
    expect(onTab).toHaveBeenCalledWith("candidates");
  });

  it("Overview shows the figures with their change, the insights and what waits", async () => {
    route(data());
    show("overview");
    expect(await screen.findByRole("heading", { name: "Pending actions" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "This month" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    expect(screen.getByText("+17.8%")).toBeTruthy();
    expect(screen.getByText("2.4 days")).toBeTruthy();
    expect(screen.getByText("Faster by 22.6 h")).toBeTruthy();
  });

  it("Projects shows how the projects stand and how much is scored", async () => {
    route(data());
    show("projects");
    for (const title of ["Projects overview", "Screening progress"]) {
      expect(await screen.findByRole("heading", { name: title })).toBeTruthy();
    }
    expect(screen.getByText("92.1%")).toBeTruthy();
  });

  it("Candidates shows the best, the split by recommendation, the funnel and the grades", async () => {
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

  it("Activity shows what just happened", async () => {
    route(data());
    show("activity");
    expect(await screen.findByRole("heading", { name: "Live activity" })).toBeTruthy();
    expect(await screen.findByRole("heading", { name: "Activity log" })).toBeTruthy();
    expect(await screen.findByText("Uploaded CVs")).toBeTruthy();
  });

  it("asks again for the chosen period, on any tab", async () => {
    route(data());
    show("overview");
    await screen.findByRole("heading", { name: "Pending actions" });
    await userEvent.click(screen.getByRole("button", { name: "This week" }));
    await vi.waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => url === "/api/company/dashboard/?days=7")).toBe(
        true,
      ),
    );
  });

  it("asks again for another project's top candidates", async () => {
    route(data());
    show("candidates");
    await screen.findByRole("heading", { name: "Top candidates" });
    await userEvent.selectOptions(screen.getByLabelText("Project"), "p2");
    await vi.waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([url]) => url === "/api/company/dashboard/?project=p2"),
      ).toBe(true),
    );
  });

  it("opens what is behind a card and a pending row (Overview)", async () => {
    route(data());
    const user = userEvent.setup();
    show("overview");
    await screen.findByRole("heading", { name: "Pending actions" });
    const asked = () => String(fetchMock.mock.calls.at(-1)?.[0]);
    await user.click(screen.getByRole("button", { name: /^CVs uploaded/ }));
    await vi.waitFor(() => expect(asked()).toContain("kind=metric&key=uploaded&days=30"));
    await user.click(await screen.findByRole("button", { name: "Close" }));
    await user.click(screen.getAllByRole("button", { name: "Review" })[1]);
    await vi.waitFor(() => expect(asked()).toContain("kind=pending&key=failed"));
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
    await user.click(screen.getByRole("button", { name: /Interview/ }));
    await vi.waitFor(() => expect(asked()).toContain("kind=funnel&key=interview"));
    await user.click(await screen.findByRole("button", { name: "Close" }));
    await user.click(await screen.findByRole("button", { name: /Grade C/ }));
    await vi.waitFor(() => expect(asked()).toContain("kind=grade&key=C"));
  });

  it("copes with a company that has nothing yet", async () => {
    route(
      data({
        cards: {
          uploaded: card(0, null),
          scored: card(0, null),
          shortlisted: card(0, null),
          average_score: card(null, null),
        },
        insights: {
          hiring_pace: { current: 0, previous: 0, change: null },
          match_quality: { share: null, previous_share: null, change: null },
          time_to_shortlist: { hours: null, previous_hours: null },
        },
        recommendations: { total: 0, parts: [] },
        projects: { not_started: 0, in_progress: 0, ready: 0 },
        screening: { uploaded: 0, scored: 0, percent: null },
        top: { ...top(0), projects: [], project_id: null },
        pending: { awaiting_confirmation: 0, failed: 0, links_expiring: 0 },
      }),
    );
    const { container } = show("overview");
    expect(await screen.findByText("0 pending")).toBeTruthy();
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
    expect(screen.getAllByRole("tab")).toHaveLength(5);
  });
});

describe("PrintableReport", () => {
  const report = {
    days: 7,
    generated_on: "2026-11-15",
    summary: [{ metric: "CVs uploaded", current: 5, previous: null, change: null }],
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
    expect(screen.getAllByText("No data").length).toBe(3);
    await userEvent.click(screen.getByRole("button", { name: "Print" }));
    expect(print).toHaveBeenCalled();
  });
  it("shows the server's message when it cannot be read", async () => {
    fetchMock.mockResolvedValue(json({ error: { code: "bad", message: "Choose one." } }, false));
    render(<PrintableReport />);
    expect((await screen.findByRole("alert")).textContent).toBe("Choose one.");
  });
});
