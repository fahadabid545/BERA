import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import DesignSample from "./page";

afterEach(() => vi.unstubAllEnvs());

describe("design sample page", () => {
  it("shows every building block", () => {
    render(<DesignSample />);

    for (const heading of [
      "Buttons",
      "Inputs, selects and checkboxes",
      "Cards, tags and tooltips",
      "Table",
      "Tabs and popup",
    ]) {
      expect(screen.getByRole("heading", { name: heading })).toBeTruthy();
    }
    expect(screen.getAllByRole("button").length).toBeGreaterThan(5);
    expect(screen.getByRole("switch", { name: "Dark mode" })).toBeTruthy();
    expect(screen.getByRole("tablist")).toBeTruthy();
    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getByRole("combobox")).toBeTruthy();
    expect(screen.getAllByRole("checkbox")).toHaveLength(2);
    expect(screen.getByRole("textbox", { name: "Project name" })).toBeTruthy();
    for (const word of ["Strong match", "Missing must-have", "Not recommended", "Live"]) {
      expect(screen.getAllByText(word).length).toBeGreaterThan(0);
    }
  });

  it("is hidden in production builds", () => {
    vi.stubEnv("NODE_ENV", "production");
    expect(() => render(<DesignSample />)).toThrow();
  });
});
