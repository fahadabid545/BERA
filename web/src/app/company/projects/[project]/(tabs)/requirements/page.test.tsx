import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ProjectRequirementsPage from "./page";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ requirements: [], warnings: [] }),
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("ProjectRequirementsPage", () => {
  it("shows the editor for the project it was opened for", async () => {
    render(await ProjectRequirementsPage({ params: Promise.resolve({ project: "p1" }) }));
    expect(screen.getByRole("button", { name: "Add requirement" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Suggest requirements" })).toBeTruthy();
    await vi.waitFor(() =>
      expect(vi.mocked(fetch).mock.calls[0][0]).toBe("/api/company/projects/p1/requirements/"),
    );
  });
});
