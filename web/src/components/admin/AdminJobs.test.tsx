import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AdminJobs } from "./AdminJobs";

const fetchMock = vi.fn();
const NOW = new Date().toISOString();
const job = (id: string, over: object = {}) => ({
  id,
  company_id: "1",
  company: "Fake Company",
  project: "Fake Project",
  state: "failed",
  tries: 3,
  reason: "We could not read this file.",
  since: NOW,
  can_retry: true,
  can_cancel: false,
  ...over,
});
const LISTING = {
  totals: { waiting: 1, running: 0, failed: 1, stuck: 1 },
  companies: [
    { id: "1", name: "Fake Company", waiting: 1, running: 0, failed: 1, stuck: 0 },
    { id: "2", name: "Other Company", waiting: 0, running: 0, failed: 0, stuck: 1 },
  ],
  total: 3,
  items: [
    job("a"),
    job("b", {
      state: "waiting",
      tries: 0,
      reason: "Waiting for its turn.",
      can_retry: false,
      can_cancel: true,
    }),
    job("c", {
      company: "Other Company",
      state: "stuck",
      reason: "It took too long.",
      can_retry: true,
      can_cancel: true,
    }),
  ],
};

function reply(status: number, body: unknown) {
  fetchMock.mockResolvedValueOnce({ ok: status < 400, status, json: async () => body });
}
const rowsOf = (name: string) =>
  Array.from(screen.getByRole("region", { name }).querySelectorAll("tbody tr"));
const cells = (row: Element) =>
  Array.from(row.querySelectorAll("th, td")).map((cell) => cell.textContent);
const calledPaths = () => fetchMock.mock.calls.map((call) => String(call[0]));

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Jobs monitor", () => {
  it("counts the jobs of each company by state, with a total", async () => {
    reply(200, LISTING);
    render(<AdminJobs />);
    await screen.findByRole("region", { name: "Jobs by company" });
    expect(rowsOf("Jobs by company").map(cells)).toEqual([
      ["Fake Company", "1", "0", "1", "0"],
      ["Other Company", "0", "0", "0", "1"],
      ["Total", "1", "0", "1", "1"],
    ]);
  });

  it("lists each job with its state in words, its reason and its age, but no file name", async () => {
    reply(200, LISTING);
    render(<AdminJobs />);
    await screen.findByRole("region", { name: "Jobs" });
    const rows = rowsOf("Jobs");
    expect(cells(rows[0]).slice(0, 6)).toEqual([
      "Fake Company",
      "Fake Project",
      "Failed",
      "3",
      "We could not read this file.",
      "Just now",
    ]);
    expect(cells(rows[1])[2]).toBe("Waiting");
    expect(cells(rows[2])[2]).toBe("Stuck");
    expect(screen.getByText("Showing 3 of 3")).toBeTruthy();
  });

  it("offers Retry for failed and stuck jobs and Cancel job for waiting and stuck ones", async () => {
    reply(200, LISTING);
    render(<AdminJobs />);
    await screen.findByRole("region", { name: "Jobs" });
    const buttons = (row: Element) =>
      within(row as HTMLElement)
        .queryAllByRole("button")
        .map((button) => button.textContent);
    const rows = rowsOf("Jobs");
    expect(buttons(rows[0])).toEqual(["Retry"]);
    expect(buttons(rows[1])).toEqual(["Cancel job"]);
    expect(buttons(rows[2])).toEqual(["Retry", "Cancel job"]);
  });

  it("retries a job and shows the list again", async () => {
    reply(200, LISTING);
    render(<AdminJobs />);
    await screen.findByRole("region", { name: "Jobs" });
    reply(200, {});
    reply(200, { ...LISTING, items: [LISTING.items[1]], total: 1 });
    await userEvent.click(within(rowsOf("Jobs")[0] as HTMLElement).getByRole("button"));
    await waitFor(() => expect(rowsOf("Jobs")).toHaveLength(1));
    const [path, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(path).toBe("/api/admin/jobs/a/retry/");
    expect(init.method).toBe("POST");
  });

  it("asks in a popup before cancelling, and cancels only when confirmed", async () => {
    reply(200, LISTING);
    render(<AdminJobs />);
    await screen.findByRole("region", { name: "Jobs" });
    await userEvent.click(
      within(rowsOf("Jobs")[1] as HTMLElement).getByRole("button", { name: "Cancel job" }),
    );
    const dialog = screen.getByRole("dialog");
    expect(fetchMock).toHaveBeenCalledTimes(1); // nothing was sent yet
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await userEvent.click(
      within(rowsOf("Jobs")[1] as HTMLElement).getByRole("button", { name: "Cancel job" }),
    );
    reply(200, {});
    reply(200, { ...LISTING, items: [], total: 0 });
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel job" }),
    );
    await waitFor(() => expect(calledPaths()).toContain("/api/admin/jobs/b/cancel/"));
    expect(await screen.findByText("No jobs.")).toBeTruthy();
  });

  it("says in plain words when the server refuses and shows the list as it now is", async () => {
    reply(200, LISTING);
    render(<AdminJobs />);
    await screen.findByRole("region", { name: "Jobs" });
    reply(409, {
      error: { code: "job_not_retryable", message: "Only a failed or stuck job can be retried." },
    });
    reply(200, LISTING);
    await userEvent.click(within(rowsOf("Jobs")[0] as HTMLElement).getByRole("button"));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Only a failed or stuck job can be retried.",
    );
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("filters by state and by company", async () => {
    reply(200, LISTING);
    render(<AdminJobs />);
    await screen.findByRole("region", { name: "Jobs" });
    reply(200, LISTING);
    await userEvent.selectOptions(screen.getByLabelText("State"), "failed");
    await waitFor(() => expect(calledPaths().at(-1)).toBe("/api/admin/jobs/?state=failed"));
    reply(200, LISTING);
    await userEvent.selectOptions(screen.getByLabelText("Company"), "2");
    await waitFor(() =>
      expect(calledPaths().at(-1)).toBe("/api/admin/jobs/?state=failed&company=2"),
    );
  });

  it("shows No jobs when there are none", async () => {
    reply(200, {
      totals: { waiting: 0, running: 0, failed: 0, stuck: 0 },
      companies: [],
      total: 0,
      items: [],
    });
    render(<AdminJobs />);
    expect(await screen.findByText("No jobs.")).toBeTruthy();
  });

  it("shows the server's message when the page cannot load", async () => {
    reply(403, {
      error: { code: "not_allowed", message: "You do not have permission to do this." },
    });
    render(<AdminJobs />);
    expect((await screen.findByRole("alert")).textContent).toBe(
      "You do not have permission to do this.",
    );
  });
});
