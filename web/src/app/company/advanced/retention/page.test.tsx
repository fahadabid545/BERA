import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RetentionPage from "./page";

const fetchMock = vi.fn();
const SETTINGS = (chosen: number | null) => ({
  name: "Acme",
  country: "DE",
  retention: { days: chosen ?? 180, chosen, default_days: 180, choices: [30, 90, 180, 365] },
});
const reply = (body: unknown, status = 200) => ({
  ok: status < 400,
  status,
  json: async () => body,
});
const patches = () => fetchMock.mock.calls.filter((c) => c[1]?.method === "PATCH");

function serve(chosen: number | null) {
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (_path: string, init?: RequestInit) =>
    reply(
      SETTINGS(init?.method === "PATCH" ? JSON.parse(init.body as string).retention_days : chosen),
    ),
  );
}

beforeEach(() => vi.stubGlobal("fetch", fetchMock));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("retention settings page", () => {
  it("offers the platform default and the platform's choices", async () => {
    serve(null);
    render(<RetentionPage />);
    const selector = (await screen.findByLabelText("Retention")) as HTMLSelectElement;
    expect(Array.from(selector.options).map((option) => option.text)).toEqual([
      "Platform default (180 days)",
      "30 days",
      "90 days",
      "180 days",
      "365 days",
    ]);
    expect(selector.value).toBe("default");
  });

  it("starts on the company's own choice", async () => {
    serve(90);
    render(<RetentionPage />);
    expect(((await screen.findByLabelText("Retention")) as HTMLSelectElement).value).toBe("90");
  });

  it("cannot save without a change", async () => {
    serve(null);
    render(<RetentionPage />);
    await screen.findByLabelText("Retention");
    expect((screen.getByRole("button", { name: "Save" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("says what will be hidden, asks, then saves the choice", async () => {
    serve(null);
    render(<RetentionPage />);
    const user = userEvent.setup();
    await user.selectOptions(await screen.findByLabelText("Retention"), "30");
    await user.click(screen.getByRole("button", { name: "Save" }));
    const dialog = await screen.findByRole("dialog", { name: "Save retention" });
    expect(within(dialog).getByText(/older than 30 days/)).toBeTruthy();
    expect(patches()).toHaveLength(0);
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    await screen.findByRole("dialog", { name: "Retention saved" });
    expect(JSON.parse(patches()[0][1].body)).toEqual({ retention_days: 30 });
  });

  it("goes back to the platform default with null", async () => {
    serve(90);
    render(<RetentionPage />);
    const user = userEvent.setup();
    await user.selectOptions(await screen.findByLabelText("Retention"), "default");
    await user.click(screen.getByRole("button", { name: "Save" }));
    const dialog = await screen.findByRole("dialog", { name: "Save retention" });
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    await screen.findByRole("dialog", { name: "Retention saved" });
    expect(JSON.parse(patches()[0][1].body)).toEqual({ retention_days: null });
  });

  it("shows the server's refusal", async () => {
    fetchMock.mockReset();
    fetchMock.mockImplementation(async () =>
      reply({ error: { code: "not_allowed", message: "You do not have access." } }, 403),
    );
    render(<RetentionPage />);
    expect((await screen.findByRole("alert")).textContent).toBe("You do not have access.");
  });
});
