import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BillingPage from "./page";

vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams("") }));

afterEach(() => vi.unstubAllGlobals());

describe("usage and billing page", () => {
  it("shows the plans to buy", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify([
              {
                id: 1,
                name: "Fake Plan",
                price: { currency: "USD", amount: "10.00", note: null, approximate: false },
                charged: { currency: "USD", amount: "10.00" },
                cvs_per_month: 100,
              },
            ]),
            { status: 200 },
          ),
      ),
    );
    render(<BillingPage />);
    expect(await screen.findByText("USD 10.00 per month")).toBeTruthy();
  });
});
