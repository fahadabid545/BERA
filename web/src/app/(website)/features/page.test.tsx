import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import FeaturesPage from "./page";

const FEATURES = [
  [
    "Job projects",
    "Gives every job opening its own space.",
    "Keeps candidates for different roles neatly apart.",
  ],
  [
    "Bulk CV upload",
    "Lets you add many PDF or Word CVs together.",
    "Saves the time of opening files one by one.",
  ],
  [
    "AI scoring",
    "Checks each CV against what the job needs.",
    "Gives you a fair first pass in minutes.",
  ],
  [
    "Explanation",
    "Shows why a candidate got their score.",
    "You can trust the result and explain it to others.",
  ],
  [
    "Ranked comparison",
    "Puts all candidates side by side, best first.",
    "Makes it easy to spot the strongest people.",
  ],
  [
    "Filters",
    "Narrows the list by score or missing skills.",
    "Helps you find exactly who you are looking for.",
  ],
  [
    "Candidate stages",
    "Lets you mark people as shortlisted, interview, approved or rejected.",
    "Keeps the hiring process organised in one place.",
  ],
  [
    "Top candidate reports",
    "Lets you share or export your best picks.",
    "Makes it simple to update managers and colleagues.",
  ],
  [
    "Team access",
    "Lets you invite colleagues to your account.",
    "Everyone works from the same information.",
  ],
  ["Usage tracking", "Shows how many CVs you have used.", "No surprises with your plan limits."],
  [
    "Data privacy controls",
    "Lets you choose how long candidate data is kept.",
    "Old data is removed when you no longer need it.",
  ],
];

describe("features page", () => {
  it("shows the approved heading", () => {
    render(<FeaturesPage />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Features");
  });

  it("shows all eleven features in order with the approved wording", () => {
    render(<FeaturesPage />);
    const cards = FEATURES.map(([name]) => screen.getByRole("region", { name }));
    expect(screen.getAllByRole("heading", { level: 2 }).map((item) => item.textContent)).toEqual(
      FEATURES.map(([name]) => name),
    );
    cards.forEach((card, index) => {
      const [, does, helps] = FEATURES[index];
      expect([...card.querySelectorAll("p")].map((item) => item.textContent)).toEqual([
        does,
        helps,
      ]);
    });
  });

  it("has one Get started button going to Sign up", () => {
    render(<FeaturesPage />);
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(1);
    expect(links[0].textContent).toBe("Get started");
    expect(links[0].getAttribute("href")).toBe("/signup");
  });
});
