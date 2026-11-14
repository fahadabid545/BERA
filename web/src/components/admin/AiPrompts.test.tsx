import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AiPrompts } from "./AiPrompts";

const fetchMock = vi.fn();
const version = (kind: string, number: number, extra = {}) => ({
  kind,
  number,
  created_at: "2026-11-14T10:00:00Z",
  text: `${kind} text ${number}`,
  current: false,
  projects: 0,
  ...extra,
});
const OVERVIEW = {
  reading: [
    version("reading", 1, { projects: 2 }),
    version("reading", 2, { current: true }),
    version("reading", 3),
  ],
  scoring: [version("scoring", 1, { current: true })],
};

function reply(status: number, body: unknown) {
  fetchMock.mockResolvedValueOnce({ ok: status < 400, status, json: async () => body });
}
const call = (index: number) => ({
  url: fetchMock.mock.calls[index][0] as string,
  init: fetchMock.mock.calls[index][1],
  body: JSON.parse((fetchMock.mock.calls[index][1].body as string) ?? "{}"),
});
const button = (name: string) => screen.getByRole("button", { name }) as HTMLButtonElement;

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function shown() {
  reply(200, OVERVIEW);
  render(<AiPrompts />);
  await screen.findByRole("region", { name: "Reading versions" });
}

describe("prompt versions list", () => {
  it("lists the versions of the open kind with the current one marked", async () => {
    await shown();
    const table = screen.getByRole("region", { name: "Reading versions" });
    expect(within(table).getAllByRole("row")).toHaveLength(4);
    expect(within(table).getByText("Current")).toBeTruthy();
  });

  it("shows the other kind on its own tab", async () => {
    await shown();
    await userEvent.click(screen.getByRole("tab", { name: "Scoring" }));
    const table = await screen.findByRole("region", { name: "Scoring versions" });
    expect(within(table).getAllByRole("row")).toHaveLength(2);
  });

  it("does not offer to delete a version that is current or used by a project", async () => {
    await shown();
    expect(button("Delete version 1").disabled).toBe(true);
    expect(button("Delete version 2").disabled).toBe(true);
    expect(button("Delete version 3").disabled).toBe(false);
    expect(button("Make version 2 current").disabled).toBe(true);
  });

  it("shows an error when the list cannot be loaded", async () => {
    reply(403, { error: { code: "forbidden", message: "You do not have access." } });
    render(<AiPrompts />);
    expect((await screen.findByRole("alert")).textContent).toBe("You do not have access.");
  });
});

describe("creating, choosing and deleting versions", () => {
  it("starts a new version from the current text", async () => {
    await shown();
    await userEvent.click(button("New version"));
    const dialog = screen.getByRole("dialog");
    const text = within(dialog).getByLabelText("Instructions") as HTMLTextAreaElement;
    expect(text.value).toBe("reading text 2");
    await userEvent.clear(text);
    await userEvent.type(text, "Better instructions");
    reply(201, {});
    reply(200, OVERVIEW);
    await userEvent.click(within(dialog).getByRole("button", { name: "Create version" }));
    expect(call(1).url).toBe("/api/admin/ai/prompts/");
    expect(call(1).body).toEqual({ kind: "reading", text: "Better instructions" });
  });

  it("makes a version current with a reason", async () => {
    await shown();
    await userEvent.click(button("Make version 3 current"));
    await userEvent.type(screen.getByLabelText("Reason"), "Better results");
    reply(200, {});
    reply(200, OVERVIEW);
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Make current" }),
    );
    expect(call(1).init.method).toBe("PUT");
    expect(call(1).body).toEqual({ kind: "reading", number: 3, reason: "Better results" });
  });

  it("deletes an unused version with a reason", async () => {
    await shown();
    await userEvent.click(button("Delete version 3"));
    await userEvent.type(screen.getByLabelText("Reason"), "Not needed");
    reply(204, {});
    reply(200, OVERVIEW);
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Delete version" }),
    );
    expect(call(1).url).toBe("/api/admin/ai/prompts/reading/3/");
    expect(call(1).init.method).toBe("DELETE");
    expect(call(1).body).toEqual({ reason: "Not needed" });
  });

  it("shows the server's refusal in plain words", async () => {
    await shown();
    await userEvent.click(button("Make version 3 current"));
    reply(400, { error: { code: "reason_required", message: "A reason is required." } });
    await userEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Make current" }),
    );
    expect((await screen.findByRole("alert")).textContent).toBe("A reason is required.");
  });
});

describe("moving a project and comparing", () => {
  it("moves one project to a chosen version", async () => {
    await shown();
    await userEvent.click(button("Move project"));
    const dialog = screen.getByRole("dialog");
    await userEvent.type(within(dialog).getByLabelText("Project ID"), "abc-123");
    await userEvent.selectOptions(within(dialog).getByLabelText("Version"), "3");
    await userEvent.type(within(dialog).getByLabelText("Reason"), "Customer asked");
    reply(200, {});
    reply(200, OVERVIEW);
    await userEvent.click(within(dialog).getByRole("button", { name: "Move project" }));
    expect(call(1).url).toBe("/api/admin/ai/prompts/move-project/");
    expect(call(1).body).toEqual({
      project_id: "abc-123",
      kind: "reading",
      number: 3,
      reason: "Customer asked",
    });
  });

  it("shows two versions side by side with the differences in words", async () => {
    await shown();
    reply(200, {
      rows: [
        { left: "Same line", right: "Same line", changed: false },
        { left: "Old line", right: "New line", changed: true },
      ],
    });
    await userEvent.click(button("Compare versions"));
    const table = await screen.findByRole("region", { name: "Comparison" });
    expect(call(1).url).toBe("/api/admin/ai/prompts/compare/?kind=reading&left=1&right=3");
    expect(within(table).getByText("Old line")).toBeTruthy();
    expect(within(table).getByText("New line")).toBeTruthy();
    expect(within(table).getAllByText("Changed")).toHaveLength(1);
  });
});
