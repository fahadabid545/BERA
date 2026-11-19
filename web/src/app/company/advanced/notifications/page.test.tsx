import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import NotificationsPage from "./page";

const fetchMock = vi.fn();
const reply = (body: unknown, status = 200) => ({
  ok: status < 400,
  status,
  json: async () => body,
});
const LIST = [
  { kind: "batch_finished", label: "Finished uploads", required: false, enabled: true },
  { kind: "usage_warning", label: "Usage warnings", required: false, enabled: true },
  { kind: "payment_failed", label: "Payment failed", required: true, enabled: true },
];
const patches = () => fetchMock.mock.calls.filter((c) => c[1]?.method === "PATCH");

function serve() {
  let current = LIST;
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (_path: string, init?: RequestInit) => {
    if (init?.method === "PATCH") {
      const { kind, enabled } = JSON.parse(init.body as string);
      current = current.map((row) => (row.kind === kind ? { ...row, enabled } : row));
    }
    return reply({ choices: current });
  });
}

beforeEach(() => vi.stubGlobal("fetch", fetchMock));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("notifications page", () => {
  it("lists every email, with the required ones on and fixed", async () => {
    serve();
    render(<NotificationsPage />);
    const finished = (await screen.findByLabelText("Finished uploads")) as HTMLInputElement;
    expect(finished.checked).toBe(true);
    expect(finished.disabled).toBe(false);
    const payment = screen.getByLabelText("Payment failed") as HTMLInputElement;
    expect(payment.checked).toBe(true);
    expect(payment.disabled).toBe(true);
  });

  it("keeps Save disabled until something changes", async () => {
    serve();
    render(<NotificationsPage />);
    await screen.findByLabelText("Finished uploads");
    expect((screen.getByRole("button", { name: "Save" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("saves only the changes, after a confirmation", async () => {
    serve();
    render(<NotificationsPage />);
    const user = userEvent.setup();
    await user.click(await screen.findByLabelText("Finished uploads"));
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(patches()).toHaveLength(0);
    const dialog = await screen.findByRole("dialog", { name: "Save notifications" });
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    await screen.findByRole("dialog", { name: "Notifications saved" });
    expect(patches()).toHaveLength(1);
    expect(JSON.parse(patches()[0][1].body)).toEqual({ kind: "batch_finished", enabled: false });
    expect((screen.getByLabelText("Finished uploads") as HTMLInputElement).checked).toBe(false);
  });

  it("shows the server's refusal", async () => {
    fetchMock.mockReset();
    fetchMock.mockImplementation(async () =>
      reply({ error: { code: "forbidden", message: "You do not have access." } }, 403),
    );
    render(<NotificationsPage />);
    expect(await screen.findByRole("alert")).toBeTruthy();
  });
});
