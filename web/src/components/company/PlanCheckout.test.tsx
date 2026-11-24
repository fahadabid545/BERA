import { render, screen, waitFor } from "@testing-library/react";
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

let posts: number;
let checkoutReply: () => Response;

function show(role: "owner" | "member", plans = [PLAN]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        posts += 1;
        return checkoutReply();
      }
      return new Response(JSON.stringify(plans), { status: 200 });
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
