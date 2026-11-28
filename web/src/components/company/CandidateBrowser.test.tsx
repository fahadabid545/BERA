import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CandidateBrowser } from "./CandidateBrowser";

const fetchMock = vi.fn();
const replace = vi.fn();
const push = vi.fn();
let search = "";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push }),
  usePathname: () => "/company/projects/p1/candidates",
  useSearchParams: () => new URLSearchParams(search),
}));

const REQUIREMENTS = [
  { id: "r1", text: "Python", kind: "must" },
  { id: "r2", text: "Docker", kind: "nice" },
];
const body = (over: object = {}) => ({
  page: 1,
  pages: 1,
  count: 0,
  filtered: false,
  requirements: REQUIREMENTS,
  refresh_seconds: 3,
  rows: [],
  ...over,
});
const NO_REPORTS = { days: { choices: [1, 7, 30], default: 7 }, reports: [] };
const paths = () =>
  fetchMock.mock.calls
    .map((call) => call[0] as string)
    .filter((path) => !path.includes("/reports/"));
function serveList(listBody: object) {
  fetchMock.mockImplementation(async (path: string) => ({
    ok: true,
    status: 200,
    json: async () => (path.includes("/reports/") ? NO_REPORTS : listBody),
  }));
}

beforeEach(() => {
  search = "";
  replace.mockReset();
  push.mockReset();
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (path: string) => ({
    ok: true,
    status: 200,
    json: async () => (path.includes("/reports/") ? NO_REPORTS : body()),
  }));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function openFilters() {
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: /^Filters/ }));
  return { user, dialog: await screen.findByRole("dialog", { name: "Filters" }) };
}

describe("candidate filters", () => {
  it("asks the server for the filters found in the address", async () => {
    search = "score_min=60&grade=A,B&q=jane&unknown=1";
    render(<CandidateBrowser projectId="p1" />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(paths()[0]).toBe(
      "/api/company/projects/p1/candidates/?sort=score&direction=desc&page=1&score_min=60&grade=A%2CB&q=jane",
    );
  });

  it("shows how many filters are on the button", async () => {
    search = "score_min=60&q=jane";
    render(<CandidateBrowser projectId="p1" />);
    expect(screen.getByRole("button", { name: "Filters (2)" })).toBeTruthy();
  });

  it("applying puts the filters in the address and leaves empty ones out", async () => {
    render(<CandidateBrowser projectId="p1" />);
    const { user, dialog } = await openFilters();
    await user.type(within(dialog).getByLabelText("Search file name and summary"), "jane");
    await user.type(within(dialog).getByLabelText("AI score, from"), "60");
    await user.click(within(dialog).getByRole("checkbox", { name: "A" }));
    await user.click(within(dialog).getByRole("checkbox", { name: "B" }));
    await user.click(within(dialog).getByRole("button", { name: "Apply filters" }));
    expect(replace).toHaveBeenCalledWith(
      "/company/projects/p1/candidates?q=jane&score_min=60&grade=A%2CB",
      { scroll: false },
    );
  });

  it("offers the project's requirements, must-haves only for missing", async () => {
    render(<CandidateBrowser projectId="p1" />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const { user, dialog } = await openFilters();
    const missing = within(dialog).getByRole("group", { name: "Missing the must-have" });
    expect(within(missing).getAllByRole("checkbox")).toHaveLength(1);
    const has = within(dialog).getByRole("group", { name: "Meets the requirement" });
    await user.click(within(has).getByRole("checkbox", { name: "Docker" }));
    await user.click(within(missing).getByRole("checkbox", { name: "Python" }));
    await user.click(within(dialog).getByRole("checkbox", { name: "Likely duplicates only" }));
    await user.click(within(dialog).getByRole("button", { name: "Apply filters" }));
    expect(replace).toHaveBeenCalledWith(
      "/company/projects/p1/candidates?has=r2&missing=r1&duplicate=true",
      { scroll: false },
    );
  });

  it("the popup starts from the filters in the address", async () => {
    search = "score_min=60&grade=B&duplicate=true";
    render(<CandidateBrowser projectId="p1" />);
    const { dialog } = await openFilters();
    expect((within(dialog).getByLabelText("AI score, from") as HTMLInputElement).value).toBe("60");
    expect((within(dialog).getByRole("checkbox", { name: "B" }) as HTMLInputElement).checked).toBe(
      true,
    );
    expect(
      (within(dialog).getByRole("checkbox", { name: "Likely duplicates only" }) as HTMLInputElement)
        .checked,
    ).toBe(true);
  });

  it("cancelling changes nothing", async () => {
    render(<CandidateBrowser projectId="p1" />);
    const { user, dialog } = await openFilters();
    await user.type(within(dialog).getByLabelText("AI score, from"), "60");
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(replace).not.toHaveBeenCalled();
  });

  it("Clear all in the popup removes every filter", async () => {
    search = "score_min=60&q=jane";
    render(<CandidateBrowser projectId="p1" />);
    const { user, dialog } = await openFilters();
    await user.click(within(dialog).getByRole("button", { name: "Clear all" }));
    expect(replace).toHaveBeenCalledWith("/company/projects/p1/candidates", { scroll: false });
  });

  it("an empty result says so and offers Clear all", async () => {
    search = "score_min=99";
    serveList(body({ filtered: true }));
    render(<CandidateBrowser projectId="p1" />);
    expect(await screen.findByText("No candidates match these filters.")).toBeTruthy();
    await userEvent.setup().click(screen.getByRole("button", { name: "Clear all" }));
    expect(replace).toHaveBeenCalledWith("/company/projects/p1/candidates", { scroll: false });
  });

  it("a project with no CVs and no filters shows no message", async () => {
    render(<CandidateBrowser projectId="p1" />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(screen.queryByText("No candidates match these filters.")).toBeNull();
  });

  it("changing the filters starts again at the first page", async () => {
    const rows = [
      {
        id: "c1", candidate_id: "k1", file_name: "a.pdf", name: "", status: "done", reason: "",
        rank: 1, score: "80.0", grade: "B", outdated: false, ats_score: 1, label: "possible",
        borderline: false, stage: "new", added_at: "2026-11-14T10:00:00Z",
      },
    ]; // prettier-ignore
    serveList(body({ count: 40, pages: 2, rows }));
    const { rerender } = render(<CandidateBrowser projectId="p1" />);
    await userEvent.setup().click(await screen.findByRole("button", { name: "Next page" }));
    await waitFor(() => expect(paths().some((p) => p.includes("page=2"))).toBe(true));
    search = "grade=A";
    rerender(<CandidateBrowser projectId="p1" />);
    await waitFor(() => expect(paths().at(-1)).toContain("page=1&grade=A"));
  });

  it("lets the stage filter bring back rejected candidates", async () => {
    render(<CandidateBrowser projectId="p1" />);
    const { user, dialog } = await openFilters();
    await user.click(within(dialog).getByRole("checkbox", { name: "Rejected" }));
    await user.click(within(dialog).getByRole("button", { name: "Apply filters" }));
    expect(replace).toHaveBeenCalledWith("/company/projects/p1/candidates?stage=rejected", {
      scroll: false,
    });
  });
});

describe("comparison links", () => {
  it("has no separate Matrix link: the Compare tab shows it", () => {
    render(<CandidateBrowser projectId="p1" />);
    expect(screen.queryByRole("link", { name: "Matrix" })).toBeNull();
  });

  it("puts the filters on the left and the actions on the right of one toolbar", () => {
    const { container } = render(<CandidateBrowser projectId="p1" />);
    const toolbar = container.querySelector(".toolbar")!;
    const end = toolbar.querySelector(".toolbar__end")!;
    expect(toolbar.firstElementChild?.textContent).toBe("Filters");
    expect([...end.querySelectorAll("button, a")].map((item) => item.textContent)).toEqual([
      "Share report",
      "Shared links",
      "Download",
      "Upload CVs",
    ]);
  });

  it("puts Select in the toolbar only when there are candidates to select", async () => {
    const row = {
      id: "c1",
      candidate_id: "k1",
      file_name: "jane.pdf",
      name: "",
      status: "done",
      reason: "",
      rank: 1,
      score: "80.0",
      grade: "B",
      outdated: false,
      ats_score: 70,
      label: "possible",
      borderline: false,
      stage: "new",
      added_at: "2026-11-14T10:00:00Z",
    }; // fmt: skip
    fetchMock.mockImplementation(async (path: string) => ({
      ok: true,
      status: 200,
      json: async () => (path.includes("/reports/") ? NO_REPORTS : body({ count: 1, rows: [row] })),
    }));
    const { container } = render(<CandidateBrowser projectId="p1" />);
    const select = await screen.findByRole("button", { name: "Select" });
    expect(container.querySelector(".toolbar__end")?.contains(select)).toBe(true);
    await userEvent.click(select);
    expect(screen.queryByRole("button", { name: "Select" })).toBeNull();
    expect(screen.getByRole("button", { name: "Cancel selection" })).toBeTruthy();
  });

  it("shows no Select button for an empty project", async () => {
    render(<CandidateBrowser projectId="p1" />);
    await screen.findByRole("button", { name: "Filters" });
    expect(screen.queryByRole("button", { name: "Select" })).toBeNull();
  });

  it("Upload CVs goes to the upload area of the project overview", () => {
    render(<CandidateBrowser projectId="p1" />);
    expect(screen.getByRole("link", { name: "Upload CVs" }).getAttribute("href")).toBe(
      "/company/projects/p1#upload",
    );
  });

  it("opens the side by side page for the chosen candidates", async () => {
    const row = {
      id: "c1",
      candidate_id: "k1",
      file_name: "jane.pdf",
      name: "",
      status: "done",
      reason: "",
      rank: 1,
      score: "80.0",
      grade: "B",
      outdated: false,
      ats_score: 70,
      label: "possible",
      borderline: false,
      stage: "new",
      added_at: "2026-11-14T10:00:00Z",
    };
    const second = { ...row, id: "c2", candidate_id: "k2", file_name: "omar.pdf" };
    fetchMock.mockImplementation(async (path: string) => ({
      ok: true,
      status: 200,
      json: async () =>
        path.includes("/reports/") ? NO_REPORTS : body({ count: 2, rows: [row, second] }),
    }));
    render(<CandidateBrowser projectId="p1" />);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Select" }));
    await user.click(await screen.findByRole("checkbox", { name: "Select jane.pdf" }));
    await user.click(screen.getByRole("checkbox", { name: "Select omar.pdf" }));
    await user.click(screen.getByRole("button", { name: "Compare" }));
    expect(push).toHaveBeenCalledWith("/company/projects/p1/compare?ids=k1,k2");
  });
});

describe("downloads", () => {
  const link = (dialog: HTMLElement, name: string) =>
    within(dialog).getByRole("link", { name }) as HTMLAnchorElement;
  async function openDownload() {
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Download" }));
    return { user, dialog: await screen.findByRole("dialog", { name: "Download" }) };
  }

  it("offers the ranked list as a spreadsheet and as a PDF, with the filters on screen", async () => {
    search = "score_min=60&grade=A,B";
    render(<CandidateBrowser projectId="p1" />);
    const { dialog } = await openDownload();
    expect(link(dialog, "Ranked list as spreadsheet").getAttribute("href")).toBe(
      "/api/company/projects/p1/candidates/export/?score_min=60&grade=A%2CB&as=xlsx",
    );
    expect(link(dialog, "Ranked list as PDF").getAttribute("href")).toBe(
      "/api/company/projects/p1/candidates/export/?score_min=60&grade=A%2CB&as=pdf",
    );
  });

  it("asks for every CV and opens the page of the download", async () => {
    render(<CandidateBrowser projectId="p1" />);
    const { user, dialog } = await openDownload();
    fetchMock.mockImplementation(async () => ({
      ok: true,
      status: 201,
      json: async () => ({ id: "pk1", status: "preparing" }),
    }));
    await user.click(within(dialog).getByRole("button", { name: "All CVs as zip" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/company/downloads/pk1"));
    const call = fetchMock.mock.calls.find((c) => c[0] === "/api/company/projects/p1/downloads/");
    expect(JSON.parse(call![1].body)).toEqual({ all: true });
  });

  it("shows the server's message when the zip cannot be asked for", async () => {
    render(<CandidateBrowser projectId="p1" />);
    const { user, dialog } = await openDownload();
    fetchMock.mockImplementation(async () => ({
      ok: false,
      status: 400,
      json: async () => ({ error: { code: "nothing_to_download", message: "Nothing here." } }),
    }));
    await user.click(within(dialog).getByRole("button", { name: "All CVs as zip" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Nothing here.");
    expect(push).not.toHaveBeenCalled();
  });
});
