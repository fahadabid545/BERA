import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AdminPayments } from "./AdminPayments";

const fetchMock = vi.fn();
const item = (id: string, over: object = {}) => ({
  id,
  provider_event_id: `evt_${id}`,
  kind: "payment",
  company_id: 7,
  company: "Fake Company",
  amount: "12.50",
  currency: "USD",
  reason: "",
  at: "2026-02-10T12:00:00+00:00",
  ...over,
});
const OVERVIEW = {
  total: 3,
  page: 1,
  page_size: 50,
  totals: [
    {
      currency: "PKR",
      payments: { count: 1, amount: "700.00" },
      refunds: { count: 0, amount: "0.00" },
      failures: { count: 0 },
    },
    {
      currency: "USD",
      payments: { count: 1, amount: "12.50" },
      refunds: { count: 1, amount: "3.00" },
      failures: { count: 1 },
    },
  ],
  items: [
    item("a"),
    item("b", { kind: "refund", amount: "3.00", at: "2026-01-12T12:00:00+00:00" }),
    item("c", {
      kind: "failure",
      reason: "Card declined",
      company_id: 9,
      company: "Other Company",
    }),
  ],
  companies: [
    { id: 7, name: "Fake Company" },
    { id: 9, name: "Other Company" },
  ],
  currencies: ["PKR", "USD"],
};

function reply(status: number, body: unknown) {
  fetchMock.mockResolvedValueOnce({ ok: status < 400, status, json: async () => body });
}
const rowsOf = (name: string) =>
  Array.from(screen.getByRole("region", { name }).querySelectorAll("tbody tr")).map((row) =>
    Array.from(row.querySelectorAll("th, td")).map((cell) => cell.textContent),
  );
const lastPath = () => String(fetchMock.mock.calls.at(-1)?.[0]);

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Payments overview", () => {
  it("lists payments, refunds and failures with their words, amounts and provider event", async () => {
    reply(200, OVERVIEW);
    render(<AdminPayments />);
    await screen.findByRole("region", { name: "Payments" });
    expect(rowsOf("Payments")).toEqual([
      ["2026-02-10", "Fake Company", "Payment", "12.50 USD", "", "evt_a"],
      ["2026-01-12", "Fake Company", "Refund", "3.00 USD", "", "evt_b"],
      ["2026-02-10", "Other Company", "Failure", "12.50 USD", "Card declined", "evt_c"],
    ]);
  });

  it("links each record to its company", async () => {
    reply(200, OVERVIEW);
    render(<AdminPayments />);
    await screen.findByRole("region", { name: "Payments" });
    expect(screen.getAllByRole("link", { name: "Other Company" })[0].getAttribute("href")).toBe(
      "/admin/companies/9",
    );
  });

  it("shows totals for each currency, never added together", async () => {
    reply(200, OVERVIEW);
    render(<AdminPayments />);
    await screen.findByRole("region", { name: "Totals" });
    expect(rowsOf("Totals")).toEqual([
      ["PKR", "1 (700.00)", "0 (0.00)", "0"],
      ["USD", "1 (12.50)", "1 (3.00)", "1"],
    ]);
  });

  it("asks the server for each filter and starts again from the first page", async () => {
    reply(200, { ...OVERVIEW, total: 120 });
    render(<AdminPayments />);
    await screen.findByRole("region", { name: "Payments" });
    reply(200, { ...OVERVIEW, total: 120, page: 2 });
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(lastPath()).toBe("/api/admin/payments/?page=2"));

    reply(200, OVERVIEW);
    await userEvent.selectOptions(screen.getByLabelText("Type"), "refund");
    await waitFor(() => expect(lastPath()).toBe("/api/admin/payments/?kind=refund"));
    reply(200, OVERVIEW);
    await userEvent.selectOptions(screen.getByLabelText("Company"), "9");
    await waitFor(() => expect(lastPath()).toBe("/api/admin/payments/?kind=refund&company=9"));
    reply(200, OVERVIEW);
    await userEvent.selectOptions(screen.getByLabelText("Currency"), "PKR");
    await waitFor(() => expect(lastPath()).toContain("currency=PKR"));
    reply(200, OVERVIEW);
    await userEvent.type(screen.getByLabelText("From"), "2026-01-01");
    await waitFor(() => expect(lastPath()).toContain("from_date=2026-01-01"));
    reply(200, OVERVIEW);
    await userEvent.type(screen.getByLabelText("To"), "2026-01-31");
    await waitFor(() => expect(lastPath()).toContain("to_date=2026-01-31"));
  });

  it("offers only the companies and currencies that have records", async () => {
    reply(200, OVERVIEW);
    render(<AdminPayments />);
    await screen.findByRole("region", { name: "Payments" });
    const names = (label: string) =>
      Array.from((screen.getByLabelText(label) as HTMLSelectElement).options).map((o) => o.text);
    expect(names("Company")).toEqual(["All companies", "Fake Company", "Other Company"]);
    expect(names("Currency")).toEqual(["All currencies", "PKR", "USD"]);
    expect(names("Type")).toEqual(["All types", "Payment", "Refund", "Failure"]);
  });

  it("pages through the records", async () => {
    reply(200, { ...OVERVIEW, total: 120 });
    render(<AdminPayments />);
    expect(await screen.findByText("Page 1 of 3")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Previous" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
    expect((screen.getByRole("button", { name: "Next" }) as HTMLButtonElement).disabled).toBe(
      false,
    );
  });

  it("shows No payments when there are none", async () => {
    reply(200, { ...OVERVIEW, total: 0, items: [], totals: [] });
    render(<AdminPayments />);
    expect(await screen.findByText("No payments.")).toBeTruthy();
    expect(
      within(screen.getByRole("region", { name: "Totals" })).queryAllByRole("row"),
    ).toHaveLength(1);
  });

  it("shows why the server refused a filter and keeps the list", async () => {
    reply(200, OVERVIEW);
    render(<AdminPayments />);
    await screen.findByRole("region", { name: "Payments" });
    reply(400, {
      error: {
        code: "validation_error",
        message: "Please check the form and try again.",
        fields: { to_date: "This must not be before the start date." },
      },
    });
    await userEvent.type(screen.getByLabelText("To"), "2020-01-01");
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Please check the form and try again.",
    );
    expect(screen.getByRole("region", { name: "Payments" })).toBeTruthy();
  });

  it("shows the server's message when the page cannot load", async () => {
    reply(403, {
      error: { code: "not_allowed", message: "You do not have permission to do this." },
    });
    render(<AdminPayments />);
    expect((await screen.findByRole("alert")).textContent).toBe(
      "You do not have permission to do this.",
    );
  });
});
