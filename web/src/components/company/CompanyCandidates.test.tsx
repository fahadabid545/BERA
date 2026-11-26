import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CompanyCandidates } from "./CompanyCandidates";

let search = "";
const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => "/company/candidates",
  useSearchParams: () => new URLSearchParams(search),
}));

const fetchMock = vi.fn();
beforeEach(() => {
  search = "";
  replace.mockReset();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
const json = (body: unknown, ok = true) => ({ ok, status: ok ? 200 : 400, json: async () => body });

const row = {
  id: "c1",
  project_id: "p1",
  project_title: "Python Developer",
  file_name: "a.pdf",
  name: "A. H.",
  score: "90.0",
  grade: "A",
  ats_score: 80,
  label: "strong_match",
  stage: "shortlisted",
  missing_must: 1,
  missing_nice: 0,
};
const listing = (over = {}) => ({
  flag: "all",
  page: 1,
  pages: 1,
  count: 1,
  flags: {
    all: 3,
    new: 1,
    shortlisted: 1,
    interviewed: 0,
    on_hold: 0,
    selected: 0,
    rejected: 1,
  },
  projects: [{ id: "p1", title: "Python Developer" }],
  rows: [row],
  ...over,
});
const asked = () => fetchMock.mock.calls.map(([url]) => String(url));

describe("CompanyCandidates", () => {
  it("shows a tab for each flag with its count and the candidate's details", async () => {
    fetchMock.mockResolvedValue(json(listing()));
    render(<CompanyCandidates />);
    expect(await screen.findByRole("tab", { name: "Shortlisted (1)" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "All (3)" })).toBeTruthy();
    expect(screen.getAllByRole("tab")).toHaveLength(7);
    const table = screen.getByRole("region", { name: "Candidates" });
    expect(within(table).getByRole("link", { name: "A. H." }).getAttribute("href")).toBe(
      "/company/projects/p1/candidates/c1",
    );
    expect(within(table).getByText("90.0 (A)")).toBeTruthy();
    expect(within(table).getByText("80")).toBeTruthy();
    expect(within(table).getByText("1 must-have")).toBeTruthy();
    expect(asked()[0]).toContain("flag=all");
  });

  it("asks for the tab named in the address and keeps a chosen tab there", async () => {
    search = "tab=rejected";
    fetchMock.mockResolvedValue(json(listing()));
    render(<CompanyCandidates />);
    await screen.findByRole("tab", { name: "Rejected (1)" });
    expect(asked()[0]).toContain("flag=rejected");
    await userEvent.click(screen.getByRole("tab", { name: "Selected (0)" }));
    expect(replace).toHaveBeenCalledWith("/company/candidates?tab=selected", { scroll: false });
  });

  it("filters by project, score thresholds, missing and the rest", async () => {
    fetchMock.mockResolvedValue(json(listing()));
    const user = userEvent.setup();
    render(<CompanyCandidates />);
    await screen.findByRole("tab", { name: "All (3)" });
    await user.selectOptions(screen.getByLabelText("Project"), "p1");
    await user.selectOptions(screen.getByLabelText("AI score"), "80");
    await user.selectOptions(screen.getByLabelText("ATS score"), "70");
    await user.selectOptions(screen.getByLabelText("Missing"), "must");
    await user.selectOptions(screen.getByLabelText("Grade"), "A");
    await user.selectOptions(screen.getByLabelText("Recommendation"), "possible");
    await vi.waitFor(() => {
      const last = asked().at(-1) ?? "";
      for (const part of [
        "project=p1",
        "score_min=80",
        "ats_min=70",
        "missing=must",
        "grade=A",
        "label=possible",
      ])
        expect(last).toContain(part);
    });
    expect(screen.getByLabelText("AI score").textContent).toContain("90 and above");
    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    await vi.waitFor(() => expect(asked().at(-1)).not.toContain("score_min"));
  });

  it("changes a candidate's flag in the row and asks again", async () => {
    fetchMock.mockImplementation(async (url: string) =>
      String(url).includes("/stage/") ? json({}) : json(listing()),
    );
    const user = userEvent.setup();
    render(<CompanyCandidates />);
    await user.selectOptions(await screen.findByLabelText("Flag for A. H."), "interviewed");
    await vi.waitFor(() => {
      const call = fetchMock.mock.calls.find(([url]) => String(url).includes("/stage/"));
      expect(call?.[0]).toBe("/api/company/projects/p1/candidates/stage/");
      expect(JSON.parse(call?.[1].body)).toEqual({ candidate_ids: ["c1"], stage: "interviewed" });
    });
    await vi.waitFor(() =>
      expect(asked().filter((url) => url.includes("/api/company/candidates/")).length).toBe(2),
    );
  });

  it("pages through the list", async () => {
    fetchMock.mockResolvedValue(json(listing({ pages: 2 })));
    const user = userEvent.setup();
    render(<CompanyCandidates />);
    await user.click(await screen.findByRole("button", { name: "Next" }));
    await vi.waitFor(() => expect(asked().at(-1)).toContain("page=2"));
  });

  it("says so when nobody matches, and shows the server's message on a failure", async () => {
    fetchMock.mockResolvedValue(json(listing({ rows: [], count: 0 })));
    render(<CompanyCandidates />);
    expect(await screen.findByText("No candidates found.")).toBeTruthy();
    cleanup();
    fetchMock.mockResolvedValue(json({ error: { code: "bad", message: "Choose a flag." } }, false));
    render(<CompanyCandidates />);
    expect((await screen.findByRole("alert")).textContent).toBe("Choose a flag.");
  });
});
