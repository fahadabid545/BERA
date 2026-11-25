import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AdminDiscountCodes } from "./AdminDiscountCodes";

const fetchMock = vi.fn();
const PLANS = [{ id: 3, name: "Fake Starter", status: "active" }];
const code = (over: object = {}) => ({
  id: 1,
  code: "SAVE20",
  plan_id: null,
  enabled: true,
  known: true,
  percent_off: 20,
  amount_off: null,
  duration: "months",
  months: 3,
  expires_at: "2026-12-31T00:00:00Z",
  max_redemptions: 5,
  times_redeemed: 2,
  first_time_only: false,
  ...over,
});
let codes: object[];

function reply(body: unknown, status = 200) {
  return { ok: status < 400, status, json: async () => body };
}
const writes = () =>
  fetchMock.mock.calls.filter((call) => call[1]?.method && call[1].method !== "GET");

beforeEach(() => {
  codes = [code()];
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (path: string, init?: RequestInit) => {
    if (init?.method && init.method !== "GET")
      return reply({ codes }, init.method === "POST" ? 201 : 200);
    if (path === "/api/admin/plans/") return reply(PLANS);
    return reply({ codes });
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("discount codes", () => {
  it("lists each code with its discount, duration, plan and use count", async () => {
    render(<AdminDiscountCodes />);
    const table = await screen.findByRole("region", { name: "Discount codes" });
    const row = within(table).getByText("SAVE20").closest("tr")!;
    expect(within(row).getByText("20% off")).toBeTruthy();
    expect(within(row).getByText("First 3 months")).toBeTruthy();
    expect(within(row).getByText("All plans")).toBeTruthy();
    expect(within(row).getByText("2 of 5")).toBeTruthy();
    expect(within(row).getByText("On")).toBeTruthy();
  });

  it("shows a fixed amount and an unlimited use count", async () => {
    codes = [
      code({ percent_off: null, amount_off: "10.00", duration: "forever", max_redemptions: null }),
    ];
    render(<AdminDiscountCodes />);
    expect(await screen.findByText("USD 10.00 off")).toBeTruthy();
    expect(screen.getByText("Every payment")).toBeTruthy();
    expect(screen.getByText("2")).toBeTruthy();
  });

  it("still lists a code the provider could not describe", async () => {
    codes = [code({ known: false })];
    render(<AdminDiscountCodes />);
    expect(await screen.findByText("SAVE20")).toBeTruthy();
  });

  it("makes a code with the chosen options", async () => {
    const user = userEvent.setup();
    render(<AdminDiscountCodes />);
    await user.click(await screen.findByRole("button", { name: "New discount code" }));
    const dialog = await screen.findByRole("dialog", { name: "New discount code" });
    await user.type(within(dialog).getByLabelText("Code"), "SPRING");
    await user.type(within(dialog).getByLabelText("Value"), "15");
    await user.selectOptions(within(dialog).getByLabelText("Applies for"), "months");
    await user.type(within(dialog).getByLabelText("Months"), "3");
    await user.type(within(dialog).getByLabelText("Most uses"), "10");
    await user.click(within(dialog).getByLabelText("First-time customers only"));
    await user.selectOptions(within(dialog).getByLabelText("Plan"), "3");
    await user.click(within(dialog).getByRole("button", { name: "Create code" }));
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(JSON.parse(writes()[0][1].body as string)).toEqual({
      code: "SPRING",
      kind: "percent",
      value: "15",
      duration: "months",
      first_time_only: true,
      months: 3,
      max_redemptions: 10,
      plan_id: 3,
    });
  });

  it("switches a code off", async () => {
    const user = userEvent.setup();
    render(<AdminDiscountCodes />);
    await user.click(await screen.findByRole("button", { name: "Switch off SAVE20" }));
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(writes()[0][0]).toBe("/api/admin/discounts/1/");
    expect(JSON.parse(writes()[0][1].body as string)).toEqual({ enabled: false });
  });

  it("limits a code to a plan, or frees it", async () => {
    const user = userEvent.setup();
    render(<AdminDiscountCodes />);
    await user.click(await screen.findByRole("button", { name: "Choose the plan of SAVE20" }));
    const dialog = await screen.findByRole("dialog", { name: "Plan of the code" });
    await user.selectOptions(within(dialog).getByLabelText("Plan"), "3");
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(JSON.parse(writes()[0][1].body as string)).toEqual({ plan_id: 3 });
  });

  it("shows the server's reason when a code is refused", async () => {
    fetchMock.mockImplementation(async (path: string, init?: RequestInit) => {
      if (init?.method && init.method !== "GET")
        return reply(
          {
            error: {
              code: "invalid_discount",
              message: "This code already exists.",
              fields: { code: "This code already exists." },
            },
          },
          400,
        );
      if (path === "/api/admin/plans/") return reply(PLANS);
      return reply({ codes });
    });
    const user = userEvent.setup();
    render(<AdminDiscountCodes />);
    await user.click(await screen.findByRole("button", { name: "New discount code" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Create code" }),
    );
    expect((await screen.findAllByText("This code already exists.")).length).toBeGreaterThan(0);
  });
});
