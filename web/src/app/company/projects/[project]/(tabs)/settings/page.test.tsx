import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ProjectSettingsPage from "./page";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const PROJECT = { id: "p1", title: "T", job_description: "D", status: "active", may_delete: true };
const SCORING = {
  must_weight_percent: 70,
  nice_weight_percent: 30,
  recommendation_threshold: 75,
  top_n: 10,
  top_n_cap: 20,
};

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string) => ({
      ok: true,
      status: 200,
      json: async () => (path.endsWith("/scoring/") ? SCORING : PROJECT),
    })),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("ProjectSettingsPage", () => {
  it("loads the project and its scoring settings for the project it was opened for", async () => {
    render(await ProjectSettingsPage({ params: Promise.resolve({ project: "p1" }) }));
    await vi.waitFor(() => {
      const paths = vi.mocked(fetch).mock.calls.map((call) => call[0]);
      expect(paths).toContain("/api/company/projects/p1/");
      expect(paths).toContain("/api/company/projects/p1/scoring/");
    });
  });
});
