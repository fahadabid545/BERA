import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import AdminDashboardPage from "./page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => "/admin",
  useSearchParams: () => new URLSearchParams(""),
}));

describe("admin dashboard page", () => {
  it("shows the overview with its tabs", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ error: { code: "not_found", message: "Not found." } }),
      }),
    );
    render(<AdminDashboardPage />);
    expect((await screen.findAllByRole("tab")).length).toBeGreaterThan(2);
    vi.unstubAllGlobals();
  });
});
