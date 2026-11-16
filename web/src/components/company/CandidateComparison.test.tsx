import { act, cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CandidateComparison } from "./CandidateComparison";

const fetchMock = vi.fn();
const replace = vi.fn();
let search = "";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => "/company/projects/p1/compare",
  useSearchParams: () => new URLSearchParams(search),
}));

const REQUIREMENTS = [
  { id: "r1", text: "Python", kind: "must", weight: 5 },
  { id: "r2", text: "Docker", kind: "nice", weight: 2 },
];
const counts = (over: object = {}) => ({
  met: 0,
  partly_met: 0,
  missing: 0,
  not_judged: 0,
  ...over,
});
const side = {
  requirements: REQUIREMENTS,
  points: { met: 100, partly_met: 50, missing: 0 },
  insights: [
    { kind: "lead", candidate: "k1", over: "k2", points: 35 },
    { kind: "must_gap", candidate: "k2", requirements: ["r1"] },
    { kind: "best_on", candidate: "k1", requirements: ["r1"] },
  ],
  candidates: [
    {
      id: "k1",
      file_name: "jane.pdf",
      name: "J. E.",
      stage: "interview",
      score: "90.0",
      grade: "A",
      outdated: false,
      label: "strong_match",
      borderline: false,
      ats_score: 80,
      must_score: "100.0",
      nice_score: null,
      capped: false,
      summary: { must: counts({ met: 1 }), nice: counts({ not_judged: 1 }) },
      results: [
        { verdict: "met", outdated: false, evidence: "Wrote Python daily", confidence: "high" },
        { verdict: null, outdated: true, evidence: "", confidence: null },
      ],
    },
    {
      id: "k2",
      file_name: "omar.pdf",
      name: "",
      stage: "new",
      score: "55.0",
      grade: "D",
      outdated: true,
      label: "possible",
      borderline: true,
      ats_score: null,
      must_score: "0.0",
      nice_score: "50.0",
      capped: true,
      summary: { must: counts({ missing: 1 }), nice: counts({ partly_met: 1 }) },
      results: [
        { verdict: "missing", outdated: false, evidence: "", confidence: "high" },
        { verdict: "partly_met", outdated: true, evidence: "Used Docker once", confidence: "low" },
      ],
    },
  ],
};
const frontier = {
  axes: "ai_ats",
  choices: ["ai_ats", "must_nice"],
  total: 3,
  left_out: 1,
  frontier: ["k1", "k3"],
  compare_limits: { min: 2, max: 4 },
  points: [
    {
      id: "k1",
      name: "J. E.",
      file_name: "jane.pdf",
      grade: "A",
      stage: "new",
      x: 80,
      y: 90,
      beaten_by: null,
    },
    {
      id: "k2",
      name: "",
      file_name: "omar.pdf",
      grade: "D",
      stage: "new",
      x: 60,
      y: 55,
      beaten_by: "k1",
    },
    {
      id: "k3",
      name: "T. W.",
      file_name: "tom.pdf",
      grade: "B",
      stage: "new",
      x: 95,
      y: 70,
      beaten_by: null,
    },
  ],
};
const matrix = (rows: object[] = []) => ({
  page: 1,
  pages: 1,
  count: rows.length,
  refresh_seconds: 3,
  requirements: REQUIREMENTS,
  rows,
});
const matrixRow = (id: string, over: object = {}) => ({
  candidate_id: id,
  file_name: `${id}.pdf`,
  name: "",
  rank: 1,
  score: "80.0",
  grade: "B",
  cells: [
    { verdict: "met", outdated: false },
    { verdict: null, outdated: true },
  ],
  ...over,
});

function serve(body: unknown, ok = true, frontierBody: unknown = frontier) {
  fetchMock.mockImplementation(async (url: string) => {
    const answer = url.includes("/frontier/") ? frontierBody : body;
    return {
      ok: ok || url.includes("/frontier/"),
      status: ok ? 200 : 400,
      json: async () => answer,
    };
  });
}
const paths = () => fetchMock.mock.calls.map((call) => call[0] as string);

beforeEach(() => {
  replace.mockReset();
  search = "";
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("side by side", () => {
  it("asks for the chosen candidates, and for the frontier only when its tab is open", async () => {
    search = "ids=k1,k2";
    serve(side);
    render(<CandidateComparison projectId="p1" />);
    await screen.findByRole("tablist", { name: "Comparison" });
    expect(paths()).toEqual(["/api/company/projects/p1/compare/?ids=k1,k2"]);
    cleanup();
    search = "ids=k1,k2&view=frontier";
    render(<CandidateComparison projectId="p1" />);
    await vi.waitFor(() => expect(paths()).toContain("/api/company/projects/p1/frontier/"));
  });

  it("splits the page into four tabs, opens the one in the address and remembers a choice", async () => {
    search = "ids=k1,k2";
    serve(side);
    render(<CandidateComparison projectId="p1" />);
    const tabs = await screen.findAllByRole("tab");
    expect(tabs.map((tab) => tab.textContent)).toEqual([
      "Overview",
      "Requirements",
      "Frontier",
      "Evidence",
    ]);
    expect(tabs[0].getAttribute("aria-selected")).toBe("true");
    expect(screen.queryByRole("region", { name: "Side by side" })).toBeNull();
    await userEvent.setup().click(tabs[3]);
    expect(replace).toHaveBeenCalledWith("/company/projects/p1/compare?ids=k1%2Ck2&view=evidence", {
      scroll: false,
    });
  });

  it("says so on the Requirements tab when the project has none", async () => {
    search = "ids=k1,k2&view=requirements";
    serve({
      ...side,
      requirements: [],
      insights: [],
      candidates: side.candidates.map((c) => ({ ...c, results: [] })),
    });
    render(<CandidateComparison projectId="p1" />);
    expect(await screen.findByText("No requirements yet.")).toBeTruthy();
  });

  it("gives each candidate a card with scores, status and the highest score marked", async () => {
    search = "ids=k1,k2";
    serve(side);
    const { container } = render(<CandidateComparison projectId="p1" />);
    await screen.findByRole("tablist", { name: "Comparison" });
    const cards = [...container.querySelectorAll(".compare-card")];
    expect(cards).toHaveLength(2);
    expect(
      within(cards[0] as HTMLElement)
        .getByRole("link", { name: "J. E." })
        .getAttribute("href"),
    ).toBe("/company/projects/p1/candidates/k1");
    expect(within(cards[0] as HTMLElement).getByText("90.0")).toBeTruthy();
    expect(within(cards[0] as HTMLElement).getByText("Highest score")).toBeTruthy();
    expect(within(cards[1] as HTMLElement).queryByText("Highest score")).toBeNull();
    expect(within(cards[1] as HTMLElement).getByText("Borderline")).toBeTruthy();
    expect(within(cards[1] as HTMLElement).getByText("ATS none")).toBeTruthy();
  });

  it("words what stands out in a sentence each", async () => {
    search = "ids=k1,k2";
    serve(side);
    render(<CandidateComparison projectId="p1" />);
    expect(await screen.findByText("J. E. is ahead of omar.pdf by 35 points")).toBeTruthy();
    expect(screen.getByText("omar.pdf is missing a must-have: Python")).toBeTruthy();
    expect(screen.getByText("J. E. is clearly best on Python")).toBeTruthy();
  });

  it("words a tie", async () => {
    search = "ids=k1,k2";
    serve({ ...side, insights: [{ kind: "tie", candidates: ["k1", "k2"] }] });
    render(<CandidateComparison projectId="p1" />);
    expect(await screen.findByText("J. E. and omar.pdf have the same AI score")).toBeTruthy();
  });

  it("draws a bar for every candidate and requirement, written with the verdict", async () => {
    search = "ids=k1,k2&view=requirements";
    serve(side);
    const { container } = render(<CandidateComparison projectId="p1" />);
    await screen.findByRole("heading", { name: "Requirement by requirement" });
    const bars = [...container.querySelectorAll<HTMLElement>(".req-bar__fill")];
    expect(bars.map((bar) => bar.style.width)).toEqual(["100%", "0%", "0%", "50%"]);
    expect(container.querySelectorAll(".req-bar__fill--partly")).toHaveLength(1);
    expect(container.querySelectorAll(".req-bar__fill--none")).toHaveLength(1);
  });

  it("opens the words behind a result from a bar", async () => {
    search = "ids=k1,k2&view=requirements";
    serve(side);
    const user = userEvent.setup();
    const { container } = render(<CandidateComparison projectId="p1" />);
    await screen.findByRole("heading", { name: "Requirement by requirement" });
    await user.click(container.querySelectorAll<HTMLElement>(".req-bar")[0]);
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("“Wrote Python daily”")).toBeTruthy();
    expect(within(dialog).getByText("high confidence")).toBeTruthy();
    expect(within(dialog).getByRole("link", { name: "Open candidate" }).getAttribute("href")).toBe(
      "/company/projects/p1/candidates/k1",
    );
  });

  it("opens the words behind a result from the table too", async () => {
    search = "ids=k1,k2&view=evidence";
    serve(side);
    render(<CandidateComparison projectId="p1" />);
    await userEvent.setup().click(await screen.findByRole("button", { name: "omar.pdf: Docker" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("“Used Docker once”")).toBeTruthy();
    expect(within(dialog).getByText("low confidence")).toBeTruthy();
  });

  it("says so in the popup when no words are quoted", async () => {
    search = "ids=k1,k2&view=evidence";
    serve(side);
    render(<CandidateComparison projectId="p1" />);
    await userEvent.setup().click(await screen.findByRole("button", { name: "omar.pdf: Python" }));
    expect(
      await screen.findByText("No words from the CV are quoted for this result."),
    ).toBeTruthy();
  });

  it("shows scores and each requirement's result with its evidence in the table", async () => {
    search = "ids=k1,k2&view=evidence";
    serve(side);
    render(<CandidateComparison projectId="p1" />);
    const table = await screen.findByRole("region", { name: "Side by side" });
    expect(within(table).getByRole("link", { name: "jane.pdf" }).getAttribute("href")).toBe(
      "/company/projects/p1/candidates/k1",
    );
    expect(within(table).getByText("90.0 (A)")).toBeTruthy();
    expect(within(table).getByText("Strong match")).toBeTruthy();
    expect(within(table).getByText("“Wrote Python daily”")).toBeTruthy();
    expect(within(table).getByText("Missing")).toBeTruthy();
    expect(within(table).getByText("“Used Docker once”")).toBeTruthy();
    expect(within(table).getByText("Not judged")).toBeTruthy();
    expect(within(table).getAllByText("Outdated")).toHaveLength(2);
  });

  it("explains a word on hover", async () => {
    search = "ids=k1,k2&view=evidence";
    serve(side);
    const user = userEvent.setup();
    render(<CandidateComparison projectId="p1" />);
    const table = await screen.findByRole("region", { name: "Side by side" });
    await user.hover(within(table).getByText("ATS score"));
    expect((await screen.findByRole("tooltip")).textContent).toContain("applicant tracking system");
  });

  it("shows the server's message when too many were chosen", async () => {
    search = "ids=k1,k2,k3,k4,k5";
    serve(
      {
        error: {
          code: "too_many_to_compare",
          message: "You can compare up to 4 candidates at a time. Choose fewer.",
        },
      },
      false,
    );
    render(<CandidateComparison projectId="p1" />);
    expect((await screen.findByRole("alert")).textContent).toContain("up to 4");
  });
});

describe("pareto frontier", () => {
  beforeEach(() => {
    search = "ids=k1,k2&view=frontier";
  });
  it("places every candidate as a link, marks the frontier and the chosen ones", async () => {
    serve(side);
    const { container } = render(<CandidateComparison projectId="p1" />);
    await screen.findByRole("heading", { name: "Pareto frontier" });
    await vi.waitFor(() => expect(container.querySelectorAll(".pareto__point")).toHaveLength(3));
    const points = [...container.querySelectorAll<HTMLElement>(".pareto__point")];
    expect(points[0].getAttribute("href")).toBe("/company/projects/p1/candidates/k1");
    expect(points[0].className).toContain("pareto__point--frontier");
    expect(points[0].className).toContain("pareto__point--green");
    expect(points[1].className).not.toContain("pareto__point--frontier");
    expect(points[1].className).toContain("pareto__point--violet");
    expect(points[2].className).toContain("pareto__point--frontier");
    expect(points[2].className).not.toMatch(/pareto__point--(green|violet|blue|amber)/);
    expect(screen.getByText("3 candidates placed, 1 left out without both scores")).toBeTruthy();
    expect(screen.getByText("In this comparison")).toBeTruthy();
  });

  it("says on hover who beats a candidate on both scores", async () => {
    serve(side);
    const user = userEvent.setup();
    render(<CandidateComparison projectId="p1" />);
    const dot = await screen.findByRole("link", { name: /^omar.pdf, AI score 55/ });
    await user.hover(dot);
    const tip = await screen.findByRole("tooltip");
    expect(tip.textContent).toContain("Beaten on both scores by J. E.");
    expect(tip.textContent).toContain("ATS score 60");
  });

  it("compares the frontier and asks again for the other pair of scores", async () => {
    serve(side);
    const user = userEvent.setup();
    render(<CandidateComparison projectId="p1" />);
    expect(
      (await screen.findByRole("link", { name: "Compare the frontier" })).getAttribute("href"),
    ).toBe("/company/projects/p1/compare?ids=k1,k3");
    await user.selectOptions(screen.getByLabelText("Scores"), "must_nice");
    await vi.waitFor(() =>
      expect(paths().at(-1)).toBe("/api/company/projects/p1/frontier/?axes=must_nice"),
    );
  });

  it("says so when nobody can be placed, and shows the server's message on failure", async () => {
    serve(side, true, { ...frontier, points: [], frontier: [], total: 0, left_out: 0 });
    render(<CandidateComparison projectId="p1" />);
    expect(await screen.findByText("No candidates to place yet.")).toBeTruthy();
    cleanup();
    fetchMock.mockReset();
    fetchMock.mockImplementation(async (url: string) =>
      url.includes("/frontier/")
        ? {
            ok: false,
            status: 400,
            json: async () => ({ error: { code: "x", message: "Choose one." } }),
          }
        : { ok: true, status: 200, json: async () => side },
    );
    render(<CandidateComparison projectId="p1" />);
    expect((await screen.findByText("Choose one.")).textContent).toBe("Choose one.");
  });
});

describe("matrix", () => {
  it("asks for the matrix with the filters of the address and ignores others", async () => {
    search = "score_min=60&grade=A,B&unknown=1";
    serve(matrix([matrixRow("k1")]));
    render(<CandidateComparison projectId="p1" />);
    await screen.findByRole("region", { name: "Candidates against requirements" });
    expect(paths()[0]).toBe("/api/company/projects/p1/matrix/?page=1&score_min=60&grade=A%2CB");
  });

  it("has a Matrix tab and a Frontier tab, and shows the frontier on the second", async () => {
    search = "view=frontier";
    serve(matrix([matrixRow("k1")]));
    render(<CandidateComparison projectId="p1" />);
    expect(await screen.findByRole("heading", { name: "Pareto frontier" })).toBeTruthy();
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual([
      "Matrix",
      "Frontier",
    ]);
  });

  it("shows every candidate against every requirement", async () => {
    serve(
      matrix([
        matrixRow("k1"),
        matrixRow("k2", {
          rank: 2,
          cells: [
            { verdict: "missing", outdated: false },
            { verdict: "partly_met", outdated: false },
          ],
        }),
      ]),
    );
    render(<CandidateComparison projectId="p1" />);
    const table = await screen.findByRole("region", { name: "Candidates against requirements" });
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((cell) => cell.textContent),
    ).toEqual(["Rank", "Candidate", "AI score", "Python", "Docker"]);
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("Met")).toBeTruthy();
    expect(within(rows[0]).getByText("Not judged")).toBeTruthy();
    expect(within(rows[1]).getByText("Missing")).toBeTruthy();
    expect(within(rows[1]).getByText("Partly met")).toBeTruthy();
  });

  it("gives the kind and weight of a requirement on hover", async () => {
    serve(matrix([matrixRow("k1")]));
    const user = userEvent.setup();
    render(<CandidateComparison projectId="p1" />);
    const table = await screen.findByRole("region", { name: "Candidates against requirements" });
    await user.hover(within(table).getByText("Python"));
    const tip = await screen.findByRole("tooltip");
    expect(tip.textContent).toContain("Must-have");
    expect(tip.textContent).toContain("Weight 5");
  });

  it("new candidates join without a reload", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    serve(matrix([matrixRow("k1")]));
    render(<CandidateComparison projectId="p1" />);
    await screen.findByText("k1.pdf");
    serve(matrix([matrixRow("k1"), matrixRow("k2", { rank: 2 })]));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3100);
    });
    expect(await screen.findByText("k2.pdf")).toBeTruthy();
  });

  it("says so when there is nobody to compare", async () => {
    serve(matrix([]));
    render(<CandidateComparison projectId="p1" />);
    expect(await screen.findByText("No candidates to compare.")).toBeTruthy();
  });

  it("pages through the candidates", async () => {
    serve({ ...matrix([matrixRow("k1")]), pages: 2, count: 60 });
    render(<CandidateComparison projectId="p1" />);
    await screen.findByText("Page 1 of 2, 60 candidates");
    expect(
      (screen.getByRole("button", { name: "Previous page" }) as HTMLButtonElement).disabled,
    ).toBe(true);
    await userEvent.setup().click(screen.getByRole("button", { name: "Next page" }));
    await screen.findByText("Page 1 of 2, 60 candidates");
    expect(paths().some((path) => path.includes("page=2"))).toBe(true);
  });
});
