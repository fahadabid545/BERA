import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CheckoutReturn } from "./CheckoutReturn";

let query = "";
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(query) }));

let replies: Response[];
let sent: unknown[];

beforeEach(() => {
  query = "session_id=cs_test_1";
  sent = [];
  replies = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_path: string, init?: RequestInit) => {
      sent.push(JSON.parse(String(init?.body)));
      return replies.shift() ?? new Response("{}", { status: 500 });
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

const result = (value: string) => new Response(JSON.stringify({ result: value }), { status: 200 });

describe("coming back from the payment page", () => {
  it("asks the server about the payment and says the plan is active", async () => {
    replies = [result("activated")];
    render(<CheckoutReturn />);
    expect((await screen.findByRole("status")).textContent).toBe("Your plan is active.");
    expect(sent).toEqual([{ session_id: "cs_test_1" }]);
  });

  it("says nothing was charged after a cancelled payment", async () => {
    replies = [result("cancelled")];
    render(<CheckoutReturn />);
    expect((await screen.findByRole("status")).textContent).toBe(
      "Payment cancelled. Nothing was charged.",
    );
  });

  it("can check again while the payment is not confirmed", async () => {
    replies = [result("pending"), result("activated")];
    render(<CheckoutReturn />);
    await screen.findByText("Your payment is not confirmed yet.");
    await userEvent.click(screen.getByRole("button", { name: "Check again" }));
    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toBe("Your plan is active."),
    );
  });

  it("shows the server's message when it refuses", async () => {
    replies = [
      new Response(JSON.stringify({ error: { code: "not_found", message: "Not found." } }), {
        status: 404,
      }),
    ];
    render(<CheckoutReturn />);
    expect((await screen.findByRole("alert")).textContent).toBe("Not found.");
    expect(screen.getByRole("link", { name: "Back to billing" })).toBeTruthy();
  });

  it("treats an address without a payment as cancelled and asks nothing", async () => {
    query = "";
    render(<CheckoutReturn />);
    expect((await screen.findByRole("status")).textContent).toBe(
      "Payment cancelled. Nothing was charged.",
    );
    expect(sent).toEqual([]);
  });
});
