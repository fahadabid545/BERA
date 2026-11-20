import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AiSpendAlerts } from "./AiSpendAlerts";

const fetchMock = vi.fn();
const LIMITS = {
  daily_limit: "50.0",
  monthly_limit: null as string | null,
  spent_today: "12.500000",
  spent_this_month: "80.00",
};

function reply(status: number, body: unknown) {
  fetchMock.mockResolvedValueOnce({ ok: status < 400, status, json: async () => body });
}
const saveButton = () =>
  Array.from(screen.getByRole("dialog").querySelectorAll("button")).find(
    (b) => b.textContent === "Save limits",
  )!;

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AI spend alerts", () => {
  it("shows what was spent against each limit, and Not set when there is none", async () => {
    reply(200, LIMITS);
    render(<AiSpendAlerts />);
    const table = await screen.findByRole("region", { name: "Spend alerts" });
    const rows = Array.from(table.querySelectorAll("tbody tr")).map((row) =>
      Array.from(row.querySelectorAll("td")).map((cell) => cell.textContent),
    );
    expect(rows).toEqual([
      ["Today", "$12.50", "$50.00"],
      ["This month", "$80.00", "Not set"],
    ]);
  });

  it("saves both limits with a reason in a popup and shows the new figures", async () => {
    reply(200, LIMITS);
    render(<AiSpendAlerts />);
    await screen.findByRole("region", { name: "Spend alerts" });
    await userEvent.click(screen.getByRole("button", { name: "Set alert limits" }));
    expect((screen.getByLabelText("Daily limit (USD)") as HTMLInputElement).value).toBe("50.0");
    await userEvent.type(screen.getByLabelText("Monthly limit (USD)"), "900");
    await userEvent.type(screen.getByLabelText("Reason"), "Budget agreed");
    reply(200, { ...LIMITS, monthly_limit: "900.0" });
    await userEvent.click(saveButton());
    await waitFor(() =>
      expect(
        within(screen.getByRole("region", { name: "Spend alerts" })).getByText("$900.00"),
      ).toBeTruthy(),
    );
    const [path, init] = fetchMock.mock.calls[1];
    expect(path).toBe("/api/admin/ai/controls/spend-alerts/");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body)).toEqual({
      daily_limit: "50.0",
      monthly_limit: "900",
      reason: "Budget agreed",
    });
  });

  it("an empty limit is sent as none, which turns that alert off", async () => {
    reply(200, LIMITS);
    render(<AiSpendAlerts />);
    await screen.findByRole("region", { name: "Spend alerts" });
    await userEvent.click(screen.getByRole("button", { name: "Set alert limits" }));
    await userEvent.clear(screen.getByLabelText("Daily limit (USD)"));
    await userEvent.type(screen.getByLabelText("Reason"), "Not needed");
    reply(200, { ...LIMITS, daily_limit: null });
    await userEvent.click(saveButton());
    await waitFor(() => expect(fetchMock.mock.calls.length).toBe(2));
    expect(JSON.parse(fetchMock.mock.calls[1][1].body).daily_limit).toBeNull();
  });

  it("a refused save shows the server's message on the page and keeps the old limits", async () => {
    reply(200, LIMITS);
    render(<AiSpendAlerts />);
    await screen.findByRole("region", { name: "Spend alerts" });
    await userEvent.click(screen.getByRole("button", { name: "Set alert limits" }));
    reply(400, { error: { code: "validation_error", message: "Please check the form." } });
    await userEvent.click(saveButton());
    expect((await screen.findByRole("alert")).textContent).toBe("Please check the form.");
    expect(screen.getByText("$50.00")).toBeTruthy();
  });

  it("shows an error when the limits cannot be opened", async () => {
    reply(403, { error: { code: "forbidden", message: "You do not have access." } });
    render(<AiSpendAlerts />);
    expect((await screen.findByRole("alert")).textContent).toBe("You do not have access.");
  });
});
