import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectSettings } from "./ProjectSettings";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const fetchMock = vi.fn();
const BASE = "/api/company/projects/p1/";
const ACTIVE = {
  id: "p1",
  title: "Backend engineer",
  job_description: "Looks after servers",
  status: "active",
  may_delete: true,
};

function reply(status: number, body: unknown) {
  fetchMock.mockResolvedValueOnce({ ok: status < 400, status, json: async () => body });
}
const calls = () => fetchMock.mock.calls.map((call) => [call[0], call[1]?.method ?? "GET"]);
const body = (index: number) => JSON.parse(fetchMock.mock.calls[index][1].body as string);

beforeEach(() => {
  push.mockReset();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("project settings", () => {
  it("shows the project's text for editing", async () => {
    reply(200, ACTIVE);
    render(<ProjectSettings projectId="p1" />);
    expect(((await screen.findByLabelText("Project title")) as HTMLInputElement).value).toBe(
      "Backend engineer",
    );
    expect((screen.getByLabelText("Job description") as HTMLTextAreaElement).value).toBe(
      "Looks after servers",
    );
    expect(calls()[0]).toEqual([BASE, "GET"]);
  });

  it("Save sends the changes and confirms in a popup", async () => {
    reply(200, ACTIVE);
    reply(200, { ...ACTIVE, title: "New title" });
    render(<ProjectSettings projectId="p1" />);
    const title = await screen.findByLabelText("Project title");
    await userEvent.clear(title);
    await userEvent.type(title, "New title");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Project saved")).toBeTruthy();
    expect(calls()[1]).toEqual([BASE, "PATCH"]);
    expect(body(1)).toEqual({ title: "New title", job_description: "Looks after servers" });
  });

  it("shows field mistakes next to the field", async () => {
    reply(200, ACTIVE);
    reply(400, {
      error: { code: "validation_error", message: "Check.", fields: { title: "Too long." } },
    });
    render(<ProjectSettings projectId="p1" />);
    await screen.findByLabelText("Project title");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Too long.")).toBeTruthy();
  });

  it("Archive asks first, then archives and shows Restore", async () => {
    reply(200, ACTIVE);
    reply(200, { ...ACTIVE, status: "archived" });
    render(<ProjectSettings projectId="p1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Archive project" }));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole("button", { name: "Archive" }));
    expect(await screen.findByRole("button", { name: "Restore project" })).toBeTruthy();
    expect(calls()[1]).toEqual([`${BASE}archive/`, "POST"]);
  });

  it("an archived project is read-only: no Save, fields cannot be edited", async () => {
    reply(200, { ...ACTIVE, status: "archived" });
    render(<ProjectSettings projectId="p1" />);
    expect(((await screen.findByLabelText("Project title")) as HTMLInputElement).readOnly).toBe(
      true,
    );
    expect((screen.getByLabelText("Job description") as HTMLTextAreaElement).readOnly).toBe(true);
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
  });

  it("Restore asks first, then restores", async () => {
    reply(200, { ...ACTIVE, status: "archived" });
    reply(200, ACTIVE);
    render(<ProjectSettings projectId="p1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Restore project" }));
    await userEvent.click(screen.getByRole("button", { name: "Restore" }));
    expect(await screen.findByRole("button", { name: "Archive project" })).toBeTruthy();
    expect(calls()[1]).toEqual([`${BASE}restore/`, "POST"]);
  });

  it("restoring at the project limit opens the Upgrade popup", async () => {
    reply(200, { ...ACTIVE, status: "archived" });
    reply(409, {
      error: {
        code: "project_limit_reached",
        message: "Limit.",
        details: { limit: 2, prompt: "upgrade" },
      },
    });
    render(<ProjectSettings projectId="p1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Restore project" }));
    await userEvent.click(screen.getByRole("button", { name: "Restore" }));
    expect(await screen.findByText("Upgrade your plan")).toBeTruthy();
  });

  it("Delete needs the title typed, then goes back to the list", async () => {
    reply(200, ACTIVE);
    reply(204, null);
    render(<ProjectSettings projectId="p1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Delete project" }));
    await userEvent.type(screen.getByLabelText(/Type .* to confirm/), "Backend engineer");
    const buttons = screen.getAllByRole("button", { name: "Delete project" });
    await userEvent.click(buttons[buttons.length - 1]);
    await waitFor(() => expect(push).toHaveBeenCalledWith("/company/projects"));
    expect(calls()[1]).toEqual([BASE, "DELETE"]);
    expect(body(1)).toEqual({ confirm_title: "Backend engineer" });
  });

  it("a wrong title shows the mistake and does not leave the page", async () => {
    reply(200, ACTIVE);
    reply(400, {
      error: {
        code: "validation_error",
        message: "Check.",
        fields: { confirm_title: "Type the project title exactly to confirm." },
      },
    });
    render(<ProjectSettings projectId="p1" />);
    await userEvent.click(await screen.findByRole("button", { name: "Delete project" }));
    const buttons = screen.getAllByRole("button", { name: "Delete project" });
    await userEvent.click(buttons[buttons.length - 1]);
    expect(await screen.findByText("Type the project title exactly to confirm.")).toBeTruthy();
    expect(push).not.toHaveBeenCalled();
  });

  it("hides Delete when the person may not delete", async () => {
    reply(200, { ...ACTIVE, may_delete: false });
    render(<ProjectSettings projectId="p1" />);
    await screen.findByLabelText("Project title");
    expect(screen.queryByRole("button", { name: "Delete project" })).toBeNull();
  });

  it("says plainly when the project cannot be loaded", async () => {
    reply(404, { error: { code: "not_found", message: "Not found." } });
    render(<ProjectSettings projectId="p1" />);
    expect((await screen.findByRole("alert")).textContent).toBe("Not found.");
  });
});
