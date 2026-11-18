import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ScoringDefaultsPage from "./page";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({
      must_weight_percent: 70,
      nice_weight_percent: 30,
      recommendation_threshold: 75,
      top_n: 10,
      cap_on_missing_must_have: false,
      top_n_cap: 20,
      factors: {},
    }),
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("scoring defaults page", () => {
  it("loads the company's defaults and offers Save", async () => {
    render(<ScoringDefaultsPage />);
    expect(await screen.findByRole("button", { name: "Save" })).toBeTruthy();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/company/scoring-defaults/");
  });
});
