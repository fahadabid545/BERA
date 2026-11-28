import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RescoreAll } from "./RescoreAll";

const fetchMock = vi.fn();
const URL = "/api/company/projects/p1/rescore/";
function reply(status: number, body: unknown) {
  fetchMock.mockResolvedValueOnce({ ok: status < 400, status, json: async () => body });
}
const sent = (index: number) => JSON.parse(fetchMock.mock.calls[index][1].body as string);
const NEEDS_AGREEMENT = {
  error: {
    code: "rescoring_needed",
    message: "Scoring everything again means judging every CV against every requirement again.",
    details: { cvs: 12, requirements: 5, estimated_cost: "0.480000" },
  },
};

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("score all CVs again", () => {
  it("first asks the server, shows the count and cost, and only then runs", async () => {
    reply(409, NEEDS_AGREEMENT);
    reply(202, { queued: 12 });
    render(<RescoreAll projectId="p1" />);
    await userEvent.click(screen.getByRole("button", { name: "Score all CVs again" }));
    expect(
      await screen.findByText(
        "12 CVs will be judged against 5 requirements again. Estimated cost: 0.480000.",
      ),
    ).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(sent(0)).toEqual({});
    await userEvent.click(screen.getByRole("button", { name: "Score again" }));
    expect(await screen.findByText("Scoring started")).toBeTruthy();
    expect(fetchMock.mock.calls[1][0]).toBe(URL);
    expect(sent(1)).toEqual({ acknowledge_rescoring: true });
  });

  it("runs nothing when the popup is cancelled", async () => {
    reply(409, NEEDS_AGREEMENT);
    render(<RescoreAll projectId="p1" />);
    await userEvent.click(screen.getByRole("button", { name: "Score all CVs again" }));
    await userEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Scoring started")).toBeNull();
  });

  it("says in words when there is nothing to score", async () => {
    reply(409, {
      error: { code: "nothing_to_rescore", message: "There are no scored CVs to score again." },
    });
    render(<RescoreAll projectId="p1" />);
    await userEvent.click(screen.getByRole("button", { name: "Score all CVs again" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "There are no scored CVs to score again.",
    );
  });

  it("shows the refusal when the second request fails", async () => {
    reply(409, NEEDS_AGREEMENT);
    reply(500, { error: { code: "x", message: "Something went wrong." } });
    render(<RescoreAll projectId="p1" />);
    await userEvent.click(screen.getByRole("button", { name: "Score all CVs again" }));
    await userEvent.click(await screen.findByRole("button", { name: "Score again" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Something went wrong.");
  });
});
