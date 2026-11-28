import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Avatar, initialsOf } from "./Avatar";
import { RESULT_WORDS, ResultGlyph, type Result } from "./ResultGlyph";
import { ScoreBadge } from "./ScoreBadge";
import { StageGlyph, type StageName } from "./StageGlyph";

const RESULTS = Object.keys(RESULT_WORDS) as Result[];
const STAGE_NAMES: StageName[] = [
  "new",
  "shortlisted",
  "interviewed",
  "on_hold",
  "selected",
  "rejected",
];

describe("ResultGlyph", () => {
  it.each(RESULTS)("draws %s with its own class and stays hidden from screen readers", (result) => {
    const { container } = render(<ResultGlyph result={result} />);
    const svg = container.querySelector("svg");
    expect(svg?.classList.contains(`ui-glyph--${result}`)).toBe(true);
    expect(svg?.getAttribute("aria-hidden")).toBe("true");
  });

  it("gives every result a different shape", () => {
    const shapes = RESULTS.map((result) => {
      const { container } = render(<ResultGlyph result={result} />);
      return container.innerHTML.replace(/ui-glyph--\w+/, "");
    });
    expect(new Set(shapes).size).toBe(RESULTS.length);
  });
});

describe("StageGlyph", () => {
  it("gives every stage a different shape", () => {
    const shapes = STAGE_NAMES.map((stage) => {
      const { container } = render(<StageGlyph stage={stage} />);
      return container.innerHTML.replace(/ui-glyph--stage-\w+/, "").replace(/ui-glyph-\w+/g, "");
    });
    expect(new Set(shapes).size).toBe(STAGE_NAMES.length);
  });
});

describe("ScoreBadge", () => {
  it.each([
    ["A", "strong"],
    ["B", "strong"],
    ["C", "fair"],
    ["D", "weak"],
    ["E", "weak"],
  ])("grade %s is the %s tone", (grade, tone) => {
    const { container } = render(<ScoreBadge score={72} grade={grade} />);
    expect((container.firstChild as HTMLElement).classList.contains(`ui-score--${tone}`)).toBe(
      true,
    );
    expect(screen.getByText(`Grade ${grade}`)).toBeTruthy();
  });

  it("says so in words when there is no score", () => {
    render(<ScoreBadge score={null} grade={null} />);
    expect(screen.getByText("No score")).toBeTruthy();
  });

  it("falls back to the fair tone for a score without a grade", () => {
    const { container } = render(<ScoreBadge score={50} grade={null} />);
    expect((container.firstChild as HTMLElement).classList.contains("ui-score--fair")).toBe(true);
    expect(screen.queryByText(/Grade/)).toBeNull();
  });

  it("can be shown large", () => {
    const { container } = render(<ScoreBadge score={90} grade="A" large />);
    expect((container.firstChild as HTMLElement).classList.contains("ui-score--large")).toBe(true);
  });
});

describe("Avatar", () => {
  it.each([
    ["Ada Lovelace", "AL"],
    ["Madonna", "M"],
    ["  grace   brewster  murray hopper ", "GH"],
    ["", "?"],
  ])("takes the initials of %j", (name, initials) => {
    expect(initialsOf(name)).toBe(initials);
  });

  it("takes turns through the pastel tints by position", () => {
    const { container, rerender } = render(<Avatar name="Ada Lovelace" position={0} />);
    expect((container.firstChild as HTMLElement).dataset.tint).toBe("lime");
    rerender(<Avatar name="Ada Lovelace" position={6} />);
    expect((container.firstChild as HTMLElement).dataset.tint).toBe("lilac");
  });
});
