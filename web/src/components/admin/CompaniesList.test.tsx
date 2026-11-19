import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CompaniesList } from "./CompaniesList";

const fetchMock = vi.fn();

const ROW = {
  id: "7",
  name: "Fake Alpha Ltd",
  country: "GB",
  status: "active",
  plan_name: "Fake Plan",
  subscription_state: "active",
  cvs_used: 3,
  cvs_limit: 10,
  users: 2,
  created_at: "2026-11-02T10:00:00Z",
};
const PLANS = [{ id: "4", name: "Fake Plan" }];

function page(results: unknown[], pageNumber = 1, pages = 1) {
  return { results, page: pageNumber, pages, total: results.length, plans: PLANS };
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

describe("companies list", () => {
  it("shows each company with its facts and a link to its page", async () => {
    answer(page([ROW]));
    render(<CompaniesList />);
    const link = await screen.findByRole("link", { name: "Fake Alpha Ltd" });
    expect(link.getAttribute("href")).toBe("/admin/companies/7");
    const cells = Array.from(link.closest("tr")!.querySelectorAll("td")).map((cell) =>
      cell.textContent?.trim(),
    );
    expect(cells.slice(1)).toEqual([
      "Active",
      "Fake Plan",
      "Active",
      "GB",
      "3 of 10",
      "2",
      "2 Nov 2026",
    ]);
  });

  it("shows a company with no plan and no limit plainly", async () => {
    answer(
      page([{ ...ROW, plan_name: null, subscription_state: "no_plan", cvs_used: 0, cvs_limit: 0 }]),
    );
    render(<CompaniesList />);
    const link = await screen.findByRole("link", { name: "Fake Alpha Ltd" });
    const cells = Array.from(link.closest("tr")!.querySelectorAll("td")).map((cell) =>
      cell.textContent?.trim(),
    );
    expect(cells.slice(2, 3)).toEqual(["None"]);
    expect(cells[3]).toBe("No plan");
    expect(cells[5]).toBe("0");
  });

  it("says so when nothing matches", async () => {
    answer(page([]));
    render(<CompaniesList />);
    expect(await screen.findByText("No companies found.")).toBeTruthy();
  });

  it("asks the server for each filter and starts again from the first page", async () => {
    answer(page([ROW], 1, 3));
    render(<CompaniesList />);
    await screen.findByRole("link", { name: "Fake Alpha Ltd" });
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(lastUrl()).toContain("page=2"));

    await userEvent.selectOptions(screen.getByLabelText("Status"), "suspended");
    await waitFor(() => expect(lastUrl()).toContain("status=suspended"));
    expect(lastUrl()).toContain("page=1");
    await userEvent.selectOptions(screen.getByLabelText("Plan"), "4");
    await waitFor(() => expect(lastUrl()).toContain("plan=4"));
    await userEvent.selectOptions(screen.getByLabelText("Plan"), "none");
    await waitFor(() => expect(lastUrl()).toContain("plan=none"));
    await userEvent.selectOptions(screen.getByLabelText("Country"), "GB");
    await waitFor(() => expect(lastUrl()).toContain("country=GB"));
    await userEvent.selectOptions(screen.getByLabelText("Usage"), "between");
    await waitFor(() => expect(lastUrl()).toContain("usage=between"));
    await userEvent.type(screen.getByLabelText("Search"), "alpha");
    await waitFor(() => expect(lastUrl()).toContain("search=alpha"));
  });

  it("offers the three usage levels", async () => {
    answer(page([ROW]));
    render(<CompaniesList />);
    await screen.findByRole("link", { name: "Fake Alpha Ltd" });
    const options = Array.from((screen.getByLabelText("Usage") as HTMLSelectElement).options).map(
      (option) => option.text,
    );
    expect(options).toEqual(["Any usage", "Under 80%", "80 to 99%", "100% reached"]);
  });

  it("shows an error from the server", async () => {
    answer({ error: { code: "validation_error", message: "Please check the form." } }, 400);
    render(<CompaniesList />);
    expect((await screen.findByRole("alert")).textContent).toContain("Please check the form.");
  });
});
