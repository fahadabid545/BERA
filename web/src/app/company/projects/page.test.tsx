import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ProjectsPage from "./page";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ results: [], page: 1, pages: 1, total: 0, page_size: 20 }),
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("projects page", () => {
  it("shows the list controls and a New project button", async () => {
    render(<ProjectsPage />);
    expect((screen.getByLabelText("Search") as HTMLInputElement).type).toBe("search");
    expect(screen.getByRole("link", { name: "New project" }).getAttribute("href")).toBe(
      "/company/projects/new",
    );
    await screen.findByText("No projects found.");
  });
});
