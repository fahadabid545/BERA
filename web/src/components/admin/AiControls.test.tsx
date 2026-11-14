import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AiControls } from "./AiControls";

const fetchMock = vi.fn();
const RUNNING = {
  paused: false,
  paused_by_admin: false,
  paused_automatically: false,
  resumes_at: null,
  message: "",
};
const PAUSED = {
  ...RUNNING,
  paused: true,
  paused_by_admin: true,
  message: "AI scoring is paused.",
};
const AUTOMATIC = { ...RUNNING, paused: true, paused_automatically: true };

function reply(status: number, body: unknown) {
  fetchMock.mockResolvedValueOnce({ ok: status < 400, status, json: async () => body });
}
const button = (name: string) => screen.getByRole("button", { name }) as HTMLButtonElement;

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function shown(state: object) {
  reply(200, state);
  render(<AiControls />);
  await screen.findByRole("status");
}

describe("AI controls", () => {
  it("says in words whether AI work is running or paused", async () => {
    await shown(RUNNING);
    expect(screen.getByRole("status").textContent).toBe("AI work is running.");
    cleanup();
    await shown(PAUSED);
    expect(screen.getByRole("status").textContent).toBe("AI work is paused by an admin.");
    cleanup();
    await shown(AUTOMATIC);
    expect(screen.getByRole("status").textContent).toBe("AI work is paused automatically.");
  });

  it("while running only Pause is available, with the danger style", async () => {
    await shown(RUNNING);
    expect(button("Pause all AI").disabled).toBe(false);
    expect(button("Pause all AI").className).toContain("ui-button--danger");
    expect(button("Resume AI").disabled).toBe(true);
  });

  it("while paused by an admin only Resume is available", async () => {
    await shown(PAUSED);
    expect(button("Pause all AI").disabled).toBe(true);
    expect(button("Resume AI").disabled).toBe(false);
  });

  it("an automatic pause can be resumed by hand", async () => {
    await shown(AUTOMATIC);
    expect(button("Resume AI").disabled).toBe(false);
  });

  it("pausing asks for a reason in a popup, sends it, and shows the new state", async () => {
    await shown(RUNNING);
    reply(200, PAUSED);
    await userEvent.click(button("Pause all AI"));
    await userEvent.type(screen.getByLabelText("Reason"), "Provider outage");
    const dialog = screen.getByRole("dialog");
    await userEvent.click(
      Array.from(dialog.querySelectorAll("button")).find((b) => b.textContent === "Pause all AI")!,
    );
    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toBe("AI work is paused by an admin."),
    );
    const [path, init] = fetchMock.mock.calls[1];
    expect(path).toBe("/api/admin/ai/controls/pause/");
    expect(JSON.parse(init.body)).toEqual({ reason: "Provider outage" });
  });

  it("resuming sends the reason too", async () => {
    await shown(PAUSED);
    reply(200, RUNNING);
    await userEvent.click(button("Resume AI"));
    await userEvent.type(screen.getByLabelText("Reason"), "Fixed");
    const dialog = screen.getByRole("dialog");
    await userEvent.click(
      Array.from(dialog.querySelectorAll("button")).find((b) => b.textContent === "Resume AI")!,
    );
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("AI work is running."));
    expect(fetchMock.mock.calls[1][0]).toBe("/api/admin/ai/controls/resume/");
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ reason: "Fixed" });
  });

  it("a refused change shows the server's message and keeps the state", async () => {
    await shown(RUNNING);
    reply(400, {
      error: {
        code: "reason_required",
        message: "Write a reason.",
        fields: { reason: "Write a reason." },
      },
    });
    await userEvent.click(button("Pause all AI"));
    const dialog = screen.getByRole("dialog");
    await userEvent.click(
      Array.from(dialog.querySelectorAll("button")).find((b) => b.textContent === "Pause all AI")!,
    );
    expect((await screen.findByRole("alert")).textContent).toBe("Write a reason.");
    expect(screen.getByRole("status").textContent).toBe("AI work is running.");
  });
});
