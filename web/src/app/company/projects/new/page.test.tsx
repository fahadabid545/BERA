import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import NewProjectPage from "./page";

describe("new project page", () => {
  it("shows the title field, a large job description box and both buttons", () => {
    render(<NewProjectPage />);
    expect(screen.getByLabelText("Project title")).toBeTruthy();
    const description = screen.getByLabelText("Job description") as HTMLTextAreaElement;
    expect(description.tagName).toBe("TEXTAREA");
    expect(description.rows).toBeGreaterThan(5);
    expect(screen.getByRole("button", { name: "Create project" })).toBeTruthy();
  });

  it("Cancel goes back to the projects list", () => {
    render(<NewProjectPage />);
    expect(screen.getByRole("link", { name: "Cancel" }).getAttribute("href")).toBe(
      "/company/projects",
    );
  });

  it("Create project does nothing, even with empty fields", async () => {
    const { container } = render(<NewProjectPage />);
    await userEvent.click(screen.getByRole("button", { name: "Create project" }));
    expect(container.querySelector("form")).toBeTruthy();
    expect(screen.queryByText(/error/i)).toBeNull();
  });
});
