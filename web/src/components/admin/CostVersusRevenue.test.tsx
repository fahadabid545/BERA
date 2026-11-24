import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CostVersusRevenue } from "./CostVersusRevenue";

const fetchMock = vi.fn();

const ROW = {
  id: "7",
  name: "Fake Alpha Ltd",
  country: "US",
  subscription_state: "active",
  paid_usd: "100.00",
  ai_cost: "15.000000",
  margin_percent: 85,
  flagged: false,
};
const OVERALL = {
  paid_usd: "100.00",
  ai_cost: "15.000000",
  margin_percent: 85,
  flagged: false,
  companies_counted: 1,
  all_ai_cost: "15.000000",
};
const REPORT = {
  days: 30,
  pkr_per_usd: null as string | null,
  overall: OVERALL,
  results: [ROW],
  page: 1,
  pages: 1,
};

function answer(body: unknown, status = 200) {
  fetchMock.mockResolvedValue({ ok: status < 400, status, json: async () => body });
}
const cellsOf = (table: HTMLElement) =>
  Array.from(table.querySelectorAll("tbody tr:first-child td")).map((cell) =>
    cell.textContent?.trim(),
  );

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("cost versus revenue", () => {
  it("shows each company's amount, cost and margin, and the overall figures", async () => {
    answer(REPORT);
    render(<CostVersusRevenue />);
    const companies = await screen.findByRole("region", { name: "Companies" });
    expect(cellsOf(companies)).toEqual(["Fake Alpha Ltd", "Active", "$100.00", "$15.00", "85%"]);
    const overall = screen.getByRole("region", { name: "Overall" });
    expect(cellsOf(overall).slice(0, 5)).toEqual(["Last 30 days", "$15.00", "$100.00", "85%", "1"]);
    expect(cellsOf(overall)[5]).toContain("Not set");
  });

  it("marks a margin under the warning level with a warning tag", async () => {
    answer({
      ...REPORT,
      results: [
        { ...ROW, margin_percent: 19, flagged: true },
        { ...ROW, id: "8", name: "Fake Two" },
      ],
      overall: { ...OVERALL, margin_percent: 10, flagged: true },
    });
    render(<CostVersusRevenue />);
    const companies = await screen.findByRole("region", { name: "Companies" });
    const tag = within(companies).getByText("19%");
    expect(tag.className).toContain("ui-tag--warning");
    expect(within(companies).getByText("85%").className).not.toContain("ui-tag");
    expect(
      within(screen.getByRole("region", { name: "Overall" })).getByText("10%").className,
    ).toContain("ui-tag--warning");
  });

  it("shows a company that has received nothing as zero with no margin", async () => {
    answer({
      ...REPORT,
      results: [{ ...ROW, name: "Fake Bare", paid_usd: "0.00", margin_percent: null }],
    });
    render(<CostVersusRevenue />);
    const companies = await screen.findByRole("region", { name: "Companies" });
    const bare = within(companies).getByText("Fake Bare").closest("tr")!;
    expect(bare.textContent).toContain("$0.00");
    expect(bare.textContent).toContain("None");
  });

  it("says so when there are no companies", async () => {
    answer({ ...REPORT, results: [] });
    render(<CostVersusRevenue />);
    expect(await screen.findByText("No companies found.")).toBeTruthy();
  });

  it("pages through the companies", async () => {
    answer({ ...REPORT, pages: 3 });
    render(<CostVersusRevenue />);
    await screen.findByRole("region", { name: "Companies" });
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(String(fetchMock.mock.calls.at(-1)?.[0])).toContain("page=2"));
  });

  it("sets the rate in a popup with a reason and reloads the figures", async () => {
    answer(REPORT);
    render(<CostVersusRevenue />);
    await screen.findByRole("region", { name: "Companies" });
    await userEvent.click(screen.getByRole("button", { name: "Set rate" }));
    await userEvent.type(screen.getByLabelText("Rate"), "281.5");
    await userEvent.type(screen.getByLabelText("Reason"), "Fake bank rate");
    answer({ ...REPORT, pkr_per_usd: "281.5" });
    const dialog = screen.getByRole("dialog");
    await userEvent.click(
      Array.from(dialog.querySelectorAll("button")).find((b) => b.textContent === "Save rate")!,
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const put = fetchMock.mock.calls.find((call) => call[1]?.method === "PUT")!;
    expect(put[0]).toBe("/api/admin/cost-versus-revenue/rate/");
    expect(JSON.parse(put[1].body)).toEqual({ pkr_per_usd: "281.5", reason: "Fake bank rate" });
    expect(
      within(screen.getByRole("region", { name: "Overall" })).getByText(/281\.5/),
    ).toBeTruthy();
  });

  it("clearing the rate sends none", async () => {
    answer({ ...REPORT, pkr_per_usd: "280" });
    render(<CostVersusRevenue />);
    await screen.findByRole("region", { name: "Companies" });
    await userEvent.click(screen.getByRole("button", { name: "Set rate" }));
    await userEvent.clear(screen.getByLabelText("Rate"));
    await userEvent.type(screen.getByLabelText("Reason"), "Fake");
    await userEvent.click(
      Array.from(screen.getByRole("dialog").querySelectorAll("button")).find(
        (b) => b.textContent === "Save rate",
      )!,
    );
    await waitFor(() =>
      expect(fetchMock.mock.calls.some((call) => call[1]?.method === "PUT")).toBe(true),
    );
    const put = fetchMock.mock.calls.find((call) => call[1]?.method === "PUT")!;
    expect(JSON.parse(put[1].body).pkr_per_usd).toBeNull();
  });

  it("shows an error from saving the rate and shows it on the page", async () => {
    answer(REPORT);
    render(<CostVersusRevenue />);
    await screen.findByRole("region", { name: "Companies" });
    await userEvent.click(screen.getByRole("button", { name: "Set rate" }));
    answer({ error: { code: "validation_error", message: "Please check the form." } }, 400);
    await userEvent.click(
      Array.from(screen.getByRole("dialog").querySelectorAll("button")).find(
        (b) => b.textContent === "Save rate",
      )!,
    );
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("Please check the form.");
  });

  it("shows an error when the figures cannot be opened", async () => {
    answer({ error: { code: "forbidden", message: "You do not have access." } }, 403);
    render(<CostVersusRevenue />);
    expect((await screen.findByRole("alert")).textContent).toBe("You do not have access.");
  });
});
