import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PlanCheckout, type SalePlan } from "./PlanCheckout";
import { RoleProvider } from "./role";

vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams("") }));
const navigateTo = vi.fn();
vi.mock("@/lib/navigation", () => ({ navigateTo: (address: string) => navigateTo(address) }));

const PLAN: SalePlan = {
  id: 7,
  name: "Fake Starter",
  price: { currency: "USD", amount: "10.00", note: null, approximate: false },
  charged: { currency: "USD", amount: "10.00" },
  cvs_per_month: 250,
};
const NO_PLAN = {
  state: "no_plan",
  plan_id: null,
  renewal: false,
  can_manage_billing: false,
  period_end: null,
  grace_ends_at: null,
  pending_change: null,
  trial: null,
  refresh_seconds: 10,
};
const NOT_USABLE = { error: { code: "code_not_usable", message: "This code cannot be used." } };
const CHECK = "/api/company/billing/code/";

let billing: object;
let sent: { path: string; body: Record<string, unknown> }[];
let answers: Record<string, { status: number; body: unknown }>;

function reply(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

function show(role: "owner" | "member" = "owner") {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        const body = JSON.parse(String(init.body));
        sent.push({ path, body });
        const key = path === CHECK && body.plan_id ? `${path}#plan` : path;
        const answer = answers[key] ?? { status: 200, body: {} };
        return reply(answer.body, answer.status);
      }
      if (path === "/api/company/usage/") return reply(billing);
      if (path === "/api/company/billing/card/") return reply({ card: null });
      return reply([PLAN]);
    }),
  );
  return render(
    <RoleProvider value={role}>
      <PlanCheckout />
    </RoleProvider>,
  );
}

beforeEach(() => {
  billing = NO_PLAN;
  sent = [];
  answers = {};
  navigateTo.mockReset();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function typeCode(user: ReturnType<typeof userEvent.setup>, code: string) {
  await user.type(await screen.findByLabelText("Have a code?"), code);
  await user.click(screen.getByRole("button", { name: "Apply code" }));
}

describe("the code field", () => {
  it("is for the owner of a company that has no plan", async () => {
    show("owner");
    expect(await screen.findByLabelText("Have a code?")).toBeTruthy();
  });

  it("is not shown to a member", async () => {
    show("member");
    await screen.findByRole("region", { name: "Fake Starter" });
    expect(screen.queryByLabelText("Have a code?")).toBeNull();
  });

  it("is not shown to a company that already has a plan", async () => {
    billing = { ...NO_PLAN, state: "active", plan_id: 7, renewal: true };
    show("owner");
    await screen.findByText(/Current plan/);
    expect(screen.queryByLabelText("Have a code?")).toBeNull();
  });
});

describe("a discount code", () => {
  beforeEach(() => {
    answers[CHECK] = { status: 200, body: { kind: "coupon" } };
    answers[`${CHECK}#plan`] = {
      status: 200,
      body: {
        kind: "coupon",
        currency: "USD",
        price: "10.00",
        discount: "2.00",
        new_price: "8.00",
        duration: "months",
        months: 3,
      },
    };
    answers["/api/company/billing/checkout/"] = {
      status: 200,
      body: { url: "https://pay.example.test/1" },
    };
  });

  it("is kept, shown before paying with price, discount and new price, and sent to checkout", async () => {
    const user = userEvent.setup();
    show();
    await typeCode(user, "SAVE20");
    expect(await screen.findByText("Code applied: SAVE20")).toBeTruthy();
    expect(sent[0]).toEqual({ path: CHECK, body: { code: "SAVE20" } });
    await user.click(await screen.findByRole("button", { name: "Choose Fake Starter" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("USD 8.00 per month")).toBeTruthy();
    expect(within(dialog).getByText("USD 2.00 off, first 3 months")).toBeTruthy();
    expect(within(dialog).getByText("USD 10.00 per month", { selector: "dd" })).toBeTruthy();
    await user.click(within(dialog).getByRole("button", { name: "Continue to payment" }));
    await waitFor(() => expect(navigateTo).toHaveBeenCalledWith("https://pay.example.test/1"));
    const checkout = sent.find((call) => call.path === "/api/company/billing/checkout/");
    expect(checkout?.body).toEqual({ plan_id: 7, code: "SAVE20" });
  });

  it("can be removed, and then checkout is sent without it", async () => {
    const user = userEvent.setup();
    show();
    await typeCode(user, "SAVE20");
    await user.click(await screen.findByRole("button", { name: "Remove code" }));
    expect(screen.queryByText("Code applied: SAVE20")).toBeNull();
    await user.click(await screen.findByRole("button", { name: "Choose Fake Starter" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", {
        name: "Continue to payment",
      }),
    );
    await waitFor(() => expect(navigateTo).toHaveBeenCalled());
    const checkout = sent.find((call) => call.path === "/api/company/billing/checkout/");
    expect(checkout?.body).toEqual({ plan_id: 7 });
  });

  it("shows the one plain message for a code that cannot be used", async () => {
    answers[CHECK] = { status: 400, body: NOT_USABLE };
    const user = userEvent.setup();
    show();
    await typeCode(user, "WRONG");
    expect(await screen.findByText("This code cannot be used.")).toBeTruthy();
    expect(screen.queryByText(/Code applied/)).toBeNull();
  });

  it("shows the same message in the plan popup when the code does not fit that plan", async () => {
    answers[`${CHECK}#plan`] = { status: 400, body: NOT_USABLE };
    const user = userEvent.setup();
    show();
    await typeCode(user, "SAVE20");
    await user.click(await screen.findByRole("button", { name: "Choose Fake Starter" }));
    expect(
      await within(await screen.findByRole("dialog")).findByText("This code cannot be used."),
    ).toBeTruthy();
  });
});

describe("a trial code", () => {
  beforeEach(() => {
    answers[CHECK] = {
      status: 200,
      body: { kind: "trial", plan: "Fake Starter", days: 14, cv_limit: 50 },
    };
    answers["/api/company/billing/trial/redeem/"] = {
      status: 200,
      body: { ends_at: "2026-12-10T00:00:00Z", cv_limit: 50, cvs_used: 0 },
    };
  });

  it("asks for a confirmation, shows what the trial is, and starts it only when confirmed", async () => {
    const user = userEvent.setup();
    show();
    await typeCode(user, "TRIAL-ABCD-EFGH-JKLM");
    const dialog = await screen.findByRole("dialog", { name: "Start free trial" });
    expect(within(dialog).getByText("Fake Starter plan, 14 days, up to 50 CVs")).toBeTruthy();
    expect(sent.some((call) => call.path.includes("redeem"))).toBe(false);
    await user.click(within(dialog).getByRole("button", { name: "Start trial" }));
    await waitFor(() =>
      expect(sent.find((call) => call.path.includes("redeem"))?.body).toEqual({
        code: "TRIAL-ABCD-EFGH-JKLM",
      }),
    );
  });

  it("starts nothing when the popup is closed", async () => {
    const user = userEvent.setup();
    show();
    await typeCode(user, "TRIAL-ABCD-EFGH-JKLM");
    const dialog = await screen.findByRole("dialog", { name: "Start free trial" });
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(sent.some((call) => call.path.includes("redeem"))).toBe(false);
  });

  it("shows the plain message when the trial cannot start", async () => {
    answers["/api/company/billing/trial/redeem/"] = {
      status: 409,
      body: {
        error: { code: "trial_used", message: "A free trial is not available for your company." },
      },
    };
    const user = userEvent.setup();
    show();
    await typeCode(user, "TRIAL-ABCD-EFGH-JKLM");
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Start trial" }),
    );
    expect(await screen.findByText("A free trial is not available for your company.")).toBeTruthy();
  });
});

describe("a running trial", () => {
  beforeEach(() => {
    billing = {
      ...NO_PLAN,
      state: "granted_free",
      plan_id: 7,
      trial: { ends_at: "2026-12-10T00:00:00Z", cv_limit: 50, cvs_used: 12 },
    };
  });

  it("shows the days and the CVs used, and lets the owner buy a plan at once", async () => {
    show();
    expect(
      await screen.findByText("Free trial until Dec 10, 2026. 12 of 50 CVs used"),
    ).toBeTruthy();
    expect(await screen.findByRole("button", { name: "Choose Fake Starter" })).toBeTruthy();
    expect(screen.getByLabelText("Have a code?")).toBeTruthy();
  });
});
