import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EmptyState } from "./EmptyState";

describe("EmptyState", () => {
  it("says the words in a tinted card and keeps what the caller passes", () => {
    render(
      <EmptyState tint="peach" role="status">
        No tickets yet.
      </EmptyState>,
    );
    const note = screen.getByRole("status");
    expect(note.textContent).toBe("No tickets yet.");
    expect(note.getAttribute("data-tint")).toBe("peach");
  });

  it("defaults to a tint, so it is never plain", () => {
    render(<EmptyState>Nothing here</EmptyState>);
    expect(screen.getByText("Nothing here").getAttribute("data-tint")).toBe("sky");
  });
});
