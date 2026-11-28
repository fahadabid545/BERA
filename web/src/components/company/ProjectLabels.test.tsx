import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectLabels } from "./ProjectLabels";

const fetchMock = vi.fn();
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

describe("project labels", () => {
  it("shows the saved labels and cannot save until they change", async () => {
    reply(200, { labels: ["Sales", "Remote"] });
    render(<ProjectLabels projectId="p1" readOnly={false} />);
    const input = (await screen.findByLabelText("Labels, separated by commas")) as HTMLInputElement;
    expect(input.value).toBe("Sales, Remote");
    expect(
      (screen.getByRole("button", { name: "Save labels" }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("sends the typed list, trimmed, and confirms in a popup", async () => {
    reply(200, { labels: [] });
    render(<ProjectLabels projectId="p1" readOnly={false} />);
    await userEvent.type(
      await screen.findByLabelText("Labels, separated by commas"),
      " Sales , ,Remote",
    );
    reply(200, { labels: ["Sales", "Remote"] });
    await userEvent.click(screen.getByRole("button", { name: "Save labels" }));
    await screen.findByText("Labels saved");
    const [, options] = fetchMock.mock.calls.at(-1)!;
    expect(JSON.parse(options.body)).toEqual({ labels: ["Sales", "Remote"] });
  });

  it("shows the server's message when the list is refused", async () => {
    reply(200, { labels: [] });
    render(<ProjectLabels projectId="p1" readOnly={false} />);
    await userEvent.type(await screen.findByLabelText("Labels, separated by commas"), "a");
    reply(400, {
      error: { code: "invalid", message: "Fix it.", fields: { labels: "At most 5 labels." } },
    });
    await userEvent.click(screen.getByRole("button", { name: "Save labels" }));
    await waitFor(() => expect(screen.getByText("At most 5 labels.")).toBeTruthy());
  });

  it("is read-only on an archived project", async () => {
    reply(200, { labels: ["Sales"] });
    render(<ProjectLabels projectId="p1" readOnly />);
    await screen.findByLabelText("Labels, separated by commas");
    expect(screen.queryByRole("button", { name: "Save labels" })).toBeNull();
  });
});
