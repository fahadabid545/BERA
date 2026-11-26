import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { UsageHistory } from "./UsageHistory";

const fetchMock = vi.fn();
const figures = (over: object = {}) => ({
  cvs: 3,
  tokens_in: 100,
  tokens_out: 42,
  tokens: 142,
  estimated_cost: "0.850000",
  ...over,
});
const feb = {
  id: "p2",
  start: "2030-02-01T00:00:00Z",
  end: "2030-03-01T00:00:00Z",
  ...figures({ cvs: 1 }),
};
const jan = { id: "p1", start: "2030-01-01T00:00:00Z", end: "2030-02-01T00:00:00Z", ...figures() };
const uploads = Array.from({ length: 7 }, () => Array<number>(24).fill(0));
const history = (over: object = {}) => ({
  periods: [feb, jan],
  selected: "p2",
  projects: [{ project_id: "a", title: "Backend", ...figures({ cvs: 1 }) }],
  uploads,
  ...over,
});
function serve(body: object, ok = true) {
  fetchMock.mockImplementation(async () => ({
    ok,
    status: ok ? 200 : 403,
    json: async () => body,
  }));
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("usage history", () => {
  it("lists CVs and estimated cost for each period", async () => {
    serve(history());
    render(<UsageHistory />);
    const table = await screen.findByRole("region", { name: "Usage by period" });
    const row = within(table).getByRole("row", { name: /1 Jan 2030 to 1 Feb 2030/ });
    expect(
      within(row)
        .getAllByRole("cell")
        .map((cell) => cell.textContent),
    ).toEqual(["3", "$0.85"]);
  });

  it("lists the projects of the chosen period", async () => {
    serve(history());
    render(<UsageHistory />);
    const table = await screen.findByRole("region", { name: "Usage by project" });
    expect(within(table).getByRole("rowheader", { name: "Backend" })).toBeTruthy();
  });

  it("names a deleted project and work with no project", async () => {
    serve(
      history({
        projects: [
          { project_id: "gone", title: null, ...figures() },
          { project_id: null, title: null, ...figures() },
        ],
      }),
    );
    render(<UsageHistory />);
    expect(await screen.findByRole("rowheader", { name: "Deleted project" })).toBeTruthy();
    expect(screen.getByRole("rowheader", { name: "No project" })).toBeTruthy();
  });

  it("asks again for another period when it is chosen", async () => {
    serve(history());
    render(<UsageHistory />);
    const select = await screen.findByLabelText("Period");
    await userEvent.setup().selectOptions(select, "p1");
    await waitFor(() =>
      expect(fetchMock.mock.calls.map((call) => call[0])).toContain(
        "/api/company/usage/history/?period=p1",
      ),
    );
  });

  it("shows when CVs are uploaded", async () => {
    serve(history());
    render(<UsageHistory />);
    expect(await screen.findByRole("group", { name: "Uploads by weekday and hour" })).toBeTruthy();
  });

  it("shows nothing for someone the server refuses", async () => {
    serve({ error: { code: "not_allowed", message: "No." } }, false);
    const { container } = render(<UsageHistory />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });

  it("shows nothing before there is any usage", async () => {
    serve(history({ periods: [], selected: null, projects: [], uploads: [] }));
    const { container } = render(<UsageHistory />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });
});
