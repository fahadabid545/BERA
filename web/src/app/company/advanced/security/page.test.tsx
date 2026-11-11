import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SecurityPage from "./page";

afterEach(() => vi.unstubAllGlobals());

describe("security page", () => {
  it("offers two-step setup and signing out of all devices", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({ enabled: false, recovery_codes_left: 0, required_by_company: false }),
          ),
      ),
    );
    render(<SecurityPage />);
    expect(
      await screen.findByRole("button", { name: "Set up two-step verification" }),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Sign out of all devices" })).toBeTruthy();
  });
});
