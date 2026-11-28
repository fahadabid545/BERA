import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectOwner } from "./ProjectOwner";

const fetchMock = vi.fn();
const MEMBERS = [
  { id: 1, name: "Olga", status: "active" },
  { id: 2, name: "Mina", status: "active" },
  { id: 3, name: "Gone", status: "removed" },
];
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

describe("project owner", () => {
  it("names the current owner and offers only the other active members", async () => {
    reply(200, MEMBERS);
    render(<ProjectOwner projectId="p1" ownerId={1} onChanged={vi.fn()} />);
    await screen.findByRole("option", { name: "Mina" });
    const labels = screen.getAllByRole("option").map((option) => option.textContent);
    expect(labels).toEqual(["Olga", "Mina"]);
  });

  it("cannot change the owner until somebody else is chosen", async () => {
    reply(200, MEMBERS);
    render(<ProjectOwner projectId="p1" ownerId={1} onChanged={vi.fn()} />);
    await screen.findByRole("option", { name: "Mina" });
    expect(
      (screen.getByRole("button", { name: "Change owner" }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("asks first, then hands the project over and tells the page", async () => {
    reply(200, MEMBERS);
    reply(200, {});
    const onChanged = vi.fn();
    render(<ProjectOwner projectId="p1" ownerId={1} onChanged={onChanged} />);
    await userEvent.selectOptions(await screen.findByLabelText("Project owner"), "2");
    await userEvent.click(screen.getByRole("button", { name: "Change owner" }));
    expect(screen.getByText("Hand this project to Mina?")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getAllByRole("button", { name: "Change owner" }).at(-1)!);
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(fetchMock.mock.calls[1][0]).toBe("/api/company/projects/p1/owner/");
    expect(JSON.parse(fetchMock.mock.calls[1][1].body as string)).toEqual({ owner_id: 2 });
  });

  it("shows a refusal in words and does not tell the page", async () => {
    reply(200, MEMBERS);
    reply(400, {
      error: {
        code: "invalid",
        message: "Check the form.",
        fields: { owner_id: "Choose an active team member." },
      },
    });
    const onChanged = vi.fn();
    render(<ProjectOwner projectId="p1" ownerId={1} onChanged={onChanged} />);
    await userEvent.selectOptions(await screen.findByLabelText("Project owner"), "2");
    await userEvent.click(screen.getByRole("button", { name: "Change owner" }));
    await userEvent.click(screen.getAllByRole("button", { name: "Change owner" }).at(-1)!);
    expect((await screen.findByRole("alert")).textContent).toBe("Choose an active team member.");
    expect(onChanged).not.toHaveBeenCalled();
  });
});
