import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChartMark, TipLines } from "./ChartTip";
import { Coverage } from "./Coverage";
import { Funnel } from "./Funnel";
import { Histogram } from "./Histogram";
import { Ranking } from "./Ranking";
import { Trend } from "./Trend";

afterEach(cleanup);

const STEPS = [
  { step: "uploaded", count: 10 },
  { step: "read", count: 8 },
  { step: "scored", count: 4 },
  { step: "shortlisted", count: 2 },
  { step: "interviewed", count: 1 },
  { step: "selected", count: 0 },
];

describe("ChartMark", () => {
  it("is a button when it opens something and only focusable when it does not", async () => {
    const open = vi.fn();
    render(
      <>
        <ChartMark tip="One" onOpen={open}>
          first
        </ChartMark>
        <ChartMark tip="Two">second</ChartMark>
      </>,
    );
    await userEvent.click(screen.getByRole("button", { name: "first" }));
    expect(open).toHaveBeenCalledOnce();
    expect(screen.getByText("second").getAttribute("tabindex")).toBe("0");
    expect(screen.queryByRole("button", { name: "second" })).toBeNull();
  });

  it("shows its details on hover and on keyboard focus", async () => {
    const user = userEvent.setup();
    render(
      <ChartMark tip={<TipLines title="Title" lines={["a fact", "another fact"]} />}>
        mark
      </ChartMark>,
    );
    await user.hover(screen.getByText("mark"));
    const tip = await screen.findByRole("tooltip");
    expect(tip.textContent).toContain("Title");
    expect(tip.textContent).toContain("another fact");
    await user.unhover(screen.getByText("mark"));
    await user.tab();
    expect((await screen.findAllByText("a fact")).length).toBeGreaterThan(0);
  });
});

describe("chart details", () => {
  it("a funnel step says how it compares and opens on click", async () => {
    const open = vi.fn();
    const user = userEvent.setup();
    render(<Funnel steps={STEPS} onOpen={open} />);
    await user.hover(screen.getByRole("button", { name: /Scored/ }));
    const tip = await screen.findByRole("tooltip");
    expect(tip.textContent).toContain("4 in this step");
    expect(tip.textContent).toContain("50% of Read");
    expect(tip.textContent).toContain("40% of all uploaded");
    await user.click(screen.getByRole("button", { name: /Interview/ }));
    expect(open).toHaveBeenCalledWith("interviewed");
  });

  it("a funnel without a click handler is hover-only", () => {
    render(<Funnel steps={STEPS} />);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("a grade column gives its share and opens its candidates", async () => {
    const open = vi.fn();
    const user = userEvent.setup();
    render(
      <Histogram
        grades={[
          { grade: "A", count: 3 },
          { grade: "B", count: 1 },
        ]}
        onOpen={open}
      />,
    );
    await user.hover(screen.getByRole("button", { name: /Grade A/ }));
    expect((await screen.findByRole("tooltip")).textContent).toContain("75% of all scored");
    await user.click(screen.getByRole("button", { name: /Grade B/ }));
    expect(open).toHaveBeenCalledWith("B");
  });

  it("a ranking row gives rank, score and grade; only the top three are filled", async () => {
    const user = userEvent.setup();
    const candidates = [1, 2, 3, 4].map((rank) => ({
      rank,
      candidate_id: `k${rank}`,
      file_name: `f${rank}.pdf`,
      name: `N${rank}`,
      score: String(100 - rank),
      grade: "A",
    }));
    const { container } = render(<Ranking projectId="p" candidates={candidates} />);
    expect(container.querySelectorAll(".chart-ranking__bar--rest")).toHaveLength(1);
    await user.hover(screen.getByText("N2"));
    const tip = await screen.findByRole("tooltip");
    expect(tip.textContent).toContain("Rank 2");
    expect(tip.textContent).toContain("AI score 98");
  });

  it("a coverage part gives its share of those scored, and the requirement links on", async () => {
    const user = userEvent.setup();
    render(
      <Coverage
        candidates={4}
        projectId="p"
        requirements={[
          {
            requirement_id: "r",
            text: "Python",
            kind: "must",
            met: 3,
            partly_met: 1,
            missing: 0,
            not_judged: 0,
          },
        ]}
      />,
    );
    expect(screen.getByRole("link", { name: "Python" }).getAttribute("href")).toBe(
      "/company/projects/p/requirements",
    );
    await user.hover(screen.getByRole("img", { name: "Met 3" }));
    expect((await screen.findByRole("tooltip")).textContent).toContain("75% of those scored");
  });

  it("a trend day gives its figure next to the same day before", async () => {
    const user = userEvent.setup();
    render(
      <Trend
        start="2026-11-01"
        label="CVs uploaded"
        metric={{
          current: [1, 4, 2],
          previous: [3, 3, 3],
          total: 7,
          previous_total: 9,
          change_percent: -22.2,
        }}
      />,
    );
    await user.hover(screen.getByRole("img", { name: /Mon 2 Nov: 4/ }));
    const tip = await screen.findByRole("tooltip");
    expect(tip.textContent).toContain("CVs uploaded: 4");
    expect(tip.textContent).toContain("Same day before: 3");
  });
});
