import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PlanCheckout, type SalePlan } from "./PlanCheckout";
import { RoleProvider } from "./role";

let query = "";
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(query) }));
const navigateTo = vi.fn();
vi.mock("@/lib/navigation", () => ({ navigateTo: (address: string) => navigateTo(address) }));

const PLAN: SalePlan = {
  id: 7,
  name: "Fake Starter",
  price: { currency: "USD", amount: "10.00", note: null, approximate: false },
  charged: { currency: "USD", amount: "10.00" },
  cvs_per_month: 250,
};
const PAKISTAN: SalePlan = {
  ...PLAN,
  price: {
    currency: "PKR",
    amount: "3000.00",
    note: "Estimate only. You are charged in US dollars.",
    approximate: true,
  },
};

const BIG: SalePlan = {
  ...PLAN,
  id: 8,
  name: "Fake Big",
  price: { currency: "USD", amount: "30.00", note: null, approximate: false },
  charged: { currency: "USD", amount: "30.00" },
};
const NO_PLAN = { state: "no_plan", plan_id: null, pending_change: null, refresh_seconds: 10 };
const ON_STARTER = { ...NO_PLAN, state: "active", plan_id: 7 };
const ON_BIG = { ...NO_PLAN, state: "active", plan_id: 8 };

let posts: number;
let sent: { path: string; body: unknown }[];
let billing: object;
let checkoutReply: () => Response;
let changeReply: () => Response;

function reply(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

function show(role: "owner" | "member", plans = [PLAN]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        posts += 1;
        sent.push({ path, body: JSON.parse(String(init.body)) });
        return path.includes("change-plan") ? changeReply() : checkoutReply();
      }
      if (path === "/api/company/usage/") return reply(billing);
      return reply(plans);
    }),
  );
  return render(
    <RoleProvider value={role}>
      <PlanCheckout />
    </RoleProvider>,
  );
}

beforeEach(() => {
  posts = 0;
  sent = [];
  billing = NO_PLAN;
  changeReply = () => reply({ result: "processing", url: null });
  query = "";
  navigateTo.mockReset();
  checkoutReply = () =>
    new Response(JSON.stringify({ url: "https://pay.example.test/1" }), { status: 200 });
});
afterEach(() => vi.unstubAllGlobals());

describe("buying a plan", () => {
  it("lists the plans with the monthly price", async () => {
    show("owner");
    expect(await screen.findByText("USD 10.00 per month")).toBeTruthy();
  });

  it("shows a Pakistan price as an estimate next to what is charged", async () => {
    show("owner", [PAKISTAN]);
    expect(await screen.findByText("About PKR 3,000.00 per month")).toBeTruthy();
    expect(
      screen.getByText(/Estimate only. You are charged in US dollars. Charged: USD 10.00/),
    ).toBeTruthy();
  });

  it("sends the owner to the payment page after confirming", async () => {
    show("owner");
    await userEvent.click(await screen.findByRole("button", { name: "Choose Fake Starter" }));
    await userEvent.click(screen.getByRole("button", { name: "Continue to payment" }));
    await waitFor(() => expect(navigateTo).toHaveBeenCalledWith("https://pay.example.test/1"));
    expect(posts).toBe(1);
  });

  it("sends nothing when the popup is cancelled", async () => {
    show("owner");
    await userEvent.click(await screen.findByRole("button", { name: "Choose Fake Starter" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(posts).toBe(0);
    expect(navigateTo).not.toHaveBeenCalled();
  });

  it("does not offer buying to a member", async () => {
    show("member");
    await screen.findByText("USD 10.00 per month");
    expect(screen.queryByRole("button", { name: /Choose/ })).toBeNull();
  });

  it("says in plain words when the payment page could not be started", async () => {
    checkoutReply = () =>
      new Response(
        JSON.stringify({
          error: { code: "already_subscribed", message: "Your company already has a plan." },
        }),
        { status: 409 },
      );
    show("owner");
    await userEvent.click(await screen.findByRole("button", { name: "Choose Fake Starter" }));
    await userEvent.click(screen.getByRole("button", { name: "Continue to payment" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Your company already has a plan.");
    expect(navigateTo).not.toHaveBeenCalled();
  });

  it("tells a person who came back from a cancelled payment that nothing was charged", async () => {
    query = "checkout=cancelled";
    show("owner");
    expect((await screen.findByRole("status")).textContent).toBe(
      "Payment cancelled. Nothing was charged.",
    );
  });
});

const waitingDowngrade = {
  kind: "downgrade",
  plan_id: 7,
  plan_name: "Fake Starter",
  takes_effect: "2030-02-15T12:00:00Z",
  processing: false,
};
const processingUpgrade = {
  kind: "upgrade",
  plan_id: 8,
  plan_name: "Fake Big",
  takes_effect: null,
  processing: true,
};

describe("changing plan", () => {
  it("marks the current plan and offers upgrade and downgrade on the others", async () => {
    billing = ON_STARTER;
    show("owner", [PLAN, BIG]);
    await screen.findByRole("button", { name: "Upgrade to Fake Big" });
    expect(screen.getByText("Current plan")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Fake Starter/ })).toBeNull();
    cleanup();
    billing = ON_BIG;
    show("owner", [PLAN, BIG]);
    expect(await screen.findByRole("button", { name: "Downgrade to Fake Starter" })).toBeTruthy();
  });

  it("asks for confirmation and sends the upgrade to the change route, not checkout", async () => {
    billing = ON_STARTER;
    show("owner", [PLAN, BIG]);
    await userEvent.click(await screen.findByRole("button", { name: "Upgrade to Fake Big" }));
    expect(posts).toBe(0);
    await userEvent.click(screen.getByRole("button", { name: "Upgrade" }));
    await waitFor(() => expect(posts).toBe(1));
    expect(sent[0]).toEqual({ path: "/api/company/billing/change-plan/", body: { plan_id: 8 } });
    expect(navigateTo).not.toHaveBeenCalled();
  });

  it("shows an upgrade in processing and does not show the old plan as final", async () => {
    billing = ON_STARTER;
    show("owner", [PLAN, BIG]);
    await userEvent.click(await screen.findByRole("button", { name: "Upgrade to Fake Big" }));
    billing = { ...ON_STARTER, pending_change: processingUpgrade };
    await userEvent.click(screen.getByRole("button", { name: "Upgrade" }));
    expect((await screen.findByRole("status")).textContent).toBe("Upgrade to Fake Big: processing");
    expect(
      (screen.getByRole("button", { name: "Upgrade to Fake Big" }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("checks again while processing and shows the new plan once the payment is confirmed", async () => {
    billing = { ...ON_STARTER, refresh_seconds: 0, pending_change: processingUpgrade };
    show("owner", [PLAN, BIG]);
    await screen.findByText("Upgrade to Fake Big: processing");
    billing = { ...ON_BIG, refresh_seconds: 0 };
    await waitFor(() => expect(screen.queryByRole("status")).toBeNull());
    expect(await screen.findByRole("button", { name: "Downgrade to Fake Starter" })).toBeTruthy();
  });

  it("goes to the provider's page when the bank wants a check", async () => {
    billing = ON_STARTER;
    changeReply = () => reply({ result: "action_required", url: "https://pay.example.test/check" });
    show("owner", [PLAN, BIG]);
    await userEvent.click(await screen.findByRole("button", { name: "Upgrade to Fake Big" }));
    await userEvent.click(screen.getByRole("button", { name: "Upgrade" }));
    await waitFor(() => expect(navigateTo).toHaveBeenCalledWith("https://pay.example.test/check"));
  });

  it("shows a failed card in plain words and keeps the plan as it was", async () => {
    billing = ON_STARTER;
    changeReply = () =>
      reply(
        { error: { code: "payment_declined", message: "Your card could not be charged." } },
        402,
      );
    show("owner", [PLAN, BIG]);
    await userEvent.click(await screen.findByRole("button", { name: "Upgrade to Fake Big" }));
    await userEvent.click(screen.getByRole("button", { name: "Upgrade" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Your card could not be charged.");
    expect(screen.getByText("Current plan")).toBeTruthy();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("shows why a downgrade is blocked", async () => {
    billing = ON_BIG;
    changeReply = () =>
      reply(
        {
          error: {
            code: "downgrade_blocked",
            message:
              "You cannot move to Fake Starter yet. Projects: 4 in use, the plan allows 2 (2 over).",
          },
        },
        409,
      );
    show("owner", [PLAN, BIG]);
    await userEvent.click(await screen.findByRole("button", { name: "Downgrade to Fake Starter" }));
    await userEvent.click(screen.getByRole("button", { name: "Downgrade" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Projects: 4 in use");
  });

  it("shows a waiting downgrade with its date and lets the owner take it back", async () => {
    billing = { ...ON_BIG, pending_change: waitingDowngrade };
    show("owner", [PLAN, BIG]);
    expect((await screen.findByRole("status")).textContent).toBe(
      "Downgrade to Fake Starter on Feb 15, 2030",
    );
    await userEvent.click(screen.getByRole("button", { name: "Cancel downgrade" }));
    expect(posts).toBe(0);
    billing = ON_BIG;
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel downgrade" }));
    await waitFor(() => expect(posts).toBe(1));
    expect(sent[0].path).toBe("/api/company/billing/change-plan/cancel/");
    await waitFor(() => expect(screen.queryByRole("status")).toBeNull());
  });

  it("does not offer changes to a member", async () => {
    billing = ON_BIG;
    show("member", [PLAN, BIG]);
    await screen.findByText("USD 10.00 per month");
    expect(screen.queryByRole("button")).toBeNull();
  });
});
