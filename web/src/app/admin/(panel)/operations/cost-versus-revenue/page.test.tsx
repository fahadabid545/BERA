import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CostVersusRevenuePage from "./page";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => ({ error: { code: "forbidden", message: "You do not have access." } }),
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("cost versus revenue page", () => {
  it("asks the server for the figures", async () => {
    render(<CostVersusRevenuePage />);
    await screen.findByRole("alert");
    expect(vi.mocked(fetch).mock.calls[0][0]).toContain("/api/admin/cost-versus-revenue/");
  });
});
