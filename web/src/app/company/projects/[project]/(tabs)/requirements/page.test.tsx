import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ProjectRequirementsPage from "./page";

describe("ProjectRequirementsPage", () => {
  it("shows the suggest button for the project it was opened for", async () => {
    render(await ProjectRequirementsPage({ params: Promise.resolve({ project: "p1" }) }));
    expect(screen.getByRole("button", { name: "Suggest requirements" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Add requirement" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save" })).toBeTruthy();
  });
});
