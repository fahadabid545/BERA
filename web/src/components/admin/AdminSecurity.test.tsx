import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { AdminSecurity } from "./AdminSecurity";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        items: [
          {
            key: "passwords.min_length",
            group: "passwords",
            kind: "number",
            value: 12,
            default: 12,
            is_default: true,
          },
        ],
        admin_two_step: { required: true, set_up: 3, not_set_up: 1 },
      }),
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows the admin two-step rule as always on, with no switch for it", async () => {
  render(<AdminSecurity />);
  const table = await screen.findByRole("region", { name: "Two-step verification for admins" });
  expect(table.querySelector("tbody")?.textContent).toBe("Required for every admin31");
  expect(screen.queryByRole("checkbox")).toBeNull();
  expect(screen.queryByRole("switch")).toBeNull();
  expect(within(table).queryByRole("button")).toBeNull();
});
