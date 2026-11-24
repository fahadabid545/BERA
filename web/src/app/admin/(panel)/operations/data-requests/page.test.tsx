import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import DataRequestsPage from "./page";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ total: 0, items: [], companies: [] }),
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows the data requests page with New request", async () => {
  render(<DataRequestsPage />);
  expect(await screen.findByRole("button", { name: "New request" })).toBeTruthy();
});
