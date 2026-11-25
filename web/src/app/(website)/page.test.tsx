import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import WebsiteHome from "./page";

describe("website home page", () => {
  it("shows the approved heading and subheading", () => {
    render(<WebsiteHome />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Bera");
    expect(
      screen.getByText(
        "Upload CVs in bulk. Bera scores each one against your job requirements and ranks the best candidates.",
      ),
    ).toBeTruthy();
  });

  it("shows the three approved sections word for word", () => {
    render(<WebsiteHome />);
    const sections = {
      "What Bera is":
        "Bera helps hiring teams get through a pile of CVs without the usual stress. You create a project for a job, upload the CVs, and Bera shows who fits best.",
      "Who it helps":
        "Recruiters, HR teams, small businesses and growing companies. Anyone who reads many applications for one role and wants a clear, fair first pass.",
      "You stay in charge":
        "Bera supports your decision and does not make it. The final call always stays with the recruiter.",
    };
    expect(screen.getAllByRole("heading", { level: 2 }).map((item) => item.textContent)).toEqual(
      Object.keys(sections),
    );
    for (const text of Object.values(sections)) expect(screen.getByText(text)).toBeTruthy();
  });

  it("has Get started going to Sign up and See pricing going to Pricing", () => {
    render(<WebsiteHome />);
    expect(screen.getByRole("link", { name: "Get started" }).getAttribute("href")).toBe("/signup");
    expect(screen.getByRole("link", { name: "See pricing" }).getAttribute("href")).toBe("/pricing");
  });

  it("adds no figures, prices or dates", () => {
    const { container } = render(<WebsiteHome />);
    expect(container.textContent).not.toMatch(/\d/);
  });
});
