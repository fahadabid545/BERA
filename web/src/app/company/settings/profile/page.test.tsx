import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ProfilePage from "./page";

const fetchMock = vi.fn();
const PROFILE = {
  name: "Mina Member",
  email: "mina@example.com",
  role: "member",
  company_name: "Co",
};
const reply = (body: unknown, status = 200) => ({
  ok: status < 400,
  status,
  json: async () => body,
});
let profileReply: ReturnType<typeof reply>;
const calls = (method: string) =>
  fetchMock.mock.calls.filter((call) => (call[1]?.method ?? "GET") === method);

beforeEach(() => {
  profileReply = reply(PROFILE);
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (path: string, init?: RequestInit) => {
    if (path === "/api/company/profile/") {
      return init?.method === "PATCH" ? profileReply : reply(PROFILE);
    }
    return reply({ rules: [], ok: false });
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("profile settings page", () => {
  it("shows the name and the email the person signs in with", async () => {
    render(<ProfilePage />);
    await waitFor(() =>
      expect((screen.getByLabelText("Name") as HTMLInputElement).value).toBe("Mina Member"),
    );
    const email = screen.getByLabelText("Email") as HTMLInputElement;
    expect(email.value).toBe("mina@example.com");
    expect(email.readOnly).toBe(true);
  });

  it("has sections to change the email and the password, and signs out of all devices", async () => {
    render(<ProfilePage />);
    expect(screen.getByRole("region", { name: "Change email" })).toBeTruthy();
    const section = screen.getByRole("region", { name: "Change password" });
    for (const label of ["Current password", "New password", "Confirm new password"]) {
      expect(within(section).getByLabelText(label, { selector: "input" })).toBeTruthy();
    }
    expect(screen.getByRole("button", { name: "Sign out of all devices" })).toBeTruthy();
  });

  it("cannot save until the name is changed", async () => {
    render(<ProfilePage />);
    await waitFor(() =>
      expect((screen.getByLabelText("Name") as HTMLInputElement).value).toBe("Mina Member"),
    );
    expect((screen.getByRole("button", { name: "Save" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("asks before saving, then saves and says so", async () => {
    render(<ProfilePage />);
    const user = userEvent.setup();
    const name = await screen.findByDisplayValue("Mina Member");
    await user.clear(name);
    await user.type(name, "Mina Better");
    profileReply = reply({ ...PROFILE, name: "Mina Better" });
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(calls("PATCH")).toHaveLength(0);
    const dialog = await screen.findByRole("dialog", { name: "Save profile" });
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    await screen.findByRole("dialog", { name: "Profile saved" });
    expect(JSON.parse(calls("PATCH")[0][1].body)).toEqual({ name: "Mina Better" });
  });

  it("cancelling saves nothing", async () => {
    render(<ProfilePage />);
    const user = userEvent.setup();
    const name = await screen.findByDisplayValue("Mina Member");
    await user.type(name, "x");
    await user.click(screen.getByRole("button", { name: "Save" }));
    const dialog = await screen.findByRole("dialog", { name: "Save profile" });
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(calls("PATCH")).toHaveLength(0);
  });

  it("shows the server's message for the name", async () => {
    render(<ProfilePage />);
    const user = userEvent.setup();
    const name = await screen.findByDisplayValue("Mina Member");
    await user.clear(name);
    await user.type(name, " ");
    profileReply = reply(
      { error: { code: "invalid", message: "Check the form.", fields: { name: "Enter a name." } } },
      400,
    );
    await user.click(screen.getByRole("button", { name: "Save" }));
    const dialog = await screen.findByRole("dialog", { name: "Save profile" });
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Enter a name.")).toBeTruthy();
  });
});
