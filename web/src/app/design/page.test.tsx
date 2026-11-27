import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", async (original) => ({
  ...(await original<typeof import("next/navigation")>()),
  useRouter: () => ({ push: vi.fn() }),
}));

import DesignSample from "./page";

afterEach(() => vi.unstubAllEnvs());

describe("design sample page", () => {
  it("shows every building block", () => {
    render(<DesignSample />);

    for (const heading of [
      "Buttons",
      "Inputs, selects and checkboxes",
      "Charts",
      "Dashboard",
      "Comparison",
      "Admin overview",
      "Announcement banner",
      "Cards, tags and tooltips",
      "Table",
      "Website skin",
      "Tabs and popup",
    ]) {
      expect(screen.getByRole("heading", { name: heading })).toBeTruthy();
    }
    expect(screen.getAllByRole("button").length).toBeGreaterThan(5);
    expect(screen.getByRole("switch", { name: "Dark mode" })).toBeTruthy();
    expect(screen.getByRole("tablist")).toBeTruthy();
    expect(screen.getByRole("navigation", { name: "Sample pages" })).toBeTruthy();
    expect(screen.getAllByRole("table").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("combobox").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("checkbox").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole("textbox", { name: "Project name" })).toBeTruthy();
    for (const word of ["Strong match", "Missing must-have", "Not recommended", "Live"]) {
      expect(screen.getAllByText(word).length).toBeGreaterThan(0);
    }
  });

  it("shows the website skin's buttons, field and card inside the skin", () => {
    render(<DesignSample />);
    const skin = document.querySelector(".site-skin") as HTMLElement;
    expect(within(skin).getByRole("button", { name: "Get started" })).toBeTruthy();
    expect(within(skin).getByRole("textbox", { name: "Website sample field" })).toBeTruthy();
    expect(within(skin).getByLabelText("Website sample card")).toBeTruthy();
  });

  it("is hidden in production builds", () => {
    vi.stubEnv("NODE_ENV", "production");
    expect(() => render(<DesignSample />)).toThrow();
  });
});
