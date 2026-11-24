import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import AuditLogPage from "./page";

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ items: [], next: null, actions: ["auth.login"] }),
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows the audit log page with its filters and Export", async () => {
  render(<AuditLogPage />);
  expect(await screen.findByRole("button", { name: "Export" })).toBeTruthy();
  expect(screen.getByLabelText("Person")).toBeTruthy();
});
