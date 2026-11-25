import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import HowItWorksPage from "./page";

const STEPS = [
  [
    "1. Create a project.",
    "Add a job description, and set what is a must have and what is nice to have.",
  ],
  ["2. Upload CVs.", "Add many PDF or Word files at once. You can add more later."],
  [
    "3. Get scores.",
    "Every candidate receives a score and a short explanation, based on what is in the CV.",
  ],
  [
    "4. Compare and decide.",
    "See everyone ranked on one dashboard, filter the list, and share your top picks.",
  ],
];

describe("how it works page", () => {
  it("shows the approved heading", () => {
    render(<HowItWorksPage />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("How it works");
  });

  it("shows the four approved steps in order, word for word", () => {
    render(<HowItWorksPage />);
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(4);
    items.forEach((item, index) => {
      expect(item.querySelector("h2")?.textContent).toBe(STEPS[index][0]);
      expect(item.querySelector("p")?.textContent).toBe(STEPS[index][1]);
    });
  });

  it("has one Get started button going to Sign up", () => {
    render(<HowItWorksPage />);
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(1);
    expect(links[0].textContent).toBe("Get started");
    expect(links[0].getAttribute("href")).toBe("/signup");
  });
});
