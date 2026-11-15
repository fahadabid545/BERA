import { act, cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CandidateComparison } from "./CandidateComparison";

const fetchMock = vi.fn();
let search = "";
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(search),
}));

const REQUIREMENTS = [
  { id: "r1", text: "Python", kind: "must", weight: 5 },
  { id: "r2", text: "Docker", kind: "nice", weight: 2 },
];
const side = {
  requirements: REQUIREMENTS,
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
      results: [
        { verdict: "met", outdated: false, evidence: "Wrote Python daily" },
        { verdict: null, outdated: true, evidence: "" },
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
      results: [
        { verdict: "missing", outdated: false, evidence: "" },
        { verdict: "partly_met", outdated: true, evidence: "Used Docker once" },
      ],
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

function serve(body: unknown, ok = true) {
  fetchMock.mockImplementation(async () => ({
    ok,
    status: ok ? 200 : 400,
    json: async () => body,
  }));
}
const paths = () => fetchMock.mock.calls.map((call) => call[0] as string);

beforeEach(() => {
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
  it("asks for the chosen candidates", async () => {
    search = "ids=k1,k2";
    serve(side);
    render(<CandidateComparison projectId="p1" />);
    await screen.findByRole("region", { name: "Side by side" });
    expect(paths()).toEqual(["/api/company/projects/p1/compare/?ids=k1,k2"]);
  });

  it("shows scores and each requirement's result with its evidence", async () => {
    search = "ids=k1,k2";
    serve(side);
    render(<CandidateComparison projectId="p1" />);
    const table = await screen.findByRole("region", { name: "Side by side" });
    expect(within(table).getByRole("link", { name: "jane.pdf" }).getAttribute("href")).toBe(
      "/company/projects/p1/candidates/k1",
    );
    expect(within(table).getByText("90.0 (A)")).toBeTruthy();
    expect(within(table).getByText("Interview")).toBeTruthy();
    expect(within(table).getByText("Strong match")).toBeTruthy();
    expect(within(table).getByText("“Wrote Python daily”")).toBeTruthy();
    expect(within(table).getByText("Missing")).toBeTruthy();
    expect(within(table).getByText("“Used Docker once”")).toBeTruthy();
    expect(within(table).getByText("Not judged")).toBeTruthy();
    expect(within(table).getAllByText("Outdated")).toHaveLength(2);
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

describe("matrix", () => {
  it("asks for the matrix with the filters of the address and ignores others", async () => {
    search = "score_min=60&grade=A,B&unknown=1";
    serve(matrix([matrixRow("k1")]));
    render(<CandidateComparison projectId="p1" />);
    await screen.findByRole("region", { name: "Candidates against requirements" });
    expect(paths()[0]).toBe("/api/company/projects/p1/matrix/?page=1&score_min=60&grade=A%2CB");
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
    expect((await screen.findByRole("status")).textContent).toBe("No candidates to compare.");
  });

  it("pages through the candidates", async () => {
    serve({ ...matrix([matrixRow("k1")]), pages: 2, count: 60 });
    render(<CandidateComparison projectId="p1" />);
    await screen.findByText("Page 1 of 2, 60 candidates");
    expect(
      (screen.getByRole("button", { name: "Previous page" }) as HTMLButtonElement).disabled,
    ).toBe(true);
    const { default: userEvent } = await import("@testing-library/user-event");
    await userEvent.setup().click(screen.getByRole("button", { name: "Next page" }));
    await screen.findByText("Page 1 of 2, 60 candidates");
    expect(paths().some((path) => path.includes("page=2"))).toBe(true);
  });
});
