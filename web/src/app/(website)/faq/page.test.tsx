import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import FaqPage from "./page";

const QUESTIONS = [
  [
    "What is Bera?",
    "Bera is a tool that scores and ranks CVs against the requirements of a job opening, so hiring teams can shortlist faster.",
  ],
  ["Which file types can I upload?", "PDF and Word (DOCX) files. You can upload many at once."],
  ["Can I add more CVs later?", "Yes. New CVs join the comparison for that job automatically."],
  [
    "How does the scoring work?",
    "You decide what is a must have and what is nice to have. Bera checks each CV against those points and explains the result.",
  ],
  [
    "Who makes the final decision?",
    "You do. Bera gives a guide, and the recruiter always has the last word.",
  ],
  [
    "Can my team use it?",
    "Yes. You can invite a few colleagues to your account, and each person gets their own login.",
  ],
  [
    "What happens to candidate data?",
    "You choose how long it is kept. After that, it is deleted automatically.",
  ],
];

describe("faq page", () => {
  it("shows the approved heading and subheading", () => {
    render(<FaqPage />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("FAQ");
    expect(screen.getByText("Short answers to common questions.")).toBeTruthy();
  });

  it("shows the seven approved questions and answers in order, word for word", () => {
    render(<FaqPage />);
    expect(screen.getAllByRole("heading", { level: 2 }).map((item) => item.textContent)).toEqual(
      QUESTIONS.map(([question]) => question),
    );
    for (const [question, answer] of QUESTIONS) {
      const card = screen.getByRole("region", { name: question });
      expect(card.querySelector("p")?.textContent).toBe(answer);
    }
  });

  it("leaves out the two answers that are out of date for a live site", () => {
    const { container } = render(<FaqPage />);
    expect(container.textContent).not.toMatch(/How much will it cost|When will Bera be available/);
  });

  it("ends with the approved line linking to the Contact page", () => {
    const { container } = render(<FaqPage />);
    const closing = container.querySelector(":scope > div > p:last-child")!;
    expect(closing.textContent).toBe("Have another question? Our team will be happy to help.");
    expect(
      screen.getByRole("link", { name: "Our team will be happy to help." }).getAttribute("href"),
    ).toBe("/contact");
  });

  it("adds no prices, numbers or dates", () => {
    const { container } = render(<FaqPage />);
    expect(container.textContent).not.toMatch(/\d/);
  });
});
