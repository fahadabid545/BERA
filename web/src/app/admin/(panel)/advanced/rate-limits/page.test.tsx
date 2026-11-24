import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import RateLimitsPage from "./page";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        items: [
          {
            key: "rate_limits.login_per_minute",
            group: "rate_limits",
            kind: "number",
            value: 10,
            default: 10,
            is_default: true,
          },
        ],
      }),
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows the settings of its page", async () => {
  render(<RateLimitsPage />);
  expect(await screen.findByText("Login per minute")).toBeTruthy();
});
