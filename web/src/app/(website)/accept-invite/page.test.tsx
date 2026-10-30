import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AcceptInvitePage from "./page";

const HINTS = {
  rules: [{ id: "min_length", text: "At least 12 characters", met: false }],
  ok: false,
};

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(HINTS), { status: 200 })),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("accept invite page", () => {
  it("shows labelled Your name, Password and Confirm password fields and the Join team button", () => {
    render(<AcceptInvitePage />);
    expect(screen.getByLabelText("Your name")).toBeTruthy();
    expect((screen.getByLabelText("Password") as HTMLInputElement).type).toBe("password");
    expect((screen.getByLabelText("Confirm password") as HTMLInputElement).type).toBe("password");
    expect(screen.getByRole("button", { name: "Join team" })).toBeTruthy();
  });

  it("applies the same password rules while typing: live hints and a live match check", async () => {
    render(<AcceptInvitePage />);
    expect(await screen.findByText("At least 12 characters: not met")).toBeTruthy();
    await userEvent.type(screen.getByLabelText("Password"), "abc");
    await userEvent.type(screen.getByLabelText("Confirm password"), "abd");
    expect(screen.getByRole("status").textContent).toBe("The passwords do not match.");
  });

  it("does nothing when Join team is pressed", async () => {
    render(<AcceptInvitePage />);
    await userEvent.click(screen.getByRole("button", { name: "Join team" }));
    expect(screen.getByRole("button", { name: "Join team" })).toBeTruthy();
  });
});
