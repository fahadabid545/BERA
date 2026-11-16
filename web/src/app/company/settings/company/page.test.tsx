import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CompanySettingsPage from "./page";

const fetchMock = vi.fn();
const SETTINGS = {
  name: "Acme Ltd",
  country: "DE",
  retention: { days: 180, chosen: null, default_days: 180, choices: [30, 90, 180, 365] },
};
const reply = (body: unknown, status = 200) => ({
  ok: status < 400,
  status,
  json: async () => body,
});
let patchReply = reply(SETTINGS);

beforeEach(() => {
  patchReply = reply(SETTINGS);
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (_path: string, init?: RequestInit) =>
    init?.method === "PATCH" ? patchReply : reply(SETTINGS),
  );
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("company settings page", () => {
  it("shows the company name and the billing country, which is locked", async () => {
    render(<CompanySettingsPage />);
    expect(await screen.findByDisplayValue("Acme Ltd")).toBeTruthy();
    const country = screen.getByLabelText("Billing country") as HTMLInputElement;
    expect(country.value).toBe("Germany");
    expect(country.disabled).toBe(true);
  });

  it("cannot save until the name is changed", async () => {
    render(<CompanySettingsPage />);
    await screen.findByDisplayValue("Acme Ltd");
    expect((screen.getByRole("button", { name: "Save" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("asks before saving, then sends only the name", async () => {
    render(<CompanySettingsPage />);
    const user = userEvent.setup();
    const name = await screen.findByDisplayValue("Acme Ltd");
    await user.type(name, " Group");
    patchReply = reply({ ...SETTINGS, name: "Acme Ltd Group" });
    await user.click(screen.getByRole("button", { name: "Save" }));
    const dialog = await screen.findByRole("dialog", { name: "Save company" });
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    await screen.findByRole("dialog", { name: "Company saved" });
    const call = fetchMock.mock.calls.find((c) => c[1]?.method === "PATCH");
    expect(JSON.parse(call![1].body)).toEqual({ name: "Acme Ltd Group" });
  });

  it("shows the server's refusal, for example to a member", async () => {
    fetchMock.mockImplementation(async () =>
      reply({ error: { code: "not_allowed", message: "You do not have access." } }, 403),
    );
    render(<CompanySettingsPage />);
    expect((await screen.findByRole("alert")).textContent).toBe("You do not have access.");
  });

  it("shows the server's message for the name", async () => {
    render(<CompanySettingsPage />);
    const user = userEvent.setup();
    const name = await screen.findByDisplayValue("Acme Ltd");
    await user.clear(name);
    patchReply = reply(
      { error: { code: "invalid", message: "Check.", fields: { name: "Enter a name." } } },
      400,
    );
    await user.type(name, " ");
    await user.click(screen.getByRole("button", { name: "Save" }));
    const dialog = await screen.findByRole("dialog", { name: "Save company" });
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.getByText("Enter a name.")).toBeTruthy());
  });
});
