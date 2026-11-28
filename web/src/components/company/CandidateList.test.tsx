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
  top: false,
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
      "JEjane.pdfJ. E.",
      "82.5Grade B ",
      "71",
      "Strong match Borderline",
      " New",
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

  it("hides the pager when everything fits on one page", async () => {
    serve(page([row()], { page: 1, pages: 1, count: 1 }));
    render(<CandidateList projectId="p1" />);
    await screen.findByRole("region", { name: "Candidates" });
    expect(screen.queryByRole("button", { name: "Next page" })).toBeNull();
    expect(screen.queryByText(/Page 1 of 1/)).toBeNull();
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

describe("changing the stage of several candidates", () => {
  const two = () =>
    page([row(), row({ id: "c2", candidate_id: "k2", file_name: "omar.pdf", rank: 2 })]);
  const posts = () => fetchMock.mock.calls.filter((call) => call[1]?.method === "POST");

  async function open() {
    serve(two());
    render(<CandidateList projectId="p1" />);
    await screen.findByRole("region", { name: "Candidates" });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Select" }));
    return user;
  }

  it("shows each stage by its name", async () => {
    serve(page([row({ stage: "interviewed" })]));
    render(<CandidateList projectId="p1" />);
    const table = await screen.findByRole("region", { name: "Candidates" });
    expect(within(table).getByText("Interviewed")).toBeTruthy();
  });

  it("shows no checkboxes until Select is pressed, and no actions until someone is chosen", async () => {
    serve(two());
    render(<CandidateList projectId="p1" />);
    await screen.findByRole("region", { name: "Candidates" });
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.queryByRole("button", { name: "Change stage" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Select" }));
    expect(screen.getAllByRole("checkbox").length).toBeGreaterThan(0);
    expect(screen.getByText("0 selected")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Change stage" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Download selected" })).toBeNull();
  });

  it("Cancel selection hides the checkboxes and forgets the choice", async () => {
    const user = await open();
    await user.click(screen.getByRole("checkbox", { name: "Select jane.pdf" }));
    await user.click(screen.getByRole("button", { name: "Cancel selection" }));
    expect(screen.queryByRole("checkbox")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Select" }));
    expect(
      (screen.getByRole("checkbox", { name: "Select jane.pdf" }) as HTMLInputElement).checked,
    ).toBe(false);
  });

  it("asks before moving the selected candidates, then moves them", async () => {
    const user = await open();
    await user.click(screen.getByRole("checkbox", { name: "Select jane.pdf" }));
    await user.click(screen.getByRole("checkbox", { name: "Select omar.pdf" }));
    await user.selectOptions(screen.getByLabelText("Move selected to"), "interviewed");
    await user.click(screen.getByRole("button", { name: "Change stage" }));
    const dialog = await screen.findByRole("dialog", { name: "Change stage" });
    expect(dialog.textContent).toContain("Move 2 candidates to Interviewed?");
    expect(posts()).toHaveLength(0);
    await user.click(within(dialog).getByRole("button", { name: "Change stage" }));
    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(posts()[0][0]).toBe(`${BASE}stage/`);
    expect(JSON.parse(posts()[0][1].body)).toEqual({
      candidate_ids: ["k1", "k2"],
      stage: "interviewed",
    });
  });

  it("cancelling changes nothing", async () => {
    const user = await open();
    await user.click(screen.getByRole("checkbox", { name: "Select jane.pdf" }));
    await user.click(screen.getByRole("button", { name: "Change stage" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Cancel" }),
    );
    expect(posts()).toHaveLength(0);
  });

  it("select all picks the page, and a second click clears it", async () => {
    const user = await open();
    const all = screen.getByRole("checkbox", { name: "Select all on this page" });
    await user.click(all);
    expect(
      (screen.getByRole("checkbox", { name: "Select omar.pdf" }) as HTMLInputElement).checked,
    ).toBe(true);
    await user.click(all);
    expect(
      (screen.getByRole("checkbox", { name: "Select omar.pdf" }) as HTMLInputElement).checked,
    ).toBe(false);
  });

  it("the selection is cleared and the list looked at again after the change", async () => {
    const user = await open();
    await user.click(screen.getByRole("checkbox", { name: "Select jane.pdf" }));
    await user.click(screen.getByRole("button", { name: "Change stage" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Change stage" }),
    );
    await waitFor(() => expect(screen.queryByRole("checkbox")).toBeNull());
    await user.click(screen.getByRole("button", { name: "Select" }));
    expect(
      (screen.getByRole("checkbox", { name: "Select jane.pdf" }) as HTMLInputElement).checked,
    ).toBe(false);
    expect(paths().filter((path) => path.includes("sort=")).length).toBeGreaterThan(1);
  });

  it("a CV with no candidate yet cannot be selected", async () => {
    serve(page([row({ id: "c3", candidate_id: null, status: "waiting", score: null })]));
    render(<CandidateList projectId="p1" />);
    await screen.findByRole("region", { name: "Candidates" });
    expect(screen.queryByRole("checkbox", { name: "Select jane.pdf" })).toBeNull();
  });

  it("shows the server's message when the change fails", async () => {
    const user = await open();
    await user.click(screen.getByRole("checkbox", { name: "Select jane.pdf" }));
    fetchMock.mockImplementation(async (_path: string, init?: { method?: string }) =>
      init?.method === "POST"
        ? {
            ok: false,
            status: 404,
            json: async () => ({ error: { code: "not_found", message: "Not found." } }),
          }
        : { ok: true, status: 200, json: async () => two() },
    );
    await user.click(screen.getByRole("button", { name: "Change stage" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Change stage" }),
    );
    expect((await screen.findByRole("alert")).textContent).toBe("Not found.");
  });
});

describe("choosing candidates to compare", () => {
  const rows = [1, 2, 3, 4, 5].map((n) =>
    row({ id: `c${n}`, candidate_id: `k${n}`, file_name: `cv${n}.pdf` }),
  );
  async function choose(count: number, onCompare = vi.fn()) {
    serve(page(rows, { compare_limits: { min: 2, max: 4 } }));
    render(<CandidateList projectId="p1" onCompare={onCompare} />);
    await screen.findByRole("region", { name: "Candidates" });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Select" }));
    for (let n = 1; n <= count; n += 1) {
      await user.click(screen.getByRole("checkbox", { name: `Select cv${n}.pdf` }));
    }
    return { user, onCompare };
  }
  const compareButton = () => screen.getByRole("button", { name: "Compare" });
  const noCompareButton = () =>
    expect(screen.queryByRole("button", { name: "Compare" })).toBeNull();

  it("needs at least two", async () => {
    await choose(1);
    noCompareButton();
  });

  it("hands over two to four chosen candidates", async () => {
    const { user, onCompare } = await choose(4);
    await user.click(compareButton());
    expect(onCompare).toHaveBeenCalledWith(["k1", "k2", "k3", "k4"]);
  });

  it("says so clearly when more than four are chosen", async () => {
    await choose(5);
    noCompareButton();
    expect(screen.getByRole("status").textContent).toBe(
      "You can compare up to 4 candidates at a time. Choose fewer.",
    );
  });
});

describe("downloading the selected CVs", () => {
  const rows = [1, 2].map((n) =>
    row({ id: `c${n}`, candidate_id: `k${n}`, file_name: `cv${n}.pdf` }),
  );

  it("needs someone to be selected", async () => {
    serve(page(rows));
    render(<CandidateList projectId="p1" />);
    await screen.findByRole("region", { name: "Candidates" });
    await userEvent.click(screen.getByRole("button", { name: "Select" }));
    expect(screen.queryByRole("button", { name: "Download selected" })).toBeNull();
  });

  it("hands over the selected candidates", async () => {
    serve(page(rows));
    const onDownload = vi.fn();
    render(<CandidateList projectId="p1" onDownload={onDownload} />);
    await screen.findByRole("region", { name: "Candidates" });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Select" }));
    await user.click(screen.getByRole("checkbox", { name: "Select cv2.pdf" }));
    await user.click(screen.getByRole("button", { name: "Download selected" }));
    expect(onDownload).toHaveBeenCalledWith(["k2"]);
  });
});

describe("the top candidates", () => {
  it("tags the rows in the top", async () => {
    serve(
      page([row({ top: true }), row({ id: "c2", candidate_id: "k2", file_name: "omar.pdf" })], {
        top: { n: 1, included: 1, tied: false },
      }),
    );
    render(<CandidateList projectId="p1" />);
    const table = await screen.findByRole("region", { name: "Candidates" });
    expect(within(table).getAllByText("Top")).toHaveLength(1);
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("explains a tie at the cut-off", async () => {
    serve(page([row({ top: true })], { top: { n: 2, included: 4, tied: true } }));
    render(<CandidateList projectId="p1" />);
    expect((await screen.findByRole("status")).textContent).toBe(
      "The top 2 shows 4 candidates because of a tie at the cut-off score.",
    );
  });
});

describe("live updates of the list", () => {
  afterEach(() => vi.useRealTimers());

  it("keeps its rows while offline and catches up when the connection is back", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let state: "good" | "lost" | "back" = "good";
    fetchMock.mockImplementation(async () => {
      if (state === "lost") throw new TypeError("network");
      const rows =
        state === "back"
          ? [row(), row({ id: "c2", candidate_id: "k2", file_name: "new.pdf" })]
          : [row()];
      return { ok: true, status: 200, json: async () => page(rows) };
    });
    render(<CandidateList projectId="p1" />);
    await screen.findByText("jane.pdf");
    state = "lost";
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3100);
    });
    expect(screen.getByText("jane.pdf")).toBeTruthy();
    state = "back";
    await act(async () => {
      window.dispatchEvent(new Event("online"));
      await vi.advanceTimersByTimeAsync(100);
    });
    expect(await screen.findByText("new.pdf")).toBeTruthy();
  });
});
