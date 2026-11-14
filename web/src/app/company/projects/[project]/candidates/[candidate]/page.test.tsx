import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CandidatePage from "./page";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ error: { code: "not_found", message: "Not found." } }),
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("candidate page", () => {
  it("asks for the candidate named in the address", async () => {
    render(await CandidatePage({ params: Promise.resolve({ project: "p1", candidate: "k1" }) }));
    await screen.findByRole("alert");
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe("/api/company/projects/p1/candidates/k1/");
  });
});
