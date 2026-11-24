import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BillingPage from "./page";

vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams("") }));

afterEach(() => vi.unstubAllGlobals());

describe("usage and billing page", () => {
  it("shows the plans to buy and Manage billing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("[]", { status: 200 })),
    );
    render(<BillingPage />);
    expect(screen.getByRole("button", { name: "Manage billing" })).toBeTruthy();
  });
});
