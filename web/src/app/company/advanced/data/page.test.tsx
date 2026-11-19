import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import DataPage from "./page";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ name: "Acme", subscription: { active: false } }),
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("data and export page", () => {
  it("shows Export data and Delete company", () => {
    render(<DataPage />);
    expect(screen.getByRole("button", { name: "Export data" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Delete company" })).toBeTruthy();
  });

  it("gives Delete company the danger style", () => {
    render(<DataPage />);
    expect(screen.getByRole("button", { name: "Delete company" }).className).toContain(
      "ui-button--danger",
    );
  });
});
