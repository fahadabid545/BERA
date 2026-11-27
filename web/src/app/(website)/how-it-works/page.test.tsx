import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import HowItWorksPage from "./page";

const STEPS = ["Create a project", "Upload CVs", "Get scores", "Compare and decide"];

describe("how it works page", () => {
  it("shows the approved heading", () => {
    render(<HowItWorksPage />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("How it works");
  });

  it("shows the four steps in order, numbered by a badge", () => {
    render(<HowItWorksPage />);
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(4);
    items.forEach((item, index) => {
      const title = within(item).getByRole("heading", { level: 3 });
      expect(title.textContent).toBe(`${index + 1}${STEPS[index]}`);
      expect(item.querySelector(".step-badge")?.getAttribute("aria-hidden")).toBe("true");
    });
  });

  it("shows only headings and buttons, with an illustration on every step", () => {
    const { container } = render(<HowItWorksPage />);
    expect(container.querySelectorAll("p")).toHaveLength(0);
    const scenes = container.querySelectorAll(".scene-tile__scene");
    expect(scenes).toHaveLength(4);
    for (const scene of scenes) expect(scene.getAttribute("aria-hidden")).toBe("true");
  });

  it("closes with Get started going to Sign up and See pricing going to Pricing", () => {
    render(<HowItWorksPage />);
    const links = screen.getAllByRole("link");
    expect(links.map((link) => link.textContent)).toEqual(["Get started", "See pricing"]);
    expect(links[0].getAttribute("href")).toBe("/signup");
    expect(links[1].getAttribute("href")).toBe("/pricing");
  });
});
