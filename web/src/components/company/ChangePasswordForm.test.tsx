import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChangePasswordForm } from "./ChangePasswordForm";

const HINTS = {
  rules: [{ id: "min_length", text: "At least 12 characters", met: true }],
  ok: true,
};

function stubServer(status: number, body: unknown) {
  const fetchMock = vi.fn(async (path: string) =>
    path.endsWith("/password-check/")
      ? new Response(JSON.stringify(HINTS), { status: 200 })
      : new Response(JSON.stringify(body), { status }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const changeCalls = (server: ReturnType<typeof stubServer>) =>
  server.mock.calls.filter(([path]) => String(path).endsWith("/change-password/"));

async function fillIn(
  current = "old-password-value",
  next = "brand-new-password-1",
  confirm = next,
) {
  await userEvent.type(screen.getByLabelText("Current password"), current);
  await userEvent.type(screen.getByLabelText("New password"), next);
  await userEvent.type(screen.getByLabelText("Confirm new password"), confirm);
  await userEvent.click(screen.getByRole("button", { name: "Change password" }));
}

const refusal = (fields: Record<string, string>) => ({
  error: { code: "validation_error", message: "x", fields },
});

afterEach(() => vi.unstubAllGlobals());

describe("change password", () => {
  it("has the three fields and shows the live hints under the new password", async () => {
    stubServer(200, {});
    render(<ChangePasswordForm />);
    for (const label of ["Current password", "New password", "Confirm new password"]) {
      expect((screen.getByLabelText(label) as HTMLInputElement).type).toBe("password");
    }
    expect(await screen.findByText("At least 12 characters: met")).toBeTruthy();
  });

  it("sends all three entries", async () => {
    const server = stubServer(200, { status: "ok" });
    render(<ChangePasswordForm />);
    await fillIn();
    await waitFor(() => expect(changeCalls(server)).toHaveLength(1));
    const [path, init] = changeCalls(server)[0] as unknown as [string, RequestInit];
    expect(path).toBe("/api/auth/company/change-password/");
    expect(JSON.parse(String(init.body))).toEqual({
      current_password: "old-password-value",
      password: "brand-new-password-1",
      confirm_password: "brand-new-password-1",
    });
  });

  it("confirms in a popup and empties the fields", async () => {
    stubServer(200, { status: "ok" });
    render(<ChangePasswordForm />);
    await fillIn();
    const popup = await screen.findByRole("dialog");
    expect(within(popup).getByText(/other devices were signed out/)).toBeTruthy();
    await userEvent.click(within(popup).getByRole("button", { name: "Close" }));
    expect((screen.getByLabelText("Current password") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("New password") as HTMLInputElement).value).toBe("");
  });

  it("shows a wrong current password under that field, and nothing else", async () => {
    stubServer(400, refusal({ current_password: "Your current password is incorrect." }));
    render(<ChangePasswordForm />);
    await fillIn();
    expect(await screen.findByText("Your current password is incorrect.")).toBeTruthy();
    expect(screen.getByLabelText("Current password").getAttribute("aria-invalid")).toBe("true");
    expect(screen.getByLabelText("New password").getAttribute("aria-invalid")).toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("keeps what was typed after a refusal", async () => {
    stubServer(400, refusal({ password: "Use at least 12 characters." }));
    render(<ChangePasswordForm />);
    await fillIn("old-password-value", "short");
    await screen.findByText("Use at least 12 characters.");
    expect((screen.getByLabelText("New password") as HTMLInputElement).value).toBe("short");
  });

  it("shows the pause when too many wrong entries were made", async () => {
    stubServer(429, {
      error: { code: "too_many_requests", message: "Too many attempts. Try again in 15 minutes." },
    });
    render(<ChangePasswordForm />);
    await fillIn();
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Too many attempts. Try again in 15 minutes.",
    );
  });

  it("shows a mismatch reported by the server under the confirm field", async () => {
    stubServer(400, refusal({ confirm_password: "The passwords do not match." }));
    render(<ChangePasswordForm />);
    await fillIn("old-password-value", "brand-new-password-1", "brand-new-password-1");
    expect(await screen.findByText("The passwords do not match.")).toBeTruthy();
  });
});
