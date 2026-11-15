import { act, cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CompanyCharts } from "./CompanyCharts";
import { Coverage } from "./Coverage";
import { Funnel } from "./Funnel";
import { Histogram } from "./Histogram";
import { ProjectCharts } from "./ProjectCharts";
import { Ranking } from "./Ranking";
import { Trend } from "./Trend";

afterEach(cleanup);

const STEPS = [
  { step: "uploaded", count: 10 },
  { step: "read", count: 8 },
  { step: "scored", count: 4 },
  { step: "shortlisted", count: 2 },
  { step: "interview", count: 1 },
  { step: "approved", count: 0 },
];

describe("Funnel", () => {
  it("shows the six steps in order with counts and the share kept from the step before", () => {
    render(<Funnel steps={STEPS} />);
    const items = within(screen.getByRole("list", { name: "Funnel" })).getAllByRole("listitem");
    expect(items.map((item) => item.textContent)).toEqual([
      "Uploaded10",
      "Read8 · 80%",
      "Scored4 · 50%",
      "Shortlisted2 · 50%",
      "Interview1 · 50%",
      "Approved0 · 0%",
    ]);
  });

  it("sizes each bar against the first step and copes with no data at all", () => {
    const { container } = render(<Funnel steps={STEPS} />);
    const widths = [...container.querySelectorAll<HTMLElement>(".chart-funnel__bar")].map(
      (bar) => bar.style.width,
    );
    expect(widths).toEqual(["100%", "80%", "40%", "20%", "10%", "0%"]);
    cleanup();
    const empty = render(<Funnel steps={STEPS.map((item) => ({ ...item, count: 0 }))} />);
    expect(empty.container.querySelectorAll(".chart-funnel__bar")).toHaveLength(6);
    expect(screen.getAllByText("0")).toHaveLength(6);
  });
});

describe("Histogram", () => {
  it("shows a column with its count for every grade, even an empty one", () => {
    render(
      <Histogram
        grades={[
          { grade: "A", count: 4 },
          { grade: "B", count: 2 },
          { grade: "C", count: 0 },
          { grade: "D", count: 1 },
          { grade: "E", count: 0 },
        ]}
      />,
    );
    const columns = within(screen.getByRole("list", { name: "Score distribution" })).getAllByRole(
      "listitem",
    );
    expect(columns.map((item) => item.textContent)).toEqual([
      "4Grade A",
      "2Grade B",
      "0Grade C",
      "1Grade D",
      "0Grade E",
    ]);
  });
});

describe("Ranking", () => {
  const candidates = [
    { rank: 1, candidate_id: "k1", file_name: "a.pdf", name: "J. E.", score: "90.0", grade: "A" },
    { rank: 2, candidate_id: "k2", file_name: "b.pdf", name: "", score: "70.5", grade: "C" },
  ];
  it("lists the best first, linking to each candidate, falling back to the file name", () => {
    const { container } = render(<Ranking projectId="p1" candidates={candidates} />);
    expect(screen.getByRole("link", { name: "J. E." }).getAttribute("href")).toBe(
      "/company/projects/p1/candidates/k1",
    );
    expect(screen.getByRole("link", { name: "b.pdf" })).toBeTruthy();
    expect(screen.getByText(/70.5/)).toBeTruthy();
    const bars = [...container.querySelectorAll<HTMLElement>(".chart-ranking__bar")];
    expect(bars.map((bar) => bar.style.width)).toEqual(["90%", "70.5%"]);
  });
});

describe("Coverage", () => {
  const item = {
    requirement_id: "r1",
    text: "Python",
    kind: "must" as const,
    met: 2,
    partly_met: 1,
    missing: 1,
    not_judged: 0,
  };
  it("splits each requirement's bar and writes every count", () => {
    const { container } = render(<Coverage candidates={4} requirements={[item]} />);
    expect(screen.getByText("Python")).toBeTruthy();
    expect(screen.getByText("Must-have")).toBeTruthy();
    expect(screen.getByText("Met 2")).toBeTruthy();
    expect(screen.getByText("Partly met 1")).toBeTruthy();
    expect(screen.getByText("Missing 1")).toBeTruthy();
    expect(screen.getByText("Not judged 0")).toBeTruthy();
    const widths = [...container.querySelectorAll<HTMLElement>(".chart-coverage__part")].map(
      (part) => part.style.width,
    );
    expect(widths).toEqual(["50%", "25%", "25%"]);
  });
});

describe("Trend", () => {
  const metric = (over: object = {}) => ({
    current: [0, 1, 3],
    previous: [1, 1, 1],
    total: 4,
    previous_total: 3,
    change_percent: 33.3,
    ...over,
  });
  it("shows the total, the previous total and the change in words", () => {
    render(<Trend metric={metric()} start="2026-11-01" label="CVs uploaded" />);
    expect(screen.getByText("4")).toBeTruthy();
    expect(screen.getByText("+33.3% against the previous period")).toBeTruthy();
    expect(screen.getByText("Previous period 3")).toBeTruthy();
    expect(screen.getAllByRole("img")[0].getAttribute("aria-label")).toBe(
      "CVs uploaded: this period 4, previous period 3",
    );
    expect(screen.getAllByText(/1 Nov/).length).toBeGreaterThan(0);
  });
  it("shows a drop with its sign and says so when there was no earlier period", () => {
    render(<Trend metric={metric({ change_percent: -75 })} start="2026-11-01" label="x" />);
    expect(screen.getByText("-75% against the previous period")).toBeTruthy();
    cleanup();
    render(<Trend metric={metric({ change_percent: null })} start="2026-11-01" label="x" />);
    expect(screen.getByText("No earlier period")).toBeTruthy();
  });
  it("draws a flat chart for all zeros without breaking", () => {
    const zeros = metric({ current: [0, 0], previous: [0, 0], total: 0, previous_total: 0 });
    const { container } = render(<Trend metric={zeros} start="2026-11-01" label="x" />);
    expect(container.querySelector(".chart-trend__line")?.getAttribute("d")).not.toContain("NaN");
  });
});

const trendData = (days = 7) => ({
  days,
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
});
const projectData = (over: object = {}) => ({
  refresh_seconds: 3,
  funnel: STEPS,
  distribution: ["A", "B", "C", "D", "E"].map((grade) => ({ grade, count: 1 })),
  ranking: [
    { rank: 1, candidate_id: "k1", file_name: "a.pdf", name: "", score: "90.0", grade: "A" },
  ],
  coverage: {
    candidates: 2,
    requirements: [
      {
        requirement_id: "r1",
        text: "Python",
        kind: "must",
        met: 1,
        partly_met: 0,
        missing: 1,
        not_judged: 0,
      },
    ],
  },
  trend: trendData(),
  ...over,
});
const fetchMock = vi.fn();
const answer = (body: unknown) =>
  fetchMock.mockImplementation(async () => ({ ok: true, status: 200, json: async () => body }));

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("project charts", () => {
  it("shows the five charts from the project's live numbers", async () => {
    answer(projectData());
    render(<ProjectCharts projectId="p1" />);
    for (const title of [
      "Funnel",
      "Score distribution",
      "Ranking",
      "Requirement coverage",
      "Trend",
    ]) {
      expect(await screen.findByRole("heading", { name: title })).toBeTruthy();
    }
    expect(fetchMock.mock.calls[0][0]).toBe("/api/company/projects/p1/charts/");
  });

  it("says so for a project with no scored candidates or requirements", async () => {
    answer(projectData({ ranking: [], coverage: { candidates: 0, requirements: [] } }));
    render(<ProjectCharts projectId="p1" />);
    expect(await screen.findByText("No scored candidates yet.")).toBeTruthy();
    expect(screen.getByText("No requirements yet.")).toBeTruthy();
  });

  it("asks again for the chosen period and counts the other thing", async () => {
    answer(projectData());
    render(<ProjectCharts projectId="p1" />);
    await screen.findByRole("heading", { name: "Trend" });
    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("Count"), "scored");
    expect(screen.getByText("Previous period 0")).toBeTruthy();
    await user.selectOptions(screen.getByLabelText("Period"), "30");
    await vi.waitFor(() =>
      expect(fetchMock.mock.calls.at(-1)?.[0]).toBe("/api/company/projects/p1/charts/?days=30"),
    );
  });

  it("follows the data as it changes", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    answer(projectData());
    render(<ProjectCharts projectId="p1" />);
    await screen.findByRole("heading", { name: "Funnel" });
    answer(projectData({ funnel: STEPS.map((item) => ({ ...item, count: item.count + 100 })) }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3100);
    });
    expect(await screen.findByText("110")).toBeTruthy();
  });

  it("shows the server's message when the numbers cannot be read", async () => {
    fetchMock.mockImplementation(async () => ({
      ok: false,
      status: 404,
      json: async () => ({ error: { code: "not_found", message: "Not found." } }),
    }));
    render(<ProjectCharts projectId="p1" />);
    expect((await screen.findByRole("alert")).textContent).toBe("Not found.");
  });
});

describe("company charts", () => {
  it("shows the funnel, the distribution and the trend of all projects", async () => {
    answer({
      refresh_seconds: 3,
      funnel: STEPS,
      distribution: projectData().distribution,
      trend: trendData(),
    });
    render(<CompanyCharts />);
    for (const title of ["Funnel", "Score distribution", "Trend"]) {
      expect(await screen.findByRole("heading", { name: title })).toBeTruthy();
    }
    expect(screen.queryByRole("heading", { name: "Ranking" })).toBeNull();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/company/charts/");
  });
});
