import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import WebsiteHome from "./page";

describe("website home page", () => {
  it("has one heading that reads as a whole sentence, with the rotating words kept for screen readers", () => {
    render(<WebsiteHome />);
    const headings = screen.getAllByRole("heading", { level: 1 });
    expect(headings).toHaveLength(1);
    expect(headings[0].textContent).toContain("Shortlist the right people");
    expect(headings[0].textContent).toContain("faster, fairer, smarter");
  });

  it("shows only headings and buttons as copy: the three section headings and the card titles", () => {
    render(<WebsiteHome />);
    expect(screen.getAllByRole("heading", { level: 2 }).map((item) => item.textContent)).toEqual([
      "Three steps, one afternoon",
      "Everything a first pass needs",
      "Ready to read less and decide better?",
    ]);
    expect(screen.getAllByRole("heading", { level: 3 }).map((item) => item.textContent)).toEqual([
      "1Upload CVs",
      "2Bera scores each one",
      "3You make the call",
      "Every score explained",
      "Compare side by side",
      "Filters that get specific",
      "Shareable reports",
      "Built for teams",
      "Data you control",
    ]);
  });

  it("has no paragraphs of descriptive text, only the two small section labels", () => {
    const { container } = render(<WebsiteHome />);
    const paragraphs = [...container.querySelectorAll("p")].map((item) => item.textContent);
    expect(paragraphs).toEqual(["How it works", "What you get"]);
  });

  it("has Get started going to Sign up and See pricing going to Pricing, in the hero and the closing band", () => {
    render(<WebsiteHome />);
    const started = screen.getAllByRole("link", { name: "Get started" });
    const pricing = screen.getAllByRole("link", { name: "See pricing" });
    expect(started).toHaveLength(2);
    expect(pricing).toHaveLength(2);
    for (const link of started) expect(link.getAttribute("href")).toBe("/signup");
    for (const link of pricing) expect(link.getAttribute("href")).toBe("/pricing");
  });

  it("gives every card an illustration that assistive technology skips", () => {
    const { container } = render(<WebsiteHome />);
    const scenes = container.querySelectorAll(".scene-tile__scene");
    expect(scenes).toHaveLength(9);
    for (const scene of scenes) expect(scene.getAttribute("aria-hidden")).toBe("true");
  });

  it("scrolls the role strip and the live screening without exposing them as content", () => {
    const { container } = render(<WebsiteHome />);
    expect(container.querySelector(".role-strip")?.getAttribute("aria-hidden")).toBe("true");
    expect(container.querySelector(".hero-demo")?.getAttribute("aria-hidden")).toBe("true");
    expect(within(container).queryByRole("list", { name: /sales/i })).toBeNull();
  });

  it("marks one phrase of each section heading, as a highlight and not as green text", () => {
    const { container } = render(<WebsiteHome />);
    const marked = [...container.querySelectorAll(".section-heading .marker")].map(
      (item) => item.textContent,
    );
    expect(marked).toEqual(["one afternoon", "first pass", "decide better?"]);
  });
});
