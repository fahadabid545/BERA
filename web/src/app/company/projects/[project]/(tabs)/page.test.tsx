import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { projectTabs } from "@/components/company/links";
import { TabLinks } from "@/components/ui";

import ProjectOverviewPage from "./page";

let pathname = "/company/projects/p1";
vi.mock("next/navigation", () => ({ usePathname: () => pathname }));

describe("project overview page", () => {
  it("shows the Upload CVs button and nothing else", () => {
    const { container } = render(<ProjectOverviewPage />);
    expect(screen.getByRole("button", { name: "Upload CVs" })).toBeTruthy();
    expect(container.querySelectorAll("button, a, input")).toHaveLength(1);
  });
});

describe("project tabs", () => {
  const current = () =>
    screen.getAllByRole("link").filter((link) => link.getAttribute("aria-current") === "page");

  it("link to five separate addresses", () => {
    render(<TabLinks label="Project" items={projectTabs("p1")} />);
    expect(
      screen.getAllByRole("link").map((link) => [link.textContent, link.getAttribute("href")]),
    ).toEqual([
      ["Overview", "/company/projects/p1"],
      ["Candidates", "/company/projects/p1/candidates"],
      ["Compare", "/company/projects/p1/compare"],
      ["Requirements", "/company/projects/p1/requirements"],
      ["Settings", "/company/projects/p1/settings"],
    ]);
  });

  it.each([
    ["/company/projects/p1", "Overview"],
    ["/company/projects/p1/candidates", "Candidates"],
    ["/company/projects/p1/candidates/c1", "Candidates"],
    ["/company/projects/p1/compare", "Compare"],
    ["/company/projects/p1/requirements", "Requirements"],
    ["/company/projects/p1/settings", "Settings"],
  ])("highlight only the tab for %s", (path, tab) => {
    pathname = path;
    render(<TabLinks label="Project" items={projectTabs("p1")} />);
    expect(current().map((link) => link.textContent)).toEqual([tab]);
  });
});
