import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

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
});

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

  it("shows an empty area for the chosen tab", () => {
    render(<DashboardTabs />);
    expect(screen.getByRole("tabpanel").textContent).toBe("");
  });
});
