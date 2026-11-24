import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import PaymentsPage from "./page";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        total: 0,
        page: 1,
        page_size: 50,
        totals: [],
        items: [],
        companies: [],
        currencies: [],
      }),
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows the payments page", async () => {
  render(<PaymentsPage />);
  expect(await screen.findByText("No payments.")).toBeTruthy();
  expect(screen.getByLabelText("Type")).toBeTruthy();
});
