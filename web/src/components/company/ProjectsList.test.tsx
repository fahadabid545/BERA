import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectsList } from "./ProjectsList";

const fetchMock = vi.fn();

const ROW = {
  id: "11111111-1111-1111-1111-111111111111",
  title: "Backend engineer",
  cv_count: 0,
  best_score: null,
  status: "active",
  updated_at: "2026-11-02T10:00:00Z",
};

function page(results: unknown[], pageNumber = 1, pages = 1) {
  return { results, page: pageNumber, pages, total: results.length, page_size: 20 };
}

function answer(body: unknown, status = 200) {
  fetchMock.mockResolvedValue({ ok: status < 400, status, json: async () => body });
}

const lastUrl = () => String(fetchMock.mock.calls.at(-1)?.[0]);

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("projects list", () => {
  it("shows each project with its columns and a link to it", async () => {
    answer(page([ROW]));
    render(<ProjectsList />);
    const link = await screen.findByRole("link", { name: "Backend engineer" });
    expect(link.getAttribute("href")).toBe(`/company/projects/${ROW.id}`);
    const cells = Array.from(link.closest("tr")!.querySelectorAll("td")).map((cell) =>
      cell.textContent?.trim(),
    );
    expect(cells.slice(1)).toEqual(["0", "None", "Active", "2 Nov 2026"]);
    expect(screen.getAllByRole("columnheader").map((header) => header.textContent)).toEqual([
      "Title",
      "CVs",
      "Best score",
      "Status",
      "Last updated",
    ]);
  });

  it("asks for active projects, newest first, by default", async () => {
    answer(page([ROW]));
    render(<ProjectsList />);
    await screen.findByText("Backend engineer");
    expect(lastUrl()).toBe("/api/company/projects/?sort=updated&status=active&page=1");
  });

  it("keeps the New project button", async () => {
    answer(page([]));
    render(<ProjectsList />);
    expect(screen.getByRole("link", { name: "New project" }).getAttribute("href")).toBe(
      "/company/projects/new",
    );
    await screen.findByText("No projects found.");
  });

  it("searching asks the server and starts again from the first page", async () => {
    answer(page([ROW], 1, 3));
    render(<ProjectsList />);
    await screen.findByText("Page 1 of 3");
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(lastUrl()).toContain("page=2"));
    await userEvent.type(screen.getByLabelText("Search"), "eng");
    await waitFor(() => expect(lastUrl()).toContain("search=eng"));
    expect(lastUrl()).toContain("page=1");
  });

  it("sort and filter choices are sent to the server", async () => {
    answer(page([ROW]));
    render(<ProjectsList />);
    await screen.findByText("Backend engineer");
    await userEvent.selectOptions(screen.getByLabelText("Sort by"), "title");
    await waitFor(() => expect(lastUrl()).toContain("sort=title"));
    await userEvent.selectOptions(screen.getByLabelText("Show"), "archived");
    await waitFor(() => expect(lastUrl()).toContain("status=archived"));
    await userEvent.selectOptions(screen.getByLabelText("Show"), "all");
    await waitFor(() => expect(lastUrl()).toContain("status=all"));
  });

  it("an archived project says so in words", async () => {
    answer(page([{ ...ROW, status: "archived" }]));
    render(<ProjectsList />);
    expect(await screen.findByText("Archived")).toBeTruthy();
  });

  it("shows a score when there is one", async () => {
    answer(page([{ ...ROW, best_score: 87.5, cv_count: 12 }]));
    render(<ProjectsList />);
    expect(await screen.findByText("87.5")).toBeTruthy();
    expect(screen.getByText("12")).toBeTruthy();
  });

  it("paging: Previous is off on the first page and Next on the last", async () => {
    answer(page([ROW], 1, 2));
    render(<ProjectsList />);
    await screen.findByText("Page 1 of 2");
    expect((screen.getByRole("button", { name: "Previous" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
    answer(page([ROW], 2, 2));
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByText("Page 2 of 2");
    expect((screen.getByRole("button", { name: "Next" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("no paging buttons for a single page", async () => {
    answer(page([ROW]));
    render(<ProjectsList />);
    await screen.findByText("Backend engineer");
    expect(screen.queryByRole("button", { name: "Next" })).toBeNull();
  });

  it("says plainly when nothing matches", async () => {
    answer(page([]));
    render(<ProjectsList />);
    expect(await screen.findByText("No projects found.")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("shows a failure in plain words", async () => {
    answer({ error: { code: "internal_error", message: "Something went wrong." } }, 500);
    render(<ProjectsList />);
    expect((await screen.findByRole("alert")).textContent).toBe("Something went wrong.");
  });
});
