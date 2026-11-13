import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import NewProjectPage from "./page";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

describe("new project page", () => {
  it("shows the create-project form", () => {
    render(<NewProjectPage />);
    expect(screen.getByRole("button", { name: "Create project" })).toBeTruthy();
  });
});
