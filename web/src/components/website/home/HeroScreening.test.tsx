import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DEMO_PROFILES, STAGE_DWELL_MS } from "./demo";
import { HeroScreening } from "./HeroScreening";

const advance = (ms: number) => act(() => vi.advanceTimersByTime(ms));
const STAGE_COUNT = STAGE_DWELL_MS.length;

// Each stage schedules the next only after React has rendered, so move one stage at a time.
let position = 0;
function steps(count: number) {
  for (let step = 0; step < count; step += 1) {
    advance(STAGE_DWELL_MS[position % STAGE_COUNT]);
    position += 1;
  }
}

function stubReducedMotion(reduced: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: reduced && query.includes("reduce"),
    media: query,
  }));
}

beforeEach(() => {
  position = 0;
  vi.useFakeTimers();
  stubReducedMotion(false);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const text = (container: HTMLElement, selector: string) =>
  container.querySelector(selector)?.textContent;

describe("hero screening", () => {
  it("is decoration for assistive technology", () => {
    const { container } = render(<HeroScreening />);
    expect(container.firstElementChild?.getAttribute("aria-hidden")).toBe("true");
  });

  it("starts with the first candidate, unscored and still New", () => {
    const { container } = render(<HeroScreening />);
    expect(text(container, ".hero-demo__card .hero-demo__person b")).toBe(DEMO_PROFILES[0].name);
    expect(text(container, ".hero-demo__status")).toBe("New");
    expect(text(container, ".hero-demo__ring b")).toBe("0");
    expect(container.querySelector(".hero-demo__sticker")?.getAttribute("data-shown")).toBe(
      "false",
    );
    for (const item of container.querySelectorAll(".hero-demo__requirements li")) {
      expect(item.getAttribute("data-result")).toBe("pending");
    }
  });

  it("ticks the requirements one by one with Met, Partly or Missing", () => {
    const { container } = render(<HeroScreening />);
    const words = () =>
      [...container.querySelectorAll(".hero-demo__requirements em")].map(
        (item) => item.textContent,
      );

    steps(2); // enter, scan, then the first requirement
    expect(words()).toEqual(["Met", "", ""]);
    steps(2);
    expect(words()).toEqual(["Met", "Met", "Partly"]);
  });

  it("scores the candidate and shows the grade sticker", () => {
    const { container } = render(<HeroScreening />);
    steps(5);
    advance(1100); // the count-up
    expect(text(container, ".hero-demo__ring b")).toBe(String(DEMO_PROFILES[0].score));
    expect(container.querySelector(".hero-demo__sticker")?.textContent).toBe("Grade A");
    expect(container.querySelector(".hero-demo__sticker")?.getAttribute("data-shown")).toBe("true");
  });

  it("moves the candidate to the next stage when the cursor presses the action", () => {
    const { container } = render(<HeroScreening />);
    expect(text(container, ".hero-demo__cursor em")).toBe("Shortlist");

    steps(7); // up to and including the click
    expect(container.querySelector(".hero-demo__action")?.getAttribute("data-pressed")).toBe(
      "true",
    );
    expect(text(container, ".hero-demo__status")).toBe("New");

    steps(1);
    expect(text(container, ".hero-demo__status")).toBe("Shortlisted");
    expect(container.querySelector(".hero-demo__status")?.getAttribute("data-decided")).toBe(
      "true",
    );
    expect(text(container, ".hero-demo__sticker--status")).toBe("Shortlisted");
  });

  it("brings in the next candidate, from another field, after one full round", () => {
    const { container } = render(<HeroScreening />);
    steps(STAGE_COUNT);
    expect(text(container, ".hero-demo__card .hero-demo__person b")).toBe(DEMO_PROFILES[1].name);
    expect(text(container, ".hero-demo__status")).toBe("New");

    steps(8);
    expect(text(container, ".hero-demo__status")).toBe("Interviewed");
  });

  it("starts over from the first candidate after the last one", () => {
    const { container } = render(<HeroScreening />);
    steps(STAGE_COUNT * DEMO_PROFILES.length);
    expect(text(container, ".hero-demo__card .hero-demo__person b")).toBe(DEMO_PROFILES[0].name);
  });

  it("shows the next two candidates behind the card", () => {
    const { container } = render(<HeroScreening />);
    const behind = [...container.querySelectorAll(".hero-demo__ghost b")].map(
      (item) => item.textContent,
    );
    expect(behind).toEqual([DEMO_PROFILES[1].name, DEMO_PROFILES[2].name]);
  });

  it("rests on one finished candidate, and never moves on, with reduced motion", () => {
    stubReducedMotion(true);
    const { container } = render(<HeroScreening />);
    act(() => vi.advanceTimersByTime(0));
    expect(text(container, ".hero-demo__status")).toBe("Shortlisted");
    expect(text(container, ".hero-demo__ring b")).toBe(String(DEMO_PROFILES[0].score));

    advance(STAGE_DWELL_MS.reduce((sum, ms) => sum + ms, 0) * 2);
    expect(text(container, ".hero-demo__card .hero-demo__person b")).toBe(DEMO_PROFILES[0].name);
    expect(text(container, ".hero-demo__status")).toBe("Shortlisted");
  });

  it("stops its timers when it leaves the page", () => {
    const { unmount } = render(<HeroScreening />);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
