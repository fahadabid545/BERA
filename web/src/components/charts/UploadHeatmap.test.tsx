import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { UploadHeatmap } from "./UploadHeatmap";

const grid = Array.from({ length: 7 }, () => Array<number>(24).fill(0));
grid[0][9] = 2;
grid[5][23] = 1;

describe("the upload heatmap", () => {
  it("has a square for every weekday and hour", () => {
    render(<UploadHeatmap grid={grid} />);
    expect(screen.getAllByRole("img")).toHaveLength(7 * 24);
  });

  it("says each square's day, hour and count without relying on colour", () => {
    render(<UploadHeatmap grid={grid} />);
    expect(screen.getByRole("img", { name: "Monday 09:00: 2 CVs" })).toBeTruthy();
    expect(screen.getByRole("img", { name: "Saturday 23:00: 1 CV" })).toBeTruthy();
    expect(screen.getByRole("img", { name: "Sunday 00:00: 0 CVs" })).toBeTruthy();
  });

  it("shades a square by its share of the busiest", () => {
    render(<UploadHeatmap grid={grid} />);
    const share = (name: string) =>
      screen.getByRole("img", { name }).style.getPropertyValue("--share");
    expect(share("Monday 09:00: 2 CVs")).toBe("100%");
    expect(share("Saturday 23:00: 1 CV")).toBe("50%");
    expect(share("Sunday 00:00: 0 CVs")).toBe("0%");
  });

  it("copes with no data at all", () => {
    render(<UploadHeatmap grid={[]} />);
    expect(screen.queryAllByRole("img")).toHaveLength(0);
  });
});
