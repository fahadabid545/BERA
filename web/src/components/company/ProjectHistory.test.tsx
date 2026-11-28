import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectHistory } from "./ProjectHistory";

const fetchMock = vi.fn();
function reply(status: number, body: unknown) {
  fetchMock.mockResolvedValueOnce({ ok: status < 400, status, json: async () => body });
}
const ENTRY = {
  id: "1",
  kind: "project_changed",
  actor_name: "Olga",
  target_kind: "project",
  target_id: "p1",
  details: { change: "job_description" },
  created_at: "2026-11-28T10:15:00Z",
};

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("project history", () => {
  it("lists when, who and what", async () => {
    reply(200, { entries: [ENTRY] });
    render(<ProjectHistory projectId="p1" />);
    expect(await screen.findByText("Changed the project's job description")).toBeTruthy();
    expect(screen.getByText("Olga")).toBeTruthy();
    expect(screen.getByText("2026-11-28 10:15")).toBeTruthy();
  });

  it("shows nothing while there is no history", async () => {
    reply(200, { entries: [] });
    const { container } = render(<ProjectHistory projectId="p1" />);
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });

  it("says plainly when it cannot load", async () => {
    reply(500, { code: "x", message: "Something went wrong." });
    render(<ProjectHistory projectId="p1" />);
    expect((await screen.findByRole("alert")).textContent).toContain("Something went wrong.");
  });
});
