import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ProjectSettingsPage from "./page";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        id: "p1",
        title: "T",
        job_description: "D",
        status: "active",
        may_delete: true,
      }),
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("ProjectSettingsPage", () => {
  it("loads the project it was opened for", async () => {
    const page = await ProjectSettingsPage({ params: Promise.resolve({ project: "p1" }) });
    render(page);
    await vi.waitFor(() =>
      expect(vi.mocked(fetch).mock.calls[0][0]).toBe("/api/company/projects/p1/"),
    );
  });
});
