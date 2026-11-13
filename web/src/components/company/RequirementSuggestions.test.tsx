import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { RequirementSuggestions } from "./RequirementSuggestions";

const fetchMock = vi.fn();
const URL = "/api/company/projects/p1/requirements/suggest/";

function reply(status: number, body: unknown) {
  fetchMock.mockResolvedValueOnce({ ok: status < 400, status, json: async () => body });
}
const result = (over: object = {}) => ({
  requirements: [],
  warnings: [],
  fallback: false,
  message: "",
  ...over,
});
const ask = () => userEvent.click(screen.getByRole("button", { name: "Suggest requirements" }));

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("requirement suggestions", () => {
  it("asks the server and lists must-have and nice-to-have requirements", async () => {
    reply(
      200,
      result({
        requirements: [
          { kind: "must", text: "5 years of Python" },
          { kind: "nice", text: "Kubernetes" },
        ],
      }),
    );
    render(<RequirementSuggestions projectId="p1" />);
    await ask();
    expect(await screen.findByText("5 years of Python")).toBeTruthy();
    expect(screen.getByText("Must have")).toBeTruthy();
    expect(screen.getByText("Nice to have")).toBeTruthy();
    expect(fetchMock.mock.calls[0][0]).toBe(URL);
    expect(fetchMock.mock.calls[0][1].method).toBe("POST");
  });

  it("shows warnings in words", async () => {
    reply(
      200,
      result({
        requirements: [{ kind: "must", text: "Python" }],
        warnings: [{ code: "other_language", message: "This description is not in English." }],
      }),
    );
    render(<RequirementSuggestions projectId="p1" />);
    await ask();
    expect(await screen.findByText("This description is not in English.")).toBeTruthy();
  });

  it("a fallback shows the friendly message and no table", async () => {
    reply(200, result({ fallback: true, message: "You can enter them yourself." }));
    render(<RequirementSuggestions projectId="p1" />);
    await ask();
    expect(await screen.findByText("You can enter them yourself.")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("a paused AI opens the Upgrade popup", async () => {
    reply(409, {
      error: {
        code: "ai_paused_token_cap",
        message: "Paused.",
        details: { limit: 1, prompt: "upgrade" },
      },
    });
    render(<RequirementSuggestions projectId="p1" />);
    await ask();
    expect(await screen.findByText("Upgrade your plan")).toBeTruthy();
  });

  it("another failure is shown in plain words", async () => {
    reply(500, { error: { code: "internal_error", message: "Something went wrong." } });
    render(<RequirementSuggestions projectId="p1" />);
    await ask();
    expect((await screen.findByRole("alert")).textContent).toBe("Something went wrong.");
  });
});
