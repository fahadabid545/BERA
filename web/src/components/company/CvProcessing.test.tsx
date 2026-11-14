import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CvProcessing } from "./CvProcessing";

const fetchMock = vi.fn();
const BASE = "/api/company/projects/p1/";

const item = (over: object = {}) => ({
  id: "c1",
  name: "jane.pdf",
  status: "waiting",
  reason: "",
  can_retry: false,
  ...over,
});
const snapshot = (items: object[], counts: object = {}, refresh = 3) => ({
  refresh_seconds: refresh,
  counts: { waiting: 0, reading: 0, scoring: 0, done: 0, failed: 0, cancelled: 0, ...counts },
  items,
});

function answer(body: unknown, status = 200) {
  fetchMock.mockResolvedValue({ ok: status < 400, status, json: async () => body });
}
const callsTo = (path: string) =>
  fetchMock.mock.calls.filter((call) => call[0] === `${BASE}${path}`);

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("CV processing", () => {
  it("shows each CV with its status in words", async () => {
    answer(
      snapshot(
        [
          item({ id: "1", name: "a.pdf", status: "waiting" }),
          item({ id: "2", name: "b.pdf", status: "reading" }),
          item({ id: "3", name: "c.pdf", status: "scoring" }),
          item({ id: "4", name: "d.pdf", status: "done" }),
        ],
        { waiting: 1, reading: 1, scoring: 1, done: 1 },
      ),
    );
    render(<CvProcessing projectId="p1" />);
    const table = await screen.findByRole("region", { name: "CV processing" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((row) => within(row).getAllByRole("cell")[1].textContent)).toEqual([
      "Waiting",
      "Reading",
      "Scoring",
      "Done",
    ]);
  });

  it("shows the counts for each status that has any", async () => {
    answer(snapshot([item()], { waiting: 3, failed: 1 }));
    render(<CvProcessing projectId="p1" />);
    const counts = await screen.findByRole("list", { name: "CV status counts" });
    expect(
      within(counts)
        .getAllByRole("listitem")
        .map((li) => li.textContent),
    ).toEqual(["Waiting 3", "Failed 1"]);
  });

  it("a failed CV shows its reason and a Retry button", async () => {
    answer(
      snapshot(
        [
          item({
            status: "failed",
            reason: "We could not read this file.",
            can_retry: true,
          }),
        ],
        { failed: 1 },
      ),
    );
    render(<CvProcessing projectId="p1" />);
    expect(await screen.findByText("We could not read this file.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Retry jane.pdf" })).toBeTruthy();
  });

  it("only failed CVs have Retry", async () => {
    answer(snapshot([item({ status: "done" })], { done: 1 }));
    render(<CvProcessing projectId="p1" />);
    await screen.findByText("jane.pdf");
    expect(screen.queryByRole("button", { name: /Retry/ })).toBeNull();
  });

  it("Retry asks the server and looks again", async () => {
    answer(snapshot([item({ status: "failed", can_retry: true })], { failed: 1 }));
    render(<CvProcessing projectId="p1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Retry jane.pdf" }));
    await waitFor(() => expect(callsTo("cvs/c1/retry/")).toHaveLength(1));
    expect(callsTo("cvs/c1/retry/")[0][1].method).toBe("POST");
    await waitFor(() => expect(callsTo("processing/").length).toBeGreaterThan(1));
  });

  it("a refused Retry shows the server's message", async () => {
    answer(snapshot([item({ status: "failed", can_retry: true })], { failed: 1 }));
    render(<CvProcessing projectId="p1" />);
    const retry = await screen.findByRole("button", { name: "Retry jane.pdf" });
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 409,
      json: async () => ({ error: { code: "x", message: "You have used this month's CVs." } }),
    });
    await userEvent.click(retry);
    expect(await screen.findByText("You have used this month's CVs.")).toBeTruthy();
  });

  it("cancelling asks first, then cancels the waiting CVs", async () => {
    answer(snapshot([item()], { waiting: 2 }));
    render(<CvProcessing projectId="p1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Cancel waiting CVs" }));
    expect(callsTo("cvs/cancel/")).toHaveLength(0);
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel waiting CVs" }));
    await waitFor(() => expect(callsTo("cvs/cancel/")).toHaveLength(1));
  });

  it("there is nothing to cancel when nothing is waiting", async () => {
    answer(snapshot([item({ status: "done" })], { done: 1 }));
    render(<CvProcessing projectId="p1" />);
    await screen.findByText("jane.pdf");
    expect(screen.queryByRole("button", { name: "Cancel waiting CVs" })).toBeNull();
  });

  it("looks again every few seconds, as the server says", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    answer(snapshot([item()], { waiting: 1 }, 3));
    render(<CvProcessing projectId="p1" />);
    await screen.findByText("jane.pdf");
    const before = callsTo("processing/").length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3100);
    });
    expect(callsTo("processing/").length).toBeGreaterThan(before);
  });

  it("stops looking when the page is left", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    answer(snapshot([item()], { waiting: 1 }, 3));
    const { unmount } = render(<CvProcessing projectId="p1" />);
    await screen.findByText("jane.pdf");
    unmount();
    const before = callsTo("processing/").length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(callsTo("processing/").length).toBe(before);
  });

  it("shows nothing when the project has no CVs yet", async () => {
    answer(snapshot([]));
    const { container } = render(<CvProcessing projectId="p1" />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(container.querySelector("table")).toBeNull();
  });

  it("a failure to load is shown in plain words", async () => {
    answer({ error: { code: "internal_error", message: "Something went wrong." } }, 500);
    render(<CvProcessing projectId="p1" />);
    expect((await screen.findByRole("alert")).textContent).toBe("Something went wrong.");
  });
});
