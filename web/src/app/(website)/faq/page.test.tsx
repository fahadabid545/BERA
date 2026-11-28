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
  it("shows the approved heading and no helper line", () => {
    const { container } = render(<FaqPage />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("FAQ");
    expect(screen.queryByText("Short answers to common questions.")).toBeNull();
    expect(container.querySelectorAll("p")).toHaveLength(QUESTIONS.length);
  });

  it("opens a question to its answer, and every card has a tint", () => {
    const { container } = render(<FaqPage />);
    const items = container.querySelectorAll("details.faq-item");
    expect(items).toHaveLength(QUESTIONS.length);
    for (const item of items) {
      expect(item.hasAttribute("open")).toBe(false);
      expect(item.getAttribute("data-tint")).toBeTruthy();
    }
    expect(items[0].getAttribute("data-tint")).not.toBe(items[1].getAttribute("data-tint"));
  });

  it("shows the seven approved questions and answers in order, word for word", () => {
    const { container } = render(<FaqPage />);
    const questions = container.querySelectorAll(".faq-item h2");
    expect([...questions].map((item) => item.textContent)).toEqual(
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

  it("ends with the approved line and a Contact button", () => {
    const { container } = render(<FaqPage />);
    expect(container.querySelector(".closing-band h2")?.textContent).toBe("Have another question?");
    expect(screen.getByRole("link", { name: "Contact" }).getAttribute("href")).toBe("/contact");
  });

  it("adds no prices, numbers or dates", () => {
    const { container } = render(<FaqPage />);
    expect(container.textContent).not.toMatch(/\d/);
  });
});
