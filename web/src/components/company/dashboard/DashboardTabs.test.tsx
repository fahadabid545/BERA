import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DashboardTabs } from "./DashboardTabs";

const replace = vi.fn();
let search = "";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => "/company",
  useSearchParams: () => new URLSearchParams(search),
}));

beforeEach(() => {
  replace.mockClear();
  search = "";
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ error: { code: "not_found", message: "Not found." } }),
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

const selectedTab = () =>
  screen.getAllByRole("tab").find((tab) => tab.getAttribute("aria-selected") === "true");

describe("DashboardTabs", () => {
  it("shows the five tabs with Overview chosen first", () => {
    render(<DashboardTabs />);
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual([
      "Overview",
      "Projects",
      "Candidates",
      "Usage",
      "Activity",
    ]);
    expect(selectedTab()?.textContent).toBe("Overview");
  });

  it("opens the tab named in the address", () => {
    search = "tab=usage";
    render(<DashboardTabs />);
    expect(selectedTab()?.textContent).toBe("Usage");
  });

  it.each(["unknown", ""])("falls back to Overview for the address tab %j", (value) => {
    search = `tab=${value}`;
    render(<DashboardTabs />);
    expect(selectedTab()?.textContent).toBe("Overview");
  });

  it("puts the chosen tab into the address", async () => {
    render(<DashboardTabs />);
    await userEvent.click(screen.getByRole("tab", { name: "Candidates" }));
    expect(replace).toHaveBeenCalledWith("/company?tab=candidates", { scroll: false });
  });

  it("shows the company's dashboard on Overview and an empty area on the other tabs", async () => {
    render(<DashboardTabs />);
    await vi.waitFor(() =>
      expect(vi.mocked(fetch).mock.calls[0][0]).toBe("/api/company/dashboard/"),
    );
    cleanup();
    search = "tab=usage";
    render(<DashboardTabs />);
    expect(screen.getByRole("tabpanel").textContent).toBe("");
  });
});
