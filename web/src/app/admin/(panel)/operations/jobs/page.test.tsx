import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import JobsPage from "./page";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        totals: { waiting: 0, running: 0, failed: 1, stuck: 0 },
        companies: [{ id: "1", name: "Fake Company", waiting: 0, running: 0, failed: 1, stuck: 0 }],
        total: 1,
        items: [
          {
            id: "a",
            company_id: "1",
            company: "Fake Company",
            project: "Fake Project",
            state: "failed",
            tries: 3,
            reason: "We could not read this file.",
            since: new Date().toISOString(),
            can_retry: true,
            can_cancel: false,
          },
        ],
      }),
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows the jobs with Retry", async () => {
  render(<JobsPage />);
  expect(await screen.findByRole("button", { name: "Retry" })).toBeTruthy();
});
