import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ProjectCandidatesPage from "./page";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ page: 1, pages: 1, count: 0, refresh_seconds: 3, rows: [] }),
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ProjectCandidatesPage", () => {
  it("keeps its Filters, Upload CVs and Download all buttons", async () => {
    render(await ProjectCandidatesPage({ params: Promise.resolve({ project: "p1" }) }));
    expect(screen.getByRole("button", { name: "Filters" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Upload CVs" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Download all" })).toBeTruthy();
  });

  it("asks for the candidates of the project it was opened for", async () => {
    render(await ProjectCandidatesPage({ params: Promise.resolve({ project: "p1" }) }));
    await vi.waitFor(() =>
      expect(vi.mocked(fetch).mock.calls[0][0]).toBe(
        "/api/company/projects/p1/candidates/?sort=score&direction=desc&page=1",
      ),
    );
  });
});
