import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RoleProvider } from "@/components/company/role";

import BillingPage from "./page";

vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams("") }));

afterEach(() => vi.unstubAllGlobals());

const PLAN = {
  id: 1,
  name: "Fake Plan",
  price: { currency: "USD", amount: "10.00", note: null, approximate: false },
  charged: { currency: "USD", amount: "10.00" },
  cvs_per_month: 100,
};
const DETAILS = {
  name: "",
  address_line1: "",
  address_line2: "",
  city: "",
  state: "",
  postal_code: "",
  country: "",
  tax_number: "",
  complete: false,
};

describe("usage and billing page", () => {
  it("shows the plans, the billing details and the invoices to the owner", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (path: string) => {
        const body = path.includes("/details/")
          ? DETAILS
          : path.includes("/invoices/")
            ? { invoices: [] }
            : path === "/api/company/usage/"
              ? { state: "no_plan", plan_id: null, pending_change: null, refresh_seconds: 10 }
              : [PLAN];
        return new Response(JSON.stringify(body), { status: 200 });
      }),
    );
    render(
      <RoleProvider value="owner">
        <BillingPage />
      </RoleProvider>,
    );
    expect(await screen.findByText("USD 10.00 per month")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Billing details" })).toBeTruthy();
    expect(await screen.findByText("No invoices yet.")).toBeTruthy();
  });
});
