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

const NOTHING_DUE = { cvs: 0, projects: 0, shared_links: 0 };
const previews = () =>
  fetchMock.mock.calls.filter((c) => String(c[0]).includes("retention-preview"));

function serve(chosen: number | null, due = NOTHING_DUE) {
  fetchMock.mockReset();
  fetchMock.mockImplementation(async (path: string, init?: RequestInit) => {
    if (String(path).includes("retention-preview")) return reply(due);
    return reply(
      SETTINGS(init?.method === "PATCH" ? JSON.parse(init.body as string).retention_days : chosen),
    );
  });
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

  it("asks, then saves the choice", async () => {
    serve(null);
    render(<RetentionPage />);
    const user = userEvent.setup();
    await user.selectOptions(await screen.findByLabelText("Retention"), "30");
    await user.click(screen.getByRole("button", { name: "Save" }));
    const dialog = await screen.findByRole("dialog", { name: "Save retention" });
    expect(within(dialog).getByText(/older than 30 days are deleted automatically/)).toBeTruthy();
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

  it("shows what a shorter period deletes before asking, and sends the confirmation", async () => {
    serve(null, { cvs: 12, projects: 2, shared_links: 1 });
    render(<RetentionPage />);
    const user = userEvent.setup();
    await user.selectOptions(await screen.findByLabelText("Retention"), "30");
    await user.click(screen.getByRole("button", { name: "Save" }));
    const dialog = await screen.findByRole("dialog", { name: "Save retention" });
    expect(previews()[0][0]).toContain("days=30");
    expect(
      within(dialog).getByText(/Saving deletes 12 CVs in 2 projects and 1 shared link/),
    ).toBeTruthy();
    expect(patches()).toHaveLength(0);
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    await screen.findByRole("dialog", { name: "Retention saved" });
    expect(JSON.parse(patches()[0][1].body)).toEqual({
      retention_days: 30,
      acknowledge_deletion: true,
    });
  });

  it("does not ask for the confirmation flag when nothing would be deleted", async () => {
    serve(null, NOTHING_DUE);
    render(<RetentionPage />);
    const user = userEvent.setup();
    await user.selectOptions(await screen.findByLabelText("Retention"), "90");
    await user.click(screen.getByRole("button", { name: "Save" }));
    const dialog = await screen.findByRole("dialog", { name: "Save retention" });
    await user.click(within(dialog).getByRole("button", { name: "Save" }));
    await screen.findByRole("dialog", { name: "Retention saved" });
    expect(JSON.parse(patches()[0][1].body)).toEqual({ retention_days: 90 });
  });

  it("does not look at what is deleted when the period gets longer", async () => {
    serve(30, { cvs: 5, projects: 1, shared_links: 0 });
    render(<RetentionPage />);
    const user = userEvent.setup();
    await user.selectOptions(await screen.findByLabelText("Retention"), "365");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByRole("dialog", { name: "Save retention" });
    expect(previews()).toHaveLength(0);
  });

  it("says one CV and one project in the singular", async () => {
    serve(null, { cvs: 1, projects: 1, shared_links: 0 });
    render(<RetentionPage />);
    const user = userEvent.setup();
    await user.selectOptions(await screen.findByLabelText("Retention"), "30");
    await user.click(screen.getByRole("button", { name: "Save" }));
    const dialog = await screen.findByRole("dialog", { name: "Save retention" });
    expect(within(dialog).getByText(/Saving deletes 1 CV in 1 project,/)).toBeTruthy();
  });
});
