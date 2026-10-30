import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import AiPlaygroundPage from "./page";

describe("AI playground page", () => {
  it("shows the CV upload, job description, both selectors and Run test", () => {
    render(<AiPlaygroundPage />);
    expect((screen.getByLabelText("CV file") as HTMLInputElement).type).toBe("file");
    expect(screen.getByLabelText("Job description").tagName).toBe("TEXTAREA");
    expect(screen.getByLabelText("Reading model").tagName).toBe("SELECT");
    expect(screen.getByLabelText("Scoring model").tagName).toBe("SELECT");
    expect(screen.getByRole("button", { name: "Run test" })).toBeTruthy();
  });

  it("does nothing when a button is pressed", async () => {
    const { container } = render(<AiPlaygroundPage />);
    const before = container.innerHTML;
    for (const button of screen.getAllByRole("button")) await userEvent.click(button);
    expect(container.innerHTML).toBe(before);
  });
});
