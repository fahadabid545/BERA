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
  counts: {
    awaiting_confirmation: 0,
    waiting: 0,
    reading: 0,
    scoring: 0,
    done: 0,
    failed: 0,
    cancelled: 0,
    ...counts,
  },
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

describe("cost estimate before processing", () => {
  const ESTIMATE = {
    approximate: true,
    cvs: 3,
    tokens_in: 6000,
    tokens_out: 1000,
    tokens_total: 7000,
    estimated_cost: "0.021000",
    limits: {
      cvs_this_month: { used: 3, limit: 100 },
      cvs_in_project: { used: 3, limit: 50 },
      tokens: { used: 500, limit: 100000, after_estimate: 7500 },
    },
    blocked: false,
    message: "",
    prompt: null,
  };

  function serve(estimate: object = ESTIMATE) {
    fetchMock.mockImplementation(async (path: string, options?: { method?: string }) => {
      const body = path.endsWith("/cvs/estimate/")
        ? options?.method === "POST"
          ? { confirmed: 3 }
          : estimate
        : snapshot([item({ status: "awaiting_confirmation" })], { awaiting_confirmation: 3 }, 0);
      return { ok: true, status: 200, json: async () => body };
    });
  }

  it("shows the held CVs as awaiting confirmation with a way to review the estimate", async () => {
    serve();
    render(<CvProcessing projectId="p1" />);
    expect(await screen.findByText("Awaiting confirmation 3")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Review cost estimate" })).toBeTruthy();
  });

  it("shows the approximate figures against the plan's limits", async () => {
    serve();
    render(<CvProcessing projectId="p1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Review cost estimate" }));
    const list = await screen.findByRole("list", { name: "Cost estimate" });
    expect(
      within(list)
        .getAllByRole("listitem")
        .map((li) => li.textContent),
    ).toEqual([
      "CVs: 3",
      "Approximate tokens: 7000",
      "Approximate cost: $0.021000",
      "CVs this month: 3 of 100",
      "CVs in this project: 3 of 50",
      "AI tokens this period: 500 of 100000",
    ]);
    expect(screen.getByText("Approximate cost")).toBeTruthy();
  });

  it("confirming sends the confirmation and nothing else", async () => {
    serve();
    render(<CvProcessing projectId="p1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Review cost estimate" }));
    await userEvent.click(await screen.findByRole("button", { name: "Process CVs" }));
    await waitFor(() =>
      expect(callsTo("cvs/estimate/").some((c) => c[1]?.method === "POST")).toBe(true),
    );
    expect(callsTo("cvs/cancel/")).toHaveLength(0);
  });

  it("discarding cancels the held CVs", async () => {
    serve();
    render(<CvProcessing projectId="p1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Review cost estimate" }));
    await userEvent.click(await screen.findByRole("button", { name: "Discard CVs" }));
    await waitFor(() => expect(callsTo("cvs/cancel/")).toHaveLength(1));
    expect(callsTo("cvs/estimate/").some((c) => c[1]?.method === "POST")).toBe(false);
  });

  it("a batch that would pass the token cap shows the message and cannot be confirmed", async () => {
    serve({
      ...ESTIMATE,
      blocked: true,
      message: "Too much AI for this period.",
      prompt: "upgrade",
    });
    render(<CvProcessing projectId="p1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Review cost estimate" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Too much AI for this period.");
    expect(screen.queryByRole("button", { name: "Process CVs" })).toBeNull();
    expect(screen.getByRole("button", { name: "Discard CVs" })).toBeTruthy();
  });

  it("opens the estimate by itself when the upload area says CVs were added", async () => {
    serve();
    render(<CvProcessing projectId="p1" />);
    await screen.findByText("Awaiting confirmation 3");
    act(() => {
      window.dispatchEvent(new Event("cvs-held"));
    });
    expect(await screen.findByRole("list", { name: "Cost estimate" })).toBeTruthy();
  });

  it("shows no estimate button when nothing is held", async () => {
    answer(snapshot([item()], { waiting: 1 }));
    render(<CvProcessing projectId="p1" />);
    await screen.findByText("Waiting 1");
    expect(screen.queryByRole("button", { name: "Review cost estimate" })).toBeNull();
  });
});
