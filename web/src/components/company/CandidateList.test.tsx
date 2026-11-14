import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CandidateList } from "./CandidateList";

const fetchMock = vi.fn();
const BASE = "/api/company/projects/p1/candidates/";

const row = (over: object = {}) => ({
  id: "c1",
  candidate_id: "k1",
  file_name: "jane.pdf",
  name: "J. E.",
  status: "done",
  reason: "",
  rank: 1,
  score: "82.5",
  grade: "B",
  outdated: false,
  ats_score: 71,
  label: "strong_match",
  borderline: false,
  stage: "new",
  added_at: "2026-11-14T10:00:00Z",
  ...over,
});
const page = (rows: object[], over: object = {}) => ({
  page: 1,
  pages: 1,
  count: rows.length,
  refresh_seconds: 3,
  rows,
  ...over,
});

function serve(body: unknown | ((path: string) => unknown)) {
  fetchMock.mockImplementation(async (path: string) => ({
    ok: true,
    status: 200,
    json: async () => (typeof body === "function" ? body(path) : body),
  }));
}
const paths = () => fetchMock.mock.calls.map((call) => call[0] as string);

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("ranked candidate list", () => {
  it("asks for AI score high to low, first page, by default", async () => {
    serve(page([row()]));
    render(<CandidateList projectId="p1" />);
    await screen.findByRole("region", { name: "Candidates" });
    expect(paths()[0]).toBe(`${BASE}?sort=score&direction=desc&page=1`);
  });

  it("shows each candidate's columns", async () => {
    serve(page([row({ borderline: true })]));
    render(<CandidateList projectId="p1" />);
    const table = await screen.findByRole("region", { name: "Candidates" });
    const cells = within(table)
      .getAllByRole("cell")
      .map((cell) => cell.textContent);
    expect(cells).toEqual([
      "1",
      "jane.pdfJ. E.",
      "82.5 (B) ",
      "71",
      "Strong match Borderline",
      "New",
      "2026-11-14",
    ]);
    expect(within(table).getByRole("link", { name: "jane.pdf" }).getAttribute("href")).toBe(
      "/company/projects/p1/candidates/k1",
    );
  });

  it("has a heading for every column", async () => {
    serve(page([row()]));
    render(<CandidateList projectId="p1" />);
    const table = await screen.findByRole("region", { name: "Candidates" });
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((header) => header.textContent),
    ).toEqual([
      "Rank",
      "Candidate",
      "AI score",
      "ATS score",
      "Recommendation",
      "Stage",
      "Date added",
    ]);
  });

  it("an item still processing shows its status instead of a score", async () => {
    serve(
      page([
        row(),
        row({
          id: "c2",
          candidate_id: null,
          file_name: "new.pdf",
          name: "",
          status: "reading",
          rank: null,
          score: null,
          grade: null,
          ats_score: null,
          label: null,
          stage: null,
        }),
      ]),
    );
    render(<CandidateList projectId="p1" />);
    const table = await screen.findByRole("region", { name: "Candidates" });
    const last = within(table).getAllByRole("row")[2];
    expect(within(last).getByText("Reading")).toBeTruthy();
    expect(within(last).queryByRole("link")).toBeNull();
    expect(last.textContent).not.toContain("(");
  });

  it("a failed item shows why", async () => {
    serve(
      page([
        row({
          status: "failed",
          score: null,
          rank: null,
          reason: "We could not read this file.",
        }),
      ]),
    );
    render(<CandidateList projectId="p1" />);
    expect(await screen.findByText("We could not read this file.")).toBeTruthy();
    expect(screen.getByText("Failed")).toBeTruthy();
  });

  it("an outdated score says so", async () => {
    serve(page([row({ outdated: true })]));
    render(<CandidateList projectId="p1" />);
    expect(await screen.findByText("Outdated")).toBeTruthy();
  });

  it("shows nothing when the project has no candidates", async () => {
    serve(page([]));
    const { container } = render(<CandidateList projectId="p1" />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(container.innerHTML).toBe("");
  });

  it("shows the server's message when the list cannot be read", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ error: { code: "not_found", message: "Not found." } }),
    });
    render(<CandidateList projectId="p1" />);
    expect((await screen.findByRole("alert")).textContent).toBe("Not found.");
  });
});

describe("sorting", () => {
  it("pressing a heading sorts by it, with a sensible first direction", async () => {
    serve(page([row()]));
    render(<CandidateList projectId="p1" />);
    await screen.findByRole("region", { name: "Candidates" });
    await userEvent.click(screen.getByRole("button", { name: "Candidate" }));
    await waitFor(() => expect(paths().at(-1)).toBe(`${BASE}?sort=candidate&direction=asc&page=1`));
    await userEvent.click(screen.getByRole("button", { name: "ATS score" }));
    await waitFor(() => expect(paths().at(-1)).toBe(`${BASE}?sort=ats&direction=desc&page=1`));
    await userEvent.click(screen.getByRole("button", { name: "Date added" }));
    await waitFor(() => expect(paths().at(-1)).toBe(`${BASE}?sort=added&direction=desc&page=1`));
  });

  it("pressing the same heading again flips the direction", async () => {
    serve(page([row()]));
    render(<CandidateList projectId="p1" />);
    await screen.findByRole("region", { name: "Candidates" });
    await userEvent.click(screen.getByRole("button", { name: "AI score" }));
    await waitFor(() => expect(paths().at(-1)).toBe(`${BASE}?sort=score&direction=asc&page=1`));
  });

  it("marks the sorted column for assistive technology", async () => {
    serve(page([row()]));
    render(<CandidateList projectId="p1" />);
    await screen.findByRole("region", { name: "Candidates" });
    const sorted = (name: string) =>
      screen.getByRole("columnheader", { name }).getAttribute("aria-sort");
    expect(sorted("AI score")).toBe("descending");
    expect(sorted("Rank")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Rank" }));
    await waitFor(() => expect(sorted("Rank")).toBe("ascending"));
    expect(sorted("AI score")).toBeNull();
  });
});

describe("paging", () => {
  it("shows where we are and moves between pages, starting again at page 1 after a sort", async () => {
    serve((path: string) =>
      page([row()], {
        page: Number(new URL(path, "http://x").searchParams.get("page")),
        pages: 3,
        count: 60,
      }),
    );
    render(<CandidateList projectId="p1" />);
    expect(await screen.findByText("Page 1 of 3, 60 candidates")).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: "Previous page" }) as HTMLButtonElement).disabled,
    ).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(await screen.findByText("Page 2 of 3, 60 candidates")).toBeTruthy();
    expect(paths().at(-1)).toContain("page=2");
    await userEvent.click(screen.getByRole("button", { name: "Candidate" }));
    expect(await screen.findByText("Page 1 of 3, 60 candidates")).toBeTruthy();
  });

  it("cannot go past the last page", async () => {
    serve(page([row()], { page: 1, pages: 1, count: 1 }));
    render(<CandidateList projectId="p1" />);
    await screen.findByText("Page 1 of 1, 1 candidates");
    expect((screen.getByRole("button", { name: "Next page" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
  });
});

describe("live arrival", () => {
  it("looks again by itself, keeping the sort and page, and shows a CV that finished", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let current = page([row({ file_name: "first.pdf" })]);
    serve(() => current);
    render(<CandidateList projectId="p1" />);
    await screen.findByText("first.pdf");
    current = page([
      row({ file_name: "newcomer.pdf", rank: 1, candidate_id: "k9", id: "c9" }),
      row({ file_name: "first.pdf", rank: 2 }),
    ]);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(await screen.findByText("newcomer.pdf")).toBeTruthy();
    const table = screen.getByRole("region", { name: "Candidates" });
    expect(within(table).getAllByRole("row")[1].textContent).toContain("newcomer.pdf");
    expect(paths().at(-1)).toBe(`${BASE}?sort=score&direction=desc&page=1`);
  });

  it("stops looking when the page is left", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    serve(page([row()]));
    const { unmount } = render(<CandidateList projectId="p1" />);
    await screen.findByRole("region", { name: "Candidates" });
    unmount();
    const calls = fetchMock.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(fetchMock.mock.calls.length).toBe(calls);
  });
});
