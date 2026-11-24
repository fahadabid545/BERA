import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AdminMaintenance } from "./AdminMaintenance";

const fetchMock = vi.fn();
const reply = (status: number, body: unknown) =>
  fetchMock.mockResolvedValueOnce({ ok: status < 400, status, json: async () => body });

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Maintenance", () => {
  it("shows whether it is on and the message", async () => {
    reply(200, { enabled: false, message: "Fake message" });
    render(<AdminMaintenance />);
    const table = await screen.findByRole("region", { name: "Maintenance mode" });
    expect(table.querySelector("tbody")?.textContent).toBe("OffFake message");
  });

  it("turns it on with a message and a reason", async () => {
    reply(200, { enabled: false, message: "Fake message" });
    render(<AdminMaintenance />);
    await screen.findByRole("region", { name: "Maintenance mode" });
    await userEvent.click(screen.getByRole("button", { name: "Change" }));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(within(dialog).getByRole("checkbox"));
    await userEvent.type(within(dialog).getByLabelText("Reason"), "Fake reason");
    reply(200, { enabled: true, message: "Fake message" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [path, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect([path, init.method]).toEqual(["/api/admin/settings/maintenance/", "POST"]);
    expect(JSON.parse(String(init.body))).toEqual({
      enabled: true,
      message: "Fake message",
      reason: "Fake reason",
    });
    await waitFor(() =>
      expect(screen.getByRole("region", { name: "Maintenance mode" }).textContent).toContain("On"),
    );
  });

  it("brings the form back with the server's message when the reason is missing", async () => {
    reply(200, { enabled: false, message: "Fake message" });
    render(<AdminMaintenance />);
    await screen.findByRole("region", { name: "Maintenance mode" });
    await userEvent.click(screen.getByRole("button", { name: "Change" }));
    reply(400, {
      error: {
        code: "validation_error",
        message: "Please check the form and try again.",
        fields: { reason: "A written reason is required for this action." },
      },
    });
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Save" }));
    expect(await screen.findByText("A written reason is required for this action.")).toBeTruthy();
  });

  it("shows the server's message when the page cannot load", async () => {
    reply(403, {
      error: { code: "not_allowed", message: "You do not have permission to do this." },
    });
    render(<AdminMaintenance />);
    expect((await screen.findByRole("alert")).textContent).toBe(
      "You do not have permission to do this.",
    );
  });
});
