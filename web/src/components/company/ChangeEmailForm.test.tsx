import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChangeEmailForm } from "./ChangeEmailForm";

const fetchMock = vi.fn();
const reply = (body: unknown, status = 200) => ({
  ok: status < 400,
  status,
  json: async () => body,
});

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function fill() {
  const user = userEvent.setup();
  render(<ChangeEmailForm />);
  await user.type(screen.getByLabelText("New email"), "new@example.com");
  await user.type(screen.getByLabelText("Current password"), "secret-pass");
  return user;
}

describe("changing the email", () => {
  it("sends the new address with the current password and says to check the inbox", async () => {
    fetchMock.mockResolvedValue(reply({ status: "ok" }));
    const user = await fill();
    await user.click(screen.getByRole("button", { name: "Change email" }));
    await screen.findByRole("dialog", { name: "Check your email" });
    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe("/api/company/profile/email/");
    expect(JSON.parse(init.body)).toEqual({
      email: "new@example.com",
      current_password: "secret-pass",
    });
  });

  it("empties the fields afterwards", async () => {
    fetchMock.mockResolvedValue(reply({ status: "ok" }));
    const user = await fill();
    await user.click(screen.getByRole("button", { name: "Change email" }));
    await screen.findByRole("dialog", { name: "Check your email" });
    await waitFor(() =>
      expect((screen.getByLabelText("New email") as HTMLInputElement).value).toBe(""),
    );
  });

  it("shows the server's message under the field that is wrong", async () => {
    fetchMock.mockResolvedValue(
      reply(
        {
          error: {
            code: "wrong_current_password",
            message: "Your current password is incorrect.",
            fields: { current_password: "Your current password is incorrect." },
          },
        },
        400,
      ),
    );
    const user = await fill();
    await user.click(screen.getByRole("button", { name: "Change email" }));
    expect(await screen.findByText("Your current password is incorrect.")).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
