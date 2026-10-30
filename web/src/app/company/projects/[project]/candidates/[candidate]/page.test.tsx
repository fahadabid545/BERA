import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import CandidatePage from "./page";

describe("candidate page", () => {
  it("shows the Download CV button, the Stage selector and the Notes box", () => {
    render(<CandidatePage />);
    expect(screen.getByRole("button", { name: "Download CV" })).toBeTruthy();
    expect(screen.getByLabelText("Notes").tagName).toBe("TEXTAREA");
    const stage = screen.getByLabelText("Stage") as HTMLSelectElement;
    expect(Array.from(stage.options).map((option) => option.text)).toEqual([
      "New",
      "Shortlisted",
      "Interview",
      "Approved",
      "Rejected",
    ]);
  });

  it("starts at New, lets the stage change, and Download CV does nothing", async () => {
    render(<CandidatePage />);
    const stage = screen.getByLabelText("Stage") as HTMLSelectElement;
    expect(stage.value).toBe("New");
    await userEvent.selectOptions(stage, "Interview");
    expect(stage.value).toBe("Interview");
    await userEvent.click(screen.getByRole("button", { name: "Download CV" }));
  });

  it("shows nothing else", () => {
    const { container } = render(<CandidatePage />);
    expect(container.querySelectorAll("button, select, textarea")).toHaveLength(3);
    expect(screen.queryByRole("heading")).toBeNull();
  });
});
