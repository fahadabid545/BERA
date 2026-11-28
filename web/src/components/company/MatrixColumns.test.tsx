import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Matrix } from "./comparison/Matrix";

const fetchMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => "/company/projects/p1/compare",
  useSearchParams: () => new URLSearchParams(""),
}));
const KEY = "matrix-hidden-columns:p1";

function requirements(count: number) {
  return Array.from({ length: count }, (_, index) => ({
    id: `r${index + 1}`,
    text: `Skill ${index + 1}`,
    kind: index === 0 ? "must" : "nice",
    weight: 3,
  }));
}
function serve(count: number, firstText = "Skill 1") {
  const body = {
    page: 1,
    pages: 1,
    count: 1,
    refresh_seconds: 3,
    requirements: requirements(count).map((item, i) =>
      i === 0 ? { ...item, text: firstText } : item,
    ),
    rows: [
      {
        candidate_id: "k1",
        file_name: "jane.pdf",
        name: "J. E.",
        rank: 1,
        score: "80.0",
        grade: "B",
        cells: Array.from({ length: count }, () => ({ verdict: "met", outdated: false })),
      },
    ],
  };
  fetchMock.mockImplementation(async () => ({ ok: true, status: 200, json: async () => body }));
}
const headers = () =>
  within(screen.getByRole("region", { name: "Candidates against requirements", hidden: true }))
    .getAllByRole("columnheader", { hidden: true })
    .map((header) => header.textContent);

beforeEach(() => {
  fetchMock.mockReset();
  window.localStorage.clear();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function open() {
  render(<Matrix projectId="p1" filterQuery="" />);
  await screen.findByRole("region", { name: "Candidates against requirements" });
  await userEvent.click(screen.getByRole("button", { name: "Columns" }));
  return screen.getByRole("dialog");
}

describe("matrix columns", () => {
  it("keeps the table sticky so wide matrices scroll inside their card", async () => {
    serve(40);
    render(<Matrix projectId="p1" filterQuery="" />);
    const region = await screen.findByRole("region", { name: "Candidates against requirements" });
    expect(region.classList.contains("ui-table-wrap--sticky")).toBe(true);
    expect(headers()).toHaveLength(3 + 40);
  });

  it("works with a single requirement, which cannot be switched off", async () => {
    serve(1);
    const picker = await open();
    expect(
      within(picker).getByRole<HTMLInputElement>("checkbox", { name: "Skill 1" }).disabled,
    ).toBe(true);
  });

  it("hides a requirement column and remembers the choice for the project", async () => {
    serve(3);
    const picker = await open();
    await userEvent.click(within(picker).getByRole("checkbox", { name: "Skill 2" }));
    expect(headers()).toEqual(["Rank", "Candidate", "AI score", "Skill 1", "Skill 3"]);
    expect(JSON.parse(window.localStorage.getItem(KEY)!)).toEqual(["r2"]);
  });

  it("starts from the saved choice", async () => {
    window.localStorage.setItem(KEY, JSON.stringify(["r1"]));
    serve(3);
    render(<Matrix projectId="p1" filterQuery="" />);
    await screen.findByRole("region", { name: "Candidates against requirements" });
    expect(await screen.findAllByRole("columnheader", { name: /Skill 2/ })).toHaveLength(1);
    expect(screen.queryByRole("columnheader", { name: /Skill 1/ })).toBeNull();
  });

  it("never lets the last shown column be switched off", async () => {
    serve(2);
    const picker = await open();
    await userEvent.click(within(picker).getByRole("checkbox", { name: "Skill 1" }));
    expect(
      within(picker).getByRole<HTMLInputElement>("checkbox", { name: "Skill 2" }).disabled,
    ).toBe(true);
    expect(headers()).toEqual(["Rank", "Candidate", "AI score", "Skill 2"]);
  });

  it("selects all and shows only must-haves on request", async () => {
    serve(3);
    const picker = await open();
    await userEvent.click(within(picker).getByRole("button", { name: "Must-haves only" }));
    expect(headers()).toEqual(["Rank", "Candidate", "AI score", "Skill 1"]);
    await userEvent.click(within(picker).getByRole("button", { name: "Select all" }));
    expect(headers()).toHaveLength(6);
    expect(JSON.parse(window.localStorage.getItem(KEY)!)).toEqual([]);
  });

  it("shows every column when a saved choice would hide them all", async () => {
    window.localStorage.setItem(KEY, JSON.stringify(["r1", "r2"]));
    serve(2);
    render(<Matrix projectId="p1" filterQuery="" />);
    await screen.findByRole("region", { name: "Candidates against requirements" });
    await vi.waitFor(() => expect(headers()).toHaveLength(5));
  });

  it("ignores a damaged saved choice", async () => {
    window.localStorage.setItem(KEY, "not json");
    serve(2);
    render(<Matrix projectId="p1" filterQuery="" />);
    await screen.findByRole("region", { name: "Candidates against requirements" });
    expect(headers()).toHaveLength(5);
  });

  it("still works when the browser refuses to store the choice", async () => {
    serve(3);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const picker = await open();
    await userEvent.click(within(picker).getByRole("checkbox", { name: "Skill 3" }));
    expect(headers()).toEqual(["Rank", "Candidate", "AI score", "Skill 1", "Skill 2"]);
    vi.restoreAllMocks();
  });

  it("keeps long requirement names in a fixed-width header with the full text", async () => {
    const long = "A very long requirement name that would otherwise stretch the column";
    serve(1, long);
    render(<Matrix projectId="p1" filterQuery="" />);
    const header = await screen.findByRole("columnheader", { name: new RegExp(long) });
    expect(header.textContent).toBe(long);
  });
});
