import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CompaniesPage from "./page";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ results: [], page: 1, pages: 1, total: 0, plans: [] }),
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("companies page", () => {
  it("shows the companies list with its search box", async () => {
    render(<CompaniesPage />);
    expect((screen.getByLabelText("Search") as HTMLInputElement).type).toBe("search");
    expect(await screen.findByText("No companies found.")).toBeTruthy();
    expect(vi.mocked(fetch).mock.calls[0][0]).toContain("/api/admin/companies/");
  });
});
