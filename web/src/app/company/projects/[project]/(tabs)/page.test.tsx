import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { projectTabs } from "@/components/company/links";
import { TabLinks } from "@/components/ui";

import ProjectOverviewPage from "./page";

let pathname = "/company/projects/p1";
vi.mock("next/navigation", () => ({ usePathname: () => pathname }));

describe("project overview page", () => {
  it("shows the Upload CVs area for the project it was opened for", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (path: string) => ({
        ok: !path.includes("/charts/"),
        status: path.includes("/charts/") ? 404 : 200,
        json: async () =>
          path.includes("/charts/")
            ? { error: { code: "not_found", message: "Not found." } }
            : {
                allowed_types: ["pdf"],
                max_file_size_mb: 10,
                max_files_per_batch: 30,
                max_files_in_progress: 60,
                files_in_progress: 0,
              },
      })),
    );
    render(await ProjectOverviewPage({ params: Promise.resolve({ project: "p1" }) }));
    expect(screen.getByRole("button", { name: "Upload CVs" })).toBeTruthy();
    await vi.waitFor(() =>
      expect(vi.mocked(fetch).mock.calls.map((call) => call[0])).toContain(
        "/api/company/projects/p1/cvs/",
      ),
    );
    vi.unstubAllGlobals();
  });

  it("shows the project's charts above the upload area", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async () => ({
        ok: false,
        status: 404,
        json: async () => ({ error: { code: "not_found", message: "Not found." } }),
      })),
    );
    render(await ProjectOverviewPage({ params: Promise.resolve({ project: "p1" }) }));
    await vi.waitFor(() =>
      expect(vi.mocked(fetch).mock.calls.map((call) => call[0])).toContain(
        "/api/company/projects/p1/charts/",
      ),
    );
    vi.unstubAllGlobals();
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
