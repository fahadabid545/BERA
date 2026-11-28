import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CandidatePreferences } from "./CandidatePreferences";

const fetchMock = vi.fn();
const URL = "/api/company/projects/p1/preferences/";
function reply(status: number, body: unknown) {
  fetchMock.mockResolvedValueOnce({ ok: status < 400, status, json: async () => body });
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("candidate preferences", () => {
  it("shows the saved choice and keeps Save off until something changes", async () => {
    reply(200, { hide_contact_by_default: true });
    render(<CandidatePreferences projectId="p1" readOnly={false} />);
    const box = (await screen.findByLabelText(
      "Hide contact details in new shared reports",
    )) as HTMLInputElement;
    expect(box.checked).toBe(true);
    expect(
      (screen.getByRole("button", { name: "Save candidate settings" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  });

  it("saves the change and confirms in a popup", async () => {
    reply(200, { hide_contact_by_default: false });
    reply(200, { hide_contact_by_default: true });
    render(<CandidatePreferences projectId="p1" readOnly={false} />);
    await userEvent.click(
      await screen.findByLabelText("Hide contact details in new shared reports"),
    );
    await userEvent.click(screen.getByRole("button", { name: "Save candidate settings" }));
    expect(await screen.findByText("Candidate settings saved")).toBeTruthy();
    expect(fetchMock.mock.calls[1][0]).toBe(URL);
    expect(JSON.parse(fetchMock.mock.calls[1][1].body as string)).toEqual({
      hide_contact_by_default: true,
    });
  });

  it("shows a refusal in words and keeps the choice", async () => {
    reply(200, { hide_contact_by_default: false });
    reply(409, { error: { code: "project_archived", message: "This project is archived." } });
    render(<CandidatePreferences projectId="p1" readOnly={false} />);
    await userEvent.click(
      await screen.findByLabelText("Hide contact details in new shared reports"),
    );
    await userEvent.click(screen.getByRole("button", { name: "Save candidate settings" }));
    expect((await screen.findByRole("alert")).textContent).toBe("This project is archived.");
  });

  it("cannot be changed on an archived project", async () => {
    reply(200, { hide_contact_by_default: false });
    render(<CandidatePreferences projectId="p1" readOnly />);
    const box = (await screen.findByLabelText(
      "Hide contact details in new shared reports",
    )) as HTMLInputElement;
    expect(box.disabled).toBe(true);
    expect(screen.queryByRole("button", { name: "Save candidate settings" })).toBeNull();
  });
});
