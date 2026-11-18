import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ActivityLog, sentence } from "./ActivityLog";

const fetchMock = vi.fn();
const entry = (over: object = {}) => ({
  id: "e1",
  kind: "upload",
  actor_name: "Olu Owner",
  target_kind: "",
  target_id: "",
  details: {},
  created_at: "2030-01-05T09:30:12Z",
  ...over,
});
const people = [
  { id: 1, name: "Mina Member" },
  { id: 2, name: "Olu Owner" },
];
const answer = (entries: object[], over: object = {}) => ({
  entries,
  next_before: null,
  people,
  ...over,
});
function serve(body: object, status = 200) {
  fetchMock.mockImplementation(async () => ({
    ok: status === 200,
    status,
    json: async () => body,
  }));
}
const urls = () => fetchMock.mock.calls.map((call) => call[0] as string);

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("the activity log", () => {
  it("shows when, who and what for each entry", async () => {
    serve(answer([entry(), entry({ id: "e2", kind: "share", actor_name: "Mina Member" })]));
    render(<ActivityLog />);
    const table = await screen.findByRole("region", { name: "Activity log" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(
      rows.map((row) =>
        within(row)
          .getAllByRole("cell")
          .map((c) => c.textContent),
      ),
    ).toEqual([
      ["2030-01-05 09:30", "Olu Owner", "Uploaded CVs", ""],
      ["2030-01-05 09:30", "Mina Member", "Made a report link", ""],
    ]);
  });

  it("links an entry about a project, except a deleted one", async () => {
    serve(
      answer([
        entry({ id: "a", kind: "share", target_kind: "project", target_id: "p1" }),
        entry({ id: "b", kind: "project_deleted", target_kind: "project", target_id: "p2" }),
      ]),
    );
    render(<ActivityLog />);
    const links = await screen.findAllByRole("link", { name: "Open project" });
    expect(links).toHaveLength(1);
    expect(links[0].getAttribute("href")).toBe("/company/projects/p1");
  });

  it("asks for the filters chosen, person and days", async () => {
    serve(answer([entry()]));
    render(<ActivityLog />);
    const user = userEvent.setup();
    await user.selectOptions(await screen.findByLabelText("Person"), "1");
    await user.type(screen.getByLabelText("From"), "2030-01-01");
    await user.type(screen.getByLabelText("To"), "2030-01-31");
    await waitFor(() =>
      expect(urls()).toContain("/api/company/activity/?actor=1&since=2030-01-01&until=2030-01-31"),
    );
  });

  it("offers every person in the log", async () => {
    serve(answer([entry()]));
    render(<ActivityLog />);
    const select = (await screen.findByLabelText("Person")) as HTMLSelectElement;
    expect([...select.options].map((option) => option.text)).toEqual([
      "Everyone",
      "Mina Member",
      "Olu Owner",
    ]);
  });

  it("names the system as the doer of an entry made by the daily clean-up", async () => {
    serve(answer([entry({ kind: "data_expired", actor_name: "", details: { files: 2 } })]));
    render(<ActivityLog />);
    expect(await screen.findByText("System")).toBeTruthy();
  });

  it("clears the filters", async () => {
    serve(answer([entry()]));
    render(<ActivityLog />);
    const user = userEvent.setup();
    await user.selectOptions(await screen.findByLabelText("Person"), "1");
    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    await waitFor(() => expect(urls().at(-1)).toBe("/api/company/activity/"));
    expect((screen.getByLabelText("Person") as HTMLSelectElement).value).toBe("");
  });

  it("says so when nothing matches", async () => {
    serve(answer([]));
    render(<ActivityLog />);
    expect((await screen.findByRole("status")).textContent).toBe(
      "No activity matches these filters.",
    );
  });

  it("loads older entries after the last one shown", async () => {
    serve(answer([entry()], { next_before: "2030-01-05T09:30:12Z" }));
    render(<ActivityLog />);
    const user = userEvent.setup();
    serve(answer([entry({ id: "e9", kind: "download" })]));
    await user.click(await screen.findByRole("button", { name: "Older" }));
    await waitFor(() => expect(screen.getByText("Downloaded a CV")).toBeTruthy());
    expect(urls().at(-1)).toBe("/api/company/activity/?before=2030-01-05T09%3A30%3A12Z");
    expect(screen.queryByRole("button", { name: "Older" })).toBeNull();
  });

  it("keeps the filters when loading older entries", async () => {
    serve(answer([entry()], { next_before: "2030-01-05T09:30:12Z" }));
    render(<ActivityLog />);
    const user = userEvent.setup();
    await user.selectOptions(await screen.findByLabelText("Person"), "2");
    await user.click(await screen.findByRole("button", { name: "Older" }));
    expect(urls().at(-1)).toContain("actor=2&before=");
  });

  it("shows nothing to someone the server refuses", async () => {
    serve({ error: { code: "not_allowed", message: "No." } }, 403);
    const { container } = render(<ActivityLog />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });

  it("shows the server's message when the log cannot be read", async () => {
    serve({ error: { code: "internal_error", message: "Something went wrong." } }, 500);
    render(<ActivityLog />);
    expect((await screen.findByRole("alert")).textContent).toBe("Something went wrong.");
  });
});

describe("the sentence of an entry", () => {
  const say = (kind: string, details = {}) => sentence(entry({ kind, details }));

  it.each([
    ["download", { scope: "cv", files: 1 }, "Downloaded a CV"],
    ["download", { scope: "package", files: 3 }, "Downloaded a zip of 3 CVs"],
    ["download", { scope: "package", files: 1 }, "Downloaded a zip of 1 CV"],
    ["download", { scope: "list", format: "pdf" }, "Downloaded the ranked list as a PDF"],
    ["download", { scope: "list", format: "xlsx" }, "Downloaded the ranked list as a spreadsheet"],
    ["share", { action: "revoked" }, "Revoked a report link"],
    ["member_removed", { removed_name: "Mina" }, "Removed Mina from the team"],
    ["ownership_transferred", { new_owner_name: "Mina" }, "Handed ownership to Mina"],
    ["invite_sent", {}, "Invited a member"],
    ["project_deleted", {}, "Deleted a project"],
    ["data_expired", { files: 4, shared_links: 1 }, "Deleted 4 CVs past the retention period"],
    ["data_expired", { files: 1, shared_links: 0 }, "Deleted 1 CV past the retention period"],
    ["something_new", {}, "something new"],
  ])("%s %j says %s", (kind, details, words) => {
    expect(say(kind, details)).toBe(words);
  });
});
