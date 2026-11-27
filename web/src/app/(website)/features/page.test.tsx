import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import FeaturesPage from "./page";

const FEATURES = [
  "Job projects",
  "Bulk CV upload",
  "AI scoring",
  "Explanation",
  "Ranked comparison",
  "Filters",
  "Candidate stages",
  "Top candidate reports",
  "Team access",
  "Usage tracking",
  "Data privacy controls",
];
const TRUST = ["You stay in charge", "Every score explained", "Your data, your rules"];

describe("features page", () => {
  it("shows the approved heading", () => {
    render(<FeaturesPage />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Features");
  });

  it("shows all eleven features, in order, as titled cards", () => {
    render(<FeaturesPage />);
    const titles = screen.getAllByRole("heading", { level: 3 }).map((item) => item.textContent);
    expect(titles.slice(0, FEATURES.length)).toEqual(FEATURES);
  });

  it("shows the three trust cards after the features", () => {
    render(<FeaturesPage />);
    const titles = screen.getAllByRole("heading", { level: 3 }).map((item) => item.textContent);
    expect(titles.slice(FEATURES.length)).toEqual(TRUST);
    expect(
      screen.getByRole("heading", { level: 2, name: "Built for a fair first pass" }),
    ).toBeTruthy();
  });

  it("shows only headings and buttons: no descriptive paragraph, only the section label", () => {
    const { container } = render(<FeaturesPage />);
    expect([...container.querySelectorAll("p")].map((item) => item.textContent)).toEqual([
      "Why teams trust it",
    ]);
  });

  it("gives every card an illustration that assistive technology skips", () => {
    const { container } = render(<FeaturesPage />);
    const scenes = container.querySelectorAll(".scene-tile__scene");
    expect(scenes).toHaveLength(FEATURES.length + TRUST.length);
    for (const scene of scenes) expect(scene.getAttribute("aria-hidden")).toBe("true");
  });

  it("has one Get started button going to Sign up", () => {
    render(<FeaturesPage />);
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(1);
    expect(links[0].textContent).toBe("Get started");
    expect(links[0].getAttribute("href")).toBe("/signup");
  });
});
