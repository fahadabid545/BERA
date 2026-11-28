import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ProjectCandidatesPage from "./page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => "/company/projects/p1/candidates",
  useSearchParams: () => new URLSearchParams(),
}));

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(async (path: string) => ({
      ok: true,
      status: 200,
      json: async () =>
        path.includes("/reports/")
          ? { days: { choices: [1, 7, 30], default: 7 }, reports: [] }
          : { page: 1, pages: 1, count: 0, refresh_seconds: 3, rows: [] },
    })),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ProjectCandidatesPage", () => {
  it("keeps its Filters, Upload CVs and Download buttons", async () => {
    render(await ProjectCandidatesPage({ params: Promise.resolve({ project: "p1" }) }));
    expect(screen.getByRole("button", { name: "Filters" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Upload CVs" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Download" })).toBeTruthy();
  });

  it("asks for the candidates of the project it was opened for", async () => {
    render(await ProjectCandidatesPage({ params: Promise.resolve({ project: "p1" }) }));
    await vi.waitFor(() =>
      expect(vi.mocked(fetch).mock.calls.map((call) => call[0])).toContain(
        "/api/company/projects/p1/candidates/?sort=score&direction=desc&page=1",
      ),
    );
  });
});
