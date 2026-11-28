import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CandidatePreferences } from "./CandidatePreferences";

const fetchMock = vi.fn();
const URL = "/api/company/projects/p1/preferences/";
const PREFERENCES = {
  hide_contact_by_default: false,
  auto_shortlist: false,
  auto_reject_below: null,
};
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
    reply(200, { ...PREFERENCES, hide_contact_by_default: true });
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
    reply(200, PREFERENCES);
    reply(200, { ...PREFERENCES, hide_contact_by_default: true });
    render(<CandidatePreferences projectId="p1" readOnly={false} />);
    await userEvent.click(
      await screen.findByLabelText("Hide contact details in new shared reports"),
    );
    await userEvent.click(screen.getByRole("button", { name: "Save candidate settings" }));
    expect(await screen.findByText("Candidate settings saved")).toBeTruthy();
    expect(fetchMock.mock.calls[1][0]).toBe(URL);
    expect(JSON.parse(fetchMock.mock.calls[1][1].body as string)).toEqual({
      ...PREFERENCES,
      hide_contact_by_default: true,
    });
  });

  it("shows a refusal in words and keeps the choice", async () => {
    reply(200, PREFERENCES);
    reply(409, { error: { code: "project_archived", message: "This project is archived." } });
    render(<CandidatePreferences projectId="p1" readOnly={false} />);
    await userEvent.click(
      await screen.findByLabelText("Hide contact details in new shared reports"),
    );
    await userEvent.click(screen.getByRole("button", { name: "Save candidate settings" }));
    expect((await screen.findByRole("alert")).textContent).toBe("This project is archived.");
  });

  it("cannot be changed on an archived project", async () => {
    reply(200, PREFERENCES);
    render(<CandidatePreferences projectId="p1" readOnly />);
    const box = (await screen.findByLabelText(
      "Hide contact details in new shared reports",
    )) as HTMLInputElement;
    expect(box.disabled).toBe(true);
    expect(screen.queryByRole("button", { name: "Save candidate settings" })).toBeNull();
  });

  it("saves the intake rules and turns the reject limit off when it is cleared", async () => {
    reply(200, { ...PREFERENCES, auto_reject_below: 30 });
    reply(200, { ...PREFERENCES, auto_shortlist: true });
    render(<CandidatePreferences projectId="p1" readOnly={false} />);
    const limit = (await screen.findByLabelText(
      "Reject new candidates scoring below",
    )) as HTMLInputElement;
    expect(limit.value).toBe("30");
    await userEvent.clear(limit);
    await userEvent.click(screen.getByLabelText("Shortlist strong matches automatically"));
    await userEvent.click(screen.getByRole("button", { name: "Save candidate settings" }));
    await screen.findByText("Candidate settings saved");
    expect(JSON.parse(fetchMock.mock.calls[1][1].body as string)).toEqual({
      hide_contact_by_default: false,
      auto_shortlist: true,
      auto_reject_below: null,
    });
  });

  it("shows a wrong limit next to its field", async () => {
    reply(200, PREFERENCES);
    reply(400, {
      error: {
        code: "invalid",
        message: "Check the form.",
        fields: { auto_reject_below: "Ensure this value is less than or equal to 100." },
      },
    });
    render(<CandidatePreferences projectId="p1" readOnly={false} />);
    await userEvent.type(
      await screen.findByLabelText("Reject new candidates scoring below"),
      "150",
    );
    await userEvent.click(screen.getByRole("button", { name: "Save candidate settings" }));
    expect(await screen.findByText("Ensure this value is less than or equal to 100.")).toBeTruthy();
  });
});
