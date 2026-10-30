import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ProjectComparePage from "./page";

describe("project compare page", () => {
  it("shows a multi-select candidate selector and nothing else", () => {
    const { container } = render(<ProjectComparePage />);
    const selector = screen.getByLabelText("Candidates") as HTMLSelectElement;
    expect(selector.multiple).toBe(true);
    expect(container.querySelectorAll("button, a, input, select, textarea")).toHaveLength(1);
  });
});
