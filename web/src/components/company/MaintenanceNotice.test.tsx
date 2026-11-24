import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NoAccess } from "@/components/panel/NoAccess";

import { MaintenanceNotice } from "./MaintenanceNotice";

function platform(body: unknown, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue({ ok: status < 400, status, json: async () => body });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const INFO = {
  app_name: "Bera",
  support_email: "help@example.test",
  maintenance: { enabled: true, message: "Fake maintenance message" },
};

describe("Maintenance notice", () => {
  it("shows the message while maintenance mode is on", async () => {
    const fetchMock = platform(INFO);
    render(<MaintenanceNotice />);
    expect((await screen.findByRole("status")).textContent).toBe("Fake maintenance message");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/platform/");
  });

  it("shows nothing when it is off or cannot be read", async () => {
    platform({ ...INFO, maintenance: { enabled: false, message: "Fake" } });
    const { container } = render(<MaintenanceNotice />);
    await waitFor(() => expect(container.innerHTML).toBe(""));
    cleanup();
    platform({ error: { code: "x", message: "x" } }, 500);
    const failed = render(<MaintenanceNotice />);
    await waitFor(() => expect(failed.container.innerHTML).toBe(""));
  });
});

describe("You do not have access", () => {
  it("names the support address from the settings", async () => {
    platform(INFO);
    render(<NoAccess />);
    expect(screen.getByRole("heading", { name: "You do not have access" })).toBeTruthy();
    expect(await screen.findByText("Contact help@example.test.")).toBeTruthy();
  });

  it("still says the main thing when the address cannot be loaded", async () => {
    platform({}, 500);
    render(<NoAccess />);
    expect(screen.getByRole("heading", { name: "You do not have access" })).toBeTruthy();
  });
});
