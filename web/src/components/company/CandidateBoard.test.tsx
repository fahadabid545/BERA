import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CandidateBoard } from "./CandidateBoard";

const fetchMock = vi.fn();
const STAGE_ORDER = ["new", "shortlisted", "interviewed", "on_hold", "selected", "rejected"];
const card = (over: object = {}) => ({
  id: "k1",
  key: "BE-1",
  file_name: "jane.pdf",
  name: "J. E.",
  role: "Sales Manager",
  score: "82.5",
  grade: "B",
  ...over,
});
function board(cardsByStage: Record<string, object[]> = {}, counts: Record<string, number> = {}) {
  return {
    refresh_seconds: 3,
    filtered: false,
    requirements: [{ id: "r1", text: "Python", kind: "must" }],
    columns: STAGE_ORDER.map((stage) => ({
      stage,
      count: counts[stage] ?? (cardsByStage[stage] ?? []).length,
      cards: cardsByStage[stage] ?? [],
    })),
  };
}
function serve(data: object) {
  fetchMock.mockImplementation(async (path: string, init?: { method?: string }) => ({
    ok: true,
    status: 200,
    json: async () => (init?.method === "POST" ? { changed: 1, unchanged: 0 } : data),
  }));
}
const posts = () =>
  fetchMock.mock.calls.filter(
    (call) => (call[1] as { method?: string } | undefined)?.method === "POST",
  );

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("candidates board", () => {
  it("shows a column for every stage with its count", async () => {
    serve(board({ new: [card()] }, { rejected: 4 }));
    render(<CandidateBoard projectId="p1" />);
    const columns = await screen.findAllByRole("region");
    expect(columns.map((column) => column.getAttribute("aria-label"))).toEqual([
      "New",
      "Shortlisted",
      "Interviewed",
      "On hold",
      "Selected",
      "Rejected",
    ]);
    expect(within(columns[0]).getByText("1")).toBeTruthy();
    expect(within(columns[5]).getByText("4")).toBeTruthy();
  });

  it("shows key, name, role and score on a simple card, linked to the candidate", async () => {
    serve(board({ new: [card()] }));
    render(<CandidateBoard projectId="p1" />);
    expect(await screen.findByText("BE-1")).toBeTruthy();
    expect(screen.getByText("Sales Manager")).toBeTruthy();
    expect(screen.getByText("82.5")).toBeTruthy();
    expect(screen.getByRole("link", { name: "J. E." }).getAttribute("href")).toBe(
      "/company/projects/p1/candidates/k1",
    );
  });

  it("falls back to the file name and leaves out an empty role", async () => {
    serve(board({ new: [card({ name: "", role: "" })] }));
    render(<CandidateBoard projectId="p1" />);
    expect(await screen.findByRole("link", { name: "jane.pdf" })).toBeTruthy();
    expect(screen.queryByText("Sales Manager")).toBeNull();
  });

  it("says how many are shown when a column holds more than it loads", async () => {
    serve(board({ new: [card()] }, { new: 60 }));
    render(<CandidateBoard projectId="p1" />);
    expect(await screen.findByText("Showing 1 of 60")).toBeTruthy();
  });

  it("sends the filters to the server", async () => {
    serve(board());
    render(<CandidateBoard projectId="p1" filters={{ score_min: "80" }} />);
    await screen.findAllByRole("region");
    expect(fetchMock.mock.calls[0][0]).toContain("/candidates/board/?score_min=80");
  });

  it("reports an error in words", async () => {
    fetchMock.mockImplementation(async () => ({
      ok: false,
      status: 500,
      json: async () => ({ error: { code: "x", message: "Something went wrong." } }),
    }));
    render(<CandidateBoard projectId="p1" />);
    expect((await screen.findByRole("alert")).textContent).toBe("Something went wrong.");
  });

  it("moves a card from its menu only after the popup is confirmed", async () => {
    serve(board({ new: [card()] }));
    render(<CandidateBoard projectId="p1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Move BE-1" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Shortlisted" }));
    expect(posts()).toHaveLength(0);
    const popup = await screen.findByRole("dialog");
    expect(within(popup).getByText("Move BE-1 to Shortlisted?")).toBeTruthy();
    await userEvent.click(within(popup).getByRole("button", { name: "Change stage" }));
    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(posts()[0][0]).toContain("/candidates/stage/");
    expect(JSON.parse(posts()[0][1].body)).toEqual({ candidate_ids: ["k1"], stage: "shortlisted" });
  });

  it("does not move the card when the popup is cancelled", async () => {
    serve(board({ new: [card()] }));
    render(<CandidateBoard projectId="p1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Move BE-1" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Rejected" }));
    await userEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Cancel" }),
    );
    expect(posts()).toHaveLength(0);
  });

  it("offers every stage except the card's own in its menu", async () => {
    serve(board({ selected: [card()] }));
    render(<CandidateBoard projectId="p1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Move BE-1" }));
    const items = (await screen.findAllByRole("menuitem")).map((item) => item.textContent);
    expect(items).toEqual(["New", "Shortlisted", "Interviewed", "On hold", "Rejected"]);
  });

  it("moves a card dropped on another column after confirmation", async () => {
    serve(board({ new: [card()] }));
    render(<CandidateBoard projectId="p1" />);
    const dragged = (await screen.findByText("BE-1")).closest("article")!;
    const target = screen.getByRole("region", { name: "Interviewed" });
    fireEvent.dragStart(dragged);
    fireEvent.dragOver(target);
    fireEvent.drop(target);
    const popup = await screen.findByRole("dialog");
    expect(within(popup).getByText("Move BE-1 to Interviewed?")).toBeTruthy();
    await userEvent.click(within(popup).getByRole("button", { name: "Change stage" }));
    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(JSON.parse(posts()[0][1].body).stage).toBe("interviewed");
  });

  it("ignores a drop when nothing is being dragged", async () => {
    serve(board({ new: [card()] }));
    render(<CandidateBoard projectId="p1" />);
    fireEvent.drop(await screen.findByRole("region", { name: "Selected" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
