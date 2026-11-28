import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectsList } from "./ProjectsList";

const fetchMock = vi.fn();

const ROW = {
  id: "11111111-1111-1111-1111-111111111111",
  title: "Backend engineer",
  created_by: "Fake Owner",
  created_at: "2026-10-20T08:00:00Z",
  cv_count: 0,
  cv_capacity: 50,
  best_score: null,
  status: "active",
  labels: [] as string[],
  updated_at: "2026-11-02T10:00:00Z",
};

function page(results: unknown[], pageNumber = 1, pages = 1) {
  return { results, page: pageNumber, pages, total: results.length, page_size: 20, labels: [] };
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

describe("project labels", () => {
  it("shows a card's labels", async () => {
    answer(page([{ ...ROW, labels: ["Sales", "Remote"] }]));
    render(<ProjectsList />);
    const labels = await screen.findByRole("list", { name: "Labels" });
    expect(
      within(labels)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual(["Sales", "Remote"]);
  });

  it("offers a label filter only when the company has labels", async () => {
    answer(page([ROW]));
    render(<ProjectsList />);
    await screen.findByRole("region", { name: "Backend engineer" });
    expect(screen.queryByLabelText("Label")).toBeNull();
  });

  it("asks the server for the chosen label, from the first page", async () => {
    answer({ ...page([ROW]), labels: ["Sales"] });
    render(<ProjectsList />);
    await userEvent.selectOptions(await screen.findByLabelText("Label"), "Sales");
    await waitFor(() => expect(lastUrl()).toContain("label=Sales"));
    expect(lastUrl()).toContain("page=1");
  });
});

describe("projects list", () => {
  it("shows each project as a card with who made it, when and how full it is", async () => {
    answer(page([{ ...ROW, cv_count: 12 }]));
    render(<ProjectsList />);
    const card = await screen.findByRole("region", { name: "Backend engineer" });
    expect(within(card).getByRole("heading", { name: "Backend engineer" })).toBeTruthy();
    expect(within(card).getByText("Fake Owner")).toBeTruthy();
    expect(within(card).getByText("20 Oct 2026")).toBeTruthy();
    expect(within(card).getByText("12 of 50")).toBeTruthy();
    const meter = within(card).getByRole("meter", { name: "CVs in Backend engineer" });
    expect(meter.getAttribute("aria-valuenow")).toBe("12");
    expect(meter.getAttribute("aria-valuemax")).toBe("50");
    expect(within(card).getByRole("link", { name: "View more" }).getAttribute("href")).toBe(
      `/company/projects/${ROW.id}`,
    );
    expect(within(card).getByRole("link", { name: "Compare" }).getAttribute("href")).toBe(
      `/company/projects/${ROW.id}/compare`,
    );
  });

  it("says Full when a project holds as many CVs as it can", async () => {
    answer(page([{ ...ROW, cv_count: 50 }]));
    render(<ProjectsList />);
    expect(await screen.findByText("Full")).toBeTruthy();
  });

  it("shows only the count, with no meter, when the plan allows no CVs", async () => {
    answer(page([{ ...ROW, cv_capacity: 0, cv_count: 3 }]));
    render(<ProjectsList />);
    const card = await screen.findByRole("region", { name: "Backend engineer" });
    expect(within(card).queryByRole("meter")).toBeNull();
    expect(within(card).getByText("3")).toBeTruthy();
  });

  it("asks for active projects, newest first, by default", async () => {
    answer(page([ROW]));
    render(<ProjectsList />);
    await screen.findByText("Backend engineer");
    expect(lastUrl()).toBe("/api/company/projects/?sort=updated&status=active&page=1");
  });

  it("tints each project card in turn and the empty note", async () => {
    answer(
      page([ROW, { ...ROW, id: "22222222-2222-2222-2222-222222222222", title: "Second role" }]),
    );
    const { container, unmount } = render(<ProjectsList />);
    await screen.findByText("Second role");
    const tints = [...container.querySelectorAll(".project-card")].map((card) =>
      card.getAttribute("data-tint"),
    );
    expect(tints[0]).toBeTruthy();
    expect(tints[0]).not.toBe(tints[1]);
    unmount();
    answer(page([]));
    render(<ProjectsList />);
    expect((await screen.findByText("No projects found.")).getAttribute("data-tint")).toBeTruthy();
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
    expect(screen.getByText("12 of 50")).toBeTruthy();
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
