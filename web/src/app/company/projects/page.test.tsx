import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ProjectsPage from "./page";

describe("projects page", () => {
  it("shows a Search box and a New project button that goes to the New project page", () => {
    const { container } = render(<ProjectsPage />);
    expect((screen.getByLabelText("Search") as HTMLInputElement).type).toBe("search");
    expect(screen.getByRole("link", { name: "New project" }).getAttribute("href")).toBe(
      "/company/projects/new",
    );
    expect(container.querySelectorAll("input, a, button")).toHaveLength(2);
  });
});
